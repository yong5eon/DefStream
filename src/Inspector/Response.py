from dataclasses import dataclass
from typing import Tuple

__all__ = (
	'Response',
)


@dataclass
class Response:
	status: str
	body: bytes
	content_type: str
	headers: Tuple[Tuple[str, str], ...] = ()
