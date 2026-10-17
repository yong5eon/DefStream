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

from ...Protocol import (
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
	def __init__(
		self,
		connection: Union[Redis, RedisCluster],
		encode: Encoder,
		decode: Decoder,
		name: str,
		group: str = 'PinkStream',
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
		try:
			self.connection.xgroup_create(
				self.queue,
				self.group,
				id='0-0',
				mkstream=True,
			)
		except ResponseError as error:
			if not str(error).startswith('BUSYGROUP '):
				raise

	def send(
		self,
		body: Any,
	) -> str:
		id = self.connection.xadd(
			self.queue,
			{'body': self.encode(body)},
		)
		return id.decode('ascii')

	def event(
		self,
		id: bytes,
		fields: dict,
		group: Optional[str] = None,
		consumer: Optional[str] = None,
	) -> Event:
		return Event(
			self.connection,
			self.queue,
			id.decode('ascii'),
			self.decode(fields[b'body']),
			group,
			consumer,
		)

	def pop(
		self,
		timeout: Optional[int] = None,
	) -> Optional[Event]:
		if timeout is not None and timeout < 0:
			raise ValueError('Redis pop timeout must be non-negative milliseconds')
		self.create_group()
		deadline = monotonic() + timeout / 1000 if timeout else None
		while True:
			messages = self.connection.xreadgroup(
				self.group,
				self.consumer,
				{self.queue: '>'},
				count=1,
			)
			for _, entries in messages:
				for id, fields in entries:
					return self.event(
						id,
						fields,
						self.group,
						self.consumer,
					)
			if deadline is not None and monotonic() >= deadline:
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
		while True:
			if deadline is not None and monotonic() >= deadline:
				return
			messages = self.connection.xread(
				{self.queue: cursor},
				count=1,
			)
			if not messages:
				sleep(0.01)
				continue
			for _, entries in messages:
				for id, fields in entries:
					cursor = id.decode('ascii')
					yield self.event(
						id,
						fields,
					)
