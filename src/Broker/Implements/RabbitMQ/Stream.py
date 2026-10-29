# -*- coding: utf-8 -*-

from DefStream.Broker import (
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
from logging import getLogger
from uuid import uuid4

from typing import (
	Dict,
	Iterable,
	Optional,
)

__all__ = (
	'Stream',
)


class Stream(
	Sendable,
	Readable,
):
	"""Stream of Event Broker for RabbitMQ"""
	logger = getLogger('Broker.RabbitMQ.Stream')

	def __init__(
		self,
		connection: BlockingConnection,
		encode: Encoder,
		decode: Decoder,
		name: str,
	):
		self.connection = connection
		self.encode = encode
		self.decode = decode
		try:
			self.channel = self.connection.channel()
		except Exception as error:
			self.logger.error('Stream channel creation failed: queue=%s error_type=%s', name, type(error).__name__)
			raise
		self.queue = name
		self.event = None
		return

	def __del__(self):
		channel = getattr(self, 'channel', None)
		try:
			if channel and channel.is_open:
				channel.close()
				self.logger.debug('Stream channel cleanup completed: queue=%s', self.queue)
		except Exception as error:
			self.logger.error('Stream channel cleanup failed: error_type=%s', type(error).__name__)
			raise
		return
	
	def __str__(self): return self.queue

	def send(
		self,
		body,
		event: Optional[str] = None,
		headers: Dict = {},
		timestamp: Optional[int] = None,
		id: Optional[str] = None,
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
		self.logger.debug('Publishing Stream message: queue=%s message_id=%s publisher_confirm=False', self.queue, id)
		try:
			self.channel.basic_publish(
				exchange='',
				routing_key=self.queue,
				properties=properties,
				body=self.encode(body)
			)
		except Exception as error:
			self.logger.error('Stream publication failed: queue=%s message_id=%s error_type=%s', self.queue, id, type(error).__name__)
			raise
		self.logger.debug('Stream publish API call completed: queue=%s message_id=%s', self.queue, id)
		return id

	def read(self, offset: int = 0, timeout: Optional[int] = None) -> Iterable[Event]:
		channel = self.channel
		self.logger.debug('Starting Stream read: queue=%s offset=%s timeout_ms=%s qos=1', self.queue, offset, timeout)
		try:
			channel.basic_qos(0, 1, False)
		except Exception as error:
			self.logger.error('Failed to apply Stream QoS: queue=%s error_type=%s', self.queue, type(error).__name__)
			raise

		deadline = time() + (timeout / 1000) if timeout else None

		failure_observed = False
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
				# pika delivers properties and body together with every non-empty method frame.
				assert properties is not None and body is not None

				try:
					decoded = self.decode(body, properties.content_type, properties.content_encoding)
				except Exception as error:
					failure_observed = True
					self.logger.error('Stream decoding failed: queue=%s delivery_tag=%s error_type=%s', self.queue, method.delivery_tag, type(error).__name__)
					raise
				self.logger.debug('Stream message received and decoded: queue=%s consumer_tag=%s delivery_tag=%s message_id=%s', self.queue, method.consumer_tag, method.delivery_tag, properties.message_id)
				event = Event(
					channel,
					self.queue,
					method.consumer_tag,
					method.delivery_tag,
					properties,
					decoded,
				)

				try:
					failure_observed = True
					yield event
					failure_observed = False
					self.logger.debug('Stream ack requested: queue=%s delivery_tag=%s', self.queue, method.delivery_tag)
					try:
						channel.basic_ack(delivery_tag=method.delivery_tag)
					except Exception as error:
						failure_observed = True
						self.logger.error('Stream ack failed: queue=%s delivery_tag=%s error_type=%s', self.queue, method.delivery_tag, type(error).__name__)
						raise
					self.logger.debug('Stream ack API call completed: queue=%s delivery_tag=%s', self.queue, method.delivery_tag)
				except Exception:
					failure_observed = True
					self.logger.warning('Attempting requeue after Stream processing exception: queue=%s delivery_tag=%s', self.queue, method.delivery_tag)
					self.logger.debug('Stream nack requested: queue=%s delivery_tag=%s requeue=True', self.queue, method.delivery_tag)
					try:
						channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
					except Exception as error:
						self.logger.error('Stream nack failed: queue=%s delivery_tag=%s error_type=%s', self.queue, method.delivery_tag, type(error).__name__)
						raise
					self.logger.debug('Stream nack API call completed: queue=%s delivery_tag=%s', self.queue, method.delivery_tag)
					raise
		except Exception as error:
			if not failure_observed:
				self.logger.error('Stream consumption loop failed: queue=%s error_type=%s', self.queue, type(error).__name__)
			raise
		finally:
			self.logger.debug('Ending Stream read loop; requesting Consumer cancellation: queue=%s', self.queue)
			try:
				channel.cancel()
			except Exception as error:
				self.logger.error('Stream Consumer cancellation failed: queue=%s error_type=%s', self.queue, type(error).__name__)
				raise
			self.logger.debug('Stream Consumer cancelled: queue=%s', self.queue)
		return
