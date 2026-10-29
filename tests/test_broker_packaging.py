from importlib.metadata import (
	distribution,
	requires,
)
from json import dumps
from pathlib import Path
from subprocess import run
from sys import executable
from tempfile import TemporaryDirectory
from unittest import (
	TestCase,
	main,
)

from tests._support import require_value


class BrokerPackagingTests(TestCase):
	def test_distribution_contains_both_brokers(self):
		package = distribution('DefStream')
		files = {
			str(path).replace('\\', '/')
			for path in require_value(package.files)
		}
		for broker in (
			'RabbitMQ',
			'Redis',
		):
			with self.subTest(broker=broker):
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
					self.assertIn(
						f'DefStream/Broker/Implements/{broker}/{module}.py',
						files,
					)
		return

	def test_extras_depend_on_clients_not_adapter_distributions(self):
		dependencies = require_value(requires('DefStream'))
		self.assertEqual(
			len(dependencies),
			2,
		)
		self.assertTrue(any(
			requirement.startswith('pika>=1.3.2;') and 'rabbitmq' in requirement.lower()
			for requirement in dependencies
		))
		self.assertTrue(any(
			requirement.startswith('redis>=5.1.1;') and 'redis' in requirement.lower()
			for requirement in dependencies
		))
		self.assertFalse(any(
			'defstream-' in requirement.lower()
			for requirement in dependencies
		))
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
