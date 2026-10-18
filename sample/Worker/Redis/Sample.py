from random import randint
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
	send,
	Run,
	ThreadPool,
	Worker,
	WorkerSetup,
	WorkerCleanup,
)


class Add(
	Run,
	parameters=Subscription('add'),
):
	def run(
		self,
		a: int,
		b: int,
	):
		result = a + b
		print(f'{a} + {b} = {result}')
		return result


class Divide(
	Run,
	parameters=Subscription('divide'),
	on_error=Reject(),
):
	def run(
		self,
		a: int,
		b: int,
	):
		result = a / b
		print(f'{a} / {b} = {result}')
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
				send(
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
		print('Prepared 5 messages per queue')


class Cleanup(WorkerCleanup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		print('Worker cleanup')


def main() -> None:
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
