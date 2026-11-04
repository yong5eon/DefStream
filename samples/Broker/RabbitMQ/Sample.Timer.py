from logging import (
	DEBUG,
	Filter,
	Formatter,
	Logger,
	StreamHandler,
	getLogger,
)
from uuid import uuid4

from DefStream.Broker import (
	Event,
	Timer,
)
from DefStream.Broker.Implements.RabbitMQ import (
	Configuration,
	Connection as RabbitConnection,
	Consumer,
)

logger: Logger = getLogger('Sample')


def main() -> None:
	con: RabbitConnection = RabbitConnection(Configuration(
		host='127.0.0.1',
		port=5672,
		username='guest',
		password='guest',
	))
	try:
		con.connect()
		queue: str = 'defstream-timer-sample-' + uuid4().hex
		con.create_queue(queue)
		try:
			def receive(event: Event) -> None:
				logger.info('Message received')
				event.ack()
				return

			consumer: Consumer = con.consumer(handler=receive)
			try:
				consumer.subs(queue)

				def cancelled_callback() -> None:
					raise RuntimeError('Cancelled timer was executed')

				cancelled: Timer = con.set_timer(cancelled_callback, 1)
				cancelled.remove()
				logger.info('Cancelled a one-shot timer before consumption')
				remaining: int = 3
				timer: Timer

				def tick() -> None:
					nonlocal remaining, timer
					remaining -= 1
					logger.info('Timer fired: remaining=%s', remaining)
					if remaining:
						timer = con.set_timer(tick, 1)
					else:
						consumer.stop()
					return

				timer = con.set_timer(tick, 1)
				try:
					consumer.run()
				finally:
					timer.remove()
			finally:
				consumer.close()
		finally:
			con.delete_queue(queue)
	finally:
		con.close()
	logger.info('RabbitMQ timer sample finished')
	return


if __name__ == '__main__':
	root: Logger = getLogger()
	root.setLevel(DEBUG)
	console: StreamHandler = StreamHandler()
	console.setLevel(DEBUG)
	sample_filter: Filter = Filter('Sample')
	rabbitmq_filter: Filter = Filter('Broker.RabbitMQ')
	console.addFilter(lambda record: sample_filter.filter(record) or rabbitmq_filter.filter(record))
	console.setFormatter(Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
	root.addHandler(console)
	logger.info('Starting RabbitMQ timer sample')
	main()
