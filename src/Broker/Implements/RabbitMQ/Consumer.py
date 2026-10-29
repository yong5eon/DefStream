# -*- coding: utf-8 -*-

from DefStream.Broker import (
	Consumer as BaseConsumer,
	EventHandler,
	Event as BaseEvent,
	EventError,
)

from .Serializer import (
	Decoder,
	Encoder,
	JavaScriptObjectNotationEncoder,
)
from logging import getLogger

from .Event import Event
from .Policies import Requeue
from .Subscription import Subscription
from typing import (
	Any,
	Callable,
	Optional,
)

from pika import (
	BasicProperties,
	BlockingConnection,
)
from pika.exceptions import UnroutableError

__all__ = (
	'Consumer'
)

class Consumer(BaseConsumer):
	"""Consumer of Event Broker for RabbitMQ"""
	logger = getLogger('DefStream.Broker.Implements.RabbitMQ.Consumer')

	def __init__(
		self,
		connection: BlockingConnection,
		decode: Decoder,
		handler: Optional[EventHandler] = None,
		qos: int = 1,
		offset: int = None,
		encode: Optional[Encoder] = None,
	):
		self.connection = connection
		self.decode = decode
		self.qos = qos
		try:
			self.channel = self.connection.channel()
			self.channel.basic_qos(
				prefetch_count=qos,
				global_qos=False,
			)
		except Exception as error:
			self.logger.error('Consumption channel initialization failed: qos=%s error_type=%s', qos, type(error).__name__)
			raise
		self.logger.debug('Consumption channel created: qos=%s offset=%s', qos, offset)
		self.channel.auto_decode = False
		self.offset = offset
		self.handler = handler
		self.encode = encode if encode is not None else JavaScriptObjectNotationEncoder()
		self.response_channel = None
		self.queues = set()
		self.stopped = False
		self.callback_error = None
		return

	def __del__(self):
		self.close()
		return

	def subs(
		self,
		queue: Any,
		handler: Optional[EventHandler] = None,
	) -> None:
		if handler is None:
			handler = self.handler
		if handler is None:
			raise ValueError('subs requires a handler or a default handler')
		if isinstance(
			queue,
			str,
		):
			subscription = Subscription(
				queue=queue,
				offset=self.offset,
			)
		else:
			subscription = Subscription.parse(queue)
		if subscription.queue in self.queues:
			raise ValueError('A Run is already subscribed to queue {}'.format(subscription.queue))
		qos = self.qos if subscription.qos is None else subscription.qos
		self.logger.debug('Applying subscription: queue=%s qos=%s offset=%s', subscription.queue, qos, subscription.offset)
		try:
			self.channel.basic_qos(
				prefetch_count=qos,
				global_qos=False,
			)
			tag = self.channel.basic_consume(
				subscription.queue,
				Callback(
					self.decode,
					handler,
					subscription.queue,
					logger=self.logger,
					owner=self,
				),
				auto_ack=False,
				exclusive=False,
				arguments={'x-stream-offset': subscription.offset} if subscription.offset is not None else None,
			)
		except Exception as error:
			self.logger.error('Subscription failed: queue=%s error_type=%s', subscription.queue, type(error).__name__)
			raise
		self.queues.add(subscription.queue)
		self.logger.debug('Subscription applied: queue=%s consumer_tag=%s', subscription.queue, tag)
		return

	def call(self, callback: Callable[[], None]) -> None:
		self.logger.debug('Scheduling callback on connection owner thread')
		try:
			self.connection.add_callback_threadsafe(callback)
		except Exception as error:
			self.logger.error('Callback scheduling failed: error_type=%s', type(error).__name__)
			raise
		self.logger.debug('Callback scheduled on connection owner thread')
		return

	def fail(
		self,
		event: BaseEvent,
		policy: Optional[EventError] = None,
	) -> None:
		self.logger.debug('Task failure policy selected: policy=%s', type(policy).__name__ if policy is not None else 'Requeue')
		if isinstance(
			event,
			Event,
		) and event.properties.reply_to:
			event = FailedRequest(
				self,
				event,
			)
		(policy if policy is not None else Requeue())(event)
		return

	def complete(
		self,
		event: BaseEvent,
		result: Any,
	) -> None:
		self.logger.debug('Task completion policy selected: ack')
		if isinstance(
			event,
			Event,
		) and event.properties.reply_to:
			self.logger.debug('Building RPC success response: queue=%s correlation_id=%s', event.queue, event.properties.correlation_id)
			self.respond(
				event,
				{
					'ok': True,
					'result': result,
				},
			)
		event.ack()
		return

	def respond(
		self,
		event: Event,
		response: Any,
	) -> None:
		if not event.properties.correlation_id:
			self.logger.error('RPC response validation failed: missing correlation_id')
			raise ValueError('RPC request requires correlation_id')
		channel = self.response_channel
		self.logger.debug('Attempting RPC response: correlation_id=%s reply_to=%s', event.properties.correlation_id, event.properties.reply_to)
		if channel is None:
			try:
				channel = self.connection.channel()
				channel.confirm_delivery()
				self.response_channel = channel
				self.logger.debug('RPC response channel created: publisher_confirm=True')
			except Exception as error:
				self.logger.error('RPC response channel creation failed: correlation_id=%s error_type=%s', event.properties.correlation_id, type(error).__name__)
				raise
		else:
			self.logger.debug('Reusing RPC response channel')
		try:
			channel.basic_publish(
				exchange='',
				routing_key=event.properties.reply_to,
				body=self.encode(response),
				properties=BasicProperties(
					correlation_id=event.properties.correlation_id,
					content_type=self.encode.format,
					content_encoding=self.encode.charset,
				),
				mandatory=True,
			)
		except UnroutableError:
			self.logger.warning(
				'RPC reply is unroutable; settling request without a response: correlation_id=%s reply_to=%s',
				event.properties.correlation_id,
				event.properties.reply_to,
			)
		except Exception as error:
			self.logger.error('RPC response publication failed: correlation_id=%s error_type=%s', event.properties.correlation_id, type(error).__name__)
			raise
		else:
			self.logger.debug('RPC response published: correlation_id=%s', event.properties.correlation_id)
		return

	def close(self) -> None:
		response_channel = getattr(self, 'response_channel', None)
		try:
			if response_channel is not None and response_channel.is_open:
				response_channel.close()
				self.logger.debug('RPC response channel closed')
			channel = getattr(self, 'channel', None)
			if channel is not None and channel.is_open:
				channel.close()
				self.logger.debug('Consumption channel closed')
		except Exception as error:
			self.logger.error('Channel close failed: error_type=%s', type(error).__name__)
			raise
		return

	def run(self):
		self.logger.debug('Starting consumption loop')
		try:
			self.channel.start_consuming()
		except Exception as error:
			# 정산 오류는 예약 콜백에서 루프로 전파되어도 Event의 기록을 재출력하지 않는다.
			owned_boundaries = (
				Event.ack.__code__,
				Event.nack.__code__,
				Event.reject.__code__,
				Consumer.respond.__code__,
				Consumer.stop.__code__,
			)
			trace = error.__traceback__
			observed = error is self.callback_error
			while trace is not None:
				if trace.tb_frame.f_code in owned_boundaries:
					observed = True
					break
				trace = trace.tb_next
			if not observed:
				self.logger.error('Consumption loop failed: error_type=%s', type(error).__name__)
			raise
		finally:
			self.callback_error = None
			self.logger.debug('Consumption loop ended')
		return

	def stop(self):
		if not self.stopped:
			self.stopped = True
			self.logger.debug('Consumption loop stop requested')
			try:
				self.channel.stop_consuming()
			except Exception as error:
				self.logger.error('Failed to stop consumption loop: error_type=%s', type(error).__name__)
				raise
			self.logger.debug('Consumption loop stopped')
		return


