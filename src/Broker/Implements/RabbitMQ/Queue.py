# -*- coding: utf-8 -*-

from DefStream.Broker import (
	Sendable,
	Callable,
	Poppable,
	RemoteError,
	validate_priority,
)

from .Serializer import (
	Encoder,
	Decoder,
)
from .Event import Event
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
	sleep,
	monotonic,
)
from uuid import uuid4

from typing import (
	Any,
	Optional,
	Dict,
)

__all__ = (
	'Queue',
)


class Queue(
	Sendable,
	Callable,
	Poppable,
):
	"""Queue of Event Broker for RabbitMQ"""
	logger = getLogger('Broker.RabbitMQ.Queue')

	def __init__(
		self,
		connection: BlockingConnection,
		encode: Encoder,
		decode: Decoder,
		name: str,
		rpc_parameters: Optional[ConnectionParameters] = None,
	):
		self.connection = connection
		self.encode = encode
		self.decode = decode
		try:
			self.channel = self.connection.channel()
		except Exception as error:
			self.logger.error('Queue channel creation failed: queue=%s error_type=%s', name, type(error).__name__)
			raise
		self.queue = name
		self.event = None
		self.rpc_parameters = rpc_parameters
		return

	def __del__(self):
		channel = getattr(self, 'channel', None)
		try:
			if channel and channel.is_open:
				channel.close()
				self.logger.debug('Queue channel cleanup completed: queue=%s', self.queue)
		except Exception as error:
			self.logger.error('Queue channel cleanup failed: error_type=%s', type(error).__name__)
			raise
		return
	
	def __str__(self): return self.queue

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
		reply_to: Optional[str] = None,
		correlation_id: Optional[str] = None,
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
			reply_to=reply_to,
			correlation_id=correlation_id,
		)
		self.logger.debug('Publishing message: queue=%s message_id=%s priority=%s persistent=%s publisher_confirm=False', self.queue, id, priority, persistent)
		try:
			self.channel.basic_publish(
				exchange='',
				routing_key=self.queue,
				properties=properties,
				body=self.encode(body)
			)
		except Exception as error:
			self.logger.error('Message publication failed: queue=%s message_id=%s error_type=%s', self.queue, id, type(error).__name__)
			raise
		self.logger.debug('Publish API call completed: queue=%s message_id=%s does not imply Consumer processing completion', self.queue, id)
		return id

	def call(
		self,
		body: Any,
		timeout: float = 5,
		*,
		priority: Optional[int] = None,
	) -> Any:
		validate_priority(
			priority,
			255,
		)
		if self.rpc_parameters is None:
			raise RuntimeError('RPC requires connection parameters; obtain the queue through Connection.queue')
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
		self.logger.debug('Opening dedicated RPC connection: queue=%s timeout=%s', self.queue, timeout)
		try:
			connection = BlockingConnection(settings)
		except Exception as error:
			self.logger.error('Dedicated RPC connection failed: queue=%s error_type=%s', self.queue, type(error).__name__)
			raise
		try:
			channel = connection.channel()
			reply_queue = channel.queue_declare(
				queue=f'{self.queue}.{uuid4().hex}',
				exclusive=True,
				auto_delete=True,
			).method.queue
			channel.confirm_delivery()
			correlation_id = uuid4().hex
			self.logger.debug('RPC reply queue created: queue=%s reply_to=%s correlation_id=%s publisher_confirm=True', self.queue, reply_queue, correlation_id)
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
					self.logger.debug('RPC response received: queue=%s correlation_id=%s', self.queue, correlation_id)
				else:
					self.logger.debug('Ignoring RPC response with mismatched correlation_id: queue=%s correlation_id=%s', self.queue, properties.correlation_id)

			channel.basic_consume(
				reply_queue,
				on_message_callback=receive,
				auto_ack=True,
			)
			remaining = deadline - monotonic()
			if remaining <= 0:
				timed_out = True
				self.logger.warning('RPC timed out before publication: queue=%s correlation_id=%s', self.queue, correlation_id)
				raise TimeoutError('RPC timed out before request publication')
			self.logger.debug('Publishing RPC request: queue=%s correlation_id=%s priority=%s', self.queue, correlation_id, priority)
			channel.basic_publish(
				exchange='',
				routing_key=self.queue,
				body=self.encode(body),
				properties=BasicProperties(
					priority=priority,
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
			self.logger.debug('RPC request published: queue=%s correlation_id=%s', self.queue, correlation_id)
			while not responses:
				remaining = deadline - monotonic()
				if remaining <= 0:
					timed_out = True
					self.logger.warning('RPC response timed out after publication; delivered work is not cancelled: queue=%s correlation_id=%s', self.queue, correlation_id)
					raise TimeoutError(f'RPC response timed out for queue {self.queue!r}')
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
				self.logger.debug('RPC response validated: queue=%s correlation_id=%s elapsed=%s', self.queue, correlation_id, timeout - (deadline - monotonic()))
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
			self.logger.warning('RPC remote task error: queue=%s correlation_id=%s', self.queue, correlation_id)
			raise RemoteError(
				error['code'],
				error['message'],
			)
		except TimeoutError:
			if not timed_out:
				self.logger.error('RPC internal timeout error: queue=%s', self.queue)
			raise
		except RemoteError:
			raise
		except Exception as error:
			self.logger.error('RPC transmission or response handling failed: queue=%s error_type=%s', self.queue, type(error).__name__)
			raise
		finally:
			try:
				if connection.is_open:
					connection.close()
					self.logger.debug('Dedicated RPC connection and reply queue cleanup completed: queue=%s', self.queue)
			except Exception as error:
				self.logger.error('Dedicated RPC connection cleanup failed: queue=%s error_type=%s', self.queue, type(error).__name__)
				raise

	def pop(self, timeout: Optional[int] = None) -> Optional[Event]:
		self.logger.debug('Waiting for a single message: queue=%s timeout_ms=%s', self.queue, timeout)
		channel = self.channel
		try:
			channel.basic_qos(0, 1, False)
			deadline = time() + (timeout / 1000) if timeout else None
			while True:
				method, properties, body = channel.basic_get(queue=self.queue, auto_ack=False)
				if method:
					# pika returns properties and body together with a GetOk method frame.
					assert properties is not None and body is not None
					event = Event(
						channel,
						self.queue,
						None,
						method.delivery_tag,
						properties,
						self.decode(body, properties.content_type, properties.content_encoding),
					)
					self.logger.debug('Single message received and decoded: queue=%s delivery_tag=%s message_id=%s', self.queue, method.delivery_tag, properties.message_id)
					return event
				if deadline and time() >= deadline:
					break
				sleep(0.1)
		except Exception as error:
			self.logger.error('Single-message reception failed: queue=%s error_type=%s', self.queue, type(error).__name__)
			raise
		self.logger.debug('Single-message wait ended: queue=%s', self.queue)
		return
