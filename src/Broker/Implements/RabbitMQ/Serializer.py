# -*- coding: utf-8 -*-

from abc import (
	ABCMeta,
	abstractmethod,
)

from json import (
	dumps,
	loads,
)
from typing import (
	Any,
	Optional,
)

__all__ = (
	'Encoder',
	'Decoder',
	'JavaScriptObjectNotationEncoder',
	'JavaScriptObjectNotationDecoder',
)

class Encoder(metaclass=ABCMeta):
	"""Encoder Interface"""
	@abstractmethod
	def __call__(self, obj: Any) -> bytes:
		raise NotImplementedError('{} must be implemented __call__'.format(self.__class__.__name__))

	@property
	@abstractmethod
	def format(self) -> str:
		raise NotImplementedError('{} must be implemented format'.format(self.__class__.__name__))	

	@property
	@abstractmethod
	def charset(self) -> str:
		raise NotImplementedError('{} must be implemented charset'.format(self.__class__.__name__))
	

class Decoder(metaclass=ABCMeta):
	"""Decoder Interface"""
	@abstractmethod
	def __call__(
		self,
		obj: bytes,
		format: Optional[str],
		charset: Optional[str],
	) -> Any:
		raise NotImplementedError('{} must be implemented __call__'.format(self.__class__.__name__))


class JavaScriptObjectNotationEncoder(Encoder):
	"""JavaScriptObjectNotation Encoder"""
	def __call__(self, obj: Any) -> bytes:
		return dumps(obj, ensure_ascii=False).encode(self.charset)

	@property
	def format(self) -> str: return 'application/json'

	@property
	def charset(self) -> str: return 'utf-8'


class JavaScriptObjectNotationDecoder(Decoder):
	"""JavaScriptObjectNotation Decoder"""
	def __call__(
		self,
		obj: bytes,
		format: Optional[str],
		charset: Optional[str],
	) -> Any:
		if format != 'application/json': raise ValueError('format is not support')
		if charset is None: raise ValueError('charset is required')
		return loads(obj.decode(charset))
