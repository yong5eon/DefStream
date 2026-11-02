from os import environ
from unittest import (
	TestCase,
	skipUnless,
)

from DefStream.Broker.Implements.RabbitMQ import (
	Configuration,
	Connection,
)
from tests._support import rabbitmq_test_port
from tests._support_inspector_play import PlayExtensionSupport


@skipUnless(
	environ.get('RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ interactive test integration',
)
class RabbitMQPlayIntegrationTests(PlayExtensionSupport, TestCase):
	def test_send_rpc_and_remote_error(self) -> None:
		self.exercise_live(
			lambda: Connection(Configuration(
				host='127.0.0.1',
				port=rabbitmq_test_port(),
				username='guest',
				password='guest',
			)),
			True,
		)
