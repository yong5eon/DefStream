from abc import (
	ABC,
	abstractmethod,
)
from collections.abc import Mapping
from logging import getLogger
from math import isfinite
from threading import (
	Event as PyEvent,
	RLock,
)
from typing import (
	Any,
	List,
	Callable,
	Optional,
	Sequence,
	Type,
	Tuple,
	Union,
	Dict,
)

from ..Broker import (
	Connection,
	GetConsumer,
	Consumer,
	Recoverable,
	EventHandler,
)
from ..Broker.Event import Event
from .Message import task_parameters
from ..Inspector import Inspector
from .Pool import (
	Pool,
	PoolFull,
)
from .Run import Run
from .Executor import run_cleanups
from .Startup import startup

__all__ = (
	'Worker',
	'WorkerSetup',
	'WorkerCleanup',
)

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
	logger = getLogger('Worker')

	def __init__(
		self,
		broker: Connection,
		pool: Pool,
		setups: Optional[Union[WorkerSetup, Sequence[WorkerSetup]]] = None,
		cleanups: Optional[Union[WorkerCleanup, Sequence[WorkerCleanup]]] = None,
		inspector: Optional[Inspector] = None,
		*,
		recovery_attempts: int = 5,
		recovery_interval: float = 60,
	) -> None:
		if isinstance(
			recovery_attempts,
			bool,
		) or not isinstance(
			recovery_attempts,
			int,
		):
			raise TypeError('Recovery attempts must be an integer')
		if recovery_attempts < 0:
			raise ValueError('Recovery attempts must not be negative')
		if isinstance(
			recovery_interval,
			bool,
		) or not isinstance(
			recovery_interval,
			(
				int,
				float,
			),
		):
			raise TypeError('Recovery interval must be a number of seconds')
		if not isfinite(recovery_interval) or recovery_interval < 0:
			raise ValueError('Recovery interval must be finite and non-negative')
		self.broker = broker
		self.pool = pool
		self.tasks: List[Type[Run]] = []
		self.consumer: Optional[Consumer] = None
		self.started = False
		self.running = PyEvent()
		self.stopping = PyEvent()
		self.finished = PyEvent()
		self.pending = 0
		self.setups = worker_hooks(setups)
		self.cleanups = worker_hooks(cleanups)
		self.inspector = inspector
		self.recovery_attempts = recovery_attempts
		self.recovery_interval = recovery_interval
		self.generation = 0
		self.delivery_lock = RLock()
		self.deliveries: Dict[object, Callable[[], None]] = {}
		self.consumption_failed = False

	def add(
		self,
		run: Type[Run],
	) -> None:
		if self.started:
			raise RuntimeError('Cannot register runs after starting the worker')
		task_parameters(run)
		if run in self.tasks:
			raise ValueError('Run is already registered')
		if any(
			registered.name == run.name
			for registered in self.tasks
		):
			raise ValueError('Duplicate Run name: ' + run.name)
		self.tasks.append(run)
		self.logger.debug(
			'Task registered: task=%s.%s',
			run.__module__,
			run.__qualname__,
		)

	def run(self) -> None:
		if self.started:
			raise RuntimeError('Worker can only be started once')
		if not self.tasks:
			raise RuntimeError('Register at least one Run before starting')
		self.started = True
		self.logger.info(
			'Starting Worker: tasks=%s',
			len(self.tasks),
		)
		try:
			startup(self)
			if self.inspector is not None:
				self.inspector.start(self)
			self.logger.debug('Connecting to broker')
			self.broker.connect()
			self.logger.debug('Broker connected')
			for setup in self.setups:
				self.logger.debug(
					'Starting Worker setup: hook=%s',
					type(setup).__qualname__,
				)
				setup(self)
				self.logger.debug(
					'Worker setup completed: hook=%s',
					type(setup).__qualname__,
				)
			if not isinstance(self.broker, GetConsumer):
				raise TypeError('Worker broker must support consumer creation')
			self.subscribe()
			if not self.stopping.is_set():
				self.consume()
		finally:
			self.running.clear()
			self.finished.set()
			if self.pending:
				self.logger.error(
					'Consumer exited with unconfirmed deliveries: pending=%s',
					self.pending,
				)
			try:
				self.logger.info(
					'Draining Worker tasks: pending=%s',
					self.pending,
				)
				if self.consumption_failed:
					self.pool.stop(abort=True)
				else:
					self.pool.stop()
			finally:
				try:
					self.cleanup()
				finally:
					try:
						if self.consumer is not None:
							self.consumer.close()
					finally:
						try:
							self.broker.close()
						finally:
							if self.inspector is not None and self.inspector.worker is self:
								self.inspector.stop()
			self.logger.info('Worker shutdown completed')

	def subscribe(self) -> None:
		if not isinstance(self.broker, GetConsumer):
			raise TypeError('Worker broker must support consumer creation')
		self.consumer = self.broker.consumer()
		self.logger.debug('Consumer created')
		for run in self.tasks:
			self.logger.debug(
				'Subscribing task: task=%s.%s',
				run.__module__,
				run.__qualname__,
			)
			self.consumer.subs(
				run.parameters,
				Handler(
					self,
					run,
				),
			)
			self.logger.debug(
				'Task subscribed: task=%s.%s',
				run.__module__,
				run.__qualname__,
			)
		return

	def discard_deliveries(self) -> None:
		"""Retire outstanding Inspector contexts before replacing an execution generation."""
		with self.delivery_lock:
			self.generation += 1
			for discard in self.deliveries.values():
				discard()
			self.deliveries.clear()
			self.pending = 0
		return

	def consume(self) -> None:
		while not self.stopping.is_set():
			consumer = self.consumer
			if consumer is None:
				raise RuntimeError('Worker consumer is not initialized')
			self.running.set()
			self.logger.info('Worker ready to consume')
			try:
				consumer.run()
				return
			except Exception as error:
				self.running.clear()
				if not isinstance(consumer, Recoverable):
					raise
				self.consumption_failed = True
				self.discard_deliveries()
				if not consumer.is_recoverable(error):
					raise
				if self.stopping.is_set():
					return
				self.recover(error, consumer)
				self.consumption_failed = False
		return

	def recover(self, error: Exception, previous: Recoverable) -> None:
		self.logger.warning(
			'Recovering Worker after consumption failure: error_type=%s attempts=%s',
			type(error).__name__,
			self.recovery_attempts,
		)
		if self.recovery_attempts == 0:
			raise error
		self.pool.restart()
		for attempt in range(self.recovery_attempts):
			if attempt and self.stopping.wait(self.recovery_interval):
				return
			if self.stopping.is_set():
				return
			try:
				if self.consumer is not None:
					self.consumer.close()
				self.broker.close()
				self.broker.connect()
				self.subscribe()
			except Exception as failure:
				self.logger.error(
					'Worker recovery attempt failed: attempt=%s error_type=%s',
					attempt + 1,
					type(failure).__name__,
				)
				if not previous.is_recoverable(failure) or attempt + 1 == self.recovery_attempts:
					raise
			else:
				self.logger.info('Worker recovery completed: attempt=%s', attempt + 1)
				return
		return

	def cleanup(self) -> None:
		self.logger.debug(
			'Starting Worker cleanup: hooks=%s',
			len(self.cleanups),
		)
		run_cleanups(
			self.cleanups,
			self,
		)
		self.logger.debug('Worker cleanup completed')

	def stop(self) -> None:
		if not self.stopping.is_set():
			self.logger.info(
				'Worker shutdown requested: pending=%s',
				self.pending,
			)
		self.stopping.set()
		if self.consumer is not None and self.running.is_set() and not self.finished.is_set():
			self.consumer.call(self.try_stop)

	def try_stop(self) -> None:
		if self.stopping.is_set() and self.pending == 0 and self.consumer is not None:
			self.logger.debug('No pending tasks; requesting Consumer stop')
			self.consumer.stop()

	def receive(
		self,
		run: Type[Run],
		event: Event,
	) -> None:
		if self.stopping.is_set():
			self.logger.debug(
				'Requeuing message received during shutdown: task=%s.%s',
				run.__module__,
				run.__qualname__,
			)
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
		inspector = self.inspector
		task = run.name
		self.logger.debug(
			'Task message received: task=%s pending=%s',
			task,
			self.pending,
		)
		contexts = inspector.begin(task) if inspector is not None else ()
		generation = self.generation
		delivery = object()
		with self.delivery_lock:
			self.deliveries[delivery] = lambda: inspector.end(
				task,
				contexts,
				None,
			) if inspector is not None else None

		def dispatch(
			error: Optional[BaseException],
			result: Any,
		) -> None:
			with self.delivery_lock:
				if generation != self.generation or self.finished.is_set():
					self.logger.warning('Discarding stale task result: task=%s', task)
					return
				self.complete(
					run,
					event,
					error,
					result,
				)
			return

		def schedule(
			error: Optional[BaseException] = None,
			result: Any = None,
		) -> None:
			with self.delivery_lock:
				if generation != self.generation:
					self.logger.warning('Discarding stale task result: task=%s', task)
					return
				self.deliveries.pop(delivery, None)
				if inspector is not None:
					inspector.end(
						task,
						contexts,
						error is None,
					)
				if self.finished.is_set():
					self.logger.error('Cannot confirm delivery after Consumer exit: task=%s', task)
					return
				consumer.call(lambda: dispatch(error, result))
			return

		try:
			self.logger.debug(
				'Submitting task to Pool: task=%s',
				task,
			)
			self.pool.submit(
				run,
				dict(event.body),
				callback=lambda result: schedule(result=result),
				error_callback=schedule,
			)
			self.logger.debug(
				'Pool task submission accepted: task=%s',
				task,
			)
		except PoolFull:
			self.deliveries.pop(delivery, None)
			self.logger.debug(
				'Requeuing message because Pool is full: task=%s',
				task,
			)
			if inspector is not None:
				inspector.end(
					task,
					contexts,
					None,
				)
			self.pending -= 1
			event.nack()
			return
		except Exception:
			self.deliveries.pop(delivery, None)
			if inspector is not None:
				inspector.end(
					task,
					contexts,
					None,
				)
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
				self.logger.debug(
					'Consumer completion returned: task=%s.%s',
					run.__module__,
					run.__qualname__,
				)
		finally:
			self.pending -= 1
			self.logger.debug(
				'Task completion handling finished: pending=%s',
				self.pending,
			)
			self.try_stop()

	def failed(
		self,
		run: Type[Run],
		event: Event,
		error: BaseException,
	) -> None:
		if isinstance(
			error,
			TypeError,
		) and not isinstance(
			event.body,
			Mapping,
		):
			self.logger.warning(
				'Rejected a non-mapping task message: task=%s.%s',
				run.__module__,
				run.__qualname__,
			)
		else:
			self.logger.error(
				'Task failed: task=%s.%s',
				run.__module__,
				run.__qualname__,
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
		self.logger.debug(
			'Consumer failure policy returned: task=%s.%s',
			run.__module__,
			run.__qualname__,
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
