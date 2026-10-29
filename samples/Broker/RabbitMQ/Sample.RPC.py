from concurrent.futures import ThreadPoolExecutor
from logging import (
	DEBUG,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
)
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

logger = getLogger('Sample')


class Calculate(EventHandler):
	def __init__(
		self,
		consumer: Consumer,
	):
		self.consumer = consumer
		return

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
		return


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
				return

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
	return


if __name__ == '__main__':
	root = getLogger()
	root.setLevel(DEBUG)
	console = StreamHandler()
	console.setLevel(DEBUG)
	sample_filter = Filter('Sample')
	rabbitmq_filter = Filter('DefStream.Broker.RabbitMQ')
	console.addFilter(lambda record: sample_filter.filter(record) or rabbitmq_filter.filter(record))
	console.setFormatter(Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
	root.addHandler(console)
	logger.info('Starting RabbitMQ RPC sample')
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
				logger.info('Queue RPC calculation completed')
				result = broker.exchange(name).call(
					{
						'a': 30,
						'b': 5,
					},
					timeout=5,
					event='divide',
				)
				logger.info('Exchange RPC calculation completed')
				try:
					broker.queue(name).call(
						{
							'a': 10,
							'b': 0,
						},
						timeout=5,
					)
				except RemoteError:
					logger.warning('RPC remote calculation rejection confirmed')
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
	logger.info('RabbitMQ RPC sample finished')
