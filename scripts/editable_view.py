from errno import (
	EACCES,
	EAGAIN,
	EEXIST,
	ENOTEMPTY,
	EPERM,
)
from importlib.metadata import distributions
from json import (
	dumps,
	loads,
)
from os import (
	link,
	symlink,
)
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import (
	monotonic,
	sleep,
)
from typing import BinaryIO


def relative_path(
	value: str,
	project: str,
) -> Path:
	path: Path = Path(value)
	if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != project:
		raise ValueError('Invalid editable product path: {!r}'.format(value))
	return path


def collect_files(
	site: Path,
	project: str,
	names: tuple[str, ...],
) -> dict[str, str]:
	selected = {
		dist.metadata['Name']: dist
		for dist in distributions(path=[str(site)])
		if dist.metadata['Name'] in names
	}
	if project not in selected:
		raise RuntimeError('Editable {} requires its core distribution'.format(project))
	core = selected[project]
	if core.read_text('editable-selection.json') is not None:
		conflicts: list[str] = [name for name in selected if name != project]
		if conflicts:
			raise RuntimeError('Remove legacy implementation distributions before using EXTRAS editable selection: {}'.format(
				', '.join(conflicts),
			))
	if core.read_text('editable-files.json') is None:
		raise RuntimeError('Install the {} core with pip install -e . before its editable implementations'.format(project))
	files: dict[str, str] = {}
	for name, dist in selected.items():
		if dist.version != core.version:
			raise RuntimeError('Editable distribution version mismatch: {}'.format(name))
		manifest = dist.read_text('editable-files.json')
		if manifest is not None:
			mapping: dict[str, str] = loads(manifest)
		else:
			if dist.files is None:
				raise RuntimeError('Missing installed file record: {}'.format(name))
			mapping = {
				str(path).replace(
					'\\',
					'/',
				): str(Path(str(dist.locate_file(path))).resolve())
				for path in dist.files
				if path.parts[0] == project and '__pycache__' not in path.parts
			}
		for relative, source in mapping.items():
			relative_path(
				relative,
				project,
			)
			if relative in files:
				raise RuntimeError('Duplicate editable file ownership: {}'.format(relative))
			if not Path(source).is_absolute() or not Path(source).is_file():
				raise FileNotFoundError('Editable source is missing; reinstall its distribution: {}'.format(source))
			files[relative] = source
	return files


def create_link(
	source: Path,
	destination: Path,
) -> None:
	try:
		symlink(
			source,
			destination,
		)
	except OSError as error:
		if error.errno not in (
			EACCES,
			EPERM,
		) and getattr(
			error,
			'winerror',
			None,
		) != 1314:
			raise
		link(
			source,
			destination,
		)
	return


def write_state(
	state: Path,
	files: dict[str, str],
) -> None:
	temporary: Path = state.with_suffix('.new')
	temporary.write_text(
		dumps(
			files,
			sort_keys=True,
		),
		encoding='utf-8',
	)
	temporary.replace(state)
	return


def refresh(
	view: Path,
	project: str,
	files: dict[str, str],
) -> None:
	state: Path = view / 'files.json'
	previous: dict[str, str] = loads(state.read_text(encoding='utf-8')) if state.is_file() else {}
	if files == previous and all(
		(view / relative).is_file() and (view / relative).samefile(source)
		for relative, source in files.items()
	):
		return
	paths: dict[str, Path] = {}
	for relative in previous.keys() | files.keys():
		paths[relative] = view / relative_path(
			relative,
			project,
		)
	touched: set[Path] = set()
	directories: set[Path] = set()
	# Record ownership before adding links so interrupted refreshes remain recoverable.
	ownership: dict[str, str] = {
		**previous,
		**files,
	}
	if ownership != previous:
		write_state(
			state,
			ownership,
		)
	for relative, source in files.items():
		path: Path = paths[relative]
		if path.is_file() and path.samefile(source):
			continue
		path.parent.mkdir(
			parents=True,
			exist_ok=True,
		)
		with TemporaryDirectory(dir=path.parent) as staging:
			replacement: Path = Path(staging) / path.name
			create_link(
				Path(source),
				replacement,
			)
			replacement.replace(path)
		touched.add(path)
	for relative in previous.keys() - files.keys():
		path = paths[relative]
		if path.exists() or path.is_symlink():
			path.unlink()
		touched.add(path)
		directories.update(parent for parent in path.parents if parent != view and view in parent.parents)
	for path in touched:
		if path.suffix == '.py':
			cache: Path = path.parent / '__pycache__'
			if cache.is_dir():
				for bytecode in cache.glob(path.stem + '.*.pyc'):
					bytecode.unlink()
				directories.add(cache)
	for directory in sorted(
		directories,
		key=lambda path: len(path.parts),
		reverse=True,
	):
		if directory.exists():
			try:
				directory.rmdir()
			except OSError as error:
				if error.errno not in (
					ENOTEMPTY,
					EEXIST,
				):
					raise
	write_state(
		state,
		files,
	)
	return


def acquire_lock(
	stream: BinaryIO,
	path: Path,
) -> None:
	deadline: float = monotonic() + 30
	while True:
		try:
			if sys.platform == 'win32':
				from msvcrt import (
					LK_NBLCK,
					locking,
				)
				locking(
					stream.fileno(),
					LK_NBLCK,
					1,
				)
			else:
				from fcntl import (
					LOCK_EX,
					LOCK_NB,
					flock,
				)
				flock(
					stream.fileno(),
					LOCK_EX | LOCK_NB,
				)
			return
		except OSError as error:
			if error.errno not in (
				EACCES,
				EAGAIN,
			):
				raise
			if monotonic() >= deadline:
				raise TimeoutError('Editable view is locked: {}'.format(path)) from error
			sleep(0.05)


def activate(
	project: str,
	names: tuple[str, ...],
) -> None:
	"""Expose only installed files through a static, environment-local import root."""
	site: Path = Path(__file__).resolve().parent
	view: Path = site / ('__editable_{}_view'.format(project.lower()))
	lock: Path = view.with_suffix('.lock')
	with lock.open('a+b') as stream:
		if stream.tell() == 0:
			stream.write(b'\0')
			stream.flush()
		stream.seek(0)
		acquire_lock(
			stream,
			lock,
		)
		view.mkdir(exist_ok=True)
		refresh(
			view,
			project,
			collect_files(
				site,
				project,
				names,
			),
		)
	return
