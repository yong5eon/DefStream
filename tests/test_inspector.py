from json import loads
from queue import (
	Empty,
	Queue,
)
from socket import socket
from threading import (
	Event,
	Thread,
)
from time import (
	monotonic,
	sleep,
)
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock
from uuid import uuid4

from DefStream.Inspector import (
	Extension,
	Inspector,
	Response,
)
from DefStream.Inspector.Extensions import (
	Metrics,
	Ping,
)
from DefStream.Worker import (
	PoolFull,
	Run,
	ThreadPool,
	Worker,
	WorkerSetup,
)
from tests._support_inspector import (
	Divide,
	InspectorIntegrationSupport,
)
from tests._support import (
	RejectPolicy,
	require_instance,
	require_value,
)


class Add(
	Run,
	parameters={'queue': 'add'},
):
	def run(
		self,
		a: int,
		b: int,
	):
		return a + b


class Consumer:
	def __init__(self):
		self.callbacks = Queue()
		self.ready = Event()
		self.stopped = False

	def subs(
		self,
		parameters,
		handler,
	):
		pass

	def call(
		self,
		callback,
	):
		self.callbacks.put(callback)

	def run(self):
		self.ready.set()
		while not self.stopped:
			try:
				callback = self.callbacks.get(timeout=0.1)
			except Empty:
				continue
			callback()

	def stop(self):
		self.stopped = True

	def close(self):
		pass

	def complete(
		self,
		event,
		result,
	):
		event.ack()

	def fail(
		self,
		event,
		policy,
	):
		event.reject()