class FailedRequest(BaseEvent):
	def __init__(
		self,
		consumer: Consumer,
		event: Event,
	):
		self.consumer = consumer
		self.event = event

	@property
	def body(self) -> Any:
		return self.event.body

	def ack(self) -> None:
		self.event.ack()

	def nack(self) -> None:
		self.event.nack()

	def reject(self) -> None:
		self.consumer.logger.debug('Building RPC failure response: queue=%s correlation_id=%s', self.event.queue, self.event.properties.correlation_id)
		self.consumer.respond(
			self.event,
			{
				'ok': False,
				'error': {
					'code': 'ProcessingError',
					'message': 'Request processing failed',
				},
			},
		)
		self.event.reject()
		return


class Callback(object):
	def __init__(
		self,
		decode: Decoder,
		handler: EventHandler,
		queue: str,
		logger=None,
		owner=None,
	):
		self.decode = decode
		self.handler = handler
		self.queue = queue
		self.logger = logger if logger is not None else Consumer.logger
		self.owner = owner
		return
	def __call__(
		self,
		channel,
		method,
		properties,
		body,
	):
		try:
			return self.deliver(channel, method, properties, body)
		except Exception as error:
			if self.owner is not None:
				self.owner.callback_error = error
			raise

	def deliver(
		self,
		channel,
		method,
		properties,
		body,
	):
		self.logger.debug('Message received: queue=%s consumer_tag=%s delivery_tag=%s message_id=%s', self.queue, method.consumer_tag, method.delivery_tag, properties.message_id)
		try:
			decoded = self.decode(body, properties.content_type, properties.content_encoding)
		except Exception as error:
			self.logger.error('Message decoding failed: queue=%s delivery_tag=%s error_type=%s', self.queue, method.delivery_tag, type(error).__name__)
			raise
		self.logger.debug('Message decoded; dispatching to handler: queue=%s delivery_tag=%s', self.queue, method.delivery_tag)
		return self.handler(Event(
			channel,
			self.queue,
			method.consumer_tag,
			method.delivery_tag,
			properties,
			decoded,
		))
