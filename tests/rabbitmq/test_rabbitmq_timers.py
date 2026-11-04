from os import environ
from pathlib import Path
from runpy import run_path
from threading import get_ident
from time import monotonic
from typing import (
	Any,
	Dict,
	List,
	Tuple,
)
from unittest import (
	TestCase,
	main,
	skipUnless,
)
from unittest.mock import (
	Mock,
	call,
	patch,
	sentinel,
)
from uuid import uuid4

from pika import BlockingConnection

from DefStream.Broker import (
	Event,
	Timer,
	TimerCallback,
)
from DefStream.Broker.Implements.RabbitMQ import (
	Configuration,
	Connection,
	Consumer,
)
from tests._support import rabbitmq_test_port


class TimerTests(TestCase):
	def setUp(self) -> None:
		self.broker: Connection = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		))
		self.connection: Mock = Mock(spec=BlockingConnection)
		self.connection.call_later.return_value = sentinel.timeout
		self.broker.connection = self.connection
		self.addCleanup(self.broker.close)
		return

	def test_positional_and_keyword_registration(self) -> None:
		cb: Mock = Mock()
		for keyword in (
			False,
			True,
		):
			with self.subTest(keyword=keyword):
				self.connection.reset_mock()
				timer: Timer
				if keyword:
					timer = self.broker.set_timer(cb=cb, seconds=5)
				else:
					timer = self.broker.set_timer(cb, 5)
				self.connection.call_later.assert_called_once_with(5, cb)
				cb.assert_not_called()
				self.assertIsInstance(timer, Timer)
				timer.remove()
				self.connection.remove_timeout.assert_called_once_with(sentinel.timeout)
		return

	def test_functions_and_callable_objects_are_passed_unchanged(self) -> None:
		calls: List[str] = []

		def callback() -> None:
			calls.append('function')
			return

		class Callback:
			def __call__(self) -> None:
				calls.append('object')
				return

		callbacks: Tuple[TimerCallback, ...] = (
			callback,
			Callback(),
		)
		for cb in callbacks:
			with self.subTest(callback=cb):
				self.connection.reset_mock()
				self.broker.set_timer(cb, 5)
				self.connection.call_later.assert_called_once_with(5, cb)
				self.assertIs(self.connection.call_later.call_args.args[1], cb)
		self.assertEqual(calls, [])
		return

	def test_registration_uses_existing_open_connection_check(self) -> None:
		self.connection.is_open = False
		with self.assertLogs('Broker.RabbitMQ.Connection', level='ERROR'):
			with self.assertRaisesRegex(RuntimeError, 'before use'):
				self.broker.set_timer(Mock(), 5)
		self.connection.call_later.assert_not_called()
		return

	def test_removal_keeps_registration_connection(self) -> None:
		timer: Timer = self.broker.set_timer(Mock(), 5)
		replacement: Mock = Mock(spec=BlockingConnection)
		self.broker.connection = replacement
		timer.remove()
		self.connection.remove_timeout.assert_called_once_with(sentinel.timeout)
		replacement.remove_timeout.assert_not_called()
		return

	def test_repeated_removal_is_delegated(self) -> None:
		timer: Timer = self.broker.set_timer(Mock(), 5)
		timer.remove()
		timer.remove()
		self.assertEqual(
			self.connection.remove_timeout.call_args_list,
			[
				call(sentinel.timeout),
				call(sentinel.timeout),
			],
		)
		return

	def test_delay_values_are_not_reinterpreted(self) -> None:
		cb: Mock = Mock()
		for seconds in (
			-1,
			0,
			5,
		):
			with self.subTest(seconds=seconds):
				self.connection.reset_mock()
				self.broker.set_timer(cb, seconds)
				self.connection.call_later.assert_called_once_with(seconds, cb)
		return

	def test_registration_error_is_propagated(self) -> None:
		failure: ValueError = ValueError('Timer registration failed')
		self.connection.call_later.side_effect = failure
		with self.assertLogs('Broker.RabbitMQ.Connection', level='ERROR'):
			with self.assertRaises(ValueError) as raised:
				self.broker.set_timer(Mock(), 5)
		self.assertIs(raised.exception, failure)
		return

	def test_removal_error_is_propagated(self) -> None:
		timer: Timer = self.broker.set_timer(Mock(), 5)
		failure: RuntimeError = RuntimeError('Timer removal failed')
		self.connection.remove_timeout.side_effect = failure
		with self.assertRaises(RuntimeError) as raised:
			timer.remove()
		self.assertIs(raised.exception, failure)
		return

	def test_timer_sample_registers_cancels_and_repeats(self) -> None:
		broker: Mock = Mock(spec=Connection)
		consumer: Mock = broker.consumer.return_value
		timers: Tuple[Mock, ...] = tuple(Mock(spec=Timer) for _ in range(4))
		broker.set_timer.side_effect = timers

		def consume() -> None:
			for _ in range(3):
				cb: TimerCallback = broker.set_timer.call_args.args[0]
				cb()
			return

		consumer.run.side_effect = consume
		path: Path = Path(__file__).resolve().parents[2] / 'samples' / 'Broker' / 'RabbitMQ' / 'Sample.Timer.py'
		with patch('DefStream.Broker.Implements.RabbitMQ.Connection', return_value=broker):
			namespace: Dict[str, Any] = run_path(str(path), run_name='sample_import_test')
			namespace['main']()
		self.assertEqual(broker.set_timer.call_count, 4)
		for registration in broker.set_timer.call_args_list:
			self.assertEqual(registration.args[1], 1)
		timers[0].remove.assert_called_once()
		timers[-1].remove.assert_called_once()
		for timer in timers[1:-1]:
			timer.remove.assert_not_called()
		consumer.stop.assert_called_once()
		consumer.close.assert_called_once()
		queue: str = broker.create_queue.call_args.args[0]
		broker.delete_queue.assert_called_once_with(queue)
		broker.close.assert_called_once()
		return


