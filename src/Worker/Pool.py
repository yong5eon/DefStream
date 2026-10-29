from abc import (
	ABC,
	abstractmethod,
)
from concurrent.futures import (
	Executor as PyExecutor,
	Future,
	wait,
)
from os import cpu_count
from logging import getLogger
from threading import (
	BoundedSemaphore,
	Lock,
)
from typing import (
	Any,
	Callable,
	Dict,
	Optional,
	Sequence,
	Set,
	Tuple,
	Type,
	Union,
)

from .Run import Run
from .Executor import Executor

__all__ = (
	'Pool',
	'PoolFull',
	'PoolSetup',
	'PoolCleanup',
	'ThreadPool',
	'ProcessPool',
)


class PoolFull(RuntimeError):
	pass


class Pool:
	logger = getLogger('Worker.Pool')

	def __init__(
		self,
		executor: PyExecutor,
		max: int,
	):
		self.pool = executor
		self.max = max
		self.slots = BoundedSemaphore(max)
		self.lock = Lock()
		self.futures: Set[Future] = set()
		self.closed = False
		self.stopped = False
		self.logger.info(
			'Pool configured: concurrency=%s',
			max,
		)

	def submit(
		self,
		run: Type[Run],
		body: Dict[str, Any],
		callback: Optional[Callable[[Any], None]] = None,
		error_callback: Optional[Callable[[BaseException], None]] = None,
	) -> Future:
		with self.lock:
			if self.closed:
				raise RuntimeError('Pool is closed')
			if not self.slots.acquire(blocking=False):
				self.logger.debug(
					'Pool capacity exhausted: active=%s capacity=%s',
					len(self.futures),
					self.max,
				)
				raise PoolFull('Pool capacity is exhausted')
			try:
				future = self.pool.submit(
					run(),
					**body,
				)
			except BaseException:
				self.slots.release()
				raise
			self.futures.add(future)
			futures = self.futures
			slots = self.slots
			self.logger.debug(
				'Task submission accepted: task=%s.%s active=%s',
				run.__module__,
				run.__qualname__,
				len(self.futures),
			)
		future.add_done_callback(lambda completed: self.complete(
			completed,
			callback,
			error_callback,
			futures,
			slots,
		))
		return future

	def complete(
		self,
		future: Future,
		callback: Optional[Callable[[Any], None]] = None,
		error_callback: Optional[Callable[[BaseException], None]] = None,
		futures: Optional[Set[Future]] = None,
		slots: Optional[BoundedSemaphore] = None,
	) -> None:
		with self.lock:
			active = self.futures if futures is None else futures
			capacity = self.slots if slots is None else slots
			active.remove(future)
			capacity.release()
			self.logger.debug(
				'Task slot released: active=%s',
				len(self.futures),
			)
		try:
			result = future.result()
		except BaseException as error:
			self.logger.debug(
				'Delivering failed result: error_type=%s',
				type(error).__qualname__,
			)
			if error_callback is not None:
				error_callback(error)
		else:
			self.logger.debug('Delivering successful result')
			if callback is not None:
				callback(result)

	def waits(
		self,
		timeout: Optional[float] = None,
	) -> None:
		with self.lock:
			tasks = tuple(self.futures)
		self.logger.debug(
			'Waiting for Pool tasks: active=%s timeout=%s',
			len(tasks),
			timeout,
		)
		if tasks and wait(
			tasks,
			timeout=timeout,
		).not_done:
			self.logger.warning(
				'Pool task wait timed out: timeout=%s',
				timeout,
			)
			raise TimeoutError('Pool tasks did not complete in time')

	def stop(self, *, abort: bool = False) -> None:
		self.logger.info('Stopping Pool')
		with self.lock:
			self.closed = True
			self.stopped = True
		if abort:
			if isinstance(self.pool, Executor):
				self.pool.abort()
			else:
				self.logger.warning('Custom executor shutdown cannot terminate running tasks')
				self.pool.shutdown(wait=False)
		else:
			self.pool.shutdown(wait=True)
		self.logger.info('Pool shutdown completed')
		return

	def restart(self) -> None:
		"""Replace the internal executor while preserving this Pool object."""
		with self.lock:
			if self.closed:
				raise RuntimeError('Pool is closed')
			previous = self.pool
			if not isinstance(previous, Executor):
				raise TypeError('Pool recovery requires a DefStream Executor')
			self.closed = True
		previous.abort()
		with self.lock:
			if self.stopped:
				return
			self.pool = previous.replacement()
			self.futures = set()
			self.slots = BoundedSemaphore(self.max)
			self.closed = False
		return

	def shutdown(self) -> None:
		self.stop()

	def size(self) -> int:
		return self.max

	def count(self) -> int:
		with self.lock:
			return len(self.futures)


class PoolSetup(ABC):
	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


class PoolCleanup(ABC):
	@abstractmethod
	def __call__(self) -> None:
		raise NotImplementedError


def pool_hooks(
	hooks: Optional[Union[Callable[[], None], Sequence[Callable[[], None]]]],
) -> Tuple[Callable[[], None], ...]:
	result = () if hooks is None else tuple(hooks) if isinstance(
		hooks,
		Sequence,
	) else (hooks,)
	if not all(callable(hook) for hook in result):
		raise TypeError('Pool hooks must be callable')
	return result


def pool_size(max: Optional[int]) -> int:
	if max is None:
		return cpu_count() or 1
	if isinstance(
		max,
		bool,
	) or not isinstance(
		max,
		int,
	) or max < 1:
		raise ValueError('Pool size must be a positive integer')
	return max


class ThreadPool(Pool):
	logger = getLogger('Worker.ThreadPool')

	def __init__(
		self,
		max: Optional[int] = None,
		setups: Optional[Union[PoolSetup, Sequence[PoolSetup]]] = None,
		cleanups: Optional[Union[PoolCleanup, Sequence[PoolCleanup]]] = None,
	):
		size = pool_size(max)
		super().__init__(
			Executor(
				size,
				pool_hooks(setups),
				pool_hooks(cleanups),
			),
			size,
		)


class ProcessPool(Pool):
	logger = getLogger('Worker.ProcessPool')

	def __init__(
		self,
		max: Optional[int] = None,
		setups: Optional[Union[PoolSetup, Sequence[PoolSetup]]] = None,
		cleanups: Optional[Union[PoolCleanup, Sequence[PoolCleanup]]] = None,
	):
		size = pool_size(max)
		super().__init__(
			Executor(
				size,
				pool_hooks(setups),
				pool_hooks(cleanups),
				process=True,
			),
			size,
		)
