from datetime import timedelta
from unittest import TestCase
from unittest.mock import (
	Mock,
	call,
	patch,
)

from pika.exceptions import ChannelClosedByBroker

from DefStream.Broker.Implements.RabbitMQ import (
	Configuration,
	Connection,
	Consumer,
	Subscription,
)
from DefStream.Worker import (
	Run,
	declare,
)
from _support import require_instance


class TimeoutTests(TestCase):
	def broker(self) -> Connection:
		broker: Connection = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		))
		broker.connection = Mock()
		self.addCleanup(broker.close)
		return broker

	def test_object_mapping_and_exact_millisecond_conversion(self) -> None:
		for duration, milliseconds in (
			(
				timedelta(hours=24),
				86400000,
			),
			(
				86400000,
				86400000,
			),
			(
				1,
				1,
			),
			(
				60123,
				60123,
			),
			(
				timedelta(milliseconds=1),
				1,
			),
			(
				timedelta(
					seconds=60,
					milliseconds=123,
				),
				60123,
			),
			(
				timedelta(
					days=999999999,
					milliseconds=999,
				),
				86399999913600999,
			),
		):
			for parameters in (
				Subscription('tasks', timeout=duration),
				{
					'queue': 'tasks',
					'timeout': duration,
				},
			):
				with self.subTest(duration=duration, parameters=parameters):
					subscription: Subscription = Subscription.parse(parameters)
					self.assertEqual(
						subscription.timeout,
						milliseconds,
					)
					self.assertIs(type(subscription.timeout), int)
					if isinstance(parameters, dict):
						self.assertEqual(parameters['timeout'], duration)
					self.assertIs(
						Subscription.parse(subscription),
						subscription,
					)
					broker: Connection = self.broker()
					connection: Mock = require_instance(broker.connection, Mock)
					broker.declare(parameters)
					connection.channel.return_value.queue_declare.assert_called_once_with(
						'tasks',
						durable=True,
						arguments={'x-consumer-timeout': milliseconds},
					)
					self.assertIs(
						type(connection.channel.return_value.queue_declare.call_args.kwargs['arguments']['x-consumer-timeout']),
						int,
					)
		return

	def test_omitted_and_none_preserve_existing_arguments(self) -> None:
		for parameters in (
			Subscription('tasks'),
			Subscription('tasks', timeout=None),
			{'queue': 'tasks'},
			{
				'queue': 'tasks',
				'timeout': None,
			},
		):
			with self.subTest(parameters=parameters):
				broker: Connection = self.broker()
				connection: Mock = require_instance(broker.connection, Mock)
				broker.declare(parameters)
				connection.channel.return_value.queue_declare.assert_called_once_with(
					'tasks',
					durable=True,
					arguments={},
				)
		return

	def test_existing_positional_fields_are_unchanged(self) -> None:
		subscription: Subscription = Subscription(
			'tasks',
			7,
			4,
			'tasks.error',
			5,
			2,
		)
		self.assertEqual(
			(
				subscription.offset,
				subscription.qos,
				subscription.error,
				subscription.max_priority,
				subscription.priority,
			),
			(
				7,
				4,
				'tasks.error',
				5,
				2,
			),
		)
		self.assertIsNone(subscription.timeout)
		return

	def test_timeout_merges_with_dead_letter_and_priority(self) -> None:
		broker: Connection = self.broker()
		connection: Mock = require_instance(broker.connection, Mock)
		broker.declare(Subscription(
			'tasks',
			error='tasks.error',
			max_priority=5,
			timeout=timedelta(hours=24),
		))
		self.assertEqual(
			connection.channel.return_value.queue_declare.call_args_list,
			[
				call('tasks.error', durable=True),
				call(
					'tasks',
					durable=True,
					arguments={
						'x-dead-letter-exchange': '',
						'x-dead-letter-routing-key': 'tasks.error',
						'x-max-priority': 5,
						'x-consumer-timeout': 86400000,
					},
				),
			],
		)
		return

	def test_invalid_timeouts_fail_before_io(self) -> None:
		for value in (
			True,
			False,
			0,
			-1,
			60.0,
			'24h',
			timedelta(0),
			timedelta(seconds=-1),
			timedelta(microseconds=1),
			timedelta(
				seconds=60,
				microseconds=1,
			),
		):
			with self.subTest(value=value):
				broker: Connection = self.broker()
				connection: Mock = require_instance(broker.connection, Mock)
				error: type[Exception] = ValueError if isinstance(value, (
					int,
					timedelta,
				)) and not isinstance(value, bool) else TypeError
				with self.assertRaises(error):
					broker.declare({
						'queue': 'tasks',
						'timeout': value,
					})
				connection.channel.assert_not_called()
		return

	def test_worker_declare_passes_timeout(self) -> None:
		class Task(
			Run,
			parameters=Subscription(
				'tasks',
				timeout=timedelta(hours=24),
			),
		):
			def run(self) -> None:
				return

		broker: Connection = self.broker()
		connection: Mock = require_instance(broker.connection, Mock)
		declare(
			task=Task,
			broker=broker,
		)
		connection.channel.return_value.queue_declare.assert_called_once_with(
			'tasks',
			durable=True,
			arguments={'x-consumer-timeout': 86400000},
		)
		return

	def test_subscription_does_not_declare_or_pass_timeout_to_consume(self) -> None:
		connection: Mock = Mock()
		consumer: Consumer = Consumer(
			connection,
			Mock(),
			Mock(),
		)
		self.addCleanup(consumer.close)
		consumer.subs(Subscription('tasks', timeout=timedelta(hours=24)))
		connection.channel.return_value.queue_declare.assert_not_called()
		self.assertIsNone(connection.channel.return_value.basic_consume.call_args.kwargs['arguments'])
		self.assertFalse(connection.channel.return_value.basic_consume.call_args.kwargs['auto_ack'])
		return

	def test_rpc_wait_timeout_is_independent(self) -> None:
		broker: Connection = self.broker()
		with patch.object(broker, 'queue') as queue:
			broker.request(
				{},
				Subscription('tasks', timeout=timedelta(hours=24)),
				timeout=2,
			)
			queue.return_value.call.assert_called_once_with(
				{},
				timeout=2,
			)
		return

	def test_declaration_error_propagates_without_queue_changes(self) -> None:
		broker: Connection = self.broker()
		connection: Mock = require_instance(broker.connection, Mock)
		channel: Mock = connection.channel.return_value
		channel.queue_declare.side_effect = ChannelClosedByBroker(
			406,
			'queue declaration failed',
		)
		with self.assertRaises(ChannelClosedByBroker):
			broker.declare(Subscription('tasks', timeout=timedelta(hours=24)))
		channel.queue_delete.assert_not_called()
		channel.close.assert_called_once()
		return
