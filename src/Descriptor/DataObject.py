# -*- coding: utf-8 -*-

from .Value import (
	Descriptor,
	Condition,
	Value,
	Schema,
	OneOf,
	TypeMapper,
	TypeEncoder,
)

from .Types import (
	Boolean,
	Integer,
	Number,
	String,
	Binary,
	Array,
	Object,
	Properties,
)

from dataclasses import (
	is_dataclass,
	MISSING,
	asdict,
)
from json import (
	dumps,
	loads,
)
from typing import (
	Type,
	Any,
	Union,
	Optional,
	Dict,
	Iterable,
	Annotated,
	get_origin,
	get_args,
	get_type_hints,
	ForwardRef,
)

__all__ = (
	'SchemaToDataObject',
	'DataObjectToSchema',
	'DataObjectToObject',
)


def SchemaToDataObject(
	o: Schema,
	name: Optional[str] = None,
) -> object:
	# TODO: 스키마에 대응하는 dataclass 동적 생성을 구현한다.
	raise NotImplementedError('SchemaToDataObject is not implemented yet')


class DataObjectToSchema(object):
	def __init__(
		self,
		mapper: Optional[TypeMapper] = None,
	) -> None:
		self.mapper = mapper
		return
	def __value__(
		self,
		o: object,
		format: Optional[object] = None,
		description: Optional[str] = None,
		required: bool = True,
		default: Any = MISSING,
		metadata: Any = None,
	) -> Union[Descriptor, Condition, Schema]:
		args = get_args(o)
		origin = get_origin(o)
		if origin is not None and not args:
			return self.__value__(
				origin,
				format=format,
				description=description,
				required=required,
				default=default,
				metadata=metadata,
			)
		if args:
			if len(args) == 1:
				if origin is list:
					return self.__value__(
						list,
						format=args[0],
						description=description,
						required=required,
						default=default,
						metadata=metadata,
					)
				if origin is tuple:
					return self.__value__(
						tuple,
						format=args[0],
						description=description,
						required=required,
						default=default,
						metadata=metadata,
					)
				if origin is set:
					return self.__value__(
						set,
						format=args[0],
						description=description,
						required=required,
						default=default,
						metadata=metadata,
					)
				if origin is Union:
					return self.__value__(
						Union,
						format=args[0],
						description=description,
						required=required,
						default=default,
						metadata=metadata,
					)
				raise TypeError('{} is not a supported type'.format(o))
			if len(args) == 2:
				if origin is Union:
					if args[0] is type(None): # Union[type, None]
						return self.__value__(
							args[1],
							description=description,
							required=False,
							default=None,
							metadata=metadata,
						)
					if args[1] is type(None): # Union[None, type]
						return self.__value__(
							args[0],
							description=description,
							required=False,
							default=None,
							metadata=metadata,
						)
					# Union[type, type]
					return self.__value__(
						origin,
						format=(args[0], args[1]),
						description=description,
						required=required,
						default=default,
						metadata=metadata,
					)
				if origin is dict: # Dict[type, type]
					return self.__value__(
						dict,
						description=description,
						required=required,
						default=default,
						metadata=metadata,
					)
				if origin is Annotated:
					if isinstance(args[1], str):
						return self.__value__(
							args[0],
							description=args[1],
							required=required,
							default=default,
						)
					return self.__value__(
						args[0],
						description=description,
						required=required,
						default=default,
						metadata=args[1],
					)
				raise TypeError('{} is not a supported type'.format(o))	
			if origin is Union:
				fs= [self.__value__(f) for f in args]
				return OneOf(*fs, required=required)
			if origin is Annotated:
				if isinstance(args[1], str):
					return self.__value__(
						args[0],
						description=args[1],
						required=required,
						default=default,
						metadata=args[2] if isinstance(args[2], dict) else args[2:],
					)
				if isinstance(args[2], str):
					return self.__value__(
						args[0],
						description=args[2],
						required=required,
						default=default,
						metadata=args[1],
					)
				return self.__value__(
					args[0],
					description=description,
					required=required,
					default=default,
					metadata=args[1:],
				)
			raise TypeError('{} is not a supported type'.format(o))	
		if o is bool:
			kwargs: Dict[str, Any] = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
			return Boolean(**kwargs)
		if o is int:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
				if 'format' in metadata.keys(): kwargs['format'] = metadata['format']
				if 'min' in metadata.keys(): kwargs['min'] = metadata['min']
				if 'max' in metadata.keys(): kwargs['max'] = metadata['max']
				if 'enum' in metadata.keys(): kwargs['enum'] = metadata['enum']
			return Integer(**kwargs)
		if o is float:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
				if 'format' in metadata.keys(): kwargs['format'] = metadata['format']
				if 'min' in metadata.keys(): kwargs['min'] = metadata['min']
				if 'max' in metadata.keys(): kwargs['max'] = metadata['max']
				if 'enum' in metadata.keys(): kwargs['enum'] = metadata['enum']
			return Number(**kwargs)
		if o is str:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
				if 'format' in metadata.keys(): kwargs['format'] = metadata['format']
				if 'min' in metadata.keys(): kwargs['min'] = metadata['min']
				if 'max' in metadata.keys(): kwargs['max'] = metadata['max']
				if 'enum' in metadata.keys(): kwargs['enum'] = metadata['enum']
			return String(**kwargs)
		if o is bytes:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
			return Binary(**kwargs)
		if o is list:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
				if format is None and 'format' in metadata:
					format = metadata['format']
			if format is not None:
				candidates = tuple(format) if isinstance(format, Iterable) else (format,)
				nodes = [self.__value__(candidate) for candidate in candidates]
				kwargs['format'] = nodes[0] if len(nodes) == 1 else OneOf(*nodes)
			return Array(**kwargs)
		if o is tuple:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
			return Array(**kwargs)
		if o is set:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
			return Array(**kwargs)
		if o is dict:
			kwargs = {
				'description': description,
				'required': required,
			}
			if default is not MISSING:
				kwargs['default'] = default
			if metadata and isinstance(metadata, dict):
				if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
				if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
			return Object(**kwargs)
		if o is Union:
			kwargs = {}
			if default is not MISSING:
				kwargs['default'] = default
			if not format:
				raise TypeError('Union type must have format')
			candidates = tuple(format) if isinstance(format, Iterable) else (format,)
			return OneOf(*[self.__value__(f) for f in candidates], **kwargs)
		if isinstance(o, type) and is_dataclass(o):
			return self.__call__(o, required=required)
		if isinstance(o, ForwardRef):
			if o.__forward_arg__ in globals():
				return self.__value__(globals()[o.__forward_arg__], description=description, required=required, default=default, metadata=metadata)
			if o.__forward_arg__ in locals():
				return self.__value__(locals()[o.__forward_arg__], description=description, required=required, default=default, metadata=metadata)
			raise TypeError('Cannot resolve schema forward reference: ' + o.__forward_arg__)
		if self.mapper and isinstance(o, type):
			V, kws = self.mapper(o)
			if V:
				if not issubclass(V, Value):
					raise TypeError('{} is not a Value'.format(V))
				kwargs = {
					'description': description,
					'required': required,
				}
				if default is not MISSING:
					kwargs['default'] = default
				if metadata and isinstance(metadata, dict):
					if 'description' in metadata.keys(): kwargs['description'] = metadata['description']
					if 'required' in metadata.keys(): kwargs['required'] = metadata['required']
					if V in (Integer, Number, String):
						if 'format' in metadata.keys(): kwargs['format'] = metadata['format']
						if 'min' in metadata.keys(): kwargs['min'] = metadata['min']
						if 'max' in metadata.keys(): kwargs['max'] = metadata['max']
						if 'enum' in metadata.keys(): kwargs['enum'] = metadata['enum']
				kwargs.update(kws)
				return V(**kwargs)
		raise TypeError('{} is not a supported type'.format(o))

	def __call__(
		self,
		o: Type[object],
		description: Optional[str] = None,
		required: bool = True,
	) -> Schema:
		if not is_dataclass(o):
			raise TypeError('{} is not a DataObject(dataclass).'.format(o.__name__))
		hints = get_type_hints(o, include_extras=True)
		return Schema(
			name=description or o.__name__,
			format=Object(
				description=description or o.__name__,
				properties=Properties(
					**{
						f.name: self.__value__(
							hints[f.name],
							required=True if f.default is MISSING and f.default_factory is MISSING else False,
							default=f.default_factory() if f.default_factory is not MISSING else f.default,
						) for f in o.__dataclass_fields__.values()
					}
				),
				required=required,
			)
		)


class DataObjectToObject(object):
	def __init__(
		self,
		encoder: Optional[TypeEncoder] = None,
	) -> None:
		self.encoder = encoder
		return

	def __call__(
		self,
		o: object,
	) -> Dict[str, Any]:
		if not is_dataclass(o) or isinstance(o, type):
			raise TypeError('{} is not a DataObject(dataclass) instance.'.format(type(o).__name__))
		_ = dumps(
			asdict(o),
			default=self.encoder,
			ensure_ascii=False,
		)
		return loads(_)
