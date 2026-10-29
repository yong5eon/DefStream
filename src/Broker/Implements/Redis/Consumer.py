from collections import deque
from logging import getLogger
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

from DefStream.Broker import (
	Consumer as BaseConsumer,
	Event as BaseEvent,
	EventError,
	EventHandler,
	Requeue,
)
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
	logger = getLogger('Broker.Redis.Consumer')

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
		self.logger.debug(
			'Consumer created: consumer=%s qos=%s reclaim_idle=%sms',
			self.name,
			self.qos,
			self.reclaim_idle,
		)

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
		self.logger.debug(
			'Preparing Consumer subscription: queue=%s group=%s consumer=%s',
			subscription.queue,
			subscription.group,
			self.name,
		)
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
		self.logger.info(
			'Consumer subscribed: queue=%s group=%s consumer=%s qos=%s reclaim_idle=%sms',
			subscription.queue,
			subscription.group,
			self.name,
			self.qos,
			self.reclaim_idle,
		)

	def call(
		self,
		callback: Callable[[], None],
	) -> None:
		if self.closed:
			raise RuntimeError('Redis consumer is closed')
		self.callbacks.put(callback)
		self.wakeup.set()
		self.logger.debug(
			'Consumer callback scheduled: consumer=%s',
			self.name,
		)

	def fail(
		self,
		event: BaseEvent,
		policy: Optional[EventError] = None,
	) -> None:
		self.logger.debug(
			'Applying message failure policy: consumer=%s policy=%s',
			self.name,
			type(policy).__name__ if policy is not None else 'Requeue',
		)
		(policy if policy is not None else Requeue())(event)

	def drain(self) -> None:
		while True:
			try:
				callback = self.callbacks.get_nowait()
			except Empty:
				break
			self.logger.debug(
				'Executing Consumer callback: consumer=%s',
				self.name,
			)
			try:
				callback()
			except Exception as error:
				self.logger.error(
					'Consumer callback failed: consumer=%s error_type=%s',
					self.name,
					type(error).__name__,
				)
				raise
		pending_count = len(self.pending)
		self.pending = {
			key: event
			for key, event in self.pending.items()
			if not event.settled
		}
		settled_count = pending_count - len(self.pending)
		if settled_count:
			self.logger.debug(
				'Settled Events removed: consumer=%s removed=%s pending=%s',
				self.name,
				settled_count,
				len(self.pending),
			)

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
				self.logger.debug(
					'Skipping delivery of already pending message: queue=%s group=%s id=%s',
					stream.queue,
					stream.group,
					key[1],
				)
				continue
			event = stream.event(
				id,
				fields,
				stream.group,
				self.name,
			)
			self.pending[key] = event
			self.logger.debug(
				'Delivering message: queue=%s group=%s consumer=%s id=%s pending=%s',
				stream.queue,
				stream.group,
				self.name,
				event.id,
				len(self.pending),
			)
			try:
				handler(event)
			except Exception as error:
				self.logger.error(
					'Message handler dispatch failed: queue=%s group=%s consumer=%s id=%s error_type=%s',
					stream.queue,
					stream.group,
					self.name,
					event.id,
					type(error).__name__,
				)
				raise
			self.drain()

	def run(self) -> None:
		if self.closed:
			raise RuntimeError('Redis consumer is closed')
		if not self.subscriptions:
			raise RuntimeError('Subscribe before running the Redis consumer')
		self.logger.info(
			'Starting Consumer consumption loop: consumer=%s subscriptions=%s qos=%s reclaim_idle=%sms',
			self.name,
			len(self.subscriptions),
			self.qos,
			self.reclaim_idle,
		)
		qos_limited = False
		while not self.stopped:
			self.wakeup.clear()
			self.drain()
			for _ in range(len(self.rotation)):
				available = self.qos - len(self.pending)
				if available <= 0:
					if not qos_limited:
						self.logger.debug(
							'Deferring reads at QoS limit: consumer=%s qos=%s pending=%s',
							self.name,
							self.qos,
							len(self.pending),
						)
					qos_limited = True
					break
				qos_limited = False
				if self.stopped:
					break
				name = self.rotation.popleft()
				self.rotation.append(name)
				stream, handler = self.subscriptions[name]
				if self.reclaim_idle is not None:
					old_cursor = self.cursors[stream.queue]
					try:
						claimed = self.connection.xautoclaim(
							stream.queue,
							stream.group,
							self.name,
							self.reclaim_idle,
							start_id=old_cursor,
							count=available,
						)
					except Exception as error:
						self.logger.error(
							'Pending message reclaim failed: queue=%s group=%s consumer=%s error_type=%s',
							stream.queue,
							stream.group,
							self.name,
							type(error).__name__,
						)
						raise
					self.cursors[stream.queue] = claimed[0].decode('ascii')
					if claimed[1] or self.cursors[stream.queue] != old_cursor:
						self.logger.debug(
							'Pending message reclaim result: queue=%s group=%s consumer=%s count=%s cursor=%s',
							stream.queue,
							stream.group,
							self.name,
							len(claimed[1]),
							self.cursors[stream.queue],
						)
					self.deliver(
						stream,
						handler,
						claimed[1],
					)
				available = self.qos - len(self.pending)
				if available <= 0:
					if not qos_limited:
						self.logger.debug(
							'Deferring reads at QoS limit: consumer=%s qos=%s pending=%s',
							self.name,
							self.qos,
							len(self.pending),
						)
					qos_limited = True
					continue
				qos_limited = False
				if self.stopped:
					continue
				try:
					messages = self.connection.xreadgroup(
						stream.group,
						self.name,
						{stream.queue: '>'},
						count=available,
					)
				except Exception as error:
					self.logger.error(
						'New message read failed: queue=%s group=%s consumer=%s error_type=%s',
						stream.queue,
						stream.group,
						self.name,
						type(error).__name__,
					)
					raise
				for _, entries in messages:
					self.deliver(
						stream,
						handler,
						entries,
					)
			self.wakeup.wait(0.05)
		self.logger.info(
			'Consumer consumption loop ended: consumer=%s pending=%s',
			self.name,
			len(self.pending),
		)

	def stop(self) -> None:
		if not self.stopped:
			self.logger.info(
				'Consumer stop requested: consumer=%s pending=%s',
				self.name,
				len(self.pending),
			)
		self.stopped = True
		self.wakeup.set()

	def close(self) -> None:
		if not self.closed:
			self.logger.info(
				'Consumer closed: consumer=%s pending=%s',
				self.name,
				len(self.pending),
			)
		self.stop()
		self.closed = True
