from logging import getLogger
from typing import (
	Any,
	Optional,
	Union,
)

from redis import Redis
from redis.cluster import RedisCluster

from DefStream.Broker import (
	Connection as BaseConnection,
	GetQueue,
	GetStream,
	GetConsumer,
	Declarable,
	Emittable,
	EventHandler,
)
from .Configuration import (
	Configuration,
	ConnectionType,
)
from .Consumer import Consumer
from .Queue import Queue
from .Subscription import Subscription

__all__ = (
	'Connection',
)


class Connection(
	BaseConnection,
	GetQueue,
	GetStream,
	GetConsumer,
	Declarable,
	Emittable,
):
	logger = getLogger('DefStream.Broker.Implements.Redis.Connection')

	def __init__(
		self,
		conf: Configuration,
	):
		self.conf = conf
		self.connection: Optional[Union[Redis, RedisCluster]] = None

	def connect(self) -> None:
		if self.connection is not None:
			self.logger.debug('Reusing existing Redis connection')
			return
		connection_type = self.conf.type.value
		self.logger.info(
			'Connecting to Redis: type=%s',
			connection_type,
		)
		self.logger.debug(
			'Redis connection settings: host=%s port=%s database=%s TLS=%s max=%s timeout=%ss',
			self.conf.host,
			self.conf.port,
			self.conf.database,
			self.conf.secure,
			self.conf.max,
			self.conf.timeout,
		)
		parameters = {
			'host': self.conf.host,
			'port': self.conf.port,
			'username': self.conf.username,
			'password': self.conf.password,
			'ssl': self.conf.secure,
			'max_connections': self.conf.max,
			'socket_connect_timeout': self.conf.timeout,
			'socket_timeout': self.conf.timeout,
			'decode_responses': False,
		}
		connection = None
		try:
			if self.conf.type == ConnectionType.Cluster:
				connection = RedisCluster(**parameters)
			else:
				connection = Redis(
					db=self.conf.database,
					**parameters,
				)
			connection.ping()
		except Exception as error:
			self.logger.error(
				'Redis connection or PING failed: type=%s error_type=%s',
				connection_type,
				type(error).__name__,
			)
			if connection is not None:
				connection.close()
			raise
		self.connection = connection
		self.logger.info(
			'Redis connection verified with PING: type=%s',
			connection_type,
		)

	def connected(self) -> Union[Redis, RedisCluster]:
		if self.connection is None:
			raise RuntimeError('Connect the Redis broker before use')
		return self.connection

	def declare(
		self,
		parameters: Any,
	) -> None:
		subscription = Subscription.parse(parameters)
		self.logger.debug(
			'Delegating stream declaration: queue=%s group=%s',
			subscription.queue,
			subscription.group,
		)
		self.create_queue(
			subscription.queue,
			group=subscription.group,
		)

	def emit(
		self,
		body: Any,
		parameters: Any,
	) -> str:
		subscription = Subscription.parse(parameters)
		self.logger.debug(
			'Delegating message publication: queue=%s group=%s',
			subscription.queue,
			subscription.group,
		)
		return self.queue(
			subscription.queue,
			group=subscription.group,
		).send(body)

	def queue(
		self,
		name: str,
		group: str = 'DefStream',
	) -> Queue:
		self.logger.debug(
			'Creating Queue: queue=%s group=%s',
			name,
			group,
		)
		return Queue(
			self.connected(),
			self.conf.encode,
			self.conf.decode,
			name,
			group,
		)

	def stream(
		self,
		name: str,
		group: str = 'DefStream',
	) -> Queue:
		return self.queue(
			name,
			group,
		)

	def consumer(
		self,
		handler: Optional[EventHandler] = None,
		qos: int = 1,
		reclaim_idle: Optional[int] = 60000,
	) -> Consumer:
		self.logger.debug(
			'Creating Consumer: qos=%s reclaim_idle=%sms',
			qos,
			reclaim_idle,
		)
		return Consumer(
			self.connected(),
			self.conf.encode,
			self.conf.decode,
			handler,
			qos,
			reclaim_idle,
		)

	def create_queue(
		self,
		name: str,
		group: str = 'DefStream',
	) -> None:
		self.logger.debug(
			'Delegating Consumer Group creation: queue=%s group=%s',
			name,
			group,
		)
		self.queue(
			name,
			group,
		).create_group()

	def delete_queue(
		self,
		name: Union[str, Queue],
	) -> int:
		queue = str(name)
		self.logger.debug(
			'Deleting Redis stream: queue=%s',
			queue,
		)
		try:
			deleted = self.connected().delete(queue)
		except Exception as error:
			self.logger.error(
				'Redis stream deletion failed: queue=%s error_type=%s',
				queue,
				type(error).__name__,
			)
			raise
		if isinstance(deleted, int) and deleted > 0:
			self.logger.info(
				'Redis stream deletion completed: queue=%s deleted=%s',
				queue,
				deleted,
			)
		else:
			self.logger.info(
				'No Redis stream to delete: queue=%s deleted=%s',
				queue,
				deleted,
			)
		return deleted

	def create_stream(
		self,
		name: str,
		group: str = 'DefStream',
	) -> None:
		self.create_queue(
			name,
			group,
		)

	def delete_stream(
		self,
		name: Union[str, Queue],
	) -> int:
		return self.delete_queue(name)

	def close(self) -> None:
		if self.connection is not None:
			self.logger.info('Closing Redis connection')
			try:
				self.connection.close()
			except Exception as error:
				self.logger.error(
					'Redis connection close failed: error_type=%s',
					type(error).__name__,
				)
				raise
			self.connection = None
			self.logger.info('Redis connection closed')
		else:
			self.logger.debug('No Redis connection to close')
