from importlib import import_module
from json import dumps
from os import environ
from unittest import (
	TestCase,
	main,
	skipUnless,
)
from unittest.mock import (
	Mock,
	patch,
)
from uuid import uuid4

from pika import (
	BasicProperties,
)
from pika.exceptions import ChannelClosedByBroker

from DefStream.Broker.Implements.RabbitMQ import (
	Configuration,
	Connection,
	Requeue,
	Subscription,
)
from DefStream.Worker import (
	Run,
	declare,
	emit,
)


class PriorityTests(TestCase):
	def broker(self):
		broker = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
		))
		broker.connection = Mock()
		self.addCleanup(broker.close)
		return broker

	def test_subscription_default_normalization_and_mapping(self):
		for priority in (
			0,
			3,
			255,
		):
			with self.subTest(priority=priority):
				settings = {
					'queue': 'tasks',
					'priority': priority,
				}
				subscription = Subscription.parse(settings)
				self.assertEqual(
					subscription.priority,
					priority,
				)
				self.assertEqual(
					subscription.max_priority,
					255,
				)
				self.assertNotIn(
					'max_priority',
					settings,
				)
				self.assertIs(
					Subscription.parse(subscription),
					subscription,
				)
		self.assertIsNone(Subscription(
			'tasks',
			max_priority=5,
		).priority)
		self.assertIsNone(Subscription('tasks').max_priority)
		return

	def test_subscription_rejects_invalid_defaults(self):
		for value in (
			-1,
			256,
			True,
			1.5,
			'5',
		):
			with self.subTest(value=value), self.assertRaises((
				TypeError,
				ValueError,
			)):
				Subscription.parse({
					'queue': 'tasks',
					'priority': value,
				})
		with self.assertRaises(ValueError):
			Subscription(
				'tasks',
				max_priority=2,
				priority=3,
			)
		return

	def test_connection_uses_subscription_default_for_send_and_rpc(self):
		broker = self.broker()
		assert isinstance(
			broker.connection,
			Mock,
		)
		channel = broker.connection.channel.return_value
		queue = Mock()
		broker.queue = Mock(return_value=queue)
		for override in (
			None,
			0,
			5,
		):
			settings = {
				'queue': 'tasks',
				'max_priority': 5,
				'priority': 3,
			}
			broker.emit(
				{},
				settings,
				priority=override,
			)
			self.assertEqual(
				channel.basic_publish.call_args.kwargs['properties'].priority,
				3 if override is None else override,
			)
			broker.request(
				{},
				settings,
				timeout=2,
				priority=override,
			)
			queue.call.assert_called_with(
				{},
				timeout=2,
				priority=3 if override is None else override,
			)
		return

	def test_subscription_mapping_and_invalid_maximum(self):
		for value in (
			1,
			255,
		):
			self.assertEqual(
				Subscription.parse({
					'queue': 'tasks',
					'max_priority': value,
				}).max_priority,
				value,
			)
		for value in (
			0,
			-1,
			256,
			True,
			1.5,
			'5',
		):
			with self.subTest(value=value), self.assertRaises((
				TypeError,
				ValueError,
			)):
				Subscription.parse({
					'queue': 'tasks',
					'max_priority': value,
				})
		return

	def test_declaration_merges_priority_and_dead_letter_arguments(self):
		broker = self.broker()
		broker.declare(Subscription(
			'tasks',
			error='tasks.error',
			max_priority=5,
		))
		assert isinstance(
			broker.connection,
			Mock,
		)
		calls = broker.connection.channel.return_value.queue_declare.call_args_list
		self.assertEqual(
			calls[0].kwargs,
			{'durable': True},
		)
		self.assertEqual(
			calls[1].kwargs['arguments'],
			{
				'x-max-priority': 5,
				'x-dead-letter-exchange': '',
				'x-dead-letter-routing-key': 'tasks.error',
			},
		)
		return

	def test_declaration_conflict_propagates_without_deleting_queue(self):
		broker = self.broker()
		assert isinstance(
			broker.connection,
			Mock,
		)
		channel = broker.connection.channel.return_value
		channel.queue_declare.side_effect = ChannelClosedByBroker(
			406,
			'inequivalent arg x-max-priority',
		)
		with self.assertRaises(ChannelClosedByBroker):
			broker.declare(Subscription(
				'tasks',
				max_priority=5,
			))
		channel.queue_delete.assert_not_called()
		return

	def test_queue_and_exchange_send_validate_and_preserve_priority(self):
		broker = self.broker()
		for target in (
			broker.queue('tasks'),
			broker.exchange('tasks'),
		):
			assert isinstance(
				target.channel,
				Mock,
			)
			for value in (
				None,
				0,
				255,
			):
				target.send(
					{},
					priority=value,
				)
				self.assertEqual(
					target.channel.basic_publish.call_args.kwargs['properties'].priority,
					value,
				)
			target.channel.basic_publish.reset_mock()
			for value in (
				-1,
				256,
				True,
				'5',
			):
				with self.subTest(value=value), self.assertRaises((
					TypeError,
					ValueError,
				)):
					target.send(
						{},
						priority=value,  # pyright: ignore[reportArgumentType]
					)
			target.channel.basic_publish.assert_not_called()
		return

	@patch.object(
		import_module('DefStream.Broker.Implements.RabbitMQ.Queue'),
		'BlockingConnection',
	)
	def test_rpc_publication_preserves_priority_and_metadata(
		self,
		connect,
	):
		broker = self.broker()
		queue = broker.queue('tasks')
		channel = connect.return_value.channel.return_value

		def respond(
			**kwargs,
		):
			properties = channel.basic_publish.call_args.kwargs['properties']
			callback = channel.basic_consume.call_args.kwargs['on_message_callback']
			callback(
				channel,
				Mock(),
				BasicProperties(
					correlation_id=properties.correlation_id,
					content_type='application/json',
					content_encoding='utf-8',
				),
				dumps({
					'ok': True,
					'result': 7,
				}).encode(),
			)
			return

		connect.return_value.process_data_events.side_effect = respond
		for priority in (
			None,
			0,
			255,
		):
			self.assertEqual(
				queue.call(
					{'value': 7},
					priority=priority,
				),
				7,
			)
			properties = channel.basic_publish.call_args.kwargs['properties']
			self.assertEqual(
				properties.priority,
				priority,
			)
			self.assertIsNotNone(properties.reply_to)
			self.assertIsNotNone(properties.correlation_id)
			self.assertIsNotNone(properties.expiration)
			connect.return_value.close.assert_called()
		connect.reset_mock()
		for value in (
			-1,
			256,
			True,
		):
			with self.assertRaises((
				TypeError,
				ValueError,
			)):
				queue.call(
					{},
					priority=value,
				)
		connect.assert_not_called()
		return


