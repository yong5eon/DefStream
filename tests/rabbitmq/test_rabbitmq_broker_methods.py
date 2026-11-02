from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
	ExchangeType,
)


class BrokerMethodTests(TestCase):
	def test_snake_case_methods_preserve_resource_operations(self):
		broker = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		))
		broker.connection = Mock()
		channel = broker.connection.channel.return_value
		cases = (
			(
				'create_exchange',
				(
					'exchange',
					ExchangeType.Topic,
				),
				'exchange_declare',
				(
					'exchange',
					'topic',
				),
			),
			(
				'delete_exchange',
				('exchange',),
				'exchange_delete',
				('exchange',),
			),
			(
				'bind_exchange_to_exchange',
				(
					'source',
					'target',
				),
				'exchange_bind',
				(
					'source',
					'target',
				),
			),
			(
				'unbind_exchange_to_exchange',
				(
					'source',
					'target',
				),
				'exchange_unbind',
				(
					'source',
					'target',
				),
			),
			(
				'create_queue',
				('queue',),
				'queue_declare',
				('queue',),
			),
			(
				'delete_queue',
				('queue',),
				'queue_delete',
				('queue',),
			),
			(
				'bind_exchange_to_queue',
				(
					'exchange',
					'queue',
				),
				'queue_bind',
				(
					'queue',
					'exchange',
				),
			),
			(
				'unbind_exchange_to_queue',
				(
					'exchange',
					'queue',
				),
				'queue_unbind',
				(
					'queue',
					'exchange',
				),
			),
			(
				'create_stream',
				('stream',),
				'queue_declare',
				('stream',),
			),
			(
				'delete_stream',
				('stream',),
				'queue_delete',
				('stream',),
			),
		)
		try:
			for name, arguments, operation, expected in cases:
				with self.subTest(method=name):
					channel.reset_mock()
					getattr(
						broker,
						name,
					)(*arguments)
					method = getattr(
						channel,
						operation,
					)
					self.assertEqual(
						method.call_count,
						1,
					)
					self.assertEqual(
						method.call_args.args,
						expected,
					)
		finally:
			broker.close()


if __name__ == '__main__':
	main()
