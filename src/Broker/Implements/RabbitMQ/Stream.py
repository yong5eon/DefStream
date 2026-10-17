# -*- coding: utf-8 -*-

from ... import (
	Sendable,
	Readable,
)
from .Serializer import (
	Encoder,
	Decoder,
)
from .Event import Event

from pika import (
	BlockingConnection,
	BasicProperties,
)

from time import time
from uuid import uuid4

from typing import (
	Dict,
	Iterable,
)

__all__ = (
	'Queue'
)


class Stream(
	Sendable,
	Readable,
):
	"""Stream of Event Broker for RabbitMQ"""
	def __init__(
		self,
		connection: BlockingConnection,
		encode: Encoder,
		decode: Decoder,
		name: str = None,
	):
		self.connection = connection
		self.encode = encode
		self.decode = decode
		self.channel = self.connection.channel()
		self.channel.auto_decode = False
		self.queue = name
		self.event = None
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
		timestamp: int = None,
		id: str = None,
	):
		if not timestamp: timestamp = int(time())
		if not id: id = uuid4().hex
		properties = BasicProperties(
			type=event if event else '',
			headers=headers,
			content_type=self.encode.format,
			content_encoding=self.encode.charset,
			timestamp=timestamp,
			message_id=id,
		)
		self.channel.basic_publish(
			exchange='',
			routing_key=self.queue,
			properties=properties,
			body=self.encode(body)
		)
		return id

	def read(self, offset: int = 0, timeout: int = None) -> Iterable[Event]:
		channel = self.channel
		channel.basic_qos(0, 1, False)

		deadline = time() + (timeout / 1000) if timeout else None

		try:
			for method, properties, body in channel.consume(
				queue=self.queue,
				auto_ack=False,
				inactivity_timeout=1,
				arguments={'x-stream-offset': offset},
			):
				if method is None:
					if deadline and time() >= deadline:
						break
					continue

				event = Event(
					channel,
					self.queue,
					method.consumer_tag,
					method.delivery_tag,
					properties,
					self.decode(body, properties.content_type, properties.content_encoding),
				)

				try:
					yield event
					channel.basic_ack(delivery_tag=method.delivery_tag)
				except Exception:
					channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
					raise
		finally:
			channel.cancel()
