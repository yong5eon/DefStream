from os import (
	environ,
	name,
	pathsep,
)
from pathlib import Path
from signal import (
	SIGINT,
	signal,
)
from subprocess import run
from sys import (
	argv,
	executable,
)
from tempfile import TemporaryDirectory
from threading import Event
from time import (
	monotonic,
	sleep,
)
from unittest import (
	TestCase,
	main,
	skipUnless,
)

from DefStream.Worker import (
	PoolCleanup,
	ProcessPool,
	Run,
)


class SlowRun(Run):
	def run(
		self,
		directory: str,
	) -> None:
		path = Path(directory)
		(path / 'started').touch()
		sleep(0.5)
		(path / 'completed').touch()


class Cleanup(PoolCleanup):
	def __init__(
		self,
		directory: str,
	):
		self.directory = directory

	def __call__(self) -> None:
		(Path(self.directory) / 'cleanup').touch()


def interrupt_probe(
	directory: str,
	idle: bool,
) -> None:
	from ctypes import WinDLL

	kernel = WinDLL(
		'kernel32',
		use_last_error=True,
	)
	# Remove an inherited Ctrl+C-ignore flag in this private console only.
	if not kernel.SetConsoleCtrlHandler(
		None,
		False,
	):
		raise OSError('Cannot enable Ctrl+C in test console')
	stopping = Event()
	previous = signal(
		SIGINT,
		lambda *_: stopping.set(),
	)
	pool = ProcessPool(
		1,
		cleanups=Cleanup(directory),
	)
	try:
		future = pool.submit(
			SlowRun,
			{'directory': directory},
		)
		deadline = monotonic() + 15
		while not (Path(directory) / 'started').exists():
			if future.done():
				future.result()
			if monotonic() >= deadline:
				raise TimeoutError('Child did not start')
			sleep(0.01)
		if idle:
			future.result(timeout=5)
		if not kernel.GenerateConsoleCtrlEvent(
			0,
			0,
		):
			raise OSError('Cannot generate isolated Ctrl+C')
		deadline = monotonic() + 5
		while not stopping.is_set():
			if monotonic() >= deadline:
				raise TimeoutError('Parent did not receive Ctrl+C')
			sleep(0.01)
		pool.stop()
		future.result(timeout=5)
	finally:
		try:
			pool.stop()
		finally:
			signal(
				SIGINT,
				previous,
			)


class ProcessSignalTests(TestCase):
	@skipUnless(
		name == 'nt',
		'Windows console signal regression',
	)
	def test_ctrl_c_finishes_task_and_cleanup_without_pool_failure(self):
		for mode in (
			'active',
			'idle',
		):
			with self.subTest(mode=mode):
				self.check_interrupt(mode)

	def check_interrupt(
		self,
		mode: str,
	) -> None:
		from subprocess import CREATE_NEW_CONSOLE

		with TemporaryDirectory() as directory:
			environment = environ.copy()
			environment['PYTHONPATH'] = pathsep.join(filter(
				None,
				(
					str(Path(__file__).resolve().parents[1]),
					environment.get('PYTHONPATH'),
				),
			))
			output = Path(directory) / 'output'
			with output.open('w') as stream:
				result = run(
					[
						executable,
						'-m',
						'test_process_signals',
						'--probe',
						directory,
						mode,
					],
					cwd=Path(__file__).resolve().parent,
					env=environment,
					stdout=stream,
					stderr=stream,
					timeout=30,
					creationflags=CREATE_NEW_CONSOLE,
				)
			text = output.read_text()
			self.assertEqual(
				result.returncode,
				0,
				text,
			)
			self.assertEqual(
				text,
				'',
			)
			for filename in (
				'completed',
				'cleanup',
			):
				self.assertTrue((Path(directory) / filename).exists())


if __name__ == '__main__':
	if len(argv) > 1 and argv[1] == '--probe':
		interrupt_probe(
			argv[2],
			argv[3] == 'idle',
		)
	else:
		main()
