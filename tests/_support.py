from collections.abc import Callable
from typing import (
	Optional,
	TypeVar,
)

T = TypeVar('T')


def call_with_invalid_input(
	target: Callable[..., T],
	*args: object,
	**kwargs: object,
) -> T:
	"""Call an API with deliberately invalid values for runtime validation tests."""
	return target(*args, **kwargs)


def require_value(
	value: Optional[T],
) -> T:
	if value is None:
		raise AssertionError('Expected a value')
	return value


def require_instance(
	value: object,
	expected_type: type[T],
) -> T:
	if not isinstance(value, expected_type):
		raise AssertionError(
			'Expected an instance of {}'.format(expected_type.__name__),
		)
	return value
