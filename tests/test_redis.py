from importlib import import_module
from threading import (
	Thread,
	get_ident,
)
from unittest import (
	TestCase,
	main,
)
from unittest.mock import (
	Mock,
	patch,
)

from redis.exceptions import ResponseError

from DefStream.Broker.Implements.Redis import (
	Connection,
	Configuration,
	ConnectionType,
	Consumer,
	Event,
	Queue,
	Reject,
	Subscription,
)
from DefStream.Broker.Implements.Redis.Serializer import (
	JavaScriptObjectNotationDecoder,
	JavaScriptObjectNotationEncoder,
)


class RedisTests(TestCase):
	def setUp(self):
		self.connection = Mock()
		self.encode = JavaScriptObjectNotationEncoder()
		self.decode = JavaScriptObjectNotationDecoder()
		self.queue = Queue(
			self.connection,
			self.encode,
			self.decode,
			'test',
		)

	def test_connect_lifecycle_and_connection_errors(self):
		broker = Connection(Configuration(password='secret'))
		with self.assertRaises(RuntimeError):
			broker.queue('test')
		with patch.object(
			import_module('DefStream.Broker.Implements.Redis.Connection'),
			'Redis',
		) as client:
			client.return_value = self.connection
			broker.connect()
			broker.connect()
			self.assertEqual(
				client.call_count,
				1,
			)
			self.connection.ping.assert_called_once()
			self.assertEqual(
				client.call_args.kwargs['password'],
				'secret',
			)
			self.assertFalse(hasattr(
				broker,
				'exchange',
			))
			broker.close()
			broker.close()
			self.connection.close.assert_called_once()
			self.connection.ping.side_effect = ConnectionError('unavailable')
			with self.assertRaises(ConnectionError):
				broker.connect()
			self.assertIsNone(broker.connection)

	def test_cluster_configuration(self):
		with self.assertRaises(ValueError):
			Configuration(
				type=ConnectionType.Cluster,
				database=1,
			)
		broker = Connection(Configuration(type=ConnectionType.Cluster))
		with patch.object(
			import_module('DefStream.Broker.Implements.Redis.Connection'),
			'RedisCluster',
		) as client:
			broker.connect()
			client.return_value.ping.assert_called_once()
			broker.close()

	def test_group_creation_only_ignores_busygroup(self):
		self.connection.xgroup_create.side_effect = ResponseError('BUSYGROUP Consumer Group name already exists')
		self.queue.create_group()
		self.connection.xgroup_create.side_effect = ResponseError('WRONGTYPE Operation against a key')
		with self.assertRaises(ResponseError):
			self.queue.create_group()

	def test_serialization_and_send(self):
		body = {
			'value': [
				1,
				True,
				None,
			],
		}
		self.connection.xadd.return_value = b'1-0'
		self.assertEqual(
			self.queue.send(body),
			'1-0',
		)
		self.assertEqual(
			self.decode(self.connection.xadd.call_args.args[1]['body']),
			body,
		)

	def test_ack_reject_and_requeue_are_idempotent(self):
		for operation in (
			'ack',
			'reject',
			'nack',
		):
			with self.subTest(operation=operation):
				self.connection.reset_mock()
				event = Event(
					self.connection,
					'test',
					'1-0',
					{},
					'group',
				)
				getattr(
					event,
					operation,
				)()
				getattr(
					event,
					operation,
				)()
				self.assertTrue(event.settled)
				self.assertEqual(
					self.connection.eval.call_count if operation == 'nack' else self.connection.xack.call_count,
					1,
				)
				self.connection.xdel.assert_not_called()

	def test_failed_settlement_is_not_marked_successful(self):
		event = Event(
			self.connection,
			'test',
			'1-0',
			{},
			'group',
		)
		self.connection.xack.side_effect = ConnectionError('unavailable')
		with self.assertRaises(ConnectionError):
			event.ack()
		self.assertFalse(event.settled)
		history = self.queue.event(
			b'1-0',
			{b'body': b'{}'},
		)
		with self.assertRaises(RuntimeError):
			history.ack()

	def test_pop_timeout_and_read(self):
		self.connection.xreadgroup.return_value = []
		self.assertIsNone(self.queue.pop(timeout=1))
		self.connection.xread.side_effect = [
			[
				(
					b'test',
					[
						(
							b'1-0',
							{b'body': b'{"value": 1}'},
						),
					],
				),
			],
			[],
		]
		events = self.queue.read(timeout=20)
		event = next(events)
		self.assertEqual(
			event.body,
			{'value': 1},
		)
		events.close()

	def test_callback_scheduling_and_failure_policy(self):
		consumer = Consumer(
			self.connection,
			self.encode,
			self.decode,
		)
		owners = []
		thread = Thread(target=lambda: consumer.call(lambda: owners.append(get_ident())))
		thread.start()
		thread.join()
		self.assertEqual(
			owners,
			[],
		)
		consumer.drain()
		self.assertEqual(
			owners,
			[get_ident()],
		)
		event = Mock()
		consumer.fail(event)
		event.nack.assert_called_once()
		consumer.fail(
			event,
			Reject(),
		)
		event.reject.assert_called_once()
		consumer.close()
		with self.assertRaises(RuntimeError):
			consumer.call(lambda: None)

	def test_subscription_validation(self):
		consumer = Consumer(
			self.connection,
			self.encode,
			self.decode,
		)
		with self.assertRaises(ValueError):
			consumer.subs('test')
		consumer.subs(
			Subscription('test'),
			Mock(),
		)
		with self.assertRaises(ValueError):
			consumer.subs(
				{'queue': 'test'},
				Mock(),
			)
		for invalid in (
			0,
			-1,
			True,
		):
			with self.assertRaises(ValueError):
				Consumer(
					self.connection,
					self.encode,
					self.decode,
					qos=invalid,
				)

	def test_decode_and_callback_errors_propagate_without_ack(self):
		consumer = Consumer(
			self.connection,
			self.encode,
			self.decode,
			reclaim_idle=None,
		)
		handler = Mock()
		consumer.subs(
			'test',
			handler,
		)
		self.connection.xreadgroup.return_value = [
			(
				b'test',
				[
					(
						b'1-0',
						{b'body': b'invalid JSON'},
					),
				],
			),
		]
		with self.assertRaises(ValueError):
			consumer.run()
		handler.assert_not_called()
		self.connection.xack.assert_not_called()

		def fail():
			raise RuntimeError('callback failure')

		consumer.call(fail)
		with self.assertRaisesRegex(
			RuntimeError,
			'callback failure',
		):
			consumer.drain()


if __name__ == '__main__':
	main()
