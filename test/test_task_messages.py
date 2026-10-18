from os import environ
from threading import (
	Event,
	Thread,
)
from unittest import (
	TestCase,
	main,
	skipUnless,
)
from unittest.mock import (
	Mock,
	call,
)
from uuid import uuid4

from src.Broker import RemoteError
from src.Broker.Implements.RabbitMQ import (
	Configuration as RabbitConfiguration,
	Connection as RabbitConnection,
	Reject,
	Subscription as RabbitSubscription,
)
from src.Broker.Implements.Redis import (
	Configuration as RedisConfiguration,
	Connection as RedisConnection,
	Subscription as RedisSubscription,
)
from src.Worker import (
	declare,
	Run,
	RunComplete,
	ThreadPool,
	Worker,
	WorkerSetup,
	send,
	request,
)
from src.Worker import __all__ as worker_exports


class Task(
	Run,
	parameters={'queue': 'task'},
	on_error=Reject(),
):
	def run(
		self,
		a: int,
		b: int,
		fail: bool = False,
	):
		if fail:
			raise ValueError('Task failed')
		return a + b


class Declare(WorkerSetup):
	def __init__(self):
		self.ready = Event()

	def __call__(
		self,
		worker: Worker,
	) -> None:
		for task in worker.tasks:
			declare(
				task=task,
				broker=worker.broker,
			)
		self.ready.set()


class MessageTests(TestCase):
	def test_send_replaces_emit_without_compatibility_alias(self):
		self.assertIn(
			'send',
			worker_exports,
		)
		self.assertNotIn(
			'emit',
			worker_exports,
		)
		for connection in (
			RabbitConnection,
			RedisConnection,
		):
			self.assertTrue(hasattr(
				connection,
				'send',
			))
			self.assertFalse(hasattr(
				connection,
				'emit',
			))

	def test_declare_delegates_without_owning_connection(self):
		broker = Mock()
		broker.declare = Mock()
		declare(
			task=Task,
			broker=broker,
		)
		broker.declare.assert_called_once_with(Task.parameters)
		broker.connect.assert_not_called()
		broker.close.assert_not_called()
		self.assertFalse(hasattr(
			Worker,
			'declare',
		))
		broker.declare.side_effect = RuntimeError('declaration failed')
		with self.assertRaisesRegex(
			RuntimeError,
			'declaration failed',
		):
			declare(
				task=Task,
				broker=broker,
			)
		broker.close.assert_not_called()

	def test_declare_validates_task_before_calling_broker(self):
		broker = Mock()
		broker.declare = Mock()
		with self.assertRaises(TypeError):
			declare(
				task=Run,
				broker=broker,
			)

		class MissingParameters(Run):
			def run(self):
				pass

		with self.assertRaises(ValueError):
			declare(
				task=MissingParameters,
				broker=broker,
			)
		broker.declare.assert_not_called()

	def test_helpers_delegate_without_owning_connection(self):
		broker = Mock()
		broker.send = Mock()
		broker.request = Mock(return_value=3)
		for _ in range(1000):
			send(
				{
					'a': 1,
					'b': 2,
				},
				task=Task,
				broker=broker,
			)
		self.assertEqual(
			broker.send.call_count,
			1000,
		)
		broker.send.assert_called_with(
			{
				'a': 1,
				'b': 2,
			},
			Task.parameters,
		)
		self.assertEqual(
			request(
				{
					'a': 1,
					'b': 2,
				},
				task=Task,
				broker=broker,
				timeout=2,
			),
			3,
		)
		broker.connect.assert_not_called()
		broker.close.assert_not_called()
		broker.declare.assert_not_called()

	def test_invalid_inputs_and_unsupported_operations_are_explicit(self):
		for body in (
			None,
			[1],
			{1: 'invalid'},
		):
			with self.subTest(body=body), self.assertRaises(TypeError):
				send(
					body,
					task=Task,
					broker=Mock(),
				)
		for task in (
			Run,
			Task(),
			object,
		):
			with self.subTest(task=task), self.assertRaises(TypeError):
				send(
					{},
					task=task,
					broker=Mock(),
				)
		with self.assertRaisesRegex(
			NotImplementedError,
			'RPC',
		):
			request(
				{},
				task=Task,
				broker=RedisConnection(RedisConfiguration()),
			)
		with self.assertRaises(NotImplementedError):
			declare(
				task=Task,
				broker=object(),
			)

	def test_rabbit_send_reuses_one_confirmed_channel(self):
		connection = RabbitConnection(RabbitConfiguration(
			host='127.0.0.1',
			port=5672,
		))
		with self.assertRaises(RuntimeError):
			send(
				{},
				task=Task,
				broker=connection,
			)
		connection.connection = Mock()
		channel = connection.connection.channel.return_value
		for _ in range(1000):
			send(
				{
					'a': 1,
					'b': 2,
				},
				task=Task,
				broker=connection,
			)
		connection.connection.channel.assert_called_once()
		channel.confirm_delivery.assert_called_once()
		self.assertEqual(
			channel.basic_publish.call_count,
			1000,
		)
		self.assertTrue(channel.basic_publish.call_args.kwargs['mandatory'])
		channel.close.assert_not_called()
		channel.basic_publish.side_effect = RuntimeError('publish failure')
		with self.assertRaisesRegex(
			RuntimeError,
			'publish failure',
		):
			send(
				{},
				task=Task,
				broker=connection,
			)
		connection.close()

	def test_declare_dlq_closes_only_declaration_channel(self):
		connection = RabbitConnection(RabbitConfiguration(
			host='127.0.0.1',
			port=5672,
		))
		connection.connection = Mock()
		channel = connection.connection.channel.return_value
		connection.declare(RabbitSubscription(
			'task',
			error='task.error',
		))
		self.assertEqual(
			channel.queue_declare.call_args_list,
			[
				call(
					'task.error',
					durable=True,
				),
				call(
					'task',
					durable=True,
					arguments={
						'x-dead-letter-exchange': '',
						'x-dead-letter-routing-key': 'task.error',
					},
				),
			],
		)
		channel.close.assert_called_once()
		connection.connection.close.assert_not_called()
		connection.close()

	def test_confirmation_failure_releases_channel_without_closing_connection(self):
		connection = RabbitConnection(RabbitConfiguration(
			host='127.0.0.1',
			port=5672,
		))
		connection.connection = Mock()
		channel = connection.connection.channel.return_value
		channel.confirm_delivery.side_effect = RuntimeError('confirm failure')
		with self.assertRaisesRegex(
			RuntimeError,
			'confirm failure',
		):
			send(
				{},
				task=Task,
				broker=connection,
			)
		channel.close.assert_called_once()
		connection.connection.close.assert_not_called()
		self.assertIsNone(connection.publisher)
		connection.close()


