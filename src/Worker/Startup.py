from collections.abc import Mapping
from os import environ, getpid
import sys
from typing import (
	Any,
	TYPE_CHECKING,
)

if TYPE_CHECKING:
	from .Worker import Worker

__all__ = (
	'startup',
)


LOGO = r"""
▄▄▄▄▄▄           ▄▄  ▄▄▄▄▄▄▄                                  
███▀▀██▄        ██  █████▀▀▀  ██                              
███  ███ ▄█▀█▄ ▀██▀  ▀████▄  ▀██▀▀ ████▄ ▄█▀█▄  ▀▀█▄ ███▄███▄ 
███  ███ ██▄█▀  ██     ▀████  ██   ██ ▀▀ ██▄█▀ ▄█▀██ ██ ██ ██ 
██████▀  ▀█▄▄▄  ██  ███████▀  ██   ██    ▀█▄▄▄ ▀█▄██ ██ ██ ██ 

Just def. Let workers do the work. You don't need to await this.
"""


def supports_color() -> bool:
	return (
		getattr(sys.stdout, 'isatty', lambda: False)()
		and not environ.get('NO_COLOR')
	)


def colorize_logo(logo: str) -> str:
	colors = (
		'\033[38;5;39m',
		'\033[38;5;45m',
		'\033[38;5;51m',
		'\033[38;5;45m',
		'\033[38;5;39m',
	)
	reset = '\033[0m'
	colorized_lines = []
	art_line = 0
	for line in logo.splitlines(keepends=True):
		if line.strip() and art_line < len(colors):
			newline = '\n' if line.endswith('\n') else ''
			colorized_lines.append(
				f'{colors[art_line]}{line[:-1] if newline else line}'
				f'{reset}{newline}',
			)
			art_line += 1
		else:
			colorized_lines.append(line)
	return ''.join(colorized_lines)


def subscription_value(
	parameters: Any,
	name: str,
) -> Any:
	if isinstance(
		parameters,
		str,
	):
		return parameters if name == 'queue' else None
	if isinstance(
		parameters,
		Mapping,
	):
		return parameters.get(name)
	return getattr(
		parameters,
		name,
		None,
	)


def startup(worker: 'Worker') -> None:
	broker = type(worker.broker)
	broker_name = broker.__qualname__
	for base in broker.__mro__:
		if '.Broker.Implements.' in base.__module__:
			broker_name = base.__module__.split('.Broker.Implements.')[1].split('.')[0]
			break
	pool = type(worker.pool)
	conf = getattr(
		worker.broker,
		'conf',
		None,
	)
	host = getattr(
		conf,
		'host',
		None,
	)
	port = getattr(
		conf,
		'port',
		None,
	)
	if isinstance(
		host,
		str,
	):
		address = f'[{host}]' if ':' in host and not host.startswith('[') else host
		broker_name += f'://{address}'
		if isinstance(
			port,
			(
				str,
				int,
			),
		):
			broker_name += f':{port}'
		vhost = getattr(
			conf,
			'vhost',
			None,
		)
		if isinstance(
			vhost,
			str,
		) and vhost:
			broker_name += '/' + vhost.lstrip('/')
	logo = LOGO.rstrip()
	starting_worker = 'Starting Worker'
	if supports_color():
		logo = colorize_logo(logo)
		starting_worker = f'\033[1;38;5;51m{starting_worker}\033[0m'
	lines = [
		logo,
		'',
		starting_worker,
		f'  PID: {getpid()}',
		f'  Broker: {broker_name}',
	]
	lines.extend((
		f'  Pool: {pool.__name__} (concurrency={worker.pool.size()})',
		f'  Tasks: {len(worker.tasks)} tasks',
	))
	queues = []
	for task in worker.tasks:
		name = task.__qualname__
		queue = subscription_value(
			task.parameters,
			'queue',
		)
		lines.append(f'    - {name}')
		lines.append(f'      queue={queue!r}' if queue is not None else '      queue=<adapter-defined>')
		if queue is not None and queue not in queues:
			queues.append(queue)
		for option in (
			'group',
			'qos',
			'offset',
			'error',
		):
			value = subscription_value(
				task.parameters,
				option,
			)
			if value is not None:
				lines.append(f'      {option}={value!r}')
		policy = type(task.on_error).__name__ if task.on_error is not None else 'broker default'
		lines.append(f'      on_error={policy}')
	lines.append(f'  Queues: {len(queues)} queues')
	lines.extend(f'    - {queue!r}' for queue in queues)
	lines.append('\n')
	print(
		'\n'.join(lines),
		flush=True,
	)
