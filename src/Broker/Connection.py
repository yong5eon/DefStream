# -*- coding: utf-8 -*-

from abc import abstractmethod
from typing import (
	Any,
	Optional,
	Protocol,
	runtime_checkable,
)

from .Consumer import Consumer
from .Event import EventHandler
from .Protocol import Sendable

__all__ = (
	'Connection',
	'GetExchange',
	'GetQueue',
	'GetStream',
	'GetConsumer',
	'Declarable',
	'TaskSender',
	'Requestable',
	'PrioritySupport',
)


class Connection(Protocol):
	@abstractmethod
	def connect(self) -> None: ...

	@abstractmethod
	def close(self) -> None: ...


class GetExchange(Protocol):
	@abstractmethod
	def exchange(
		self,
		name: str,
		/,
	) -> Sendable: ...


class GetQueue(Protocol):
	@abstractmethod
	def queue(
		self,
		name: str,
		/,
	) -> Sendable: ...


class GetStream(Protocol):
	@abstractmethod
	def stream(
		self,
		name: str,
		/,
	) -> Sendable: ...


class GetConsumer(Protocol):
	@abstractmethod
	def consumer(
		self,
		handler: Optional[EventHandler] = None,
	) -> Consumer: ...


@runtime_checkable
class Declarable(Protocol):
	@abstractmethod
	def declare(
		self,
		parameters: Any,
	) -> None: ...


@runtime_checkable
class TaskSender(Protocol):
	@abstractmethod
	def send(
		self,
		body: Any,
		parameters: Any,
	) -> Any: ...


@runtime_checkable
class Requestable(Protocol):
	@abstractmethod
	def request(
		self,
		body: Any,
		parameters: Any,
		timeout: float = 5,
	) -> Any: ...


@runtime_checkable
class PrioritySupport(Protocol):
	"""작업 구독 설정의 우선순위 처리와 우선순위 발행을 지원하는 계약."""

	def priority_parameters(
		self,
		parameters: Any,
	) -> Any: ...

	def send(
		self,
		body: Any,
		parameters: Any,
		*,
		priority: Optional[int] = None,
	) -> Any: ...

	def request(
		self,
		body: Any,
		parameters: Any,
		timeout: float = 5,
		*,
		priority: Optional[int] = None,
	) -> Any: ...
