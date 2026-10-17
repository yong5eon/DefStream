from hashlib import sha256
from hmac import compare_digest
from html import escape
from importlib.resources import files
from json import (
	dumps,
	loads,
)
from logging import getLogger
from math import isfinite
from re import sub
from threading import BoundedSemaphore
from time import monotonic
from typing import (
	Callable,
	Optional,
	Protocol,
	TYPE_CHECKING,
)
from urllib.parse import urlsplit

from ...Broker.Connection import (
	Connection,
	Requestable,
	TaskSender,
)
from ...Broker.Errors import RemoteError
from ...Worker.Message import (
	message_body,
	request,
	send,
)
from ..Extension import Extension
from ..Response import Response
from .Specifications import Specifications

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'Console',
)

logger = getLogger(__name__)


class Producer(
	Connection,
	TaskSender,
	Protocol,
):
	pass


def json_response(
	status: str,
	value: dict,
) -> Response:
	return Response(
		status,
		dumps(
			value,
			ensure_ascii=False,
			allow_nan=False,
		).encode('utf-8'),
		'application/json; charset=utf-8',
		(
			(
				'X-Content-Type-Options',
				'nosniff',
			),
		),
	)


class Console(Extension):
	methods = (
		'GET',
		'HEAD',
		'POST',
	)

	def __init__(
		self,
		path: str,
		*,
		broker: Callable[[], Producer],
		token: Optional[str] = None,
		timeout: float = 5,
		title: str = 'PinkStream',
		description: Optional[str] = None,
	):
		super().__init__(path)
		if not callable(broker):
			raise TypeError('Console broker must be a factory creating a new producer connection')
		if token is not None and (not isinstance(
			token,
			str,
		) or len(token) < 16):
			raise ValueError('Console token must contain at least 16 characters')
		if isinstance(
			timeout,
			bool,
		) or not isfinite(timeout) or timeout <= 0:
			raise ValueError('Console RPC timeout must be finite and positive')
		self.broker = broker
		if not isinstance(
			title,
			str,
		) or not title:
			raise ValueError('Console title must be a nonempty string')
		if description is not None and not isinstance(
			description,
			str,
		):
			raise TypeError('Console description must be a string or None')
		self.title = title
		self.description = description
		self.token_digest = sha256(token.encode('utf-8')).digest() if token is not None else None
		self.timeout = timeout
		self.slots = BoundedSemaphore(4)

	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		page = files(__package__).joinpath('Console.html').read_bytes()
		values = {
			'title': escape(self.title),
			'description': escape(self.description) if self.description is not None else '',
		}
		page = sub(
			r'\{\{console_(title|description)\}\}',
			lambda match: values[match[1]],
			page.decode('utf-8'),
		).encode('utf-8')
		if self.token_digest is None:
			page = page.replace(
				b'data-auth-required="true"',
				b'data-auth-required="false"',
			)
		return Response(
			'200 OK',
			page,
			'text/html; charset=utf-8',
			(
				(
					'Content-Security-Policy',
					"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
				),
				(
					'X-Content-Type-Options',
					'nosniff',
				),
				(
					'Referrer-Policy',
					'no-referrer',
				),
			),
		)

	def handle(
		self,
		inspector: 'Inspector',
		environ: dict,
	) -> Response:
		method = environ['REQUEST_METHOD']
		if method in (
			'GET',
			'HEAD',
		) and environ.get('HTTP_ACCEPT') != 'application/json':
			return self(inspector)
		authorization = environ.get(
			'HTTP_AUTHORIZATION',
			'',
		)
		if self.token_digest is not None and (not authorization.startswith('Bearer ') or not compare_digest(
			sha256(authorization[7:].encode('utf-8')).digest(),
			self.token_digest,
		)):
			logger.warning('Inspector Console rejected an unauthorized request')
			return json_response(
				'401 Unauthorized',
				{'error': 'A valid Bearer token is required'},
			)
		origin = environ.get('HTTP_ORIGIN')
		if origin is not None:
			try:
				parsed = urlsplit(origin)
				valid_origin = parsed.scheme in (
					'http',
					'https',
				) and parsed.netloc == environ.get('HTTP_HOST')
			except ValueError:
				valid_origin = False
			if not valid_origin:
				logger.warning('Inspector Console rejected a cross-origin request')
				return json_response(
					'403 Forbidden',
					{'error': 'Cross-origin requests are not allowed'},
				)
		if not self.slots.acquire(blocking=False):
			return json_response(
				'429 Too Many Requests',
				{'error': 'Too many concurrent console requests'},
			)
		try:
			if method in (
				'GET',
				'HEAD',
			):
				return self.catalog(inspector)
			return self.execute(
				inspector,
				environ,
			)
		except Exception:
			logger.exception('Inspector Console request failed')
			return json_response(
				'500 Internal Server Error',
				{'error': 'Inspector console failed; consult the worker logs'},
			)
		finally:
			self.slots.release()

	def catalog(
		self,
		inspector: 'Inspector',
	) -> Response:
		producer = self.broker()
		try:
			if inspector.worker is not None and producer is inspector.worker.broker:
				raise ValueError('Console requires a separate producer, not the Worker connection')
			rpc = isinstance(
				producer,
				Requestable,
			)
			specifications = next(
				(
					extension for extension in inspector.exts.values()
					if isinstance(
						extension,
						Specifications,
					)
				),
				None,
			)
			if specifications is None:
				specifications = Specifications(self.path)
			document = specifications.document(inspector)
			return json_response(
				'200 OK',
				{
					'specification': document,
					'rpc': rpc,
					'timeout': self.timeout,
				},
			)
		finally:
			if inspector.worker is None or producer is not inspector.worker.broker:
				producer.close()

	def execute(
		self,
		inspector: 'Inspector',
		environ: dict,
	) -> Response:
		worker = inspector.worker
		if worker is None or not worker.running.is_set() or worker.stopping.is_set() or worker.finished.is_set():
			return json_response(
				'503 Service Unavailable',
				{'error': 'Worker is not running'},
			)
		if environ.get(
			'CONTENT_TYPE',
			'',
		).split(';')[0].strip().lower() != 'application/json':
			return json_response(
				'415 Unsupported Media Type',
				{'error': 'Use application/json'},
			)
		length = environ.get(
			'CONTENT_LENGTH',
			'',
		)
		if not length.isascii() or not length.isdecimal():
			return json_response(
				'411 Length Required',
				{'error': 'A Content-Length is required'},
			)
		size = int(length)
		if size > 65536:
			return json_response(
				'413 Payload Too Large',
				{'error': 'Console requests must not exceed 64 KiB'},
			)
		raw = environ['wsgi.input'].read(size)
		try:
			if len(raw) != size:
				raise ValueError('Incomplete request body')
			payload = loads(raw)
			if not isinstance(
				payload,
				dict,
			) or set(payload) != {
				'task',
				'mode',
				'body',
			}:
				raise ValueError('Expected task, mode and body fields')
			if payload['mode'] not in (
				'send',
				'request',
			):
				raise ValueError('Mode must be send or request')
			body = message_body(payload['body'])
			dumps(
				body,
				allow_nan=False,
			)
			task = next(
				(
					task for task in worker.tasks if task.__name__ == payload['task']
				),
				None,
			)
			if task is None:
				raise ValueError('Unknown registered task')
			if sum(task.__name__ == payload['task'] for task in worker.tasks) != 1:
				raise ValueError('Ambiguous registered task name')
		except (
			ValueError,
			TypeError,
			UnicodeDecodeError,
		) as error:
			logger.warning('Inspector Console rejected invalid input')
			return json_response(
				'400 Bad Request',
				{'error': str(error)},
			)
		started = monotonic()
		producer = self.broker()
		if producer is worker.broker:
			raise ValueError('Console requires a separate producer, not the Worker connection')
		try:
			if payload['mode'] == 'request' and not isinstance(
				producer,
				Requestable,
			):
				return json_response(
					'501 Not Implemented',
					{'error': 'This broker does not support RPC'},
				)
			producer.connect()
			try:
				if payload['mode'] == 'request':
					result = request(
						body,
						task=task,
						broker=producer,
						timeout=self.timeout,
					)
				else:
					result = send(
						body,
						task=task,
						broker=producer,
					)
			except TimeoutError:
				logger.warning('Inspector Console RPC timed out')
				return json_response(
					'504 Gateway Timeout',
					{'error': 'RPC timed out; delivered work is not cancelled'},
				)
			except RemoteError as error:
				logger.warning(
					'Inspector Console received a remote task error: %s',
					error.code,
				)
				return json_response(
					'502 Bad Gateway',
					{
						'error': str(error),
						'code': error.code,
					},
				)
			return json_response(
				'200 OK',
				{
					'mode': payload['mode'],
					'result': result,
					'elapsed': monotonic() - started,
				},
			)
		finally:
			producer.close()
