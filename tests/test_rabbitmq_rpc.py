from importlib import import_module
from json import (
	dumps,
	loads,
)
from typing import List
from unittest import (
	TestCase,
	main,
)
from unittest.mock import (
	Mock,
	patch,
)

from pika import (
	BasicProperties,
	ConnectionParameters,
)
from pika.exceptions import UnroutableError

from DefStream.Broker import (
	Callable,
	RemoteError,
)
from DefStream.Broker.Implements.RabbitMQ import (
	Consumer,
	Event,
	Exchange,
	Queue,
	Reject,
	Requeue,
)
from DefStream.Broker.Implements.RabbitMQ.Serializer import (
	JavaScriptObjectNotationDecoder,
	JavaScriptObjectNotationEncoder,
)
from _support import call_with_invalid_input


class RpcTests(TestCase):
	@patch.object(
		import_module('DefStream.Broker.Implements.RabbitMQ.Exchange'),
		'BlockingConnection',
	)
	def test_queue_and_exchange_inherit_callable_and_exchange_routes_rpc(
		self,
		connect,
	):
		self.assertIn(
			Callable,
			Queue.__bases__,
		)
		self.assertIn(
			Callable,
			Exchange.__bases__,
		)
		parameters = ConnectionParameters()
		encode = JavaScriptObjectNotationEncoder()
		decode = JavaScriptObjectNotationDecoder()
		exchange = Exchange(
			Mock(),
			encode,
			'operations',
			decode=decode,
			rpc_parameters=parameters,
		)
		channel = connect.return_value.channel.return_value

		def respond(**kwargs):
			callback = channel.basic_consume.call_args.kwargs['on_message_callback']
			request = channel.basic_publish.call_args.kwargs['properties']
			callback(
				channel,
				Mock(),
				BasicProperties(
					correlation_id=request.correlation_id,
					content_type='application/json',
					content_encoding='utf-8',
				),
				dumps({
					'ok': True,
					'result': 3,
				}).encode(),
			)

		connect.return_value.process_data_events.side_effect = respond
		self.assertEqual(
			exchange.call(
				{'a': 1},
				timeout=2,
				event='add',
			),
			3,
		)
		self.assertEqual(
			channel.basic_publish.call_args.kwargs['routing_key'],
			'add',
		)
		self.assertEqual(
			channel.basic_publish.call_args.kwargs['exchange'],
			'operations',
		)
		exchange.call({})
		self.assertEqual(
			channel.basic_publish.call_args.kwargs['routing_key'],
			'',
		)

	def test_send_preserves_rpc_metadata(self):
		connection = Mock()
		queue = Queue(
			connection,
			JavaScriptObjectNotationEncoder(),
			JavaScriptObjectNotationDecoder(),
			'requests',
		)
		queue.send(
			{'a': 1},
			reply_to='responses',
			correlation_id='id',
		)
		properties = connection.channel.return_value.basic_publish.call_args.kwargs['properties']
		self.assertEqual(
			properties.reply_to,
			'responses',
		)
		self.assertEqual(
			properties.correlation_id,
			'id',
		)

	def request(self):
		return Event(
			Mock(),
			'request',
			'consumer',
			1,
			BasicProperties(
				reply_to='response',
				correlation_id='correlation',
			),
			{},
		)

	def consumer(self):
		connection = Mock()
		self.connection = connection
		return Consumer(
			connection,
			JavaScriptObjectNotationDecoder(),
		)

	def test_response_published_before_ack_including_none(self):
		for result in (
			None,
			{'value': 3},
		):
			consumer = self.consumer()
			event = self.request()
			trace = []
			channel = self.connection.channel.return_value
			channel.basic_publish.side_effect = lambda **kwargs: trace.append('response')
			event.channel.basic_ack.side_effect = lambda *args: trace.append('ack')
			consumer.complete(
				event,
				result,
			)
			self.assertEqual(
				trace,
				[
					'response',
					'ack',
				],
			)
			channel.confirm_delivery.assert_called_once_with()
			message = channel.basic_publish.call_args.kwargs
			self.assertEqual(
				loads(message['body']),
				{
					'ok': True,
					'result': result,
				},
			)
			self.assertTrue(message['mandatory'])
			self.assertEqual(
				message['properties'].correlation_id,
				'correlation',
			)

	def test_no_response_when_not_rpc(self):
		consumer = self.consumer()
		event = self.request()
		event.properties.reply_to = None
		consumer.complete(
			event,
			3,
		)
		self.assertIsNone(consumer.response_channel)
		event.channel.basic_ack.assert_called_once_with(1)

	def test_missing_correlation_does_not_ack(self):
		consumer = self.consumer()
		event = self.request()
		event.properties.correlation_id = None
		with self.assertRaisesRegex(
			ValueError,
			'correlation_id',
		):
			consumer.complete(
				event,
				3,
			)
		event.channel.basic_ack.assert_not_called()

	def test_publish_failure_does_not_ack_or_reject(self):
		consumer = self.consumer()
		event = self.request()
		self.connection.channel.return_value.basic_publish.side_effect = RuntimeError('publish failed')
		for operation in (
			lambda: consumer.complete(
				event,
				3,
			),
			lambda: consumer.fail(
				event,
				Reject(),
			),
		):
			with self.assertRaisesRegex(
				RuntimeError,
				'publish failed',
			):
				operation()
		event.channel.basic_ack.assert_not_called()
		event.channel.basic_reject.assert_not_called()

	def test_requeue_has_no_response_reject_responds_first(self):
		consumer = self.consumer()
		event = self.request()
		consumer.fail(
			event,
			Requeue(),
		)
		self.assertIsNone(consumer.response_channel)
		event.channel.basic_nack.assert_called_once()
		trace = []
		channel = self.connection.channel.return_value
		channel.basic_publish.side_effect = lambda **kwargs: trace.append('response')
		event.channel.basic_reject.side_effect = lambda *args, **kwargs: trace.append('reject')
		consumer.fail(
			event,
			Reject(),
		)
		self.assertEqual(
			trace,
			[
				'response',
				'reject',
			],
		)
		self.assertFalse(loads(channel.basic_publish.call_args.kwargs['body'])['ok'])

	def test_missing_reply_destination_is_logged_and_request_settled(self):
		consumer = self.consumer()
		event = self.request()
		self.connection.channel.return_value.basic_publish.side_effect = UnroutableError([])
		with self.assertLogs(
			'Broker.RabbitMQ.Consumer',
			level='WARNING',
		):
			consumer.complete(
				event,
				3,
			)
			consumer.fail(
				event,
				Reject(),
			)
		event.channel.basic_ack.assert_called_once_with(1)
		event.channel.basic_reject.assert_called_once()

