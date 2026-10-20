from dataclasses import (
	dataclass,
	field,
)
from http.client import HTTPConnection
from json import loads
from os import environ
from pickle import (
	dumps,
	loads as unpickle,
)
from sys import modules
from threading import (
	Event,
	Thread,
)
from typing import (
	List,
)
from unittest import (
	TestCase,
	main,
	skipUnless,
)
from unittest.mock import Mock
from uuid import uuid4

from DefStream.Broker import RemoteError
from DefStream.Broker.Policies import Reject
from DefStream.Descriptor import (
	AllOf,
	Array,
	DumpSchema,
	Integer,
	Object,
	OneOf,
	Properties,
	Schema,
	String,
	ToObject,
	ToSchema,
)
from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import Specifications
from DefStream.Validator import (
	Validate,
	Validator,
)
from DefStream.Validator.Patterns import (
	IsGreaterThan,
	IsInteger,
	IsObject,
	SetDefault,
	ToInteger,
)
from DefStream.Validator.Patterns.Object import (
	IsMappingOf,
	IsRequiredIn,
)
from DefStream.Worker import (
	ProcessPool,
	Run,
	Specification,
	ThreadPool,
	Worker,
	request,
)


@dataclass
class Operands:
	a: int
	b: int = 2


@dataclass
class Batch:
	items: List[int] = field(default_factory=list)


@dataclass
class ForwardOperands:
	value: 'Operands'


class Add(
	Run,
	parameters={'queue': 'spec.add'},
	request=Specification(
		schema=Object(
			properties=Properties(
				a=Integer(),
				b=Integer(required=False),
			),
		),
		validator=Validator(IsObject(
			IsRequiredIn('a'),
			IsMappingOf({
				'a': ToInteger(),
				'b': (
					SetDefault(2),
					IsInteger(),
				),
			}),
		)),
		example={'a': 3},
	),
	response=Specification(
		schema=Integer(),
		validator=ToInteger(),
		example=5,
	),
):
	"""Add two operands."""

	def run(
		self,
		a,
		b,
	):
		return str(a + b)


