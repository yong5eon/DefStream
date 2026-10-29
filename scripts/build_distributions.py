from argparse import ArgumentParser
from os import environ
from pathlib import Path
from subprocess import run
from sys import executable

PROJECT = 'DefStream'
IMPLEMENTATIONS = {
	'RabbitMQ': 'Broker.Implements.RabbitMQ',
	'Redis': 'Broker.Implements.Redis',
}
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
	from setuptools_scm import get_version

	parser = ArgumentParser(description='Build the core and implementation distributions.')
	parser.add_argument(
		'--outdir',
		default='dist',
	)
	parser.add_argument(
		'--wheel',
		action='store_true',
	)
	parser.add_argument(
		'--no-isolation',
		action='store_true',
	)
	options = parser.parse_args()
	environment: dict[str, str] = dict(environ)
	environment['SETUPTOOLS_SCM_PRETEND_VERSION'] = get_version(
		root=str(ROOT),
		dist_name=PROJECT,
		tag_regex=r'^v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:rc|\.post)[0-9]+)?)$',
	)
	for target in (
		'core',
		*IMPLEMENTATIONS,
	):
		environment['DEF_BUILD_TARGET'] = target
		command = [
			executable,
			'-m',
			'build',
			'--outdir',
			str(Path(options.outdir).resolve()),
		]
		if options.wheel:
			command.append('--wheel')
		if options.no_isolation:
			command.append('--no-isolation')
		run(
			command,
			cwd=ROOT,
			env=environment,
			check=True,
		)
	return


if __name__ == '__main__':
	main()
