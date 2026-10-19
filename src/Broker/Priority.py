from typing import Optional


def validate_priority(
	value: Optional[int],
	maximum: Optional[int],
	*,
	minimum: int = 0,
	name: str = 'priority',
) -> None:
	"""우선순위 타입과 범위를 검증하며, 최대값이 없으면 하한만 검사한다."""
	if value is None:
		return
	if isinstance(
		value,
		bool,
	) or not isinstance(
		value,
		int,
	):
		raise TypeError(name + ' must be an integer or None')
	if value < minimum:
		raise ValueError(f'{name} must be at least {minimum}')
	if maximum is not None and value > maximum:
		raise ValueError(f'{name} must be between {minimum} and {maximum}')
	return
