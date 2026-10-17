from dataclasses import dataclass
from logging import getLogger
from math import isfinite
from socketserver import ThreadingMixIn
from threading import (
	Event,
	Lock,
	Thread,
)
from time import monotonic
from typing import (
	Callable,
	Dict,
	Iterable,
	Optional,
	Sequence,
	TYPE_CHECKING,
)
from wsgiref.simple_server import (
	WSGIRequestHandler,
	WSGIServer,
	make_server,
)

from .Extension import Extension
from .Response import Response

if TYPE_CHECKING:
	from ..Worker.Worker import Worker

__all__ = (
	'Inspector',
)

logger = getLogger(__name__)


@dataclass
class TaskMetrics:
	active: int = 0
	success: int = 0
	failure: int = 0
	duration: float = 0


class Server(
	ThreadingMixIn,
	WSGIServer,
):
	daemon_threads = True
	block_on_close = False

	def get_request(self):
		connection, address = super().get_request()
		connection.settimeout(5)
		return connection, address


class RequestHandler(WSGIRequestHandler):
	def log_message(
		self,
		format: str,
		*args,
	) -> None:
		logger.info(
			'%s - %s',
			self.client_address[0],
			format % args,
		)


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


class Inspector:
	def __init__(
		self,
		host: str = '127.0.0.1',
		port: int = 9999,
		exts: Sequence[Extension] = (),
		name: str = 'PinkStream',
		timeout: float = 1,
	):
		if isinstance(
			port,
			bool,
		) or not isinstance(
			port,
			int,
		) or not 0 <= port <= 65535:
			raise ValueError('Inspector port must be between 0 and 65535')
		if isinstance(
			timeout,
			bool,
		) or not isfinite(timeout) or timeout <= 0:
			raise ValueError('Inspector probe timeout must be finite and positive')
		if not isinstance(
			name,
			str,
		) or not name:
			raise ValueError('Inspector name must be a nonempty string')
		self.host = host
		self.port = port
		self.name = name
		self.timeout = timeout
		self.exts: Dict[str, Extension] = {}
		for ext in exts:
			if not isinstance(
				ext,
				Extension,
			):
				raise TypeError('Inspector extensions must inherit Extension')
			if ext.path in self.exts:
				raise ValueError('Duplicate Inspector path: ' + ext.path)
			self.exts[ext.path] = ext
		self.worker: Optional['Worker'] = None
		self.server: Optional[WSGIServer] = None
		self.thread: Optional[Thread] = None
		self.started_at: Optional[float] = None
		self.lock = Lock()
		self.tasks: Dict[str, TaskMetrics] = {}
		self.probe: Optional[Event] = None

	def start(
		self,
		worker: 'Worker',
	) -> None:
		if self.worker is not None:
			raise RuntimeError('Inspector can only be attached and started once')
		self.worker = worker
		self.started_at = monotonic()
		with self.lock:
			for task in worker.tasks:
				self.tasks[task.__module__ + '.' + task.__qualname__] = TaskMetrics()
		server = make_server(
			self.host,
			self.port,
			self,
			server_class=Server,
			handler_class=RequestHandler,
		)
		self.server = server
		thread = Thread(
			target=self.serve,
			name=self.name + '-Inspector',
			daemon=True,
		)
		self.thread = thread
		try:
			thread.start()
		except BaseException:
			server.server_close()
			raise

	def serve(self) -> None:
		server = self.server
		if server is None:
			raise RuntimeError('Inspector server is not initialized')
		try:
			server.serve_forever(poll_interval=0.1)
		except Exception:
			logger.exception('Inspector HTTP server failed')
			if self.worker is not None:
				self.worker.stop()
			raise

	def stop(self) -> None:
		server = self.server
		thread = self.thread
		if server is not None:
			try:
				if thread is not None and thread.is_alive():
					server.shutdown()
					thread.join()
			finally:
				server.server_close()

	def state(self) -> str:
		worker = self.worker
		if worker is None:
			return 'starting'
		if worker.finished.is_set():
			return 'stopped'
		if worker.stopping.is_set():
			return 'stopping'
		if not worker.running.is_set():
			return 'starting'
		return 'running'

	def healthy(self) -> bool:
		worker = self.worker
		if worker is None or not worker.running.is_set() or worker.stopping.is_set() or worker.finished.is_set():
			return False
		consumer = worker.consumer
		if consumer is None:
			return False
		with self.lock:
			if self.probe is None or self.probe.is_set():
				self.probe = Event()
				try:
					consumer.call(self.probe.set)
				except Exception:
					self.probe = None
					logger.exception('Inspector could not schedule the consumer health probe')
					return False
			probe = self.probe
		return probe.wait(self.timeout) and worker.running.is_set() and not worker.stopping.is_set() and not worker.finished.is_set()

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
		started: float,
		success: Optional[bool],
	) -> None:
		with self.lock:
			stats = self.tasks[task]
			stats.active -= 1
			if success is not None:
				stats.success += int(success)
				stats.failure += int(not success)
				stats.duration += monotonic() - started

	def metrics(self) -> str:
		worker = self.worker
		running = worker is not None and worker.running.is_set() and not worker.stopping.is_set() and not worker.finished.is_set()
		name = 'name="' + label(self.name) + '"'
		uptime = 0 if self.started_at is None else monotonic() - self.started_at
		lines = [
			'# HELP pinkstream_worker_running Worker consumer lifecycle is running; not a heartbeat probe.',
			'# TYPE pinkstream_worker_running gauge',
			f'pinkstream_worker_running{{{name}}} {int(running)}',
			'# HELP pinkstream_worker_uptime_seconds Seconds since Inspector startup.',
			'# TYPE pinkstream_worker_uptime_seconds gauge',
			f'pinkstream_worker_uptime_seconds{{{name}}} {uptime}',
			'# HELP pinkstream_tasks_active Submitted task executions not yet completed.',
			'# TYPE pinkstream_tasks_active gauge',
			'# HELP pinkstream_tasks_total Completed execution attempts including retries.',
			'# TYPE pinkstream_tasks_total counter',
			'# HELP pinkstream_task_duration_seconds End-to-end execution time including pool wait and hooks.',
			'# TYPE pinkstream_task_duration_seconds summary',
		]
		with self.lock:
			for task, stats in self.tasks.items():
				labels = name + ',task="' + label(task) + '"'
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
		environ: dict,
		start_response: Callable,
	) -> Iterable[bytes]:
		method = environ['REQUEST_METHOD']
		environ['wsgi.multithread'] = True
		headers = []
		if method not in (
			'GET',
			'HEAD',
		):
			response = Response(
				'405 Method Not Allowed',
				b'Method not allowed\n',
				'text/plain; charset=utf-8',
			)
			headers.append((
				'Allow',
				'GET, HEAD',
			))
		else:
			ext = self.exts.get(environ['PATH_INFO'])
			response = ext(self) if ext is not None else Response(
				'404 Not Found',
				b'Not found\n',
				'text/plain; charset=utf-8',
			)
		headers.extend((
			(
				'Content-Type',
				response.content_type,
			),
			(
				'Content-Length',
				str(len(response.body)),
			),
			(
				'Cache-Control',
				'no-store',
			),
		))
		start_response(
			response.status,
			headers,
		)
		return [b'' if method == 'HEAD' else response.body]
