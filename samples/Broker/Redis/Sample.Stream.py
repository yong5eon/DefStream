from logging import (
	DEBUG,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
)
from uuid import uuid4

from DefStream.Broker.Implements.Redis import (
	Connection,
	Configuration,
)

logger = getLogger('Sample')


class SampleLogFilter(Filter):
	def filter(self, record) -> bool:
		return any(
			record.name == prefix or record.name.startswith(prefix + '.')
			for prefix in (
				'Sample',
				'Broker.Redis',
			)
		)


def main() -> None:
	handler = StreamHandler()
	handler.setLevel(DEBUG)
	handler.setFormatter(Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
	handler.addFilter(SampleLogFilter())
	root_logger = getLogger()
	root_logger.setLevel(DEBUG)
	root_logger.addHandler(handler)

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

		logger.info(
			'Reading stream from beginning: queue=%s',
			name,
		)
		for event in stream.read(
			offset=0,
			timeout=1000,
		):
			logger.debug(
				'Stream message received: queue=%s id=%s',
				name,
				event.id,
			)

		logger.info(
			'Reading stream again after first message: queue=%s offset=%s',
			name,
			ids[0],
		)
		for event in stream.read(
			offset=ids[0],
			timeout=1000,
		):
			logger.debug(
				'Stream message received: queue=%s id=%s',
				name,
				event.id,
			)
	finally:
		try:
			if broker.connection is not None:
				broker.delete_stream(name)
		finally:
			broker.close()


if __name__ == '__main__':
	main()
