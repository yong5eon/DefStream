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
from tests._support_inspector_play import PlayExtensionSupport


@skipUnless(
	environ.get('REDIS_TESTS') == '1',
	'Opt-in local Redis interactive test integration',
)
class RedisPlayIntegrationTests(PlayExtensionSupport, TestCase):
	def test_send_and_unsupported_rpc(self) -> None:
		self.exercise_live(
			lambda: Connection(Configuration(port=redis_test_port())),
			False,
		)
