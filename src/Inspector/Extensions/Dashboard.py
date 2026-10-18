from html import escape
from importlib.resources import files
from json import dumps
from re import sub
from typing import (
	Optional,
	TYPE_CHECKING,
)

from ..Extension import Extension
from ..Response import Response
from .Metrics import Metrics

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'Dashboard',
)


class Dashboard(Extension):
	def __init__(
		self,
		path: str,
		*,
		title: str = 'DefStream',
		description: Optional[str] = None,
	):
		super().__init__(path)
		if not isinstance(
			title,
			str,
		) or not title:
			raise ValueError('Dashboard title must be a nonempty string')
		if description is not None and not isinstance(
			description,
			str,
		):
			raise TypeError('Dashboard description must be a string or None')
		self.title = title
		self.description = description
		self.metrics: Optional[Metrics] = None

	def start(
		self,
		inspector: 'Inspector',
	) -> None:
		metrics = [
			ext for ext in inspector.exts.values()
			if isinstance(
				ext,
				Metrics,
			)
		]
		if len(metrics) != 1:
			raise ValueError('Dashboard requires exactly one registered Metrics extension')
		self.metrics = metrics[0]

	def handle(
		self,
		inspector: 'Inspector',
		environ: dict,
	) -> Response:
		if environ.get('HTTP_ACCEPT') == 'application/json':
			if self.metrics is None:
				raise RuntimeError('Dashboard has not been started')
			return Response(
				'200 OK',
				dumps(
					self.metrics.snapshot(inspector),
					ensure_ascii=False,
					allow_nan=False,
				).encode('utf-8'),
				'application/json; charset=utf-8',
				((
					'X-Content-Type-Options',
					'nosniff',
				),),
			)
		return self(inspector)

	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		values = {
			'title': escape(self.title),
			'description': escape(self.description) if self.description is not None else '',
		}
		page = sub(
			r'\{\{dashboard_(title|description)\}\}',
			lambda match: values[match[1]],
			files(__package__).joinpath('Dashboard.html').read_text(encoding='utf-8'),
		)
		return Response(
			'200 OK',
			page.encode('utf-8'),
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
