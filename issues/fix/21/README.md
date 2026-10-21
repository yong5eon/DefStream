# Validator 패턴 이름을 `IsOptional`로 변경

## 변경 요약

Validator 패턴의 이름을 `IsToNone`에서 `IsOptional`로 변경했습니다.
`None` 입력은 그대로 반환하고, 그 외 입력에는 지정한 패턴을 순서대로 적용합니다.
처리 동작은 달라지지 않았으며 이름만 더 알아보기 쉽게 바뀌었습니다.

## 기존 코드에서 바꿀 부분

기존 `IsToNone` import와 사용 코드를 `IsOptional`로 변경하세요.
`IsToNone`은 호환 별칭으로 제공되지 않습니다.

변경 전:

```python
from DefStream.Validator.Patterns import IsToNone

validator = IsToNone(pattern)
```

변경 후:

```python
from DefStream.Validator.Patterns import IsOptional

validator = IsOptional(pattern)
```

`IsOptional`은 Python의 `typing.Optional`이 아니라 런타임 입력값을 처리하는
Validator 패턴입니다.

## 검증

- `None` 입력 시 후속 패턴을 실행하지 않고 `None` 반환
- 비`None` 입력 시 후속 패턴을 순서대로 실행
- 후속 패턴의 예외 전파 및 `repr` 결과 확인
- 패키지 공개 export와 기존 이름 미노출 확인
- 신규 단위 테스트 5개 통과

## 상세 기록

- [요구사항 명세서](./REQUIREMENTS.md)
- [구현 및 검증 기록](./IMPLEMENTS.md)
