from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import (
	Any,
	Optional,
	Union,
)
from DefStream.Broker import validate_priority

__all__ = (
	'Subscription',
)


@dataclass(frozen=True)
class Subscription:
	queue: str
	offset: Optional[int] = None
	qos: Optional[int] = None
	error: Optional[str] = None
	max_priority: Optional[int] = None
	priority: Optional[int] = None
	timeout: Optional[Union[int, timedelta]] = None

	def __post_init__(self) -> None:
		if self.timeout is not None:
			if isinstance(self.timeout, timedelta):
				if self.timeout <= timedelta(0) or self.timeout.microseconds % 1000:
					raise ValueError('Subscription timeout must be positive with whole-millisecond precision')
				object.__setattr__(
					self,
					'timeout',
					self.timeout // timedelta(milliseconds=1),
				)
			elif isinstance(self.timeout, bool) or not isinstance(self.timeout, int):
				raise TypeError('Subscription timeout must be integer milliseconds, a timedelta or None')
			elif self.timeout <= 0:
				raise ValueError('Subscription timeout must be positive')
		if self.priority is not None and self.max_priority is None:
			object.__setattr__(
				self,
				'max_priority',
				255,
			)
		validate_priority(
			self.max_priority,
			255,
			minimum=1,
			name='max_priority',
		)
		self.validate_priority(self.priority)
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
		return

	def validate_priority(
		self,
		priority: Optional[int],
	) -> None:
		validate_priority(
			priority,
			255 if self.max_priority is None else self.max_priority,
		)
		return

	@classmethod
	def parse(cls, parameters: Any) -> 'Subscription':
		if isinstance(parameters, cls):
			return parameters
		if isinstance(parameters, Mapping):
			return cls(**dict(parameters))
		raise TypeError('RabbitMQ subscriptions require a Subscription or mapping')
