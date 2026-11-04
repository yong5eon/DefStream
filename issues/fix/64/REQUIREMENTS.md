# RabbitMQ Consumer의 Recoverable 명시적 상속 요구사항

## 목적

RabbitMQ Consumer가 이미 제공하는 복구 가능 오류 분류 계약을 클래스 선언에 명시한다. 기능 오류를 수정하거나 복구 동작을 변경하는 작업이 아니다.

원문과 작업 정보는 [이슈 기록](./README.md)을 기준으로 한다.

## 변경 전 분석 근거

- [RabbitMQ Consumer](../../../src/Broker/Implements/RabbitMQ/Consumer.py)는 `BaseConsumer`만 상속하지만 `is_recoverable(self, error: BaseException) -> bool`을 구현한다.
- [Recoverable](../../../src/Broker/Protocol.py)은 `@runtime_checkable`이 적용된 Protocol이다. 명시적 상속 없이도 현재 Consumer의 `issubclass`와 인스턴스의 `isinstance` 판별은 성공한다.
- [기존 계약 테스트](../../../tests/test_protocol_contracts.py)는 구조적 판별과 공통 Consumer·Redis Consumer의 비지원 여부를 검증하지만, RabbitMQ Consumer의 직접 상속 여부는 검증하지 않는다.
- [Worker](../../../src/Worker/Worker.py)는 `isinstance(consumer, Recoverable)`와 `is_recoverable(error)`로 복구 여부를 결정한다. 이번 요청을 충족하기 위해 해당 흐름을 변경할 필요는 없다.

따라서 import와 클래스 상속 선언을 변경하고, 명시적 상속 및 기존 동작을 직접 검증하는 범위가 적절하다.

## 범위

### 포함

- `src/Broker/Implements/RabbitMQ/Consumer.py`의 `Recoverable` import와 상속 선언
- 명시적 상속, 인스턴스 생성, 런타임 판별과 기존 오류 분류에 직접 관련된 테스트

### 제외

- `Recoverable` 정의나 공통 Consumer 인터페이스 변경
- Redis Consumer 및 다른 Protocol의 상속 관계 변경
- Worker·Executor의 복구 흐름 변경과 리팩터링
- 타이머 지원, 재시도 정책 및 새로운 복구 기능 추가

## 확정 요구사항

| ID | 요구사항 | 근거 |
| --- | --- | --- |
| R1 | RabbitMQ Consumer에 `Recoverable`을 import하고 클래스 선언을 `Consumer(BaseConsumer, Recoverable)`로 변경한다. | 원문의 제안 및 완료 기준 |
| R2 | 기존 생성자 시그니처와 정상적인 인스턴스 생성 동작을 유지한다. | 원문의 기존 Consumer 생성 유지 |
| R3 | `is_recoverable(self, error: BaseException) -> bool`의 시그니처, 구현과 오류 분류 결과를 유지한다. | 원문의 기존 구현 및 오류 분류 유지 |
| R4 | RabbitMQ Consumer 인스턴스의 `isinstance(consumer, Recoverable)` 판별을 유지한다. 다른 구조적 구현체의 지원과 공통 Consumer·Redis Consumer의 비지원도 유지한다. | 원문의 런타임 판별 유지 및 기존 계약 테스트 |
| R5 | 직접 상속 여부를 검증하여 구조적 판별만으로 요구사항 충족을 판단하지 않는다. | 원문의 명시적 상속 완료 기준 |

## 호환성과 제약

- 공개 import 경로, 메서드 시그니처와 기존 사용 방법을 유지한다.
- 인증·권한 오류, 연결·채널 종료, ACK 시간 초과와 콜백 오류의 기존 분류를 바꾸지 않는다.
- Protocol의 구조적 타입 지원을 명시적 상속 전용으로 제한하지 않는다.
- 새로운 설정, 의존성, 호환성 계층이나 운영 전환 절차를 추가하지 않는다.

## 인수 기준

| 기준 | 검증 방법 | 대응 요구사항 |
| --- | --- | --- |
| 클래스 선언이 `Consumer(BaseConsumer, Recoverable)`이고 `Recoverable`이 직접 부모에 포함된다. | 선언 확인 및 `Recoverable in RabbitConsumer.__bases__` 검증 | R1, R5 |
| Consumer가 추상 클래스가 되지 않고 기존 인자로 생성된다. | 기존 Mock 연결을 사용하는 생성 검증 | R2 |
| 생성된 Consumer의 `isinstance(consumer, Recoverable)`가 `True`이다. | 실제 생성 인스턴스의 런타임 판별 | R4 |
| 기존 구조적 구현체는 계속 인식되고 공통 Consumer·Redis Consumer는 비지원 상태를 유지한다. | 기존 Protocol 계약 테스트 | R4 |
| 기존 복구 가능·불가능 오류 분류와 콜백 오류 제외 동작을 유지한다. | 기존 RabbitMQ 오류 분류 및 ACK 시간 초과 관련 테스트 | R3 |

## 현재 상태

구현과 인수 기준 검증을 완료했다. 실제 소스 변경 후 관련 테스트 14개가 통과했으며 이전 분석의 메모리상 검증과 구분했다. 결과와 검증 범위는 [구현 결과](./IMPLEMENTS.md) 및 [작업 결과](./TASKS.md)를 따른다.

현재 요구사항 확정에 필요한 미확정 사항은 없다.
