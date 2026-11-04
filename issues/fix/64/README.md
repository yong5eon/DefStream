# RabbitMQ Consumer의 Recoverable 명시적 상속

- 원본: [DefStream #64](https://github.com/yong5eon/DefStream/issues/64)
- 유형·레이블: `fix` (원본 적용 확인)
- 대상 저장소: DefStream
- 작업 브랜치: `fix/64`
- 분기 기준: `master`
- 상태: 이슈 원문 기록 완료, 요구사항 분석과 구현은 미착수

## 원본 이슈 본문

```text
## 변경 유형

일반 변경

## 변경 목적

RabbitMQ Consumer는 `is_recoverable(error)`를 구현하고 있지만 클래스 선언에는 `BaseConsumer`만 명시되어 있습니다.

`Recoverable`은 `@runtime_checkable`이 적용된 Protocol이므로 현재도 구조적 타입으로 인식됩니다. 기능 오류를 수정하려는 것이 아니라 클래스 선언에서 지원 계약을 명확히 드러내려는 변경입니다.

## 제안하는 변경 내용

- RabbitMQ Consumer가 `Recoverable`을 명시적으로 상속하도록 선언합니다.
- 기존 `is_recoverable` 구현과 오류 분류 동작은 유지합니다.

## 영향 범위

`src/Broker/Implements/RabbitMQ/Consumer.py`의 import와 상속 선언 및 직접 관련된 검증으로 한정합니다. 다른 프로토콜이나 Consumer 인터페이스, Worker·Executor의 리팩터링으로 범위를 확대하지 않습니다.

## 완료 기준

- 클래스 선언에 `Consumer(BaseConsumer, Recoverable)`이 명시됩니다.
- 기존 Consumer 생성과 `isinstance(consumer, Recoverable)` 판별 및 복구 가능 오류 분류가 유지됩니다.

## 관련 이슈

- 타이머 지원과 별도 진행: https://github.com/yong5eon/DefStream/issues/62
- 워커 리팩토링과 별도 진행: https://github.com/yong5eon/DefStream/issues/63
```
