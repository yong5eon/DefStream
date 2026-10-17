from abc import (
	ABC,
	abstractmethod,
)
from typing import (
	Optional,
	TYPE_CHECKING,
)

from .Response import Response

if TYPE_CHECKING:
	from .Inspector import Inspector

__all__ = (
	'Extension',
)


class Extension(ABC):
	methods = (
		'GET',
		'HEAD',
	)

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

	def start(
		self,
		inspector: 'Inspector',
	) -> None:
		pass

	def begin(
		self,
		task: str,
	) -> object:
		return None

	def end(
		self,
		task: str,
		context: object,
		success: Optional[bool],
	) -> None:
		pass

	def handle(
		self,
		inspector: 'Inspector',
		environ: dict,
	) -> Response:
		return self(inspector)

	@abstractmethod
	def __call__(
		self,
		inspector: 'Inspector',
	) -> Response:
		raise NotImplementedError
