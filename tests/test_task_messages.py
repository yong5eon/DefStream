from threading import TIMEOUT_MAX
from typing import get_type_hints
from unittest import (
	TestCase,
	main,
)
from unittest.mock import (
	Mock,
	call,
	patch,
)
from DefStream.Broker import (
	Connection,
	PrioritySupport,
	RemoteError,
)
from DefStream.Worker import (
	declare,
	Run,
	Worker,
	emit,
	request,
)
from DefStream.Worker import __all__ as worker_exports
from tests._support import (
	call_with_invalid_input,
)
from tests._support_task_messages import Task


class MessageTests(TestCase):
	def test_emit_replaces_send_without_compatibility_alias(self):
		self.assertIn(
			'emit',
			worker_exports,
		)
		self.assertNotIn(
			'send',
			worker_exports,
		)

	def test_helpers_accept_common_connection_and_check_each_capability(self):
		for helper in (
			declare,
			emit,
			request,
		):
			self.assertIs(
				get_type_hints(helper)['broker'],
				Connection,
			)
		broker = Mock(
			spec=Connection,
			declare=Mock(),
			emit=Mock(return_value='message-id'),
			request=Mock(return_value=3),
		)
		declare(
			task=Task,
			broker=broker,
		)
		self.assertEqual(
			emit(
				{},
				task=Task,
				broker=broker,
			),
			'message-id',
		)
		self.assertEqual(
			request(
				{},
				task=Task,
				broker=broker,
			),
			3,
		)
		broker.connect.assert_not_called()
		broker.close.assert_not_called()
		return

	def test_helpers_reject_missing_capabilities_before_broker_io(self):
		broker = Mock(spec=Connection)
		for helper, arguments in (
			(
				declare,
				{},
			),
			(
				emit,
				{
					'body': {},
					'retry': 2,
				},
			),
			(
				request,
				{
					'body': {},
					'retry': 2,
				},
			),
			(
				request,
				{
					'body': {},
					'priority': 1,
				},
			),
		):
			with self.subTest(helper=helper, arguments=arguments), self.assertRaises(NotImplementedError):
				call_with_invalid_input(
					helper,
					task=Task,
					broker=broker,
					**arguments,
				)
		self.assertEqual(
			broker.mock_calls,
			[],
		)
		return

	def test_request_does_not_require_emission_capability(self):
		broker = Mock(
			spec=Connection,
			request=Mock(return_value=3),
		)
		self.assertEqual(
			request(
				{},
				task=Task,
				broker=broker,
			),
			3,
		)
		broker.request.assert_called_once_with(
			{},
			Task.parameters,
			timeout=5,
		)
		return

	def test_emit_retries_until_success_and_waits_between_attempts(self):
		broker = Mock(
			spec=PrioritySupport,
			emit=Mock(side_effect=[
				RuntimeError('temporary failure'),
				RuntimeError('temporary failure'),
				'message-id',
			]),
		)
		broker.priority_parameters.return_value = Task.parameters
		with patch('DefStream.Worker.Message.sleep') as wait:
			self.assertEqual(
				emit(
					{'a': 1},
					task=Task,
					broker=broker,
					priority=3,
					retry=3,
					interval=0.25,
				),
				'message-id',
			)
		self.assertEqual(
			broker.emit.call_count,
			3,
		)
		self.assertEqual(
			wait.call_args_list,
			[
				call(0.25),
				call(0.25),
			],
		)
		broker.emit.assert_has_calls([
			call(
				{'a': 1},
				Task.parameters,
				priority=3,
			),
			call(
				{'a': 1},
				Task.parameters,
				priority=3,
			),
			call(
				{'a': 1},
				Task.parameters,
				priority=3,
			),
		])

	def test_request_retries_remote_errors_and_preserves_timeout(self):
		broker = Mock(
			spec=PrioritySupport,
			request=Mock(side_effect=[
				RemoteError(
					'TaskError',
					'temporary failure',
				),
				3,
			]),
		)
		broker.priority_parameters.return_value = Task.parameters
		with patch('DefStream.Worker.Message.sleep') as wait:
			self.assertEqual(
				request(
					{'a': 1},
					task=Task,
					broker=broker,
					timeout=2,
					priority=4,
					retry=1,
					interval=0.5,
				),
				3,
			)
		broker.request.assert_has_calls([
			call(
				{'a': 1},
				Task.parameters,
				timeout=2,
				priority=4,
			),
			call(
				{'a': 1},
				Task.parameters,
				timeout=2,
				priority=4,
			),
		])
		wait.assert_called_once_with(0.5)

	def test_no_retry_default_and_zero_call_once(self):
		for helper in (
			emit,
			request,
		):
			for retry in (
				None,
				0,
			):
				broker = Mock(
					emit=Mock(side_effect=RuntimeError('broker call failed')),
					request=Mock(side_effect=RuntimeError('broker call failed')),
				)
				with self.subTest(helper=helper, retry=retry), patch(
					'DefStream.Worker.Message.sleep',
				) as wait:
					with self.assertRaisesRegex(
						RuntimeError,
						'broker call failed',
					):
						helper(
							{},
							task=Task,
							broker=broker,
							retry=retry,
						)
				if helper is emit:
					broker.emit.assert_called_once_with(
						{},
						Task.parameters,
					)
					broker.request.assert_not_called()
				else:
					broker.emit.assert_not_called()
					broker.request.assert_called_once_with(
						{},
						Task.parameters,
						timeout=5,
					)
				wait.assert_not_called()

	def test_retries_stop_at_limit_and_raise_the_last_exception(self):
		errors = [
			RuntimeError('first failure'),
			RuntimeError('second failure'),
			RuntimeError('third failure'),
			RuntimeError('last failure'),
		]
		broker = Mock(
			emit=Mock(side_effect=errors),
		)
		with patch('DefStream.Worker.Message.sleep') as wait:
			with self.assertRaises(RuntimeError) as raised:
				emit(
					{},
					task=Task,
					broker=broker,
					retry=3,
				)
		self.assertIs(
			raised.exception,
			errors[-1],
		)
		self.assertEqual(
			broker.emit.call_count,
			4,
		)
		self.assertEqual(
			wait.call_args_list,
			[
				call(1),
				call(1),
				call(1),
			],
		)

	def test_retry_settings_are_validated_before_broker_calls(self):
		broker = Mock(
			spec=Connection,
			emit=Mock(),
			request=Mock(),
		)
		for helper in (
			emit,
			request,
		):
			for value, error in (
				(True, TypeError),
				(1.5, TypeError),
				(-1, ValueError),
			):
				with self.subTest(helper=helper, retry=value), self.assertRaises(error):
					helper(
						{},
						task=Task,
						broker=broker,
						retry=value,
					)
			for value, error in (
				(True, TypeError),
				('1', TypeError),
				(-0.1, ValueError),
				(float('inf'), ValueError),
				(float('nan'), ValueError),
			):
				with self.subTest(helper=helper, interval=value), self.assertRaises(error):
					helper(
						{},
						task=Task,
						broker=broker,
						interval=value,
					)
		broker.emit.assert_not_called()
		broker.request.assert_not_called()

	def test_interval_above_timeout_max_is_rejected_before_broker_calls(self):
		for helper in (
			emit,
			request,
		):
			for interval in (
				10**400,
				1e100,
				TIMEOUT_MAX + 1,
			):
				broker = Mock(
					spec=Connection,
					emit=Mock(),
					request=Mock(),
				)
				with self.subTest(helper=helper, interval=interval), patch(
					'DefStream.Worker.Message.sleep',
				) as wait:
					with self.assertRaises(ValueError):
						helper(
							{},
							task=Task,
							broker=broker,
							retry=1,
							interval=interval,
						)
					broker.emit.assert_not_called()
					broker.request.assert_not_called()
					wait.assert_not_called()

	def test_interval_boundaries_are_passed_to_retry_wait(self):
		for helper in (
			emit,
			request,
		):
			for interval in (
				0,
				TIMEOUT_MAX,
			):
				result = object()
				operation = Mock(side_effect=[
					RuntimeError('broker call failed'),
					result,
				])
				broker = Mock(
					spec=Connection,
					**{helper.__name__: operation},
				)
				with self.subTest(helper=helper, interval=interval), patch(
					'DefStream.Worker.Message.sleep',
				) as wait:
					self.assertIs(
						helper(
							{},
							task=Task,
							broker=broker,
							retry=1,
							interval=interval,
						),
						result,
					)
					self.assertEqual(operation.call_count, 2)
					wait.assert_called_once_with(interval)

	def test_declare_delegates_without_owning_connection(self):
		broker = Mock()
		broker.declare = Mock()
		declare(
			task=Task,
			broker=broker,
		)
		broker.declare.assert_called_once_with(Task.parameters)
		broker.connect.assert_not_called()
		broker.close.assert_not_called()
		self.assertFalse(hasattr(
			Worker,
			'declare',
		))
		broker.declare.side_effect = RuntimeError('declaration failed')
		with self.assertRaisesRegex(
			RuntimeError,
			'declaration failed',
		):
			declare(
				task=Task,
				broker=broker,
			)
		broker.close.assert_not_called()

	def test_declare_validates_task_before_calling_broker(self):
		broker = Mock()
		broker.declare = Mock()
		with self.assertRaises(TypeError):
			declare(
				task=Run,
				broker=broker,
			)

		class MissingParameters(Run):
			def run(self):
				pass

		with self.assertRaises(ValueError):
			declare(
				task=MissingParameters,
				broker=broker,
			)
		broker.declare.assert_not_called()

	def test_helpers_delegate_without_owning_connection(self):
		broker = Mock()
		broker.emit = Mock()
		broker.request = Mock(return_value=3)
		for _ in range(1000):
			emit(
				{
					'a': 1,
					'b': 2,
				},
				task=Task,
				broker=broker,
			)
		self.assertEqual(
			broker.emit.call_count,
			1000,
		)
		broker.emit.assert_called_with(
			{
				'a': 1,
				'b': 2,
			},
			Task.parameters,
		)
		self.assertEqual(
			request(
				{
					'a': 1,
					'b': 2,
				},
				task=Task,
				broker=broker,
				timeout=2,
			),
			3,
		)
		broker.connect.assert_not_called()
		broker.close.assert_not_called()
		broker.declare.assert_not_called()

	def test_invalid_inputs_and_unsupported_operations_are_explicit(self):
		for body in (
			None,
			[1],
			{1: 'invalid'},
		):
			with self.subTest(body=body), self.assertRaises(TypeError):
				call_with_invalid_input(
					emit,
					body,
					task=Task,
					broker=Mock(),
				)
		for task in (
			Run,
			Task(),
			object,
		):
			with self.subTest(task=task), self.assertRaises(TypeError):
				call_with_invalid_input(
					emit,
					{},
					task=task,
					broker=Mock(),
				)
		with self.assertRaises(NotImplementedError):
			call_with_invalid_input(
				declare,
				task=Task,
				broker=object(),
			)

if __name__ == '__main__':
	main()
