from os import environ
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

from DefStream.Broker.Implements.Redis import (
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
from _support import require_value


class RedisRunner(
	Run,
	parameters=Subscription('integration'),
):
	def run(
		self,
		path: str,
		retry: bool = False,
		fail: bool = False,
	):
		output = Path(path)
		if fail:
			raise ValueError('Redis integration rejection')
		if retry and not output.exists():
			output.write_text('retry')
			raise ValueError('Redis integration retry')
		output.write_text('done')


class RejectRedisRunner(
	RedisRunner,
	on_error=Reject(),
):
	pass


@skipUnless(
	environ.get('DEFSTREAM_REDIS_TESTS') == '1',
	'Opt-in local Redis integration',
)
class RedisIntegrationTests(TestCase):
	def setUp(self):
		self.broker = Connection(Configuration())
		self.broker.connect()
		self.addCleanup(self.broker.close)
		self.names = []

	def queue(self):
		name = 'defstream-test-' + uuid4().hex
		self.names.append(name)
		self.addCleanup(
			self.broker.delete_queue,
			name,
		)
		return self.broker.queue(
			name,
			group='integration',
		)

	def start(
		self,
		function,
	):
		errors = []

		def run():
			try:
				function()
			except Exception as error:
				errors.append(error)

		thread = Thread(target=run)
		thread.start()
		return (
			thread,
			errors,
		)

	def wait(
		self,
		condition,
		errors,
	):
		deadline = monotonic() + 15
		while monotonic() < deadline:
			if condition():
				return
			if errors:
				raise errors[0]
			sleep(0.01)
		self.fail('Timed out waiting for Redis integration')

	def test_send_pop_read_and_atomic_requeue(self):
		queue = self.queue()
		body = {
			'number': 42,
			'items': [
				True,
				None,
				'text',
			],
		}
		id = queue.send(body)
		event = require_value(queue.pop(timeout=200))
		self.assertEqual(
			event.id,
			id,
		)
		self.assertEqual(
			event.body,
			body,
		)
		event.nack()
		event.nack()
		retry = require_value(queue.pop(timeout=200))
		self.assertNotEqual(
			retry.id,
			id,
		)
		self.assertEqual(
			retry.body,
			body,
		)
		retry.reject()
		self.assertIsNone(queue.pop(timeout=20))
		self.assertEqual(
			self.broker.connected().xpending(
				str(queue),
				queue.group,
			)['pending'],
			0,
		)
		history = list(queue.read(timeout=30))
		self.assertEqual(
			[event.body for event in history],
			[
				body,
				body,
			],
		)

	def test_qos_callbacks_and_graceful_stop(self):
		queue = self.queue()
		for number in range(4):
			queue.send({'number': number})
		consumer = self.broker.consumer(
			qos=2,
			reclaim_idle=None,
		)
		deliveries = []

		def handler(event):
			deliveries.append(event)

		consumer.subs(
			queue.subscription,
			handler,
		)
		thread, errors = self.start(consumer.run)
		try:
			self.wait(
				lambda: len(deliveries) == 2,
				errors,
			)
			sleep(0.1)
			self.assertEqual(
				len(deliveries),
				2,
			)
			consumer.call(deliveries[0].ack)
			self.wait(
				lambda: len(deliveries) == 3,
				errors,
			)
			consumer.call(deliveries[1].ack)
			self.wait(
				lambda: len(deliveries) == 4,
				errors,
			)

			def finish():
				for event in deliveries:
					event.ack()
				consumer.stop()

			consumer.call(finish)
		finally:
			consumer.call(consumer.stop)
			thread.join(5)
			consumer.close()
		self.assertFalse(thread.is_alive())
		self.assertEqual(
			errors,
			[],
		)
		self.assertEqual(
			self.broker.connected().xpending(
				str(queue),
				queue.group,
			)['pending'],
			0,
		)

	def test_abandoned_pending_delivery_is_reclaimed(self):
		queue = self.queue()
		id = queue.send({'value': 1})
		queue.pop(timeout=200)
		sleep(0.02)
		consumer = self.broker.consumer(reclaim_idle=1)
		deliveries = []

		def handler(event):
			deliveries.append(event.id)
			event.ack()
			consumer.stop()

		consumer.subs(
			queue.subscription,
			handler,
		)
		thread, errors = self.start(consumer.run)
		try:
			thread.join(5)
		finally:
			consumer.stop()
			thread.join(5)
			consumer.close()
		self.assertFalse(thread.is_alive())
		self.assertEqual(
			errors,
			[],
		)
		self.assertEqual(
			deliveries,
			[id],
		)

	def test_worker_retry_reject_and_shutdown(self):
		for pool_type in (
			ThreadPool,
			ProcessPool,
		):
			with self.subTest(pool=pool_type), TemporaryDirectory() as directory:
				queue = self.queue()
				rejected = self.queue()
				old_parameters = RedisRunner.parameters
				old_rejected = RejectRedisRunner.parameters
				RedisRunner.parameters = queue.subscription
				RejectRedisRunner.parameters = rejected.subscription
				worker = Worker(
					Connection(Configuration()),
					pool_type(2),
				)
				worker.add(RedisRunner)
				worker.add(RejectRedisRunner)
				path = Path(directory).joinpath('result')
				queue.send({
					'path': str(path),
					'retry': True,
				})
				rejected.send({
					'path': str(path),
					'fail': True,
				})
				try:
					with self.assertLogs(
						'Worker',
						level='ERROR',
					) as logs:
						thread, errors = self.start(worker.run)
						try:
							self.wait(
								lambda: path.exists() and path.read_text() == 'done',
								errors,
							)
							self.wait(
								lambda: len(logs.records) == 2,
								errors,
							)
						finally:
							worker.stop()
							thread.join(15)
					self.assertFalse(thread.is_alive())
					self.assertEqual(
						errors,
						[],
					)
					for stream in (
						queue,
						rejected,
					):
						self.assertEqual(
							self.broker.connected().xpending(
								str(stream),
								stream.group,
							)['pending'],
							0,
						)
				finally:
					RedisRunner.parameters = old_parameters
					RejectRedisRunner.parameters = old_rejected


if __name__ == '__main__':
	main()
