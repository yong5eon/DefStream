from pathlib import Path
from queue import Queue
from tempfile import TemporaryDirectory
from threading import (
	Barrier,
	Event,
	Thread,
	get_ident,
)
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Broker.Implements.RabbitMQ import (
	Requeue,
	Reject,
	Subscription,
)
from DefStream.Worker import (
	PoolFull,
	PoolSetup,
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
)
from _support import call_with_invalid_input


class FileRunner(Run, parameters={'queue': 'file'}):
	def run(self, path, value):
		Path(path).write_text(value, encoding='utf-8')
		return value


class FailingRunner(Run, parameters={'queue': 'failure'}):
	def run(self, **kwargs):
		raise ValueError('processing failed')


class RejectingRunner(
	FailingRunner,
	on_error=Reject(),
):
	pass


class FileSetup(PoolSetup):
	def __init__(self, path: str) -> None:
		self.path = path
		return

	def __call__(self) -> None:
		Path(self.path).write_text('ready', encoding='utf-8')
		return


class FakeConsumer:
	def complete(
		self,
		event,
		result,
	):
		event.ack()

	def __init__(self):
		self.handlers = {}
		self.callbacks = Queue()
		self.stopped = False
		self.owner = None
		self.on_run = lambda: None
		self.closed = False

	def subs(
		self,
		parameters,
		handler,
	):
		queue = Subscription.parse(parameters).queue
		if queue in self.handlers:
			raise ValueError('Duplicate queue')
		self.handlers[queue] = handler

	def call(self, callback):
		self.callbacks.put(callback)

	def fail(self, delivery, policy=None):
		(policy if policy is not None else Requeue())(delivery)

	def run(self):
		self.owner = get_ident()
		self.on_run()
		while not self.stopped:
			self.callbacks.get(timeout=15)()

	def stop(self):
		self.stopped = True

	def close(self):
		self.closed = True


class RunnerTests(TestCase):
	def test_named_runs_preserve_abstract_class_contract(self):
		class Abstract(
			Run,
			name='abstract_task',
			description='Abstract task',
		):
			pass

		self.assertEqual(
			Abstract.name,
			'abstract_task',
		)
		with self.assertRaisesRegex(TypeError, 'abstract'):
			call_with_invalid_input(Abstract)

		class Concrete(
			Abstract,
			name='concrete_task',
		):
			def run(self):
				return 3

		self.assertEqual(
			Concrete.name,
			'concrete_task',
		)
		self.assertIsNone(Concrete.description)
		self.assertEqual(
			Concrete()(),
			3,
		)

	def test_registration_is_explicit_and_worker_local(self):
		first = Worker(Mock(), Mock())
		second = Worker(Mock(), Mock())
		first.add(FileRunner)
		self.assertEqual(first.tasks, [FileRunner])
		self.assertEqual(second.tasks, [])
		self.assertEqual(FileRunner.parameters, {'queue': 'file'})
		self.assertIsInstance(
			RejectingRunner.on_error,
			Reject,
		)
		self.assertIsNone(FailingRunner.on_error)
		with self.assertRaises(ValueError):
			first.add(FileRunner)
		with self.assertRaises(TypeError):
			first.add(Run)
		with self.assertRaises(TypeError):
			call_with_invalid_input(first.add, object)

	def test_parameters_and_policy_are_inherited_without_global_registration(self):
		class Child(FileRunner):
			pass

		self.assertIs(Child.parameters, FileRunner.parameters)
		self.assertEqual(
			Child.name,
			Child.__module__ + '.' + Child.__qualname__,
		)
		self.assertIsNone(Child.description)
		with self.assertRaises(TypeError):
			class Invalid(
				Run,
				on_error='reject',
			):
				def run(self):
					pass

	def test_distinct_runs_cannot_register_with_duplicate_names(self):
		class First(FileRunner, name='same'):
			pass

		class Second(FileRunner, name='same'):
			pass

		worker = Worker(Mock(), Mock())
		worker.add(First)
		with self.assertRaisesRegex(ValueError, 'Duplicate Run name'):
			worker.add(Second)

	def test_missing_parameters_are_reported(self):
		class Missing(Run):
			def run(self):
				pass

		with self.assertRaises(ValueError):
			Worker(Mock(), Mock()).add(Missing)


