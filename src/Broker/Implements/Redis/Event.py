from logging import getLogger
from typing import (
	Any,
	Optional,
	Union,
)

from redis import Redis
from redis.cluster import RedisCluster

from DefStream.Broker import Event as BaseEvent

__all__ = (
	'Event',
)


class Event(BaseEvent):
	logger = getLogger('Broker.Redis.Event')

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
			self.logger.warning(
				'Rejected ACK for history Event without a consumer group: queue=%s id=%s',
				self.queue,
				self.id,
			)
			raise RuntimeError('Events from read() have no consumer group to acknowledge')
		if not self.settled:
			self.logger.debug(
				'Attempting Event ACK: queue=%s group=%s consumer=%s id=%s',
				self.queue,
				self.group,
				self.consumer,
				self.id,
			)
			try:
				result = self.connection.xack(
					self.queue,
					self.group,
					self.id,
				)
			except Exception as error:
				self.logger.error(
					'Event ACK failed: queue=%s group=%s consumer=%s id=%s error_type=%s',
					self.queue,
					self.group,
					self.consumer,
					self.id,
					type(error).__name__,
				)
				raise
			self.settled = True
			if isinstance(result, int) and result > 0:
				self.logger.debug(
					'Event ACK completed: queue=%s group=%s consumer=%s id=%s count=%s',
					self.queue,
					self.group,
					self.consumer,
					self.id,
					result,
				)
			else:
				self.logger.debug(
					'No Event ACK target: queue=%s group=%s consumer=%s id=%s count=%s',
					self.queue,
					self.group,
					self.consumer,
					self.id,
					result,
				)
		else:
			self.logger.debug(
				'Skipping ACK for settled Event: queue=%s group=%s consumer=%s id=%s',
				self.queue,
				self.group,
				self.consumer,
				self.id,
			)

	def nack(self) -> None:
		if self.group is None:
			self.logger.warning(
				'Rejected NACK for history Event without a consumer group: queue=%s id=%s',
				self.queue,
				self.id,
			)
			raise RuntimeError('Events from read() have no consumer group to requeue')
		if not self.settled:
			self.logger.debug(
				'Attempting Event requeue: queue=%s group=%s consumer=%s id=%s',
				self.queue,
				self.group,
				self.consumer,
				self.id,
			)
			# Requeue and acknowledge atomically on one stream (also valid in Cluster).
			try:
				result = self.connection.eval(
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
			except Exception as error:
				self.logger.error(
					'Event atomic requeue failed: queue=%s group=%s consumer=%s id=%s error_type=%s',
					self.queue,
					self.group,
					self.consumer,
					self.id,
					type(error).__name__,
				)
				raise
			self.settled = True
			if isinstance(result, int) and result > 0:
				self.logger.debug(
					'Event requeue and ACK completed: queue=%s group=%s consumer=%s id=%s count=%s',
					self.queue,
					self.group,
					self.consumer,
					self.id,
					result,
				)
			else:
				self.logger.debug(
					'No Event requeue target: queue=%s group=%s consumer=%s id=%s count=%s',
					self.queue,
					self.group,
					self.consumer,
					self.id,
					result,
				)
		else:
			self.logger.debug(
				'Skipping NACK for settled Event: queue=%s group=%s consumer=%s id=%s',
				self.queue,
				self.group,
				self.consumer,
				self.id,
			)

	def reject(self) -> None:
		self.logger.debug(
			'Event reject requested (currently implemented as ACK): queue=%s group=%s consumer=%s id=%s',
			self.queue,
			self.group,
			self.consumer,
			self.id,
		)
		self.ack()
