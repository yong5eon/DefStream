from importlib.metadata import (
	Distribution,
	PackageNotFoundError,
	distribution,
	requires,
)
from json import (
	dumps,
	loads,
)
from pathlib import Path
from subprocess import run
from sys import executable
from tempfile import TemporaryDirectory
from unittest import (
	TestCase,
	main,
)

from _support import require_value


def distribution_files(package: Distribution) -> set[str]:
	manifest = package.read_text('editable-files.json')
	if manifest is not None:
		mapping: dict[str, str] = loads(manifest)
		return set(mapping)
	return {
		str(path).replace(
			'\\',
			'/',
		)
		for path in require_value(package.files)
	}


class BrokerPackagingTests(TestCase):
	def test_distribution_contains_play_extension_and_template(self) -> None:
		package = distribution('DefStream')
		files: set[str] = distribution_files(package)
		for name in (
			'Play.py',
			'Play.html',
		):
			self.assertIn(
				'DefStream/Inspector/Extensions/' + name,
				files,
			)
		for name in (
			'Console.py',
			'Console.html',
		):
			self.assertNotIn(
				'DefStream/Inspector/Extensions/' + name,
				files,
			)
		return

	def test_brokers_are_owned_by_the_selected_distribution(self) -> None:
		package = distribution('DefStream')
		files: set[str] = distribution_files(package)
		selection = package.read_text('editable-selection.json')
		for broker in (
			'RabbitMQ',
			'Redis',
		):
			with self.subTest(broker=broker):
				owner_files: set[str] = (
					distribution_files(distribution('DefStream-' + broker))
					if selection is None else files
				)
				if selection is not None:
					with self.assertRaises(PackageNotFoundError):
						distribution('DefStream-' + broker)
				for module in (
					'__init__',
					'Configuration',
					'Connection',
					'Consumer',
					'Event',
					'Queue',
					'Serializer',
					'Subscription',
				):
					path = f'DefStream/Broker/Implements/{broker}/{module}.py'
					if selection is None:
						self.assertNotIn(path, files)
						self.assertIn(path, owner_files)
					else:
						self.assertEqual(
							path in files,
							broker in loads(selection),
						)
		return

	def test_dependencies_match_the_distribution_mode(self) -> None:
		dependencies = require_value(requires('DefStream'))
		selection = distribution('DefStream').read_text('editable-selection.json')
		if selection is not None:
			selected: list[str] = loads(selection)
			clients: dict[str, str] = {
				'RabbitMQ': 'pika>=1.3.2',
				'Redis': 'redis>=5.1.1',
			}
			self.assertCountEqual(
				dependencies,
				[
					*(clients[broker] for broker in selected),
					*(f'{client}; extra == "{broker.lower()}"' for broker, client in clients.items()),
				],
			)
			return
		self.assertEqual(
			len(dependencies),
			2,
		)
		version = distribution('DefStream').version
		for broker in (
			'RabbitMQ',
			'Redis',
		):
			self.assertTrue(any(
				requirement.startswith(f'DefStream-{broker}=={version};')
				and broker.lower() in requirement.lower()
				for requirement in dependencies
			))
			self.assertIn(
				f'DefStream=={version}',
				require_value(requires('DefStream-' + broker)),
			)
		self.assertIn(
			'pika>=1.3.2',
			require_value(requires('DefStream-RabbitMQ')),
		)
		self.assertIn(
			'redis>=5.1.1',
			require_value(requires('DefStream-Redis')),
		)
		return

	def test_imports_do_not_require_unselected_clients(self):
		for blocked, modules in (
			(
				['pika', 'redis'],
				['DefStream', 'DefStream.Broker', 'DefStream.Worker', 'DefStream.Inspector'],
			),
			(
				['redis'],
				['DefStream.Broker.Implements.RabbitMQ'],
			),
			(
				['pika'],
				['DefStream.Broker.Implements.Redis'],
			),
		):
			with self.subTest(blocked=blocked), TemporaryDirectory() as directory:
				code = '\n'.join((
					'from importlib import import_module',
					'from sys import modules',
					f'for name in {dumps(blocked)}:',
					'    modules[name] = None',
					f'for name in {dumps(modules)}:',
					'    import_module(name)',
				))
				result = run(
					[
						executable,
						'-I',
						'-c',
						code,
					],
					cwd=Path(directory),
					capture_output=True,
					text=True,
					timeout=30,
				)
				self.assertEqual(
					result.returncode,
					0,
					result.stderr,
				)
		return


if __name__ == '__main__':
	main()
