# Run 에 이름(name)과 설명(description) 지원

## 1. 목적

Run을 정의할 때 이름과 설명을 선택적으로 지정할 수 있도록 한다. 지정한
이름을 AsyncAPI `operations`의 키와 Metrics의 작업 키로 공통 사용하며,
이름을 지정하지 않으면 `모듈.클래스명`을 사용한다. 설명은 AsyncAPI Operation에
반영한다. `Specification`에서는 `description`을 제거한다.

본 문서는 구현 전 요구사항 명세이다.

## 2. 범위

### 포함

- Run 정의 시 선택적 `name` 및 `description` 지정.
- Run별 유효 이름 결정 및 AsyncAPI와 Metrics에서의 일관된 사용.
- 이름의 입력 검증, 충돌 처리, 기본 이름과 기존 동작의 호환성 검증.
- `Specification`에서 `description` 제거 및 설명의 Run 단위 관리.

### 제외

- AsyncAPI 채널 주소, 메시지 키·이름 또는 payload 변경.
- Metrics 집계 방식, 지표 이름, 기간 및 응답 형식 변경.
- Run의 실행·검증·메시지 처리 방식 변경.

## 3. 용어 및 현재 동작

| 용어 | 의미 |
|---|---|
| Run 이름 | Run 정의에 선택적으로 지정하는 사용자 제공 식별자 |
| 유효 Run 이름 | AsyncAPI와 Metrics에서 해당 Run을 식별하는 공통 문자열 |
| 기본 이름 | 명시적 이름이 없을 때 사용하는 `Run.__module__ + '.' + Run.__qualname__` |
| Run 설명 | Run 정의에 선택적으로 지정하여 AsyncAPI Operation에 반영하는 문자열 |

- AsyncAPI `operations`의 현재 키는 Run 클래스의 `__name__`이다.
- Metrics의 현재 작업 키는 Run 클래스의 `__module__`과 `__qualname__`을
  결합한 값이다.
- 변경 후에는 AsyncAPI와 Metrics가 모두 동일한 유효 Run 이름을 사용한다.
- 현재 `Specification`은 `description`을 받아 메시지 및 Operation 설명에
  활용한다. 변경 후 설명은 Run 정의에서 관리하고 Specification에는 두지 않는다.

## 4. 기능 요구사항

| ID | 요구사항 |
|---|---|
| SPECNAME-01 | Run 정의 시 선택적 `name`을 지정할 수 있어야 한다. 지정하지 않은 경우의 기본값은 미지정 상태여야 한다. |
| SPECNAME-02 | Run 정의 시 선택적 `description`을 지정할 수 있어야 한다. 지정하지 않은 경우 설명은 없어야 한다. |
| SPECNAME-03 | `name`은 Python 문법상 유효한 식별자여야 하며 예약어는 허용하지 않는다. 이름을 자동 정규화하거나 변경하지 않는다. 잘못된 타입은 `TypeError`, 유효하지 않은 식별자나 예약어는 `ValueError`로 거부한다. |
| SPECNAME-04 | `description`은 문자열 또는 `None`이어야 한다. 다른 타입은 `TypeError`로 명확히 거부한다. 빈 설명 문자열은 그대로 보존한다. |
| SPECNAME-05 | 이름이 지정되지 않은 Run의 유효 이름은 `Run.__module__ + '.' + Run.__qualname__`이어야 한다. 중첩 클래스도 `__qualname__`을 포함해야 한다. |
| SPECNAME-06 | AsyncAPI 문서의 `operations` 객체에서 각 Run의 키로 유효 Run 이름을 사용해야 한다. 이 요구사항은 Operation 객체의 별도 필드가 아니라 `operations` 맵의 키에 적용한다. |
| SPECNAME-07 | Run의 `description`이 지정된 경우 AsyncAPI Operation의 `description`으로 사용해야 한다. 지정하지 않은 경우 해당 필드는 생성하지 않는다. |
| SPECNAME-08 | `Specification` 생성자는 `description` 인자를 더 이상 받지 않아야 한다. 기존 description positional 인자에 의존하는 호출은 Run의 `description`으로 이전해야 하며, 제거된 인자를 전달하면 기존 Python 호출 규칙에 따라 명확히 실패해야 한다. |
| SPECNAME-09 | Metrics의 작업 저장 키와 해당 작업을 식별하는 출력 키·레이블은 유효 Run 이름을 사용해야 한다. Metrics 집계 내용과 지표 구조는 변경하지 않는다. |
| SPECNAME-10 | 서로 다른 Run이 같은 유효 이름을 가지면 Run 등록 시와 AsyncAPI 문서 생성 시 충돌을 감지해야 한다. 데이터가 조용히 덮어써지거나 합쳐지지 않도록 원인을 알 수 있는 예외로 거부한다. |
| SPECNAME-11 | Run에 이름을 지정하지 않은 경우 AsyncAPI와 Metrics 모두 같은 `모듈.클래스명` 기본 이름을 사용해야 한다. 이는 기존 AsyncAPI의 클래스명 단독 키를 qualified 이름으로 바꾸는 의도된 호환성 변경이다. |
| SPECNAME-12 | Run의 `name`과 `description`은 해당 Run 정의에 적용하며, 하위 Run 정의가 값을 지정하지 않으면 상위 Run의 메타데이터를 상속하지 않는다. 이름 미지정 하위 Run은 자체 모듈·클래스명으로 식별되고 설명도 미지정 상태가 된다. |

