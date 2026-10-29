from argparse import ArgumentParser
from email.parser import BytesParser
from itertools import combinations
from os import environ
from pathlib import Path
from shutil import (
	copy2,
	copytree,
	ignore_patterns,
)
from subprocess import run
from sys import executable
from tempfile import TemporaryDirectory
from venv import EnvBuilder
from zipfile import ZipFile

from build_distributions import (
	IMPLEMENTATIONS,
	PROJECT,
	ROOT,
)


def check(
	command: list[str],
	directory: Path,
	environment: dict[str, str],
) -> None:
	result = run(
		command,
		cwd=directory,
		env=environment,
		capture_output=True,
		text=True,
	)
	if result.returncode:
		raise RuntimeError(
			'Command failed: {}\n{}\n{}'.format(
				command,
				result.stdout,
				result.stderr,
			)
		)
	return


def python_in(directory: Path) -> str:
	EnvBuilder(with_pip=True).create(directory)
	python = str(directory / ('Scripts/python.exe' if environ.get('OS') == 'Windows_NT' else 'bin/python'))
	check(
		[
			executable,
			'-m',
			'pip',
			'--python',
			python,
			'install',
			'pip>=23',
		],
		directory,
		dict(environ),
	)
	return python


def verify_install(
	python: str,
	directory: Path,
	environment: dict[str, str],
	selected: tuple[str, ...],
) -> None:
	code = (
		'from importlib import import_module\n'
		'from importlib.util import find_spec\n'
		'from importlib.metadata import distribution, PackageNotFoundError\n'
		'from json import loads\n'
		'from importlib.machinery import PathFinder\n'
		'from sys import path as search_path\n'
		f'import_module({PROJECT!r})\n'
		f'core = distribution({PROJECT!r})\n'
		'selection = core.read_text("editable-selection.json")\n'
		f'if selection is not None: assert set(loads(selection)) == set({selected!r})\n'
		f'for target, path in {IMPLEMENTATIONS!r}.items():\n'
		f'    selected = target in {selected!r}\n'
		f'    module = {PROJECT!r} + "." + path\n'
		'    assert (find_spec(module) is not None) == selected, module\n'
		'    parts = module.split(".")\n'
		'    locations = search_path\n'
		'    spec = None\n'
		'    for count in range(1, len(parts) + 1):\n'
		'        spec = PathFinder.find_spec(".".join(parts[:count]), locations)\n'
		'        if spec is None:\n'
		'            break\n'
		'        locations = spec.submodule_search_locations\n'
		'    assert (spec is not None) == selected, module\n'
		'    if selected:\n'
		'        import_module(module)\n'
		'    try:\n'
		f'        installed = distribution({PROJECT!r} + "-" + target)\n'
		'    except PackageNotFoundError:\n'
		'        assert selection is not None or not selected, target\n'
		'    else:\n'
		'        assert selection is None and selected, target\n'
	)
	check(
		[
			python,
			'-I',
			'-c',
			code,
		],
		directory,
		environment,
	)
	check(
		[
			python,
			'-m',
			'pip',
			'check',
		],
		directory,
		environment,
	)
	return


