from __future__ import annotations

from contextlib import contextmanager
from os import environ
from typing import (
	Generator,
	Optional,
	Union,
)

from setuptools import build_meta

from build_distributions import IMPLEMENTATIONS

ConfigSettings = Optional[dict[str, Union[str, list[str]]]]
EDITABLE_SELECTION = 'DEF_EDITABLE_EXTRAS'


def selected_extras(config_settings: ConfigSettings) -> list[str]:
	value: str | list[str] = (config_settings or {}).get('EXTRAS', '')
	values: list[str] = value if isinstance(value, list) else [value]
	known: dict[str, str] = {target.lower(): target for target in IMPLEMENTATIONS}
	selected: list[str] = []
	for item in values:
		if not item.strip():
			continue
		for part in item.split(','):
			key: str = part.strip().lower()
			if key not in known:
				raise ValueError('Unknown EXTRAS entry: {!r}; expected {}'.format(
					part,
					', '.join(IMPLEMENTATIONS),
				))
			target: str = known[key]
			if target not in selected:
				selected.append(target)
	return selected


@contextmanager
def editable_settings(config_settings: ConfigSettings) -> Generator[dict[str, str | list[str]], None, None]:
	"""Apply one editable selection consistently to every PEP 660 hook."""
	extras: list[str] = selected_extras(config_settings)
	previous: dict[str, Optional[str]] = {
		key: environ.get(key) for key in (
			EDITABLE_SELECTION,
			'DEF_BUILD_TARGET',
		)
	}
	environ[EDITABLE_SELECTION] = ','.join(extras)
	environ['DEF_BUILD_TARGET'] = 'core'
	try:
		yield {key: value for key, value in (config_settings or {}).items() if key != 'EXTRAS'}
	finally:
		for key, value in previous.items():
			if value is None:
				environ.pop(
					key,
					None,
				)
			else:
				environ[key] = value
	return


def regular_settings(config_settings: ConfigSettings) -> ConfigSettings:
	if config_settings is not None and 'EXTRAS' in config_settings:
		raise ValueError('EXTRAS is only supported by pip install -e; regular distributions use DEF_BUILD_TARGET')
	return config_settings


def get_requires_for_build_editable(config_settings: ConfigSettings = None) -> list[str]:
	with editable_settings(config_settings) as settings:
		return build_meta.get_requires_for_build_editable(settings)


def prepare_metadata_for_build_editable(
	metadata_directory: str,
	config_settings: ConfigSettings = None,
) -> str:
	with editable_settings(config_settings) as settings:
		return build_meta.prepare_metadata_for_build_editable(
			metadata_directory,
			settings,
		)


def build_editable(
	wheel_directory: str,
	config_settings: ConfigSettings = None,
	metadata_directory: Optional[str] = None,
) -> str:
	with editable_settings(config_settings) as settings:
		return build_meta.build_editable(
			wheel_directory,
			settings,
			metadata_directory,
		)


def get_requires_for_build_wheel(config_settings: ConfigSettings = None) -> list[str]:
	return build_meta.get_requires_for_build_wheel(regular_settings(config_settings))


def prepare_metadata_for_build_wheel(
	metadata_directory: str,
	config_settings: ConfigSettings = None,
) -> str:
	return build_meta.prepare_metadata_for_build_wheel(
		metadata_directory,
		regular_settings(config_settings),
	)


def build_wheel(
	wheel_directory: str,
	config_settings: ConfigSettings = None,
	metadata_directory: Optional[str] = None,
) -> str:
	return build_meta.build_wheel(
		wheel_directory,
		regular_settings(config_settings),
		metadata_directory,
	)


def get_requires_for_build_sdist(config_settings: ConfigSettings = None) -> list[str]:
	return build_meta.get_requires_for_build_sdist(regular_settings(config_settings))


def build_sdist(
	sdist_directory: str,
	config_settings: ConfigSettings = None,
) -> str:
	return build_meta.build_sdist(
		sdist_directory,
		regular_settings(config_settings),
	)