class QueueClientTests(TestCase):
	client_class = Queue

	def setUp(self):
		connection = patch.object(
			import_module(self.client_class.__module__),
			'BlockingConnection',
		)
		self.connect = connection.start()
		self.addCleanup(connection.stop)

	def invoke(
		self,
		timeout=1,
	):
		client = self.client_class(
			connection=Mock(),
			encode=JavaScriptObjectNotationEncoder(),
			decode=JavaScriptObjectNotationDecoder(),
			name='requests',
			rpc_parameters=ConnectionParameters(),
		)
		return client.call(
			{'value': 1},
			timeout,
		)

	def test_reply_matching_and_connection_closed(self):
		connect = self.connect
		connection = connect.return_value
		channel = connection.channel.return_value
		reply_queues: List[str] = []

		def declare_reply_queue(
			*,
			queue: str,
			exclusive: bool,
			auto_delete: bool,
		) -> Mock:
			declaration: Mock = Mock()
			declaration.method.queue = queue if queue else 'amq.gen-test'
			reply_queues.append(declaration.method.queue)
			return declaration

		channel.queue_declare.side_effect = declare_reply_queue

		def respond(**kwargs):
			callback = channel.basic_consume.call_args.kwargs['on_message_callback']
			request = channel.basic_publish.call_args.kwargs['properties']
			for correlation in (
				'other-request',
				request.correlation_id,
			):
				callback(
					channel,
					Mock(),
					BasicProperties(
						correlation_id=correlation,
						content_type='application/json',
						content_encoding='utf-8',
					),
					dumps({
						'ok': True,
						'result': 7,
					}).encode(),
				)

		connection.process_data_events.side_effect = respond
		self.assertEqual(
			self.invoke(),
			7,
		)
		connection.close.assert_called_once_with()
		queue_declaration = channel.queue_declare.call_args.kwargs
		if self.client_class is Queue:
			self.assertRegex(
				queue_declaration['queue'],
				r'^requests\.[0-9a-f]{32}$',
			)
		else:
			self.assertEqual(
				queue_declaration['queue'],
				'',
			)
		self.assertTrue(queue_declaration['exclusive'])
		self.assertTrue(queue_declaration['auto_delete'])
		properties = channel.basic_publish.call_args.kwargs['properties']
		self.assertEqual(
			channel.basic_consume.call_args.args[0],
			reply_queues[0],
		)
		self.assertEqual(
			properties.reply_to,
			reply_queues[0],
		)
		self.assertTrue(channel.basic_publish.call_args.kwargs['mandatory'])

	def test_timeout_closes_connection(self):
		with self.assertRaises(TimeoutError):
			call_with_invalid_input(self.invoke, timeout=0.001)
		self.connect.return_value.close.assert_called_once_with()

	def test_invalid_timeouts(self):
		for timeout in (
			0,
			-1,
			True,
			'1',
			float('nan'),
			float('inf'),
		):
			with self.subTest(timeout=timeout), self.assertRaises(ValueError):
				call_with_invalid_input(self.invoke, timeout)

	def test_remote_error_and_invalid_response(self):
		connect = self.connect
		connection = connect.return_value
		channel = connection.channel.return_value
		for response, exception in (
			(
				{
					'ok': False,
					'error': {
						'code': 'ProcessingError',
						'message': 'Request processing failed',
					},
				},
				RemoteError,
			),
			(
				{'ok': 'true'},
				ValueError,
			),
			(
				{'ok': True},
				ValueError,
			),
			(
				{
					'ok': False,
					'error': {},
				},
				ValueError,
			),
		):
			def respond(**kwargs):
				callback = channel.basic_consume.call_args.kwargs['on_message_callback']
				request = channel.basic_publish.call_args.kwargs['properties']
				callback(
					channel,
					Mock(),
					BasicProperties(
						correlation_id=request.correlation_id,
						content_type='application/json',
						content_encoding='utf-8',
					),
					dumps(response).encode(),
				)

			connection.process_data_events.side_effect = respond
			with self.subTest(response=response), self.assertRaises(exception):
				self.invoke()
		self.assertEqual(
			connection.close.call_count,
			4,
		)


class ExchangeClientTests(QueueClientTests):
	client_class = Exchange


if __name__ == '__main__':
	main()
