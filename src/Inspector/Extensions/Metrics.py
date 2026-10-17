from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import (
	Dict,
	Optional,
	TYPE_CHECKING,
)

from ..Extension import Extension
from ..Response import Response

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'Metrics',
)


@dataclass
class TaskMetrics:
	active: int = 0
	success: int = 0
	failure: int = 0
	duration: float = 0


def label(
	value: str,
) -> str:
	return value.replace(
		'\\',
		'\\\\',
	).replace(
		'\n',
		'\\n',
	).replace(
		'"',
		'\\"',
	)


class Metrics(Extension):
	def __init__(
		self,
		path: str,
	):
		super().__init__(path)
		self.lock = Lock()
		self.tasks: Dict[str, TaskMetrics] = {}
		self.started_at: Optional[float] = None

	def start(
		self,
		inspector: 'Inspector',
	) -> None:
		worker = inspector.worker
		if worker is None:
			raise RuntimeError('Metrics requires an attached Worker')
		with self.lock:
			self.started_at = monotonic()
			self.tasks = {
				task.__module__ + '.' + task.__qualname__: TaskMetrics()
				for task in worker.tasks
			}

	def begin(
		self,
		task: str,
	) -> float:
		with self.lock:
			self.tasks[task].active += 1
		return monotonic()

	def end(
		self,
		task: str,
		context: object,
		success: Optional[bool],
	) -> None:
		if not isinstance(
			context,
			float,
		):
			raise TypeError('Metrics completion requires its submission timestamp')
		with self.lock:
			stats = self.tasks[task]
			stats.active -= 1
			if success is not None:
				stats.success += int(success)
				stats.failure += int(not success)
				stats.duration += monotonic() - context

	def render(
		self,
		inspector: 'Inspector',
	) -> str:
		worker = inspector.worker
		running = worker is not None and worker.running.is_set() and not worker.stopping.is_set() and not worker.finished.is_set()
		uptime = 0 if self.started_at is None else monotonic() - self.started_at
		lines = [
			'# HELP pinkstream_worker_running Worker consumer lifecycle is running; not a heartbeat probe.',
			'# TYPE pinkstream_worker_running gauge',
			f'pinkstream_worker_running {int(running)}',
			'# HELP pinkstream_worker_uptime_seconds Seconds since Inspector startup.',
			'# TYPE pinkstream_worker_uptime_seconds gauge',
			f'pinkstream_worker_uptime_seconds {uptime}',
			'# HELP pinkstream_tasks_active Submitted task executions not yet completed.',
			'# TYPE pinkstream_tasks_active gauge',
			'# HELP pinkstream_tasks_total Completed execution attempts including retries.',
			'# TYPE pinkstream_tasks_total counter',
			'# HELP pinkstream_task_duration_seconds End-to-end execution time including pool wait and hooks.',
			'# TYPE pinkstream_task_duration_seconds summary',
		]
		with self.lock:
			for task, stats in self.tasks.items():
				labels = 'task="' + label(task) + '"'
				lines.extend((
					f'pinkstream_tasks_active{{{labels}}} {stats.active}',
					f'pinkstream_tasks_total{{{labels},outcome="success"}} {stats.success}',
					f'pinkstream_tasks_total{{{labels},outcome="failure"}} {stats.failure}',
					f'pinkstream_task_duration_seconds_count{{{labels}}} {stats.success + stats.failure}',
					f'pinkstream_task_duration_seconds_sum{{{labels}}} {stats.duration}',
				))
		return '\n'.join(lines) + '\n'

	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		return Response(
			'200 OK',
			self.render(inspector).encode('utf-8'),
			'text/plain; version=0.0.4; charset=utf-8',
		)
