# -*- coding: utf-8 -*-

from ...Connection import (
	Connection as BaseConnection,
	GetExchange,
	GetQueue,
	GetStream,
	GetConsumer,
)

from .Configuration import Configuration

from .Exchange import Exchange
from .Queue import Queue
from .Stream import Stream
from .Consumer import Consumer
from ...Event import EventHandler

from pika import (
	BlockingConnection,
	ConnectionParameters,
	PlainCredentials,
)
from pika.exceptions import *

from collections.abc import Mapping
from operator import (
	eq,
	ne,
)
from enum import Enum

from typing import (
	Any,
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
	
	def __getitem__(self, key: Any) -> Any:
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
):
	"""Connection of Event Broker for RabbitMQ"""
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
		return

	def __del__(self):
		self.close()
		return

	def connect(self):
		if self.connection and self.connection.is_open:
			return
		self.connection = BlockingConnection(parameters=self.parameters)
		return

	def exchange(self, exchange: str) -> Exchange:
		return Exchange(
			self.connection,
			self.conf.encode,
			exchange,
			decode=self.conf.decode,
			rpc_parameters=self.parameters,
		)

	def queue(self, queue: str) -> Queue:
		return Queue(
			self.connection,
			self.conf.encode,
			self.conf.decode,
			queue,
			rpc_parameters=self.parameters,
		)

	def stream(self, queue: str) -> Stream:
		return Stream(self.connection, self.conf.encode, self.conf.decode, queue)

	def consumer(
		self,
		handler: Optional[EventHandler] = None,
		qos: int = 1,
		offset: int = None,
	) -> Consumer:
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
			self.connection.close()
			self.connection = None
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
		channel = self.connection.channel()
		channel.exchange_declare(
			name,
			str(type),
			durable=durable,
			auto_delete=autodelete,
			arguments=args
		)
		return

	def delete_exchange(
		self,
		name: str,
	):
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
		channel = self.connection.channel()
		args = {
			'x-queue-type': 'stream',
		}
		if size:
			args['x-max-length-bytes'] = size
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

