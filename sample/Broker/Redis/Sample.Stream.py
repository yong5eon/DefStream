from uuid import uuid4

from DefStream.Broker.Implements.Redis import (
	Connection,
	Configuration,
)


def main() -> None:
	broker = Connection(Configuration())
	name = 'defstream-stream-sample-' + uuid4().hex
	try:
		broker.connect()
		stream = broker.stream(name)
		ids = []
		for number in range(3):
			ids.append(stream.send({
				'message': 'Hello Redis Stream',
				'number': number,
			}))

		print('Read from the beginning:')
		for event in stream.read(
			offset=0,
			timeout=1000,
		):
			print(
				event.id,
				event.body,
			)

		print('Resume after the first event:')
		for event in stream.read(
			offset=ids[0],
			timeout=1000,
		):
			print(
				event.id,
				event.body,
			)
	finally:
		try:
			if broker.connection is not None:
				broker.delete_stream(name)
		finally:
			broker.close()


if __name__ == '__main__':
	main()
