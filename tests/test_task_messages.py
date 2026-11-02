from typing import get_type_hints
from unittest import (
	TestCase,
	main,
)
from unittest.mock import (
	Mock,
)
from DefStream.Broker import (
	Connection,
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
				{'body': {}},
			),
			(
				request,
				{'body': {}},
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
