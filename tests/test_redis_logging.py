from importlib.util import (
	module_from_spec,
	spec_from_file_location,
)
from importlib import import_module
from logging import (
	DEBUG,
	getLogger,
	makeLogRecord,
)
from pathlib import Path
from unittest import (
	TestCase,
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
)
from DefStream.Broker.Implements.Redis.Serializer import (
	JavaScriptObjectNotationDecoder,
	JavaScriptObjectNotationEncoder,
)


class RedisLoggingTests(TestCase):
	def test_class_loggers_have_explicit_names_and_propagate(self):
		for log_class, name in (
			(Connection, 'Connection'),
			(Consumer, 'Consumer'),
			(Queue, 'Queue'),
			(Event, 'Event'),
		):
			with self.subTest(class_name=name):
				self.assertEqual(
					log_class.logger.name,
					'Broker.Redis.' + name,
				)
				self.assertTrue(log_class.logger.propagate)

	def test_namespace_and_root_propagation(self):
		connection = Mock()
		connection.xadd.return_value = b'7-0'
		queue = Queue(
			connection,
			lambda body: body,
			lambda body: body,
			'safe-stream',
		)
		for name in (
			'Broker.Redis.Queue',
			'Broker.Redis',
			'Broker',
			'',
		):
			with self.subTest(name=name), self.assertLogs(name, level=DEBUG) as captured:
				queue.send({'message': 'safe'})
			self.assertTrue(any(
				record.name == Queue.logger.name
				for record in captured.records
			))

	def test_connection_failure_log_omits_credentials_and_exception_text(self):
		broker = Connection(Configuration(password='private-password'))
		connection_module = import_module('DefStream.Broker.Implements.Redis.Connection')
		with patch.object(
			connection_module,
			'Redis',
		) as redis:
			redis.return_value.ping.side_effect = ConnectionError('private-password')
			with self.assertLogs(
				Connection.logger,
				level='ERROR',
			) as captured:
				with self.assertRaises(ConnectionError):
					broker.connect()
		self.assertTrue(any('ConnectionError' in record.getMessage() for record in captured.records))
		self.assertNotIn('private-password', '\n'.join(captured.output))
		self.assertNotIn('Traceback', '\n'.join(captured.output))
		redis.return_value.close.assert_called_once()

	def test_connection_logs_pool_and_cluster_modes(self):
		connection_module = import_module('DefStream.Broker.Implements.Redis.Connection')
		for connection_type, client_name in (
			(ConnectionType.Pool, 'Redis'),
			(ConnectionType.Cluster, 'RedisCluster'),
		):
			with self.subTest(connection_type=connection_type.value):
				broker = Connection(Configuration(
					type=connection_type,
					password='private-password',
				))
				with patch.object(
					connection_module,
					client_name,
				):
					with self.assertLogs(
						Connection.logger,
						level=DEBUG,
					) as captured:
						broker.connect()
						broker.close()
				output = '\n'.join(captured.output)
				self.assertIn(connection_type.value, output)
				self.assertNotIn('private-password', output)

	def test_queue_logs_metadata_without_serialized_body(self):
		connection = Mock()
		connection.xadd.return_value = b'7-0'
		queue = Queue(
			connection,
			lambda body: b'private-payload',
			lambda body: body,
			'safe-stream',
		)
		with self.assertLogs(
			Queue.logger,
			level=DEBUG,
		) as captured:
			self.assertEqual(
				queue.send({'token': 'private-payload'}),
				'7-0',
			)
		output = '\n'.join(captured.output)
		self.assertIn('safe-stream', output)
		self.assertIn('7-0', output)
		self.assertNotIn('private-payload', output)

	def test_existing_group_is_debug_only(self):
		connection = Mock()
		queue = Queue(
			connection,
			JavaScriptObjectNotationEncoder(),
			JavaScriptObjectNotationDecoder(),
			'safe-stream',
		)
		with self.assertLogs(
			Queue.logger,
			level=DEBUG,
		) as captured:
			queue.create_group()
		self.assertTrue(any('creation completed' in record.getMessage() for record in captured.records))

		connection.xgroup_create.side_effect = ResponseError('BUSYGROUP already exists')
		with self.assertLogs(
			Queue.logger,
			level=DEBUG,
		) as captured:
			queue.create_group()
		self.assertTrue(any('Reusing' in record.getMessage() for record in captured.records))
		self.assertFalse(any(record.levelname in ('WARNING', 'ERROR') for record in captured.records))

	def test_queue_read_timeout_and_failure_are_distinguished(self):
		connection = Mock()
		queue = Queue(
			connection,
			JavaScriptObjectNotationEncoder(),
			JavaScriptObjectNotationDecoder(),
			'safe-stream',
		)
		connection.xread.return_value = []
		with self.assertLogs(
			Queue.logger,
			level=DEBUG,
		) as captured:
			self.assertEqual(list(queue.read(timeout=1)), [])
		self.assertTrue(any('timed out' in record.getMessage() for record in captured.records))

		connection.xread.side_effect = ConnectionError('private-payload')
		with self.assertLogs(
			Queue.logger,
			level='ERROR',
		) as captured:
			with self.assertRaises(ConnectionError):
				list(queue.read(timeout=1))
		output = '\n'.join(captured.output)
		self.assertIn('ConnectionError', output)
		self.assertNotIn('private-payload', output)
		self.assertNotIn('Traceback', output)

	def test_consumer_logs_reclaimed_delivery(self):
		connection = Mock()
		connection.xautoclaim.return_value = (
			b'0-0',
			[
				(
					b'7-0',
					{b'body': b'private-payload'},
				),
			],
			[],
		)
		consumer = Consumer(
			connection,
			lambda body: body,
			lambda body: 'private-payload',
		)
		consumer.subs(
			'safe-stream',
			lambda event: consumer.stop(),
		)
		with self.assertLogs(
			Consumer.logger,
			level=DEBUG,
		) as captured:
			consumer.run()
		output = '\n'.join(captured.output)
		self.assertIn('reclaim result', output)
		self.assertIn('7-0', output)
		self.assertNotIn('private-payload', output)
		connection.xautoclaim.assert_called_once()

	def test_event_zero_result_and_history_warning_are_not_success(self):
		connection = Mock()
		connection.xack.return_value = 0
		connection.eval.return_value = 0
		event = Event(
			connection,
			'safe-stream',
			'7-0',
			{},
			'group',
			'consumer',
		)
		with self.assertLogs(
			Event.logger,
			level=DEBUG,
		) as captured:
			event.ack()
			requeued = Event(
				connection,
				'safe-stream',
				'8-0',
				{},
				'group',
				'consumer',
			)
			requeued.nack()
		self.assertTrue(event.settled)
		self.assertTrue(requeued.settled)
		self.assertTrue(any('No Event' in record.getMessage() for record in captured.records))
		self.assertFalse(any('completed' in record.getMessage() for record in captured.records))

		history = Event(
			connection,
			'safe-stream',
			'9-0',
			{},
		)
		with self.assertLogs(
			Event.logger,
			level='WARNING',
		) as captured:
			with self.assertRaises(RuntimeError):
				history.ack()
		self.assertEqual(captured.records[0].levelname, 'WARNING')
		connection.xack.assert_called_once()

	def test_event_failure_logs_only_exception_type(self):
		connection = Mock()
		connection.xack.side_effect = ConnectionError('private-payload')
		event = Event(
			connection,
			'safe-stream',
			'7-0',
			{},
			'group',
		)
		with self.assertLogs(
			Event.logger,
			level='ERROR',
		) as captured:
			with self.assertRaises(ConnectionError):
				event.ack()
		output = '\n'.join(captured.output)
		self.assertIn('ConnectionError', output)
		self.assertNotIn('private-payload', output)
		self.assertNotIn('Traceback', output)
		self.assertFalse(event.settled)

	def test_handler_failure_logs_context_without_payload_or_traceback(self):
		connection = Mock()
		consumer = Consumer(
			connection,
			lambda body: body,
			lambda body: 'private-payload',
			reclaim_idle=None,
		)
		stream = Queue(
			connection,
			lambda body: body,
			lambda body: 'private-payload',
			'safe-stream',
		)
		handler = Mock(side_effect=RuntimeError('private-payload'))
		with self.assertLogs(
			Consumer.logger,
			level='ERROR',
		) as captured:
			with self.assertRaises(RuntimeError):
				consumer.deliver(
					stream,
					handler,
					[
						(
							b'7-0',
							{b'body': b'private-payload'},
						),
					],
				)
		output = '\n'.join(captured.output)
		self.assertIn('safe-stream', output)
		self.assertIn('7-0', output)
		self.assertNotIn('private-payload', output)
		self.assertNotIn('Traceback', output)

	def test_sample_filters_allow_only_named_hierarchies(self):
		sample_dir = Path(__file__).resolve().parent.parent / 'samples' / 'Broker' / 'Redis'
		root_logger = getLogger()
		root_level = root_logger.level
		root_handlers = tuple(root_logger.handlers)
		sample_paths = (
			sample_dir / 'Sample.py',
			sample_dir / 'Sample.Stream.py',
		)
		filters = []
		for index, path in enumerate(sample_paths):
			spec = spec_from_file_location('redis_sample_{}'.format(index), path)
			module = module_from_spec(spec)
			spec.loader.exec_module(module)
			filters.append(module.SampleLogFilter())
		self.assertEqual(root_logger.level, root_level)
		self.assertEqual(tuple(root_logger.handlers), root_handlers)
		for log_filter in filters:
			for name, expected in (
				('Sample', True),
				('Sample.worker', True),
				('Sampled', False),
				('Broker.Redis', True),
				('Broker.Redis.Queue', True),
				('Broker.RedisExtra.Queue', False),
				('Worker', False),
			):
				with self.subTest(name=name):
					self.assertEqual(
						log_filter.filter(makeLogRecord({'name': name})),
						expected,
					)
