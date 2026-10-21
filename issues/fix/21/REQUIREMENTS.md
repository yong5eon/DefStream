# Validator의 `IsToNone`을 `IsOptional`로 변경

## 1. 목적

Validator 패턴 `IsToNone`의 이름을 `IsOptional`로 변경한다. 이름만으로
`None` 값을 허용하는 패턴임을 알아보기 쉽게 하며, 값의 처리 동작은 유지한다.

본 문서는 구현 전 요구사항 명세이다.

## 2. 범위

### 포함

- 패턴 클래스 이름을 `IsToNone`에서 `IsOptional`로 변경.
- 모듈 및 패키지 공개 export에 새 이름 반영.
- 기존 `None` 및 비`None` 값 처리와 후속 패턴 실행 동작 유지.
- 기존 이름을 제거하고 새 이름으로 이전하는 호환성 정책 명시.

### 제외

- 패턴의 검증, 변환, 예외 처리 동작 변경.
- `typing.Optional` 등 Python 타입 힌트 기능과의 통합.
- 다른 Validator 패턴의 이름이나 동작 변경.

## 3. 용어 및 현재 동작

| 용어 | 의미 |
|---|---|
| 선택적 값 | `None` 또는 지정된 패턴으로 처리할 값 |
| 후속 패턴 | `IsOptional`에 전달되어 비`None` 값에 순서대로 적용되는 패턴 |
| 공개 export | `Validator.Patterns` 패키지에서 import할 수 있도록 노출하는 이름 |

- 현재 `IsToNone`은 입력값이 `None`이면 그대로 반환한다.
- 입력값이 `None`이 아니면 생성 시 전달된 패턴을 순서대로 적용한 뒤 결과를 반환한다.
- 이 클래스는 Python의 `typing.Optional` 타입 별칭이 아니라 런타임 값 처리용 Validator 패턴이다.

## 4. 기능 요구사항

| ID | 요구사항 |
|---|---|
| ISOPT-01 | 패턴 클래스의 이름은 `IsOptional`이어야 한다. |
| ISOPT-02 | `IsOptional`은 가변 개수의 후속 패턴을 받을 수 있어야 한다. |
| ISOPT-03 | 입력값이 `None`이면 후속 패턴을 실행하지 않고 `None`을 반환해야 한다. |
| ISOPT-04 | 입력값이 `None`이 아니면 후속 패턴을 전달된 순서대로 적용하고 마지막 결과를 반환해야 한다. |
| ISOPT-05 | 후속 패턴에서 발생한 예외는 기존과 같이 호출자에게 전파해야 한다. |
| ISOPT-06 | `IsOptional`은 `Validator.Patterns.Common` 모듈과 `Validator.Patterns` 패키지에서 공개 import 가능해야 한다. 각 모듈의 `__all__`에도 새 이름을 포함해야 한다. |
| ISOPT-07 | 기존 이름 `IsToNone`은 클래스 이름, 공개 export 또는 호환 별칭으로 제공하지 않아야 한다. 기존 이름을 사용하는 코드는 `IsOptional`로 이전해야 한다. |
| ISOPT-08 | `repr` 결과의 클래스명 부분은 `IsOptional`이어야 하며, 전달된 후속 패턴의 표현은 기존과 동일한 형식으로 표시해야 한다. |

## 5. 동작 및 호환성

- 이번 변경은 이름 변경이며, 입력값 처리 결과와 후속 패턴의 실행 순서는 바꾸지 않는다.
- `IsToNone`에서 `IsOptional`로의 변경은 공개 API의 호환성을 깨는 변경이다.
  기존 이름을 사용하는 import와 호출 코드는 새 이름으로 수정해야 한다.
- `None` 허용 여부 외에 형식 검사, 기본값 처리 또는 값 변환을 새로 추가하지 않는다.
- `typing.Optional`과는 별개의 런타임 Validator 패턴으로 유지한다.

## 6. 인수 기준

| ID | 검증 시나리오 및 기대 결과 |
|---|---|
| WAT-01 | `Validator.Patterns.Common`에서 `IsOptional`을 import할 수 있다. |
| WAT-02 | `Validator.Patterns`에서 `IsOptional`을 import할 수 있고, 두 모듈의 `__all__`에 `IsOptional`이 포함되어 있다. |
| WAT-03 | `IsOptional(pattern)(None)`은 `None`을 반환하며 `pattern`은 호출되지 않는다. |
| WAT-04 | 비`None` 입력은 전달된 모든 패턴에 순서대로 전달되고 마지막 패턴의 반환값이 결과가 된다. |
| WAT-05 | 후속 패턴이 예외를 발생시키면 해당 예외가 호출자에게 전파된다. |
| WAT-06 | `repr(IsOptional(...))`의 결과는 `IsOptional`을 이름으로 표시한다. |
| WAT-07 | `IsToNone`은 해당 모듈 또는 패키지의 공개 API로 import할 수 없으며, `IsOptional` 별칭으로도 제공되지 않는다. |
