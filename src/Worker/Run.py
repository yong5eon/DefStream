from abc import (
	ABC,
	abstractmethod,
)
from typing import (
	Any,
	Optional,
	Sequence,
	Tuple,
	Union,
)

from ..Broker.Event import EventError

__all__ = (
	'Context',
	'RunSetup',
	'RunComplete',
	'RunError',
	'Run',
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

	def __init_subclass__(
		cls,
		*,
		parameters: Any = None,
		on_error: Optional[EventError] = None,
		setups: Optional[Union[RunSetup, Sequence[RunSetup]]] = None,
		completes: Optional[Union[RunComplete, Sequence[RunComplete]]] = None,
		errors: Optional[Union[RunError, Sequence[RunError]]] = None,
		**kwargs,
	):
		super().__init_subclass__(**kwargs)
		if parameters is not None:
			cls.parameters = parameters
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
			result = self.run(
				*context.args,
				**context.kwargs,
			)
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
