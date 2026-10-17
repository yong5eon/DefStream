from random import randint
from signal import (
	SIGINT,
	signal,
)

from PinkStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
	Reject,
	Requeue,
	Subscription,
)
from PinkStream.Worker import (
	ProcessPool,
	Run,
	Worker,
	WorkerSetup,
	WorkerCleanup,
)


class Add(
	Run,
	parameters={
		'queue': 'add',
	},
	on_error=Requeue(),
):
	def run(
		self,
		a: int,
		b: int,
	):
		print(f'{a} + {b} = {a + b}')
		return a + b


class Divide(
	Run,
	parameters=Subscription(
		queue='divide',
	),
	on_error=Reject(),
):
	def run(
		self,
		a: int,
		b: int,
	):
		print(f'{a} / {b} = {a / b}')
		return a / b


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
		for run in worker.runs:
			parameters = Subscription.parse(run.parameters)
			broker.create_queue(parameters.queue)
			queue = broker.queue(parameters.queue)
			for index in range(5):
				queue.send({
					'a': randint(
						0,
						99,
					),
					'b': randint(
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


if __name__ == '__main__':
	broker = Connection(Configuration(
		host='127.0.0.1',
		port=5672,
		username='guest',
		password='guest',
	))
	worker = Worker(
		broker,
		ProcessPool(10),
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