@skipUnless(environ.get('RABBITMQ_TESTS') == '1', 'Opt-in local RabbitMQ integration')
class RabbitMQTimerIntegrationTests(TestCase):
	def setUp(self) -> None:
		self.broker: Connection = Connection(Configuration(
			host='127.0.0.1',
			port=rabbitmq_test_port(),
			username='guest',
			password='guest',
		))
		self.broker.parameters.socket_timeout = 2
		self.broker.parameters.stack_timeout = 3
		self.addCleanup(self.broker.close)
		self.broker.connect()
		queue: str = 'defstream-timer-test-' + uuid4().hex
		self.broker.create_queue(queue)
		self.addCleanup(self.broker.delete_queue, queue)
		self.consumer: Consumer = self.broker.consumer()
		self.addCleanup(self.consumer.close)
		self.consumer.subs(queue, self.unexpected_message)
		connection: BlockingConnection = self.broker.connected()
		watchdog: int = connection.call_later(5, self.expired)
		self.addCleanup(connection.remove_timeout, watchdog)
		return

	def unexpected_message(
		self,
		event: Event,
	) -> None:
		self.fail('The timer test queue must remain empty')

	def expired(self) -> None:
		self.fail('Timer test did not finish within five seconds')

	def test_idle_timer_runs_once_on_owner_thread(self) -> None:
		threads: List[int] = []
		owner: int = get_ident()
		started: float = monotonic()

		def callback() -> None:
			threads.append(get_ident())
			self.consumer.stop()
			return

		timer: Timer = self.broker.set_timer(callback, 1)
		self.addCleanup(timer.remove)
		self.consumer.run()
		self.assertEqual(threads, [owner])
		self.assertGreaterEqual(monotonic() - started, 1)
		return

	def test_cancelled_timer_does_not_run(self) -> None:
		callback: Mock = Mock()
		timer: Timer = self.broker.set_timer(callback, 1)
		timer.remove()
		timer.remove()
		stop: Timer = self.broker.set_timer(self.consumer.stop, 2)
		self.addCleanup(stop.remove)
		self.consumer.run()
		callback.assert_not_called()
		return

	def test_callback_can_register_next_timer(self) -> None:
		threads: List[int] = []
		owner: int = get_ident()

		def callback() -> None:
			threads.append(get_ident())
			if len(threads) == 3:
				self.consumer.stop()
			else:
				next_timer: Timer = self.broker.set_timer(callback, 1)
				self.addCleanup(next_timer.remove)
			return

		timer: Timer = self.broker.set_timer(callback, 1)
		self.addCleanup(timer.remove)
		self.consumer.run()
		self.assertEqual(threads, [owner] * 3)
		return

	def test_callback_exception_reaches_consumption_loop(self) -> None:
		failure: ValueError = ValueError('Timer callback failed')

		def callback() -> None:
			raise failure

		timer: Timer = self.broker.set_timer(callback, 1)
		self.addCleanup(timer.remove)
		with self.assertLogs('Broker.RabbitMQ.Consumer', level='ERROR'):
			with self.assertRaises(ValueError) as raised:
				self.consumer.run()
		self.assertIs(raised.exception, failure)
		return


if __name__ == '__main__':
	main()
