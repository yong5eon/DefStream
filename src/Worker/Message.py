from collections.abc import Mapping
from inspect import isabstract
from typing import (
	Any,
	Type,
)

from ..Broker.Connection import (
	Declarable,
	TaskSender,
	Requestable,
)
from .Run import Run

__all__ = (
	'declare',
	'send',
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


def declare(
	*,
	task: Type[Run],
	broker: Declarable,
) -> None:
	parameters = task_parameters(task)
	if not isinstance(
		broker,
		Declarable,
	):
		raise NotImplementedError('This connection does not support task declarations')
	broker.declare(parameters)


def send(
	body: Mapping,
	*,
	task: Type[Run],
	broker: TaskSender,
) -> Any:
	parameters = task_parameters(task)
	payload = message_body(body)
	if not isinstance(
		broker,
		TaskSender,
	):
		raise NotImplementedError('This connection does not support task sending')
	return broker.send(
		payload,
		parameters,
	)


def request(
	body: Mapping,
	*,
	task: Type[Run],
	broker: TaskSender,
	timeout: float = 5,
) -> Any:
	parameters = task_parameters(task)
	payload = message_body(body)
	if not isinstance(
		broker,
		Requestable,
	):
		raise NotImplementedError('This connection does not support task RPC requests')
	return broker.request(
		payload,
		parameters,
		timeout=timeout,
	)
