from multiprocessing import active_children
from os import (
	_exit,
	getpid,
)
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import get_ident
from time import (
	monotonic,
	sleep,
)
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Worker import (
	PoolCleanup,
	PoolSetup,
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
	WorkerCleanup,
	WorkerSetup,
)
from _support import (
	call_with_invalid_input,
	require_value,
)


def identity():
	return f'{getpid()}-{get_ident()}'


class TraceSetup(PoolSetup):
	def __init__(
		self,
		directory,
		fail=False,
	):
		self.directory = directory
		self.fail = fail

	def __call__(self):
		path = Path(self.directory) / identity()
		path.write_text(
			'setup\n',
			encoding='utf-8',
		)
		if self.fail:
			raise ValueError('setup failed')


class TraceCleanup(PoolCleanup):
	def __init__(
		self,
		directory,
		label='cleanup',
		fail=False,
	):
		self.directory = directory
		self.label = label
		self.fail = fail

	def __call__(self):
		path = Path(self.directory) / identity()
		with path.open(
			'a',
			encoding='utf-8',
		) as stream:
			stream.write(self.label + '\n')
		if self.fail:
			raise ValueError('cleanup failed')


class IdentityRun(Run):
	def run(self):
		return identity()


class ConcurrentIdentityRun(Run):
	def run(
		self,
		directory,
	):
		current = identity()
		path = Path(directory)
		(path / (current + '.ready')).touch()
		deadline = monotonic() + 15
		while len(list(path.glob('*.ready'))) < 3:
			if monotonic() >= deadline:
				raise TimeoutError('Three pool execution environments did not start')
			sleep(0.01)
		return current


class CrashRun(Run):
	def run(self):
		_exit(1)


class UnpicklableRun(Run):
	def run(self):
		return lambda: None


class FailingRun(Run):
	def run(self):
		raise ValueError('task failed')


class LifecycleTests(TestCase):
	def test_pool_hooks_run_once_in_each_execution_environment(self):
		for pool_class in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(pool=pool_class), TemporaryDirectory() as directory:
				children = {child.pid for child in active_children()}
				ready = Path(directory) / 'ready'
				ready.mkdir()
				pool = pool_class(
					3,
					setups=TraceSetup(directory),
					cleanups=TraceCleanup(directory),
				)
				try:
					futures = [
						pool.submit(
							ConcurrentIdentityRun,
							{'directory': str(ready)},
						)
						for index in range(3)
					]
					identities = {future.result(timeout=30) for future in futures}
				finally:
					pool.stop()
				self.assertEqual(
					len(identities),
					3,
				)
				self.assertEqual(
					{child.pid for child in active_children()} - children,
					set(),
				)
				traces = {
					path.name: path.read_text(encoding='utf-8').splitlines()
					for path in Path(directory).iterdir()
					if path.is_file()
				}
				self.assertEqual(
					len(traces),
					3,
				)
				for future in futures:
					self.assertIn(
						future.result(timeout=5),
						traces,
					)
				for trace in traces.values():
					self.assertEqual(
						trace,
						[
							'setup',
							'cleanup',
						],
					)
				pool.stop()

	def test_task_failure_still_cleans_up_successful_environment(self):
		for pool_class in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(pool=pool_class), TemporaryDirectory() as directory:
				pool = pool_class(
					1,
					setups=TraceSetup(directory),
					cleanups=TraceCleanup(directory),
				)
				try:
					future = pool.submit(
						FailingRun,
						{},
					)
					with self.assertRaisesRegex(
						ValueError,
						'task failed',
					):
						future.result(timeout=15)
					if pool_class is ProcessPool:
						exception = require_value(future.exception())
						self.assertIn(
							"raise ValueError('task failed')",
							str(exception.__cause__),
						)
				finally:
					pool.stop()
				trace = next(Path(directory).iterdir())
				self.assertEqual(
					trace.read_text(encoding='utf-8').splitlines(),
					[
						'setup',
						'cleanup',
					],
				)

	def test_setup_failure_reaches_future_and_shutdown(self):
		for pool_class in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(pool=pool_class), TemporaryDirectory() as directory:
				pool = pool_class(
					1,
					setups=TraceSetup(
						directory,
						fail=True,
					),
					cleanups=TraceCleanup(directory),
				)
				future = pool.submit(
					IdentityRun,
					{},
				)
				with self.assertRaisesRegex(
					ValueError,
					'setup failed',
				):
					future.result(timeout=15)
				with self.assertRaisesRegex(
					RuntimeError,
					'execution environment failed',
				):
					pool.stop()
				traces = list(Path(directory).iterdir())
				self.assertEqual(
					traces[0].read_text(encoding='utf-8'),
					'setup\n',
				)

	def test_cleanup_failure_does_not_skip_other_cleanups(self):
		for pool_class in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(pool=pool_class), TemporaryDirectory() as directory:
				pool = pool_class(
					1,
					setups=TraceSetup(directory),
					cleanups=[
						TraceCleanup(
							directory,
							fail=True,
						),
						TraceCleanup(
							directory,
							label='last',
						),
					],
				)
				pool.submit(
					IdentityRun,
					{},
				).result(timeout=15)
				with self.assertRaisesRegex(
					RuntimeError,
					'execution environment failed',
				):
					pool.stop()
				trace = next(Path(directory).iterdir())
				self.assertEqual(
					trace.read_text(encoding='utf-8').splitlines(),
					[
						'setup',
						'cleanup',
						'last',
					],
				)

	def test_unused_pool_does_not_run_hooks(self):
		for pool_class in (
			ThreadPool,
			ProcessPool,
		):
			setup = Mock()
			cleanup = Mock()
			pool = pool_class(
				1,
				setups=setup,
				cleanups=cleanup,
			)
			pool.stop()
			setup.assert_not_called()
			cleanup.assert_not_called()

	def test_process_crash_is_reported_without_hanging(self):
		pool = ProcessPool(1)
		future = pool.submit(
			CrashRun,
			{},
		)
		with self.assertRaises(Exception):
			future.result(timeout=15)
		with self.assertRaisesRegex(
			RuntimeError,
			'execution environment failed',
		):
			pool.stop()

	def test_unpicklable_result_fails_task_not_pool(self):
		pool = ProcessPool(1)
		try:
			future = pool.submit(
				UnpicklableRun,
				{},
			)
			with self.assertRaisesRegex(
				RuntimeError,
				'Cannot serialize task outcome',
			):
				future.result(timeout=15)
			self.assertIsInstance(
				pool.submit(
					IdentityRun,
					{},
				).result(timeout=15),
				str,
			)
		finally:
			pool.stop()

	def test_hooks_are_validated_before_start(self):
		for owner in (
			ThreadPool,
			ProcessPool,
		):
			with self.assertRaises(TypeError):
				call_with_invalid_input(
					owner,
					1,
					cleanups=[object()],
				)
		with self.assertRaises(TypeError):
			call_with_invalid_input(
				Worker,
				Mock(),
				Mock(),
				setups=[object()],
			)


