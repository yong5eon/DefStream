from abc import abstractmethod
from typing import (
	Any,
	Protocol,
)

__all__ = (
	'Event',
	'EventHandler',
	'EventErrorPolicy',
)


class Event(Protocol):
	@property
	def body(self) -> Any: ...

	def ack(self) -> None: ...
	def nack(self) -> None: ...
	def reject(self) -> None: ...


class EventHandler(Protocol):
	@abstractmethod
	def __call__(
		self,
		event: Event,
	) -> None: ...


class EventErrorPolicy(Protocol):
	def __call__(
		self,
		event: Event,
	) -> None: ...
