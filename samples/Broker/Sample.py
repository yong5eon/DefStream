from logging import (
	DEBUG,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
)

from DefStream.Broker import (
	Configuration as BaseConfiguration,
	Connection as BaseConnection,
	GetExchange,
	GetQueue,
	GetConsumer,
	Sendable,
	Consumer as BaseConsumer,
)
from DefStream.Broker.Event import EventHandler

from queue import (
	SimpleQueue,
	Empty,
)
from threading import Timer
from typing import Optional


logger = getLogger('Sample')


def configure_logging() -> None:
	handler = StreamHandler()
	handler.setFormatter(Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
	sources = (
		Filter('Sample'),
		Filter('Worker'),
	)
	handler.addFilter(lambda record: any(source.filter(record) for source in sources))
	root = getLogger()
	root.setLevel(DEBUG)
	root.addHandler(handler)
	return


class Configuration(BaseConfiguration):
	def __init__(self):
		pass

class Connection(
	BaseConnection,
	GetExchange,
	GetQueue,
	GetConsumer,
):
	def __init__(
		self,
		conf: Configuration,
	):
		self.con = conf
		self.e = {}
		self.q = {}
		return

	def connect(self):
		pass

	def exchange(
		self,
		exchange: str,
	):
		if exchange not in self.e.keys():
			self.e[exchange] = set()
		return Exchange(
			self,
			exchange,
		)

	def queue(
		self,
		queue: str,
	):
		if queue not in self.q.keys():
			self.q[queue] = SimpleQueue()
		return Queue(
			self,
			queue,
		)

	def consumer(
		self,
		handler: Optional[EventHandler] = None,
	):
		return Consumer(
			self,
			handler,
		)

	def close(self):
		pass


class Exchange(Sendable):
	def __init__(
		self,
		con: Connection,
		exchange: str,
	):
		self.con = con
		self.exchange = exchange
		return

	def send(
		self,
		body,
	):
		for queue in self.con.e[self.exchange]:
			self.con.q[queue].put(body)
		return


class Queue(Sendable):
	def __init__(
		self,
		con: Connection,
		queue: str,
	):
		self.con = con
		self.queue = queue
		return

	def bind(
		self,
		exchange: str,
	):
		if exchange not in self.con.e.keys():
			raise RuntimeError('No Exchange')
		self.con.e[exchange].add(self.queue)

	def send(
		self,
		body,
	):
		self.con.q[self.queue].put(body)
		return

	def get(
		self,
		timeout: Optional[int] = None,
	):
		try:
			return self.con.q[self.queue].get(
				block=True,
				timeout=timeout / 1000 if timeout else None,
			)
		except Empty:
			return None


class Consumer(BaseConsumer):
	def __init__(
		self,
		con: Connection,
		handler: Optional[EventHandler] = None,
	):
		self.con = con
		self.handler = handler
		self.alive = True
		self.queue = None
		return

	def subs(
		self,
		queue: str,
		handler: Optional[EventHandler] = None,
	):
		if handler is not None:
			self.handler = handler
		if self.handler is None:
			raise ValueError('A subscription handler is required')
		self.queue = queue
		return

	def run(self):
		handler = self.handler
		if handler is None:
			raise ValueError('A subscription handler is required')
		q: SimpleQueue = self.con.q[self.queue]
		while self.alive:
			try:
				v = q.get(
					block=True,
					timeout=1,
				)
				if v:
					handler(v)
			except Empty:
				if self.alive:
					continue
				break
		return

	def stop(self):
		self.alive = False
		return


class SampleEventHandler(EventHandler):
	def __call__(
		self,
		event,
	):
		logger.info(
			'Sample event received: %s',
			event,
		)
		return


if __name__ == '__main__':
	configure_logging()
	con = Connection(Configuration())
	con.connect()
	e = con.exchange('e')
	q1 = con.queue('q1')
	q2 = con.queue('q2')
	q3 = con.queue('q3')
	q1.bind('e')
	q2.bind('e')
	q3.bind('e')

	e.send(1) # expect q1, q2 have 1 
	q1.send(2) # expect q1 has 1, 2
	q3.send(2) # expect q3 has 1, 2
	q2.send(3) # expect q2 has 1, 3
	q3.send(3) # expect q3 has 1, 2, 3

	logger.info(
		'q1 received: %s',
		q1.get(),
	)
	logger.info(
		'q1 received: %s',
		q1.get(),
	)

	logger.info(
		'q2 received: %s',
		q2.get(),
	)
	logger.info(
		'q2 received: %s',
		q2.get(),
	)

	c = con.consumer(SampleEventHandler())
	c.subs('q3')

	def stop():
		c.stop()
		return
	
	Timer(
		0.01,
		stop,
	).start()

	c.run()
	con.close()
