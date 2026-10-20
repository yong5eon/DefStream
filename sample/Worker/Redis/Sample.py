from random import randint
from logging import (
	DEBUG,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
)
from signal import (
	SIGINT,
	signal,
)

from DefStream.Broker.Implements.Redis import (
	Connection,
	Configuration,
	Reject,
	Subscription,
)
from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import (
	HealthCheck,
	Metrics,
	Specifications,
	Console,
	Dashboard,
)
from DefStream.Worker import (
	declare,
	emit,
	Run,
	ThreadPool,
	Worker,
	WorkerSetup,
	WorkerCleanup,
)


logger = getLogger('Sample')


def configure_logging() -> None:
	handler = StreamHandler()
	handler.setFormatter(Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
	sources = (
		Filter('Sample'),
		Filter('DefStream'),
	)
	handler.addFilter(lambda record: any(source.filter(record) for source in sources))
	root = getLogger()
	root.setLevel(DEBUG)
	root.addHandler(handler)
	return


class Add(
	Run,
	parameters=Subscription('add'),
	name='add',
	description='Add two integers',
):
	def run(
		self,
		a: int,
		b: int,
	):
		result = a + b
		logger.info(
			'%s + %s = %s',
			a,
			b,
			result,
		)
		return result


class Divide(
	Run,
	parameters=Subscription('divide'),
	on_error=Reject(),
	name='divide',
	description='Divide a dividend by a divisor',
):
	def run(
		self,
		a: int,
		b: int,
	):
		result = a / b
		logger.info(
			'%s / %s = %s',
			a,
			b,
			result,
		)
		return result


class Prepare(WorkerSetup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		broker = worker.broker
		if not isinstance(
			broker,
			Connection,
		):
			raise TypeError('A Redis connection is required')
		for run in worker.tasks:
			declare(
				task=run,
				broker=broker,
			)
			for index in range(5):
				emit(
					{
						'a': randint(
							0,
							99,
						),
						'b': 0 if run is Divide and index == 0 else randint(
							0,
							99,
						),
					},
					task=run,
					broker=broker,
				)
		logger.info('Prepared 5 messages per queue')


class Cleanup(WorkerCleanup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		logger.info('Worker cleanup')


def main() -> None:
	configure_logging()
	worker = Worker(
		Connection(Configuration()),
		ThreadPool(10),
		setups=Prepare(),
		cleanups=Cleanup(),
		inspector=Inspector(
			host='127.0.0.1',
			port=9999,
			exts=(
				HealthCheck('/status'),
				Metrics('/metrics'),
				Dashboard(
					'/dashboard',
					title='DefStream using Redis Sample',
					description='A sample DefStream worker using Redis as the broker',
				),
				Specifications('/spec'),
				Console(
					'/console',
					broker=lambda: Connection(Configuration()),
					title='DefStream using Redis Sample',
					description='A sample DefStream worker using Redis as the broker',
				),
			),
		),
	)
	worker.add(Add)
	worker.add(Divide)
	signal(
		SIGINT,
		lambda *_: worker.stop(),
	)
	worker.run()


if __name__ == '__main__':
	main()
