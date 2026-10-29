from http.client import HTTPConnection
from importlib import import_module
from contextlib import nullcontext
from io import BytesIO
from json import (
	dumps,
	loads,
)
from os import environ
from threading import (
	Event,
	Thread,
)
from typing import Optional
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

from DefStream.Broker.Errors import RemoteError
from DefStream.Broker.Policies import Reject
from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import (
	Console,
	Specifications,
)
from DefStream.Worker import (
	Run,
	Specification,
	ThreadPool,
	Worker,
	WorkerSetup,
)
from tests._support import require_value

TOKEN = 'test-token-at-least-32-characters!'


class Task(
	Run,
	parameters={'queue': 'test'},
	request=Specification(example={
		'a': 6,
		'b': 2,
	}),
	response=Specification(),
	on_error=Reject(),
):
	def run(
		self,
		a,
		b,
	):
		return a / b


class NamedTask(
	Run,
	run_name='ETL.OBS.Split',
	parameters={'queue': 'named-task'},
):
	def run(
		self,
		a,
		b,
	):
		return a / b


class Producer:
	def __init__(self):
		self.connected = 0
		self.closed = 0
		self.sent = []
		self.error: Optional[BaseException] = None

	def connect(self):
		self.connected += 1

	def close(self):
		self.closed += 1

	def emit(
		self,
		body,
		parameters,
	):
		self.sent.append((
			body,
			parameters,
		))
		if self.error is not None:
			raise self.error
		return 'message-id'


class RPCProducer(Producer):
	def request(
		self,
		body,
		parameters,
		timeout=5,
	):
		self.sent.append((
			body,
			parameters,
		))
		if self.error is not None:
			raise self.error
		return body['a'] / body['b']


