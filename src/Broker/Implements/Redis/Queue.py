from logging import getLogger
from time import (
	monotonic,
	sleep,
)
from typing import (
	Any,
	Iterable,
	Optional,
	Union,
)
from uuid import uuid4

from redis import Redis
from redis.cluster import RedisCluster
from redis.exceptions import ResponseError

from DefStream.Broker import (
	Poppable,
	Readable,
	Sendable,
)
from .Event import Event
from .Serializer import (
	Decoder,
	Encoder,
)
from .Subscription import Subscription

__all__ = (
	'Queue',
)


class Queue(
	Sendable,
	Poppable,
	Readable,
):
	logger = getLogger('Broker.Redis.Queue')

	def __init__(
		self,
		connection: Union[Redis, RedisCluster],
		encode: Encoder,
		decode: Decoder,
		name: str,
		group: str = 'DefStream',
	):
		self.subscription = Subscription(
			name,
			group,
		)
		self.connection = connection
		self.encode = encode
		self.decode = decode
		self.queue = name
		self.group = group
		self.consumer = uuid4().hex

	def __str__(self) -> str:
		return self.queue

	def create_group(self) -> None:
		self.logger.debug(
			'Creating Consumer Group: queue=%s group=%s',
			self.queue,
			self.group,
		)
		try:
			self.connection.xgroup_create(
				self.queue,
				self.group,
				id='0-0',
				mkstream=True,
			)
		except ResponseError as error:
			if not str(error).startswith('BUSYGROUP '):
				self.logger.error(
					'Consumer Group creation failed: queue=%s group=%s error_type=%s',
					self.queue,
					self.group,
					type(error).__name__,
				)
				raise
			self.logger.debug(
				'Reusing existing Consumer Group: queue=%s group=%s',
				self.queue,
				self.group,
			)
			return
		except Exception as error:
			self.logger.error(
				'Consumer Group creation failed: queue=%s group=%s error_type=%s',
				self.queue,
				self.group,
				type(error).__name__,
			)
			raise
		self.logger.info(
			'Consumer Group creation completed: queue=%s group=%s',
			self.queue,
			self.group,
		)

	def send(
		self,
		body: Any,
	) -> str:
		self.logger.debug(
			'Publishing Redis Stream message: queue=%s',
			self.queue,
		)
		try:
			id = self.connection.xadd(
				self.queue,
				{'body': self.encode(body)},
			)
			message_id = id.decode('ascii')
		except Exception as error:
			self.logger.error(
				'Redis Stream publication or serialization failed: queue=%s error_type=%s',
				self.queue,
				type(error).__name__,
			)
			raise
		self.logger.debug(
			'Redis Stream message published: queue=%s id=%s',
			self.queue,
			message_id,
		)
		return message_id

	def event(
		self,
		id: bytes,
		fields: dict,
		group: Optional[str] = None,
		consumer: Optional[str] = None,
	) -> Event:
		try:
			message_id = id.decode('ascii')
			body = self.decode(fields[b'body'])
		except Exception as error:
			self.logger.error(
				'Redis message deserialization or Event conversion failed: queue=%s group=%s id=%s error_type=%s',
				self.queue,
				group,
				id,
				type(error).__name__,
			)
			raise
		self.logger.debug(
			'Converting message to Event: queue=%s group=%s consumer=%s id=%s',
			self.queue,
			group,
			consumer,
			message_id,
		)
		return Event(
			self.connection,
			self.queue,
			message_id,
			body,
			group,
			consumer,
		)

	def pop(
		self,
		timeout: Optional[int] = None,
	) -> Optional[Event]:
		if timeout is not None and timeout < 0:
			raise ValueError('Redis pop timeout must be non-negative milliseconds')
		self.logger.debug(
			'Starting group-based single-message reception: queue=%s group=%s consumer=%s timeout=%sms',
			self.queue,
			self.group,
			self.consumer,
			timeout,
		)
		self.create_group()
		deadline = monotonic() + timeout / 1000 if timeout else None
		while True:
			try:
				messages = self.connection.xreadgroup(
					self.group,
					self.consumer,
					{self.queue: '>'},
					count=1,
				)
			except Exception as error:
				self.logger.error(
					'Group-based single-message reception failed: queue=%s group=%s error_type=%s',
					self.queue,
					self.group,
					type(error).__name__,
				)
				raise
			for _, entries in messages:
				for id, fields in entries:
					event = self.event(
						id,
						fields,
						self.group,
						self.consumer,
					)
					self.logger.debug(
						'Group message received: queue=%s group=%s id=%s',
						self.queue,
						self.group,
						event.id,
					)
					return event
			if deadline is not None and monotonic() >= deadline:
				self.logger.debug(
					'Group-based single-message wait timed out: queue=%s group=%s timeout=%sms',
					self.queue,
					self.group,
					timeout,
				)
				return None
			sleep(0.01)

	def read(
		self,
		offset: Union[int, str] = 0,
		timeout: Optional[int] = None,
	) -> Iterable[Event]:
		if timeout is not None and timeout < 0:
			raise ValueError('Redis read timeout must be non-negative milliseconds')
		cursor = str(offset)
		deadline = monotonic() + timeout / 1000 if timeout else None
		self.logger.debug(
			'Starting history read without a consumer group: queue=%s offset=%s timeout=%sms',
			self.queue,
			cursor,
			timeout,
		)
		try:
			while True:
				if deadline is not None and monotonic() >= deadline:
					self.logger.debug(
						'History read without a consumer group timed out: queue=%s cursor=%s timeout=%sms',
						self.queue,
						cursor,
						timeout,
					)
					return
				try:
					messages = self.connection.xread(
						{self.queue: cursor},
						count=1,
					)
				except Exception as error:
					self.logger.error(
						'History read without a consumer group failed: queue=%s cursor=%s error_type=%s',
						self.queue,
						cursor,
						type(error).__name__,
					)
					raise
				if not messages:
					sleep(0.01)
					continue
				for _, entries in messages:
					for id, fields in entries:
						event = self.event(
							id,
							fields,
						)
						cursor = event.id
						self.logger.debug(
							'History message received without a consumer group: queue=%s id=%s',
							self.queue,
							event.id,
						)
						yield event
		finally:
			self.logger.debug(
				'History read without a consumer group ended: queue=%s cursor=%s',
				self.queue,
				cursor,
			)
