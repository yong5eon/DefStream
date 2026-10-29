from concurrent.futures import (
	Executor as PyExecutor,
	Future,
	ThreadPoolExecutor,
)
from multiprocessing import get_context
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event as ProcessEvent
from logging import getLogger
from multiprocessing.managers import SyncManager
from pickle import (
	dumps,
	loads,
)
from queue import (
	Empty,
	Queue,
)
from signal import (
	SIGINT,
	SIG_IGN,
	signal,
)
from threading import (
	Event,
	Lock,
	Thread,
)
from traceback import format_exc
from typing import (
	Any,
	Callable,
	Dict,
	List,
	Optional,
	Sequence,
	Set,
	TypeVar,
	Union,
)

__all__ = (
	'Executor',
)

Result = TypeVar('Result')


def initialize_process() -> None:
	# 부모 프로세스가 종료 요청과 정리를 조정한다.
	signal(
		SIGINT,
		SIG_IGN,
	)


def execute_loop(
	incoming: Any,
	outgoing: Any,
	setups: Sequence[Callable[[], None]],
	cleanups: Sequence[Callable[[], None]],
	serialized: bool,
	stopping: Union[Event, ProcessEvent],
	draining: Optional[ProcessEvent] = None,
) -> None:
	if serialized:
		initialize_process()
	logger = Executor.logger
	ready = False
	try:
		for setup in setups:
			logger.debug(
				'Starting execution environment setup: hook=%s',
				type(setup).__qualname__,
			)
			setup()
			logger.debug(
				'Execution environment setup completed: hook=%s',
				type(setup).__qualname__,
			)
		ready = True
		logger.debug(
			'Execution unit ready: serialized=%s',
			serialized,
		)
		while True:
			item = incoming.get()
			if item is None or stopping.is_set():
				if draining is not None:
					draining.set()
				return
			key, payload = item
			logger.debug(
				'Execution unit task received: key=%s',
				key,
			)
			try:
				function, args, kwargs = loads(payload) if serialized else payload
				result = function(
					*args,
					**kwargs,
				)
			except BaseException as error:
				logger.debug(
					'Execution unit task failed: key=%s error_type=%s',
					key,
					type(error).__qualname__,
				)
				outcome = (
					False,
					error,
					format_exc() if serialized else None,
				)
			else:
				outcome = (
					True,
					result,
					None,
				)
			if serialized:
				try:
					outcome = dumps(outcome)
				except Exception as error:
					logger.error(
						'Task outcome serialization failed: key=%s error_type=%s',
						key,
						type(error).__qualname__,
					)
					outcome = dumps((
						False,
						RuntimeError('Cannot serialize task outcome: ' + repr(error)),
						format_exc(),
					))
			outgoing.put((
				key,
				outcome,
			))
			logger.debug(
				'Execution unit result sent: key=%s',
				key,
			)
	finally:
		if ready:
			logger.debug(
				'Starting execution environment cleanup: hooks=%s',
				len(cleanups),
			)
			run_cleanups(cleanups)
			logger.debug('Execution environment cleanup completed')


def run_cleanups(
	cleanups: Sequence[Callable[..., None]],
	*args: Any,
) -> None:
	failure: Optional[BaseException] = None
	for cleanup in cleanups:
		try:
			cleanup(*args)
		except BaseException as error:
			if failure is not None:
				error.__context__ = failure
			failure = error
	if failure is not None:
		raise failure


def execute_process(
	incoming: Any,
	outgoing: Any,
	setups: Sequence[Callable[[], None]],
	cleanups: Sequence[Callable[[], None]],
	serialized: bool,
	stopping: Union[Event, ProcessEvent],
	draining: ProcessEvent,
	completed: ProcessEvent,
) -> None:
	try:
		execute_loop(
			incoming,
			outgoing,
			setups,
			cleanups,
			serialized,
			stopping,
			draining,
		)
	except BaseException as error:
		traceback = format_exc()
		try:
			outcome = dumps((
				False,
				(
					error,
					draining.is_set(),
				),
				traceback,
			))
		except Exception:
			Executor.logger.exception('Execution environment error serialization failed')
			outcome = dumps((
				False,
				(
					RuntimeError('Cannot serialize execution environment error'),
					draining.is_set(),
				),
				traceback,
			))
		outgoing.put((
			None,
			outcome,
		))
	finally:
		completed.set()
	return


