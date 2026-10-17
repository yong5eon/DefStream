from concurrent.futures import (
	Executor as PyExecutor,
	Future,
	ProcessPoolExecutor,
	ThreadPoolExecutor,
)
from multiprocessing import get_context
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
	TypeVar,
)

__all__ = (
	'Executor',
)

Result = TypeVar('Result')


def initialize_process() -> None:
	# The parent coordinates draining and cleanup after Ctrl+C.
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
) -> None:
	ready = False
	try:
		for setup in setups:
			setup()
		ready = True
		while True:
			item = incoming.get()
			if item is None:
				return
			key, payload = item
			try:
				function, args, kwargs = loads(payload) if serialized else payload
				result = function(
					*args,
					**kwargs,
				)
			except BaseException as error:
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
					outcome = dumps((
						False,
						RuntimeError('Cannot serialize task outcome: ' + repr(error)),
						format_exc(),
					))
			outgoing.put((
				key,
				outcome,
			))
	finally:
		if ready:
			run_cleanups(cleanups)


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


class Executor(PyExecutor):
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
		self.closed = False
		self.failure: Optional[BaseException] = None
		self.manager: Optional[SyncManager] = None
		self.executor: Optional[PyExecutor] = None
		self.monitor: Optional[Thread] = None
		self.incoming: Any = None
		self.outgoing: Any = None
		self.sequence = 0

	def start(self) -> None:
		try:
			if self.process:
				context = get_context('spawn')
				self.manager = context.Manager()
				self.incoming = self.manager.Queue()
				self.outgoing = self.manager.Queue()
				executor: PyExecutor = ProcessPoolExecutor(
					self.size,
					mp_context=context,
					initializer=initialize_process,
				)
			else:
				self.incoming = Queue()
				self.outgoing = Queue()
				executor = ThreadPoolExecutor(self.size)
			self.executor = executor
			for index in range(self.size):
				self.workers.append(executor.submit(
					execute_loop,
					self.incoming,
					self.outgoing,
					self.setups,
					self.cleanups,
					self.process,
				))
			monitor = Thread(target=self.collect)
			monitor.start()
			self.monitor = monitor
		except BaseException:
			self.closed = True
			try:
				for worker in self.workers:
					self.incoming.put(None)
			finally:
				try:
					if self.executor is not None:
						self.executor.shutdown(wait=True)
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
			if self.executor is None:
				self.start()
			key = self.sequence
			self.sequence += 1
			future: Future[Result] = Future()
			future.set_running_or_notify_cancel()
			self.pending[key] = future
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
	) -> None:
		with self.lock:
			self.failure = error
			pending = tuple(self.pending.values())
			self.pending.clear()
		for future in pending:
			future.set_exception(error)

	def collect_results(self) -> None:
		while True:
			try:
				key, outcome = self.outgoing.get(timeout=0.05)
			except Empty:
				pass
			else:
				success, value, traceback = loads(outcome) if self.process else outcome
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
			failure = next(
				(
					worker.exception()
					for worker in self.workers
					if worker.done() and worker.exception() is not None
				),
				None,
			)
			if failure is not None:
				self.fail(failure)
			with self.lock:
				finished = not self.pending and all(worker.done() for worker in self.workers)
			if finished:
				return

	def shutdown(
		self,
		wait: bool = True,
		*,
		cancel_futures: bool = False,
	) -> None:
		with self.lock:
			if not self.closed:
				self.closed = True
				if self.executor is not None:
					for worker in self.workers:
						self.incoming.put(None)
			executor = self.executor
		if executor is None:
			return
		executor.shutdown(wait=wait)
		if wait:
			if self.monitor is not None:
				self.monitor.join()
			if self.manager is not None:
				self.manager.shutdown()
			if self.failure is not None:
				raise RuntimeError('Pool execution environment failed') from self.failure
