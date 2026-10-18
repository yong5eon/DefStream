from typing import (
	Any,
	Optional,
	Union,
)

from redis import Redis
from redis.cluster import RedisCluster

from ...Connection import (
	Connection as BaseConnection,
	GetQueue,
	GetStream,
	GetConsumer,
	Declarable,
	TaskSender,
)
from ...Event import EventHandler
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
	TaskSender,
):
	def __init__(
		self,
		conf: Configuration,
	):
		self.conf = conf
		self.connection: Optional[Union[Redis, RedisCluster]] = None

	def connect(self) -> None:
		if self.connection is not None:
			return
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
		if self.conf.type == ConnectionType.Cluster:
			connection = RedisCluster(**parameters)
		else:
			connection = Redis(
				db=self.conf.database,
				**parameters,
			)
		try:
			connection.ping()
		except Exception:
			connection.close()
			raise
		self.connection = connection

	def connected(self) -> Union[Redis, RedisCluster]:
		if self.connection is None:
			raise RuntimeError('Connect the Redis broker before use')
		return self.connection

	def declare(
		self,
		parameters: Any,
	) -> None:
		subscription = Subscription.parse(parameters)
		self.create_queue(
			subscription.queue,
			group=subscription.group,
		)

	def send(
		self,
		body: Any,
		parameters: Any,
	) -> str:
		subscription = Subscription.parse(parameters)
		return self.queue(
			subscription.queue,
			group=subscription.group,
		).send(body)

	def queue(
		self,
		name: str,
		group: str = 'DefStream',
	) -> Queue:
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
		self.queue(
			name,
			group,
		).create_group()

	def delete_queue(
		self,
		name: Union[str, Queue],
	) -> int:
		return self.connected().delete(str(name))

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
			self.connection.close()
			self.connection = None
