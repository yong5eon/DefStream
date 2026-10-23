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
				'DefStream.Broker.Implements.Redis',
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
	name = 'defstream-sample-' + uuid4().hex
	try:
		broker.connect()
		queue = broker.queue(name)
		message_id = queue.send({
			'message': 'Hello Redis',
			'number': 1,
		})
		logger.info(
			'Message published: queue=%s id=%s',
			name,
			message_id,
		)
		event = queue.pop(timeout=1000)
		if event is None:
			raise TimeoutError('Redis sample did not receive its message')
		logger.info(
			'Message received: queue=%s id=%s',
			name,
			event.id,
		)
		event.ack()
		for event in queue.read(timeout=100):
			logger.debug(
				'History message received: queue=%s id=%s',
				name,
				event.id,
			)
	finally:
		try:
			if broker.connection is not None:
				broker.delete_queue(name)
		finally:
			broker.close()


if __name__ == '__main__':
	main()
