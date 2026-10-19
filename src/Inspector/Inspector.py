from logging import getLogger
from socketserver import ThreadingMixIn
from sys import exc_info
from threading import Thread
from time import monotonic
from traceback import extract_tb
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
	ServerHandler,
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


class Server(
	ThreadingMixIn,
	WSGIServer,
):
	logger = getLogger('DefStream.Inspector')

	daemon_threads = True
	block_on_close = False

	def get_request(self):
		connection, address = super().get_request()
		connection.settimeout(5)
		return connection, address

	def handle_error(
		self,
		request,
		client_address,
	) -> None:
		_, error, traceback = exc_info()
		self.logger.error(
			'HTTP connection handling failed: error_type=%s\n%s',
			type(error).__name__,
			''.join(
				f'  {frame.filename}:{frame.lineno} ({frame.name})\n'
				for frame in extract_tb(traceback)
			),
		)
		return


class InspectorServerHandler(ServerHandler):
	def log_exception(
		self,
		exc_info,
	) -> None:
		_, error, traceback = exc_info
		self.request_handler.logger.error(
			'WSGI request handling failed: error_type=%s\n%s',
			type(error).__name__,
			''.join(
				f'  {frame.filename}:{frame.lineno} ({frame.name})\n'
				for frame in extract_tb(traceback)
			),
		)
		return


class RequestHandler(WSGIRequestHandler):
	logger = getLogger('DefStream.Inspector')

	def handle(self) -> None:
		self.started_at = monotonic()
		self.path = ''
		self.raw_requestline = self.rfile.readline(65537)
		if len(self.raw_requestline) > 65536:
			self.requestline = ''
			self.request_version = ''
			self.command = ''
			self.send_error(414)
			return
		if not self.raw_requestline:
			self.close_connection = True
			return
		if not self.parse_request():
			return
		self.logger.debug(
			'HTTP request received: method=%s path=%s',
			self.command,
			self.path.partition('?')[0],
		)
		handler = InspectorServerHandler(
			self.rfile,
			self.wfile,
			self.get_stderr(),
			self.get_environ(),
			multithread=True,
		)
		handler.request_handler = self
		handler.run(self.server.get_app())

	def log_request(
		self,
		code='-',
		size='-',
	) -> None:
		self.logger.info(
			'HTTP response sent: method=%s path=%s status=%s bytes=%s duration=%s',
			self.command,
			self.path.partition('?')[0],
			code,
			size if size is not None else '-',
			monotonic() - self.started_at,
		)
		return

	def log_message(
		self,
		format: str,
		*args,
	) -> None:
		self.logger.warning('HTTP protocol error or request timeout')
		return


class Inspector:
	logger = getLogger('DefStream.Inspector')

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
			self.logger.debug(
				'Inspector extension registered: class=%s path=%s',
				type(ext).__name__,
				ext.path,
			)
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
			self.logger.debug(
				'Starting Inspector extension: class=%s path=%s',
				type(ext).__name__,
				ext.path,
			)
			try:
				ext.start(self)
			except Exception as error:
				self.logger.error(
					'Inspector extension startup failed: class=%s path=%s error=%s',
					type(ext).__name__,
					ext.path,
					type(error).__name__,
				)
				raise
		try:
			server = make_server(
				self.host,
				self.port,
				self,
				server_class=Server,
				handler_class=RequestHandler,
			)
		except Exception as error:
			self.logger.error(
				'Inspector HTTP server binding failed: error=%s',
				type(error).__name__,
			)
			raise
		self.server = server
		thread = Thread(
			target=self.serve,
			daemon=True,
		)
		self.thread = thread
		try:
			thread.start()
		except BaseException:
			self.logger.error('Inspector HTTP server thread startup failed')
			server.server_close()
			raise
		self.logger.info(
			'Inspector HTTP server started: host=%s port=%s',
			server.server_address[0],
			server.server_port,
		)

	def serve(self) -> None:
		server = self.server
		if server is None:
			raise RuntimeError('Inspector server is not initialized')
		try:
			server.serve_forever(poll_interval=0.1)
		except Exception as error:
			self.logger.error(
				'Inspector HTTP server failed: error=%s',
				type(error).__name__,
			)
			if self.worker is not None:
				self.worker.stop()
			raise

	def stop(self) -> None:
		server = self.server
		thread = self.thread
		if server is not None:
			try:
				if thread is not None and thread.is_alive():
					self.logger.info('Stopping Inspector HTTP server')
					server.shutdown()
					thread.join()
			finally:
				server.server_close()
				self.logger.info('Inspector HTTP server stopped')

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
		self.logger.debug(
			'Routing Inspector request: method=%s path=%s extension=%s',
			method,
			environ['PATH_INFO'],
			type(ext).__name__ if ext is not None else 'none',
		)
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
		self.logger.debug(
			'Inspector response built: status=%s bytes=%d',
			response.status,
			len(response.body),
		)
		start_response(
			response.status,
			headers,
		)
		return [b'' if method == 'HEAD' else response.body]
