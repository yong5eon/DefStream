from typing import TYPE_CHECKING

from ..Extension import Extension
from ..Response import Response

if TYPE_CHECKING:
	from ..Inspector import Inspector

__all__ = (
	'Metrics',
)


class Metrics(Extension):
	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		return Response(
			'200 OK',
			inspector.metrics().encode('utf-8'),
			'text/plain; version=0.0.4; charset=utf-8',
		)
