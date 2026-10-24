# -*- coding: utf-8 -*-

from pathlib import Path

from setuptools import (
	find_packages,
	setup,
)

PACKAGE = 'DefStream'
SOURCE = 'src'
PACKAGES = [PACKAGE]
PACKAGE_DIR = {PACKAGE: SOURCE}

for package in find_packages(SOURCE):
	PACKAGES.append('{}.{}'.format(PACKAGE, package))
	PACKAGE_DIR['{}.{}'.format(PACKAGE, package)] = '{}/{}'.format(
		SOURCE,
		package.replace('.', '/'),
	)

setup(
	name='DefStream',
	description='Synchronous message processing with pluggable broker adapters',
	long_description=Path('README.md').read_text(encoding='utf-8'),
	long_description_content_type='text/markdown',
	author='Heo Yongseon',
	url='https://github.com/yong5eon/DefStream',
	project_urls={
		'Source': 'https://github.com/yong5eon/DefStream',
		'Issues': 'https://github.com/yong5eon/DefStream/issues',
		'Releases': 'https://github.com/yong5eon/DefStream/releases',
	},
	use_scm_version={
		'tag_regex': r'^v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:rc|\.post)[0-9]+)?)$',
	},
	setup_requires=[
		'setuptools-scm>=8,<10',
	],
	packages=PACKAGES,
	package_dir=PACKAGE_DIR,
	include_package_data=False,
	package_data={
		'DefStream.Inspector.Extensions': [
			'Console.html',
			'Status.html',
		],
	},
	classifiers=[
		'Programming Language :: Python :: 3.9',
		'Programming Language :: Python :: 3.10',
		'Programming Language :: Python :: 3.11',
		'Programming Language :: Python :: 3.12',
		'Programming Language :: Python :: 3.13',
		'Programming Language :: Python :: 3.14',
	],
	extras_require={
		'RabbitMQ': [
			'pika>=1.3.2',
		],
		'Redis': [
			'redis>=5.1.1',
		],
	},
	python_requires='>=3.9',
)
