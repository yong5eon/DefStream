from contextlib import redirect_stdout
from io import StringIO
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Broker.Implements.RabbitMQ import (
	Configuration as RabbitConfiguration,
	Connection as RabbitConnection,
	Reject,
	Subscription as RabbitSubscription,
)
from DefStream.Broker.Implements.Redis import (
	Configuration as RedisConfiguration,
	Connection as RedisConnection,
	Subscription as RedisSubscription,
)
from DefStream.Worker import (
	Run,
	Worker,
)
from DefStream.Worker.Startup import (
	LOGO,
	startup,
)


class StartupTests(TestCase):
	def worker(
		self,
		parameters,
	):
		class Task(
			Run,
			parameters=parameters,
			on_error=Reject(),
		):
			def run(self):
				pass

		pool = Mock()
		pool.size.return_value = 4
		worker = Worker(
			Mock(consumer=Mock()),
			pool,
		)
		worker.add(Task)
		return worker

	def test_banner_supports_subscription_formats_and_options(self):
		for parameters, options in (
			(
				RabbitSubscription(
					queue='rabbit.jobs',
					qos=0,
					offset=0,
					error='rabbit.errors',
				),
				(
					"queue='rabbit.jobs'",
					'qos=0',
					'offset=0',
					"error='rabbit.errors'",
				),
			),
			(
				RedisSubscription(
					queue='redis.jobs',
					group='workers',
				),
				(
					"queue='redis.jobs'",
					"group='workers'",
				),
			),
			(
				{
					'queue': 'mapping.jobs',
					'qos': 2,
					'password': 'do-not-print',
				},
				(
					"queue='mapping.jobs'",
					'qos=2',
				),
			),
			(
				'string.jobs',
				("queue='string.jobs'",),
			),
		):
			with self.subTest(parameters=parameters):
				worker = self.worker(parameters)
				stream = StringIO()
				with redirect_stdout(stream):
					worker.run()
				output = stream.getvalue()
				for expected in (
					LOGO.rstrip(),
					'Starting Worker',
					'concurrency=4',
					'Tasks: 1 tasks',
					'StartupTests.worker.<locals>.Task',
					'on_error=Reject',
					'Queues: 1 queues',
					*options,
				):
					self.assertIn(
						expected,
						output,
					)
				self.assertNotIn(
					'do-not-print',
					output,
				)

	def test_output_precedes_connection_setup_subscription_and_consumption(self):
		worker = self.worker('jobs')
		stream = StringIO()
		observed = []

		def check_startup():
			self.assertTrue(stream.getvalue().startswith(LOGO.rstrip() + '\n\nStarting Worker\n'))
			self.assertIn(
				"queue='jobs'",
				stream.getvalue(),
			)
			self.assertFalse(worker.running.is_set())
			observed.append('preparing')

		def check_consumption():
			self.assertIn(
				"  Queues: 1 queues\n    - 'jobs'\n",
				stream.getvalue(),
			)
			self.assertTrue(worker.running.is_set())
			observed.append('consuming')

		worker.broker.connect.side_effect = check_startup
		worker.setups = (lambda current: check_startup(),)
		consumer = worker.broker.consumer.return_value
		consumer.subs.side_effect = lambda *args: check_startup()
		consumer.run.side_effect = check_consumption
		with redirect_stdout(stream):
			worker.run()
		self.assertEqual(
			observed,
			[
				'preparing',
				'preparing',
				'preparing',
				'consuming',
			],
		)
		self.assertEqual(
			stream.getvalue().count('Starting Worker'),
			1,
		)
		with redirect_stdout(stream), self.assertRaises(RuntimeError):
			worker.run()
		self.assertEqual(
			stream.getvalue().count('Starting Worker'),
			1,
		)

	def test_failed_preparation_prints_banner_but_does_not_consume(self):
		for stage in (
			'connect',
			'subscribe',
		):
			with self.subTest(stage=stage):
				worker = self.worker('jobs')
				consumer = worker.broker.consumer.return_value
				action = worker.broker.connect if stage == 'connect' else consumer.subs
				action.side_effect = RuntimeError('preparation failed')
				stream = StringIO()
				with redirect_stdout(stream), self.assertRaisesRegex(
					RuntimeError,
					'preparation failed',
				):
					worker.run()
				self.assertIn(
					'Starting Worker',
					stream.getvalue(),
				)
				consumer.run.assert_not_called()
				worker.pool.stop.assert_called_once_with()
				worker.broker.close.assert_called_once_with()

	def test_stopped_worker_prints_banner_but_does_not_consume(self):
		worker = self.worker('jobs')
		worker.stop()
		stream = StringIO()
		with redirect_stdout(stream):
			worker.run()
		self.assertIn(
			'Starting Worker',
			stream.getvalue(),
		)
		worker.broker.consumer.return_value.run.assert_not_called()

	def test_custom_subscription_is_not_dumped_or_rejected_by_banner(self):
		worker = self.worker(object())
		stream = StringIO()
		with redirect_stdout(stream):
			worker.run()
		self.assertIn(
			'queue=<adapter-defined>',
			stream.getvalue(),
		)
		worker.broker.consumer.return_value.run.assert_called_once_with()

	def test_all_tasks_are_listed_and_known_queues_are_deduplicated(self):
		worker = self.worker('jobs')

		class Shared(
			Run,
			parameters={'queue': 'jobs'},
		):
			def run(self):
				pass

		class Other(
			Shared,
			parameters={'queue': 'other.jobs'},
		):
			pass

		worker.add(Shared)
		worker.add(Other)
		stream = StringIO()
		with redirect_stdout(stream):
			worker.run()
		output = stream.getvalue()
		self.assertIn(
			'Tasks: 3 tasks',
			output,
		)
		self.assertIn(
			"Queues: 2 queues\n    - 'jobs'\n    - 'other.jobs'",
			output,
		)
		for task in worker.tasks:
			self.assertIn(
				task.__qualname__,
				output,
			)
			self.assertNotIn(
				task.__module__ + '.' + task.__qualname__,
				output,
			)
		self.assertIn(
			'on_error=broker default',
			output,
		)

	def test_missing_tasks_do_not_print_a_startup_banner(self):
		worker = Worker(
			Mock(),
			Mock(),
		)
		stream = StringIO()
		with redirect_stdout(stream), self.assertRaisesRegex(
			RuntimeError,
			'Register at least one Run',
		):
			worker.run()
		self.assertEqual(
			stream.getvalue(),
			'',
		)

	def test_broker_summary_shows_adapter_and_only_endpoint_fields(self):
		for broker, expected in (
			(
				RabbitConnection(RabbitConfiguration(
					host='rabbit.local',
					port=5672,
					vhost='/jobs',
					username='private-user',
					password='private-password',
				)),
				'  Broker: RabbitMQ://rabbit.local:5672/jobs\n',
			),
			(
				RedisConnection(RedisConfiguration(
					host='redis.local',
					port=6379,
					username='private-user',
					password='private-password',
				)),
				'  Broker: Redis://redis.local:6379',
			),
			(
				RabbitConnection(RabbitConfiguration(
					host='127.0.0.1',
					port=5672,
				)),
				'  Broker: RabbitMQ://127.0.0.1:5672/\n',
			),
			(
				RedisConnection(RedisConfiguration(
					host='::1',
					port=6379,
				)),
				'  Broker: Redis://[::1]:6379',
			),
		):
			with self.subTest(broker=type(broker)):
				worker = self.worker('jobs')
				worker.broker = broker
				stream = StringIO()
				with redirect_stdout(stream):
					startup(worker)
				output = stream.getvalue()
				self.assertIn(
					expected,
					output,
				)
				for hidden in (
					'private-user',
					'private-password',
					'DefStream.Broker.Implements',
					'    HOST:',
					'    PORT:',
					'VHOST:',
				):
					self.assertNotIn(
						hidden,
						output,
					)

	def test_rabbitmq_vhost_is_appended_only_when_present(self):
		for vhost, suffix in (
			(
				'jobs',
				'/jobs',
			),
			(
				'/jobs',
				'/jobs',
			),
			(
				'/',
				'/',
			),
			(
				'',
				'',
			),
			(
				None,
				'',
			),
		):
			with self.subTest(vhost=vhost):
				conf = RabbitConfiguration(
					host='127.0.0.1',
					port=5672,
				)
				worker = self.worker('jobs')
				worker.broker = RabbitConnection(conf)
				conf.vhost = vhost
				stream = StringIO()
				with redirect_stdout(stream):
					startup(worker)
				self.assertIn(
					f'  Broker: RabbitMQ://127.0.0.1:5672{suffix}\n  Pool:',
					stream.getvalue(),
				)

	def test_custom_broker_without_configuration_uses_qualname(self):
		class Broker:
			pass

		worker = self.worker('jobs')
		worker.broker = Broker()
		stream = StringIO()
		with redirect_stdout(stream):
			startup(worker)
		self.assertIn(
			f'  Broker: {Broker.__qualname__}\n  Pool:',
			stream.getvalue(),
		)


if __name__ == '__main__':
	main()
