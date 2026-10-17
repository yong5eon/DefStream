from .Event import (
	Event,
	EventError,
)

__all__ = (
	'Requeue',
	'Reject',
)


class Requeue(EventError):
	def __call__(
		self,
		event: Event,
	) -> None:
		event.nack()


class Reject(EventError):
	def __call__(
		self,
		event: Event,
	) -> None:
		event.reject()
