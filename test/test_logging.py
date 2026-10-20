from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from importlib.util import (
	module_from_spec,
	spec_from_file_location,
)
from io import StringIO
from logging import (
	DEBUG,
	ERROR,
	FileHandler,
	Formatter,
	INFO,
	WARNING,
	getLogger,
)
from pathlib import Path
from os import environ
from subprocess import run
from sys import executable
from threading import Event
from tempfile import TemporaryDirectory
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Worker import (
	Pool,
	PoolFull,
	PoolSetup,
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
)
from DefStream.Worker.Executor import Executor


class Example(Run, parameters={'queue': 'example'}):
	def run(self, value: str = 'private-payload') -> str:
		return value


class Failure(Run, parameters={'queue': 'failure'}):
	def run(self) -> None:
		raise ValueError('작업 실패 예제')


class ProcessLoggingSetup(PoolSetup):
	def __init__(self, path: str):
		self.path = path

	def __call__(self) -> None:
		handler = FileHandler(
			self.path,
			encoding='utf-8',
		)
		handler.setFormatter(Formatter('%(processName)s %(name)s %(message)s'))
		root = getLogger()
		root.setLevel(DEBUG)
		root.addHandler(handler)
		return


class LoggingTests(TestCase):
	def test_in_memory_samples_emit_sample_and_framework_logs(self):
		root = Path(__file__).resolve().parents[1]
		for relative in (
			('Worker', 'Sample.py'),
			('Broker', 'Sample.py'),
		):
			with self.subTest(sample=relative):
				path = root.joinpath('sample', *relative)
				result = run(
					[
						executable,
						str(path),
					],
					capture_output=True,
					text=True,
					encoding='utf-8',
					env={
						**environ,
						'PYTHONIOENCODING': 'utf-8',
					},
					timeout=20,
					check=True,
				)
				self.assertIn('Sample INFO', result.stderr)
				if relative[0] == 'Worker':
					self.assertIn('DefStream.Worker INFO', result.stderr)
					self.assertIn('DefStream.Run DEBUG', result.stderr)
					self.assertIn('Starting Worker', result.stdout)
				else:
					self.assertEqual(result.stdout, '')

	def test_spawn_child_logging_is_configured_by_pool_setup(self):
		with TemporaryDirectory() as directory:
			path = Path(directory) / 'child.log'
			pool = ProcessPool(
				max=1,
				setups=ProcessLoggingSetup(str(path)),
			)
			try:
				self.assertEqual(pool.submit(Example, {}).result(timeout=15), 'private-payload')
			finally:
				pool.stop()
			output = path.read_text(encoding='utf-8')
			self.assertIn('DefStream.Run', output)
			self.assertIn('DefStream.Executor', output)
			self.assertIn('SpawnProcess', output)
			self.assertNotIn('private-payload', output)

	def test_class_members_and_pool_inheritance(self):
		class CustomPool(ThreadPool):
			pass

		for cls, name in (
			(
				Pool,
				'DefStream.Pool',
			),
			(
				ThreadPool,
				'DefStream.ThreadPool',
			),
			(
				ProcessPool,
				'DefStream.ProcessPool',
			),
			(
				CustomPool,
				'DefStream.ThreadPool',
			),
			(
				Run,
				'DefStream.Run',
			),
			(
				Example,
				'DefStream.Run',
			),
			(
				Worker,
				'DefStream.Worker',
			),
			(
				Executor,
				'DefStream.Executor',
			),
		):
			with self.subTest(cls=cls):
				self.assertEqual(cls.logger.name, name)
				self.assertEqual(cls.logger.handlers, [])
				self.assertTrue(cls.logger.propagate)

	def test_pool_common_methods_use_concrete_member(self):
		for cls in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(cls=cls), self.assertLogs(cls.logger, level=DEBUG) as logs:
				pool = cls(max=1)
				try:
					self.assertEqual(pool.submit(Example, {}).result(timeout=15), 'private-payload')
					pool.waits(timeout=15)
				finally:
					pool.stop()
			self.assertEqual({record.name for record in logs.records}, {cls.logger.name})
			self.assertIn(DEBUG, {record.levelno for record in logs.records})
			self.assertIn(INFO, {record.levelno for record in logs.records})
			self.assertNotIn('private-payload', '\n'.join(logs.output))

	def test_pool_override_is_used_by_inherited_methods(self):
		class CustomPool(ThreadPool):
			logger = getLogger('Sample.CustomPool')

		with self.assertLogs('Sample.CustomPool', level=DEBUG) as logs:
			pool = CustomPool(max=1)
			pool.stop()
		self.assertTrue(all(record.name == 'Sample.CustomPool' for record in logs.records))

	def test_pool_capacity_is_debug_and_wait_timeout_is_warning(self):
		executor = Mock()
		future = Mock()
		executor.submit.return_value = future
		with self.assertLogs('DefStream.Pool', level=DEBUG) as logs:
			pool = Pool(executor, max=1)
			pool.submit(Example, {})
			with self.assertRaises(PoolFull):
				pool.submit(Example, {})
			pool.stop()
		self.assertFalse(any(record.levelno >= WARNING for record in logs.records))
		with ThreadPoolExecutor(max_workers=1) as external:
			pool = Pool(external, max=1)
			with self.assertLogs('DefStream.Pool', level=WARNING) as warnings:
				release = Event()
				pending = external.submit(release.wait)
				pool.futures.add(pending)
				try:
					with self.assertRaises(TimeoutError):
						pool.waits(timeout=0)
				finally:
					release.set()
					pool.stop()
			self.assertEqual(warnings.records[0].levelno, WARNING)

	def test_run_logs_framework_name_and_not_arguments_or_results(self):
		with self.assertLogs('DefStream.Run', level=DEBUG) as logs:
			self.assertEqual(Example()(), 'private-payload')
		output = '\n'.join(logs.output)
		self.assertIn(__name__ + '.Example', output)
		self.assertNotIn('private-payload', output)
		self.assertTrue(all(record.levelno == DEBUG for record in logs.records))
		with self.assertLogs('DefStream.Run', level=DEBUG) as failed:
			with self.assertRaises(ValueError):
				Failure()()
		self.assertFalse(any(record.exc_info for record in failed.records))

	def test_worker_records_lifecycle_without_changing_banner(self):
		consumer = Mock()

		class Broker:
			def connect(self) -> None:
				return

			def close(self) -> None:
				return

			def consumer(self):
				return consumer

		broker = Broker()
		worker = Worker(broker, Mock())
		output = StringIO()
		with self.assertLogs('DefStream.Worker', level=DEBUG) as logs, redirect_stdout(output):
			worker.add(Example)
			worker.run()
		self.assertIn('Starting Worker', output.getvalue())
		self.assertIn(INFO, {record.levelno for record in logs.records})
		self.assertIn(DEBUG, {record.levelno for record in logs.records})
		self.assertIn('Worker shutdown completed', logs.records[-1].getMessage())
		self.assertNotIn('private-payload', '\n'.join(logs.output))

	def test_invalid_message_is_warning_and_task_failure_has_one_traceback(self):
		worker = Worker(Mock(), Mock())
		worker.consumer = Mock()
		event = Mock()
		event.body = 'private-payload'
		with self.assertLogs('DefStream', level=DEBUG) as invalid:
			worker.receive(Example, event)
		self.assertEqual(sum(record.levelno == WARNING for record in invalid.records), 1)
		self.assertFalse(any(record.levelno >= ERROR for record in invalid.records))
		worker.consumer.fail.assert_called_once_with(event, Example.on_error)
		try:
			raise ValueError('작업 실패 예제')
		except ValueError as error:
			with self.assertLogs('DefStream', level=DEBUG) as failed:
				worker.failed(Failure, event, error)
		self.assertEqual(sum(record.levelno == ERROR for record in failed.records), 1)
		self.assertEqual(sum(bool(record.exc_info) for record in failed.records), 1)

	def test_sample_filter_allows_only_sample_and_defstream_hierarchies(self):
		root = getLogger()
		handlers = root.handlers[:]
		level = root.level
		path = Path(__file__).resolve().parents[1] / 'sample' / 'Worker' / 'Sample.py'
		spec = spec_from_file_location('sample_logging_test', path)
		self.assertIsNotNone(spec)
		assert spec is not None and spec.loader is not None
		sample = module_from_spec(spec)
		try:
			spec.loader.exec_module(sample)
			self.assertEqual(root.handlers, handlers)
			sample.SetupLogger()(Mock())
			handler = root.handlers[-1]
			for name, expected in (
				(
					'Sample',
					True,
				),
				(
					'Sample.Task',
					True,
				),
				(
					'DefStream',
					True,
				),
				(
					'DefStream.Worker',
					True,
				),
				(
					'SampleExtra',
					False,
				),
				(
					'DefStreamExtra',
					False,
				),
				(
					'pika',
					False,
				),
				(
					'redis',
					False,
				),
				(
					'root',
					False,
				),
			):
				with self.subTest(name=name):
					record = root.makeRecord(name, DEBUG, '', 0, '메시지', (), None)
					self.assertEqual(bool(handler.filter(record)), expected)
		finally:
			for handler in root.handlers:
				if handler not in handlers:
					handler.close()
			root.handlers = handlers
			root.setLevel(level)


if __name__ == '__main__':
	main()