## 5. 동작 보장 및 호환성

- 사용자 지정 이름은 AsyncAPI와 Metrics에서 동일한 문자열로 사용한다.
- 이름은 AsyncAPI Operation의 키와 Metrics 작업 식별자에만 적용한다.
  채널 주소, request/response 메시지 이름과 payload 구성은 기존 규칙을 유지한다.
- 설명은 AsyncAPI Operation에만 적용한다. request/response 메시지 설명은
  Specification에서 제거되며, 이번 변경에서 별도 대체 메타데이터를 추가하지 않는다.
- 이름이 없는 Run의 Metrics 키 형식은 기존과 같다. AsyncAPI 키는 기존의
  클래스명 단독 형식에서 `모듈.클래스명` 형식으로 변경된다.
- 이름 및 설명 지정 여부와 관계없이 Specification의 schema, validator,
  example, format 검증 및 payload 문서화 동작을 유지한다. 단,
  Specification의 `description`은 의도적으로 제거한다.
- 중복 이름을 허용하지 않는 기존 AsyncAPI 동작을 보존하고, Metrics에서도
  이름 중복으로 작업 데이터가 유실되지 않도록 한다.

## 6. 인수 기준

| ID | 검증 시나리오 및 기대 결과 |
|---|---|
| WAT-01 | `Run` 정의에 `name='orders'`를 지정하면 AsyncAPI `operations`와 Metrics에서 `orders` 키로 식별된다. |
| WAT-02 | 이름을 지정하지 않은 모듈 최상위 Run의 AsyncAPI 키와 Metrics 키가 모두 `모듈명.클래스명`이다. |
| WAT-03 | 이름을 지정하지 않은 중첩 Run의 기본 이름에 모듈명과 중첩 경로를 포함한 `__qualname__`이 반영된다. |
| WAT-04 | `name`이 Python 문법상 식별자가 아니거나 예약어이거나 문자열이 아니면 각각 `ValueError` 또는 `TypeError`가 발생한다. |
| WAT-05 | `description`이 문자열이면 AsyncAPI Operation 설명에 반영되고, `None`이면 Operation에 설명 필드가 없다. |
| WAT-06 | `description`에 문자열 또는 `None` 이외의 값을 전달하면 `TypeError`가 발생한다. |
| WAT-07 | 두 Run에 같은 사용자 지정 이름을 지정하면 Run 등록 시 충돌을 감지하고, 문서 생성에서도 충돌을 검증한다. 기존 항목을 덮어쓰거나 통계를 합치지 않는다. |
| WAT-08 | Run의 하위 클래스가 이름과 설명을 재지정하지 않으면 상위 값이 상속되지 않는다. 하위 Run은 자신의 기본 이름을 사용하고 설명은 미지정으로 남는다. |
| WAT-09 | `Specification(description=...)` 호출은 지원되지 않으며, 이를 사용하는 기존 코드는 Run의 설명 지정 방식으로 이전해야 한다. |
| WAT-10 | 채널 주소, request/response 메시지 키, payload, Metrics 집계값이 이름 지정 전후 기존 계약을 유지한다. |
