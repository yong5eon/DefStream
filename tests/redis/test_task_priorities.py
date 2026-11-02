from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Broker.Implements.Redis import (
	Configuration,
	Connection,
)
from DefStream.Worker import (
	Run,
	declare,
	emit,
)


class Task(
	Run,
	parameters={'queue': 'priority-test'},
):
	def run(
		self,
		**kwargs,
	):
		return kwargs


class RedisTaskPriorityTests(TestCase):
	def test_priority_is_rejected_before_io_and_regular_send_still_works(self):
		broker = Connection(Configuration())
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


if __name__ == '__main__':
	main()
