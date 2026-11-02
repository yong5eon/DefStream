from contextlib import nullcontext
from importlib import import_module
from io import BytesIO
from json import loads
from unittest import (
	TestCase,
	main,
)
from unittest.mock import (
	patch,
)
from DefStream.Broker.Errors import RemoteError
from DefStream.Inspector.Extensions import (
	Play,
	Specifications,
)
from tests._support_inspector_play import (
	NamedTask,
	PlayExtensionSupport,
	Producer,
	RPCProducer,
	TOKEN,
)


class PlayExtensionTests(PlayExtensionSupport, TestCase):

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
		self.assertIn(
			b'DefStream Inspector &middot; Play',
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
		self.inspector.exts['/play'] = Play(
			'/play',
			broker=RPCProducer,
			token=TOKEN,
			title='My <Worker> & {{play_description}}',
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
			b'<title>My &lt;Worker&gt; &amp; {{play_description}}</title>',
			body,
		)
		self.assertIn(
			b'<h1 id="title">My &lt;Worker&gt; &amp; {{play_description}}</h1>',
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
			b' - Play',
			body,
		)

	def test_html_is_read_again_on_each_refresh(self):
		with patch.object(
			import_module('DefStream.Inspector.Extensions.Play'),
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
			resources.return_value.joinpath.assert_called_with('Play.html')

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
				'Worker.Inspector.Play',
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
			Play(
				'/play',
				broker=RPCProducer,
			),
			Play(
				'/play',
				broker=RPCProducer,
				token=None,
			),
		):
			self.extension = extension
			self.inspector.exts['/play'] = self.extension
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
			'Worker.Inspector.Play',
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
			Play(
				'/play',
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
			'Worker.Inspector.Play',
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
			'Worker.Inspector.Play',
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
				'Worker.Inspector.Play',
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
			'Worker.Inspector.Play',
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
				'Worker.Inspector.Play',
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
			'Worker.Inspector.Play',
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
				'Worker.Inspector.Play',
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
			'Worker.Inspector.Play',
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



if __name__ == '__main__':
	main()
