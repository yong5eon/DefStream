from unittest import TestCase
from unittest.mock import Mock

from DefStream.Validator import Patterns
from DefStream.Validator.Patterns import (
	IsOptional,
	IsTypeOf,
)
from DefStream.Validator.Patterns.Common import (
	IsOptional as CommonIsOptional,
	__all__ as common_exports,
)


class IsOptionalTests(TestCase):
	def test_type_sequences_are_normalized_for_runtime_checks(self):
		pattern = IsTypeOf([
			int,
			float,
		])

		self.assertEqual(pattern(1), 1)
		self.assertEqual(pattern(1.5), 1.5)
		with self.assertRaises(TypeError):
			pattern('1')

	def test_none_is_returned_without_running_patterns(self):
		pattern = Mock()

		result = IsOptional(pattern)(None)

		self.assertIsNone(result)
		pattern.assert_not_called()

	def test_patterns_are_applied_in_order(self):
		first = Mock(return_value=2)
		second = Mock(return_value=3)

		result = IsOptional(first, second)(1)

		self.assertEqual(result, 3)
		first.assert_called_once_with(1)
		second.assert_called_once_with(2)

	def test_repr_uses_public_class_name(self):
		self.assertEqual(repr(IsOptional()), 'IsOptional()')

	def test_pattern_errors_are_propagated(self):
		error = RuntimeError('pattern failed')
		pattern = Mock(side_effect=error)

		with self.assertRaises(RuntimeError) as raised:
			IsOptional(pattern)(1)

		self.assertIs(raised.exception, error)

	def test_class_is_exported_without_legacy_name(self):
		self.assertIs(CommonIsOptional, IsOptional)
		self.assertIn('IsOptional', common_exports)
		self.assertIn('IsOptional', Patterns.__all__)
		self.assertFalse(hasattr(Patterns, 'IsToNone'))
		self.assertFalse(hasattr(Patterns.Common, 'IsToNone'))