class ConsoleExtensionTests(TestCase):
	def setUp(self):
		self.producers = []

		def factory():
			producer = RPCProducer()
			self.producers.append(producer)
			return producer

		self.extension = Console(
			'/console',
			broker=factory,
			token=TOKEN,
		)
		self.broker = Mock()
		self.worker = Worker(self.broker, ThreadPool(1))
		self.worker.add(Task)
		self.worker.running.set()
		self.inspector = Inspector(
			port=0,
			exts=(self.extension,),
		)
		self.inspector.start(self.worker)
		self.addCleanup(self.worker.pool.stop)
		self.addCleanup(self.inspector.stop)

	def fetch(
		self,
		method='GET',
		payload=None,
		token: Optional[str] = TOKEN,
		headers=None,
	):
		connection = HTTPConnection(
			'127.0.0.1',
			require_value(self.inspector.server).server_port,
			timeout=5,
		)
		request_headers = {
			'Accept': 'application/json',
		}
		if token is not None:
			request_headers['Authorization'] = 'Bearer ' + token
		body = None
		if payload is not None:
			body = dumps(payload)
			request_headers['Content-Type'] = 'application/json'
		if headers:
			request_headers.update(headers)
		try:
			connection.request(
				method,
				'/console',
				body=body,
				headers=request_headers,
			)
			response = connection.getresponse()
			return response.status, response.read(), dict(response.getheaders())
		finally:
			connection.close()

	def payload(
		self,
		mode='send',
	):
		return {
			'task': Task.name,
			'mode': mode,
			'body': {
				'a': 6,
				'b': 2,
			},
		}

	def test_html_is_public_but_does_not_contain_token_or_metadata(self):
		status, body, headers = self.fetch(headers={'Accept': 'text/html'})
		self.assertEqual(
			status,
			200,
		)
		self.assertIn(
			b'<title>DefStream</title>',
			body,
		)
		self.assertNotIn(
			TOKEN.encode(),
			body,
		)
		self.assertEqual(
			headers['Content-Type'],
			'text/html; charset=utf-8',
		)
		self.assertIn(
			"frame-ancestors 'none'",
			headers['Content-Security-Policy'],
		)
		self.assertEqual(
			self.producers,
			[],
		)

	def test_custom_title_and_description_are_escaped_before_authentication(self):
		self.inspector.exts['/console'] = Console(
			'/console',
			broker=RPCProducer,
			token=TOKEN,
			title='My <Worker> & {{console_description}}',
			description='<script>alert("subtitle")</script>',
		)
		status, body, headers = self.fetch(
			token=None,
			headers={'Accept': 'text/html'},
		)
		self.assertEqual(
			status,
			200,
		)
		self.assertIn(
			b'<title>My &lt;Worker&gt; &amp; {{console_description}}</title>',
			body,
		)
		self.assertIn(
			b'<h1 id="title">My &lt;Worker&gt; &amp; {{console_description}}</h1>',
			body,
		)
		self.assertIn(
			b'&lt;script&gt;alert(&quot;subtitle&quot;)&lt;/script&gt;',
			body,
		)
		self.assertNotIn(
			b'<script>alert',
			body,
		)

	def test_catalog_uses_registered_specifications_version(self):
		self.inspector.exts['/spec'] = Specifications(
			'/spec',
			version='2.4.1',
			description='Registered document',
		)
		status, body, headers = self.fetch()
		self.assertEqual(
			status,
			200,
		)
		self.assertEqual(
			loads(body)['specification']['info']['version'],
			'2.4.1',
		)
		self.assertEqual(
			loads(body)['specification']['info']['description'],
			'Registered document',
		)

	def test_catalog_without_specifications_uses_default_version(self):
		self.assertEqual(
			loads(self.fetch()[1])['specification']['info']['version'],
			'1.0.0',
		)

	def test_default_subtitle_is_empty(self):
		status, body, headers = self.fetch(headers={'Accept': 'text/html'})
		self.assertIn(
			b'<p class="muted subtitle"></p>',
			body,
		)
		self.assertNotIn(
			b' - Console',
			body,
		)

	def test_html_is_read_again_on_each_refresh(self):
		with patch.object(
			import_module('DefStream.Inspector.Extensions.Console'),
			'files',
		) as resources:
			resource = resources.return_value.joinpath.return_value
			resource.read_bytes.side_effect = [
				b'<body data-auth-required="true">First</body>',
				b'<body data-auth-required="true">Updated</body>',
			]
			for expected in (
				b'First',
				b'Updated',
			):
				status, body, headers = self.fetch(headers={'Accept': 'text/html'})
				self.assertEqual(
					status,
					200,
				)
				self.assertIn(
					expected,
					body,
				)
				self.assertEqual(
					headers['Cache-Control'],
					'no-store',
				)
			self.assertEqual(
				resource.read_bytes.call_count,
				2,
			)

	def test_unauthorized_catalog_and_execution_never_create_producer(self):
		for method, payload in (
			(
				'GET',
				None,
			),
			(
				'POST',
				self.payload(),
			),
		):
			with self.assertLogs(
				'DefStream.Inspector.Extensions.Console',
				level='WARNING',
			):
				status, body, headers = self.fetch(
					method,
					payload,
					token='wrong',
				)
			self.assertEqual(
				status,
				401,
			)
		self.assertEqual(
			self.producers,
			[],
		)

	def test_optional_token_allows_catalog_send_and_rpc_without_authorization(self):
		for extension in (
			Console(
				'/console',
				broker=RPCProducer,
			),
			Console(
				'/console',
				broker=RPCProducer,
				token=None,
			),
		):
			self.extension = extension
			self.inspector.exts['/console'] = self.extension
			status, body, headers = self.fetch(
				token=None,
				headers={'Accept': 'text/html'},
			)
			self.assertEqual(
				status,
				200,
			)
			self.assertIn(
				b'data-auth-required="false"',
				body,
			)
			self.assertEqual(
				self.fetch(token=None)[0],
				200,
			)
			for mode, result in (
				(
					'send',
					'message-id',
				),
				(
					'request',
					3,
				),
			):
				status, body, headers = self.fetch(
					'POST',
					self.payload(mode),
					token=None,
				)
				self.assertEqual(
					status,
					200,
				)
				self.assertEqual(
					loads(body)['result'],
					result,
				)

	def test_configured_token_rejects_missing_authorization(self):
		with self.assertLogs(
			'DefStream.Inspector.Extensions.Console',
			level='WARNING',
		):
			self.assertEqual(
				self.fetch(token=None)[0],
				401,
			)
			self.assertEqual(
				self.fetch(
					'POST',
					self.payload(),
					token=None,
				)[0],
				401,
			)

	def test_empty_token_is_not_an_implicit_authentication_bypass(self):
		with self.assertRaises(ValueError):
			Console(
				'/console',
				broker=RPCProducer,
				token='',
			)

	def test_catalog_and_real_helper_delegation_borrow_independent_connections(self):
		status, body, headers = self.fetch()
		self.assertEqual(
			status,
			200,
		)
		self.assertTrue(loads(body)['rpc'])
		self.assertEqual(
			loads(body)['specification']['channels']['test']['messages']['request']['examples'][0]['payload'],
			{
				'a': 6,
				'b': 2,
			},
		)
		for mode, result in (
			(
				'send',
				'message-id',
			),
			(
				'request',
				3,
			),
		):
			status, body, headers = self.fetch(
				'POST',
				self.payload(mode),
			)
			self.assertEqual(
				status,
				200,
			)
			self.assertEqual(
				loads(body)['result'],
				result,
			)
		self.assertEqual(
			[producer.connected for producer in self.producers],
			[
				0,
				1,
				1,
			],
		)
		self.assertTrue(all(producer.closed == 1 for producer in self.producers))
		self.broker.connect.assert_not_called()
		self.broker.close.assert_not_called()

	def test_custom_task_name_is_resolved_and_duplicate_names_are_rejected(self):
		self.worker.add(NamedTask)
		payload = self.payload()
		payload['task'] = NamedTask.name
		status, body, headers = self.fetch(
			'POST',
			payload,
		)
		self.assertEqual(status, 200)
		self.assertEqual(loads(body)['result'], 'message-id')
		self.assertEqual(self.producers[-1].sent[0][1], NamedTask.parameters)

		self.worker.tasks.append(NamedTask)
		with self.assertLogs(
			'DefStream.Inspector.Extensions.Console',
			level='WARNING',
		) as logs:
			status, body, headers = self.fetch(
				'POST',
				payload,
			)
		self.assertEqual(status, 400)
		self.assertEqual(loads(body)['error'], 'Ambiguous registered task name')
		self.assertIn('message=Ambiguous registered task name', logs.output[0])

	def test_invalid_task_warning_includes_the_specific_error(self):
		payload = self.payload()
		payload['task'] = 'not-registered'
		with self.assertLogs(
			'DefStream.Inspector.Extensions.Console',
			level='WARNING',
		) as logs:
			status, body, headers = self.fetch(
				'POST',
				payload,
			)
		self.assertEqual(status, 400)
		self.assertIn('error=ValueError', logs.output[0])
		self.assertIn('message=Unknown registered task', logs.output[0])
		self.assertEqual(self.producers, [])

	def test_unsupported_rpc_and_worker_not_running(self):
		self.extension.broker = Producer
		self.assertFalse(loads(self.fetch()[1])['rpc'])
		self.assertEqual(
			self.fetch(
				'POST',
				self.payload('request'),
			)[0],
			501,
		)
		self.worker.stopping.set()
		self.assertEqual(
			self.fetch(
				'POST',
				self.payload(),
			)[0],
			503,
		)

	def test_head_and_direct_body_validation(self):
		status, body, headers = self.fetch('HEAD')
		self.assertEqual(
			(
				status,
				body,
			),
			(
				200,
				b'',
			),
		)
		self.assertGreater(
			int(headers['Content-Length']),
			0,
		)
		for raw, length, expected in (
			(
				b'{}',
				'',
				411,
			),
			(
				b'{}',
				'3',
				400,
			),
			(
				b'{"task":"Task","mode":"send","body":{"a":NaN}}',
				None,
				400,
			),
		):
			request_environ = {
				'REQUEST_METHOD': 'POST',
				'HTTP_AUTHORIZATION': 'Bearer ' + TOKEN,
				'CONTENT_TYPE': 'application/json',
				'CONTENT_LENGTH': length if length is not None else str(len(raw)),
				'wsgi.input': BytesIO(raw),
			}
			with self.assertLogs(
				'DefStream.Inspector.Extensions.Console',
				level='WARNING',
			) if expected == 400 else nullcontext():
				response = self.extension.handle(
					self.inspector,
					request_environ,
				)
			self.assertEqual(
				int(response.status.split()[0]),
				expected,
			)

	def test_malformed_origin_is_rejected_explicitly(self):
		with self.assertLogs(
			'DefStream.Inspector.Extensions.Console',
			level='WARNING',
		):
			self.assertEqual(
				self.fetch(
					'POST',
					self.payload(),
					headers={'Origin': 'http://['},
				)[0],
				403,
			)
		self.assertEqual(
			self.producers,
			[],
		)

	def test_connect_and_serialization_failures_close_producers(self):
		class BrokenConnection(Producer):
			def connect(self):
				raise RuntimeError('Connection failed')

		class BrokenResponse(Producer):
			def emit(
				self,
				body,
				parameters,
			):
				return object()

		for producer in (
			BrokenConnection(),
			BrokenResponse(),
		):
			self.extension.broker = lambda: producer
			with self.assertLogs(
				'DefStream.Inspector.Extensions.Console',
				level='ERROR',
			):
				self.assertEqual(
					self.fetch(
						'POST',
						self.payload(),
					)[0],
					500,
				)
			self.assertEqual(
				producer.closed,
				1,
			)

	def test_cross_origin_and_invalid_requests_do_not_publish(self):
		with self.assertLogs(
			'DefStream.Inspector.Extensions.Console',
			level='WARNING',
		):
			self.assertEqual(
				self.fetch(
					'POST',
					self.payload(),
					headers={'Origin': 'https://other.example'},
				)[0],
				403,
			)
			for payload in (
				{
					'task': 'Unknown',
					'mode': 'send',
					'body': {},
				},
				{
					'task': 'Task',
					'mode': 'delete',
					'body': {},
				},
				{
					'task': 'Task',
					'mode': 'send',
					'body': [],
				},
			):
				self.assertEqual(
					self.fetch(
						'POST',
						payload,
					)[0],
					400,
				)
		self.assertEqual(
			self.producers,
			[],
		)
		self.assertEqual(
			self.fetch(
				'POST',
				self.payload(),
				headers={'Content-Type': 'text/plain'},
			)[0],
			415,
		)
		self.assertEqual(
			self.fetch(
				'POST',
				{'padding': 'x' * 65536},
			)[0],
			413,
		)

	def test_rpc_errors_and_publication_failure_close_connections(self):
		for error, expected in (
			(
				TimeoutError(),
				504,
			),
			(
				RemoteError(
					'ProcessingError',
					'Request failed',
				),
				502,
			),
			(
				RuntimeError('private connection information'),
				500,
			),
		):
			producer = RPCProducer()
			producer.error = error
			self.extension.broker = lambda: producer
			with self.assertLogs(
				'DefStream.Inspector.Extensions.Console',
				level='WARNING',
			):
				status, body, headers = self.fetch(
					'POST',
					self.payload('request'),
				)
			self.assertEqual(
				status,
				expected,
			)
			self.assertNotIn(
				b'private connection information',
				body,
			)
			self.assertEqual(
				producer.closed,
				1,
			)

	def test_worker_connection_is_rejected_without_closing_it(self):
		self.extension.broker = lambda: self.worker.broker
		with self.assertLogs(
			'DefStream.Inspector.Extensions.Console',
			level='ERROR',
		):
			self.assertEqual(
				self.fetch(
					'POST',
					self.payload(),
				)[0],
				500,
			)
		self.broker.close.assert_not_called()

	def test_concurrency_limit_and_existing_routes_keep_methods(self):
		for _ in range(4):
			self.extension.slots.acquire()
		try:
			self.assertEqual(
				self.fetch()[0],
				429,
			)
		finally:
			for _ in range(4):
				self.extension.slots.release()
		self.assertEqual(
			self.fetch('DELETE')[0],
			405,
		)

	def exercise_live(
		self,
		factory,
		rpc,
	):
		class Live(
			Task,
			parameters={'queue': 'defstream-test-ui-' + uuid4().hex},
		):
			pass

		ready = Event()
		worker_broker = factory()

		class Prepare(WorkerSetup):
			def __call__(self, worker: Worker) -> None:
				worker_broker.declare(Live.parameters)
				ready.set()

		extension = Console(
			'/console',
			broker=factory,
			token=TOKEN,
		)
		inspector = Inspector(
			port=0,
			exts=(extension,),
		)
		worker = Worker(
			worker_broker,
			ThreadPool(2),
			setups=Prepare(),
			inspector=inspector,
		)
		worker.add(Live)
		failures = []

		def run():
			try:
				worker.run()
			except BaseException as error:
				failures.append(error)
				ready.set()

		thread = Thread(target=run)
		thread.start()
		producer = factory()
		try:
			self.assertTrue(ready.wait(5))
			self.assertTrue(worker.running.wait(5))
			self.inspector, previous = inspector, self.inspector
			try:
				self.assertEqual(
					loads(self.fetch()[1])['rpc'],
					rpc,
				)
				payload = self.payload()
				payload['task'] = Live.name
				self.assertEqual(
					self.fetch(
						'POST',
						payload,
					)[0],
					200,
				)
				payload['mode'] = 'request'
				if rpc:
					status, body, headers = self.fetch(
						'POST',
						payload,
					)
					self.assertEqual(
						(
							status,
							loads(body)['result'],
						),
						(
							200,
							3,
						),
					)
					payload['body']['b'] = 0
					with self.assertLogs(level='WARNING'):
						self.assertEqual(
							self.fetch(
								'POST',
								payload,
							)[0],
							502,
						)
				else:
					self.assertEqual(
						self.fetch(
							'POST',
							payload,
						)[0],
						501,
					)
			finally:
				self.inspector = previous
		finally:
			worker.stop()
			thread.join(10)
			try:
				self.assertFalse(thread.is_alive())
				self.assertEqual(
					failures,
					[],
				)
				producer.connect()
				producer.delete_queue(Live.parameters['queue'])
			finally:
				producer.close()

	@skipUnless(
		environ.get('DEFSTREAM_RABBITMQ_TESTS') == '1',
		'Opt-in local RabbitMQ interactive test integration',
	)
	def test_live_rabbitmq_send_rpc_and_remote_error(self):
		from DefStream.Broker.Implements.RabbitMQ import (
			Connection,
			Configuration,
		)

		self.exercise_live(
			lambda: Connection(Configuration(
				host='127.0.0.1',
				port=5672,
				username='guest',
				password='guest',
			)),
			True,
		)

	@skipUnless(
		environ.get('DEFSTREAM_REDIS_TESTS') == '1',
		'Opt-in local Redis interactive test integration',
	)
	def test_live_redis_send_and_unsupported_rpc(self):
		from DefStream.Broker.Implements.Redis import (
			Connection,
			Configuration,
		)

		self.exercise_live(
			lambda: Connection(Configuration()),
			False,
		)


if __name__ == '__main__':
	main()
