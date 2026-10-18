from pathlib import Path
from tempfile import TemporaryDirectory
from threading import get_ident
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from src.Broker.Implements.RabbitMQ import Reject
from src.Worker import (
	RunComplete,
	RunError,
	Context,
	RunSetup,
	PoolFull,
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
)
from test_worker import FakeConsumer


def record(parameters, name):
	with Path(parameters.kwargs['path']).open('a', encoding='utf-8') as stream:
		stream.write(name + '\n')
	if parameters.kwargs.get('failure') == name:
		raise ValueError(name)


class SetupHook(RunSetup):
	def __init__(self, name):
		self.name = name

	def __call__(self, parameters):
		record(parameters, self.name)


class CompleteHook(RunComplete):
	def __init__(self, name):
		self.name = name

	def __call__(self, parameters, completion):
		if completion != 'result':
			raise AssertionError('Unexpected completion result')
		record(parameters, self.name)


class ErrorHook(RunError):
	def __init__(self, name):
		self.name = name

	def __call__(self, parameters, error):
		if not isinstance(error, ValueError):
			raise AssertionError('Unexpected runner exception')
		record(parameters, self.name)


class HookRunner(
	Run,
	parameters={'queue': 'hooks'},
	on_error=Reject(),
	setups=[SetupHook('setup1'), SetupHook('setup2')],
	completes=[CompleteHook('complete1'), CompleteHook('complete2')],
	errors=[ErrorHook('error1'), ErrorHook('error2')],
):
	def run(self, path, failure=None):
		record(Context(path=path, failure=failure), 'run')
		if failure == 'error1':
			raise ValueError('run')
		return 'result'


class HookTests(TestCase):
	def test_direct_call_executes_hooks_and_returns_result(self):
		with TemporaryDirectory() as directory:
			path = str(Path(directory) / 'trace')
			instance = HookRunner()
			self.assertEqual(instance(path=path), 'result')
			self.assertEqual(
				Path(path).read_text().splitlines(),
				['setup1', 'setup2', 'run', 'complete1', 'complete2'],
			)

	def test_direct_failure_runs_errors_and_propagates(self):
		with TemporaryDirectory() as directory:
			path = str(Path(directory) / 'trace')
			with self.assertRaisesRegex(ValueError, 'run'):
				HookRunner()(path=path, failure='run')
			self.assertEqual(
				Path(path).read_text().splitlines(),
				['setup1', 'setup2', 'run', 'error1', 'error2'],
			)

	def test_direct_call_passes_positional_arguments_through_context(self):
		setup, complete = Mock(), Mock()

		class Add(Run, setups=setup, completes=complete):
			def run(self, a, b):
				return a + b

		self.assertEqual(Add()(2, b=3), 5)
		context = setup.call_args.args[0]
		self.assertEqual(context.args, (2,))
		self.assertEqual(context.kwargs, {'b': 3})
		complete.assert_called_once_with(context, 5)

	def test_constructor_failure_releases_capacity(self):
		class Broken(Run):
			def __init__(self):
				raise ValueError('constructor failed')

			def run(self):
				pass

		pool = ThreadPool(1)
		try:
			for _ in range(2):
				with self.assertRaisesRegex(ValueError, 'constructor failed'):
					pool.submit(Broken, {})
			self.assertEqual(pool.count(), 0)
		finally:
			pool.stop()

	def test_lifecycle_and_settlement_order_with_both_pools(self):
		cases = (
			(None, ['setup1', 'setup2', 'run', 'complete1', 'complete2'], 'ack'),
			('run', ['setup1', 'setup2', 'run', 'error1', 'error2'], 'reject'),
			('setup1', ['setup1'], 'reject'),
			('complete1', ['setup1', 'setup2', 'run', 'complete1'], 'reject'),
			('error1', ['setup1', 'setup2', 'run', 'error1'], 'reject'),
		)
		for pool_cls in (ThreadPool, ProcessPool):
			for failure, expected, action in cases:
				with self.subTest(pool=pool_cls, failure=failure), TemporaryDirectory() as directory:
					path = str(Path(directory) / 'trace')
					consumer = FakeConsumer()
					broker = Mock()
					broker.consumer.return_value = consumer
					worker = Worker(broker, pool_cls(1))
					worker.add(HookRunner)
					delivery = Mock()
					delivery.body = {'path': path, 'failure': failure}
					observed = []

					def settle():
						observed.append((get_ident(), Path(path).read_text().splitlines()))

					getattr(delivery, action).side_effect = settle

					def receive():
						consumer.handlers['hooks'](delivery)
						worker.stop()

					consumer.on_run = receive
					if failure is None:
						worker.run()
					else:
						with self.assertLogs('src.Worker.Worker', level='ERROR'):
							worker.run()
					self.assertEqual(observed, [(consumer.owner, expected)])
					getattr(delivery, action).assert_called_once_with()
					if action == 'reject':
						delivery.ack.assert_not_called()

	def test_hooks_hold_pool_capacity_until_finished(self):
		from threading import Event
		started, release = Event(), Event()

		class BlockingComplete(RunComplete):
			def __call__(self, parameters, completion):
				started.set()
				if not release.wait(5):
					raise TimeoutError('Hook was not released')

		class BlockingRunner(Run, completes=BlockingComplete()):
			def run(self):
				return None

		pool = ThreadPool(1)
		try:
			future = pool.submit(BlockingRunner, {})
			self.assertTrue(started.wait(5))
			self.assertFalse(future.done())
			with self.assertRaises(PoolFull):
				pool.submit(BlockingRunner, {})
			release.set()
			future.result(5)
		finally:
			release.set()
			pool.stop()

	def test_hooks_support_single_sequence_inheritance_and_reset(self):
		hook = SetupHook('setup')

		class Parent(Run, setups=hook):
			def run(self):
				pass

		class Child(Parent):
			pass

		class Empty(Parent, setups=[]):
			pass

		self.assertEqual(Parent.setups, (hook,))
		self.assertEqual(Child.setups, (hook,))
		self.assertEqual(Empty.setups, ())
		with self.assertRaises(TypeError):
			class Invalid(Parent, errors=['invalid']):
				pass


if __name__ == '__main__':
	main()
