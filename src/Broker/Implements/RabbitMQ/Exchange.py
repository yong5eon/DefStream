# -*- coding: utf-8 -*-

from DefStream.Broker import (
	Sendable,
	Callable,
	RemoteError,
	validate_priority,
)

from .Serializer import (
	Encoder,
	Decoder,
)
from copy import deepcopy
from logging import getLogger
from math import (
	ceil,
	isfinite,
)

from pika import (
	BlockingConnection,
	BasicProperties,
	ConnectionParameters,
)

from time import (
	time,
	monotonic,
)
from uuid import uuid4

from typing import (
	Any,
	Dict,
	Optional,
)

__all__ = (
	'Exchange',
)


class Exchange(
	Sendable,
	Callable,
):
	"""Exchange of Event Broker for RabbitMQ"""
	logger = getLogger('Broker.RabbitMQ.Exchange')

	def __init__(
		self,
		connection: BlockingConnection,
		encode: Encoder,
		name: str,
		decode: Optional[Decoder] = None,
		rpc_parameters: Optional[ConnectionParameters] = None,
	):
		self.connection = connection
		self.encode = encode
		try:
			self.channel = self.connection.channel()
		except Exception as error:
			self.logger.error('Exchange channel creation failed: exchange=%s error_type=%s', name, type(error).__name__)
			raise
		self.exchange = name
		self.decode = decode
		self.rpc_parameters = rpc_parameters
		return

	def __del__(self):
		channel = getattr(self, 'channel', None)
		try:
			if channel and channel.is_open:
				channel.close()
				self.logger.debug('Exchange channel cleanup completed: exchange=%s', self.exchange)
		except Exception as error:
			self.logger.error('Exchange channel cleanup failed: error_type=%s', type(error).__name__)
			raise
		return
	
	def __str__(self): return self.exchange

	def send(
		self,
		body,
		event: Optional[str] = None,
		headers: Dict = {},
		priority: Optional[int] = None,
		expiration: Optional[int] = None,
		timestamp: Optional[int] = None,
		persistent: bool = True,
		id: Optional[str] = None,
	):
		validate_priority(
			priority,
			255,
		)
		if not timestamp: timestamp = int(time())
		if not id: id = uuid4().hex
		properties = BasicProperties(
			type=event if event else '',
			headers=headers,
			content_type=self.encode.format,
			content_encoding=self.encode.charset,
			priority=priority,
			timestamp=timestamp,
			expiration=str(expiration) if expiration is not None else None,
			message_id=id,
			delivery_mode=2 if persistent else 1,
		)
		self.logger.debug('Publishing message: exchange=%s routing_key=%s message_id=%s priority=%s persistent=%s publisher_confirm=False', self.exchange, event, id, priority, persistent)
		try:
			self.channel.basic_publish(
				exchange=self.exchange,
				routing_key=event if event else '',
				properties=properties,
				body=self.encode(body),
			)
		except Exception as error:
			self.logger.error('Message publication failed: exchange=%s routing_key=%s message_id=%s error_type=%s', self.exchange, event, id, type(error).__name__)
			raise
		self.logger.debug('Publish API call completed: exchange=%s message_id=%s does not imply Consumer processing completion', self.exchange, id)
		return id

	def call(
		self,
		body: Any,
		timeout: float = 5,
		*,
		event: Optional[str] = None,
	) -> Any:
		if self.rpc_parameters is None or self.decode is None:
			raise RuntimeError('RPC requires decoder and connection parameters; obtain the exchange through Connection.exchange')
		if isinstance(
			timeout,
			bool,
		) or not isinstance(
			timeout,
			(
				int,
				float,
			),
		) or not isfinite(timeout) or timeout <= 0:
			raise ValueError('RPC timeout must be a finite positive number of seconds')
		deadline = monotonic() + timeout
		settings = deepcopy(self.rpc_parameters)
		settings.connection_attempts = 1
		settings.socket_timeout = timeout if settings.socket_timeout is None else min(
			settings.socket_timeout,
			timeout,
		)
		settings.stack_timeout = timeout
		settings.blocked_connection_timeout = timeout
		timed_out = False
		self.logger.debug('Opening dedicated RPC connection: exchange=%s routing_key=%s timeout=%s', self.exchange, event, timeout)
		try:
			connection = BlockingConnection(settings)
		except Exception as error:
			self.logger.error('Dedicated RPC connection failed: exchange=%s error_type=%s', self.exchange, type(error).__name__)
			raise
		try:
			channel = connection.channel()
			reply_queue = channel.queue_declare(
				queue='',
				exclusive=True,
				auto_delete=True,
			).method.queue
			channel.confirm_delivery()
			correlation_id = uuid4().hex
			self.logger.debug('RPC reply queue created: exchange=%s reply_to=%s correlation_id=%s publisher_confirm=True', self.exchange, reply_queue, correlation_id)
			responses = []

			def receive(
				channel,
				method,
				properties,
				payload,
			):
				if properties.correlation_id == correlation_id:
					responses.append((
						properties,
						payload,
					))
					self.logger.debug('RPC response received: exchange=%s correlation_id=%s', self.exchange, correlation_id)
				else:
					self.logger.debug('Ignoring RPC response with mismatched correlation_id: exchange=%s correlation_id=%s', self.exchange, properties.correlation_id)

			channel.basic_consume(
				reply_queue,
				on_message_callback=receive,
				auto_ack=True,
			)
			remaining = deadline - monotonic()
			if remaining <= 0:
				timed_out = True
				self.logger.warning('RPC timed out before publication: exchange=%s routing_key=%s correlation_id=%s', self.exchange, event, correlation_id)
				raise TimeoutError('RPC timed out before request publication')
			self.logger.debug('Publishing RPC request: exchange=%s routing_key=%s correlation_id=%s', self.exchange, event, correlation_id)
			channel.basic_publish(
				exchange=self.exchange,
				routing_key=event if event is not None else '',
				body=self.encode(body),
				properties=BasicProperties(
					reply_to=reply_queue,
					correlation_id=correlation_id,
					content_type=self.encode.format,
					content_encoding=self.encode.charset,
					expiration=str(max(
						1,
						ceil(remaining * 1000),
					)),
				),
				mandatory=True,
			)
			self.logger.debug('RPC request published: exchange=%s routing_key=%s correlation_id=%s', self.exchange, event, correlation_id)
			while not responses:
				remaining = deadline - monotonic()
				if remaining <= 0:
					timed_out = True
					self.logger.warning('RPC response timed out after publication; delivered work is not cancelled: exchange=%s routing_key=%s correlation_id=%s', self.exchange, event, correlation_id)
					raise TimeoutError(f'RPC response timed out for exchange {self.exchange!r} routing_key={event!r}')
				# pika accepts a float time_limit; the bundled stub declares int only.
				connection.process_data_events(time_limit=min(  # pyright: ignore[reportArgumentType]
					remaining,
					0.1,
				))
			properties, payload = responses[0]
			response = self.decode(
				payload,
				properties.content_type,
				properties.content_encoding,
			)
			if not isinstance(
				response,
				dict,
			) or type(response.get('ok')) is not bool:
				raise ValueError('Invalid RPC response envelope')
			if response['ok']:
				if 'result' not in response:
					raise ValueError('RPC response has no result')
				self.logger.debug('RPC response validated: exchange=%s routing_key=%s correlation_id=%s elapsed=%s', self.exchange, event, correlation_id, timeout - (deadline - monotonic()))
				return response['result']
			error = response.get('error')
			if not isinstance(
				error,
				dict,
			) or not isinstance(
				error.get('code'),
				str,
			) or not isinstance(
				error.get('message'),
				str,
			):
				raise ValueError('Invalid RPC error response')
			self.logger.warning('RPC remote task error: exchange=%s routing_key=%s correlation_id=%s', self.exchange, event, correlation_id)
			raise RemoteError(
				error['code'],
				error['message'],
			)
		except TimeoutError:
			if not timed_out:
				self.logger.error('RPC internal timeout error: exchange=%s routing_key=%s', self.exchange, event)
			raise
		except RemoteError:
			raise
		except Exception as error:
			self.logger.error('RPC transmission or response handling failed: exchange=%s routing_key=%s error_type=%s', self.exchange, event, type(error).__name__)
			raise
		finally:
			try:
				if connection.is_open:
					connection.close()
					self.logger.debug('Dedicated RPC connection and reply queue cleanup completed: exchange=%s', self.exchange)
			except Exception as error:
				self.logger.error('Dedicated RPC connection cleanup failed: exchange=%s error_type=%s', self.exchange, type(error).__name__)
				raise
