from json import (
	dumps,
	loads,
)
from typing import (
	Any,
	Protocol,
)

__all__ = (
	'Encoder',
	'Decoder',
	'JavaScriptObjectNotationEncoder',
	'JavaScriptObjectNotationDecoder',
)


class Encoder(Protocol):
	def __call__(
		self,
		body: Any,
	) -> bytes: ...


class Decoder(Protocol):
	def __call__(
		self,
		body: bytes,
	) -> Any: ...


class JavaScriptObjectNotationEncoder(Encoder):
	def __call__(
		self,
		body: Any,
	) -> bytes:
		return dumps(
			body,
			ensure_ascii=False,
		).encode('utf-8')


class JavaScriptObjectNotationDecoder(Decoder):
	def __call__(
		self,
		body: bytes,
	) -> Any:
		return loads(body)
