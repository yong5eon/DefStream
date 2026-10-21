from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Broker.Implements.RabbitMQ import (
	Configuration,
	Connection,
	Subscription,
)
from DefStream.Broker.Implements.Redis import (
	Configuration as RedisConfiguration,
	Connection as RedisConnection,
)
from DefStream.Worker import (
	Run,
	declare,
	request,
	emit,
)


class Task(
	Run,
	parameters=Subscription('priority-test'),
):
	def run(
		self,
		**kwargs,
	):
		return kwargs


class TaskPriorityTests(TestCase):
	def broker(self):
		broker = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
		))
		broker.connection = Mock()
		self.addCleanup(broker.close)
		return broker

	def test_default_only_declares_broker_maximum_including_zero(self):
		for default in (
			0,
			3,
			255,
		):
			with self.subTest(default=default):
				class DefaultTask(
					Task,
					parameters=Subscription(
						'priority-test',
						priority=default,
					),
				):
					pass

				broker = self.broker()
				declare(
					task=DefaultTask,
					broker=broker,
				)
				assert isinstance(
					broker.connection,
					Mock,
				)
				channel = broker.connection.channel.return_value
				self.assertEqual(
					channel.queue_declare.call_args.kwargs['arguments'],
					{'x-max-priority': 255},
				)
				for override in (
					None,
					0,
					255,
				):
					emit(
						{'value': 1},
						task=DefaultTask,
						broker=broker,
						priority=override,
					)
					self.assertEqual(
						channel.basic_publish.call_args.kwargs['properties'].priority,
						default if override is None else override,
					)
				self.assertEqual(
					DefaultTask.parameters.max_priority,
					255,
				)
		return

	def test_maximum_only_preserves_none_and_validates_overrides(self):
		class MaximumTask(
			Task,
			parameters=Subscription(
				'priority-test',
				max_priority=5,
			),
		):
			pass

		self.assertIsNone(MaximumTask.parameters.priority)
		self.assertFalse(hasattr(
			Run,
			'priority',
		))
		broker = self.broker()
		emit(
			{},
			task=MaximumTask,
			broker=broker,
		)
		assert isinstance(
			broker.connection,
			Mock,
		)
		channel = broker.connection.channel.return_value
		self.assertIsNone(channel.basic_publish.call_args.kwargs['properties'].priority)
		with self.assertRaises(ValueError):
			emit(
				{},
				task=MaximumTask,
				broker=broker,
				priority=6,
			)
		self.assertEqual(
			channel.basic_publish.call_count,
			1,
		)
		return

	def test_rpc_default_and_override_reach_queue_call(self):
		class RpcTask(
			Task,
			parameters={
				'queue': 'priority-test',
				'max_priority': 5,
				'priority': 3,
			},
		):
			pass

		broker = self.broker()
		queue = Mock()
		broker.queue = Mock(return_value=queue)
		queue.call.return_value = {'result': 4}
		for override in (
			None,
			0,
			5,
		):
			result = request(
				{'value': 4},
				task=RpcTask,
				broker=broker,
				timeout=2,
				priority=override,
			)
			self.assertEqual(
				result,
				{'result': 4},
			)
			queue.call.assert_called_with(
				{'value': 4},
				timeout=2,
				priority=3 if override is None else override,
			)
		with self.assertRaises(ValueError):
			request(
				{},
				task=RpcTask,
				broker=broker,
				priority=6,
			)
		return

	def test_call_only_checks_broker_range_without_declaration(self):
		broker = self.broker()
		for value in (
			0,
			255,
		):
			emit(
				{},
				task=Task,
				broker=broker,
				priority=value,
			)
		assert isinstance(
			broker.connection,
			Mock,
		)
		channel = broker.connection.channel.return_value
		channel.queue_declare.assert_not_called()
		for value in (
			-1,
			256,
			True,
			1.5,
			'1',
		):
			with self.subTest(value=value), self.assertRaises((
				TypeError,
				ValueError,
			)):
				emit(
					{},
					task=Task,
					broker=broker,
					priority=value,  # pyright: ignore[reportArgumentType]
				)
		self.assertEqual(
			channel.basic_publish.call_count,
			2,
		)
		return

	def test_redis_rejects_priority_before_io_and_legacy_send_still_works(self):
		broker = RedisConnection(RedisConfiguration())
		broker.connection = Mock()
		self.addCleanup(broker.close)
		broker.connection.xadd.return_value = b'1-0'
		class DefaultTask(
			Task,
			parameters={
				'queue': 'priority-test',
				'priority': 1,
			},
		):
			pass

		for task in (
			DefaultTask,
			type(
				'MaximumTask',
				(Task,),
				{
					'parameters': {
						'queue': 'priority-test',
						'max_priority': 5,
					},
				},
			),
		):
			with self.subTest(task=task):
				with self.assertRaises(NotImplementedError):
					declare(
						task=task,
						broker=broker,
					)
				with self.assertRaises(NotImplementedError):
					emit(
						{},
						task=task,
						broker=broker,
					)
		with self.assertRaises(NotImplementedError):
			emit(
				{},
				task=Task,
				broker=broker,
				priority=0,
			)
		broker.connection.xadd.assert_not_called()
		broker.connection.xgroup_create.assert_not_called()
		class RedisTask(
			Task,
			parameters={'queue': 'priority-test'},
		):
			pass

		self.assertEqual(
			emit(
				{},
				task=RedisTask,
				broker=broker,
			),
			'1-0',
		)
		return

	def test_settings_inherit_and_cannot_be_cleared(self):
		class Parent(
			Task,
			parameters=Subscription(
				'priority-test',
				max_priority=5,
				priority=3,
			),
		):
			pass

		class Child(Parent):
			pass

		class Override(
			Parent,
			parameters=Subscription(
				'priority-test',
				max_priority=5,
				priority=0,
			),
		):
			pass

		self.assertEqual(
			Child.parameters.priority,
			3,
		)
		self.assertEqual(
			Override.parameters.priority,
			0,
		)
		self.assertEqual(
			Child.parameters.max_priority,
			5,
		)
		with self.assertRaises(ValueError):
			class ClearDefault(
				Parent,
				parameters=Subscription(
					'priority-test',
					max_priority=5,
				),
			):
				pass

		with self.assertRaises(ValueError):
			class ClearMaximum(
				Parent,
				parameters=Subscription('other'),
			):
				pass
		return

	def test_invalid_task_defaults_fail_before_publication(self):
		for value in (
			True,
			'1',
			1.5,
			-1,
		):
			with self.subTest(value=value), self.assertRaises((
				TypeError,
				ValueError,
			)):
				type(
					'InvalidTask',
					(Task,),
					{
						'parameters': {
							'queue': 'priority-test',
							'priority': value,
						},
					},
				)
		with self.assertRaises(ValueError):
			class AboveMaximum(
				Task,
				parameters=Subscription(
					'priority-test',
					max_priority=2,
					priority=3,
				),
			):
				pass

		class AboveBroker(
			Task,
			parameters={
				'queue': 'priority-test',
				'priority': 256,
			},
		):
			pass

		broker = self.broker()
		with self.assertRaises(ValueError):
			declare(
				task=AboveBroker,
				broker=broker,
			)
		assert isinstance(
			broker.connection,
			Mock,
		)
		broker.connection.channel.assert_not_called()
		return


if __name__ == '__main__':
	main()
