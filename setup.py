# -*- coding: utf-8 -*-

from pathlib import Path

from setuptools import (
	find_packages,
	setup,
)

PACKAGE = 'PinkStream'
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
	name='PinkStream',
	description='Synchronous message processing with broker adapters',
	long_description=Path('README.md').read_text(encoding='utf-8'),
	long_description_content_type='text/markdown',
	author='Heo Yongseon',
	version=Path('VERSION').read_text(encoding='utf-8').strip(),
	packages=PACKAGES,
	package_dir=PACKAGE_DIR,
	include_package_data=False,
	package_data={
		'PinkStream.Inspector.Extensions': [
			'Console.html',
			'Dashboard.html',
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
