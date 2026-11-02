from os import environ
from unittest import (
	TestCase,
	skipUnless,
)

from DefStream.Broker.Implements.Redis import (
	Configuration,
	Connection,
)
from tests._support import redis_test_port
from tests._support_inspector import InspectorIntegrationSupport


@skipUnless(
	environ.get('REDIS_TESTS') == '1',
	'Opt-in local Redis Inspector integration',
)
class RedisInspectorIntegrationTests(InspectorIntegrationSupport, TestCase):
	def test_process_pool_health_and_metrics(self) -> None:
		self.exercise_live_broker(lambda: Connection(Configuration(
			port=redis_test_port(),
		)))
