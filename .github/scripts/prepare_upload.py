from email.parser import BytesParser
from hashlib import sha256
from json import load
from os import environ
from pathlib import Path
from shutil import copy2
from tarfile import open as open_tar
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

from build_distributions import (
	IMPLEMENTATIONS,
	PROJECT,
)


def main() -> None:
	version = environ['RELEASE_VERSION']
	new_version = environ['NEW_VERSION'] == 'true'
	expected = {
		PROJECT,
		*(f'{PROJECT}-{target}' for target in IMPLEMENTATIONS),
	}
	distributions: dict[str, list[Path]] = {}
	for wheel in Path('dist').glob('*.whl'):
		if wheel.name.split('-')[2] != environ['WHEEL_BUILD']:
			raise ValueError('Wheel build tag does not match the release plan')
		with ZipFile(wheel) as archive:
			metadata_path, = (
				name for name in archive.namelist()
				if name.endswith('.dist-info/METADATA')
			)
			metadata = BytesParser().parsebytes(archive.read(metadata_path))
		name = metadata['Name']
		if name not in expected or name in distributions or metadata['Version'] != version:
			raise ValueError('Unexpected wheel name or version: {}'.format(wheel.name))
		distributions[name] = [wheel]
	if set(distributions) != expected:
		raise ValueError('Missing core or implementation wheels')
	source_names: set[str] = set()
	for source in Path('dist').glob('*.tar.gz'):
		with open_tar(
			source,
			'r:gz',
		) as archive:
			metadata_file, = (
				member for member in archive.getmembers()
				if member.name.count('/') == 1 and member.name.endswith('/PKG-INFO')
			)
			stream = archive.extractfile(metadata_file)
			if stream is None:
				raise ValueError('Missing source metadata: {}'.format(source.name))
			with stream:
				metadata = BytesParser().parse(stream)
		name = metadata['Name']
		if name not in expected or name in source_names or metadata['Version'] != version:
			raise ValueError('Unexpected source name or version: {}'.format(source.name))
		source_names.add(name)
		distributions[name].append(source)
	if source_names != (expected if new_version else set()):
		raise ValueError('Unexpected source distribution count for the release plan')
	upload = Path('upload')
	(upload / 'core').mkdir(parents=True)
	(upload / 'implementations').mkdir()
	for project, paths in distributions.items():
		try:
			with urlopen(
				f'https://pypi.org/pypi/{project}/{version}/json',
				timeout=30,
			) as response:
				release = load(response)
		except HTTPError as error:
			if error.code != 404:
				raise
			published = {}
		else:
			published = {file['filename']: file['digests']['sha256'] for file in release['urls']}
		if not new_version and not published:
			raise RuntimeError('Cannot rebuild an unpublished distribution: {}'.format(project))
		for path in paths:
			if path.name in published:
				if sha256(path.read_bytes()).hexdigest() != published[path.name]:
					raise RuntimeError('Published file differs: {}'.format(path.name))
				print('Already published: {}'.format(path.name))
			else:
				destination = upload / ('core' if project == PROJECT else 'implementations')
				copy2(
					path,
					destination / path.name,
				)
	with Path(environ['GITHUB_OUTPUT']).open(
		'a',
		encoding='utf-8',
	) as output:
		output.write('publish={}\nversion={}\n'.format(
			str(any(upload.glob('*/*'))).lower(),
			version,
		))
	return


if __name__ == '__main__':
	main()
