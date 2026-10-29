from inspect import isabstract
from typing import (
	Optional,
	get_type_hints,
)
from unittest import (
	TestCase,
	main,
)
from unittest.mock import Mock

from DefStream.Broker import (
	Connection,
	BrokerFactory,
	Consumer,
	Event,
	Emittable,
	GetConsumer,
	GetExchange,
	GetQueue,
	GetStream,
	Declarable,
	Requestable,
)
from DefStream.Broker import __all__ as broker_exports
from DefStream.Broker.Connection import __all__ as connection_exports
from DefStream.Inspector.Extensions import Play
from DefStream.Broker.Implements.RabbitMQ import __all__ as rabbit_exports
from DefStream.Broker.Implements.Redis import __all__ as redis_exports
from DefStream.Broker.Event import (
	EventErrorPolicy,
	EventHandler,
)
from DefStream.Broker.Implements.RabbitMQ import (
	Configuration as RabbitConfiguration,
	Connection as RabbitConnection,
	Event as RabbitEvent,
	Queue as RabbitQueue,
	Reject as RabbitReject,
	Requeue as RabbitRequeue,
)
from DefStream.Broker.Implements.RabbitMQ.Consumer import FailedRequest
from DefStream.Broker.Implements.Redis import (
	Configuration as RedisConfiguration,
	Connection as RedisConnection,
	Event as RedisEvent,
	Queue as RedisQueue,
	Reject as RedisReject,
	Requeue as RedisRequeue,
)
from DefStream.Broker.Implements.Redis.Serializer import (
	Decoder,
	Encoder,
	JavaScriptObjectNotationDecoder,
	JavaScriptObjectNotationEncoder,
)
from DefStream.Worker import (
	Run,
	Worker,
)
from DefStream.Worker import __all__ as worker_exports
from _support import call_with_invalid_input


def queue_provider(
	connection: GetQueue,
) -> GetQueue:
	return connection


class StructuralConnection:
	def connect(self) -> None:
		pass

	def close(self) -> None:
		pass

	def consumer(
		self,
		handler: Optional[EventHandler] = None,
	) -> Consumer:
		return Mock(
			spec=Consumer,
			handler=handler,
		)


