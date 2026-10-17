from random import randint
from sys import stderr

from PinkStream.Broker import RemoteError
from PinkStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
)


if __name__ == '__main__':
	broker = Connection(Configuration(
		host='127.0.0.1',
		port=5672,
		username='guest',
		password='guest',
	))
	try:
		broker.connect()
		result = broker.queue('add').call(
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
			timeout=5,
		)
		print(f'RPC add result: {result}')
		result = broker.queue('divide').call(
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
			timeout=5,
		)
		print(f'RPC divide result: {result}')
		try:
			broker.queue('divide').call(
				{
					'a': randint(
						1,
						100,
					),
					'b': 0,
				},
				timeout=5,
			)
		except RemoteError as error:
			print(
				f'RPC rejected: {error}',
				file=stderr,
			)
	finally:
		broker.close()
