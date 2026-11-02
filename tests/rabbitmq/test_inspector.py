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
from tests._support_inspector import InspectorIntegrationSupport


@skipUnless(
	environ.get('RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ Inspector integration',
)
class RabbitMQInspectorIntegrationTests(InspectorIntegrationSupport, TestCase):
	def test_process_pool_health_and_metrics(self) -> None:
		self.exercise_live_broker(lambda: Connection(Configuration(
			host='127.0.0.1',
			port=rabbitmq_test_port(),
			username='guest',
			password='guest',
		)))
