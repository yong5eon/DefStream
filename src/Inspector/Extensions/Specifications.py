from collections.abc import Mapping
from json import dumps
from logging import getLogger
from re import fullmatch
from typing import (
	TYPE_CHECKING,
	Optional,
)

from ..Extension import Extension
from ..Response import Response

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'Specifications',
)


def reference(
	*parts: str,
) -> dict:
	return {'$ref': '#/' + '/'.join(part.replace(
		'~',
		'~0',
	).replace(
		'/',
		'~1',
	) for part in parts)}


class Specifications(Extension):
	logger = getLogger('DefStream.Inspector.Extensions.Specifications')

	def __init__(
		self,
		path: str,
		version: str = '1.0.0',
		description: Optional[str] = None,
		format: str = 'application/json',
	):
		super().__init__(path)
		if not isinstance(
			version,
			str,
		) or not version:
			raise ValueError('A document version is required')
		self.version = version
		self.description = description
		if not isinstance(
			format,
			str,
		) or fullmatch(
			r"[!#$%&'+.^_`|~0-9A-Za-z-]+/[!#$%&'+.^_`|~0-9A-Za-z-]+(?:[ \t]*;[^\r\n]+)?",
			format,
		) is None:
			raise ValueError('Specifications format must be a concrete media type')
		self.format = format

	def document(
		self,
		inspector: 'Inspector',
	) -> dict:
		self.logger.debug('Building Specifications AsyncAPI document')
		worker = inspector.worker
		if worker is None:
			raise RuntimeError('Specifications requires an attached Worker')
		info = {
			'title': 'DefStream',
			'version': self.version,
		}
		if self.description is not None:
			info['description'] = self.description
		channels = {}
		operations = {}
		for task in worker.tasks:
			key = task.__name__
			if key in operations:
				raise ValueError('Duplicate task specification identifier: ' + key)
			parameters = task.parameters
			if isinstance(
				parameters,
				str,
			):
				queue = parameters
			elif isinstance(
				parameters,
				Mapping,
			):
				queue = parameters.get('queue')
			else:
				queue = getattr(
					parameters,
					'queue',
					None,
				)
			if not isinstance(
				queue,
				str,
			) or not queue:
				raise ValueError('Task specification requires a nonempty queue address: ' + key)
			if queue in channels:
				raise ValueError('Duplicate channel identifier: ' + queue)
			message = task.request.document() if task.request is not None else {
				'payload': {'type': 'object'},
			}
			message['name'] = task.__name__ + 'Request'
			channels[queue] = {
				'address': queue,
				'messages': {'request': message},
			}
			operation = {
				'action': 'receive',
				'channel': reference(
					'channels',
					queue,
				),
				'messages': [reference(
					'channels',
					queue,
					'messages',
					'request',
				)],
			}
			if task.request is not None and task.request.description is not None:
				operation['description'] = task.request.description
			if task.response is not None:
				channels[queue]['messages']['response'] = task.response.document()
				operation['reply'] = {
					'channel': reference(
						'channels',
						queue,
					),
					'messages': [reference(
						'channels',
						queue,
						'messages',
						'response',
					)],
				}
			operations[key] = operation
		document = {
			'asyncapi': '3.1.0',
			'info': info,
			'defaultContentType': self.format,
			'channels': channels,
			'operations': operations,
		}
		self.logger.debug(
			'Specifications AsyncAPI document built: tasks=%d channels=%d',
			len(operations),
			len(channels),
		)
		return document

	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		body = dumps(
			self.document(inspector),
			ensure_ascii=False,
			allow_nan=False,
			indent=2,
		).encode('utf-8')
		self.logger.debug(
			'Specifications HTTP response built: bytes=%d',
			len(body),
		)
		return Response(
			'200 OK',
			body,
			'application/json; charset=utf-8',
		)
