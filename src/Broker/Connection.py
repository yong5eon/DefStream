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
