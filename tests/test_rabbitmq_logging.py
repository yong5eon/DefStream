from ast import (
	Module,
	parse,
)
from importlib import import_module
from gc import collect
from io import StringIO
from logging import (
	DEBUG,
	ERROR,
	INFO,
	WARNING,
	StreamHandler,
	getLogger,
)
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
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

from DefStream.Broker import RemoteError
from DefStream.Broker.Implements.RabbitMQ import (
	Configuration,
	Connection,
	Consumer,
	Event,
	Exchange,
	ExchangeType,
	Queue,
	Reject,
	Stream,
)
from DefStream.Broker.Implements.RabbitMQ.Serializer import (
	JavaScriptObjectNotationDecoder,
	JavaScriptObjectNotationEncoder,
)


NAMESPACE = 'DefStream.Broker.Implements.RabbitMQ'
PROJECT = Path(__file__).resolve().parents[1]
SECRET = '비밀본문_인증정보_헤더'


class LoggingTests(TestCase):
	def setUp(self):
		self.encode = JavaScriptObjectNotationEncoder()
		self.decode = JavaScriptObjectNotationDecoder()
		self.connection = Mock()
		self.channel = self.connection.channel.return_value
		self.properties = BasicProperties(
			message_id='message',
			correlation_id='correlation',
			reply_to='reply',
			headers={'secret': SECRET},
			content_type='application/json',
			content_encoding='utf-8',
		)
		self.method = SimpleNamespace(
			consumer_tag='consumer',
			delivery_tag=7,
		)
		return

	def event(self):
		return Event(
			self.channel,
			'queue',
			'consumer',
			7,
			self.properties,
			SECRET,
		)

	def queue(self):
		return Queue(
			self.connection,
			self.encode,
			self.decode,
			'queue',
			rpc_parameters=ConnectionParameters(),
		)

	def assert_safe(self, records):
		for record in records:
			self.assertNotIn(SECRET, record.getMessage())
			self.assertIsNone(record.exc_info)
		return

	def test_names_inheritance_and_no_library_configuration(self):
		for cls in (
			Connection,
			Consumer,
			Queue,
			Exchange,
			Stream,
			Event,
		):
			with self.subTest(cls=cls.__name__):
				self.assertEqual(cls.logger.name, NAMESPACE + '.' + cls.__name__)
				self.assertEqual(cls.logger.handlers, [])
				self.assertEqual(cls.logger.filters, [])
				self.assertEqual(cls.logger.level, 0)
				self.assertTrue(cls.logger.propagate)
				child = type('Custom', (cls,), {})
				self.assertIs(child.logger, cls.logger)
		return

	def test_ancestor_selection_and_root_propagation(self):
		event = self.event()
		for name in (
			NAMESPACE + '.Event',
			NAMESPACE,
			'DefStream.Broker',
			'DefStream',
			'',
		):
			with self.subTest(name=name), self.assertLogs(name, level=DEBUG) as logs:
				event.ack()
			self.assertEqual(len(logs.records), 2)
			self.assertTrue(all(record.name == NAMESPACE + '.Event' for record in logs.records))
		return

	def test_settlement_success_and_failure_no_false_completion(self):
		event = self.event()
		for action in (
			'ack',
			'nack',
			'reject',
		):
			with self.subTest(action=action), self.assertLogs(NAMESPACE, level=DEBUG) as logs:
				getattr(event, action)()
			self.assertEqual([record.levelno for record in logs.records], [DEBUG, DEBUG])
			method = getattr(self.channel, 'basic_' + action)
			failure = RuntimeError(SECRET)
			method.side_effect = failure
			with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError) as caught:
				getattr(event, action)()
			self.assertIs(caught.exception, failure)
			self.assertEqual([record.levelno for record in logs.records], [DEBUG, ERROR])
			self.assert_safe(logs.records)
			method.side_effect = None
		return

	def test_send_metadata_and_failures_all_publishers(self):
		publishers = (
			self.queue(),
			Exchange(self.connection, self.encode, 'exchange'),
			Stream(self.connection, self.encode, self.decode, 'stream'),
		)
		for publisher in publishers:
			with self.subTest(cls=type(publisher).__name__):
				with self.assertLogs(NAMESPACE, level=DEBUG) as logs:
					publisher.send(SECRET, headers={'secret': SECRET}, id='message')
				self.assertEqual(len(logs.records), 2)
				self.assert_safe(logs.records)
				self.channel.basic_publish.side_effect = RuntimeError(SECRET)
				with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
					publisher.send(SECRET)
				self.assertEqual(sum(record.levelno == ERROR for record in logs.records), 1)
				self.assert_safe(logs.records)
				self.channel.basic_publish.side_effect = None
		return

	def test_connection_lifecycle_resources_confirm_and_request_delegation(self):
		module = import_module(NAMESPACE + '.Connection')
		broker = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username=SECRET,
			password=SECRET,
		))
		with patch.object(module, 'BlockingConnection', return_value=self.connection), self.assertLogs(NAMESPACE, level=DEBUG) as logs:
			broker.connect()
			broker.connect()
			broker.create_queue('queue', maxPriority=5)
			broker.create_exchange('exchange', ExchangeType.Direct)
			broker.bind_exchange_to_queue('exchange', 'queue')
			broker.unbind_exchange_to_queue('exchange', 'queue')
			broker.bind_exchange_to_exchange('exchange', 'other')
			broker.unbind_exchange_to_exchange('exchange', 'other')
			broker.create_stream('stream')
			broker.declare({'queue': 'queue'})
			broker.emit(SECRET, {'queue': 'queue'})
			broker.emit(SECRET, {'queue': 'queue'})
			broker.delete_queue('queue')
			broker.delete_stream('stream')
			broker.delete_exchange('exchange')
		self.assertTrue(any(record.levelno == INFO for record in logs.records))
		self.assertTrue(any('publisher_confirm=True' in record.getMessage() for record in logs.records))
		self.assert_safe(logs.records)
		self.channel.confirm_delivery.assert_called_once_with()
		with patch.object(Queue, 'call', side_effect=RuntimeError(SECRET)), self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
			broker.request(SECRET, {'queue': 'queue'})
		self.assertFalse(any(record.levelno == ERROR for record in logs.records))
		with self.assertLogs(NAMESPACE, level=INFO) as logs:
			broker.close()
		self.assertIn('connection close completed', logs.output[0])
		return

	def test_connection_resource_and_connect_failure(self):
		broker = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			password=SECRET,
		))
		module = import_module(NAMESPACE + '.Connection')
		with patch.object(module, 'BlockingConnection', side_effect=RuntimeError(SECRET)), self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
			broker.connect()
		self.assertEqual(sum(record.levelno == ERROR for record in logs.records), 1)
		self.assert_safe(logs.records)
		broker.connection = self.connection
		self.channel.queue_declare.side_effect = RuntimeError(SECRET)
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
			broker.create_queue('queue')
		self.assertEqual(len(logs.records), 2)
		self.assertEqual(logs.records[-1].levelno, ERROR)
		self.assert_safe(logs.records)
		return

	def test_pop_timeout_is_debug_without_poll_noise_and_success(self):
		queue = self.queue()
		queue.logger = getLogger(self.id())
		# 다른 큐의 지연 정리 로그가 대기 중 발생해도 대상 큐의 로그만 검증한다.
		unrelated = self.queue()
		unrelated.cycle = unrelated
		pending_cleanup = [unrelated]
		del unrelated

		def collect_unrelated_queue(*args):
			pending_cleanup.clear()
			collect()
			return

		module = import_module(NAMESPACE + '.Queue')
		self.channel.basic_get.return_value = (None, None, None)
		with patch.object(module, 'time', side_effect=[0, 0, 1]), patch.object(module, 'sleep', side_effect=collect_unrelated_queue), self.assertLogs(queue.logger, level=DEBUG) as logs:
			self.assertIsNone(queue.pop(timeout=1))
		self.assertFalse(pending_cleanup)
		self.assertEqual(len(logs.records), 2)
		self.assertTrue(all(record.levelno == DEBUG for record in logs.records))
		self.channel.basic_get.return_value = (self.method, self.properties, self.encode(SECRET))
		with self.assertLogs(queue.logger, level=DEBUG) as logs:
			event = queue.pop(timeout=1)
		self.assertEqual(event.body, SECRET)
		self.assert_safe(logs.records)
		self.channel.basic_get.side_effect = RuntimeError(SECRET)
		with self.assertLogs(queue.logger, level=DEBUG) as logs, self.assertRaises(RuntimeError):
			queue.pop(timeout=1)
		self.assertEqual(logs.records[-1].levelno, ERROR)
		self.assert_safe(logs.records)
		return

	def test_consumer_receive_decode_handler_and_loop_error_ownership(self):
		consumer = Consumer(self.connection, self.decode)
		handler = Mock()
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs:
			consumer.subs('queue', handler)
			callback = self.channel.basic_consume.call_args.args[1]
			callback(self.channel, self.method, self.properties, self.encode(SECRET))
			consumer.call(Mock())
			consumer.run()
			consumer.stop()
		self.assert_safe(logs.records)
		handler.assert_called_once()
		self.assertEqual(handler.call_args.args[0].body, SECRET)
		for decoder, expected_errors in (
			(Mock(side_effect=ValueError(SECRET)), 1),
			(self.decode, 0),
		):
			callback.decode = decoder
			handler.side_effect = RuntimeError(SECRET)
			self.channel.start_consuming.side_effect = lambda: callback(self.channel, self.method, self.properties, self.encode(SECRET))
			with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises((ValueError, RuntimeError)):
				consumer.run()
			self.assertEqual(sum(record.levelno == ERROR for record in logs.records), expected_errors)
			self.assert_safe(logs.records)
		self.channel.start_consuming.side_effect = RuntimeError(SECRET)
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
			consumer.run()
		self.assertEqual(sum(record.levelno == ERROR for record in logs.records), 1)
		return

	def test_consumer_rpc_unroutable_settles_and_ack_failure_logs_only_event(self):
		consumer = Consumer(self.connection, self.decode)
		event = self.event()
		self.channel.basic_publish.side_effect = UnroutableError([])
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs:
			consumer.complete(event, SECRET)
		self.channel.basic_ack.assert_called_once_with(7)
		self.assertEqual(sum(record.levelno == WARNING for record in logs.records), 1)
		self.assertFalse(any(record.levelno == ERROR for record in logs.records))
		self.assert_safe(logs.records)
		self.channel.basic_publish.side_effect = None
		self.channel.basic_ack.side_effect = RuntimeError(SECRET)
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
			consumer.complete(event, SECRET)
		errors = [record for record in logs.records if record.levelno == ERROR]
		self.assertEqual([record.name for record in errors], [NAMESPACE + '.Event'])
		self.channel.start_consuming.side_effect = event.ack
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
			consumer.run()
		errors = [record for record in logs.records if record.levelno == ERROR]
		self.assertEqual([record.name for record in errors], [NAMESPACE + '.Event'])
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs:
			consumer.fail(event, Reject())
		self.assertFalse(any(record.levelno >= WARNING for record in logs.records))
		self.assert_safe(logs.records)
		return

	def test_rpc_success_mismatch_remote_error_malformed_and_transport_failure(self):
		for cls in (Queue, Exchange):
			module = import_module(NAMESPACE + '.' + cls.__name__)
			publisher = self.queue() if cls is Queue else Exchange(
				self.connection,
				self.encode,
				'exchange',
				decode=self.decode,
				rpc_parameters=ConnectionParameters(),
			)
			for response, exception, level in (
				({'ok': True, 'result': SECRET}, None, DEBUG),
				({'ok': False, 'error': {'code': SECRET, 'message': SECRET}}, RemoteError, WARNING),
				({'ok': True}, ValueError, ERROR),
			):
				with self.subTest(cls=cls.__name__, level=level), patch.object(module, 'BlockingConnection') as connect:
					channel = connect.return_value.channel.return_value

					def receive(**kwargs):
						callback = channel.basic_consume.call_args.kwargs['on_message_callback']
						properties = channel.basic_publish.call_args.kwargs['properties']
						for correlation in ('ignored', properties.correlation_id):
							callback(
								channel,
								self.method,
								BasicProperties(
									correlation_id=correlation,
									content_type='application/json',
									content_encoding='utf-8',
								),
								self.encode(response),
							)
						return

					connect.return_value.process_data_events.side_effect = receive
					with self.assertLogs(NAMESPACE, level=DEBUG) as logs:
						if exception is None:
							self.assertEqual(publisher.call(SECRET), SECRET)
						else:
							with self.assertRaises(exception):
								publisher.call(SECRET)
					self.assertTrue(any('mismatched' in record.getMessage() for record in logs.records))
					self.assertEqual(sum(record.levelno == level for record in logs.records) if level != DEBUG else 1, 1)
					self.assert_safe(logs.records)
					connect.return_value.close.assert_called_once_with()
			with patch.object(module, 'BlockingConnection', side_effect=RuntimeError(SECRET)), self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
				publisher.call(SECRET)
			self.assertEqual(logs.records[-1].levelno, ERROR)
			self.assert_safe(logs.records)
		return

	def test_rpc_pre_and_post_publication_timeout(self):
		for cls in (Queue, Exchange):
			module = import_module(NAMESPACE + '.' + cls.__name__)
			publisher = self.queue() if cls is Queue else Exchange(
				self.connection,
				self.encode,
				'exchange',
				decode=self.decode,
				rpc_parameters=ConnectionParameters(),
			)
			for clock, published, text in (
				([0, 2], False, 'before publication'),
				([0, 0, 2], True, 'after publication'),
			):
				with self.subTest(cls=cls.__name__, phase=text), patch.object(module, 'BlockingConnection') as connect, patch.object(module, 'monotonic', side_effect=clock), self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(TimeoutError):
					publisher.call(SECRET, timeout=1)
				self.assertEqual(connect.return_value.channel.return_value.basic_publish.called, published)
				warnings = [record for record in logs.records if record.levelno == WARNING]
				self.assertEqual(len(warnings), 1)
				self.assertIn(text, warnings[0].getMessage())
				self.assertFalse(any(record.levelno == ERROR for record in logs.records))
		return

	def test_stream_ack_nack_cancel_and_no_false_success(self):
		stream = Stream(self.connection, self.encode, self.decode, 'stream')
		self.channel.consume.return_value = [(self.method, self.properties, self.encode(SECRET))]
		with self.assertLogs(NAMESPACE, level=DEBUG) as logs:
			self.assertEqual(len(list(stream.read())), 1)
		self.channel.basic_ack.assert_called_once_with(delivery_tag=7)
		self.channel.cancel.assert_called_once_with()
		self.assert_safe(logs.records)
		for failing in ('processing', 'ack', 'nack', 'cancel', 'consume'):
			with self.subTest(failing=failing):
				self.channel.reset_mock(side_effect=True)
				self.channel.consume.return_value = [(self.method, self.properties, self.encode(SECRET))]
				if failing in ('ack', 'nack', 'cancel'):
					getattr(self.channel, 'basic_' + failing if failing != 'cancel' else 'cancel').side_effect = RuntimeError(SECRET)
				if failing == 'consume':
					self.channel.consume.side_effect = RuntimeError(SECRET)
				with self.assertLogs(NAMESPACE, level=DEBUG) as logs, self.assertRaises(RuntimeError):
					reader = stream.read()
					if failing in ('processing', 'nack'):
						next(reader)
						reader.throw(RuntimeError(SECRET))
					else:
						list(reader)
				errors = [record for record in logs.records if record.levelno == ERROR]
				self.assertEqual(len(errors), 0 if failing == 'processing' else 1)
				self.assert_safe(logs.records)
		return

	def test_debug_disabled_does_not_emit_message_trace(self):
		event = self.event()
		logger = event.logger
		level = logger.level
		output = StringIO()
		handler = StreamHandler(output)
		handler.setLevel(INFO)
		logger.addHandler(handler)
		logger.setLevel(INFO)
		try:
			event.ack()
			self.assertEqual(output.getvalue(), '')
			self.channel.basic_ack.assert_called_once_with(self.method.delivery_tag)
		finally:
			logger.removeHandler(handler)
			logger.setLevel(level)
		return

	def test_sample_imports_do_not_configure_root_and_console_filter_boundaries(self):
		root = getLogger()
		handlers = root.handlers[:]
		level = root.level
		for path in (PROJECT / 'samples' / 'Broker' / 'RabbitMQ').glob('*.py'):
			with self.subTest(sample=path.name):
				run_path(str(path), run_name='sample_import_test')
				self.assertEqual(root.handlers, handlers)
				self.assertEqual(root.level, level)
				tree = parse(path.read_text(encoding='utf-8'))
				entry = next(node for node in tree.body if getattr(node, 'test', None) is not None)
				config = []
				for statement in entry.body:
					config.append(statement)
					if getattr(getattr(getattr(statement, 'value', None), 'func', None), 'attr', None) == 'info':
						break
				namespace = run_path(str(path), run_name='sample_import_test')
				try:
					exec(compile(Module(body=config, type_ignores=[]), str(path), 'exec'), namespace)
					console = namespace['console']
					self.assertIsInstance(console, StreamHandler)
					self.assertEqual(console.level, DEBUG)
					output = StringIO()
					console.setStream(output)
					for name in (
						'Sample',
						'Sample.child',
						NAMESPACE,
						NAMESPACE + '.Event',
						'SampleOther',
						NAMESPACE + 'Other',
						'pika',
						'DefStream.Worker',
					):
						console.handle(getLogger(name).makeRecord(name, DEBUG, '', 1, name, (), None))
					self.assertEqual(len(output.getvalue().splitlines()), 4)
				finally:
					for handler in root.handlers:
						if handler not in handlers:
							handler.close()
					root.handlers[:] = handlers
					root.setLevel(level)
		return


if __name__ == '__main__':
	main()
