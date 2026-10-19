# -*- coding: utf-8 -*-

from collections.abc import Mapping

from enum import Enum
from typing import (
	Any,
	Iterator,
	KeysView,
	ItemsView,
	ValuesView,
	Optional,
	Dict,
	Union,
	Iterable,
	Tuple,
)
from abc import (
	ABCMeta,
	ABC,
)

__all__ = (
	'Type',
	'Value',
	'Condition',
	'Schema',
	'OneOf',
	'AllOf',
	'TypeMapper',
	'TypeEncoder',
)


class Descriptor(Mapping[str, Any]):
	def __init__(
		self,
		**kwargs: Any,
	) -> None:
		self.__properties__: Dict[str, Any] = kwargs
		return

	def __getitem__(
		self,
		key: str,
	) -> Any:
		return self.__properties__.__getitem__(key)
	
	def __setitem__(
		self,
		key: str,
		value: Any,
	) -> None:
		return self.__properties__.__setitem__(key, value)
	
	def __delitem__(
		self,
		key: str,
	) -> None:
		return self.__properties__.__delitem__(key)
	
	def __iter__(self) -> Iterator[str]:
		return self.__properties__.__iter__()
	
	def __len__(self) -> int:
		return self.__properties__.__len__()
	
	def __contains__(
		self,
		key: object,
	) -> bool:
		return self.__properties__.__contains__(key)
	
	def keys(self) -> KeysView[str]:
		return self.__properties__.keys()
	
	def items(self) -> ItemsView[str, Any]:
		return self.__properties__.items()
	
	def values(self) -> ValuesView[Any]:
		return self.__properties__.values()
	
	def __eq__(
		self,
		other: object,
	) -> bool:
		return self.__properties__.__eq__(other)
	
	def __ne__(
		self,
		value: object,
	) -> bool:
		return self.__properties__.__ne__(value)
	
	def get(
		self,
		key: str,
		default: Any = None,
	) -> Any:
		return self.__properties__.get(key, default)


class Type(str, Enum):
	Boolean = 'boolean'
	Integer = 'integer'
	Number = 'number'
	String = 'string'
	Array = 'array'
	Object = 'object'


class Value(Descriptor):
	def __init__(
		self, 
		type: Type,
		description: Optional[str] = None,
		format: Optional[str] = None,
		min: Any = None,
		max: Any = None,
		default: Any = None,
		enum: Optional[Iterable[Any]] = None,
		required: bool = True,
	) -> None:
		super().__init__(type=type)
		if description: self['description'] = description
		if format: self['format'] = format
		if min is not None: self['minimum'] = min
		if max is not None: self['maximum'] = max
		if not required: self['default'] = default
		if enum: self['enum'] = enum
		self.required = required
		return


class Condition(ABC):
	def __init__(
		self,
		*args: Union[Descriptor, 'Condition', 'Schema'],
	) -> None:
		self.args = args
		return


class Schema(object):
	"""Descriptor 노드, 조건 또는 JSON Schema 매핑을 이름으로 감싼다."""

	def __init__(
		self,
		name: str,
		format: Optional[Union[Mapping[str, Any], Condition, 'Schema']] = None,
	) -> None:
		self.name = name
		self.format = format
		return


class OneOf(Condition):
	def __init__(
		self,
		*args: Union[Descriptor, Condition, Schema],
		discriminator: Optional[str] = None,
		required: bool = True,
	) -> None:
		super().__init__(*args)
		self.discriminator = discriminator
		self.required = required
		return


class AllOf(Condition): pass


class TypeMapper(metaclass=ABCMeta):
	"""사용자 타입을 Value 파생 클래스와 생성 인자로 변환한다."""

	def __call__(
		self,
		o: type,
	) -> Tuple[type[Value], Dict[str, Any]]:
		raise NotImplementedError('{} must be implemented __call__'.format(self.__class__.__name__))


class TypeEncoder(metaclass=ABCMeta):
	def __call__(
		self,
		o: Any,
	) -> Any:
		raise NotImplementedError('{} must be implemented __call__'.format(self.__class__.__name__))
