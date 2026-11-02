from os import environ
from threading import (
	Event,
	Thread,
)
from unittest import (
	TestCase,
	skipUnless,
)
from uuid import uuid4

from DefStream.Broker import RemoteError
from DefStream.Worker import (
	ThreadPool,
	Worker,
	WorkerSetup,
	request,
)
from tests._support import rabbitmq_test_port
from tests.test_specifications import Add


@skipUnless(
	environ.get('RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ Specification integration',
)
class SpecificationRPCTests(TestCase):
	def test_validation_and_transformed_response_over_real_rpc(self):
		from DefStream.Broker.Implements.RabbitMQ import (
			Connection,
			Configuration,
			Reject,
		)

		class Checked(
			Add,
			parameters={'queue': 'defstream-spec-' + uuid4().hex},
			on_error=Reject(),
		):
			pass

		connection = Connection(Configuration(
			host='127.0.0.1',
			port=rabbitmq_test_port(),
			username='guest',
			password='guest',
		))
		connection.connect()
		ready = Event()
		worker_broker = Connection(connection.conf)

		class Prepare(WorkerSetup):
			def __call__(self, worker: Worker) -> None:
				worker_broker.declare(Checked.parameters)
				ready.set()

		worker = Worker(
			worker_broker,
			ThreadPool(1),
			setups=Prepare(),
		)
		worker.add(Checked)
		failures = []

		def run():
			try:
				worker.run()
			except BaseException as error:
				failures.append(error)
				ready.set()

		thread = Thread(target=run)
		thread.start()
		try:
			self.assertTrue(ready.wait(5))
			self.assertEqual(
				request(
					{'a': '3'},
					task=Checked,
					broker=connection,
					timeout=5,
				),
				5,
			)
			with self.assertLogs(
				'Worker',
				level='ERROR',
			), self.assertRaises(RemoteError):
				request(
					{'a': 'invalid'},
					task=Checked,
					broker=connection,
					timeout=5,
				)
		finally:
			worker.stop()
			thread.join(10)
			try:
				self.assertFalse(thread.is_alive())
				self.assertEqual(
					failures,
					[],
				)
				connection.delete_queue(Checked.parameters['queue'])
			finally:
				connection.close()
