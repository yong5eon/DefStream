from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = (
	'Subscription',
)


@dataclass(frozen=True)
class Subscription:
	queue: str
	group: str = 'stream'

	def __post_init__(self) -> None:
		for value in (
			self.queue,
			self.group,
		):
			if not isinstance(
				value,
				str,
			) or not value:
				raise ValueError('Redis queue and group must be non-empty strings')

	@classmethod
	def parse(
		cls,
		parameters: Any,
	) -> 'Subscription':
		if isinstance(
			parameters,
			cls,
		):
			return parameters
		if isinstance(
			parameters,
			str,
		):
			return cls(parameters)
		if isinstance(
			parameters,
			Mapping,
		):
			return cls(**dict(parameters))
		raise TypeError('Redis subscriptions require a queue name, Subscription or mapping')