class ContractTests(TestCase):
	def test_format_sets_message_content_type_without_changing_validation(self):
		self.assertEqual(
			Specification().document()['contentType'],
			'application/json',
		)
		specification = Specification(
			schema=String(),
			validator=str,
			format='text/plain; charset=utf-8',
		)
		self.assertEqual(
			specification.document()['contentType'],
			'text/plain; charset=utf-8',
		)
		self.assertEqual(
			specification(3),
			'3',
		)
		for invalid in (
			None,
			'',
			'json',
			'text/',
			'*/json',
			'application/json\r\nInjected: header',
		):
			with self.subTest(format=invalid), self.assertRaises(ValueError):
				Specification(format=invalid)

	def test_original_descriptor_and_validator_api_without_datamodel(self):
		self.assertEqual(
			Add()(a='3'),
			5,
		)
		self.assertEqual(
			ToObject(Operands(3)),
			{
				'a': 3,
				'b': 2,
			},
		)
		schema = DumpSchema(ToSchema(Operands))
		self.assertEqual(
			schema['required'],
			['a'],
		)
		self.assertEqual(
			schema['properties']['b']['default'],
			2,
		)
		self.assertFalse(any('DataModel' in name for name in modules if name.startswith('DefStream.Descriptor')))
		batch_schema = DumpSchema(ToSchema(Batch))
		self.assertEqual(
			batch_schema['properties']['items']['items'],
			{'type': 'integer'},
		)
		self.assertEqual(
			batch_schema['properties']['items']['default'],
			[],
		)
		self.assertEqual(
			DumpSchema(ToSchema(ForwardOperands))['properties']['value']['type'],
			'object',
		)

	def test_schema_conditions_bounds_defaults_and_unsupported_values(self):
		schema = DumpSchema(Schema(
			'Value',
			AllOf(
				Integer(min=0),
				Integer(max=99),
			),
		))
		self.assertEqual(
			list(schema),
			['allOf'],
		)
		self.assertEqual(
			DumpSchema(Schema(
				'Text',
				String(
					min=2,
					max=5,
				),
			)),
			{
				'type': 'string',
				'minLength': 2,
				'maxLength': 5,
			},
		)
		self.assertEqual(
			DumpSchema(Schema(
				'Items',
				Array(default=[]),
			))['default'],
			[],
		)
		self.assertIn(
			'oneOf',
			DumpSchema(Schema(
				'Choice',
				OneOf(
					Integer(),
					String(),
				),
			)),
		)
		with self.assertRaises(TypeError):
			DumpSchema(Schema(
				'Unsupported',
				object(),
			))

	def test_literal_conversion_rejects_code_and_validate_supports_no_defaults(self):
		with self.assertRaises(ValueError):
			ToInteger()("__import__('sys').exit()")
		self.assertEqual(
			Validator(
				ToInteger(),
				IsGreaterThan(0),
			)('3'),
			3,
		)

		@Validate({'a': ToInteger()})
		def convert(a, /):
			return a

		self.assertEqual(
			convert('3'),
			3,
		)

	def test_specification_inheritance_pickling_and_both_pools(self):
		class Child(Add):
			pass

		self.assertIs(
			Child.request,
			Add.request,
		)
		self.assertEqual(
			unpickle(dumps(Add.request))({'a': '4'}),
			{
				'a': 4,
				'b': 2,
			},
		)
		for pool_type in (
			ThreadPool,
			ProcessPool,
		):
			pool = pool_type(1)
			try:
				self.assertEqual(
					pool.submit(
						Add,
						{'a': '3'},
					).result(timeout=15),
					5,
				)
			finally:
				pool.stop()

	def test_request_and_response_failures_reach_error_hooks_before_complete(self):
		error = Mock()
		complete = Mock()

		class Checked(
			Add,
			errors=error,
			completes=complete,
		):
			pass

		with self.assertRaises(ValueError):
			Checked()(a='invalid')
		error.assert_called_once()
		complete.assert_not_called()
		error.reset_mock()

		class WrongResponse(
			Checked,
			response=Specification(validator=IsInteger()),
		):
			pass

		with self.assertRaises(TypeError):
			WrongResponse()(a='3')
		error.assert_called_once()
		complete.assert_not_called()
		self.assertEqual(
			error.call_args.args[0].kwargs,
			{
				'a': 3,
				'b': 2,
			},
		)

	def test_transformed_response_reaches_completion_hooks(self):
		complete = Mock()

		class Checked(
			Add,
			completes=complete,
		):
			pass

		self.assertEqual(
			Checked()(a='3'),
			5,
		)
		self.assertEqual(
			complete.call_args.args[1],
			5,
		)

	def test_invalid_contracts_and_nonmapping_requests_fail_explicitly(self):
		with self.assertRaises(TypeError):
			class Invalid(
				Run,
				request='invalid',
			):
				pass
		with self.assertRaises(TypeError):
			Specification(schema=object())
		with self.assertRaises(TypeError):
			Specification(validator=1)

		class NonMapping(
			Add,
			request=Specification(validator=lambda value: 3),
		):
			pass

		with self.assertRaisesRegex(
			TypeError,
			'mapping',
		):
			NonMapping()(a=1)
		self.assertEqual(
			Specification(schema=Operands).document()['payload']['type'],
			'object',
		)
		self.assertEqual(
			Specification(example=None).document()['examples'],
			[{'payload': None}],
		)


