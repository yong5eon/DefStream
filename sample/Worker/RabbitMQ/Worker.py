from random import randint
from signal import (
	SIGINT,
	signal,
)

from Tasks import (
	Add,
	Divide,
)

from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
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
		print('Prepared 5 messages per queue')


class Cleanup(WorkerCleanup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		print('Worker cleanup')


if __name__ == '__main__':
	worker = Worker(
		Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		)),
		ProcessPool(10),
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
					title='DefStream using RabbitMQ Sample',
					description='A sample DefStream worker using RabbitMQ as the broker',
				),
				Specifications('/spec'),
				Console(
					'/console',
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
