# -*- coding: utf-8 -*-

from DefStream.Broker import (
	Connection as BaseConnection,
	GetExchange,
	GetQueue,
	GetStream,
	GetConsumer,
	Declarable,
	PrioritySupport,
	EventHandler,
)

from .Configuration import Configuration

from .Exchange import Exchange
from .Queue import Queue
from .Stream import Stream
from .Consumer import Consumer
from .Subscription import Subscription

from pika import (
	BlockingConnection,
	ConnectionParameters,
	PlainCredentials,
	BasicProperties,
)
from pika.exceptions import *

from collections.abc import Mapping
from operator import (
	eq,
	ne,
)
from enum import Enum
from uuid import uuid4
from contextlib import contextmanager
from logging import getLogger

from typing import (
	Any as AnyValue,
	Iterator,
	Union,
	Optional,
)

__all__ = (
	'Connection',
	'ExchangeType',
	'Parameters',
	'All',
	'Any',
)


class ExchangeType(str, Enum):
	Direct = 'direct'
	FanOut = 'fanout'
	Topic  = 'topic'
	Header = 'headers'
	def __str__(self): return str(self.value)


class Parameters(Mapping):
	"""Bind Parameters Event Broker for RabbitMQ"""
	def __init__(self, **kwargs):
		self.args = kwargs
		return
	
	def __iter__(self) -> Iterator:
		return self.args.__iter__()
	
	def __reversed__(self) -> Iterator:
		return self.args.__reversed__()
	
	def __len__(self) -> int:
		return self.args.__len__()
	
	def __getitem__(
		self,
		key: AnyValue,
	) -> AnyValue:
		return self.args.__getitem__(key)
	
	def __contains__(self, key: object) -> bool:
		return self.args.__contains__(key)
	
	def __eq__(self, other) -> bool:
		return eq(self.args, other)
	
	def __ne__(self, other) -> bool:
		return ne(self.args, other)
	
	def keys(self) -> Iterator:
		return self.args.keys()
	
	def items(self):
		return self.args.items()
	
	def values(self):
		return self.args.values()


