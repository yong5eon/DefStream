from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock
from unittest.mock import call

from DefStream.Broker import Event as BaseEvent
from DefStream.Broker.Implements.RabbitMQ import (
	Consumer,
	Event,
	Requeue,
	Reject,
	Subscription,
)
from _support import call_with_invalid_input


class SubscriptionTests(TestCase):
	def test_optional_error_queue_metadata(self):
		self.assertIsNone(Subscription('queue').error)
		parameters = Subscription(
			'queue',
			7,
			4,
			error='queue.error',
		)
		self.assertEqual(
			parameters.offset,
			7,
		)
		self.assertEqual(
			parameters.qos,
			4,
		)
		self.assertIs(
			Subscription.parse(parameters),
			parameters,
		)
		self.assertEqual(
			Subscription.parse({
				'queue': 'queue',
				'error': 'queue.error',
			}).error,
			'queue.error',
		)
		for value in (
			'',
			False,
			1,
		):
			with self.subTest(value=value), self.assertRaises(ValueError):
				call_with_invalid_input(
					Subscription,
					'queue',
					error=value,
				)

		connection = Mock()
		consumer = Consumer(
			connection,
			Mock(),
			Mock(),
		)
		consumer.subs(parameters)
		channel = connection.channel.return_value
		channel.queue_declare.assert_not_called()
		channel.queue_bind.assert_not_called()
		channel.basic_consume.assert_called_once()

	def test_queue_name_preserves_defaults_and_explicit_handler_takes_precedence(self):
		connection = Mock()
		default = Mock()
		override = Mock()
		consumer = Consumer(
			connection,
			Mock(),
			default,
			qos=4,
			offset=7,
		)
		consumer.subs(queue='first')
		channel = connection.channel.return_value
		registration = channel.basic_consume.call_args
		self.assertIs(
			registration.args[1].handler,
			default,
		)
		self.assertEqual(
			registration.kwargs['arguments'],
			{'x-stream-offset': 7},
		)
		consumer.subs(
			'second',
			override,
		)
		self.assertIs(
			channel.basic_consume.call_args.args[1].handler,
			override,
		)
		channel.basic_qos.assert_called_with(
			prefetch_count=4,
			global_qos=False,
		)
		with self.assertRaises(ValueError):
			consumer.subs('first')

	def test_prefetch_is_set_before_each_subscription_and_defaults_do_not_leak(self):
		connection = Mock()
		consumer = Consumer(
			connection,
			Mock(),
			Mock(),
			qos=3,
		)
		channel = connection.channel.return_value
		channel.reset_mock()
		for parameters in (
			Subscription(
				queue='first',
				qos=10,
			),
			{
				'queue': 'second',
				'qos': 0,
			},
			Subscription('third'),
		):
			consumer.subs(
				parameters,
				Mock(),
			)
		self.assertEqual(
			channel.basic_qos.call_args_list,
			[
				call(
					prefetch_count=10,
					global_qos=False,
				),
				call(
					prefetch_count=0,
					global_qos=False,
				),
				call(
					prefetch_count=3,
					global_qos=False,
				),
			],
		)
		self.assertEqual(
			[item[0] for item in channel.method_calls],
			[
				'basic_qos',
				'basic_consume',
				'basic_qos',
				'basic_consume',
				'basic_qos',
				'basic_consume',
			],
		)
		consumer.subs('legacy')
		channel.basic_qos.assert_called_with(
			prefetch_count=3,
			global_qos=False,
		)

	def test_invalid_qos_is_rejected(self):
		for value in (
			-1,
			65536,
			True,
			1.5,
			'10',
		):
			with self.subTest(value=value), self.assertRaises(ValueError):
				call_with_invalid_input(
					Subscription,
					queue='queue',
					qos=value,
				)
		for value in (
			None,
			0,
			1,
			65535,
		):
			self.assertEqual(
				Subscription(
					queue='queue',
					qos=value,
				).qos,
				value,
			)

	def test_consumer_without_default_handler_uses_subscription_handler(self):
		connection = Mock()
		consumer = Consumer(
			connection,
			Mock(),
		)
		handler = Mock()
		consumer.subs(
			Subscription('queue'),
			handler,
		)
		callback = connection.channel.return_value.basic_consume.call_args.args[1]
		self.assertIs(
			callback.handler,
			handler,
		)
		with self.assertRaisesRegex(
			ValueError,
			'default handler',
		):
			consumer.subs('other')

	def test_rabbitmq_event_implements_common_event(self):
		properties = Mock()
		properties.message_id = 'message'
		properties.type = 'sample'
		event = Event(
			Mock(),
			'queue',
			'consumer',
			42,
			properties,
			{'value': 1},
		)
		self.assertIn(
			BaseEvent,
			Event.__mro__,
		)
		self.assertEqual(
			event.body,
			{'value': 1},
		)
		self.assertEqual(
			event.src,
			'queue',
		)
		self.assertEqual(
			event.id,
			'message',
		)
		self.assertEqual(
			event.type,
			'sample',
		)

	def test_dict_and_dataclass_subscriptions(self):
		connection = Mock()
		consumer = Consumer(connection, Mock(), Mock())
		first, second = Mock(), Mock()
		consumer.subs(
			{'queue': 'first'},
			first,
		)
		consumer.subs(
			Subscription(
				'second',
				offset=0,
			),
			second,
		)
		calls = connection.channel.return_value.basic_consume.call_args_list
		self.assertEqual(calls[0].args[0], 'first')
		self.assertIs(calls[0].args[1].handler, first)
		self.assertEqual(calls[1].kwargs['arguments'], {'x-stream-offset': 0})
		self.assertIs(calls[1].args[1].handler, second)
		with self.assertRaisesRegex(ValueError, 'already subscribed'):
			consumer.subs(
				{'queue': 'first'},
				second,
			)

	def test_invalid_settings_are_not_silently_ignored(self):
		for parameters in ({'queue': ''}, {'queue': 'q', 'queue.error': 'errors'}, 'q'):
			with self.subTest(parameters=parameters), self.assertRaises((TypeError, ValueError)):
				Subscription.parse(parameters)

	def test_callback_scheduling_and_repeat_stop(self):
		connection = Mock()
		consumer = Consumer(connection, Mock(), Mock())
		callback = Mock()
		consumer.call(callback)
		connection.add_callback_threadsafe.assert_called_once_with(callback)
		callback.assert_not_called()
		consumer.stop()
		consumer.stop()
		connection.channel.return_value.stop_consuming.assert_called_once_with()

	def test_policies_use_the_expected_protocol_operations(self):
		channel = Mock()
		event = Event(channel, 'queue', 'consumer', 42, Mock(), {})
		Requeue()(event)
		channel.basic_nack.assert_called_once_with(42, requeue=True)
		Reject()(event)
		channel.basic_reject.assert_called_once_with(42, requeue=False)
		event.ack()
		channel.basic_ack.assert_called_once_with(42)


if __name__ == '__main__':
	main()
