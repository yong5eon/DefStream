# -*- coding: utf-8 -*-

from abc import (
	ABCMeta,
	abstractmethod,
)
from typing import (
	Any,
	Callable,
	Optional,
)

from .Event import (
	Event,
	EventHandler,
	EventError,
)

__all__ = (
	'Consumer'
)


class Consumer(metaclass=ABCMeta):
	"""Consumer Interface of Event Broker"""
	def complete(
		self,
		event: Event,
		result: Any,
	) -> None:
		event.ack()

	def call(self, callback: Callable[[], None]) -> None:
		"""Schedule a callback on the connection owner thread."""
		raise NotImplementedError('Consumer must implement thread-safe callback scheduling')

	def fail(
		self,
		event: Event,
		policy: Optional[EventError] = None,
	) -> None:
		raise NotImplementedError('Consumer must implement failure policies')

	def close(self) -> None:
		raise NotImplementedError('Consumer must implement close')

	@abstractmethod
	def subs(
		self,
		queue: Any,
		handler: Optional[EventHandler] = None,
	) -> None:
		raise NotImplementedError('{} must implement subs'.format(self.__class__.__name__))
	@abstractmethod
	def run(self):
		raise NotImplementedError('{} must be implemented run'.format(self.__class__.__name__))
	@abstractmethod
	def stop(self):
		raise NotImplementedError('{} must be implemented stop'.format(self.__class__.__name__))
