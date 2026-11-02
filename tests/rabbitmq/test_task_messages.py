from os import environ
from threading import (
	Thread,
)
from unittest import (
	TestCase,
	skipUnless,
)
from uuid import uuid4

from DefStream.Broker import (
	RemoteError,
)
from DefStream.Broker.Implements.RabbitMQ import (
	Configuration as RabbitConfiguration,
	Connection as RabbitConnection,
	Subscription as RabbitSubscription,
)
from DefStream.Worker import (
	ThreadPool,
	Worker,
	emit,
	request,
)
from tests._support import (
	rabbitmq_test_port,
	require_value,
)
from tests.test_task_messages import (
	Declare,
	Task,
)


@skipUnless(
	environ.get('RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ integration',
)
class RabbitMessageTests(TestCase):
	def test_declare_send_request_and_dlq(self):
		name = 'defstream-send-' + uuid4().hex
		dlq = name + '.error'
		connection = RabbitConnection(RabbitConfiguration(
			host='127.0.0.1',
			port=rabbitmq_test_port(),
			username='guest',
			password='guest',
		))
		connection.connect()
		old = Task.parameters
		Task.parameters = RabbitSubscription(
			name,
			error=dlq,
		)
		setup = Declare()
		worker = Worker(
			RabbitConnection(connection.conf),
			ThreadPool(2),
			setups=setup,
		)
		worker.add(Task)
		errors = []

		def run():
			try:
				worker.run()
			except Exception as error:
				errors.append(error)
				setup.ready.set()

		thread = Thread(target=run)
		try:
			# Repeated declarations are safe and do not accumulate channels.
			connection.declare(Task.parameters)
			for index in range(1000):
				emit(
					{
						'a': index,
						'b': 1,
					},
					task=Task,
					broker=connection,
				)
			transport = require_value(connection.connection)
			channel = transport.channel()
			self.assertEqual(
				channel.queue_declare(
					name,
					passive=True,
				).method.message_count,
				1000,
			)
			channel.queue_purge(name)
			thread.start()
			self.assertTrue(setup.ready.wait(10))
			self.assertEqual(
				errors,
				[],
			)
			self.assertEqual(
				request(
					{
						'a': 2,
						'b': 5,
					},
					task=Task,
					broker=connection,
					timeout=10,
				),
				7,
			)
			with self.assertLogs(
				'Worker',
				level='ERROR',
			), self.assertRaises(RemoteError):
				request(
					{
						'a': 1,
						'b': 0,
						'fail': True,
					},
					task=Task,
					broker=connection,
					timeout=10,
				)
			worker.stop()
			thread.join(10)
			self.assertFalse(thread.is_alive())
			self.assertEqual(
				errors,
				[],
			)
			self.assertEqual(
				channel.queue_declare(
					dlq,
					passive=True,
				).method.message_count,
				1,
			)
			self.assertTrue(transport.is_open)
		finally:
			worker.stop()
			if thread.ident is not None:
				thread.join(10)
			Task.parameters = old
			connection.delete_queue(name)
			connection.delete_queue(dlq)
			connection.close()