class DocumentTests(TestCase):
	def test_document_default_format_and_message_overrides(self):
		class Plain(
			Run,
			parameters={'queue': 'plain'},
		):
			def run(self):
				pass

		inspector = self.inspector()
		inspector.worker.add(Plain)
		self.assertEqual(
			Specifications('/spec').document(inspector)['defaultContentType'],
			'application/json',
		)
		extension = Specifications(
			'/spec',
			format='application/xml',
		)
		document = extension.document(inspector)
		self.assertEqual(
			document['defaultContentType'],
			'application/xml',
		)
		self.assertNotIn(
			'contentType',
			document['channels']['plain']['messages']['request'],
		)
		self.assertEqual(
			document['channels']['spec.add']['messages']['request']['contentType'],
			'application/json',
		)
		self.assertEqual(
			extension(inspector).content_type,
			'application/json; charset=utf-8',
		)
		for invalid in (
			None,
			'',
			'json',
			'text/*',
			'application/json\r\nInjected: header',
		):
			with self.subTest(format=invalid), self.assertRaises(ValueError):
				Specifications(
					'/spec',
					format=invalid,
				)

	def test_operation_uses_run_name_and_description(self):
		class Described(
			Add,
			parameters={'queue': 'described'},
			name='described',
			description='Add request description',
		):
			"""Not the operation description."""

		class Empty(
			Add,
			parameters={'queue': 'empty'},
			name='empty',
			description='',
		):
			pass

		inspector = self.inspector()
		inspector.worker.add(Described)
		inspector.worker.add(Empty)
		operations = Specifications('/spec').document(inspector)['operations']
		self.assertEqual(
			operations['described']['description'],
			'Add request description',
		)
		self.assertEqual(
			operations['empty']['description'],
			'',
		)
		self.assertNotIn(
			'description',
			operations[Add.name],
		)

	def test_run_name_defaults_to_qualified_class_name(self):
		class Local(
			Run,
			parameters={'queue': 'local-name'},
		):
			def run(self):
				pass

		self.assertEqual(
			Local.name,
			Local.__module__ + '.' + Local.__qualname__,
		)

	def test_run_name_must_be_a_python_identifier(self):
		for invalid in (
			'',
			'not-valid',
			'has space',
			'class',
		):
			with self.subTest(name=invalid), self.assertRaises(ValueError):
				class Invalid(
					Run,
					name=invalid,
				):
					def run(self):
						pass
		with self.assertRaises(TypeError):
			class InvalidType(
				Run,
				name=1,
			):
				def run(self):
					pass
		with self.assertRaises(TypeError):
			class InvalidDescription(
				Run,
				description=1,
			):
				def run(self):
					pass

	def test_run_metadata_is_not_inherited_by_subclasses(self):
		class Parent(
			Run,
			name='parent',
			description='Parent task',
		):
			def run(self):
				pass

		class Child(Parent):
			pass

		self.assertEqual(
			Parent.name,
			'parent',
		)
		self.assertEqual(
			Parent.description,
			'Parent task',
		)
		self.assertEqual(
			Child.name,
			Child.__module__ + '.' + Child.__qualname__,
		)
		self.assertIsNone(Child.description)

	def test_duplicate_run_names_are_rejected_on_registration_and_documentation(self):
		class First(
			Run,
			parameters={'queue': 'first'},
			name='duplicate',
		):
			def run(self):
				pass

		class Second(
			Run,
			parameters={'queue': 'second'},
			name='duplicate',
		):
			def run(self):
				pass

		inspector = self.inspector()
		inspector.worker.add(First)
		with self.assertRaisesRegex(ValueError, 'Duplicate Run name'):
			inspector.worker.add(Second)
		inspector.worker.tasks.append(Second)
		with self.assertRaisesRegex(ValueError, 'Duplicate task specification'):
			Specifications('/spec').document(inspector)

	def test_specification_does_not_accept_description(self):
		with self.assertRaises(TypeError):
			Specification(description='No longer supported')

	def test_request_and_response_formats_are_preserved_in_asyncapi(self):
		class Formatted(
			Add,
			parameters={'queue': 'formatted'},
			request=Specification(format='application/vnd.defstream.task+json'),
			response=Specification(
				schema=String(),
				format='text/plain',
			),
		):
			pass

		inspector = self.inspector()
		inspector.worker.add(Formatted)
		document = Specifications('/spec').document(inspector)
		formats = {
			message['contentType']
			for channel in document['channels'].values()
			for message in channel['messages'].values()
		}
		self.assertIn(
			'application/vnd.defstream.task+json',
			formats,
		)
		self.assertIn(
			'text/plain',
			formats,
		)

	def inspector(self):
		worker = Worker(
			Mock(),
			ThreadPool(1),
		)
		worker.add(Add)
		inspector = Inspector()
		inspector.worker = worker
		self.addCleanup(worker.pool.stop)
		return inspector

	def test_asyncapi_references_and_response_contract(self):
		inspector = self.inspector()
		document = Specifications('/asyncapi.json').document(inspector)
		self.assertEqual(
			document['asyncapi'],
			'3.1.0',
		)
		key = Add.name
		self.assertEqual(
			document['channels']['spec.add']['address'],
			'spec.add',
		)
		operation = document['operations'][key]
		self.assertEqual(
			operation['action'],
			'receive',
		)
		self.assertIn(
			'reply',
			operation,
		)
		self.assertNotIn(
			'x-response',
			operation,
		)
		self.assertEqual(
			operation['reply'],
			{
				'channel': {'$ref': '#/channels/spec.add'},
				'messages': [{'$ref': '#/channels/spec.add/messages/response'}],
			},
		)
		self.assertEqual(
			set(document['channels']),
			{'spec.add'},
		)
		self.assertEqual(
			operation['messages'],
			[{'$ref': '#/channels/spec.add/messages/request'}],
		)

		def resolve(value):
			if isinstance(
				value,
				dict,
			):
				if '$ref' in value:
					target = document
					for part in value['$ref'][2:].split('/'):
						target = target[part.replace(
							'~1',
							'/',
						).replace(
							'~0',
							'~',
						)]
				for item in value.values():
					resolve(item)
			elif isinstance(
				value,
				list,
			):
				for item in value:
					resolve(item)

		resolve(document)

	def test_http_serving_json_and_head(self):
		inspector = self.inspector()
		worker = inspector.worker
		extension = Specifications('/asyncapi.json')
		inspector = Inspector(
			port=0,
			exts=(extension,),
		)
		inspector.start(worker)
		self.addCleanup(inspector.stop)
		connection = HTTPConnection(
			'127.0.0.1',
			inspector.server.server_port,
			timeout=3,
		)
		try:
			connection.request(
				'GET',
				'/asyncapi.json',
			)
			response = connection.getresponse()
			self.assertEqual(
				response.status,
				200,
			)
			self.assertEqual(
				loads(response.read())['asyncapi'],
				'3.1.0',
			)
			connection.request(
				'HEAD',
				'/asyncapi.json',
			)
			response = connection.getresponse()
			self.assertEqual(
				response.read(),
				b'',
			)
		finally:
			connection.close()

	def test_missing_queue_and_unattached_inspector_fail_explicitly(self):
		with self.assertRaises(RuntimeError):
			Specifications('/spec').document(Inspector())
		inspector = self.inspector()

		class Unknown(
			Run,
			parameters={'not-queue': 'value'},
		):
			def run(self):
				pass

		inspector.worker.add(Unknown)
		with self.assertRaisesRegex(
			ValueError,
			'queue',
		):
			Specifications('/spec').document(inspector)

	def test_default_operation_names_use_qualified_class_names(self):
		class Local(
			Add,
			parameters={'queue': 'local'},
		):
			pass

		inspector = self.inspector()
		inspector.worker.add(Local)
		document = Specifications('/spec').document(inspector)
		self.assertEqual(
			set(document['operations']),
			{
				Add.name,
				Local.name,
			},
		)

	def test_queue_keys_are_preserved_and_json_pointer_references_escaped(self):
		class Custom(
			Add,
			parameters={'queue': 'orders/add~v1'},
		):
			pass

		inspector = self.inspector()
		inspector.worker.add(Custom)
		document = Specifications('/spec').document(inspector)
		self.assertEqual(
			document['channels']['orders/add~v1']['address'],
			'orders/add~v1',
		)
		self.assertEqual(
			document['operations'][Custom.name]['channel'],
			{'$ref': '#/channels/orders~1add~0v1'},
		)
		self.assertEqual(
			document['operations'][Custom.name]['messages'],
			[{'$ref': '#/channels/orders~1add~0v1/messages/request'}],
		)
		self.assertEqual(
			document['operations'][Custom.name]['reply']['messages'],
			[{'$ref': '#/channels/orders~1add~0v1/messages/response'}],
		)

	def test_class_name_fallback_without_request_and_duplicate_channels(self):
		class Plain(
			Run,
			parameters={'queue': 'plain'},
		):
			def run(self):
				pass

		class Duplicate(
			Add,
		):
			pass

		inspector = self.inspector()
		inspector.worker.add(Plain)
		self.assertIn(
			'plain',
			Specifications('/spec').document(inspector)['channels'],
		)
		inspector.worker.add(Duplicate)
		with self.assertRaisesRegex(
			ValueError,
			'Duplicate',
		):
			Specifications('/spec').document(inspector)

	def test_removed_channel_option_is_rejected(self):
		with self.assertRaises(TypeError):
			Specification(channel='unused')

	def test_shared_reply_channel_and_no_response(self):
		class Custom(
			Add,
			parameters={'queue': 'custom'},
		):
			pass

		class Plain(
			Run,
			parameters={'queue': 'plain'},
		):
			def run(self):
				pass

		inspector = self.inspector()
		inspector.worker.add(Custom)
		inspector.worker.add(Plain)
		document = Specifications('/spec').document(inspector)
		self.assertEqual(
			document['operations'][Custom.name]['reply']['channel'],
			{'$ref': '#/channels/custom'},
		)
		self.assertNotIn(
			'reply',
			document['operations'][Plain.name],
		)
		self.assertNotIn(
			'response',
			document['channels']['plain']['messages'],
		)

	def test_completion_suffix_is_an_independent_queue_name(self):
		class Conflict(
			Add,
			parameters={'queue': 'spec.add.completion'},
		):
			pass

		inspector = self.inspector()
		inspector.worker.add(Conflict)
		document = Specifications('/spec').document(inspector)
		self.assertEqual(
			set(document['channels']),
			{
				'spec.add',
				'spec.add.completion',
			},
		)

	def test_duplicate_operation_names_are_explicit(self):
		class Other(
			Add,
			parameters={'queue': 'other'},
		):
			pass

		Other.name = Add.name
		inspector = self.inspector()
		inspector.worker.tasks.append(Other)
		with self.assertRaisesRegex(
			ValueError,
			'Duplicate task specification',
		):
			Specifications('/spec').document(inspector)

	def test_completion_suffix_does_not_collide_regardless_of_task_order(self):
		class First(
			Add,
			parameters={'queue': 'later.completion'},
		):
			pass

		class Later(
			Add,
			parameters={'queue': 'later'},
		):
			pass

		inspector = self.inspector()
		inspector.worker.add(First)
		inspector.worker.add(Later)
		document = Specifications('/spec').document(inspector)
		self.assertEqual(
			document['operations'][Later.name]['reply']['channel'],
			{'$ref': '#/channels/later'},
		)


