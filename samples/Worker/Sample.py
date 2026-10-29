from queue import Queue as PyQueue
from logging import (
	DEBUG,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
)
from typing import (
	Any,
	Callable,
	Dict,
	Optional,
)

from DefStream.Broker import (
	Connection as BaseConnection,
	GetQueue,
	GetConsumer,
	Sendable,
	Consumer as BaseConsumer,
	Event as BaseEvent,
)
from DefStream.Broker.Event import EventHandler
from DefStream.Broker.Event import EventErrorPolicy
from DefStream.Worker import (
	Run,
	ThreadPool,
	Worker,
	WorkerCleanup,
	WorkerSetup,
)


logger = getLogger('Sample')



class Queue(Sendable):
	def __init__(self):
		self.messages: PyQueue[Dict[str, Any]] = PyQueue()

	def send(
		self,
		body: Dict[str, Any],
	) -> None:
		self.messages.put(body)


class Broker(
	BaseConnection,
	GetQueue,
	GetConsumer,
):
	def __init__(self):
		self.connected = False
		self.queues: Dict[str, Queue] = {}

	def connect(self) -> None:
		self.connected = True

	def close(self) -> None:
		self.connected = False

	def queue(
		self,
		name: str,
		**kwargs: Any,
	) -> Queue:
		if not self.connected:
			raise RuntimeError('Broker is not connected')
		if name not in self.queues:
			self.queues[name] = Queue()
		return self.queues[name]

	def consumer(
		self,
		handler: Optional[EventHandler] = None,
		**kwargs: Any,
	) -> 'Consumer':
		if not self.connected:
			raise RuntimeError('Broker is not connected')
		return Consumer(
			self,
			handler,
		)

class Event(BaseEvent):
	def __init__(
		self,
		consumer: 'Consumer',
		queue: Queue,
		body: Dict[str, Any],
	):
		self.consumer = consumer
		self.queue = queue
		self.payload = body

	@property
	def body(self) -> Dict[str, Any]:
		return self.payload

	def ack(self) -> None:
		self.consumer.pending -= 1

	def nack(self) -> None:
		self.queue.messages.put(self.body)
		self.consumer.pending -= 1

	def reject(self) -> None:
		logger.info('Sample message rejected')
		self.consumer.pending -= 1


class Consumer(BaseConsumer):
	def __init__(
		self,
		broker: Broker,
		handler: Optional[EventHandler] = None,
	):
		self.broker = broker
		self.handler = handler
		self.handlers: Dict[str, EventHandler] = {}
		self.callbacks: PyQueue[Callable[[], None]] = PyQueue()
		self.pending = 0
		self.running = False

	def subs(
		self,
		queue: Any,
		handler: Optional[EventHandler] = None,
	) -> None:
		name = queue if isinstance(
			queue,
			str,
		) else queue['queue']
		selected = handler if handler is not None else self.handler
		if selected is None:
			raise ValueError('A subscription handler is required')
		if name in self.handlers:
			raise ValueError('Queue is already subscribed')
		self.broker.queue(name)
		self.handlers[name] = selected

	def call(
		self,
		callback: Callable[[], None],
	) -> None:
		self.callbacks.put(callback)

	def fail(
		self,
		event: BaseEvent,
		policy: Optional[EventErrorPolicy] = None,
	) -> None:
		if policy is None:
			event.reject()
		else:
			policy(event)

	def run(self) -> None:
		self.running = True
		while self.running:
			if self.pending:
				self.callbacks.get()()
				continue
			if not self.callbacks.empty():
				self.callbacks.get_nowait()()
				continue
			for name, handler in self.handlers.items():
				queue = self.broker.queues[name]
				if not queue.messages.empty():
					self.pending += 1
					handler(Event(
						self,
						queue,
						queue.messages.get_nowait(),
					))
					break
			else:
				self.stop()

	def stop(self) -> None:
		self.running = False

	def close(self) -> None:
		self.stop()


class Add(
	Run,
	parameters={
		'queue': 'add',
	},
):
	def run(
		self,
		a: int,
		b: int,
	) -> None:
		logger.info(
			'%s + %s = %s',
			a,
			b,
			a + b,
		)


class SetupLogger(WorkerSetup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		handler = StreamHandler()
		handler.setFormatter(Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
		sources = (
			Filter('Sample'),
			Filter('Worker'),
			Filter('Task'),
		)
		handler.addFilter(lambda record: any(source.filter(record) for source in sources))
		root = getLogger()
		root.setLevel(DEBUG)
		root.addHandler(handler)
		return


class Prepare(WorkerSetup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		broker = worker.broker
		if not isinstance(
			broker,
			Broker,
		):
			raise TypeError('The sample in-memory broker is required')
		for run in worker.tasks:
			broker.queue(run.parameters['queue'])
		queue = broker.queue('add')
		queue.send({
			'a': 1,
			'b': 2,
		})
		queue.send({
			'a': 3,
			'b': 4,
		})


class Cleanup(WorkerCleanup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		logger.info('Worker cleanup')


if __name__ == '__main__':
	worker = Worker(
		Broker(),
		ThreadPool(1),
		setups=(
			SetupLogger(),
			Prepare(),
		),
		cleanups=(
			Cleanup(),
		),
	)
	worker.add(Add)
	worker.run()