class Executor(PyExecutor):
	logger = getLogger('Worker.Executor')

	def __init__(
		self,
		size: int,
		setups: Sequence[Callable[[], None]],
		cleanups: Sequence[Callable[[], None]],
		process: bool = False,
	):
		self.size = size
		self.setups = setups
		self.cleanups = cleanups
		self.process = process
		self.lock = Lock()
		self.pending: Dict[int, Future[Any]] = {}
		self.workers: List[Future] = []
		self.processes: List[BaseProcess] = []
		self.draining: Dict[int, ProcessEvent] = {}
		self.completed: Dict[int, ProcessEvent] = {}
		self.process_lock = Lock()
		self.stopping: Union[Event, ProcessEvent] = Event()
		self.closed = False
		self.failure: Optional[BaseException] = None
		self.manager: Optional[SyncManager] = None
		self.executor: Optional[PyExecutor] = None
		self.monitor: Optional[Thread] = None
		self.incoming: Any = None
		self.outgoing: Any = None
		self.sequence = 0

	def start(self) -> None:
		self.logger.info(
			'Starting Executor: concurrency=%s process=%s',
			self.size,
			self.process,
		)
		try:
			context = get_context('spawn')
			if self.process:
				self.stopping = context.Event()
				self.manager = context.Manager()
				self.incoming = self.manager.Queue()
				self.outgoing = self.manager.Queue()
			else:
				self.incoming = Queue()
				self.outgoing = Queue()
				self.executor = ThreadPoolExecutor(self.size)
			for _ in range(self.size):
				parameters = (
					self.incoming,
					self.outgoing,
					self.setups,
					self.cleanups,
					self.process,
					self.stopping,
				)
				if self.process:
					draining = context.Event()
					completed = context.Event()
					process = context.Process(
						target=execute_process,
						args=parameters + (
							draining,
							completed,
						),
					)
					process.start()
					self.processes.append(process)
					if process.pid is None:
						raise RuntimeError('Started process has no PID')
					# Keep named semaphores alive until spawned children have exited.
					self.draining[process.pid] = draining
					self.completed[process.pid] = completed
				else:
					if self.executor is None:
						raise RuntimeError('Thread executor is not initialized')
					self.workers.append(self.executor.submit(
						execute_loop,
						*parameters,
					))
			monitor = Thread(target=self.collect)
			monitor.start()
			self.monitor = monitor
			self.logger.info('Executor execution environment ready')
		except BaseException:
			self.logger.exception('Executor startup failed')
			self.closed = True
			try:
				for _ in self.workers:
					self.incoming.put(None)
			finally:
				try:
					if self.executor is not None:
						self.executor.shutdown(wait=True)
					for process in self.processes:
						process.terminate()
						process.join()
				finally:
					if self.manager is not None:
						self.manager.shutdown()
			raise

	def submit(
		self,
		fn: Callable[..., Result],
		/,
		*args: Any,
		**kwargs: Any,
	) -> Future[Result]:
		payload = (
			fn,
			args,
			kwargs,
		)
		if self.process:
			payload = dumps(payload)
		with self.lock:
			if self.closed:
				raise RuntimeError('Pool is closed')
			if self.failure is not None:
				raise RuntimeError('Pool execution environment failed') from self.failure
			if self.monitor is None:
				self.start()
			key = self.sequence
			self.sequence += 1
			future: Future[Result] = Future()
			future.set_running_or_notify_cancel()
			self.pending[key] = future
			self.logger.debug(
				'Dispatching task to execution environment: key=%s pending=%s',
				key,
				len(self.pending),
			)
			try:
				self.incoming.put((
					key,
					payload,
				))
			except BaseException:
				del self.pending[key]
				raise
			return future

	def collect(self) -> None:
		try:
			self.collect_results()
		except BaseException as error:
			self.fail(error)

	def fail(
		self,
		error: BaseException,
		*,
		report: bool = True,
	) -> None:
		with self.lock:
			first_failure = self.failure is None
			self.failure = error
			pending = tuple(self.pending.values())
			self.pending.clear()
		if self.process:
			self.stopping.set()
			self.stop_processes()
		if report and (first_failure or self.stopping.is_set()):
			self.logger.error(
				'Executor execution environment failed: pending=%s',
				len(pending),
				exc_info=(
					type(error),
					error,
					error.__traceback__,
				),
			)
		for future in pending:
			future.set_exception(error)

	def collect_results(self) -> None:
		observed: Set[Future] = set()
		while True:
			no_outcome = False
			try:
				key, outcome = self.outgoing.get(timeout=0.05)
			except Empty:
				no_outcome = True
			else:
				success, value, traceback = loads(outcome) if self.process else outcome
				if key is None:
					error, draining = value
					if traceback is not None:
						error.__cause__ = RuntimeError('Remote execution traceback:\n' + traceback)
					if draining and self.closed and not self.stopping.is_set():
						with self.lock:
							self.failure = error
						self.logger.error('Execution environment cleanup failed', exc_info=(
							type(error),
							error,
							error.__traceback__,
						))
					else:
						self.fail(error)
					continue
				self.logger.debug(
					'Execution result collected: key=%s success=%s',
					key,
					success,
				)
				with self.lock:
					future = self.pending.pop(
						key,
						None,
					)
				if future is not None:
					if success:
						future.set_result(value)
					else:
						if traceback is not None:
							value.__cause__ = RuntimeError('Remote execution traceback:\n' + traceback)
						future.set_exception(value)
			for worker in self.workers:
				if worker.done() and worker not in observed:
					observed.add(worker)
					failure: Optional[BaseException] = worker.exception()
					if failure is not None:
						self.fail(failure)
			if not self.stopping.is_set() and any(
				process.pid is not None and process.exitcode is not None and (
					process.exitcode != 0 or not self.completed[process.pid].is_set()
				)
				for process in self.processes
			):
				self.fail(RuntimeError('Pool execution process failed'))
			with self.lock:
				finished = (
					not self.pending
					and all(worker.done() for worker in self.workers)
					and all(not process.is_alive() for process in self.processes)
					and (not self.process or no_outcome)
				)
			if finished:
				return

	def shutdown(
		self,
		wait: bool = True,
		*,
		cancel_futures: bool = False,
	) -> None:
		self.logger.info(
			'Executor shutdown requested: wait=%s',
			wait,
		)
		with self.lock:
			if not self.closed:
				self.closed = True
				if self.monitor is not None:
					for _ in range(self.size):
						self.incoming.put(None)
			executor = self.executor
		if self.monitor is None:
			self.logger.debug('Closing an unstarted Executor')
			return
		if executor is not None:
			executor.shutdown(wait=wait)
		if wait:
			for process in self.processes:
				process.join()
			if self.monitor is not None:
				self.monitor.join()
			if self.manager is not None:
				self.manager.shutdown()
			if self.failure is not None:
				raise RuntimeError('Pool execution environment failed') from self.failure
			self.logger.info('Executor shutdown completed')
		return

	def replacement(self) -> 'Executor':
		return Executor(
			self.size,
			self.setups,
			self.cleanups,
			process=self.process,
		)

	def stop_processes(self) -> None:
		"""Reap surviving processes before publishing failures for their tasks."""
		with self.process_lock:
			for process in self.processes:
				if process.is_alive():
					process.kill()
			for process in self.processes:
				process.join()
		return

	def abort(self) -> None:
		"""Discard this execution generation without waiting for running threads."""
		self.stopping.set()
		if self.process:
			self.stop_processes()
		self.logger.warning('Discarding execution generation: pending=%s', len(self.pending))
		self.fail(RuntimeError('Execution generation discarded'), report=False)
		self.shutdown(wait=False)
		if self.process:
			if self.monitor is not None:
				self.monitor.join()
			if self.manager is not None:
				self.manager.shutdown()
		return
