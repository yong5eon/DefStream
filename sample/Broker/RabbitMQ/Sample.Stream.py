# Sample for PinkStream.Broker.Implements.RabbitMQ

from PinkStream.Broker.Implements.RabbitMQ import (
	Connection as RabbitConnection,
	Configuration,
	Event,
	EventHandler,
)
from threading import Timer
from random import randint

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
				print(event.body)
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
		print('Consuming Events from Stream Queue: {}'.format(i + 1))	
		print('-' * 20)
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

	print('Read Events from Stream Queue:')	
	print('-' * 20)	
	stream = con.stream('stream')
	try:
		for event in stream.read(timeout=1000):
			print(event.body)
	except KeyboardInterrupt:
		pass

	con.delete_stream('stream')
	con.close()
