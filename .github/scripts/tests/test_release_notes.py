from json import dumps
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
from typing import Optional
from unittest import TestCase
from unittest.mock import (
	MagicMock,
	patch,
)


class ReleaseNotesTests(TestCase):
	def setUp(self) -> None:
		self.directory: TemporaryDirectory = TemporaryDirectory()
		self.addCleanup(self.directory.cleanup)
		self.notes: Path = Path(self.directory.name) / 'release-notes' / 'README.md'
		workflow: str = (Path(__file__).resolve().parents[3] / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
		step: str = workflow.split('      - name: Collect branch changelog for release\n', 1)[1]
		script: str = step.split("          python - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
		self.script: str = dedent(script)
		self.check_output: MagicMock = MagicMock()
		return

	def pull(self, body: Optional[str], branch: str = 'task/12') -> dict[str, object]:
		return {
			'merged_at': '2026-01-01T00:00:00Z',
			'merge_commit_sha': 'test-head',
			'base': {'ref': 'master', 'repo': {'full_name': 'example/project'}},
			'head': {'ref': branch},
			'body': body,
		}

	def run_collector(self, version: str = 'true') -> bytes:
		env: dict[str, str] = {
			'GITHUB_SHA': 'test-head',
			'GITHUB_REPOSITORY': 'example/project',
			'BEFORE': 'test-before',
			'NEW_VERSION': version,
			'RELEASE_TAG': 'v1',
			'RUNNER_TEMP': self.directory.name,
		}
		with patch.dict(environ, env), patch('subprocess.check_output', self.check_output):
			exec(self.script, {})
		return self.notes.read_bytes()

	def test_explicit_issue_and_non_issue_paths_override_branch(self) -> None:
		for path in (
			'issues/task/12/CHANGELOG.md',
			'tasks/1794057212842/CHANGELOG.md',
		):
			with self.subTest(path=path):
				self.check_output.reset_mock()
				self.check_output.side_effect = [
					dumps([[self.pull(f'- Changes: {path}', 'copilot/change')]]).encode(),
					b'100644 blob abc\tfile\n',
					b'approved notes',
				]
				self.assertEqual(self.run_collector(), b'approved notes')
				self.assertEqual(self.check_output.call_args_list[1].args[0], ['git', 'ls-tree', 'test-head', '--', path])
				self.assertEqual(self.check_output.call_args_list[2].args[0], ['git', 'show', f'test-head:{path}'])
		return

	def test_missing_marker_keeps_branch_based_path(self) -> None:
		for body in (
			None,
			'- Changes: tasks/999/CHANGELOG.md\nordinary final line',
			'<details>\n- Changes: tasks/111/CHANGELOG.md\n</details>\n'
			'```\n- Changes: tasks/222/CHANGELOG.md\n```\n'
			'<!--\n- Changes: tasks/333/CHANGELOG.md\n-->\n'
			'    - Changes: tasks/444/CHANGELOG.md',
			'\t- Changes: tasks/444/CHANGELOG.md',
		):
			with self.subTest(body=body):
				self.check_output.reset_mock()
				self.check_output.side_effect = [
					dumps([[self.pull(body, 'task/12')]]).encode(),
					b'100644 blob abc\tfile\n',
					b'legacy notes',
				]
				self.assertEqual(self.run_collector(), b'legacy notes')
				self.assertEqual(self.check_output.call_args_list[1].args[0], ['git', 'ls-tree', 'test-head', '--', 'issues/task/12/CHANGELOG.md'])
		return

	def test_invalid_markers_do_not_fall_back(self) -> None:
		for body in (
			'- Changes: ../CHANGELOG.md',
			'- Changes: tasks/../CHANGELOG.md',
			'- Changes: tasks/123/OTHER.md',
			'- Changes:',
			'- Changes tasks/123/CHANGELOG.md',
			'- Changes=tasks/123/CHANGELOG.md',
			'- Notes:\n  - Changes: tasks/123/CHANGELOG.md',
			' - Changes: tasks/123/CHANGELOG.md',
			'   - Changes: tasks/123/CHANGELOG.md',
		):
			with self.subTest(body=body):
				self.check_output.reset_mock()
				self.check_output.side_effect = [dumps([[self.pull(body)]]).encode()]
				with self.assertRaises(ValueError):
					self.run_collector()
				self.assertEqual(self.check_output.call_count, 1)
		return

	def test_document_examples_before_footer_do_not_affect_path(self) -> None:
		body: str = (
			'<details>\n<summary>Document</summary>\n\n'
			'Inline `</details>`\n'
			'- Changes: tasks/111/CHANGELOG.md\n</details>\n\n'
			'```text\n- Changes: tasks/222/CHANGELOG.md\n```\n\n'
			'<!--\n- Changes: tasks/444/CHANGELOG.md\n-->\n\n'
			'    - Changes: tasks/555/CHANGELOG.md\n\n'
			'- Closes #12\n- Changes: tasks/123/CHANGELOG.md\n\n'
			'- Changes: tasks/333/CHANGELOG.md\n\n'
		)
		self.check_output.side_effect = [
			dumps([[self.pull(body)]]).encode(),
			b'100644 blob abc\tfile\n',
			b'notes',
		]
		self.assertEqual(self.run_collector(), b'notes')
		self.assertEqual(self.check_output.call_args_list[1].args[0][-1], 'tasks/333/CHANGELOG.md')
		return

	def test_missing_non_regular_or_empty_changelog_fails(self) -> None:
		for entry, contents in (
			(b'', None),
			(b'120000 blob abc\tfile\n', None),
			(b'100644 blob abc\tfile\n', b' \n'),
		):
			with self.subTest(entry=entry, contents=contents):
				self.check_output.reset_mock()
				results: list[bytes] = [dumps([[self.pull('- Changes: tasks/123/CHANGELOG.md')]]).encode(), entry]
				if contents is not None:
					results.append(contents)
				self.check_output.side_effect = results
				with self.assertRaises(ValueError):
					self.run_collector()
		return

	def test_direct_push_keeps_commit_based_notes(self) -> None:
		self.check_output.side_effect = [dumps([[]]).encode(), b'- Change (abc)\n']
		self.assertEqual(self.run_collector(), '## master 직접 push\n\n'.encode('utf-8') + b'- Change (abc)\n')
		self.assertEqual(self.check_output.call_args_list[1].args[0], ['git', 'log', '--reverse', '--format=- %s (%h)', 'test-before..test-head'])
		return

	def test_existing_release_notes_are_reused(self) -> None:
		self.check_output.side_effect = [
			dumps([[self.pull('- Changes: invalid')]]).encode(),
			dumps({'tag_name': 'v1', 'body': 'existing notes'}).encode(),
		]
		self.assertEqual(self.run_collector('false'), b'existing notes')
		return
