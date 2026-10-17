# Sample for PinkStream.Broker.Implements.RabbitMQ

from PinkStream.Broker.Implements.RabbitMQ import (
	Connection as RabbitConnection,
	Configuration,
	ExchangeType,
	Event,
	EventHandler,
)
from threading import Timer

if __name__ == '__main__':

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
	e = reader.pop()
	print(e)
	e.ack()
	e = reader.pop()
	print(e)
	e.ack()

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
				print(event.body)
				print(event.priority)
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