class PoolTests(TestCase):
	def test_real_thread_and_process_execution(self):
		for pool_cls in (ThreadPool, ProcessPool):
			with self.subTest(pool=pool_cls), TemporaryDirectory() as directory:
				path = str(Path(directory) / 'result')
				setup_path = str(Path(directory) / 'setup')
				pool = pool_cls(1, setups=FileSetup(setup_path))
				try:
					future = pool.submit(FileRunner, {'path': path, 'value': 'done'})
					self.assertEqual(future.result(timeout=15), 'done')
					pool.waits(15)
					self.assertEqual(Path(path).read_text(encoding='utf-8'), 'done')
					self.assertEqual(Path(setup_path).read_text(encoding='utf-8'), 'ready')
					with self.assertRaisesRegex(ValueError, 'processing failed'):
						pool.submit(FailingRunner, {}).result(timeout=15)
				finally:
					pool.stop()
				self.assertEqual(pool.count(), 0)
				with self.assertRaisesRegex(RuntimeError, 'closed'):
					pool.submit(FileRunner, {})

	def test_capacity_has_no_unbounded_waiting_queue(self):
		release = Event()
		started = Event()

		class Blocking(Run):
			def run(self):
				started.set()
				release.wait(10)

		pool = ThreadPool(1)
		try:
			future = pool.submit(Blocking, {})
			self.assertTrue(started.wait(5))
			self.assertEqual(pool.count(), 1)
			with self.assertRaises(PoolFull):
				pool.submit(Blocking, {})
			with self.assertRaises(TimeoutError):
				pool.waits(0)
			release.set()
			future.result(5)
		finally:
			release.set()
			pool.stop()

	def test_submission_failure_releases_capacity(self):
		executor = Mock()
		executor.submit.side_effect = RuntimeError('submit failed')
		from DefStream.Worker import Pool
		pool = Pool(executor, 1)
		for _ in range(2):
			with self.assertRaisesRegex(RuntimeError, 'submit failed'):
				pool.submit(FileRunner, {})
		self.assertEqual(pool.count(), 0)

	def test_concurrent_submissions_cannot_exceed_capacity(self):
		release = Event()
		barrier = Barrier(12)
		outcomes = Queue()

		class Blocking(Run):
			def run(self):
				release.wait(10)

		pool = ThreadPool(2)

		def submit():
			barrier.wait(timeout=5)
			try:
				pool.submit(Blocking, {})
			except PoolFull:
				outcomes.put('full')
			else:
				outcomes.put('accepted')

		threads = [Thread(target=submit) for _ in range(12)]
		try:
			for thread in threads:
				thread.start()
			for thread in threads:
				thread.join(5)
				self.assertFalse(thread.is_alive())
			results = [outcomes.get_nowait() for _ in threads]
			self.assertEqual(results.count('accepted'), 2)
			self.assertEqual(results.count('full'), 10)
			self.assertEqual(pool.count(), 2)
		finally:
			release.set()
			pool.stop()

	def test_pool_size_and_setup_validation(self):
		for size in (0, -1, True, 1.5):
			with self.assertRaises(ValueError):
				call_with_invalid_input(ThreadPool, size)
		first, second = Mock(), Mock()
		pool = ThreadPool(
			1,
			setups=[
				first,
				second,
			],
		)
		try:
			pool.submit(
				FailingRunner,
				{},
			).exception(timeout=5)
		finally:
			pool.stop()
		first.assert_called_once_with()
		second.assert_called_once_with()


