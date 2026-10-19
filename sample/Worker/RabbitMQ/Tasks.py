from logging import (
	DEBUG,
	Filter,
	Formatter,
	StreamHandler,
	getLogger,
)

from DefStream.Broker.Implements.RabbitMQ import (
	Reject,
	Requeue,
	Subscription,
)
from DefStream.Descriptor import (
	Integer,
	Number,
	Object,
	Properties,
)
from DefStream.Validator import Validator
from DefStream.Validator.Patterns import (
	IsInteger,
	IsNumber,
	IsObject,
)
from DefStream.Validator.Patterns.Object import (
	IsMappingOf,
	IsRequiredIn,
)
from DefStream.Worker import (
	PoolSetup,
	Run,
	Specification,
)

__all__ = (
	'Add',
	'Divide',
)


logger = getLogger('Sample')


class LoggingSetup(PoolSetup):
	"""부모와 spawn 자식 프로세스의 샘플 로그 출력을 설정한다."""

	def __call__(self) -> None:
		handler = StreamHandler()
		handler.setFormatter(Formatter('%(asctime)s %(processName)s %(name)s %(levelname)s %(message)s'))
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
	parameters={
		'queue': 'add',
	},
	on_error=Requeue(),
	request=Specification(
		description='Addition request',
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
		description='Addition response',
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
		logger.info(
			'%s + %s = %s',
			a,
			b,
			a + b,
		)
		return a + b


class Divide(
	Run,
	parameters=Subscription(
		queue='divide',
	),
	on_error=Reject(),
	request=Specification(
		description='Division request',
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
		description='Division response',
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
		logger.info(
			'%s / %s = %s',
			a,
			b,
			a / b,
		)
		return a / b
