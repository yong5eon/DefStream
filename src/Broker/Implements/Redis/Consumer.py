from collections import deque
from queue import (
	Empty,
	SimpleQueue,
)
from threading import Event as Wakeup
from typing import (
	Any,
	Callable,
	Dict,
	Optional,
	Tuple,
	Union,
)
from uuid import uuid4

from redis import Redis
from redis.cluster import RedisCluster

from ...Consumer import Consumer as BaseConsumer
from ...Event import (
	Event as BaseEvent,
	EventError,
	EventHandler,
)
from ...Policies import Requeue
from .Event import Event
from .Queue import Queue
from .Serializer import (
	Decoder,
	Encoder,
)
from .Subscription import Subscription

__all__ = (
	'Consumer',
)


class Consumer(BaseConsumer):
	def __init__(
		self,
		connection: Union[Redis, RedisCluster],
		encode: Encoder,
		decode: Decoder,
		handler: Optional[EventHandler] = None,
		qos: int = 1,
		reclaim_idle: Optional[int] = 60000,
	):
		if isinstance(
			qos,
			bool,
		) or not isinstance(
			qos,
			int,
		) or qos < 1:
			raise ValueError('Redis qos must be a positive integer')
		if reclaim_idle is not None and reclaim_idle < 1:
			raise ValueError('Redis reclaim_idle must be positive milliseconds or None')
		self.connection = connection
		self.encode = encode
		self.decode = decode
		self.handler = handler
		self.qos = qos
		self.reclaim_idle = reclaim_idle
		self.name = uuid4().hex
		self.subscriptions: Dict[str, Tuple[Queue, EventHandler]] = {}
		self.rotation = deque()
		self.pending: Dict[Tuple[str, str], Event] = {}
		self.cursors: Dict[str, str] = {}
		self.callbacks: SimpleQueue[Callable[[], None]] = SimpleQueue()
		self.wakeup = Wakeup()
		self.stopped = False
		self.closed = False

	def subs(
		self,
		queue: Any,
		handler: Optional[EventHandler] = None,
	) -> None:
		if self.closed:
			raise RuntimeError('Redis consumer is closed')
		subscription = Subscription.parse(queue)
		handler = handler if handler is not None else self.handler
		if handler is None:
			raise ValueError('subs requires a handler or a default handler')
		if subscription.queue in self.subscriptions:
			raise ValueError('A Run is already subscribed to queue {}'.format(subscription.queue))
		stream = Queue(
			self.connection,
			self.encode,
			self.decode,
			subscription.queue,
			subscription.group,
		)
		stream.create_group()
		self.subscriptions[subscription.queue] = (
			stream,
			handler,
		)
		self.cursors[subscription.queue] = '0-0'
		self.rotation.append(subscription.queue)

	def call(
		self,
		callback: Callable[[], None],
	) -> None:
		if self.closed:
			raise RuntimeError('Redis consumer is closed')
		self.callbacks.put(callback)
		self.wakeup.set()

	def fail(
		self,
		event: BaseEvent,
		policy: Optional[EventError] = None,
	) -> None:
		(policy if policy is not None else Requeue())(event)

	def drain(self) -> None:
		while True:
			try:
				callback = self.callbacks.get_nowait()
			except Empty:
				break
			callback()
		self.pending = {
			key: event
			for key, event in self.pending.items()
			if not event.settled
		}

	def deliver(
		self,
		stream: Queue,
		handler: EventHandler,
		entries: list,
	) -> None:
		for id, fields in entries:
			key = (
				stream.queue,
				id.decode('ascii'),
			)
			if key in self.pending:
				continue
			event = stream.event(
				id,
				fields,
				stream.group,
				self.name,
			)
			self.pending[key] = event
			handler(event)
			self.drain()

	def run(self) -> None:
		if self.closed:
			raise RuntimeError('Redis consumer is closed')
		if not self.subscriptions:
			raise RuntimeError('Subscribe before running the Redis consumer')
		while not self.stopped:
			self.wakeup.clear()
			self.drain()
			for _ in range(len(self.rotation)):
				available = self.qos - len(self.pending)
				if self.stopped or available <= 0:
					break
				name = self.rotation.popleft()
				self.rotation.append(name)
				stream, handler = self.subscriptions[name]
				if self.reclaim_idle is not None:
					claimed = self.connection.xautoclaim(
						stream.queue,
						stream.group,
						self.name,
						self.reclaim_idle,
						start_id=self.cursors[stream.queue],
						count=available,
					)
					self.cursors[stream.queue] = claimed[0].decode('ascii')
					self.deliver(
						stream,
						handler,
						claimed[1],
					)
				available = self.qos - len(self.pending)
				if self.stopped or available <= 0:
					continue
				messages = self.connection.xreadgroup(
					stream.group,
					self.name,
					{stream.queue: '>'},
					count=available,
				)
				for _, entries in messages:
					self.deliver(
						stream,
						handler,
						entries,
					)
			self.wakeup.wait(0.05)

	def stop(self) -> None:
		self.stopped = True
		self.wakeup.set()

	def close(self) -> None:
		self.stop()
		self.closed = True
