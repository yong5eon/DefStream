from json import dumps
from os import link
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import (
	TestCase,
	main,
)
from unittest.mock import patch

from editable_view import (
	collect_files,
	refresh,
	relative_path,
)


class EditableViewTests(TestCase):
	def test_hardlink_refresh_keeps_existing_files_until_atomic_replacement(self) -> None:
		with TemporaryDirectory() as temporary:
			root: Path = Path(temporary)
			view: Path = root / 'view'
			view.mkdir()
			core: Path = root / 'core.py'
			changed: Path = root / 'changed.py'
			core.write_text('CORE = 1\n')
			changed.write_text('VALUE = 1\n')
			files: dict[str, str] = {
				'Example/__init__.py': str(core),
				'Example/changed.py': str(changed),
			}
			with patch('editable_view.create_link', side_effect=link):
				refresh(view, 'Example', files)
			core_link: Path = view / 'Example/__init__.py'
			changed_link: Path = view / 'Example/changed.py'
			core_inode: int = core_link.stat().st_ino
			replacement: Path = root / 'replacement.py'
			replacement.write_text('VALUE = 2\n')
			replacement.replace(changed)

			def observe(
				source: Path,
				destination: Path,
			) -> None:
				self.assertEqual(core_link.stat().st_ino, core_inode)
				self.assertEqual(changed_link.read_text(), 'VALUE = 1\n')
				link(source, destination)
				return

			with patch('editable_view.create_link', side_effect=observe) as create:
				refresh(view, 'Example', files)
			self.assertEqual(create.call_count, 1)
			self.assertEqual(core_link.stat().st_ino, core_inode)
			self.assertTrue(changed_link.samefile(changed))
		return

	def test_selection_change_preserves_unmanaged_files_and_unchanged_core(self) -> None:
		with TemporaryDirectory() as temporary:
			root: Path = Path(temporary)
			view: Path = root / 'view'
			view.mkdir()
			source: Path = root / 'source.py'
			source.write_text('VALUE = 1\n')
			files: dict[str, str] = {
				'Example/__init__.py': str(source),
				'Example/Selected/__init__.py': str(source),
			}
			refresh(view, 'Example', files)
			unmanaged: Path = view / 'Example/Selected/.DS_Store'
			unmanaged.write_text('unmanaged')
			with patch('editable_view.create_link', side_effect=AssertionError('Unchanged link recreated')):
				refresh(view, 'Example', {'Example/__init__.py': str(source)})
			self.assertEqual(unmanaged.read_text(), 'unmanaged')
			self.assertTrue((view / 'Example/__init__.py').samefile(source))
			self.assertFalse((view / 'Example/Selected/__init__.py').exists())
		return

	def test_failed_replacement_preserves_old_link_and_state(self) -> None:
		with TemporaryDirectory() as temporary:
			root: Path = Path(temporary)
			view: Path = root / 'view'
			view.mkdir()
			source: Path = root / 'source.py'
			source.write_text('VALUE = 1\n')
			files: dict[str, str] = {'Example/__init__.py': str(source)}
			with patch('editable_view.create_link', side_effect=link):
				refresh(view, 'Example', files)
			state: bytes = (view / 'files.json').read_bytes()
			replacement: Path = root / 'replacement.py'
			replacement.write_text('VALUE = 2\n')
			replacement.replace(source)
			with patch('editable_view.create_link', side_effect=PermissionError('link failed')):
				with self.assertRaises(PermissionError):
					refresh(view, 'Example', files)
			self.assertEqual((view / 'Example/__init__.py').read_text(), 'VALUE = 1\n')
			self.assertEqual((view / 'files.json').read_bytes(), state)
			self.assertEqual(sorted(path.name for path in (view / 'Example').iterdir()), ['__init__.py'])
		return

	def test_single_editable_rejects_legacy_implementation_distributions(self) -> None:
		with TemporaryDirectory() as temporary:
			site: Path = Path(temporary)
			for name in (
				'Example',
				'Example-Selected',
			):
				info: Path = site / (name + '-1.0.dist-info')
				info.mkdir()
				(info / 'METADATA').write_text(
					'Name: {}\nVersion: 1.0\n'.format(name),
					encoding='utf-8',
				)
			(site / 'Example-1.0.dist-info/editable-selection.json').write_text(
				'[]',
				encoding='utf-8',
			)
			with self.assertRaisesRegex(
				RuntimeError,
				'Remove legacy implementation distributions',
			):
				collect_files(
					site,
					'Example',
					(
						'Example',
						'Example-Selected',
					),
				)
		return

	def test_selection_changes_remove_files_and_namespace_directories(self) -> None:
		with TemporaryDirectory() as temporary:
			root: Path = Path(temporary)
			view: Path = root / 'view'
			view.mkdir()
			core: Path = root / 'core.py'
			core.write_text(
				'VALUE = 1\n',
				encoding='utf-8',
			)
			implementation: Path = root / 'implementation.py'
			implementation.write_text(
				'VALUE = 2\n',
				encoding='utf-8',
			)
			files: dict[str, str] = {
				'Example/__init__.py': str(core),
				'Example/Implements/Selected/__init__.py': str(implementation),
			}
			refresh(
				view,
				'Example',
				files,
			)
			linked: Path = view / 'Example/Implements/Selected/__init__.py'
			self.assertTrue(linked.samefile(implementation))
			cache: Path = linked.parent / '__pycache__'
			cache.mkdir()
			(cache / '__init__.cpython-313.pyc').write_bytes(b'cached')
			refresh(
				view,
				'Example',
				{'Example/__init__.py': str(core)},
			)
			self.assertFalse((view / 'Example/Implements').exists())
			self.assertTrue((view / 'Example/__init__.py').samefile(core))
		return

	def test_refresh_preserves_unchanged_files_and_reflects_source_edits(self) -> None:
		with TemporaryDirectory() as temporary:
			root: Path = Path(temporary)
			view: Path = root / 'view'
			view.mkdir()
			source: Path = root / 'source.py'
			source.write_text(
				'VALUE = 1\n',
				encoding='utf-8',
			)
			files: dict[str, str] = {'Example/__init__.py': str(source)}
			refresh(
				view,
				'Example',
				files,
			)
			state: Path = view / 'files.json'
			changed: int = state.stat().st_mtime_ns
			source.write_text(
				'VALUE = 200\n',
				encoding='utf-8',
			)
			refresh(
				view,
				'Example',
				files,
			)
			self.assertEqual(
				state.stat().st_mtime_ns,
				changed,
			)
			self.assertEqual(
				(view / 'Example/__init__.py').read_text(encoding='utf-8'),
				'VALUE = 200\n',
			)
		return

	def test_recorded_paths_cannot_escape_managed_view(self) -> None:
		for value in (
			'../outside.py',
			'Other/__init__.py',
			'/Example/module.py',
		):
			with self.subTest(value=value), self.assertRaises(ValueError):
				relative_path(
					value,
					'Example',
				)
		with TemporaryDirectory() as temporary:
			view: Path = Path(temporary) / 'view'
			view.mkdir()
			(view / 'files.json').write_text(
				dumps({'../outside.py': 'outside.py'}),
				encoding='utf-8',
			)
			with self.assertRaises(ValueError):
				refresh(
					view,
					'Example',
					{},
				)
		return

	def test_source_replacement_refreshes_existing_links(self) -> None:
		with TemporaryDirectory() as temporary:
			root: Path = Path(temporary)
			view: Path = root / 'view'
			view.mkdir()
			source: Path = root / 'source.py'
			source.write_text(
				'VALUE = 1\n',
				encoding='utf-8',
			)
			files: dict[str, str] = {'Example/__init__.py': str(source)}
			refresh(
				view,
				'Example',
				files,
			)
			replacement: Path = root / 'replacement.py'
			replacement.write_text(
				'VALUE = 200\n',
				encoding='utf-8',
			)
			replacement.replace(source)
			refresh(
				view,
				'Example',
				files,
			)
			self.assertTrue((view / 'Example/__init__.py').samefile(source))
		return

	def test_missing_editable_core_is_explicit_error(self) -> None:
		with TemporaryDirectory() as temporary, self.assertRaisesRegex(
			RuntimeError,
			'requires its core',
		):
			collect_files(
				Path(temporary),
				'Example',
				('Example',),
			)
		return

	def test_environment_metadata_selects_only_its_own_sources(self) -> None:
		with TemporaryDirectory() as temporary:
			root: Path = Path(temporary)
			source: Path = root / 'source.py'
			source.write_text(
				'VALUE = 1\n',
				encoding='utf-8',
			)
			site: Path = root / 'site'
			info: Path = site / 'example-1.0.dist-info'
			info.mkdir(parents=True)
			(info / 'METADATA').write_text(
				'Name: Example\nVersion: 1.0\n',
				encoding='utf-8',
			)
			mapping: dict[str, str] = {'Example/__init__.py': str(source)}
			(info / 'editable-files.json').write_text(
				dumps(mapping),
				encoding='utf-8',
			)
			self.assertEqual(
				collect_files(
					site,
					'Example',
					(
						'Example',
						'Example-Selected',
					),
				),
				mapping,
			)
			source.unlink()
			with self.assertRaises(FileNotFoundError):
				collect_files(
					site,
					'Example',
					('Example',),
				)
		return


if __name__ == '__main__':
	main()
