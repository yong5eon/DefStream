# -*- coding: utf-8 -*-

from ... import (
	Consumer as BaseConsumer,
	EventHandler,
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
from ...Event import (
	Event as BaseEvent,
	EventError,
)
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

logger = getLogger(__name__)


class Consumer(BaseConsumer):
	"""Consumer of Event Broker for RabbitMQ"""
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
		self.channel = self.connection.channel()
		self.qos = qos
		self.channel.basic_qos(
			prefetch_count=qos,
			global_qos=False,
		)
		self.channel.auto_decode = False
		self.offset = offset
		self.handler = handler
		self.encode = encode if encode is not None else JavaScriptObjectNotationEncoder()
		self.response_channel = None
		self.queues = set()
		self.stopped = False
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
		self.channel.basic_qos(
			prefetch_count=self.qos if subscription.qos is None else subscription.qos,
			global_qos=False,
		)
		self.channel.basic_consume(
			subscription.queue,
			Callback(
				self.decode,
				handler,
				subscription.queue,
			),
			auto_ack=False,
			exclusive=False,
			arguments={'x-stream-offset': subscription.offset} if subscription.offset is not None else None,
		)
		self.queues.add(subscription.queue)

	def call(self, callback: Callable[[], None]) -> None:
		self.connection.add_callback_threadsafe(callback)

	def fail(
		self,
		event: BaseEvent,
		policy: Optional[EventError] = None,
	) -> None:
		if isinstance(
			event,
			Event,
		) and event.properties.reply_to:
			event = FailedRequest(
				self,
				event,
			)
		(policy if policy is not None else Requeue())(event)

	def complete(
		self,
		event: BaseEvent,
		result: Any,
	) -> None:
		if isinstance(
			event,
			Event,
		) and event.properties.reply_to:
			self.respond(
				event,
				{
					'ok': True,
					'result': result,
				},
			)
		event.ack()

	def respond(
		self,
		event: Event,
		response: Any,
	) -> None:
		if not event.properties.correlation_id:
			raise ValueError('RPC request requires correlation_id')
		channel = self.response_channel
		if channel is None:
			channel = self.connection.channel()
			channel.confirm_delivery()
			self.response_channel = channel
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
			logger.warning(
				'RPC reply is unroutable; settling request without a response: correlation_id=%s reply_to=%s',
				event.properties.correlation_id,
				event.properties.reply_to,
			)

	def close(self) -> None:
		response_channel = getattr(self, 'response_channel', None)
		if response_channel is not None and response_channel.is_open:
			response_channel.close()
		channel = getattr(self, 'channel', None)
		if channel is not None and channel.is_open:
			channel.close()

	def run(self):
		self.channel.start_consuming()
		return

	def stop(self):
		if not self.stopped:
			self.stopped = True
			self.channel.stop_consuming()
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


class Callback(object):
	def __init__(self, decode: Decoder, handler: EventHandler, queue: str):
		self.decode = decode
		self.handler = handler
		self.queue = queue
		return
	def __call__(self, channel, method, properties, body):
		return self.handler(Event(
			channel,
			self.queue,
			method.consumer_tag,
			method.delivery_tag,
			properties,
			self.decode(body, properties.content_type, properties.content_encoding),
		))
