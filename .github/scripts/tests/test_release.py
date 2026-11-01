from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
from json import dumps
from os import (
	chdir as change_directory,
	environ,
	getcwd,
)
from pathlib import Path
from tarfile import (
	TarInfo,
	open as open_tar,
)
from tempfile import TemporaryDirectory
from typing import Iterator
from unittest import (
	TestCase,
	main,
)
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile

from build_distributions import (
	IMPLEMENTATIONS,
	PROJECT,
)
from prepare_upload import main as prepare


@contextmanager
def chdir(directory: str) -> Iterator[None]:
	original: str = getcwd()
	change_directory(directory)
	try:
		yield
	finally:
		change_directory(original)
	return


class ReleaseTests(TestCase):
	def create_distributions(self) -> None:
		Path('dist').mkdir()
		for project in (
			PROJECT,
			*(f'{PROJECT}-{target}' for target in IMPLEMENTATIONS),
		):
			name = project.lower().replace(
				'-',
				'_',
			)
			metadata = f'Metadata-Version: 2.4\nName: {project}\nVersion: 1.2.3\n\n'.encode()
			with ZipFile(
				f'dist/{name}-1.2.3-7-py3-none-any.whl',
				'w',
			) as archive:
				archive.writestr(
					f'{name}-1.2.3.dist-info/METADATA',
					metadata,
				)
			with open_tar(
				f'dist/{name}-1.2.3.tar.gz',
				'w:gz',
			) as archive:
				info = TarInfo(f'{name}-1.2.3/PKG-INFO')
				info.size = len(metadata)
				archive.addfile(
					info,
					BytesIO(metadata),
				)
		return

	def test_new_release_stages_implementations_separately_from_core(self) -> None:
		with TemporaryDirectory() as temporary, chdir(temporary), patch.dict(
			environ,
			{
				'RELEASE_VERSION': '1.2.3',
				'WHEEL_BUILD': '7',
				'NEW_VERSION': 'true',
				'GITHUB_OUTPUT': 'output.txt',
			},
		):
			self.create_distributions()
			with patch(
				'prepare_upload.urlopen',
				side_effect=HTTPError(
					'https://pypi.org',
					404,
					'missing',
					None,
					None,
				),
			):
				prepare()
			self.assertEqual(
				len(list(Path('upload/core').iterdir())),
				2,
			)
			self.assertEqual(
				len(list(Path('upload/implementations').iterdir())),
				2 * len(IMPLEMENTATIONS),
			)
			self.assertIn(
				'publish=true',
				Path('output.txt').read_text(encoding='utf-8'),
			)
		return

	def test_same_version_rebuild_requires_all_distributions_to_exist(self) -> None:
		with TemporaryDirectory() as temporary, chdir(temporary), patch.dict(
			environ,
			{
				'RELEASE_VERSION': '1.2.3',
				'WHEEL_BUILD': '7',
				'NEW_VERSION': 'false',
				'GITHUB_OUTPUT': 'output.txt',
			},
		):
			self.create_distributions()
			for source in Path('dist').glob('*.tar.gz'):
				source.unlink()
			with patch(
				'prepare_upload.urlopen',
				side_effect=HTTPError(
					'https://pypi.org',
					404,
					'missing',
					None,
					None,
				),
			), self.assertRaisesRegex(
				RuntimeError,
				'unpublished distribution',
			):
				prepare()
		return

	def test_invalid_build_number_is_rejected(self) -> None:
		with TemporaryDirectory() as temporary, chdir(temporary), patch.dict(
			environ,
			{
				'RELEASE_VERSION': '1.2.3',
				'WHEEL_BUILD': '8',
				'NEW_VERSION': 'true',
			},
		):
			self.create_distributions()
			with self.assertRaisesRegex(
				ValueError,
				'build tag',
			):
				prepare()
		return

	def test_missing_implementation_is_rejected(self) -> None:
		with TemporaryDirectory() as temporary, chdir(temporary), patch.dict(
			environ,
			{
				'RELEASE_VERSION': '1.2.3',
				'WHEEL_BUILD': '7',
				'NEW_VERSION': 'true',
			},
		):
			self.create_distributions()
			next(Path('dist').glob('*.whl')).unlink()
			with self.assertRaisesRegex(
				ValueError,
				'Missing core or implementation',
			):
				prepare()
		return

	def test_published_identical_artifacts_are_not_uploaded_again(self) -> None:
		with TemporaryDirectory() as temporary, chdir(temporary), patch.dict(
			environ,
			{
				'RELEASE_VERSION': '1.2.3',
				'WHEEL_BUILD': '7',
				'NEW_VERSION': 'true',
				'GITHUB_OUTPUT': 'output.txt',
			},
		):
			self.create_distributions()
			release = {
				'urls': [
					{
						'filename': path.name,
						'digests': {'sha256': sha256(path.read_bytes()).hexdigest()},
					}
					for path in Path('dist').iterdir()
				],
			}
			responses = [
				BytesIO(dumps(release).encode())
				for _ in range(len(IMPLEMENTATIONS) + 1)
			]
			with patch(
				'prepare_upload.urlopen',
				side_effect=responses,
			):
				prepare()
			self.assertIn(
				'publish=false',
				Path('output.txt').read_text(encoding='utf-8'),
			)
		return

	def test_published_different_artifacts_are_rejected(self) -> None:
		with TemporaryDirectory() as temporary, chdir(temporary), patch.dict(
			environ,
			{
				'RELEASE_VERSION': '1.2.3',
				'WHEEL_BUILD': '7',
				'NEW_VERSION': 'true',
				'GITHUB_OUTPUT': 'output.txt',
			},
		):
			self.create_distributions()
			release = {
				'urls': [
					{'filename': path.name, 'digests': {'sha256': 'wrong'}}
					for path in Path('dist').iterdir()
				],
			}
			with patch(
				'prepare_upload.urlopen',
				return_value=BytesIO(dumps(release).encode()),
			), self.assertRaisesRegex(
				RuntimeError,
				'Published file differs',
			):
				prepare()
		return


if __name__ == '__main__':
	main()
