# -*- coding: utf-8 -*-

from os import environ
from json import dumps
from pathlib import Path
from types import TracebackType
from typing import (
	Mapping,
	Optional,
)

from setuptools import (
	find_packages,
	setup,
)
from setuptools.command.build import build
from setuptools.command.editable_wheel import editable_wheel
from setuptools.command.egg_info import egg_info
from setuptools.command.sdist import sdist
from setuptools_scm import get_version
from wheel.wheelfile import WheelFile

PACKAGE = 'DefStream'
SOURCE = 'src'
IMPLEMENTATIONS = {
	'RabbitMQ': 'Broker.Implements.RabbitMQ',
	'Redis': 'Broker.Implements.Redis',
}
DEPENDENCIES = {
	'RabbitMQ': ['pika>=1.3.2'],
	'Redis': ['redis>=5.1.1'],
}
TARGET_FILE = Path('.distribution-target')
ARCHIVE_TARGET: Optional[str] = (
	TARGET_FILE.read_text(encoding='utf-8').strip()
	if TARGET_FILE.is_file() else None
)
TARGET: str = environ.get(
	'DEF_BUILD_TARGET',
	ARCHIVE_TARGET or 'core',
)
EDITABLE: bool = 'DEF_EDITABLE_EXTRAS' in environ
EXTRAS: list[str] = [
	target for target in environ.get('DEF_EDITABLE_EXTRAS', '').split(',') if target
]
if any(target not in IMPLEMENTATIONS for target in EXTRAS):
	raise ValueError('Unknown editable EXTRAS selection')
if TARGET not in (
	'core',
	*IMPLEMENTATIONS,
):
	raise ValueError('Unknown DEF_BUILD_TARGET: {!r}'.format(TARGET))
if ARCHIVE_TARGET is not None and TARGET != ARCHIVE_TARGET:
	raise ValueError('Cannot change the build target of a source distribution')

VERSION: str = get_version(
	dist_name=PACKAGE,
	tag_regex=r'^v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:(?:rc|\.post)[0-9]+)?)$',
)
NAME = PACKAGE if TARGET == 'core' else '{}-{}'.format(
	PACKAGE,
	TARGET,
)
PACKAGES = [PACKAGE] if TARGET == 'core' else []
PACKAGE_DIR = {PACKAGE: SOURCE} if TARGET == 'core' else {}

for package in find_packages(SOURCE):
	selected = (
		not any(
			(package == path or package.startswith(path + '.'))
			and target not in EXTRAS
			for target, path in IMPLEMENTATIONS.items()
		)
		if TARGET == 'core' else (
			package == IMPLEMENTATIONS[TARGET]
			or package.startswith(IMPLEMENTATIONS[TARGET] + '.')
		)
	)
	if not selected:
		continue
	qualified = '{}.{}'.format(
		PACKAGE,
		package,
	)
	PACKAGES.append(qualified)
	PACKAGE_DIR[qualified] = '{}/{}'.format(
		SOURCE,
		package.replace(
			'.',
			'/',
		),
	)


class TargetBuild(build):
	def initialize_options(self) -> None:
		super().initialize_options()
		self.build_base = 'build/{}'.format(TARGET)
		return


class TargetEggInfo(egg_info):
	def finalize_options(self) -> None:
		if self.egg_base is None:
			self.egg_base = 'build/{}'.format(TARGET)
		Path(self.egg_base).mkdir(
			parents=True,
			exist_ok=True,
		)
		super().finalize_options()
		return


class TargetSdist(sdist):
	def make_release_tree(
		self,
		base_dir: str,
		files: list[str],
	) -> None:
		super().make_release_tree(
			base_dir,
			files,
		)
		(Path(base_dir) / TARGET_FILE).write_text(
			TARGET + '\n',
			encoding='utf-8',
		)
		return


