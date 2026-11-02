from collections.abc import Callable
from http.client import HTTPConnection
from threading import (
	Event,
	Thread,
)
from time import (
	monotonic,
	sleep,
)
from typing import Protocol
from uuid import uuid4

from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import (
	Metrics,
	Ping,
)
from DefStream.Worker import (
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
	WorkerSetup,
)
from tests._support import (
	RejectPolicy,
	require_instance,
	require_value,
)


class Divide(
	Run,
	parameters={'queue': 'divide'},
	on_error=RejectPolicy(),
):
	def run(
		self,
		a: int,
		b: int,
	):
		return a / b


class LiveConnection(Protocol):
	def connect(self) -> None: ...

	def close(self) -> None: ...

	def declare(self, parameters: object) -> None: ...

	def emit(
		self,
		body: object,
		parameters: object,
	) -> object: ...

	def delete_queue(
		self,
		name: str,
		/,
	) -> object: ...


class InspectorIntegrationSupport:
	def launch(
		self,
		worker: Worker,
	) -> Thread:
		failures: list[BaseException] = []

		def run() -> None:
			try:
				worker.run()
			except BaseException as error:
				failures.append(error)
			return

		thread = Thread(target=run)
		thread.start()

		def cleanup() -> None:
			if thread.is_alive():
				worker.stop()
				thread.join(10)
			self.assertFalse(thread.is_alive())
			self.assertEqual(
				failures,
				[],
			)
			return

		self.addCleanup(cleanup)
		return thread

	def fetch(
		self,
		inspector: Inspector,
		path: str,
		method: str = 'GET',
	):
		server = require_value(inspector.server)
		connection = HTTPConnection(
			'127.0.0.1',
			server.server_port,
			timeout=3,
		)
		try:
			connection.request(
				method,
				path,
			)
			response = connection.getresponse()
			return response.status, response.read(), dict(response.getheaders())
		finally:
			connection.close()

	def exercise_live_broker(
		self,
		connection: Callable[[], LiveConnection],
	) -> None:
		producer = connection()
		producer.connect()
		worker_broker = connection()
		name = 'defstream-inspector-' + uuid4().hex
		original = Divide.parameters
		Divide.parameters = {'queue': name}
		inspector = Inspector(
			port=0,
			exts=(
				Ping('/ping'),
				Metrics('/stats'),
			),
		)

		class Prepare(WorkerSetup):
			def __call__(self, worker: Worker) -> None:
				worker_broker.declare(Divide.parameters)

		worker = Worker(
			worker_broker,
			ProcessPool(1),
			setups=Prepare(),
			inspector=inspector,
		)
		worker.add(Divide)
		thread = self.launch(worker)
		try:
			deadline = monotonic() + 10
			while not worker.running.wait(0.01):
				self.assertFalse(worker.finished.is_set())
				self.assertLess(
					monotonic(),
					deadline,
				)
			self.assertEqual(
				self.fetch(
					inspector,
					'/ping',
				)[0],
				200,
			)
			task = Divide.name
			with self.assertLogs(
				'Worker',
				level='ERROR',
			):
				for divisor in (
					2,
					0,
				):
					producer.emit(
						{
							'a': 10,
							'b': divisor,
						},
						Divide.parameters,
					)
				deadline = monotonic() + 15
				metrics = require_instance(inspector.exts['/stats'], Metrics)
				while True:
					with metrics.lock:
						stats = metrics.tasks[task]
						done = stats.success == 1 and stats.failure == 1 and stats.active == 0
					if done:
						break
					self.assertLess(
						monotonic(),
						deadline,
					)
					sleep(0.01)
				settled = Event()
				require_value(worker.consumer).call(settled.set)
				self.assertTrue(settled.wait(5))
			self.assertEqual(
				self.fetch(
					inspector,
					'/ping',
				)[0],
				200,
			)
			status, body, headers = self.fetch(
				inspector,
				'/stats',
			)
			self.assertEqual(
				status,
				200,
			)
			self.assertIn(
				b'outcome="success"} 1',
				body,
			)
			self.assertIn(
				b'outcome="failure"} 1',
				body,
			)
		finally:
			worker.stop()
			thread.join(10)
			try:
				self.assertFalse(thread.is_alive())
				producer.delete_queue(name)
			finally:
				producer.close()
				Divide.parameters = original
		return
