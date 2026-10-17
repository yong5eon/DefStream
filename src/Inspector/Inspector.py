from logging import getLogger
from socketserver import ThreadingMixIn
from threading import Thread
from typing import (
	Callable,
	Dict,
	Iterable,
	Optional,
	Sequence,
	TYPE_CHECKING,
	Tuple,
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


class Inspector:
	def __init__(
		self,
		host: str = '127.0.0.1',
		port: int = 9999,
		exts: Sequence[Extension] = (),
	):
		if isinstance(
			port,
			bool,
		) or not isinstance(
			port,
			int,
		) or not 0 <= port <= 65535:
			raise ValueError('Inspector port must be between 0 and 65535')
		self.host = host
		self.port = port
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

	def start(
		self,
		worker: 'Worker',
	) -> None:
		if self.worker is not None:
			raise RuntimeError('Inspector can only be attached and started once')
		self.worker = worker
		for ext in self.exts.values():
			ext.start(self)
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

	def begin(
		self,
		task: str,
	) -> Tuple[Tuple[Extension, object], ...]:
		return tuple(
			(
				ext,
				ext.begin(task),
			)
			for ext in self.exts.values()
		)

	def end(
		self,
		task: str,
		contexts: Tuple[Tuple[Extension, object], ...],
		success: Optional[bool],
	) -> None:
		for ext, context in contexts:
			ext.end(
				task,
				context,
				success,
			)

	def __call__(
		self,
		environ: dict,
		start_response: Callable,
	) -> Iterable[bytes]:
		method = environ['REQUEST_METHOD']
		environ['wsgi.multithread'] = True
		headers = []
		ext = self.exts.get(environ['PATH_INFO'])
		methods = ext.methods if ext is not None else (
			'GET',
			'HEAD',
		)
		if method not in methods:
			response = Response(
				'405 Method Not Allowed',
				b'Method not allowed\n',
				'text/plain; charset=utf-8',
			)
			headers.append((
				'Allow',
				', '.join(methods),
			))
		else:
			response = ext.handle(
				self,
				environ,
			) if ext is not None else Response(
				'404 Not Found',
				b'Not found\n',
				'text/plain; charset=utf-8',
			)
		headers.extend(response.headers)
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
