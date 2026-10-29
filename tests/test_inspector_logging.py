from http.client import HTTPConnection
from io import StringIO
from logging import (
	DEBUG,
	ERROR,
	INFO,
)
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Inspector import Inspector
from DefStream.Inspector.Extension import Extension
from DefStream.Inspector.Extensions import (
	Console,
	Metrics,
	Ping,
	Specifications,
	Status,
)
from DefStream.Inspector.Inspector import (
	InspectorServerHandler,
	RequestHandler,
	Server,
)
from DefStream.Inspector.Response import Response


class Example(Extension):
	def __call__(self, inspector: Inspector) -> Response:
		return Response(
			'200 OK',
			b'private-response',
			'text/plain',
		)


class Failure(Extension):
	def __call__(self, inspector: Inspector) -> Response:
		raise ValueError('private-exception-message')


class InspectorLoggingTests(TestCase):
	def fetch(self, extension: Extension):
		inspector = Inspector(
			port=0,
			exts=(extension,),
		)
		inspector.start(Mock())
		connection = HTTPConnection(
			'127.0.0.1',
			inspector.server.server_port,
			timeout=5,
		)
		try:
			connection.request(
				'GET',
				extension.path + '?token=private-query',
			)
			response = connection.getresponse()
			body = response.read()
			return response.status, body
		finally:
			connection.close()
			inspector.stop()

	def test_shared_logger_and_extension_members(self):
		for cls in (
			Inspector,
			Server,
			RequestHandler,
		):
			self.assertEqual(cls.logger.name, 'Worker.Inspector')
			self.assertTrue(cls.logger.propagate)
		for cls in (
			Console,
			Status,
			Ping,
			Metrics,
			Specifications,
		):
			self.assertEqual(cls.logger.name, 'Worker.Inspector.' + cls.__name__)
			self.assertEqual(cls.logger.handlers, [])
			self.assertTrue(cls.logger.propagate)

	def test_logs_propagate_through_worker_inspector_to_root(self):
		for name in (
			'Worker.Inspector',
			'Worker',
			'',
		):
			with self.subTest(logger=name), self.assertLogs(name, level=DEBUG) as logs:
				self.fetch(Example('/sample'))
			self.assertTrue(any(
				record.name.startswith('Worker.Inspector')
				for record in logs.records
			))

	def test_one_request_debug_and_one_response_info_without_query_or_body(self):
		with self.assertLogs('Worker.Inspector', level=DEBUG) as logs:
			status, body = self.fetch(Example('/sample'))
		self.assertEqual(status, 200)
		self.assertEqual(body, b'private-response')
		requests = [record for record in logs.records if 'HTTP request received:' in record.getMessage()]
		responses = [record for record in logs.records if 'HTTP response sent:' in record.getMessage()]
		self.assertEqual(len(requests), 1)
		self.assertEqual(requests[0].levelno, DEBUG)
		self.assertEqual(len(responses), 1)
		self.assertEqual(responses[0].levelno, INFO)
		self.assertIn('status=200', responses[0].getMessage())
		self.assertIn('path=/sample', responses[0].getMessage())
		self.assertNotIn('private-query', '\n'.join(logs.output))
		self.assertNotIn('private-response', '\n'.join(logs.output))

	def test_wsgi_failure_is_logged_once_and_returns_500(self):
		with self.assertLogs('Worker.Inspector', level=DEBUG) as logs:
			status, _ = self.fetch(Failure('/failure'))
		self.assertEqual(status, 500)
		errors = [record for record in logs.records if record.levelno == ERROR]
		self.assertEqual(len(errors), 1)
		self.assertIn('ValueError', errors[0].getMessage())
		self.assertNotIn('private-exception-message', '\n'.join(logs.output))
		responses = [record for record in logs.records if record.levelno == INFO and 'status=500' in record.getMessage()]
		self.assertEqual(len(responses), 1)

	def test_interrupted_response_does_not_log_success(self):
		handler = InspectorServerHandler(
			StringIO(),
			StringIO(),
			StringIO(),
			{},
		)
		handler.request_handler = Mock()
		handler.result = [b'private-response']
		handler.write = Mock(side_effect=ConnectionResetError())
		with self.assertRaises(ConnectionResetError):
			handler.finish_response()
		handler.request_handler.log_request.assert_not_called()

	def test_console_handled_failure_retains_error_type_not_private_message(self):
		console = Console(
			'/console',
			broker=Mock(),
		)
		console.catalog = Mock(side_effect=ValueError('private-exception-message'))
		with self.assertLogs(console.logger, level=ERROR) as logs:
			response = console.handle(
				Mock(),
				{
					'REQUEST_METHOD': 'GET',
					'HTTP_ACCEPT': 'application/json',
				},
			)
		self.assertEqual(response.status, '500 Internal Server Error')
		self.assertEqual(len(logs.records), 1)
		self.assertIn('ValueError', logs.records[0].getMessage())
		self.assertNotIn('private-exception-message', '\n'.join(logs.output))


if __name__ == '__main__':
	main()