@skipUnless(
	environ.get('DEFSTREAM_RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ integration',
)
class PriorityIntegrationTests(TestCase):
	def test_delivery_order_fifo_requeue_and_declaration_conflict(self):
		broker = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username=environ.get(
				'DEFSTREAM_RABBITMQ_USERNAME',
				'guest',
			),
			password=environ.get(
				'DEFSTREAM_RABBITMQ_PASSWORD',
				'guest',
			),
		))
		broker.connect()
		name = 'defstream-priority-' + uuid4().hex

		class Task(
			Run,
			parameters=Subscription(
				name,
				max_priority=5,
				qos=1,
				priority=1,
			),
		):
			def run(
				self,
				**kwargs,
			):
				return kwargs

		try:
			declare(
				task=Task,
				broker=broker,
			)
			for label, priority in (
				(
					'low',
					1,
				),
				(
					'high-first',
					5,
				),
				(
					'high-second',
					5,
				),
				(
					'middle',
					3,
				),
			):
				emit(
					{'label': label},
					task=Task,
					broker=broker,
					priority=priority,
				)
			queue = broker.queue(name)
			for label in (
				'high-first',
				'high-second',
				'middle',
				'low',
			):
				event = queue.pop(timeout=5000)
				if event is None:
					self.fail('Priority delivery timed out')
				self.assertEqual(
					event.body['label'],
					label,
				)
				event.ack()
			emit(
				{'label': 'retry'},
				task=Task,
				broker=broker,
				priority=4,
			)
			event = queue.pop(timeout=5000)
			if event is None:
				self.fail('Initial requeue delivery timed out')
			Requeue()(event)
			retry = queue.pop(timeout=5000)
			if retry is None:
				self.fail('Requeued delivery timed out')
			self.assertEqual(
				retry.priority,
				4,
			)
			retry.ack()
			with self.assertRaises(ChannelClosedByBroker):
				broker.declare(Subscription(
					name,
					max_priority=4,
				))
			self.assertTrue(broker.connected().is_open)
		finally:
			broker.delete_queue(name)
			broker.close()
		return


if __name__ == '__main__':
	main()
