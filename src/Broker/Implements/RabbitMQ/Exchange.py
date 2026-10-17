# -*- coding: utf-8 -*-

from ... import (
	Sendable,
	Callable,
)

from .Serializer import (
	Encoder,
	Decoder,
)
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
	monotonic,
)
from enum import Enum
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
	def __init__(
		self,
		connection: BlockingConnection,
		encode: Encoder,
		name: str = None,
		decode: Optional[Decoder] = None,
		rpc_parameters: Optional[ConnectionParameters] = None,
	):
		self.connection = connection
		self.encode = encode
		self.channel = self.connection.channel()
		self.channel.auto_decode = False
		self.exchange = name
		self.decode = decode
		self.rpc_parameters = rpc_parameters
		return

	def __del__(self):
		if self.channel and self.channel.is_open:
			self.channel.close()
		return
	
	def __str__(self): return self.exchange

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
		)
		self.channel.basic_publish(
			exchange=self.exchange,
			routing_key=event if event else '',
			properties=properties,
			body=self.encode(body),
		)
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
			while not responses:
				remaining = deadline - monotonic()
				if remaining <= 0:
					raise TimeoutError(f'RPC response timed out for exchange {self.exchange!r} routing_key={event!r}')
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
