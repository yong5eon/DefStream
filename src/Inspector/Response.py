from dataclasses import dataclass

__all__ = (
	'Response',
)


@dataclass
class Response:
	status: str
	body: bytes
	content_type: str
