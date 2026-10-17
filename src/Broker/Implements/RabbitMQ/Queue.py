# -*- coding: utf-8 -*-

from ... import (
	Sendable,
	Callable,
	Poppable,
)

from .Serializer import (
	Encoder,
	Decoder,
)
from .Event import Event
from ...Errors import RemoteError
from copy import deepcopy
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
	'Queue'
)


class Queue(
	Sendable,
	Callable,
	Poppable,
):
	"""Queue of Event Broker for RabbitMQ"""
	def __init__(
		self,
		connection: BlockingConnection,
		encode: Encoder,
		decode: Decoder,
		name: str = None,
		rpc_parameters: Optional[ConnectionParameters] = None,
	):
		self.connection = connection
		self.encode = encode
		self.decode = decode
		self.channel = self.connection.channel()
		self.channel.auto_decode = False
		self.queue = name
		self.event = None
		self.rpc_parameters = rpc_parameters
		return

	def __del__(self):
		if self.channel and self.channel.is_open:
			self.channel.close()
		return
	
	def __str__(self): return self.queue

	def send(
		self,
		body,
		event: str = None,
		headers: Dict = {},
		priority: int = None,
		expiration: int = None,
		timestamp: int = None,
		persistent: bool = True,
		id: str = None,
		reply_to: str = None,
		correlation_id: str = None,
	):
		if not timestamp: timestamp = int(time())
		if not id: id = uuid4().hex
		properties = BasicProperties(
			type=event if event else '',
			headers=headers,
			content_type=self.encode.format,
			content_encoding=self.encode.charset,
			priority=priority,
			timestamp=timestamp,
			expiration=expiration,
			message_id=id,
			delivery_mode=2 if persistent else 1,
			reply_to=reply_to,
			correlation_id=correlation_id,
		)
		self.channel.basic_publish(
			exchange='',
			routing_key=self.queue,
			properties=properties,
			body=self.encode(body)
		)
		return id

	def call(
		self,
		body: Any,
		timeout: float = 5,
	) -> Any:
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
		settings.socket_timeout = min(
			settings.socket_timeout,
			timeout,
		)
		settings.stack_timeout = timeout
		settings.blocked_connection_timeout = timeout
		connection = BlockingConnection(settings)
		try:
			channel = connection.channel()
			reply_queue = channel.queue_declare(
				queue='',
				exclusive=True,
				auto_delete=True,
			).method.queue
			channel.confirm_delivery()
			correlation_id = uuid4().hex
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

			channel.basic_consume(
				reply_queue,
				on_message_callback=receive,
				auto_ack=True,
			)
			remaining = deadline - monotonic()
			if remaining <= 0:
				raise TimeoutError('RPC timed out before request publication')
			channel.basic_publish(
				exchange='',
				routing_key=self.queue,
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
			while not responses:
				remaining = deadline - monotonic()
				if remaining <= 0:
					raise TimeoutError(f'RPC response timed out for queue {self.queue!r}')
				connection.process_data_events(time_limit=min(
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
			raise RemoteError(
				error['code'],
				error['message'],
			)
		finally:
			if connection.is_open:
				connection.close()

	def pop(self, timeout: int = None) -> Optional[Event]:
		channel = self.channel
		channel.basic_qos(0, 1, False)
		deadline = time() + (timeout / 1000) if timeout else None
		while True:
			method, properties, body = channel.basic_get(queue=self.queue, auto_ack=False)
			if method:
				return Event(
					channel,
					self.queue,
					None,
					method.delivery_tag,
					properties,
					self.decode(body, properties.content_type, properties.content_encoding),
				)
			if deadline and time() >= deadline:
				break
			sleep(0.1)
		return