class ProtocolContractTests(TestCase):
	def test_broker_factory_contract_and_play_annotation(self):
		from DefStream.Broker.Connection import BrokerFactory as FactoryContract

		self.assertIs(
			BrokerFactory,
			FactoryContract,
		)
		self.assertIn(
			'BrokerFactory',
			connection_exports,
		)
		self.assertIs(
			get_type_hints(Play.__init__)['broker'],
			BrokerFactory,
		)
		self.assertIs(
			get_type_hints(BrokerFactory.__call__)['return'],
			Connection,
		)

		class IncompleteFactory(BrokerFactory):
			pass

		self.assertTrue(isabstract(IncompleteFactory))
		with self.assertRaises(TypeError):
			call_with_invalid_input(IncompleteFactory)

		def factory_function() -> Connection:
			return StructuralConnection()

		class Factory(BrokerFactory):
			def __call__(self) -> Connection:
				return StructuralConnection()

		class StructuralFactory:
			def __call__(self) -> Connection:
				return StructuralConnection()

		factories: tuple[BrokerFactory, ...] = (
			factory_function,
			lambda: StructuralConnection(),
			Factory(),
			StructuralFactory(),
		)
		for factory in factories:
			with self.subTest(factory=factory):
				play = Play(
					'/play',
					broker=factory,
				)
				first = play.broker()
				second = play.broker()
				self.assertIsInstance(
					first,
					StructuralConnection,
				)
				self.assertIsNot(
					first,
					second,
				)
		return

	def test_resource_capabilities_support_runtime_checks(self):
		for implementation, capabilities in (
			(
				RabbitConnection,
				(
					GetExchange,
					GetQueue,
					GetStream,
					GetConsumer,
					Declarable,
					Emittable,
					Requestable,
				),
			),
			(
				RedisConnection,
				(
					GetQueue,
					GetStream,
					GetConsumer,
					Declarable,
					Emittable,
				),
			),
		):
			for capability in capabilities:
				with self.subTest(implementation=implementation, capability=capability):
					self.assertTrue(issubclass(
						implementation,
						capability,
					))
					self.assertNotIsInstance(
						object(),
						capability,
					)
		self.assertFalse(issubclass(
			RedisConnection,
			GetExchange,
		))
		self.assertNotIn(
			'TaskSender',
			connection_exports,
		)
		self.assertIn(
			'Emittable',
			connection_exports,
		)
		return

	def test_event_handler_protocol_and_public_exports(self):
		from DefStream.Broker import EventHandler as PublicEventHandler
		from DefStream.Broker.Implements.Redis import EventHandler as RedisEventHandler

		self.assertIs(
			PublicEventHandler,
			EventHandler,
		)
		self.assertIs(
			RedisEventHandler,
			EventHandler,
		)
		class IncompleteHandler(EventHandler):
			pass

		with self.assertRaises(TypeError):
			call_with_invalid_input(IncompleteHandler)

		class Handler(EventHandler):
			def __call__(
				self,
				event: Event,
			) -> None:
				event.ack()

		ack = Mock()
		event = Mock(spec=Event, ack=ack)
		Handler()(event)
		ack.assert_called_once()

	def test_protocols_are_abstract(self):
		self.assertNotIn(
			'Broker',
			connection_exports,
		)
		for protocol in (
			Connection,
			GetExchange,
			GetQueue,
			GetStream,
			GetConsumer,
		):
			with self.subTest(protocol=protocol):
				with self.assertRaises(TypeError):
					call_with_invalid_input(protocol)

		class IncompleteQueue(GetQueue):
			pass

		self.assertTrue(isabstract(IncompleteQueue))
		with self.assertRaises(TypeError):
			call_with_invalid_input(IncompleteQueue)

	def test_concrete_connections_declare_only_supported_capabilities(self):
		for exports in (
			rabbit_exports,
			redis_exports,
		):
			self.assertNotIn(
				'Broker',
				exports,
			)
		for implementation, capabilities in (
			(
				RabbitConnection,
				(
					GetExchange,
					GetQueue,
					GetStream,
				),
			),
			(
				RedisConnection,
				(
					GetQueue,
					GetStream,
				),
			),
		):
			with self.subTest(implementation=implementation):
				self.assertIn(
					Connection,
					implementation.__bases__,
				)
				self.assertFalse(isabstract(implementation))
				for capability in capabilities:
					self.assertIn(
						capability,
						implementation.__bases__,
					)
				self.assertIn(
					GetConsumer,
					implementation.__bases__,
				)
		self.assertNotIn(
			GetExchange,
			RedisConnection.__mro__,
		)
		self.assertFalse(hasattr(
			RedisConnection,
			'exchange',
		))

	def test_worker_accepts_minimal_structural_and_concrete_connections(self):
		self.assertIs(
			get_type_hints(Worker.__init__)['broker'],
			Connection,
		)
		self.assertNotIn(
			'WorkerConnection',
			worker_exports,
		)
		connections = (
			StructuralConnection(),
			RabbitConnection(RabbitConfiguration(
				host='127.0.0.1',
				port=5672,
				username='guest',
				password='guest',
			)),
			RedisConnection(RedisConfiguration()),
		)
		for connection in connections:
			broker: Connection = connection
			worker = Worker(
				broker,
				Mock(),
			)
			self.assertIs(
				worker.broker,
				connection,
			)
			self.assertIsInstance(
				connection,
				GetConsumer,
			)
		self.assertIs(
			queue_provider(RedisConnection(RedisConfiguration())).__class__,
			RedisConnection,
		)

	def test_worker_rejects_connection_without_consumer_creation(self):
		class ProducerConnection(Connection):
			def connect(self) -> None:
				return

			def close(self) -> None:
				return

		class Task(
			Run,
			parameters={'queue': 'protocol-test'},
		):
			def run(self):
				return

		connection = ProducerConnection()
		self.assertNotIsInstance(
			connection,
			GetConsumer,
		)
		pool = Mock()
		worker = Worker(
			connection,
			pool,
		)
		worker.add(Task)
		with self.assertRaisesRegex(
			TypeError,
			'Worker broker must support consumer creation',
		):
			worker.run()
		pool.stop.assert_called_once_with()
		self.assertTrue(worker.finished.is_set())
		return

	def test_existing_event_codec_and_policy_protocols_are_explicit(self):
		for implementation, contract in (
			(
				RedisEvent,
				Event,
			),
			(
				RabbitEvent,
				Event,
			),
			(
				FailedRequest,
				Event,
			),
			(
				RabbitRequeue,
				EventErrorPolicy,
			),
			(
				RabbitReject,
				EventErrorPolicy,
			),
			(
				RedisRequeue,
				EventErrorPolicy,
			),
			(
				RedisReject,
				EventErrorPolicy,
			),
			(
				JavaScriptObjectNotationEncoder,
				Encoder,
			),
			(
				JavaScriptObjectNotationDecoder,
				Decoder,
			),
		):
			with self.subTest(implementation=implementation):
				self.assertIn(
					contract,
					implementation.__bases__,
				)
		self.assertNotIn('EventError', broker_exports)
		self.assertIn('EventErrorPolicy', broker_exports)
		self.assertNotIn('Requeue', broker_exports)
		self.assertNotIn('Reject', broker_exports)
		self.assertIn('Requeue', rabbit_exports)
		self.assertIn('Reject', rabbit_exports)
		self.assertIn('Requeue', redis_exports)
		self.assertIn('Reject', redis_exports)

	def test_redis_event_body_is_readable_after_protocol_inheritance(self):
		body = {'value': 1}
		event = RedisEvent(
			Mock(),
			'queue',
			'1-0',
			body,
			'group',
		)
		contract: Event = event
		self.assertIs(
			contract.body,
			body,
		)
		event.body = {'value': 2}
		self.assertEqual(
			event.body,
			{'value': 2},
		)
		event.ack()

	def test_factory_protocols_return_concrete_resources(self):
		rabbit_connection = RabbitConnection(RabbitConfiguration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		))
		redis_connection = RedisConnection(RedisConfiguration())
		rabbit_connection.connection = Mock()
		redis_connection.connection = Mock()
		rabbit: GetQueue = rabbit_connection
		redis: GetQueue = redis_connection
		self.assertIsInstance(
			rabbit.queue('protocol-test'),
			RabbitQueue,
		)
		self.assertIsInstance(
			redis.queue('protocol-test'),
			RedisQueue,
		)


if __name__ == '__main__':
	main()
