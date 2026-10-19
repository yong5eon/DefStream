from random import randint

from Tasks import (
	Add,
	Divide,
	LoggingSetup,
	logger,
)

from DefStream.Broker import RemoteError
from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
)
from DefStream.Worker import request


if __name__ == '__main__':
	LoggingSetup()()
	broker = Connection(Configuration(
		host='127.0.0.1',
		port=5672,
		username='guest',
		password='guest',
	))
	try:
		broker.connect()
		result = request(
			{
				'a': randint(
					1,
					100,
				),
				'b': randint(
					1,
					100,
				),
			},
			task=Add,
			broker=broker,
			timeout=5,
		)
		logger.info(
			'RPC add result: %s',
			result,
		)
		result = request(
			{
				'a': randint(
					1,
					100,
				),
				'b': randint(
					1,
					100,
				),
			},
			task=Divide,
			broker=broker,
			timeout=5,
		)
		logger.info(
			'RPC divide result: %s',
			result,
		)
		try:
			request(
				{
					'a': randint(
						1,
						100,
					),
					'b': 0,
				},
				task=Divide,
				broker=broker,
				timeout=5,
			)
		except RemoteError as error:
			logger.info(
				'RPC rejected: code=%s',
				error.code,
			)
	finally:
		broker.close()
