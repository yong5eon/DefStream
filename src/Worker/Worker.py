from abc import (
	ABC,
	abstractmethod,
)
from collections.abc import Mapping
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
)

from ..Broker import (
	Connection,
	GetConsumer,
	Consumer,
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
	):
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
			if not self.stopping.is_set():
				self.running.set()
				self.logger.info('Worker ready to consume')
				self.consumer.run()
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
		if self.consumer is not None and not self.finished.is_set():
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

		def schedule(
			error: Optional[BaseException] = None,
			result: Any = None,
		) -> None:
			if inspector is not None:
				inspector.end(
					task,
					contexts,
					error is None,
				)
			if self.finished.is_set():
				self.logger.error(
					'Cannot confirm delivery after Consumer exit: task=%s',
					task,
				)
				return
			self.logger.debug(
				'Scheduling task result callback: task=%s success=%s',
				task,
				error is None,
			)
			consumer.call(lambda: self.complete(
				run,
				event,
				error,
				result,
			))

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