class EditableView:
	def __init__(
		self,
		name: str,
		build_lib: str,
	) -> None:
		self.name = name
		self.build_lib = Path(build_lib).resolve()
		return

	def __enter__(self) -> 'EditableView':
		return self

	def __exit__(
		self,
		exception_type: Optional[type[BaseException]],
		exception: Optional[BaseException],
		traceback: Optional[TracebackType],
	) -> None:
		return

	def __call__(
		self,
		wheel: WheelFile,
		files: list[str],
		mapping: Mapping[str, str],
	) -> None:
		sources: dict[str, str] = {
			Path(output).resolve().relative_to(self.build_lib).as_posix(): str(Path(source).resolve())
			for output, source in mapping.items()
		}
		for output in files:
			relative: str = Path(output).resolve().relative_to(self.build_lib).as_posix()
			if relative not in sources:
				raise ValueError('Editable output has no persistent source: {}'.format(output))
		helper: str = '__editable_{}'.format(NAME.lower().replace(
			'-',
			'_',
		))
		wheel.writestr(
			helper + '.py',
			Path('scripts/editable_view.py').read_bytes(),
		)
		wheel.writestr(
			self.name + '.dist-info/editable-files.json',
			dumps(sources),
		)
		wheel.writestr(
			self.name + '.dist-info/editable-selection.json',
			dumps(EXTRAS),
		)
		names: tuple[str, ...] = (
			PACKAGE,
			*('{}-{}'.format(
				PACKAGE,
				target,
			) for target in IMPLEMENTATIONS),
		)
		wheel.writestr(
			'__editable__.{}.pth'.format(self.name),
			'import {0}; {0}.activate({1!r}, {2!r})\n__editable_{3}_view\n'.format(
				helper,
				PACKAGE,
				names,
				PACKAGE.lower(),
			),
		)
		return


class TargetEditableWheel(editable_wheel):
	def finalize_options(self) -> None:
		super().finalize_options()
		mode = 'strict'
		if self.mode not in (
			None,
			mode,
		):
			raise ValueError('This build target requires {} editable mode'.format(mode))
		self.mode = mode
		return

	def _select_strategy(
		self,
		name: str,
		tag: str,
		build_lib: str,
	) -> EditableView:
		return EditableView(
			name,
			build_lib,
		)


setup(
	name=NAME,
	version=VERSION,
	description='Synchronous message processing with pluggable broker adapters',
	long_description=Path('README.setup.md').read_text(encoding='utf-8'),
	long_description_content_type='text/markdown',
	author='Heo Yongseon',
	url='https://github.com/yong5eon/DefStream',
	project_urls={
		'Source': 'https://github.com/yong5eon/DefStream',
		'Issues': 'https://github.com/yong5eon/DefStream/issues',
		'Releases': 'https://github.com/yong5eon/DefStream/releases',
	},
	cmdclass={
		'build': TargetBuild,
		'egg_info': TargetEggInfo,
		'sdist': TargetSdist,
		'editable_wheel': TargetEditableWheel,
	},
	packages=PACKAGES,
	package_dir=PACKAGE_DIR,
	include_package_data=False,
	package_data={
		'DefStream.Inspector.Extensions': [
			'Play.html',
			'Status.html',
		],
	} if TARGET == 'core' else {},
	classifiers=[
		'Programming Language :: Python :: 3.9',
		'Programming Language :: Python :: 3.10',
		'Programming Language :: Python :: 3.11',
		'Programming Language :: Python :: 3.12',
		'Programming Language :: Python :: 3.13',
		'Programming Language :: Python :: 3.14',
	],
	install_requires=[
		dependency for target in EXTRAS for dependency in DEPENDENCIES[target]
	] if EDITABLE else [] if TARGET == 'core' else [
		'{}=={}'.format(
			PACKAGE,
			VERSION,
		),
		*DEPENDENCIES[TARGET],
	],
	extras_require={
		target: DEPENDENCIES[target] for target in IMPLEMENTATIONS
	} if EDITABLE else {
		target: ['{}-{}=={}'.format(
			PACKAGE,
			target,
			VERSION,
		)]
		for target in IMPLEMENTATIONS
	} if TARGET == 'core' else {},
	python_requires='>=3.9',
)
