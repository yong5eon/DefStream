# -*- coding: utf-8 -*-

from ...Event import (
	Event as BaseEvent,
	EventHandler as BaseEventHandler,
)

from abc import abstractmethod

__all__ = (
	'Event',
	'EventHandler',
)


class Event(BaseEvent):
	"""Event of Event Broker for RabbitMQ"""
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
		self.props = properties.headers
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
		self.channel.basic_ack(self.transaction)
		return

	def nack(self):
		self.channel.basic_nack(
			self.transaction,
			requeue=True,
		)
		return

	def reject(self):
		self.channel.basic_reject(
			self.transaction,
			requeue=False,
		)
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
