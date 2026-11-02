from threading import Event

from DefStream.Worker import (
	Run,
	Worker,
	WorkerSetup,
	declare,
)


class Task(
	Run,
	parameters={'queue': 'task'},
):
	def run(
		self,
		a: int,
		b: int,
		fail: bool = False,
	):
		if fail:
			raise ValueError('Task failed')
		return a + b


class Declare(WorkerSetup):
	def __init__(self):
		self.ready = Event()

	def __call__(
		self,
		worker: Worker,
	) -> None:
		for task in worker.tasks:
			declare(
				task=task,
				broker=worker.broker,
			)
		self.ready.set()
		return
