from typing import (
	Any,
	Optional,
	Union,
)

from redis import Redis
from redis.cluster import RedisCluster

from ...Event import Event as BaseEvent

__all__ = (
	'Event',
)


class Event(BaseEvent):
	def __init__(
		self,
		connection: Union[Redis, RedisCluster],
		queue: str,
		id: str,
		body: Any,
		group: Optional[str] = None,
		consumer: Optional[str] = None,
	):
		self.connection = connection
		self.queue = queue
		self.id = id
		self.payload = body
		self.group = group
		self.consumer = consumer
		self.settled = False

	@property
	def body(self) -> Any:
		return self.payload

	@body.setter
	def body(
		self,
		body: Any,
	) -> None:
		self.payload = body

	@property
	def src(self) -> str:
		return self.queue

	def ack(self) -> None:
		if self.group is None:
			raise RuntimeError('Events from read() have no consumer group to acknowledge')
		if not self.settled:
			self.connection.xack(
				self.queue,
				self.group,
				self.id,
			)
			self.settled = True

	def nack(self) -> None:
		if self.group is None:
			raise RuntimeError('Events from read() have no consumer group to requeue')
		if not self.settled:
			# Requeue and acknowledge atomically on one stream (also valid in Cluster).
			self.connection.eval(
				"""
				local pending = redis.call('XPENDING', KEYS[1], ARGV[1], ARGV[2], ARGV[2], 1)
				if #pending == 0 then return 0 end
				local entries = redis.call('XRANGE', KEYS[1], ARGV[2], ARGV[2])
				if #entries == 0 then return redis.error_reply('Pending entry was deleted') end
				redis.call('XADD', KEYS[1], '*', unpack(entries[1][2]))
				return redis.call('XACK', KEYS[1], ARGV[1], ARGV[2])
				""",
				1,
				self.queue,
				self.group,
				self.id,
			)
			self.settled = True

	def reject(self) -> None:
		self.ack()
