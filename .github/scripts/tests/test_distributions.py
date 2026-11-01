from itertools import combinations
from json import loads
from pathlib import Path
from subprocess import (
	STDOUT,
	check_output,
)
from sys import executable
from tempfile import TemporaryDirectory
from unittest import (
	TestCase,
	main,
)
from zipfile import ZipFile

from build_distributions import (
	IMPLEMENTATIONS,
	PROJECT,
)
from check_distributions import local_requirements


class DistributionTests(TestCase):
	def test_pip_prefers_local_requirements_over_higher_build_candidates(self) -> None:
		with TemporaryDirectory(prefix='local wheels ') as temporary:
			directory: Path = Path(temporary)
			index: Path = directory / 'index'
			index.mkdir()
			wheels: dict[str, Path] = {}
			selected: tuple[str, ...] = tuple(IMPLEMENTATIONS)
			for name in (
				PROJECT,
				*(f'{PROJECT}-{target}' for target in selected),
			):
				normalized: str = name.lower().replace('-', '_')
				wheel: Path = directory / f'{normalized}-1.2.3-py3-none-any.whl'
				info: str = f'{normalized}-1.2.3.dist-info'
				with ZipFile(wheel, 'w') as archive:
					archive.writestr(
						info + '/METADATA',
						f'Metadata-Version: 2.1\nName: {name}\nVersion: 1.2.3\n'
						+ ''.join(f'Provides-Extra: {target}\n' for target in selected)
						+ '\n',
					)
					archive.writestr(
						info + '/WHEEL',
						'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
					)
					archive.writestr(info + '/RECORD', '')
				(index / f'{normalized}-1.2.3-99-py3-none-any.whl').write_bytes(wheel.read_bytes())
				wheels[name.lower()] = wheel
			report: Path = directory / 'report.json'
			command: list[str] = [
				executable,
				'-m',
				'pip',
				'install',
				'--dry-run',
				'--ignore-installed',
				'--no-deps',
				'--no-index',
				'--find-links',
				str(index),
				'--find-links',
				str(directory),
				'--report',
				str(report),
			]
			check_output(
				[*command, f'{PROJECT}==1.2.3'],
				stderr=STDOUT,
			)
			before = loads(report.read_text(encoding='utf-8'))
			self.assertIn('-99-', before['install'][0]['download_info']['url'])
			check_output(
				[*command, *local_requirements(wheels, selected)],
				stderr=STDOUT,
			)
			after = loads(report.read_text(encoding='utf-8'))
			self.assertEqual(
				{
					item['metadata']['name'].lower(): item['download_info']['url']
					for item in after['install']
				},
				{name: path.as_uri() for name, path in wheels.items()},
			)
		return

	def test_installation_requirements_pin_every_selected_project_wheel(self) -> None:
		with TemporaryDirectory(prefix='local wheels ') as temporary:
			directory: Path = Path(temporary)
			names: tuple[str, ...] = (
				PROJECT.lower(),
				*(f'{PROJECT}-{target}'.lower() for target in IMPLEMENTATIONS),
			)
			wheels: dict[str, Path] = {
				name: directory / (name.replace('-', '_') + '-1.2.3-py3-none-any.whl')
				for name in names
			}
			for count in range(len(IMPLEMENTATIONS) + 1):
				for selected in combinations(IMPLEMENTATIONS, count):
					with self.subTest(selected=selected):
						requirements: list[str] = local_requirements(wheels, selected)
						extras: str = '[' + ','.join(selected) + ']' if selected else ''
						self.assertEqual(
							requirements,
							[
								f'{PROJECT}{extras} @ {wheels[PROJECT.lower()].as_uri()}',
								*(str(wheels[f'{PROJECT}-{target}'.lower()]) for target in selected),
							],
						)
						self.assertNotIn(' ', requirements[0].split(' @ ')[1])
		return


if __name__ == '__main__':
	main()