class Connection(
	BaseConnection,
	GetExchange,
	GetQueue,
	GetStream,
	GetConsumer,
	Declarable,
	PrioritySupport,
):
	"""Connection of Event Broker for RabbitMQ"""
	logger = getLogger('DefStream.Broker.RabbitMQ.Connection')

	def __init__(self, conf: Configuration):
		self.conf = conf
		self.parameters = ConnectionParameters(
			host=self.conf.host,
			port=self.conf.port,
			credentials=PlainCredentials(self.conf.username, self.conf.password),
			virtual_host=self.conf.vhost,
			ssl_options=self.conf.ssl,
			blocked_connection_timeout=self.conf.timeout,
			heartbeat=self.conf.heartbeat
		)
		self.connection = None
		self.publisher = None
		return

	def __del__(self):
		self.close()
		return

	def connect(self):
		if self.connection and self.connection.is_open:
			self.logger.debug('Reusing open connection')
			return
		self.logger.debug('Connecting to RabbitMQ: host=%s port=%s vhost=%s', self.conf.host, self.conf.port, self.conf.vhost)
		with self.observe('RabbitMQ connection'):
			self.connection = BlockingConnection(parameters=self.parameters)
		return

	@contextmanager
	def observe(
		self,
		operation: str,
		*context,
	):
		"""이 클래스가 소유하는 I/O 경계만 기록하며 예외 내용은 노출하지 않는다."""
		try:
			yield
		except Exception as error:
			self.logger.error(operation + ' failed: error_type=%s', *context, type(error).__name__)
			raise
		else:
			self.logger.debug(operation + ' completed', *context)
		return

	def connected(self):
		if self.connection is None or not self.connection.is_open:
			self.logger.error('RabbitMQ connection is not open')
			raise RuntimeError('Connect the RabbitMQ connection before use')
		return self.connection

	def declare(
		self,
		parameters: AnyValue,
	) -> None:
		subscription = Subscription.parse(parameters)
		self.logger.debug('Task queue declaration: queue=%s error_queue=%s max_priority=%s durable=True', subscription.queue, subscription.error, subscription.max_priority)
		connection = self.connected()
		with self.observe('Task queue declaration'):
			channel = connection.channel()
			try:
				arguments = {}
				if subscription.error is not None:
					channel.queue_declare(
						subscription.error,
						durable=True,
					)
					arguments = {
						'x-dead-letter-exchange': '',
						'x-dead-letter-routing-key': subscription.error,
					}
				if subscription.max_priority is not None:
					arguments['x-max-priority'] = subscription.max_priority
				channel.queue_declare(
					subscription.queue,
					durable=True,
					arguments=arguments,
				)
			finally:
				if channel.is_open:
					channel.close()
		return

	def priority_parameters(
		self,
		parameters: AnyValue,
	) -> Subscription:
		"""작업 기본값을 검증하고 선언·발행에 사용할 구독 설정을 반환한다."""
		return Subscription.parse(parameters)

	def emit(
		self,
		body: AnyValue,
		parameters: AnyValue,
		*,
		priority: Optional[int] = None,
	) -> str:
		subscription = Subscription.parse(parameters)
		if priority is None:
			priority = subscription.priority
		subscription.validate_priority(priority)
		connection = self.connected()
		channel = self.publisher
		if channel is None or not channel.is_open:
			try:
				channel = connection.channel()
				channel.confirm_delivery()
				self.logger.debug('Publisher channel created: publisher_confirm=True')
			except Exception as error:
				self.logger.error('Publisher channel creation failed: queue=%s error_type=%s', subscription.queue, type(error).__name__)
				if channel is not None and channel.is_open:
					channel.close()
				raise
			self.publisher = channel
		else:
			self.logger.debug('Reusing publisher channel: publisher_confirm=True')
		id = uuid4().hex
		self.logger.debug('Publishing directly: queue=%s message_id=%s priority=%s publisher_confirm=True', subscription.queue, id, priority)
		try:
			channel.basic_publish(
				exchange='',
				routing_key=subscription.queue,
				body=self.conf.encode(body),
				properties=BasicProperties(
					message_id=id,
					headers={},
					content_type=self.conf.encode.format,
					content_encoding=self.conf.encode.charset,
					delivery_mode=2,
					priority=priority,
				),
				mandatory=True,
			)
		except Exception as error:
			self.logger.error('Direct publication failed: queue=%s message_id=%s error_type=%s', subscription.queue, id, type(error).__name__)
			raise
		self.logger.debug('Direct publication confirmed: queue=%s message_id=%s', subscription.queue, id)
		return id

	def request(
		self,
		body: AnyValue,
		parameters: AnyValue,
		timeout: float = 5,
		*,
		priority: Optional[int] = None,
	) -> AnyValue:
		subscription = Subscription.parse(parameters)
		if priority is None:
			priority = subscription.priority
		subscription.validate_priority(priority)
		self.connected()
		queue = self.queue(subscription.queue)
		self.logger.debug('Delegating RPC to Queue: queue=%s timeout=%s priority=%s', subscription.queue, timeout, priority)
		try:
			if priority is not None:
				return queue.call(
					body,
					timeout=timeout,
					priority=priority,
				)
			return queue.call(
				body,
				timeout=timeout,
			)
		finally:
			try:
				if queue.channel.is_open:
					queue.channel.close()
					self.logger.debug('RPC delegated channel cleanup completed: queue=%s', subscription.queue)
			except Exception as error:
				self.logger.error('RPC delegated channel cleanup failed: queue=%s error_type=%s', subscription.queue, type(error).__name__)
				raise

	def exchange(self, exchange: str) -> Exchange:
		self.logger.debug('Creating Exchange: exchange=%s', exchange)
		return Exchange(
			self.connection,
			self.conf.encode,
			exchange,
			decode=self.conf.decode,
			rpc_parameters=self.parameters,
		)

	def queue(self, queue: str) -> Queue:
		self.logger.debug('Creating Queue: queue=%s', queue)
		return Queue(
			self.connection,
			self.conf.encode,
			self.conf.decode,
			queue,
			rpc_parameters=self.parameters,
		)

	def stream(self, queue: str) -> Stream:
		self.logger.debug('Creating Stream: queue=%s', queue)
		return Stream(self.connection, self.conf.encode, self.conf.decode, queue)

	def consumer(
		self,
		handler: Optional[EventHandler] = None,
		qos: int = 1,
		offset: int = None,
	) -> Consumer:
		self.logger.debug('Creating Consumer: qos=%s offset=%s', qos, offset)
		return Consumer(
			self.connection,
			self.conf.decode,
			handler,
			qos=qos,
			offset=offset,
			encode=self.conf.encode,
		)

	def close(self):
		if self.connection and self.connection.is_open:
			with self.observe('RabbitMQ connection close'):
				self.connection.close()
				self.connection = None
		self.publisher = None
		return

	def create_exchange(
		self,
		name: str,
		type: ExchangeType,
		durable: bool = True,
		autodelete: bool = False,
		alter: Union[str, Exchange] = None,
	):
		args = {}
		if alter:
			args['alternate-exchange'] = str(alter)
		self.logger.debug('Exchange declaration: exchange=%s type=%s durable=%s auto_delete=%s alternate_exchange=%s', name, type, durable, autodelete, str(alter) if alter else None)
		with self.observe('Exchange declaration: exchange=%s', name):
			channel = self.connection.channel()
			try:
				channel.exchange_declare(
					name,
					str(type),
					durable=durable,
					auto_delete=autodelete,
					arguments=args
				)
			finally:
				if channel.is_open:
					channel.close()
		return

	def delete_exchange(
		self,
		name: str,
	):
		with self.observe('Exchange deletion: exchange=%s', name):
			channel = self.connection.channel()
			channel.exchange_delete(name)
		return

	def bind_exchange_to_exchange(
		self,
		src: Union[str, Exchange],
		to: Union[str, Exchange],
		event: str = None,
		parameters: Parameters = None,
	):
		with self.observe('Exchange binding: src=%s to=%s routing_key=%s', str(src), str(to), event):
			channel = self.connection.channel()
			channel.exchange_bind(
				str(src),
				str(to),
				routing_key=event if event else '',
				arguments=parameters
			)
		return

	def unbind_exchange_to_exchange(
		self,
		src: Union[str, Exchange],
		to: Union[str, Exchange],
		event: str = None,
		parameters: Parameters = None,
	):
		with self.observe('Exchange unbinding: src=%s to=%s routing_key=%s', str(src), str(to), event):
			channel = self.connection.channel()
			channel.exchange_unbind(
				str(src),
				str(to),
				routing_key=event if event else '',
				arguments=parameters,
			)
		return

	def create_queue(
		self,
		name: str,
		expires: int = None,
		ttl: int = None,
		limit: int = None,
		size: int = None,
		maxPriority: int = None,
		durable: bool = True,
		autodelete: bool = False,
		errorQueue: Union[str, Queue] = None,
		errorExchange: Union[str, Exchange] = None,
	):
		args = {}
		if errorQueue:
			args['x-dead-letter-exchange'] = ''
			args['x-dead-letter-routing-key'] = str(errorQueue)
		if errorExchange:
			args['x-dead-letter-exchange'] = str(errorExchange)
		if expires:
			args['x-expires'] = expires
		if ttl:
			args['x-message-ttl'] = ttl
		if limit:
			args['x-max-length'] = limit
		if size:
			args['x-max-length-bytes'] = size
		if maxPriority:
			args['x-max-priority'] = maxPriority
		self.logger.debug('Queue declaration options: queue=%s durable=%s auto_delete=%s expires=%s ttl=%s limit=%s size=%s max_priority=%s error_queue=%s error_exchange=%s', name, durable, autodelete, expires, ttl, limit, size, maxPriority, str(errorQueue) if errorQueue else None, str(errorExchange) if errorExchange else None)
		with self.observe('Queue declaration: queue=%s', name):
			channel = self.connection.channel()
			channel.queue_declare(
				name,
				durable=durable,
				auto_delete=autodelete,
				arguments=args
			)
		return

	def delete_queue(
		self,
		queue: str,
	):
		with self.observe('Queue deletion: queue=%s', queue):
			channel = self.connection.channel()
			channel.queue_delete(queue)
		return

	def bind_exchange_to_queue(
		self,
		src: Union[str, Exchange],
		to: Union[str, Queue],
		event: str = None,
		parameters: Parameters = None,
	):
		with self.observe('Queue binding: exchange=%s queue=%s routing_key=%s', str(src), str(to), event):
			channel = self.connection.channel()
			channel.queue_bind(
				str(to),
				str(src),
				routing_key=event if event else '',
				arguments=parameters
			)
		return

	def unbind_exchange_to_queue(
		self,
		src: Union[str, Exchange],
		to: Union[str, Queue],
		event: str = None,
		parameters: Parameters = None,
	):
		with self.observe('Queue unbinding: exchange=%s queue=%s routing_key=%s', str(src), str(to), event):
			channel = self.connection.channel()
			channel.queue_unbind(
				str(to),
				str(src),
				routing_key=event if event else '',
				arguments=parameters,
			)
		return
	
	def create_stream(
		self,
		name: str,
		size: int = None,
		durable: bool = True,
		autodelete: bool = False,
	):
		args = {
			'x-queue-type': 'stream',
		}
		if size:
			args['x-max-length-bytes'] = size
		self.logger.debug('Stream declaration options: queue=%s durable=%s auto_delete=%s size=%s', name, durable, autodelete, size)
		with self.observe('Stream declaration: queue=%s', name):
			channel = self.connection.channel()
			channel.queue_declare(
				name,
				durable=durable,
				auto_delete=autodelete,
				arguments=args
			)
		return
	
	def delete_stream(
		self,
		queue: str,
	):
		with self.observe('Stream deletion: queue=%s', queue):
			channel = self.connection.channel()
			channel.queue_delete(queue)
		return


class All(Parameters):
	"""All Bind Parameters Event Broker for RabbitMQ"""
	def __init__(self, **kwargs):
		headers = {
			'x-match': 'all-with-x'
		}
		headers.update(kwargs)
		super().__init__(**headers)
		return


class Any(Parameters):
	"""Any Bind Parameters Event Broker for RabbitMQ"""
	def __init__(self, **kwargs):
		headers = {
			'x-match': 'any-with-x'
		}
		headers.update(kwargs)
		super().__init__(**headers)
		return
