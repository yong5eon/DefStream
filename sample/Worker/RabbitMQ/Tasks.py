from PinkStream.Broker.Implements.RabbitMQ import (
	Reject,
	Requeue,
	Subscription,
)
from PinkStream.Worker import Run

__all__ = (
	'Add',
	'Divide',
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
