from contextlib import redirect_stdout
from hashlib import sha256
from io import (
	BytesIO,
	StringIO,
)
from json import dumps
from os import environ
from pathlib import Path
from subprocess import check_output
from tarfile import (
	TarInfo,
	open as open_tar,
)
from tempfile import TemporaryDirectory
from unittest import (
	TestCase,
	main,
)
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile


WORKFLOW = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'ci.yml'


def workflow_script(name: str) -> str:
	lines = WORKFLOW.read_text(encoding='utf-8').splitlines()
	start = lines.index(f'      - name: {name}')
	start = lines.index("          python - <<'PY'", start) + 1
	end = lines.index('          PY', start)
	return '\n'.join(line[10:] for line in lines[start:end])


class ReleaseWorkflowTests(TestCase):
	def test_embedded_python_syntax(self) -> None:
		lines = WORKFLOW.read_text(encoding='utf-8').splitlines()
		for index, line in enumerate(lines):
			if line == "          python - <<'PY'":
				end = lines.index('          PY', index + 1)
				code = '\n'.join(line[10:] for line in lines[index + 1:end])
				compile(code, str(WORKFLOW), 'exec')
		return

	def plan(
		self,
		tags: str,
		changed: str = '',
		event: str = 'true',
	) -> dict:
		with TemporaryDirectory() as directory:
			output = Path(directory) / 'output'
			event_path = Path(directory) / 'event.json'
			event_path.write_text(dumps({'pull_request': {'base': {'sha': 'pr-base'}}}))
			environment = {
				'GITHUB_OUTPUT': str(output),
				'RELEASE_PUSH': event,
				'RELEASE_SERIES': '0.1',
				'BEFORE': 'before',
				'GITHUB_SHA': 'head',
				'GITHUB_RUN_NUMBER': '42',
				'GITHUB_EVENT_PATH': str(event_path),
			}
			with (
				patch.dict(environ, environment),
				patch('subprocess.check_output', side_effect=[tags, changed]) as git,
				redirect_stdout(StringIO()),
			):
				try:
					exec(workflow_script('Check complete push range and plan version'), {})
				except SystemExit as error:
					self.assertEqual(error.code, 0)
				self.commands = git.call_args_list
			return dict(line.split('=', 1) for line in output.read_text().splitlines())

	def test_code_and_packaging_changes_increase_patch(self) -> None:
		for path in ['src/__init__.py', 'src/Worker/__init__.py', 'setup.py', 'pyproject.toml']:
			with self.subTest(path=path):
				result = self.plan('0.1.4', path)
				self.assertEqual(result['version'], '0.1.5')
				self.assertEqual(result['new_version'], 'true')
				self.assertEqual(result['build'], '42')
		return

	def test_rebuild_keeps_public_version(self) -> None:
		result = self.plan('0.1.3.7\n0.1.4')
		self.assertEqual(result['version'], '0.1.4')
		self.assertEqual(result['new_version'], 'false')
		return

	def test_migrating_legacy_versions_increases_patch(self) -> None:
		for tag in ['0.1.4.12', 'v0.1.4.12', '0.1.4.post1', '0.1.4.0', '0.1.4.post0']:
			with self.subTest(tag=tag):
				result = self.plan(tag)
				self.assertEqual(result['version'], '0.1.5')
				self.assertEqual(result['new_version'], 'true')
		return

	def test_rebuild_preserves_existing_tag(self) -> None:
		self.assertEqual(self.plan('v0.1.4')['tag'], 'v0.1.4')
		return

	def test_source_comparison_includes_previously_failed_pushes(self) -> None:
		self.plan('0.1.4', 'setup.py')
		self.assertIn('0.1.4', self.commands[1].args[0])
		self.assertNotIn('before', self.commands[1].args[0])
		return

	def test_initial_release(self) -> None:
		self.assertEqual(self.plan('', 'src/__init__.py')['version'], '0.1.0')
		return

	def test_rebuild_without_release_history_is_rejected(self) -> None:
		with self.assertRaisesRegex(ValueError, 'No release tag'):
			self.plan('')
		return

	def test_pull_request_does_not_release(self) -> None:
		result = self.plan('0.1.4', event='false')
		self.assertEqual(result['release'], 'false')
		self.assertEqual(result['new_version'], 'false')
		self.assertEqual(result['tag'], '0.1.4')
		self.assertIn('pr-base', self.commands[0].args[0])
		return

	def test_git_pathspec_distinguishes_resources_and_packaging(self) -> None:
		with TemporaryDirectory() as directory:
			root = Path(directory)
			check_output(['git', 'init', '--quiet', str(root)])
			names = [
				'src/__init__.py',
				'src/nested/code.py',
				'src/nested/view.html',
				'setup.py',
				'setup.cfg',
				'pyproject.toml',
				'MANIFEST.in',
				'README.md',
				'.github/workflows/ci.yml',
			]
			for name in names:
				path = root / name
				path.parent.mkdir(parents=True, exist_ok=True)
				path.write_text('test\n')
			check_output(['git', '-C', str(root), 'add', '.'])
			check_output([
				'git', '-C', str(root),
				'-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
				'commit', '--quiet', '-m', 'test',
			])
			base = check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
			for name in names:
				(root / name).write_text('changed\n')
			self.plan('0.1.4')
			diff = self.commands[1].args[0]
			selected = check_output(
				['git', '-C', str(root), 'diff', '--name-only', base, '--', *diff[diff.index('--') + 1:]],
				text=True,
			).splitlines()
			self.assertEqual(set(selected), set(names[:2] + names[3:7]))
		return

	def test_direct_push_generates_notes(self) -> None:
		with TemporaryDirectory() as directory:
			output = Path(directory) / 'output'
			environment = {
				'GITHUB_OUTPUT': str(output),
				'GITHUB_SHA': 'head',
				'GITHUB_EVENT_NAME': 'push',
				'GITHUB_REPOSITORY': 'owner/project',
				'BEFORE': 'before',
				'RUNNER_TEMP': directory,
				'NEW_VERSION': 'true',
			}
			with (
				patch.dict(environ, environment),
				patch('subprocess.check_output', side_effect=[b'[[]]', b'- setup.py update (abc)\n']),
				redirect_stdout(StringIO()),
			):
				exec(workflow_script('Validate PR branch changelog'), {})
			self.assertEqual(output.read_text().strip(), 'branch=master')
			notes = (Path(directory) / 'release-notes' / 'README.md').read_text(encoding='utf-8')
			self.assertIn('setup.py update', notes)
		return

	def test_pr_still_requires_changelog(self) -> None:
		with TemporaryDirectory() as directory:
			event = Path(directory) / 'event.json'
			event.write_text(dumps({'pull_request': {'head': {'ref': 'fix/1'}}}))
			with (
				patch.dict(environ, {
					'GITHUB_EVENT_NAME': 'pull_request',
					'GITHUB_EVENT_PATH': str(event),
					'GITHUB_SHA': 'head',
					'NEW_VERSION': 'true',
				}),
				patch('subprocess.check_output', return_value=b''),
			):
				with self.assertRaisesRegex(ValueError, 'Changelog must exist'):
					exec(workflow_script('Validate PR branch changelog'), {})
		return

	def check_upload(
		self,
		published: dict,
		new_version: bool = False,
	) -> tuple:
		with TemporaryDirectory() as directory:
			root = Path(directory)
			dist = root / 'dist'
			dist.mkdir()
			wheel = dist / 'defstream-0.1.5-42-py3-none-any.whl'
			with ZipFile(wheel, 'w') as archive:
				archive.writestr('defstream-0.1.5.dist-info/METADATA', 'Name: DefStream\nVersion: 0.1.5\n')
			if new_version:
				(dist / 'defstream-0.1.5.tar.gz').write_bytes(b'sdist')
			wheel_hash = sha256(wheel.read_bytes()).hexdigest()
			files = {
				name: wheel_hash if digest == 'matching' else digest
				for name, digest in published.items()
			}
			response = StringIO(dumps({
				'urls': [
					{'filename': name, 'digests': {'sha256': digest}}
					for name, digest in files.items()
				],
			}))
			if not published:
				response.close()
				response = HTTPError('https://example.invalid', 404, 'not found', None, None)
			with (
				response,
				patch.dict(environ, {
					'PROJECT': 'DefStream',
					'RELEASE_VERSION': '0.1.5',
					'WHEEL_BUILD': '42',
					'NEW_VERSION': str(new_version).lower(),
					'GITHUB_OUTPUT': str(root / 'output'),
				}),
				patch('pathlib.Path', side_effect=lambda *args: root.joinpath(*args)),
				patch('urllib.request.urlopen', side_effect=[response]),
				redirect_stdout(StringIO()),
			):
				exec(workflow_script('Check release status'), {})
			result = dict(line.split('=', 1) for line in (root / 'output').read_text().splitlines())
			return result, {path.name for path in (root / 'upload').iterdir()}

	def test_new_release_uploads_wheel_and_sdist(self) -> None:
		result, files = self.check_upload({}, new_version=True)
		self.assertEqual(result['publish'], 'true')
		self.assertEqual(files, {
			'defstream-0.1.5-42-py3-none-any.whl',
			'defstream-0.1.5.tar.gz',
		})
		return

	def test_rebuild_only_uploads_new_wheel(self) -> None:
		result, files = self.check_upload({'defstream-0.1.5.tar.gz': 'old-sdist-hash'})
		self.assertEqual(result['publish'], 'true')
		self.assertEqual(files, {'defstream-0.1.5-42-py3-none-any.whl'})
		return

	def test_rerun_skips_identical_published_wheel(self) -> None:
		result, files = self.check_upload({'defstream-0.1.5-42-py3-none-any.whl': 'matching'})
		self.assertEqual(result['publish'], 'false')
		self.assertEqual(files, set())
		return

	def test_rerun_rejects_different_published_wheel(self) -> None:
		with self.assertRaisesRegex(RuntimeError, 'refusing to overwrite'):
			self.check_upload({'defstream-0.1.5-42-py3-none-any.whl': 'different'})
		return

	def test_rebuild_requires_existing_pypi_release(self) -> None:
		with self.assertRaisesRegex(RuntimeError, 'has not been published'):
			self.check_upload({})
		return

	def test_github_rebuild_preserves_original_notes(self) -> None:
		with TemporaryDirectory() as directory:
			root = Path(directory)
			notes = root / 'release-notes' / 'README.md'
			notes.parent.mkdir()
			notes.write_text('new build notes', encoding='utf-8')
			(root / 'dist').mkdir()
			(root / 'dist' / 'defstream-0.1.5-42-py3-none-any.whl').write_bytes(b'wheel')
			release = {'tag_name': '0.1.5', 'body': 'original release notes', 'assets': []}
			for attempt in range(2):
				with (
					patch.dict(environ, {
						'GITHUB_REPOSITORY': 'owner/project',
						'GITHUB_API_URL': 'https://api.github.com',
						'GITHUB_SERVER_URL': 'https://github.com',
						'GITHUB_SHA': 'source-commit',
						'GH_TOKEN': 'test-token',
						'VERSION': '0.1.5',
						'RELEASE_TAG': '0.1.5',
						'WHEEL_BUILD': '42',
						'NEW_VERSION': 'false',
					}),
					patch('pathlib.Path', side_effect=lambda *args: root.joinpath(*args)),
					patch('urllib.request.urlopen', return_value=StringIO(dumps(release))),
					patch('subprocess.run') as commands,
				):
					exec(workflow_script('Publish GitHub Release with verified distributions'), {})
				body = notes.read_text(encoding='utf-8')
				self.assertIn('original release notes', body)
				self.assertEqual(body, 'original release notes')
				self.assertTrue(all('--clobber' not in call.args[0] for call in commands.call_args_list))
				release['body'] = body
		return

	def test_rebuild_reuses_existing_notes_without_branch_changelog(self) -> None:
		for event_name in ['push', 'pull_request']:
			with self.subTest(event=event_name), TemporaryDirectory() as directory:
				root = Path(directory)
				event = root / 'event.json'
				event.write_text(dumps({'pull_request': {'head': {'ref': 'docs/1'}}}))
				body = '## 이전 변경로그\n\n기존 내용을 그대로 유지합니다.\n'
				release = {'tag_name': '0.1.4', 'body': body}
				responses = [dumps(release).encode('utf-8')]
				if event_name == 'push':
					responses.insert(0, b'[[]]')
				with (
					patch.dict(environ, {
						'GITHUB_EVENT_NAME': event_name,
						'GITHUB_EVENT_PATH': str(event),
						'GITHUB_SHA': 'head',
						'GITHUB_REPOSITORY': 'owner/project',
						'NEW_VERSION': 'false',
						'RELEASE_TAG': '0.1.4',
						'GITHUB_OUTPUT': str(root / 'output'),
						'RUNNER_TEMP': directory,
					}),
					patch('subprocess.check_output', side_effect=responses) as commands,
					redirect_stdout(StringIO()),
				):
					exec(workflow_script('Validate PR branch changelog'), {})
				self.assertEqual((root / 'release-notes' / 'README.md').read_bytes(), body.encode('utf-8'))
				self.assertTrue(all(call.args[0][0] == 'gh' for call in commands.call_args_list))
		return

	def test_rebuild_rejects_empty_existing_notes(self) -> None:
		with TemporaryDirectory() as directory:
			event = Path(directory) / 'event.json'
			event.write_text(dumps({'pull_request': {'head': {'ref': 'docs/1'}}}))
			with (
				patch.dict(environ, {
					'GITHUB_EVENT_NAME': 'pull_request',
					'GITHUB_EVENT_PATH': str(event),
					'GITHUB_SHA': 'head',
					'GITHUB_REPOSITORY': 'owner/project',
					'NEW_VERSION': 'false',
					'RELEASE_TAG': '0.1.4',
				}),
				patch('subprocess.check_output', return_value=b'{"tag_name":"0.1.4","body":""}'),
			):
				with self.assertRaisesRegex(ValueError, 'missing or empty'):
					exec(workflow_script('Validate PR branch changelog'), {})
		return

	def test_sdist_normalization_preserves_content_and_is_reproducible(self) -> None:
		with TemporaryDirectory() as directory:
			root = Path(directory)
			dist = root / 'dist'
			dist.mkdir()
			for number in range(2):
				with open_tar(dist / f'{number}.tar.gz', 'w:gz') as archive:
					member = TarInfo('defstream-0.1.5/src/__init__.py')
					member.mtime = 1700000000 + number
					member.size = 4
					member.pax_headers = {'mtime': str(member.mtime)}
					archive.addfile(member, BytesIO(b'code'))
			with (
				patch.dict(environ, {'SOURCE_DATE_EPOCH': '1700000000'}),
				patch('pathlib.Path', side_effect=lambda *args: root.joinpath(*args)),
			):
				exec(workflow_script('Normalize source archive timestamps'), {})
			self.assertEqual((dist / '0.tar.gz').read_bytes(), (dist / '1.tar.gz').read_bytes())
			with open_tar(dist / '0.tar.gz', 'r:gz') as archive:
				self.assertEqual(archive.extractfile(archive.getmembers()[0]).read(), b'code')
		return


if __name__ == '__main__':
	main()
