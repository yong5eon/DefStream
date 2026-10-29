from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import (
	Event,
	Thread,
)
from time import sleep
from unittest import (
	TestCase,
	main,
	skipUnless,
)
from uuid import uuid4

from DefStream.Broker import RemoteError
from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
	ExchangeType,
	Reject,
	Subscription,
)
from DefStream.Worker import (
	ProcessPool,
	Run,
	ThreadPool,
	Worker,
)
from tests._support import require_value


class RpcRun(Run):
	def run(
		self,
		a=0,
		b=0,
		fail=False,
		path=None,
		empty=False,
		delay=0,
	):
		if delay:
			sleep(delay)
		if fail:
			raise ValueError('private server error')
		if path is not None and not Path(path).exists():
			Path(path).touch()
			raise ValueError('retry once')
		return None if empty else a + b


class RejectRun(
	RpcRun,
	on_error=Reject(),
):
	pass


@skipUnless(
	environ.get('DEFSTREAM_RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ integration',
)
class RpcIntegrationTests(TestCase):
	def test_rpc_success_none_requeue_remote_error_timeout_and_unroutable(self):
		from pika.exceptions import UnroutableError

		for pool_class in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(pool=pool_class), TemporaryDirectory() as directory:
				client = Connection(Configuration(
					host='127.0.0.1',
					port=5672,
					username='guest',
					password='guest',
				))
				client.connect()
				names = [
					'defstream-rpc-' + uuid4().hex
					for index in range(3)
				]
				channel = require_value(client.connection).channel()
				exchange = 'defstream-rpc-' + uuid4().hex
				worker = Worker(
					Connection(client.conf),
					pool_class(2),
				)
				thread = None
				failures = []
				ready = Event()

				def start():
					try:
						worker.run()
					except BaseException as error:
						failures.append(error)

				try:
					for name in names:
						channel.queue_declare(
							name,
							arguments={'x-expires': 60000},
						)
					client.create_exchange(
						exchange,
						ExchangeType.Direct,
					)
					client.bind_exchange_to_queue(
						exchange,
						names[0],
						event='add',
					)
					for run, name in zip(
						(
							RpcRun,
							RejectRun,
						),
						names,
					):
						self.addCleanup(
							setattr,
							run,
							'parameters',
							run.parameters,
						)
						run.parameters = Subscription(name)
						worker.add(run)
					worker.setups = (lambda owner: ready.set(),)
					thread = Thread(target=start)
					thread.start()
					self.assertTrue(ready.wait(10))
					queue = client.queue(names[0])
					self.assertEqual(
						queue.call(
							{
								'a': 2,
								'b': 5,
							},
							timeout=10,
						),
						7,
					)
					self.assertIsNone(queue.call(
						{'empty': True},
						timeout=10,
					))
					self.assertEqual(
						client.exchange(exchange).call(
							{
								'a': 8,
								'b': 9,
							},
							timeout=10,
							event='add',
						),
						17,
					)
					with self.assertRaises(UnroutableError):
						client.exchange(exchange).call(
							{},
							timeout=2,
							event='missing',
						)
					with self.assertLogs(
						'Worker',
						level='ERROR',
					):
						self.assertEqual(
							queue.call(
								{
									'a': 4,
									'b': 6,
									'path': str(Path(directory) / 'retried'),
								},
								timeout=10,
							),
							10,
						)
						with self.assertRaises(RemoteError) as caught:
							client.queue(names[1]).call(
								{'fail': True},
								timeout=10,
							)
					self.assertEqual(
						caught.exception.code,
						'ProcessingError',
					)
					self.assertNotIn(
						'private server error',
						str(caught.exception),
					)
					with self.assertRaises(TimeoutError):
						client.queue(names[2]).call(
							{},
							timeout=0.2,
						)
					with self.assertRaises(UnroutableError):
						client.queue('defstream-missing-' + uuid4().hex).call(
							{},
							timeout=2,
						)
					with self.assertLogs(
						'Broker.RabbitMQ.Consumer',
						level='WARNING',
					):
						with self.assertRaises(TimeoutError):
							queue.call(
								{'delay': 0.5},
								timeout=0.2,
							)
						self.assertEqual(
							queue.call(
								{
									'a': 1,
									'b': 1,
								},
								timeout=10,
							),
							2,
						)
					worker.stop()
					thread.join(15)
					self.assertFalse(thread.is_alive())
					self.assertEqual(
						failures,
						[],
					)
				finally:
					if thread is not None and thread.is_alive():
						worker.stop()
						thread.join(15)
					for name in names:
						channel.queue_delete(name)
					channel.exchange_delete(exchange)
					client.close()


if __name__ == '__main__':
	main()
