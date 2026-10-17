from abc import (
	ABC,
	abstractmethod,
)
from typing import TYPE_CHECKING

from .Response import Response

if TYPE_CHECKING:
	from .Inspector import Inspector

__all__ = (
	'Extension',
)


class Extension(ABC):
	def __init__(
		self,
		path: str,
	):
		if not isinstance(
			path,
			str,
		) or not path.startswith('/') or '?' in path or '#' in path:
			raise ValueError('An absolute HTTP path without a query or fragment is required')
		self.path = path

	@abstractmethod
	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		raise NotImplementedError