def main() -> None:
	parser = ArgumentParser(description='Verify distribution ownership, rebuilds and installation isolation.')
	parser.add_argument(
		'--dist-dir',
		default='dist',
	)
	parser.add_argument(
		'--editable',
		action='store_true',
	)
	options = parser.parse_args()
	dist = Path(options.dist_dir).resolve()
	environment: dict[str, str] = dict(environ)
	environment.pop(
		'DEF_BUILD_TARGET',
		None,
	)
	environment.pop(
		'SETUPTOOLS_SCM_PRETEND_VERSION',
		None,
	)
	wheels = sorted(dist.glob('*.whl'))
	expected = {
		PROJECT.lower(),
		*(f'{PROJECT}-{target}'.lower() for target in IMPLEMENTATIONS),
	}
	contents: dict[str, dict[str, bytes]] = {}
	version = ''
	owned: set[str] = set()
	for wheel in wheels:
		with ZipFile(wheel) as archive:
			metadata_path, = (
				name for name in archive.namelist()
				if name.endswith('.dist-info/METADATA')
			)
			metadata = BytesParser().parsebytes(archive.read(metadata_path))
			name = metadata['Name'].lower()
			assert name in expected and name not in contents, name
			if version:
				assert metadata['Version'] == version
			version = metadata['Version']
			payload = {
				path: archive.read(path)
				for path in archive.namelist()
				if path.startswith(PROJECT + '/')
			}
			assert payload, name
			assert not (owned & payload.keys()), name
			owned.update(payload)
			contents[name] = payload
			for target, path in IMPLEMENTATIONS.items():
				prefix = PROJECT + '/' + path.replace(
					'.',
					'/',
				) + '/'
				present = any(item.startswith(prefix) for item in payload)
				assert present == (name == f'{PROJECT}-{target}'.lower()), (
					name,
					target,
				)
	assert set(contents) == expected

	with TemporaryDirectory() as temporary:
		directory = Path(temporary)
		sources = sorted(dist.glob('*.tar.gz'))
		assert len(sources) in (
			0,
			len(expected),
		)
		for index, source in enumerate(sources):
			rebuilt = directory / f'rebuilt-{index}'
			check(
				[
					executable,
					'-m',
					'pip',
					'wheel',
					str(source),
					'--no-deps',
					'--no-build-isolation',
					'--no-cache-dir',
					'--wheel-dir',
					str(rebuilt),
				],
				directory,
				environment,
			)
			wheel, = rebuilt.glob('*.whl')
			with ZipFile(wheel) as archive:
				metadata_path, = (name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))
				metadata = BytesParser().parsebytes(archive.read(metadata_path))
				assert metadata['Version'] == version
				payload = {
					path: archive.read(path)
					for path in archive.namelist()
					if path.startswith(PROJECT + '/')
				}
				assert payload == contents[metadata['Name'].lower()]
		targets = tuple(IMPLEMENTATIONS)
		for count in range(len(targets) + 1):
			for selected in combinations(
				targets,
				count,
			):
				python = python_in(directory / ('installed-' + '-'.join(selected)))
				extras = '[' + ','.join(selected) + ']' if selected else ''
				check(
					[
						python,
						'-m',
						'pip',
						'install',
						'--find-links',
						str(dist),
						f'{PROJECT}{extras}=={version}',
					],
					directory,
					environment,
				)
				verify_install(
					python,
					directory,
					environment,
					selected,
				)
				if not selected:
					for target in targets:
						check(
							[
								python,
								'-m',
								'pip',
								'install',
								'--find-links',
								str(dist),
								f'{PROJECT}[{target}]=={version}',
							],
							directory,
							environment,
						)
					verify_install(
						python,
						directory,
						environment,
						targets,
					)
					check(
						[
							python,
							'-m',
							'pip',
							'install',
							'--force-reinstall',
							'--no-deps',
							*(str(wheel) for wheel in wheels),
						],
						directory,
						environment,
					)
					verify_install(
						python,
						directory,
						environment,
						targets,
					)
					check(
						[
							python,
							'-m',
							'pip',
							'uninstall',
							'-y',
							f'{PROJECT}-{targets[0]}',
						],
						directory,
						environment,
					)
					verify_install(
						python,
						directory,
						environment,
						targets[1:],
					)
		if options.editable:
			source = directory / 'source'
			source.mkdir()
			for filename in (
				'setup.py',
				'pyproject.toml',
				'README.setup.md',
				'LICENSE',
				'MANIFEST.in',
			):
				copy2(
					ROOT / filename,
					source / filename,
				)
			(source / 'scripts').mkdir()
			for filename in (
				'editable_view.py',
				'build_backend.py',
				'build_distributions.py',
			):
				copy2(
					ROOT / 'scripts' / filename,
					source / 'scripts' / filename,
				)
			copytree(
				ROOT / 'src',
				source / 'src',
				ignore=ignore_patterns('__pycache__'),
			)
			probe = source / 'src' / '_editable_probe.py'
			probe.write_text(
				'VALUE = 1\n',
				encoding='utf-8',
			)
			python = python_in(directory / 'editable')
			environment['SETUPTOOLS_SCM_PRETEND_VERSION'] = version
			for index, selected in enumerate((
				(),
				targets[:1],
				targets,
				targets[1:],
				(),
				targets,
			)):
				environment['DEF_BUILD_TARGET'] = targets[0]
				check(
					[
						python,
						'-m',
						'pip',
						'install',
						'--find-links',
						str(dist),
						'-e',
						str(source),
						*([
							'--config-settings',
							'EXTRAS=' + ','.join(selected),
						] if selected else []),
					],
					directory,
					environment,
				)
				verify_install(
					python,
					directory,
					environment,
					selected,
				)
				if index == 2:
					target = targets[0]
					module = source / 'src' / IMPLEMENTATIONS[target].replace(
						'.',
						'/',
					) / '__init__.py'
					with module.open(
						'a',
						encoding='utf-8',
					) as stream:
						stream.write('\nPACKAGING_EDITABLE_PROBE = 200\n')
					check(
						[
							python,
							'-I',
							'-c',
							f'from {PROJECT}.{IMPLEMENTATIONS[target]} import PACKAGING_EDITABLE_PROBE; assert PACKAGING_EDITABLE_PROBE == 200',
						],
						directory,
						environment,
					)
			probe.write_text(
				'VALUE = 200\n',
				encoding='utf-8',
			)
			check(
				[
					python,
					'-I',
					'-c',
					f'from {PROJECT}._editable_probe import VALUE; assert VALUE == 200',
				],
				directory,
				environment,
			)
			added = source / 'src' / '_new_editable_probe.py'
			added.write_text(
				'VALUE = 1\n',
				encoding='utf-8',
			)
			check(
				[
					python,
					'-I',
					'-c',
					f'from importlib.util import find_spec; assert find_spec("{PROJECT}._new_editable_probe") is None',
				],
				directory,
				environment,
			)
			check(
				[
					python,
					'-m',
					'pip',
					'install',
					'-e',
					str(source),
					'--config-settings',
					'EXTRAS=' + ','.join(targets),
				],
				directory,
				environment,
			)
			check(
				[
					python,
					'-I',
					'-c',
					f'from {PROJECT}._new_editable_probe import VALUE; assert VALUE == 1',
				],
				directory,
				environment,
			)
			verify_install(
				python,
				directory,
				environment,
				targets,
			)
			for invalid in (
				'unknown',
				targets[0] + ',',
			):
				rejected = run(
					[
						python,
						'-m',
						'pip',
						'install',
						'-e',
						str(source),
						'--config-settings',
						'EXTRAS=' + invalid,
					],
					cwd=directory,
					env=environment,
					capture_output=True,
					text=True,
				)
				assert rejected.returncode != 0, rejected.stdout
				assert 'Unknown EXTRAS entry' in rejected.stdout + rejected.stderr
			verify_install(
				python,
				directory,
				environment,
				targets,
			)
			next_version = '9999.0.0' if version != '9999.0.0' else '9999.0.1'
			environment['SETUPTOOLS_SCM_PRETEND_VERSION'] = next_version
			check(
				[
					python,
					'-m',
					'pip',
					'install',
					'-e',
					str(source),
					'--config-settings',
					'EXTRAS=' + ','.join(targets),
				],
				directory,
				environment,
			)
			check(
				[
					python,
					'-I',
					'-c',
					f'from importlib.metadata import version; assert version({PROJECT!r}) == {next_version!r}',
				],
				directory,
				environment,
			)
			verify_install(
				python,
				directory,
				environment,
				targets,
			)
			other = python_in(directory / 'other-editable')
			check(
				[
					other,
					'-m',
					'pip',
					'install',
					'-e',
					str(source),
				],
				directory,
				environment,
			)
			verify_install(
				other,
				directory,
				environment,
				(),
			)
			check(
				[
					other,
					'-m',
					'pip',
					'install',
					'--find-links',
					str(dist),
					'-e',
					str(source),
					'--config-settings',
					'EXTRAS=' + targets[0],
				],
				directory,
				environment,
			)
			verify_install(
				other,
				directory,
				environment,
				targets[:1],
			)
			verify_install(
				python,
				directory,
				environment,
				targets,
			)
	print(f'{PROJECT}: ownership, sdist rebuilds, four install combinations and lifecycle checks passed')
	return


if __name__ == '__main__':
	main()