class InspectorTests(InspectorIntegrationSupport, TestCase):
	def test_unregistered_monitoring_has_no_state(self):
		inspector = Inspector(port=0)
		worker = Worker(
			Mock(),
			ThreadPool(1),
		)
		self.addCleanup(worker.pool.stop)
		self.addCleanup(inspector.stop)
		inspector.start(worker)
		self.assertEqual(
			inspector.begin('unused'),
			(),
		)
		for attribute in (
			'tasks',
			'lock',
			'probe',
			'timeout',
			'started_at',
			'healthy',
			'metrics',
		):
			self.assertFalse(hasattr(
				inspector,
				attribute,
			))

	def test_extension_events_preserve_independent_contexts(self):
		class Observer(Extension):
			def start(
				self,
				inspector,
			):
				self.worker = inspector.worker
				self.completed = []
				self.context = object()

			def begin(
				self,
				task,
			):
				return self.context

			def end(
				self,
				task,
				context,
				success,
			):
				self.completed.append((
					task,
					context,
					success,
				))

			def __call__(
				self,
				inspector,
			):
				return Response(
					'200 OK',
					b'',
					'text/plain',
				)

		observers = (
			Observer('/one'),
			Observer('/two'),
		)
		inspector = Inspector(
			port=0,
			exts=observers,
		)
		worker = Worker(
			Mock(),
			ThreadPool(1),
		)
		self.addCleanup(worker.pool.stop)
		self.addCleanup(inspector.stop)
		inspector.start(worker)
		contexts = inspector.begin('task')
		inspector.end(
			'task',
			contexts,
			None,
		)
		for observer in observers:
			self.assertIs(
				observer.worker,
				worker,
			)
			self.assertEqual(
				observer.completed,
				[(
					'task',
					observer.context,
					None,
				)],
			)

	def make_worker(
		self,
		**kwargs,
	):
		inspector = Inspector(
			port=0,
			exts=(
				Ping(
					'/ping',
					timeout=0.1,
				),
				Metrics('/stats'),
			),
		)
		consumer = Consumer()
		broker = Mock(consumer=Mock(return_value=consumer))
		pool = ThreadPool(2)
		self.broker = broker
		self.pool = pool
		worker = Worker(
			broker,
			pool,
			inspector=inspector,
			**kwargs,
		)
		worker.add(Add)
		worker.add(Divide)
		return worker, consumer, inspector

	def test_lifecycle_and_consumer_heartbeat_over_http(self):
		preparing = Event()
		prepared = Event()
		cleaning = Event()
		cleaned = Event()
		blocked = Event()
		release = Event()
		self.addCleanup(release.set)
		self.addCleanup(cleaned.set)
		self.addCleanup(prepared.set)

		def prepare(worker):
			preparing.set()
			if not prepared.wait(5):
				raise TimeoutError('prepare gate timed out')

		def cleanup(worker):
			cleaning.set()
			if not cleaned.wait(5):
				raise TimeoutError('cleanup gate timed out')

		worker, consumer, inspector = self.make_worker(
			setups=prepare,
			cleanups=cleanup,
		)
		thread = self.launch(worker)
		try:
			self.assertTrue(preparing.wait(5))
			status, body, headers = self.fetch(
				inspector,
				'/ping',
			)
			self.assertEqual(
				status,
				503,
			)
			self.assertEqual(
				loads(body)['status'],
				'starting',
			)
			self.assertEqual(
				self.fetch(
					inspector,
					'/stats',
				)[0],
				200,
			)
			prepared.set()
			self.assertTrue(consumer.ready.wait(5))
			self.assertEqual(
				self.fetch(
					inspector,
					'/ping?probe=1',
				)[0],
				200,
			)

			def block():
				blocked.set()
				if not release.wait(5):
					raise TimeoutError('consumer gate timed out')

			consumer.call(block)
			self.assertTrue(blocked.wait(5))
			status, body, headers = self.fetch(
				inspector,
				'/ping',
			)
			self.assertEqual(
				status,
				503,
			)
			self.assertEqual(
				loads(body)['status'],
				'unresponsive',
			)
			self.assertEqual(
				self.fetch(
					inspector,
					'/ping',
				)[0],
				503,
			)
			self.assertEqual(
				consumer.callbacks.qsize(),
				1,
			)
			release.set()
			self.assertEqual(
				self.fetch(
					inspector,
					'/ping',
				)[0],
				200,
			)
			worker.stop()
			self.assertTrue(cleaning.wait(5))
			self.assertEqual(
				self.fetch(
					inspector,
					'/ping',
				)[0],
				503,
			)
			status, body, headers = self.fetch(
				inspector,
				'/stats',
			)
			self.assertEqual(
				status,
				200,
			)
			self.assertIn(
				b'defstream_worker_running 0',
				body,
			)
		finally:
			prepared.set()
			release.set()
			cleaned.set()
			worker.stop()
			thread.join(10)
		self.assertFalse(require_value(inspector.thread).is_alive())
		self.assertEqual(
			require_value(inspector.server).fileno(),
			-1,
		)

	def test_task_metrics_success_failure_active_and_duration(self):
		worker, consumer, inspector = self.make_worker()
		self.launch(worker)
		self.assertTrue(consumer.ready.wait(5))
		first = Mock()
		first.body = {
			'a': 6,
			'b': 2,
		}
		second = Mock()
		second.body = {
			'a': 1,
			'b': 0,
		}
		acked = Event()
		rejected = Event()
		first.ack.side_effect = acked.set
		second.reject.side_effect = rejected.set
		consumer.call(lambda: worker.receive(
			Add,
			first,
		))
		self.assertTrue(acked.wait(5))
		with self.assertLogs(
			'Worker',
			level='ERROR',
		):
			consumer.call(lambda: worker.receive(
				Divide,
				second,
			))
			self.assertTrue(rejected.wait(5))
		status, body, headers = self.fetch(
			inspector,
			'/stats',
		)
		text = body.decode()
		self.assertEqual(
			status,
			200,
		)
		self.assertIn(
			'version=0.0.4',
			headers['Content-Type'],
		)
		for task, outcome in (
			(
				Add,
				'success',
			),
			(
				Divide,
				'failure',
			),
		):
			labels = 'task="' + task.name + '"'
			self.assertIn(
				f'defstream_tasks_total{{{labels},outcome="{outcome}"}} 1',
				text,
			)
			self.assertIn(
				f'defstream_tasks_active{{{labels}}} 0',
				text,
			)
			self.assertIn(
				f'defstream_task_duration_seconds_count{{{labels}}} 1',
				text,
			)
			duration = next(line for line in text.splitlines() if line.startswith(f'defstream_task_duration_seconds_sum{{{labels}}} '))
			self.assertGreaterEqual(
				float(duration.rsplit(' ')[1]),
				0,
			)

	def test_metrics_use_run_name(self):
		class NamedAdd(
			Add,
			parameters={'queue': 'named-add'},
			name='Orders.create-v2_Job',
		):
			pass

		inspector = Inspector()
		worker = Worker(
			Mock(),
			ThreadPool(1),
		)
		worker.add(NamedAdd)
		inspector.worker = worker
		metrics = Metrics('/stats')
		metrics.start(inspector)
		self.addCleanup(worker.pool.stop)
		self.assertEqual(
			set(metrics.tasks),
			{'Orders.create-v2_Job'},
		)
		started = metrics.begin(NamedAdd.name)
		metrics.end(
			NamedAdd.name,
			started,
			True,
		)
		self.assertEqual(
			metrics.snapshot(inspector)['tasks'][NamedAdd.name]['success'],
			1,
		)
		self.assertIn(
			'defstream_tasks_total{task="Orders.create-v2_Job",outcome="success"} 1',
			metrics.render(inspector),
		)

	def test_metrics_reject_duplicate_run_names_without_overwriting(self):
		class First(
			Add,
			parameters={'queue': 'first-metrics'},
			name='first',
		):
			pass

		class Second(
			Add,
			parameters={'queue': 'second-metrics'},
			name='second',
		):
			pass

		inspector = Inspector()
		worker = Worker(
			Mock(),
			ThreadPool(1),
		)
		worker.add(First)
		worker.add(Second)
		Second.name = First.name
		inspector.worker = worker
		metrics = Metrics('/stats')
		self.addCleanup(worker.pool.stop)
		with self.assertRaisesRegex(ValueError, 'Duplicate Metrics task name'):
			metrics.start(inspector)
		self.assertIsNone(metrics.started_at)
		self.assertEqual(metrics.tasks, {})

	def test_active_execution_and_pool_full_are_not_counted_as_failures(self):
		worker, consumer, inspector = self.make_worker()
		self.pool.stop()
		pool = Mock()
		worker.pool = pool
		self.launch(worker)
		self.assertTrue(consumer.ready.wait(5))
		submitted = Event()
		pool.submit.side_effect = lambda *args, **kwargs: submitted.set()
		delivery = Mock()
		delivery.body = {'a': 1}
		consumer.call(lambda: worker.receive(
			Add,
			delivery,
		))
		self.assertTrue(submitted.wait(5))
		task = Add.name
		metrics = require_instance(inspector.exts['/stats'], Metrics)
		with metrics.lock:
			self.assertEqual(
				metrics.tasks[task].active,
				1,
			)
		completed = Event()
		delivery.ack.side_effect = completed.set
		callback = pool.submit.call_args.kwargs['callback']
		callback(1)
		self.assertTrue(completed.wait(5))
		pool.submit.side_effect = PoolFull()
		nacked = Event()
		delivery.nack.side_effect = nacked.set
		consumer.call(lambda: worker.receive(
			Add,
			delivery,
		))
		self.assertTrue(nacked.wait(5))
		with metrics.lock:
			stats = metrics.tasks[task]
			self.assertEqual(
				(
					stats.active,
					stats.success,
					stats.failure,
				),
				(
					0,
					1,
					0,
				),
			)

	def test_routes_methods_head_and_custom_paths(self):
		worker, consumer, inspector = self.make_worker()
		self.launch(worker)
		self.assertTrue(consumer.ready.wait(5))
		status, body, headers = self.fetch(
			inspector,
			'/ping',
			'HEAD',
		)
		self.assertEqual(
			(
				status,
				body,
			),
			(
				200,
				b'',
			),
		)
		self.assertGreater(
			int(headers['Content-Length']),
			0,
		)
		self.assertEqual(
			self.fetch(
				inspector,
				'/status',
			)[0],
			404,
		)
		status, body, headers = self.fetch(
			inspector,
			'/ping',
			'POST',
		)
		self.assertEqual(
			status,
			405,
		)
		self.assertEqual(
			headers['Allow'],
			'GET, HEAD',
		)

	def test_setup_failure_releases_http_and_connection(self):
		def fail(worker):
			raise RuntimeError('setup failed')

		worker, consumer, inspector = self.make_worker(setups=fail)
		with self.assertRaisesRegex(
			RuntimeError,
			'setup failed',
		):
			worker.run()
		self.broker.close.assert_called_once()
		self.assertFalse(worker.running.is_set())
		self.assertFalse(require_value(inspector.thread).is_alive())
		self.assertEqual(
			require_value(inspector.server).fileno(),
			-1,
		)

	def test_bind_failure_is_explicit_and_does_not_connect_broker(self):
		worker, consumer, inspector = self.make_worker()
		with socket() as occupied:
			occupied.bind((
				'127.0.0.1',
				0,
			))
			occupied.listen()
			inspector.port = occupied.getsockname()[1]
			with self.assertRaises(OSError):
				worker.run()
		self.broker.connect.assert_not_called()
		self.assertTrue(worker.finished.is_set())
		self.assertTrue(self.pool.closed)

	def test_validation(self):
		for path in (
			'health',
			'/ping?query=1',
			'/ping#fragment',
		):
			with self.assertRaises(ValueError):
				Ping(path)
		with self.assertRaisesRegex(
			ValueError,
			'Duplicate',
		):
			Inspector(exts=(
				Ping('/same'),
				Metrics('/same'),
			))
		for timeout in (
			0,
			-1,
			float('inf'),
			float('nan'),
			True,
		):
			with self.assertRaises(ValueError):
				Ping(
					'/ping',
					timeout=timeout,
				)

	def test_inspector_cannot_be_shared_or_stop_its_original_worker(self):
		worker, consumer, inspector = self.make_worker()
		self.launch(worker)
		self.assertTrue(consumer.ready.wait(5))
		other = Worker(
			Mock(),
			ThreadPool(1),
			inspector=inspector,
		)
		other.add(Add)
		with self.assertRaisesRegex(
			RuntimeError,
			'only be attached',
		):
			other.run()
		self.assertTrue(require_value(inspector.thread).is_alive())
		self.assertEqual(
			self.fetch(
				inspector,
				'/ping',
			)[0],
			200,
		)

if __name__ == '__main__':
	main()
