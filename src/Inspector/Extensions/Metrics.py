from dataclasses import (
	dataclass,
	field,
)
from logging import getLogger
from math import floor
from threading import Lock
from time import monotonic
from typing import (
	Dict,
	Optional,
	TypedDict,
	TYPE_CHECKING,
)
from uuid import uuid4

from ..Extension import Extension
from ..Response import Response

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'Metrics',
)


class WindowSnapshot(TypedDict):
	success: int
	failure: int
	duration: float
	max_duration: float


class TaskSnapshot(TypedDict):
	active: int
	success: int
	failure: int
	duration: float
	oldest_active: float
	windows: Dict[str, WindowSnapshot]


class MetricsSnapshot(TypedDict):
	instance: str
	sampled_at: float
	uptime: float
	running: bool
	tasks: Dict[str, TaskSnapshot]
	window_end: int


@dataclass
class TaskMetrics:
	active: int = 0
	success: int = 0
	failure: int = 0
	duration: float = 0
	starts: Dict[float, int] = field(default_factory=dict)
	buckets: Dict[int, WindowSnapshot] = field(default_factory=dict)

	def prune(
		self,
		now: float,
	) -> None:
		for second in tuple(self.buckets):
			if second < floor(now) - 60:
				del self.buckets[second]

	def window(
		self,
		end: int,
		seconds: int,
	) -> WindowSnapshot:
		buckets = [
			bucket for second, bucket in self.buckets.items()
			if end - seconds <= second < end
		]
		return {
			'success': sum(bucket['success'] for bucket in buckets),
			'failure': sum(bucket['failure'] for bucket in buckets),
			'duration': sum(bucket['duration'] for bucket in buckets),
			'max_duration': max(
				(bucket['max_duration'] for bucket in buckets),
				default=0,
			),
		}


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
	logger = getLogger('Worker.Inspector.Extensions.Metrics')

	def __init__(
		self,
		path: str,
	):
		super().__init__(path)
		self.lock = Lock()
		self.tasks: Dict[str, TaskMetrics] = {}
		self.started_at: Optional[float] = None
		self.instance = ''

	def start(
		self,
		inspector: 'Inspector',
	) -> None:
		worker = inspector.worker
		if worker is None:
			raise RuntimeError('Metrics requires an attached Worker')
		tasks = {}
		for task in worker.tasks:
			if task.name in tasks:
				raise ValueError('Duplicate Metrics task name: ' + task.name)
			tasks[task.name] = TaskMetrics()
		with self.lock:
			self.started_at = monotonic()
			self.instance = uuid4().hex
			self.tasks = tasks
		self.logger.info(
			'Metrics collection initialized: path=%s tasks=%d',
			self.path,
			len(self.tasks),
		)

	def begin(
		self,
		task: str,
	) -> float:
		with self.lock:
			started = monotonic()
			stats = self.tasks[task]
			stats.active += 1
			stats.starts[started] = stats.starts.get(
				started,
				0,
			) + 1
			self.logger.debug(
				'Metrics task observation started: task=%s',
				task,
			)
			return started

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
			now = monotonic()
			stats.starts[context] -= 1
			if stats.starts[context] == 0:
				del stats.starts[context]
			stats.active -= 1
			stats.prune(now)
			if success is not None:
				stats.success += int(success)
				stats.failure += int(not success)
				duration = now - context
				stats.duration += duration
				bucket = stats.buckets.setdefault(
					floor(now),
					{
						'success': 0,
						'failure': 0,
						'duration': 0,
						'max_duration': 0,
					},
				)
				bucket['success'] += int(success)
				bucket['failure'] += int(not success)
				bucket['duration'] += duration
				bucket['max_duration'] = max(
					bucket['max_duration'],
					duration,
				)
			else:
				duration = now - context
			self.logger.debug(
				'Metrics task observation completed: task=%s success=%s duration=%.6f active=%d',
				task,
				success,
				duration,
				stats.active,
			)

	def snapshot(
		self,
		inspector: 'Inspector',
	) -> MetricsSnapshot:
		worker = inspector.worker
		with self.lock:
			if self.started_at is None:
				raise RuntimeError('Metrics has not been started')
			sampled_at = monotonic()
			for stats in self.tasks.values():
				stats.prune(sampled_at)
			return {
				'instance': self.instance,
				'sampled_at': sampled_at,
				'uptime': sampled_at - self.started_at,
				'running': worker is not None and worker.running.is_set() and not worker.stopping.is_set() and not worker.finished.is_set(),
				'window_end': floor(sampled_at),
				'tasks': {
					task: {
						'active': stats.active,
						'success': stats.success,
						'failure': stats.failure,
						'duration': stats.duration,
						'oldest_active': sampled_at - min(stats.starts) if stats.starts else 0,
						'windows': {
							str(seconds): stats.window(
								floor(sampled_at),
								seconds,
							)
							for seconds in (
								1,
								60,
							)
						},
					}
					for task, stats in self.tasks.items()
				},
			}
		self.logger.debug(
			'Metrics snapshot built: tasks=%d running=%s',
			len(snapshot['tasks']),
			snapshot['running'],
		)
		return snapshot

	def render(
		self,
		inspector: 'Inspector',
	) -> str:
		self.logger.debug('Rendering Metrics in Prometheus format')
		snapshot = self.snapshot(inspector)
		running = snapshot['running']
		uptime = snapshot['uptime']
		lines = [
			'# HELP defstream_worker_running Worker consumer lifecycle is running; not a heartbeat probe.',
			'# TYPE defstream_worker_running gauge',
			f'defstream_worker_running {int(running)}',
			'# HELP defstream_worker_uptime_seconds Seconds since Inspector startup.',
			'# TYPE defstream_worker_uptime_seconds gauge',
			f'defstream_worker_uptime_seconds {uptime}',
			'# HELP defstream_tasks_active Submitted task executions not yet completed.',
			'# TYPE defstream_tasks_active gauge',
			'# HELP defstream_tasks_total Completed execution attempts including retries.',
			'# TYPE defstream_tasks_total counter',
			'# HELP defstream_task_duration_seconds End-to-end execution time including pool wait and hooks.',
			'# TYPE defstream_task_duration_seconds summary',
			'# HELP defstream_task_oldest_active_seconds Age of oldest submitted unfinished attempt including pool wait.',
			'# TYPE defstream_task_oldest_active_seconds gauge',
			'# HELP defstream_tasks_window Completed attempts in the last fully elapsed second or minute window.',
			'# TYPE defstream_tasks_window gauge',
			'# HELP defstream_task_window_duration_seconds_sum Total duration of attempts completed in the window.',
			'# TYPE defstream_task_window_duration_seconds_sum gauge',
			'# HELP defstream_task_window_duration_seconds_max Maximum duration of attempts completed in the window.',
			'# TYPE defstream_task_window_duration_seconds_max gauge',
		]
		for task, stats in snapshot['tasks'].items():
			labels = 'task="' + label(task) + '"'
			lines.extend((
				f'defstream_tasks_active{{{labels}}} {stats["active"]}',
				f'defstream_tasks_total{{{labels},outcome="success"}} {stats["success"]}',
				f'defstream_tasks_total{{{labels},outcome="failure"}} {stats["failure"]}',
				f'defstream_task_duration_seconds_count{{{labels}}} {stats["success"] + stats["failure"]}',
				f'defstream_task_duration_seconds_sum{{{labels}}} {stats["duration"]}',
				f'defstream_task_oldest_active_seconds{{{labels}}} {stats["oldest_active"]}',
			))
			for seconds, window in stats['windows'].items():
				window_labels = labels + ',window_seconds="' + seconds + '"'
				lines.extend((
					f'defstream_tasks_window{{{window_labels},outcome="success"}} {window["success"]}',
					f'defstream_tasks_window{{{window_labels},outcome="failure"}} {window["failure"]}',
					f'defstream_task_window_duration_seconds_sum{{{window_labels}}} {window["duration"]}',
					f'defstream_task_window_duration_seconds_max{{{window_labels}}} {window["max_duration"]}',
				))
		return '\n'.join(lines) + '\n'

	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		body = self.render(inspector).encode('utf-8')
		self.logger.debug(
			'Metrics HTTP response built: bytes=%d',
			len(body),
		)
		return Response(
			'200 OK',
			body,
			'text/plain; version=0.0.4; charset=utf-8',
		)
