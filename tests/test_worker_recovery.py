from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from threading import (
	Event,
	Thread,
	current_thread,
)
from time import (
	monotonic,
	sleep,
)
from unittest import (
	TestCase,
	main,
)
from unittest.mock import (
	Mock,
	patch,
)

from pika.exceptions import (
	ChannelClosedByBroker,
	ConnectionClosedByBroker,
	ProbableAuthenticationError,
	StreamLostError,
)

from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Consumer,
)
from DefStream.Worker import (
	Pool,
	PoolSetup,
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
)
from DefStream.Worker.Executor import Executor
from _support import (
	call_with_invalid_input,
	require_instance,
	require_value,
)


class RecoveryRun(Run, parameters={'queue': 'recovery'}):
	def run(self, started=None, release=None):
		if started is not None:
			started.set()
		if release is not None:
			if not release.wait(10):
				raise TimeoutError('Test task was not released')
		return 'done'


class ProcessRecoveryRun(Run):
	def run(self, path):
		Path(path).write_text('started', encoding='utf-8')
		sleep(30)
		return 'done'


class ValueRun(Run):
	def run(self):
		return 'new generation'


class CaptureThread(PoolSetup):
	def __init__(self, threads: Queue[Thread]) -> None:
		self.threads = threads

	def __call__(self) -> None:
		self.threads.put(current_thread())
		return


class OtherRecoveryRun(RecoveryRun, parameters={'queue': 'other', 'qos': 3}):
	pass


