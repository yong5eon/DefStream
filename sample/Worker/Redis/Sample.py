from random import randint
from signal import (
	SIGINT,
	signal,
)

from PinkStream.Broker.Implements.Redis import (
	Connection,
	Configuration,
	Reject,
	Subscription,
)
from PinkStream.Worker import (
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
		for run in worker.runs:
			parameters = Subscription.parse(run.parameters)
			broker.create_queue(
				parameters.queue,
				group=parameters.group,
			)
			queue = broker.queue(
				parameters.queue,
				group=parameters.group,
			)
			for index in range(5):
				queue.send({
					'a': randint(
						0,
						99,
					),
					'b': 0 if run is Divide and index == 0 else randint(
						0,
						99,
					),
				})
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
