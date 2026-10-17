from collections.abc import Mapping
from dataclasses import dataclass
from typing import (
	Any,
	Optional,
)

__all__ = (
	'Subscription',
)


@dataclass(frozen=True)
class Subscription:
	queue: str
	offset: Optional[int] = None
	qos: Optional[int] = None
	error: Optional[str] = None

	def __post_init__(self):
		if not isinstance(self.queue, str) or not self.queue:
			raise ValueError('Subscription queue must be a non-empty string')
		if self.error is not None:
			if not isinstance(
				self.error,
				str,
			) or not self.error:
				raise ValueError('Subscription error must be a non-empty string or None')
		if self.offset is not None and (isinstance(self.offset, bool) or not isinstance(self.offset, int)):
			raise ValueError('Subscription offset must be an integer')
		if self.qos is not None:
			if isinstance(
				self.qos,
				bool,
			) or not isinstance(
				self.qos,
				int,
			) or not 0 <= self.qos <= 65535:
				raise ValueError('Subscription qos must be an integer between 0 and 65535')

	@classmethod
	def parse(cls, parameters: Any) -> 'Subscription':
		if isinstance(parameters, cls):
			return parameters
		if isinstance(parameters, Mapping):
			return cls(**dict(parameters))
		raise TypeError('RabbitMQ subscriptions require a Subscription or mapping')
