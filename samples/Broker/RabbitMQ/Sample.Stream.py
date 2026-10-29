# Sample for DefStream.Broker.Implements.RabbitMQ

from DefStream.Broker.Implements.RabbitMQ import (
	Connection as RabbitConnection,
	Configuration,
	Event,
	EventHandler,
)
from threading import Timer
from random import randint
from logging import (
	DEBUG,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
)

logger = getLogger('Sample')

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
	logger.info('Starting RabbitMQ Stream sample')

	con = RabbitConnection(
		Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		),
	)

	con.connect()
	con.create_stream('stream')

	stream = con.stream('stream')
	for i in range(randint(
		5,
		10,
	)):
		stream.send(randint(
			0,
			10,
		))

	class SampleEventHandler(EventHandler):
		def __call__(
			self,
			event: Event,
		):
			try:
				logger.debug('Processing Stream message: message_id=%s', event.id)
				event.ack()
			except RuntimeError:
				event.nack()  # if you want requeue message
				# event.reject()  # if you want drop message or move to DLQ or DLE
				pass
			return

	for i in range(randint(
		2,
		5,
	)):
		logger.info('Starting Stream subscription: iteration=%s', i + 1)
		consumer = con.consumer(
			handler=SampleEventHandler(),
			qos=1,
			offset=0,
		)
	
		def stop(timer):
			consumer.stop()
			return
		
		Timer(
			1,
			lambda: stop(None),
		).start()
	
		consumer.subs('stream')
		consumer.run()

	logger.info('Starting Stream read loop')
	stream = con.stream('stream')
	try:
		for event in stream.read(timeout=1000):
			logger.debug('Reading Stream message: message_id=%s', event.id)
	except KeyboardInterrupt:
		pass

	con.delete_stream('stream')
	con.close()
	logger.info('RabbitMQ Stream sample finished')
