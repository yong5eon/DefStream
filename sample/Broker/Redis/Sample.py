from uuid import uuid4

from DefStream.Broker.Implements.Redis import (
	Connection,
	Configuration,
)


def main() -> None:
	broker = Connection(Configuration())
	name = 'defstream-sample-' + uuid4().hex
	try:
		broker.connect()
		queue = broker.queue(name)
		queue.send({
			'message': 'Hello Redis',
			'number': 1,
		})
		event = queue.pop(timeout=1000)
		if event is None:
			raise TimeoutError('Redis sample did not receive its message')
		print(event.body)
		event.ack()
		for event in queue.read(timeout=100):
			print(
				event.id,
				event.body,
			)
	finally:
		try:
			if broker.connection is not None:
				broker.delete_queue(name)
		finally:
			broker.close()


if __name__ == '__main__':
	main()
