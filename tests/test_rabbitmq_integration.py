import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from time import (
	monotonic,
	sleep,
)
from unittest import (
	TestCase,
	main,
	skipUnless,
)
from uuid import uuid4

import pika

from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
	Reject,
	Subscription,
)
from DefStream.Worker import (
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
)


class IntegrationRunner(Run, parameters=Subscription(queue='integration')):
	def run(self, path, retry=False, fail=False):
		output = Path(path)
		if fail:
			raise ValueError('integration rejection')
		if retry and not output.exists():
			output.write_text('retry', encoding='utf-8')
			raise ValueError('integration requeue')
		output.write_text('done', encoding='utf-8')


class RejectIntegrationRunner(
	IntegrationRunner,
	on_error=Reject(),
):
	pass


@skipUnless(os.environ.get('DEFSTREAM_RABBITMQ_TESTS') == '1', 'Opt-in local RabbitMQ integration')
class RabbitMQIntegrationTests(TestCase):
	def test_real_consumption_requeue_reject_and_shutdown(self):
		for pool_cls in (ThreadPool, ProcessPool):
			with self.subTest(pool=pool_cls), TemporaryDirectory() as directory:
				connection = pika.BlockingConnection(pika.ConnectionParameters(
					host='127.0.0.1',
					credentials=pika.PlainCredentials('guest', 'guest'),
				))
				channel = connection.channel()
				prefix = 'defstream-test-' + uuid4().hex
				queue, rejected, dead = prefix, prefix + '-reject', prefix + '-dead'
				created = []
				thread = None
				worker = None
				errors = []
				try:
					for name in (queue, dead, rejected):
						channel.queue_declare(
							name,
							arguments={
								'x-expires': 60000,
								**({
									'x-dead-letter-exchange': '',
									'x-dead-letter-routing-key': dead,
								} if name == rejected else {}),
							},
						)
						created.append(name)
					self.addCleanup(setattr, IntegrationRunner, 'parameters', IntegrationRunner.parameters)
					self.addCleanup(setattr, RejectIntegrationRunner, 'parameters', RejectIntegrationRunner.parameters)
					IntegrationRunner.parameters = Subscription(queue)
					RejectIntegrationRunner.parameters = Subscription(rejected)
					worker = Worker(
						Connection(Configuration('127.0.0.1', 5672, 'guest', 'guest')),
						pool_cls(2),
					)
					worker.add(IntegrationRunner)
					worker.add(RejectIntegrationRunner)
					path = str(Path(directory) / 'result')
					for target, payload in (
						(queue, {'path': path, 'retry': True}),
						(rejected, {'path': path, 'fail': True}),
					):
						channel.basic_publish(
							'', target, json.dumps(payload).encode('utf-8'),
							pika.BasicProperties(
								content_type='application/json', content_encoding='utf-8', headers={},
							),
						)

					def run():
						try:
							worker.run()
						except Exception as error:
							errors.append(error)

					thread = Thread(target=run)
					with self.assertLogs('Worker', level='ERROR') as logs:
						thread.start()
						dead_letter = None
						deadline = monotonic() + 15
						while monotonic() < deadline:
							if dead_letter is None:
								dead_letter, _, _ = channel.basic_get(dead, auto_ack=True)
							if dead_letter is not None and Path(path).exists():
								if Path(path).read_text(encoding='utf-8') == 'done':
									break
							if errors:
								break
							sleep(0.01)
						worker.stop()
						thread.join(15)
					self.assertFalse(thread.is_alive(), 'Worker did not shut down')
					self.assertEqual(errors, [])
					self.assertIsNotNone(dead_letter, 'Rejected delivery did not reach DLQ')
					self.assertEqual(Path(path).read_text(encoding='utf-8'), 'done')
					self.assertEqual(len(logs.records), 2)
					for name in (queue, rejected):
						state = channel.queue_declare(name, passive=True).method
						self.assertEqual(state.message_count, 0)
						self.assertEqual(state.consumer_count, 0)
				finally:
					if thread is not None and thread.is_alive():
						worker.stop()
						thread.join(15)
					for name in reversed(created):
						channel.queue_delete(name)
					connection.close()


if __name__ == '__main__':
	main()
