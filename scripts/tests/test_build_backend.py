from os import environ
from unittest import (
	TestCase,
	main,
)
from unittest.mock import patch

from build_backend import (
	build_editable,
	editable_settings,
	regular_settings,
	selected_extras,
)
from build_distributions import IMPLEMENTATIONS


class BuildBackendTests(TestCase):
	def test_omitted_and_empty_extras_select_core_only(self) -> None:
		self.assertEqual(
			selected_extras(None),
			[],
		)
		self.assertEqual(
			selected_extras({'EXTRAS': ''}),
			[],
		)
		return

	def test_comma_lists_case_and_repeated_values(self) -> None:
		targets: list[str] = list(IMPLEMENTATIONS)
		self.assertEqual(
			selected_extras({'EXTRAS': [
				' ' + targets[0].lower() + ', ' + targets[1],
				targets[0],
			]}),
			targets,
		)
		return

	def test_unknown_and_empty_list_entries_are_rejected(self) -> None:
		for value in (
			'unknown',
			next(iter(IMPLEMENTATIONS)) + ',',
		):
			with self.subTest(value=value), self.assertRaises(ValueError):
				selected_extras({'EXTRAS': value})
		return

	def test_editable_hooks_override_target_and_restore_environment_on_failure(self) -> None:
		target: str = next(iter(IMPLEMENTATIONS))
		with patch.dict(
			environ,
			{
				'DEF_BUILD_TARGET': target,
				'DEF_EDITABLE_EXTRAS': 'previous',
			},
		):
			with self.assertRaisesRegex(
				RuntimeError,
				'build failure',
			):
				with editable_settings({'EXTRAS': target}) as settings:
					self.assertEqual(
						settings,
						{},
					)
					self.assertEqual(
						environ['DEF_BUILD_TARGET'],
						'core',
					)
					self.assertEqual(
						environ['DEF_EDITABLE_EXTRAS'],
						target,
					)
					raise RuntimeError('build failure')
			self.assertEqual(
				environ['DEF_BUILD_TARGET'],
				target,
			)
			self.assertEqual(
				environ['DEF_EDITABLE_EXTRAS'],
				'previous',
			)
		return

	def test_extras_is_not_silently_accepted_for_regular_builds(self) -> None:
		with self.assertRaisesRegex(
			ValueError,
			'only supported',
		):
			regular_settings({'EXTRAS': ''})
		return

	def test_hook_forwards_only_setuptools_settings(self) -> None:
		target: str = next(iter(IMPLEMENTATIONS))
		with patch(
			'build_backend.build_meta.build_editable',
			return_value='example.whl',
		) as backend:
			self.assertEqual(
				build_editable(
					'wheel',
					{
						'EXTRAS': target,
						'editable_mode': 'strict',
					},
					'metadata',
				),
				'example.whl',
			)
			backend.assert_called_once_with(
				'wheel',
				{'editable_mode': 'strict'},
				'metadata',
			)
		return


if __name__ == '__main__':
	main()