@skipUnless(
	environ.get('DEFSTREAM_REDIS_TESTS') == '1',
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
				broker = RedisConnection(RedisConfiguration())
				broker.connect()
				try:
					send(
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
			RedisConnection(RedisConfiguration()),
			ThreadPool(2),
			setups=setup,
		)
		worker.add(First)
		worker.add(Next)
		client = RedisConnection(RedisConfiguration())
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
			send(
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
			for name in (
				first,
				second,
			):
				self.assertEqual(
					client.connected().xpending(
						name,
						'DefStream',
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
		connection = RedisConnection(RedisConfiguration())
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
				send(
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


@skipUnless(
	environ.get('DEFSTREAM_RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ integration',
)
class RabbitMessageTests(TestCase):
	def test_declare_send_request_and_dlq(self):
		name = 'defstream-send-' + uuid4().hex
		dlq = name + '.error'
		connection = RabbitConnection(RabbitConfiguration(
			host='127.0.0.1',
			port=5672,
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
				send(
					{
						'a': index,
						'b': 1,
					},
					task=Task,
					broker=connection,
				)
			channel = connection.connection.channel()
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
				'src.Worker.Worker',
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
			self.assertTrue(connection.connection.is_open)
		finally:
			worker.stop()
			if thread.ident is not None:
				thread.join(10)
			Task.parameters = old
			connection.delete_queue(name)
			connection.delete_queue(dlq)
			connection.close()


if __name__ == '__main__':
	main()
