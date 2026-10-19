from abc import (
	ABC,
	abstractmethod,
)
from collections.abc import Mapping
from typing import (
	Any,
	Optional,
	Sequence,
	Tuple,
	Union,
)

from ..Broker.Event import EventError
from ..Broker.Priority import validate_priority
from .Specification import Specification

__all__ = (
	'Context',
	'RunSetup',
	'RunComplete',
	'RunError',
	'Run',
)


def priority_setting(
	parameters: Any,
	name: str,
) -> Optional[int]:
	if isinstance(
		parameters,
		Mapping,
	):
		return parameters.get(name)
	return getattr(
		parameters,
		name,
		None,
	)


class Context:
	def __init__(
		self,
		*args,
		**kwargs,
	):
		self.args = args
		self.kwargs = kwargs


class RunSetup(ABC):
	@abstractmethod
	def __call__(
		self,
		context: Context,
	) -> None:
		raise NotImplementedError


class RunComplete(ABC):
	@abstractmethod
	def __call__(
		self,
		context: Context,
		completion: Any,
	) -> None:
		raise NotImplementedError


class RunError(ABC):
	@abstractmethod
	def __call__(
		self,
		context: Context,
		error: Exception,
	) -> None:
		raise NotImplementedError


class Run(ABC):
	parameters: Any = None
	on_error: Optional[EventError] = None
	setups: Tuple[RunSetup, ...] = ()
	completes: Tuple[RunComplete, ...] = ()
	errors: Tuple[RunError, ...] = ()
	request: Optional[Specification] = None
	response: Optional[Specification] = None

	def __init_subclass__(
		cls,
		*,
		parameters: Any = None,
		on_error: Optional[EventError] = None,
		setups: Optional[Union[RunSetup, Sequence[RunSetup]]] = None,
		completes: Optional[Union[RunComplete, Sequence[RunComplete]]] = None,
		errors: Optional[Union[RunError, Sequence[RunError]]] = None,
		request: Optional[Specification] = None,
		response: Optional[Specification] = None,
		**kwargs,
	):
		super().__init_subclass__(**kwargs)
		parent = next(base for base in cls.__mro__[1:] if issubclass(
			base,
			Run,
		))
		if parameters is not None:
			cls.parameters = parameters
		for name in (
			'priority',
			'max_priority',
		):
			if priority_setting(
				parent.parameters,
				name,
			) is not None and priority_setting(
				cls.parameters,
				name,
			) is None:
				raise ValueError('Inherited task ' + name + ' cannot be cleared')
		maximum = priority_setting(
			cls.parameters,
			'max_priority',
		)
		validate_priority(
			maximum,
			None,
			minimum=1,
			name='max_priority',
		)
		validate_priority(
			priority_setting(
				cls.parameters,
				'priority',
			),
			maximum,
		)
		for name, specification in (
			(
				'request',
				request,
			),
			(
				'response',
				response,
			),
		):
			if specification is not None:
				if not isinstance(
					specification,
					Specification,
				):
					raise TypeError(name + ' must be a Specification')
				setattr(
					cls,
					name,
					specification,
				)
		if on_error is not None:
			if not callable(on_error):
				raise TypeError('on_error must be a callable event error policy')
			cls.on_error = on_error
		if setups is not None:
			cls.setups = tuple(setups) if isinstance(
				setups,
				Sequence,
			) else (setups,)
		if completes is not None:
			cls.completes = tuple(completes) if isinstance(
				completes,
				Sequence,
			) else (completes,)
		if errors is not None:
			cls.errors = tuple(errors) if isinstance(
				errors,
				Sequence,
			) else (errors,)
		for hooks in (
			cls.setups,
			cls.completes,
			cls.errors,
		):
			if not all(callable(hook) for hook in hooks):
				raise TypeError('Run hooks must be callable')
		return

	def __call__(
		self,
		*args,
		**kwargs,
	) -> Any:
		context = Context(
			*args,
			**kwargs,
		)
		for setup in self.setups:
			setup(context)
		try:
			if self.request is not None:
				if context.args:
					raise TypeError('A specified task request requires keyword arguments')
				body = self.request(context.kwargs)
				if not isinstance(
					body,
					Mapping,
				) or not all(isinstance(
					key,
					str,
				) for key in body):
					raise TypeError('A task request must remain a mapping with string keys')
				context.kwargs = dict(body)
			result = self.run(
				*context.args,
				**context.kwargs,
			)
			if self.response is not None:
				result = self.response(result)
		except Exception as error:
			for handler in self.errors:
				handler(
					context,
					error,
				)
			raise
		for complete in self.completes:
			complete(
				context,
				result,
			)
		return result

	@abstractmethod
	def run(
		self,
		**kwargs,
	) -> Any:
		raise NotImplementedError
