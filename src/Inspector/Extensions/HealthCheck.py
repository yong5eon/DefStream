from json import dumps
from typing import TYPE_CHECKING

from ..Extension import Extension
from ..Response import Response

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'HealthCheck',
)


class HealthCheck(Extension):
	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		healthy = inspector.healthy()
		state = 'running' if healthy else inspector.state()
		if not healthy and state == 'running':
			state = 'unresponsive'
		return Response(
			'200 OK' if healthy else '503 Service Unavailable',
			dumps({
				'name': inspector.name,
				'status': state,
			}).encode('utf-8'),
			'application/json; charset=utf-8',
		)
