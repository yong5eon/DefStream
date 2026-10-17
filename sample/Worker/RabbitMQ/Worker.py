from random import randint
from signal import (
	SIGINT,
	signal,
)

from Tasks import (
	Add,
	Divide,
)

from PinkStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
)
from PinkStream.Inspector import Inspector
from PinkStream.Inspector.Extensions import (
	HealthCheck,
	Metrics,
	Specifications,
)
from PinkStream.Worker import (
	declare,
	send,
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
				send(
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
			name='PinkStream.RabbitMQ',
			exts=(
				HealthCheck('/status'),
				Metrics('/metrics'),
				Specifications('/spec'),
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