class RecoveryTests(TestCase):
	def consumer(self):
		connection = Mock()
		consumer = Consumer(connection, Mock())

		def cleanup():
			consumer.close()
			require_instance(consumer.channel, Mock).is_open = False
			if consumer.response_channel is not None:
				require_instance(consumer.response_channel, Mock).is_open = False
			return

		self.addCleanup(cleanup)
		return consumer

	def connection(self, consumer: Consumer) -> Mock:
		return require_instance(consumer.connection, Mock)

	def channel(self, consumer: Consumer) -> Mock:
		return require_instance(consumer.channel, Mock)

	def broker(self, worker: Worker) -> Mock:
		return require_instance(worker.broker, Mock)

	def worker(self, consumers, **kwargs):
		broker = Mock(spec=Connection)
		broker.consumer.side_effect = consumers
		pool = ThreadPool(1)
		worker = Worker(broker, pool, **kwargs)
		worker.add(RecoveryRun)
		return worker

	def run_worker(self, worker):
		with patch('DefStream.Worker.Worker.startup'):
			worker.run()

	def test_first_attempt_is_immediate_and_recovery_resets_budget(self):
		consumers = [self.consumer() for _ in range(3)]
		worker = self.worker(consumers, recovery_attempts=1)
		consumers[0].run = Mock(side_effect=StreamLostError())
		consumers[1].run = Mock(side_effect=StreamLostError())
		consumers[2].run = Mock(side_effect=worker.stopping.set)
		wait = Mock(return_value=False)
		with patch.object(worker.stopping, 'wait', wait):
			self.run_worker(worker)
		wait.assert_not_called()
		self.assertEqual(self.broker(worker).connect.call_count, 3)
		self.assertEqual(self.broker(worker).consumer.call_count, 3)
		self.assertTrue(worker.finished.is_set())

	def test_default_limit_and_fixed_interval(self):
		consumer = self.consumer()
		consumer.run = Mock(side_effect=StreamLostError())
		worker = self.worker([consumer])
		self.broker(worker).connect.side_effect = [None] + [StreamLostError() for _ in range(5)]
		with patch.object(worker.stopping, 'wait', return_value=False) as wait:
			with self.assertRaises(StreamLostError):
				self.run_worker(worker)
		self.assertEqual(self.broker(worker).connect.call_count, 6)
		self.assertEqual(wait.call_count, 4)
		self.assertTrue(all(call.args == (60,) for call in wait.call_args_list))
		self.assertFalse(worker.running.is_set())

	def test_custom_limit_interval_and_partial_subscription_failure(self):
		first = self.consumer()
		first.run = Mock(side_effect=StreamLostError())
		partial = self.consumer()
		partial.subs = Mock(side_effect=StreamLostError())
		last = self.consumer()
		worker = self.worker([first, partial, last], recovery_attempts=2, recovery_interval=7)
		last.run = Mock(side_effect=worker.stopping.set)
		with patch.object(worker.stopping, 'wait', return_value=False) as wait:
			self.run_worker(worker)
		wait.assert_called_once_with(7)
		self.assertEqual(self.channel(partial).close.call_count, 1)

	def test_every_subscription_and_qos_are_restored_on_a_new_connection(self):
		first = self.consumer()
		second = self.consumer()
		worker = self.worker([first, second])
		worker.add(OtherRecoveryRun)
		first.run = Mock(side_effect=StreamLostError())
		second.run = Mock(side_effect=worker.stopping.set)
		self.run_worker(worker)
		self.assertIsNot(first.connection, second.connection)
		for consumer in (first, second):
			registrations = self.channel(consumer).basic_consume.call_args_list
			self.assertEqual([call.args[0] for call in registrations], ['recovery', 'other'])
			self.assertTrue(all(call.kwargs['auto_ack'] is False for call in registrations))
			self.channel(consumer).basic_qos.assert_called_with(
				prefetch_count=3,
				global_qos=False,
			)

	def test_stop_interrupts_recovery_wait_without_scheduling_on_closed_connection(self):
		first = self.consumer()
		first.run = Mock(side_effect=StreamLostError())
		worker = self.worker([first])
		self.broker(worker).connect.side_effect = [None, StreamLostError()]

		def stop(timeout):
			self.assertEqual(timeout, 60)
			worker.stop()
			return True

		with patch.object(worker.stopping, 'wait', side_effect=stop):
			self.run_worker(worker)
		self.connection(first).add_callback_threadsafe.assert_not_called()
		self.assertEqual(self.broker(worker).connect.call_count, 2)

	def test_nonrecoverable_error_and_zero_budget_are_propagated(self):
		for error, attempts in (
			(ValueError('handler failed'), 5),
			(StreamLostError(), 0),
			(ChannelClosedByBroker(404, 'queue missing'), 5),
		):
			with self.subTest(error=type(error), attempts=attempts):
				first = self.consumer()
				first.run = Mock(side_effect=error)
				worker = self.worker([first], recovery_attempts=attempts)
				with self.assertRaises(type(error)):
					self.run_worker(worker)
				self.assertEqual(self.broker(worker).connect.call_count, 1)

	def test_recovery_configuration_rejects_invalid_values(self):
		for key, value, error in (
			('recovery_attempts', True, TypeError),
			('recovery_attempts', -1, ValueError),
			('recovery_interval', True, TypeError),
			('recovery_interval', -1, ValueError),
			('recovery_interval', float('inf'), ValueError),
			('recovery_interval', float('nan'), ValueError),
		):
			with self.subTest(key=key, value=value), self.assertRaises(error):
				call_with_invalid_input(Worker, Mock(), Mock(), **{key: value})

	def test_old_success_and_failure_callbacks_cannot_touch_new_generation(self):
		for error in (None, ValueError('old task failed')):
			with self.subTest(error=error):
				pool = Mock()
				inspector = Mock()
				first = self.consumer()
				second = self.consumer()
				worker = Worker(Mock(), pool, inspector=inspector)
				worker.consumer = first
				event = Mock()
				event.body = {}
				worker.receive(RecoveryRun, event)
				callback = pool.submit.call_args.kwargs[
					'callback' if error is None else 'error_callback'
				]
				worker.discard_deliveries()
				worker.consumer = second
				worker.pending = 3
				callback('done' if error is None else error)
				self.connection(first).add_callback_threadsafe.assert_not_called()
				self.connection(second).add_callback_threadsafe.assert_not_called()
				self.assertEqual(worker.pending, 3)
				inspector.end.assert_called_once()
				self.assertIsNone(inspector.end.call_args.args[2])

	def test_already_scheduled_result_cannot_ack_or_respond_after_recovery(self):
		pool = Mock()
		first = self.consumer()
		worker = Worker(Mock(), pool)
		worker.consumer = first
		event = Mock()
		event.body = {}
		worker.receive(RecoveryRun, event)
		pool.submit.call_args.kwargs['callback']('done')
		dispatch = self.connection(first).add_callback_threadsafe.call_args.args[0]
		worker.discard_deliveries()
		worker.consumer = self.consumer()
		worker.pending = 2
		dispatch()
		event.ack.assert_not_called()
		self.assertEqual(worker.pending, 2)

	def test_thread_pool_identity_and_retired_thread_cleanup(self):
		threads: Queue[Thread] = Queue()
		pool = ThreadPool(1, setups=CaptureThread(threads))
		started = Event()
		release = Event()
		try:
			future = pool.submit(RecoveryRun, {'started': started, 'release': release})
			self.assertTrue(started.wait(5))
			retired_thread = threads.get(timeout=5)
			previous = require_instance(pool.pool, Executor)
			before_restart = monotonic()
			pool.restart()
			self.assertLess(monotonic() - before_restart, 5)
			self.assertFalse(previous.workers[0].done())
			self.assertIsNot(pool.pool, previous)
			self.assertEqual(pool.submit(ValueRun, {}).result(5), 'new generation')
			self.assertIsNot(threads.get(timeout=5), retired_thread)
			self.assertTrue(future.done())
			release.set()
			require_value(previous.monitor).join(5)
			retired_thread.join(5)
			self.assertFalse(retired_thread.is_alive())
			self.assertFalse(require_value(previous.monitor).is_alive())
			self.assertTrue(all(worker.done() for worker in previous.workers))
			self.assertEqual(pool.count(), 0)
		finally:
			release.set()
			pool.stop()

	def test_worker_recovers_with_running_thread_and_settles_only_new_delivery(self):
		started = Event()
		release = Event()
		first = self.consumer()
		second = self.consumer()
		worker = self.worker([first, second])
		pool = worker.pool
		old_event = Mock()
		old_event.body = {'started': started, 'release': release}
		new_event = Mock()
		new_event.body = {}
		callbacks = Queue()
		self.connection(second).add_callback_threadsafe.side_effect = callbacks.put
		retired = []

		def fail():
			worker.receive(RecoveryRun, old_event)
			self.assertTrue(started.wait(5))
			retired.append(require_instance(pool.pool, Executor))
			raise StreamLostError()

		def resume():
			self.assertIs(worker.pool, pool)
			self.assertFalse(release.is_set())
			worker.receive(RecoveryRun, new_event)
			callbacks.get(timeout=5)()
			new_event.ack.assert_called_once()
			self.assertEqual(worker.pending, 0)
			worker.stop()
			callbacks.get(timeout=5)()

		first.run = Mock(side_effect=fail)
		second.run = Mock(side_effect=resume)
		try:
			self.run_worker(worker)
		finally:
			release.set()
			for executor in retired:
				require_value(executor.monitor).join(5)
		old_event.ack.assert_not_called()
		old_event.nack.assert_not_called()
		self.connection(first).add_callback_threadsafe.assert_not_called()

	def test_fatal_worker_failure_does_not_wait_for_retired_thread(self):
		started = Event()
		release = Event()
		consumer = self.consumer()
		worker = self.worker([consumer])
		event = Mock()
		event.body = {'started': started, 'release': release}
		previous = require_instance(worker.pool.pool, Executor)

		def fail():
			worker.receive(RecoveryRun, event)
			self.assertTrue(started.wait(5))
			raise ValueError('fatal consumption failure')

		consumer.run = Mock(side_effect=fail)
		try:
			before_failure = monotonic()
			with self.assertRaisesRegex(ValueError, 'fatal consumption failure'):
				self.run_worker(worker)
			self.assertLess(monotonic() - before_failure, 5)
			self.assertFalse(previous.workers[0].done())
			self.assertFalse(release.is_set())
			self.assertTrue(worker.finished.is_set())
		finally:
			release.set()
			require_value(previous.monitor).join(5)
		event.ack.assert_not_called()

	def test_unstarted_tasks_are_discarded_by_retired_executor(self):
		pool = ThreadPool(1)
		started = Event()
		release = Event()
		queued = Mock(return_value='must not run')
		try:
			pool.submit(RecoveryRun, {'started': started, 'release': release})
			self.assertTrue(started.wait(5))
			previous = require_instance(pool.pool, Executor)
			pending = previous.submit(queued)
			pool.restart()
			release.set()
			require_value(previous.monitor).join(5)
			queued.assert_not_called()
			with self.assertRaisesRegex(RuntimeError, 'discarded'):
				pending.result()
		finally:
			release.set()
			pool.stop()

	def test_custom_executor_recovery_fails_explicitly_without_replacing_it(self):
		executor = Mock()
		pool = Pool(executor, 1)
		with self.assertRaisesRegex(TypeError, 'DefStream Executor'):
			pool.restart()
		self.assertIs(pool.pool, executor)
		self.assertFalse(pool.closed)

	def test_process_pool_terminates_old_processes_and_releases_manager(self):
		pool = ProcessPool(1)
		try:
			with TemporaryDirectory() as directory:
				path = Path(directory) / 'started'
				future = pool.submit(ProcessRecoveryRun, {'path': str(path)})
				deadline = monotonic() + 10
				while not path.exists() and monotonic() < deadline:
					sleep(0.01)
				self.assertTrue(path.exists())
				previous = require_instance(pool.pool, Executor)
				processes = tuple(previous.processes)
				pool.restart()
				self.assertTrue(future.done())
				self.assertTrue(all(not process.is_alive() for process in processes))
				self.assertFalse(require_value(previous.monitor).is_alive())
				self.assertEqual(pool.submit(ValueRun, {}).result(10), 'new generation')
		finally:
			pool.stop()

	def test_closed_idle_channel_is_detected_without_settlement(self):
		consumer = self.consumer()
		self.channel(consumer).is_closed = True
		with self.assertRaisesRegex(RuntimeError, 'without a stop request'):
			consumer.run()
		self.channel(consumer).basic_ack.assert_not_called()
		self.connection(consumer).remove_timeout.assert_called_once()

	def test_ack_timeout_and_exception_classification(self):
		consumer = self.consumer()
		error = ChannelClosedByBroker(406, 'delivery acknowledgement on channel 1 timed out')
		self.channel(consumer).start_consuming.side_effect = error
		consumer.subs('queue', Mock())
		with self.assertLogs(consumer.logger, level='WARNING') as logs:
			with self.assertRaises(ChannelClosedByBroker):
				consumer.run()
		self.assertTrue(any('queue' in message and 'timed out' in message for message in logs.output))
		self.assertTrue(consumer.is_recoverable(error))
		self.assertTrue(consumer.is_recoverable(StreamLostError()))
		self.assertTrue(consumer.is_recoverable(ConnectionClosedByBroker(320, 'shutdown')))
		self.assertFalse(consumer.is_recoverable(ConnectionClosedByBroker(403, 'denied')))
		self.assertFalse(consumer.is_recoverable(ChannelClosedByBroker(406, 'unknown delivery tag')))
		self.assertFalse(consumer.is_recoverable(ProbableAuthenticationError()))
		with patch.object(consumer, 'callback_error', error):
			self.assertFalse(consumer.is_recoverable(error))


if __name__ == '__main__':
	main()
