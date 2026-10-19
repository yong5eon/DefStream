from collections.abc import Mapping
from inspect import isabstract
from typing import (
	Any,
	Optional,
	Type,
)

from ..Broker.Connection import (
	Connection,
	Declarable,
	Emittable,
	Requestable,
	PrioritySupport,
)
from .Run import (
	Run,
	priority_setting,
)

__all__ = (
	'declare',
	'emit',
	'request',
)


def task_parameters(
	task: Type[Run],
) -> Any:
	if not isinstance(
		task,
		type,
	) or not issubclass(
		task,
		Run,
	) or isabstract(task):
		raise TypeError('A concrete Run class is required')
	if task.parameters is None:
		raise ValueError('Run subscription parameters are required')
	return task.parameters


def message_body(
	body: Mapping,
) -> dict:
	if not isinstance(
		body,
		Mapping,
	) or not all(isinstance(
		key,
		str,
	) for key in body):
		raise TypeError('Task body must be a mapping with string keys')
	return dict(body)


def priority_parameters(
	broker: Connection,
	parameters: Any,
	priority: Optional[int],
) -> Any:
	if priority_setting(
		parameters,
		'priority',
	) is None and priority_setting(
		parameters,
		'max_priority',
	) is None and priority is None:
		return parameters
	if not isinstance(
		broker,
		PrioritySupport,
	):
		raise NotImplementedError('This connection does not support task priorities')
	return broker.priority_parameters(
		parameters,
	)


def declare(
	*,
	task: Type[Run],
	broker: Connection,
) -> None:
	parameters = task_parameters(task)
	if not isinstance(
		broker,
		Declarable,
	):
		raise NotImplementedError('This connection does not support task declarations')
	broker.declare(priority_parameters(
		broker,
		parameters,
		None,
	))
	return


def emit(
	body: Mapping,
	*,
	task: Type[Run],
	broker: Connection,
	priority: Optional[int] = None,
) -> Any:
	parameters = task_parameters(task)
	payload = message_body(body)
	if not isinstance(
		broker,
		Emittable,
	):
		raise NotImplementedError('This connection does not support task emission')
	parameters = priority_parameters(
		broker,
		parameters,
		priority,
	)
	effective = priority_setting(
		parameters,
		'priority',
	) if priority is None else priority
	if effective is not None:
		if not isinstance(
			broker,
			PrioritySupport,
		):
			raise NotImplementedError('This connection does not support task priorities')
		return broker.emit(
			payload,
			parameters,
			priority=effective,
		)
	return broker.emit(
		payload,
		parameters,
	)


def request(
	body: Mapping,
	*,
	task: Type[Run],
	broker: Connection,
	timeout: float = 5,
	priority: Optional[int] = None,
) -> Any:
	parameters = task_parameters(task)
	payload = message_body(body)
	if not isinstance(
		broker,
		Requestable,
	):
		raise NotImplementedError('This connection does not support task RPC requests')
	parameters = priority_parameters(
		broker,
		parameters,
		priority,
	)
	effective = priority_setting(
		parameters,
		'priority',
	) if priority is None else priority
	if effective is not None:
		if not isinstance(
			broker,
			PrioritySupport,
		):
			raise NotImplementedError('This connection does not support task priorities')
		return broker.request(
			payload,
			parameters,
			timeout=timeout,
			priority=effective,
		)
	return broker.request(
		payload,
		parameters,
		timeout=timeout,
	)