class WorkerLifecycleTests(TestCase):
	def make_worker(
		self,
		setups=None,
		cleanups=None,
	):
		class Example(
			Run,
			parameters={'queue': 'example'},
		):
			def run(self):
				pass

		broker = Mock(consumer=Mock())
		pool = Mock()
		self.broker = broker
		self.pool = pool
		worker = Worker(
			broker,
			pool,
			setups=setups,
			cleanups=cleanups,
		)
		worker.add(Example)
		return worker

	def test_worker_setup_can_provision_registered_runs_before_subscription(self):
		trace = []
		broker = self.broker
		pool = self.pool

		class Provision(WorkerSetup):
			def __call__(
				self,
				worker,
			):
				for run in worker.tasks:
					trace.append(run.parameters['queue'])
				broker.connect.assert_called_once_with()
				broker.consumer.assert_not_called()

		class Release(WorkerCleanup):
			def __call__(
				self,
				worker,
			):
				pool.stop.assert_called_once_with()
				broker.close.assert_not_called()
				trace.append('cleanup')

		worker = self.make_worker(
			setups=Provision(),
			cleanups=Release(),
		)
		worker.run()
		self.assertEqual(
			trace,
			[
				'example',
				'cleanup',
			],
		)
		broker.consumer.return_value.close.assert_called_once_with()
		broker.close.assert_called_once_with()

	def test_setup_failure_still_runs_cleanup_and_closes_resources(self):
		setup = Mock(side_effect=ValueError('setup failed'))
		cleanup = Mock()
		worker = self.make_worker(
			setups=setup,
			cleanups=cleanup,
		)
		with self.assertRaisesRegex(
			ValueError,
			'setup failed',
		):
			worker.run()
		cleanup.assert_called_once_with(worker)
		self.broker.consumer.assert_not_called()
		self.pool.stop.assert_called_once_with()
		self.broker.close.assert_called_once_with()

	def test_cleanup_failure_does_not_skip_hooks_or_resource_closure(self):
		first = Mock(side_effect=ValueError('cleanup failed'))
		last = Mock()
		worker = self.make_worker(cleanups=[
			first,
			last,
		])
		with self.assertRaisesRegex(
			ValueError,
			'cleanup failed',
		):
			worker.run()
		last.assert_called_once_with(worker)
		self.broker.consumer.return_value.close.assert_called_once_with()
		self.broker.close.assert_called_once_with()


if __name__ == '__main__':
	main()
