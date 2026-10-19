from abc import (
	ABC,
	abstractmethod,
)
from collections.abc import Mapping
from logging import getLogger
from time import monotonic
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
	logger = getLogger('DefStream.Run')
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
		parents = tuple(base for base in cls.__mro__[1:] if issubclass(
			base,
			Run,
		))
		if parameters is not None:
			cls.parameters = parameters
		for name in (
			'priority',
			'max_priority',
		):
			if any(priority_setting(
				base.parameters,
				name,
			) is not None for base in parents) and priority_setting(
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
		task = type(self).__module__ + '.' + type(self).__qualname__
		started = monotonic()
		self.logger.debug(
			'Starting task execution: task=%s',
			task,
		)
		context = Context(
			*args,
			**kwargs,
		)
		for setup in self.setups:
			self.logger.debug(
				'Starting task setup: task=%s hook=%s',
				task,
				type(setup).__qualname__,
			)
			setup(context)
			self.logger.debug(
				'Task setup completed: task=%s hook=%s',
				task,
				type(setup).__qualname__,
			)
		try:
			if self.request is not None:
				self.logger.debug(
					'Validating task input: task=%s',
					task,
				)
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
				self.logger.debug(
					'Task input validated: task=%s',
					task,
				)
			self.logger.debug(
				'Calling user task: task=%s',
				task,
			)
			result = self.run(
				*context.args,
				**context.kwargs,
			)
			self.logger.debug(
				'User task returned: task=%s',
				task,
			)
			if self.response is not None:
				self.logger.debug(
					'Validating task output: task=%s',
					task,
				)
				result = self.response(result)
				self.logger.debug(
					'Task output validated: task=%s',
					task,
				)
		except Exception as error:
			self.logger.debug(
				'Task execution or validation failed: task=%s error_type=%s',
				task,
				type(error).__qualname__,
			)
			for handler in self.errors:
				self.logger.debug(
					'Starting task error hook: task=%s hook=%s',
					task,
					type(handler).__qualname__,
				)
				handler(
					context,
					error,
				)
				self.logger.debug(
					'Task error hook completed: task=%s hook=%s',
					task,
					type(handler).__qualname__,
				)
			raise
		for complete in self.completes:
			self.logger.debug(
				'Starting task completion hook: task=%s hook=%s',
				task,
				type(complete).__qualname__,
			)
			complete(
				context,
				result,
			)
			self.logger.debug(
				'Task completion hook completed: task=%s hook=%s',
				task,
				type(complete).__qualname__,
			)
		self.logger.debug(
			'Task execution completed: task=%s duration=%s',
			task,
			monotonic() - started,
		)
		return result

	@abstractmethod
	def run(
		self,
		**kwargs,
	) -> Any:
		raise NotImplementedError
