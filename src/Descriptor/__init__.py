from collections.abc import (
	Mapping,
	Sequence,
)
from dataclasses import is_dataclass
from json import (
	dumps,
	loads,
)
from typing import (
	Any,
	Optional,
	Type,
)

from .Value import (
	Value,
	Condition,
	Schema,
	OneOf,
	AllOf,
	TypeMapper,
	TypeEncoder,
)
from .Types import (
	Boolean,
	IntegerFormat,
	Integer,
	NumberFormat,
	Number,
	StringFormat,
	String,
	Binary,
	BinaryBase64Encoded,
	Array,
	Object,
	Properties,
)
from .DataObject import (
	DataObjectToSchema,
	DataObjectToObject,
)

__all__ = (
	'Value',
	'Condition',
	'Schema',
	'OneOf',
	'AllOf',
	'TypeMapper',
	'TypeEncoder',
	'Boolean',
	'IntegerFormat',
	'Integer',
	'NumberFormat',
	'Number',
	'StringFormat',
	'String',
	'Binary',
	'BinaryBase64Encoded',
	'Array',
	'Object',
	'Properties',
	'ToSchema',
	'DumpSchema',
	'ToObject',
)


def schema_value(
	value: Any,
) -> Any:
	if isinstance(
		value,
		Schema,
	):
		return schema_value(value.format)
	if isinstance(
		value,
		Condition,
	):
		if isinstance(
			value,
			OneOf,
		):
			key = 'oneOf'
		elif isinstance(
			value,
			AllOf,
		):
			key = 'allOf'
		else:
			raise TypeError('Unsupported schema condition: ' + type(value).__name__)
		return {key: [schema_value(arg) for arg in value.args]}
	if isinstance(
		value,
		Mapping,
	):
		return {
			key: schema_value(item) for key, item in value.items()
		}
	if isinstance(
		value,
		Sequence,
	) and not isinstance(
		value,
		(
			str,
			bytes,
			bytearray,
		),
	):
		return [schema_value(item) for item in value]
	if value is None or isinstance(
		value,
		(
			str,
			int,
			float,
			bool,
		),
	):
		return value
	raise TypeError('Unsupported schema value: ' + type(value).__name__)


def DumpSchema(
	o: Schema,
) -> dict:
	if not isinstance(
		o,
		Schema,
	):
		raise TypeError('A Schema is required')
	result = schema_value(o)
	if not isinstance(
		result,
		dict,
	):
		raise TypeError('A schema must describe an object, value or condition')
	return loads(dumps(
		result,
		allow_nan=False,
	))


def ToSchema(
	o: Type[object],
	description: Optional[str] = None,
	typedef: Optional[TypeMapper] = None,
) -> Schema:
	if not isinstance(
		o,
		type,
	) or not is_dataclass(o):
		raise TypeError('A dataclass type is required')
	return DataObjectToSchema(mapper=typedef)(
		o,
		description,
	)


def ToObject(
	o: object,
	typeenc: Optional[TypeEncoder] = None,
) -> dict:
	if isinstance(
		o,
		type,
	) or not is_dataclass(o):
		raise TypeError('A dataclass instance is required')
	return DataObjectToObject(encoder=typeenc)(o)
