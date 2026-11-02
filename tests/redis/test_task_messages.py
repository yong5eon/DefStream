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

from DefStream.Broker.Implements.Redis import (
	Configuration as RedisConfiguration,
	Connection as RedisConnection,
	Subscription as RedisSubscription,
)
from DefStream.Worker import (
	Run,
	RunComplete,
	ThreadPool,
	Worker,
	declare,
	emit,
	request,
)
from tests._support import redis_test_port
from tests._support_task_messages import (
	Declare,
	Task,
)


class RedisConnectionApiTests(TestCase):
	def test_connection_exposes_emit_without_send_alias(self):
		self.assertTrue(hasattr(RedisConnection, 'emit'))
		self.assertFalse(hasattr(RedisConnection, 'send'))


@skipUnless(
	environ.get('REDIS_TESTS') == '1',
	'Opt-in local Redis integration',
)
class RedisMessageTests(TestCase):
	def test_completion_hook_sends_to_next_task(self):
		prefix = 'defstream-chain-' + uuid4().hex
		first = prefix + '-first'
		second = prefix + '-second'
		finished = Event()
		results = []

		class Next(
			Run,
			parameters=RedisSubscription(second),
		):
			def run(
				self,
				result: int,
			):
				results.append(result)
				finished.set()

		class SendNext(RunComplete):
			def __call__(
				self,
				context,
				completion,
			):
				broker = RedisConnection(RedisConfiguration(port=redis_test_port()))
				broker.connect()
				try:
					emit(
						completion,
						task=Next,
						broker=broker,
					)
				finally:
					broker.close()

		class First(
			Run,
			parameters=RedisSubscription(first),
			completes=SendNext(),
		):
			def run(
				self,
				a: int,
				b: int,
			):
				return {'result': a + b}

		setup = Declare()
		worker = Worker(
			RedisConnection(RedisConfiguration(port=redis_test_port())),
			ThreadPool(2),
			setups=setup,
		)
		worker.add(First)
		worker.add(Next)
		client = RedisConnection(RedisConfiguration(port=redis_test_port()))
		client.connect()
		errors = []

		def run():
			try:
				worker.run()
			except Exception as error:
				errors.append(error)
				setup.ready.set()
				finished.set()

		thread = Thread(target=run)
		try:
			thread.start()
			self.assertTrue(setup.ready.wait(10))
			emit(
				{
					'a': 2,
					'b': 5,
				},
				task=First,
				broker=client,
			)
			self.assertTrue(finished.wait(10))
			worker.stop()
			thread.join(10)
			self.assertFalse(thread.is_alive())
			self.assertEqual(
				errors,
				[],
			)
			self.assertEqual(
				results,
				[7],
			)
			for task in (
				First,
				Next,
			):
				subscription = RedisSubscription.parse(task.parameters)
				self.assertEqual(
					client.connected().xpending(
						subscription.queue,
						subscription.group,
					)['pending'],
					0,
				)
		finally:
			worker.stop()
			thread.join(10)
			client.delete_queue(first)
			client.delete_queue(second)
			client.close()

	def test_declare_and_send_1000_on_borrowed_connection(self):
		name = 'defstream-send-' + uuid4().hex
		connection = RedisConnection(RedisConfiguration(port=redis_test_port()))
		connection.connect()
		old = Task.parameters
		Task.parameters = RedisSubscription(
			name,
			group='send-test',
		)
		try:
			worker = Worker(
				connection,
				ThreadPool(1),
			)
			worker.add(Task)
			declare(
				task=Task,
				broker=connection,
			)
			for index in range(1000):
				emit(
					{
						'a': index,
						'b': 1,
					},
					task=Task,
					broker=connection,
				)
			self.assertEqual(
				connection.connected().xlen(name),
				1000,
			)
			self.assertEqual(
				connection.connected().xinfo_groups(name)[0]['name'],
				b'send-test',
			)
			with self.assertRaises(NotImplementedError):
				request(
					{},
					task=Task,
					broker=connection,
				)
			self.assertTrue(connection.connected().ping())
			worker.pool.stop()
		finally:
			Task.parameters = old
			connection.delete_queue(name)
			connection.close()