class WorkerTests(TestCase):
	def make_worker(self, runner, pool):
		consumer = FakeConsumer()
		broker = Mock(consumer=Mock(return_value=consumer))
		worker = Worker(broker, pool)
		worker.add(runner)
		return worker, consumer, broker

	def test_ack_runs_on_owner_thread_after_success_for_both_pools(self):
		for pool_cls in (ThreadPool, ProcessPool):
			with self.subTest(pool=pool_cls), TemporaryDirectory() as directory:
				path = str(Path(directory) / 'result')
				pool = pool_cls(1)
				worker, consumer, broker = self.make_worker(FileRunner, pool)
				delivery = Mock()
				delivery.body = {'path': path, 'value': 'done'}
				acks = []
				delivery.ack.side_effect = lambda: acks.append(
					(get_ident(), Path(path).read_text(encoding='utf-8'))
				)

				def receive():
					consumer.handlers['file'](delivery)
					worker.stop()

				consumer.on_run = receive
				worker.run()
				self.assertEqual(acks, [(consumer.owner, 'done')])
				delivery.nack.assert_not_called()
				delivery.reject.assert_not_called()
				self.assertTrue(consumer.closed)
				broker.connect.assert_called_once_with()
				broker.consumer.assert_called_once_with()
				self.assertFalse(callable(worker))
				broker.close.assert_called_once_with()

	def test_on_error_runs_on_owner_thread(self):
		for runner, action in ((FailingRunner, 'nack'), (RejectingRunner, 'reject')):
			with self.subTest(runner=runner):
				worker, consumer, broker = self.make_worker(runner, ThreadPool(1))
				delivery = Mock()
				delivery.body = {}
				threads = []
				getattr(delivery, action).side_effect = lambda: threads.append(get_ident())

				def receive():
					consumer.handlers['failure'](delivery)
					worker.stop()

				consumer.on_run = receive
				with self.assertLogs('Worker', level='ERROR'):
					worker.run()
				self.assertEqual(threads, [consumer.owner])
				delivery.ack.assert_not_called()

	def test_full_pool_nacks_without_execution(self):
		pool = Mock()
		pool.submit.side_effect = PoolFull()
		worker, consumer, _ = self.make_worker(FileRunner, pool)
		delivery = Mock()
		delivery.body = {}

		def receive():
			consumer.handlers['file'](delivery)
			worker.stop()

		consumer.on_run = receive
		worker.run()
		delivery.nack.assert_called_once_with()
		delivery.ack.assert_not_called()

	def test_invalid_body_uses_run_on_error(self):
		pool = Mock()
		worker, consumer, _ = self.make_worker(RejectingRunner, pool)
		delivery = Mock()
		delivery.body = 'not a mapping'

		def receive():
			consumer.handlers['failure'](delivery)
			worker.stop()

		consumer.on_run = receive
		with self.assertLogs('Worker', level='WARNING'):
			worker.run()
		delivery.reject.assert_called_once_with()
		pool.submit.assert_not_called()

	def test_stop_from_another_thread_waits_for_processing_and_ack(self):
		started, release = Event(), Event()
		errors = []

		class Blocking(Run, parameters={'queue': 'blocking'}):
			def run(self):
				started.set()
				if not release.wait(10):
					raise TimeoutError('test did not release task')

		worker, consumer, _ = self.make_worker(Blocking, ThreadPool(1))
		delivery = Mock()
		delivery.body = {}
		consumer.on_run = lambda: consumer.handlers['blocking'](delivery)

		def run():
			try:
				worker.run()
			except Exception as error:
				errors.append(error)

		thread = Thread(target=run)
		thread.start()
		try:
			self.assertTrue(started.wait(5))
			worker.stop()
			self.assertTrue(thread.is_alive())
			delivery.ack.assert_not_called()
		finally:
			release.set()
			thread.join(15)
		self.assertFalse(thread.is_alive())
		self.assertEqual(errors, [])
		delivery.ack.assert_called_once_with()

	def test_startup_failure_closes_pool_and_broker(self):
		pool = Mock()
		worker, _, broker = self.make_worker(FileRunner, pool)
		broker.connect.side_effect = RuntimeError('connect failed')
		with self.assertRaisesRegex(RuntimeError, 'connect failed'):
			worker.run()
		pool.stop.assert_called_once_with()
		broker.close.assert_called_once_with()

	def test_delivery_received_after_stop_is_nacked_without_submission(self):
		pool = Mock()
		worker, consumer, _ = self.make_worker(FileRunner, pool)
		delivery = Mock()
		delivery.body = {}

		def receive():
			worker.stop()
			consumer.handlers['file'](delivery)

		consumer.on_run = receive
		worker.run()
		delivery.nack.assert_called_once_with()
		pool.submit.assert_not_called()

	def test_ack_failure_is_propagated_and_resources_are_closed(self):
		pool = Mock()

		def submit(
			runner,
			body,
			callback,
			error_callback,
		):
			callback(None)

		pool.submit.side_effect = submit
		worker, consumer, broker = self.make_worker(FileRunner, pool)
		delivery = Mock()
		delivery.body = {}
		delivery.ack.side_effect = RuntimeError('ack failed')
		consumer.on_run = lambda: consumer.handlers['file'](delivery)
		with self.assertRaisesRegex(RuntimeError, 'ack failed'):
			worker.run()
		self.assertTrue(consumer.closed)
		broker.close.assert_called_once_with()

	def test_duplicate_queue_is_reported_and_resources_close(self):
		worker, consumer, broker = self.make_worker(FailingRunner, Mock())
		worker.add(RejectingRunner)
		with self.assertRaisesRegex(ValueError, 'Duplicate queue'):
			worker.run()
		self.assertTrue(consumer.closed)
		broker.close.assert_called_once_with()

	def test_registration_and_restart_are_rejected_after_start(self):
		worker, consumer, _ = self.make_worker(FileRunner, Mock())
		consumer.on_run = worker.stop
		worker.run()
		worker.stop()
		worker.stop()
		with self.assertRaises(RuntimeError):
			worker.add(FailingRunner)
		with self.assertRaises(RuntimeError):
			worker.run()


if __name__ == '__main__':
	main()
