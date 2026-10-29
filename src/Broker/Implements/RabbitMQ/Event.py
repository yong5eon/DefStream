# -*- coding: utf-8 -*-

from DefStream.Broker import (
	Event as BaseEvent,
	EventHandler as BaseEventHandler,
)

from abc import abstractmethod
from logging import getLogger

__all__ = (
	'Event',
	'EventHandler',
)


class Event(BaseEvent):
	"""Event of Event Broker for RabbitMQ"""
	logger = getLogger('DefStream.Broker.RabbitMQ.Event')

	def __init__(
		self,
		channel,
		queue,
		consumer,
		transaction,
		properties,
		body,
	):
		self.channel = channel
		self.queue = queue
		self.consumer = consumer
		self.transaction = transaction
		self.properties = properties
		self.props = properties.headers or {}
		self.payload = body
		return

	def __repr__(self):
		return 'Event(id={}, body={}, type={}, headers={})'.format(
			self.properties.message_id,
			self.payload,
			self.properties.type,
			self.props,
		)

	def ack(self):
		self.logger.debug('ack requested: queue=%s delivery_tag=%s message_id=%s', self.queue, self.transaction, self.id)
		try:
			self.channel.basic_ack(self.transaction)
		except Exception as error:
			self.logger.error('ack failed: queue=%s delivery_tag=%s error_type=%s', self.queue, self.transaction, type(error).__name__)
			raise
		self.logger.debug('ack broker API call completed: queue=%s delivery_tag=%s', self.queue, self.transaction)
		return

	def nack(self):
		self.logger.debug('nack requested: queue=%s delivery_tag=%s message_id=%s requeue=True', self.queue, self.transaction, self.id)
		try:
			self.channel.basic_nack(
				self.transaction,
				requeue=True,
			)
		except Exception as error:
			self.logger.error('nack failed: queue=%s delivery_tag=%s error_type=%s', self.queue, self.transaction, type(error).__name__)
			raise
		self.logger.debug('nack broker API call completed: queue=%s delivery_tag=%s', self.queue, self.transaction)
		return

	def reject(self):
		self.logger.debug('reject requested: queue=%s delivery_tag=%s message_id=%s requeue=False', self.queue, self.transaction, self.id)
		try:
			self.channel.basic_reject(
				self.transaction,
				requeue=False,
			)
		except Exception as error:
			self.logger.error('reject failed: queue=%s delivery_tag=%s error_type=%s', self.queue, self.transaction, type(error).__name__)
			raise
		self.logger.debug('reject broker API call completed: queue=%s delivery_tag=%s', self.queue, self.transaction)
		return

	def headers(self):
		return self.props

	def header(
		self,
		key,
	):
		if key not in self.props:
			return None
		return self.props[key]

	@property
	def src(self):
		return self.queue

	@property
	def id(self):
		return self.properties.message_id

	@property
	def type(self):
		return self.properties.type

	@property
	def body(self):
		return self.payload
	
	@property
	def priority(self):
		if not hasattr(
			self.properties,
			'priority',
		):
			return None
		return self.properties.priority


class EventHandler(BaseEventHandler):
	"""Event Handler Interface of Event Broker for RabbitMQ"""
	@abstractmethod
	def __call__(
		self,
		event: Event,
	):
		raise NotImplementedError('{} must be implemented __call__'.format(self.__class__.__name__))
