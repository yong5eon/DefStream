from PinkStream.Broker.Implements.RabbitMQ import (
	Reject,
	Requeue,
	Subscription,
)
from PinkStream.Descriptor import (
	Integer,
	Number,
	Object,
	Properties,
)
from PinkStream.Validator import Validator
from PinkStream.Validator.Patterns import (
	IsInteger,
	IsNumber,
	IsObject,
)
from PinkStream.Validator.Patterns.Object import (
	IsMappingOf,
	IsRequiredIn,
)
from PinkStream.Worker import (
	Run,
	Specification,
)

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
	request=Specification(
		schema=Object(
			properties=Properties(
				a=Integer('First operand'),
				b=Integer('Second operand'),
			),
		),
		validator=Validator(IsObject(
			IsRequiredIn(
				'a',
				'b',
			),
			IsMappingOf({
				'a': IsInteger(),
				'b': IsInteger(),
			}),
		)),
		example={
			'a': 10,
			'b': 20,
		},
	),
	response=Specification(
		schema=Integer('Sum'),
		validator=Validator(IsInteger()),
		example=30,
	),
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
	request=Specification(
		schema=Object(
			properties=Properties(
				a=Integer('Dividend'),
				b=Integer('Divisor; zero demonstrates task failure'),
			),
		),
		validator=Validator(IsObject(
			IsRequiredIn(
				'a',
				'b',
			),
			IsMappingOf({
				'a': IsInteger(),
				'b': IsInteger(),
			}),
		)),
		example={
			'a': 10,
			'b': 2,
		},
	),
	response=Specification(
		schema=Number('Quotient'),
		validator=Validator(IsNumber()),
		example=5.0,
	),
):
	def run(
		self,
		a: int,
		b: int,
	):
		print(f'{a} / {b} = {a / b}')
		return a / b
