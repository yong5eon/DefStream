from random import randint
from signal import (
	SIGINT,
	signal,
)

from Tasks import (
	Add,
	Divide,
	TaskLoggingSetup,
	SetupLogger,
	logger,
)

from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
)
from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import (
	Metrics,
	Ping,
	Specifications,
	Play,
	Status,
)
from DefStream.Worker import (
	declare,
	emit,
	ProcessPool,
	Worker,
	WorkerSetup,
	WorkerCleanup,
)


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
			raise TypeError('A RabbitMQ broker is required')
		for run in worker.tasks:
			declare(
				task=run,
				broker=broker,
			)
			for _ in range(5):
				emit(
					{
						'a': randint(
							0,
							99,
						),
						'b': randint(
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


if __name__ == '__main__':
	worker = Worker(
		Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		)),
		ProcessPool(
			10,
			setups=TaskLoggingSetup(),
		),
		setups=(
			SetupLogger(),
			Prepare(),
		),
		cleanups=Cleanup(),
		inspector=Inspector(
			host='127.0.0.1',
			port=9999,
			exts=(
				Ping('/ping'),
				Metrics('/metrics'),
				Status(
					'/status',
					title='DefStream using RabbitMQ Sample',
					description='A sample DefStream worker using RabbitMQ as the broker',
				),
				Specifications('/spec'),
				Play(
					'/play',
					broker=lambda: Connection(Configuration(
						host='127.0.0.1',
						port=5672,
						username='guest',
						password='guest',
					)),
					title='DefStream using RabbitMQ Sample',
					description='A sample DefStream worker using RabbitMQ as the broker',
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
