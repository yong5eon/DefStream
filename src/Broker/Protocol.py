from typing import (
	Any,
	Generator,
	Optional,
	Protocol,
)

from .Event import Event

__all__ = (
	'Sendable',
	'Callable',
	'Poppable',
	'Readable',
)


class Sendable(Protocol):
	def send(
		self,
		body: Any,
	) -> Any: ...


class Callable(Protocol):
	def call(
		self,
		body: Any,
		timeout: float = 5,
	) -> Any: ...


class Poppable(Protocol):
	def pop(
		self,
		timeout: Optional[int] = None,
	) -> Optional[Event]: ...


class Readable(Protocol):
	def read(
		self,
		offset: int = 0,
		timeout: Optional[int] = None,
	) -> Generator[Event, None, None]: ...
