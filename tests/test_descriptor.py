from collections.abc import Mapping
from dataclasses import (
	dataclass,
	field,
)
from datetime import date
from inspect import (
	Parameter,
	signature,
)
from typing import (
	Annotated,
	Any,
	Dict,
	List,
	Optional,
	Set,
	Tuple,
	Union,
	get_args,
	get_type_hints,
)
from unittest import (
	TestCase,
	main,
)

from DefStream.Descriptor import (
	AllOf,
	Array,
	Binary,
	BinaryBase64Encoded,
	Boolean,
	DumpSchema,
	Integer,
	IntegerFormat,
	Number,
	NumberFormat,
	Object,
	OneOf,
	Properties,
	Schema,
	String,
	StringFormat,
	ToObject,
	ToSchema,
	TypeEncoder,
	TypeMapper,
	Value,
)
from DefStream.Descriptor.DataObject import (
	DataObjectToObject,
	DataObjectToSchema,
	SchemaToDataObject,
)
from DefStream.Descriptor.Value import (
	Type,
)
from DefStream.Worker import Specification


@dataclass
class Nullable:
	value: Optional[int] = None


@dataclass
class Choice:
	value: Union[int, str]


@dataclass
class Nested:
	items: List[Nullable] = field(default_factory=list)


@dataclass
class MetadataList:
	value: Annotated[List[int], {'format': int}]


@dataclass
class MetadataOnly:
	value: Annotated[list, {'format': int}]


@dataclass
class MetadataChoices:
	value: Annotated[list, {'format': (int, str)}]


@dataclass
class MetadataPrecedence:
	value: Annotated[List[int], {'format': str}]


@dataclass
class Dated:
	value: date


@dataclass
class Containers:
	boolean: bool
	integer: int
	number: float
	string: str
	binary: bytes
	array: list
	tuple_array: tuple
	set_array: set
	mapping: dict
	legacy_array: List
	legacy_tuple: Tuple
	legacy_set: Set
	legacy_mapping: Dict


class DateMapper(TypeMapper):
	def __call__(
		self,
		o: type,
	) -> Tuple[type[Value], Dict[str, Any]]:
		if o is not date:
			raise TypeError('지원하지 않는 사용자 타입: ' + o.__name__)
		return (
			String,
			{'format': StringFormat.date},
		)


class DateEncoder(TypeEncoder):
	def __call__(
		self,
		o: Any,
	) -> Any:
		if not isinstance(o, date):
			raise TypeError('지원하지 않는 사용자 값: ' + type(o).__name__)
		return o.isoformat()


