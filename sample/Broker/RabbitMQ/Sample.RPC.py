from concurrent.futures import ThreadPoolExecutor
from sys import stderr
from threading import Event as PyEvent
from uuid import uuid4

from DefStream.Broker import RemoteError
from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
	Consumer,
	Event,
	EventHandler,
	ExchangeType,
	Reject,
)


class Calculate(EventHandler):
	def __init__(
		self,
		consumer: Consumer,
	):
		self.consumer = consumer

	def __call__(
		self,
		event: Event,
	) -> None:
		try:
			result = event.body['a'] / event.body['b']
		except ZeroDivisionError:
			self.consumer.fail(
				event,
				Reject(),
			)
		else:
			self.consumer.complete(
				event,
				result,
			)


def serve(
	configuration: Configuration,
	queue: str,
	ready: PyEvent,
	stopping: PyEvent,
) -> None:
	broker = Connection(configuration)
	try:
		broker.connect()
		consumer = broker.consumer()
		try:
			consumer.subs(
				queue,
				Calculate(consumer),
			)
			ready.set()

			def check_stop() -> None:
				if stopping.is_set():
					consumer.stop()
				else:
					broker.connection.call_later(
						0.1,
						check_stop,
					)

			broker.connection.call_later(
				0.1,
				check_stop,
			)
			consumer.run()
		finally:
			consumer.close()
	finally:
		broker.close()
		ready.set()


if __name__ == '__main__':
	configuration = Configuration(
		host='127.0.0.1',
		port=5672,
		username='guest',
		password='guest',
	)
	broker = Connection(configuration)
	name = 'defstream-rpc-sample-' + uuid4().hex
	ready = PyEvent()
	stopping = PyEvent()
	created_queue = False
	created_exchange = False
	try:
		broker.connect()
		broker.create_exchange(
			name,
			ExchangeType.Direct,
			durable=False,
		)
		created_exchange = True
		broker.create_queue(
			name,
			durable=False,
		)
		created_queue = True
		broker.bind_exchange_to_queue(
			name,
			name,
			event='divide',
		)
		with ThreadPoolExecutor(1) as executor:
			server = executor.submit(
				serve,
				configuration,
				name,
				ready,
				stopping,
			)
			try:
				if not ready.wait(10):
					raise TimeoutError('RPC server did not start')
				if server.done():
					server.result()
					raise RuntimeError('RPC server exited before handling requests')
				result = broker.queue(name).call(
					{
						'a': 20,
						'b': 4,
					},
					timeout=5,
				)
				print(f'Queue RPC: 20 / 4 = {result}')
				result = broker.exchange(name).call(
					{
						'a': 30,
						'b': 5,
					},
					timeout=5,
					event='divide',
				)
				print(f'Exchange RPC: 30 / 5 = {result}')
				try:
					broker.queue(name).call(
						{
							'a': 10,
							'b': 0,
						},
						timeout=5,
					)
				except RemoteError as error:
					print(
						f'RPC rejected: {error}',
						file=stderr,
					)
			finally:
				stopping.set()
				server.result(timeout=10)
	finally:
		try:
			if created_queue:
				broker.delete_queue(name)
		finally:
			try:
				if created_exchange:
					broker.delete_exchange(name)
			finally:
				broker.close()
