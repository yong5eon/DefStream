from abc import (
	ABC,
	abstractmethod,
)
from collections.abc import Mapping
from inspect import isabstract
from logging import getLogger
from threading import Event as PyEvent
from typing import (
	Any,
	List,
	Callable,
	Optional,
	Sequence,
	Type,
	Tuple,
	Union,
	Protocol,
)

from ..Broker import (
	Connection,
	GetConsumer,
	Consumer,
	EventHandler,
)
from ..Broker.Event import Event
from .Pool import (
	Pool,
	PoolFull,
)
from .Run import Run
from .Executor import run_cleanups

__all__ = (
	'Worker',
	'WorkerConnection',
	'WorkerSetup',
	'WorkerCleanup',
)

logger = getLogger(__name__)


class WorkerConnection(
	Connection,
	GetConsumer,
	Protocol,
):
	pass


class WorkerSetup(ABC):
	@abstractmethod
	def __call__(
		self,
		worker: 'Worker',
	) -> None:
		raise NotImplementedError


class WorkerCleanup(ABC):
	@abstractmethod
	def __call__(
		self,
		worker: 'Worker',
	) -> None:
		raise NotImplementedError


def worker_hooks(
	hooks: Optional[Union[Callable[['Worker'], None], Sequence[Callable[['Worker'], None]]]],
) -> Tuple[Callable[['Worker'], None], ...]:
	result = () if hooks is None else tuple(hooks) if isinstance(
		hooks,
		Sequence,
	) else (hooks,)
	if not all(callable(hook) for hook in result):
		raise TypeError('Worker hooks must be callable')
	return result


class Worker:
	def __init__(
		self,
		broker: WorkerConnection,
		pool: Pool,
		setups: Optional[Union[WorkerSetup, Sequence[WorkerSetup]]] = None,
		cleanups: Optional[Union[WorkerCleanup, Sequence[WorkerCleanup]]] = None,
	):
		self.broker = broker
		self.pool = pool
		self.runs: List[Type[Run]] = []
		self.consumer: Optional[Consumer] = None
		self.started = False
		self.stopping = PyEvent()
		self.finished = PyEvent()
		self.pending = 0
		self.setups = worker_hooks(setups)
		self.cleanups = worker_hooks(cleanups)

	def add(
		self,
		run: Type[Run],
	) -> None:
		if self.started:
			raise RuntimeError('Cannot register runs after starting the worker')
		if not isinstance(
			run,
			type,
		) or not issubclass(
			run,
			Run,
		) or isabstract(run):
			raise TypeError('A concrete Run class is required')
		if run.parameters is None:
			raise ValueError('Run subscription parameters are required')
		if run in self.runs:
			raise ValueError('Run is already registered')
		self.runs.append(run)

	def run(self) -> None:
		if self.started:
			raise RuntimeError('Worker can only be started once')
		if not self.runs:
			raise RuntimeError('Register at least one Run before starting')
		self.started = True
		try:
			self.broker.connect()
			for setup in self.setups:
				setup(self)
			self.consumer = self.broker.consumer()
			for run in self.runs:
				self.consumer.subs(
					run.parameters,
					Handler(
						self,
						run,
					),
				)
			if not self.stopping.is_set():
				self.consumer.run()
		finally:
			self.finished.set()
			if self.pending:
				logger.error(
					'Consumer exited with %s unconfirmed deliveries',
					self.pending,
				)
			try:
				self.pool.stop()
			finally:
				try:
					self.cleanup()
				finally:
					try:
						if self.consumer is not None:
							self.consumer.close()
					finally:
						self.broker.close()

	def cleanup(self) -> None:
		run_cleanups(
			self.cleanups,
			self,
		)

	def stop(self) -> None:
		self.stopping.set()
		if self.consumer is not None and not self.finished.is_set():
			self.consumer.call(self.try_stop)

	def try_stop(self) -> None:
		if self.stopping.is_set() and self.pending == 0 and self.consumer is not None:
			self.consumer.stop()

	def receive(
		self,
		run: Type[Run],
		event: Event,
	) -> None:
		if self.stopping.is_set():
			event.nack()
			return
		if not isinstance(
			event.body,
			Mapping,
		):
			self.failed(
				run,
				event,
				TypeError('Run message body must be a mapping'),
			)
			return
		self.pending += 1
		consumer = self.consumer
		if consumer is None:
			self.pending -= 1
			raise RuntimeError('Worker consumer is not initialized')

		def schedule(
			error: Optional[BaseException] = None,
			result: Any = None,
		) -> None:
			if self.finished.is_set():
				logger.error(
					'Consumer exited before Run %s delivery could be confirmed',
					run.__name__,
				)
				return
			consumer.call(lambda: self.complete(
				run,
				event,
				error,
				result,
			))

		try:
			self.pool.submit(
				run,
				dict(event.body),
				callback=lambda result: schedule(result=result),
				error_callback=schedule,
			)
		except PoolFull:
			self.pending -= 1
			event.nack()
			return
		except Exception:
			self.pending -= 1
			raise

	def complete(
		self,
		run: Type[Run],
		event: Event,
		error: Optional[BaseException] = None,
		result: Any = None,
	) -> None:
		try:
			if error is not None:
				self.failed(
					run,
					event,
					error,
				)
			else:
				if self.consumer is None:
					raise RuntimeError('Worker consumer is not initialized')
				self.consumer.complete(
					event,
					result,
				)
		finally:
			self.pending -= 1
			self.try_stop()

	def failed(
		self,
		run: Type[Run],
		event: Event,
		error: BaseException,
	) -> None:
		logger.error(
			'Run %s failed',
			run.__name__,
			exc_info=(
				type(error),
				error,
				error.__traceback__,
			),
		)
		if self.consumer is None:
			raise RuntimeError('Worker consumer is not initialized')
		self.consumer.fail(
			event,
			run.on_error,
		)


class Handler(EventHandler):
	def __init__(
		self,
		worker: Worker,
		run: Type[Run],
	):
		self.worker = worker
		self.run = run

	def __call__(
		self,
		event: Event,
	) -> None:
		self.worker.receive(
			self.run,
			event,
		)