@skipUnless(
	environ.get('DEFSTREAM_RABBITMQ_TESTS') == '1',
	'Opt-in local RabbitMQ Specification integration',
)
class SpecificationRPCTests(TestCase):
	def test_validation_and_transformed_response_over_real_rpc(self):
		from DefStream.Broker.Implements.RabbitMQ import (
			Connection,
			Configuration,
		)

		class Checked(
			Add,
			parameters={'queue': 'defstream-spec-' + uuid4().hex},
			on_error=Reject(),
		):
			pass

		connection = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		))
		connection.connect()
		ready = Event()

		def prepare(worker):
			worker.broker.declare(Checked.parameters)
			ready.set()

		worker = Worker(
			Connection(connection.conf),
			ThreadPool(1),
			setups=prepare,
		)
		worker.add(Checked)
		failures = []

		def run():
			try:
				worker.run()
			except BaseException as error:
				failures.append(error)
				ready.set()

		thread = Thread(target=run)
		thread.start()
		try:
			self.assertTrue(ready.wait(5))
			self.assertEqual(
				request(
					{'a': '3'},
					task=Checked,
					broker=connection,
					timeout=5,
				),
				5,
			)
			with self.assertLogs(
				'DefStream.Worker',
				level='ERROR',
			), self.assertRaises(RemoteError):
				request(
					{'a': 'invalid'},
					task=Checked,
					broker=connection,
					timeout=5,
				)
		finally:
			worker.stop()
			thread.join(10)
			try:
				self.assertFalse(thread.is_alive())
				self.assertEqual(
					failures,
					[],
				)
				connection.delete_queue(Checked.parameters['queue'])
			finally:
				connection.close()


if __name__ == '__main__':
	main()
