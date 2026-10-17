from random import randint
from sys import stderr

from Tasks import (
	Add,
	Divide,
)

from PinkStream.Broker import RemoteError
from PinkStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
)
from PinkStream.Worker import request


if __name__ == '__main__':
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
		print(f'RPC add result: {result}')
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
		print(f'RPC divide result: {result}')
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
			print(
				f'RPC rejected: {error}',
				file=stderr,
			)
	finally:
		broker.close()
