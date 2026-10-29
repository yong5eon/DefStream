# Sample for DefStream.Broker.Implements.RabbitMQ

from DefStream.Broker.Implements.RabbitMQ import (
	Connection as RabbitConnection,
	Configuration,
	ExchangeType,
	Event,
	EventHandler,
)
from threading import Timer
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
	rabbitmq_filter = Filter('Broker.RabbitMQ')
	console.addFilter(lambda record: sample_filter.filter(record) or rabbitmq_filter.filter(record))
	console.setFormatter(Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
	root.addHandler(console)
	logger.info('Starting RabbitMQ queue and exchange sample')

	con = RabbitConnection(
		Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		),
	)

	con.connect()
	con.create_exchange(
		'topic',
		ExchangeType.Topic,
	)
	con.create_queue(
		'queue',
		maxPriority=255,
	)
	con.bind_exchange_to_queue(
		'topic',
		'queue',
	)

	exchange = con.exchange('topic')
	exchange.send(
		{
			'a': True,
			'b': 1,
			'c': 1.0,
			'd': 'abc',
		},
		priority=1,
	)
	queue = con.queue('queue')
	queue.send({
		'a': False,
		'b': 2,
		'c': 2.0,
		'd': 'def',
	})

	reader = con.queue('queue')
	event = reader.pop()
	if event is None:
		raise RuntimeError('Queue unexpectedly returned no message')
	logger.debug('Single message received: queue=%s message_id=%s', event.src, event.id)
	event.ack()
	event = reader.pop()
	if event is None:
		raise RuntimeError('Queue unexpectedly returned no message')
	logger.debug('Single message received: queue=%s message_id=%s', event.src, event.id)
	event.ack()

	exchange.send(
		{
			'a': True,
			'b': 1,
			'c': 1.0,
			'd': 'abc',
		},
		priority=0,
	)
	queue.send(
		{
			'a': False,
			'b': 2,
			'c': 2.0,
			'd': 'def',
		},
		priority=255,
	)
	exchange.send({
		'a': True,
		'b': 1,
		'c': 1.0,
		'd': 'abc',
	})
	queue.send({
		'a': False,
		'b': 1,
		'c': 3.0,
		'd': 'def',
	})

	class SampleEventHandler(EventHandler):
		def __call__(
			self,
			event: Event,
		):
			try:
				logger.debug('Processing message: message_id=%s priority=%s', event.id, event.priority)
				event.ack()
			except RuntimeError:
				event.nack()  # if you want requeue message
				# event.reject()  # if you want drop message or move to DLQ or DLE
			return
		
	consumer = con.consumer(
		handler=SampleEventHandler(),
		qos=1,
	)

	def stop(timer):
		consumer.stop()
		return
	
	Timer(
		1,
		lambda: stop(None),
	).start()

	consumer.subs('queue')
	consumer.run()

	con.delete_queue('queue')
	con.delete_exchange('topic')
	con.close()
	logger.info('RabbitMQ queue and exchange sample finished')
