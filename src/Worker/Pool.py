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
		future.add_done_callback(lambda completed: self.complete(
			completed,
			callback,
			error_callback,
		))
		return future

	def complete(
		self,
		future: Future,
		callback: Optional[Callable[[Any], None]] = None,
		error_callback: Optional[Callable[[BaseException], None]] = None,
	) -> None:
		with self.lock:
			self.futures.remove(future)
			self.slots.release()
		try:
			result = future.result()
		except BaseException as error:
			if error_callback is not None:
				error_callback(error)
		else:
			if callback is not None:
				callback(result)

	def waits(
		self,
		timeout: Optional[float] = None,
	) -> None:
		with self.lock:
			tasks = tuple(self.futures)
		if tasks and wait(
			tasks,
			timeout=timeout,
		).not_done:
			raise TimeoutError('Pool tasks did not complete in time')

	def stop(self) -> None:
		with self.lock:
			self.closed = True
		self.pool.shutdown(wait=True)

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