class DescriptorTests(TestCase):
	def test_none_defaults_have_nullable_annotations(self) -> None:
		targets = (
			Value,
			Boolean,
			Integer,
			Number,
			String,
			Binary,
			BinaryBase64Encoded,
			Object,
			Array,
			Schema,
			OneOf,
			DataObjectToSchema,
			DataObjectToObject,
			SchemaToDataObject,
			DataObjectToSchema.__value__,
			DataObjectToSchema.__call__,
		)
		for target in targets:
			function = target.__init__ if isinstance(target, type) else target
			hints = get_type_hints(function)
			for name, parameter in signature(function).parameters.items():
				if parameter.default is None and parameter.annotation is not Parameter.empty:
					with self.subTest(
						target=target,
						parameter=name,
					):
						annotation = hints[name]
						self.assertTrue(
							annotation is Any or type(None) in get_args(annotation),
						)
		return

	def test_public_schema_nodes_and_conditions(self) -> None:
		properties = Properties(
			a=Integer(),
			items=Array(format=Object()),
			wrapped=Schema(
				'Text',
				String(required=False),
			),
			choice=OneOf(
				Integer(),
				String(),
			),
		)
		result = DumpSchema(Schema(
			'Object',
			Object(properties=properties),
		))
		self.assertEqual(
			result['required'],
			[
				'a',
				'items',
				'choice',
			],
		)
		self.assertEqual(
			result['properties']['items']['items']['type'],
			'object',
		)
		self.assertEqual(
			result['properties']['wrapped'],
			{
				'type': 'string',
				'default': None,
			},
		)
		condition = AllOf(
			Integer(min=0),
			OneOf(
				Integer(max=3),
				Array(format=Schema(
					'Item',
					String(),
				)),
			),
		)
		self.assertEqual(
			DumpSchema(Schema(
				'Conditions',
				condition,
			))['allOf'][1]['oneOf'][1]['items'],
			{'type': 'string'},
		)
		return

	def test_schema_mappings_keep_specification_compatible(self) -> None:
		mapping = {
			'type': 'object',
			'properties': {'name': {'type': 'string'}},
		}
		self.assertEqual(
			DumpSchema(Schema(
				'Mapping',
				mapping,
			)),
			mapping,
		)
		self.assertEqual(
			Specification(schema=mapping).document()['payload'],
			mapping,
		)
		self.assertEqual(
			DumpSchema(Schema(
				'Outer',
				Schema(
					'Inner',
					Integer(),
				),
			)),
			{'type': 'integer'},
		)
		return

	def test_mapping_contract(self) -> None:
		value = Integer(
			description='정수',
			format=IntegerFormat.int32,
			min=0,
			max=9,
			enum=['1'],
		)
		self.assertIsInstance(
			value,
			Mapping,
		)
		value['custom'] = 3
		self.assertEqual(
			value['custom'],
			3,
		)
		self.assertEqual(
			value.get('custom', 4),
			3,
		)
		self.assertEqual(
			value.get('missing', 4),
			4,
		)
		self.assertIsNone(value.get('missing'))
		self.assertEqual(
			list(value),
			list(value.keys()),
		)
		self.assertEqual(
			len(value),
			len(value.items()),
		)
		self.assertEqual(
			list(value.values()),
			list(dict(value).values()),
		)
		self.assertEqual(
			value,
			dict(value),
		)
		self.assertFalse(value != dict(value))
		del value['custom']
		self.assertNotIn(
			'custom',
			value,
		)
		with self.assertRaises(KeyError):
			value['missing']
		return

	def test_optional_union_and_nested_dataclasses(self) -> None:
		nullable = DumpSchema(ToSchema(
			Nullable,
			description=None,
			typedef=None,
		))
		self.assertEqual(
			nullable['properties']['value'],
			{
				'type': 'integer',
				'default': None,
			},
		)
		self.assertEqual(
			nullable['required'],
			[],
		)
		self.assertEqual(
			DumpSchema(ToSchema(Choice))['properties']['value'],
			{'oneOf': [
				{'type': 'integer'},
				{'type': 'string'},
			]},
		)
		nested = DumpSchema(ToSchema(Nested))['properties']['items']
		self.assertEqual(
			nested['default'],
			[],
		)
		self.assertEqual(
			nested['items']['type'],
			'object',
		)
		return

	def test_all_dataclass_value_branches(self) -> None:
		properties = DumpSchema(ToSchema(Containers))['properties']
		self.assertEqual(
			{
				name: value['type']
				for name, value in properties.items()
			},
			{
				'boolean': 'boolean',
				'integer': 'integer',
				'number': 'number',
				'string': 'string',
				'binary': 'string',
				'array': 'array',
				'tuple_array': 'array',
				'set_array': 'array',
				'mapping': 'object',
				'legacy_array': 'array',
				'legacy_tuple': 'array',
				'legacy_set': 'array',
				'legacy_mapping': 'object',
			},
		)
		return

	def test_collection_metadata_is_converted_once_without_mutation(self) -> None:
		for model in (
			MetadataList,
			MetadataOnly,
			MetadataChoices,
			MetadataPrecedence,
		):
			with self.subTest(model=model):
				before = dict(get_args(get_type_hints(model, include_extras=True)['value'])[1])
				first = DumpSchema(ToSchema(model))['properties']['value']
				second = DumpSchema(ToSchema(model))['properties']['value']
				self.assertEqual(
					first,
					second,
				)
				self.assertEqual(
					get_args(get_type_hints(model, include_extras=True)['value'])[1],
					before,
				)
				expected = {'oneOf': [
					{'type': 'integer'},
					{'type': 'string'},
				]} if model is MetadataChoices else {'type': 'integer'}
				self.assertEqual(
					first,
					{
						'type': 'array',
						'items': expected,
					},
				)
		return

	def test_iterable_metadata_and_invalid_candidates(self) -> None:
		converter = DataObjectToSchema()
		self.assertEqual(
			DumpSchema(Schema(
				'Items',
				converter.__value__(
					list,
					metadata={'format': iter((
						int,
						str,
					))},
				),
			))['items'],
			{'oneOf': [
				{'type': 'integer'},
				{'type': 'string'},
			]},
		)
		with self.assertRaisesRegex(
			TypeError,
			'not a supported type',
		):
			converter.__value__(
				list,
				metadata={'format': object()},
			)
		return

	def test_custom_mapper_and_encoder(self) -> None:
		schema = DumpSchema(ToSchema(
			Dated,
			typedef=DateMapper(),
		))
		self.assertEqual(
			schema['properties']['value'],
			{
				'type': 'string',
				'format': 'date',
			},
		)
		self.assertEqual(
			ToObject(
				Dated(date(2026, 10, 19)),
				typeenc=DateEncoder(),
			),
			{'value': '2026-10-19'},
		)
		with self.assertRaises(TypeError):
			ToSchema(Dated)
		with self.assertRaises(TypeError):
			ToObject(Dated(date(2026, 10, 19)))
		return

	def test_dataclass_instance_boundaries(self) -> None:
		for converter in (
			ToObject,
			DataObjectToObject(),
		):
			self.assertEqual(
				converter(Nullable()),
				{'value': None},
			)
			for invalid in (
				Nullable,
				object(),
			):
				with self.subTest(
					converter=converter,
					invalid=invalid,
				), self.assertRaises(TypeError):
					converter(invalid)
		return

	def test_defaults_formats_and_explicit_none(self) -> None:
		for node in (
			Boolean(description=None),
			Integer(
				description=None,
				format=None,
			),
			Number(
				description=None,
				format=None,
			),
			String(
				description=None,
				format=None,
			),
			Binary(
				description=None,
				default=None,
			),
			BinaryBase64Encoded(
				description=None,
				default=None,
			),
			Object(
				properties=None,
				default=None,
			),
			Array(
				description=None,
				format=None,
				default=None,
			),
		):
			self.assertNotIn(
				'default',
				DumpSchema(Schema(
					'Value',
					node,
				)),
			)
		self.assertEqual(
			Number(format=NumberFormat.double)['format'],
			'double',
		)
		self.assertEqual(
			String(
				format=StringFormat.date,
				min=2,
				max=5,
				default='x',
				required=False,
			),
			{
				'type': 'string',
				'format': 'date',
				'minLength': 2,
				'maxLength': 5,
				'default': 'x',
			},
		)
		self.assertEqual(
			Value(Type.Integer)['type'],
			Type.Integer,
		)
		with self.assertRaises(NotImplementedError):
			SchemaToDataObject(Schema('Empty'))
		return


if __name__ == '__main__':
	main()
