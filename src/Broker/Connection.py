# -*- coding: utf-8 -*-

from abc import abstractmethod
from typing import (
	Optional,
	Protocol,
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
