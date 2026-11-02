from http.client import HTTPConnection
from json import dumps, loads
from threading import (
	Event,
	Thread,
)
from typing import Optional
from unittest.mock import Mock
from uuid import uuid4

from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import Play
from DefStream.Worker import (
	Run,
	Specification,
	ThreadPool,
	Worker,
	WorkerSetup,
)
from tests._support import (
	RejectPolicy,
	require_value,
)

TOKEN = 'test-token-at-least-32-characters!'


class Task(
	Run,
	parameters={'queue': 'test'},
	request=Specification(example={
		'a': 6,
		'b': 2,
	}),
	response=Specification(),
	on_error=RejectPolicy(),
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


class PlayExtensionSupport:
	def setUp(self):
		self.producers = []

		def factory():
			producer = RPCProducer()
			self.producers.append(producer)
			return producer

		self.extension = Play(
			'/play',
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
				'/play',
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

		extension = Play(
			'/play',
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
		return
