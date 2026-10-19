# 워커 작업 우선순위 지원

## 변경 전 (AS-IS)

작업을 대상으로 하는 `declare`, `send`, `request`에서는 큐의 우선순위 설정과
메시지 우선순위를 지정할 수 없었습니다.

## 변경 후 (TO-BE)

지원 브로커의 작업 구독 설정에 기본·최대 우선순위를 정의하고, `emit`과 `request`에서
메시지별 우선순위를 재정의할 수 있습니다. 현재 지원 브로커는 RabbitMQ입니다.

## 사용 방법

RabbitMQ 작업의 `parameters`에 `Subscription(priority=2, max_priority=5, ...)`를
지정하세요. 기본값은 `Run`의 별도 속성이 아니라 구독 설정에 정의합니다.
호출자가 연결한 `broker`와 구체적인 작업 클래스 `Add`를 사용해 다음처럼 호출합니다.

```python
from DefStream.Worker import (
  declare,
  request,
  emit,
)


# 작업 구독 설정을 읽어 큐를 준비합니다.
declare(
  task=Add,
  broker=broker,
)

# 호출값을 생략하면 작업 구독의 기본 우선순위를 사용합니다.
emit(
  {'a': 1, 'b': 2},
  task=Add,
  broker=broker,
)

# RPC 요청도 호출별 우선순위를 지정할 수 있습니다.
result = request(
  {'a': 1, 'b': 2},
  task=Add,
  broker=broker,
  priority=5,
)
```

RPC 결과를 받으려면 해당 작업을 처리하는 Worker가 실행 중이어야 합니다.
전체 작업 정의와 큐 전환 방법은
[RabbitMQ 우선순위 사용 안내](https://github.com/yong5eon/DefStream-RabbitMQ/blob/master/issues/feature/1/README.md)를 참고하세요.

## 기존 코드에 미치는 영향

- 우선순위를 지정하지 않은 기존 호출은 그대로 사용할 수 있습니다.
- 호출값 생략 또는 `None`은 작업 기본값을 사용하며, `0`은 명시적인 재정의입니다.
- 기본값만 지정하면 RabbitMQ 큐 최대값은 `255`입니다. 최대값만 지정하고
  호출값도 없으면 메시지 우선순위 속성을 생략합니다.
- 잘못된 타입이나 범위는 선언·발행 전에 오류로 처리합니다.
  작업 설정 없이 호출에서만 지정하는 경우에는 브로커 허용 범위만 검증하므로,
  실제 우선순위 큐의 사전 선언은 호출자가 보장해야 합니다.
- 자식 작업에서 구독 설정을 교체한다면 부모의 기본·최대 우선순위도 새 설정에
  명시해야 합니다. 유효한 값으로 재정의할 수 있지만 해제할 수는 없습니다.
- Redis는 우선순위를 지원하지 않습니다. Redis에 우선순위를 요청하면
  `NotImplementedError`가 발생하며, 미지정 시에는 기존 동작을 유지합니다.
- 우선순위는 같은 큐의 대기 메시지 전달에만 적용되며, 실행 중 작업의 선점이나
  전역 실행·완료 순서를 보장하지 않습니다.

## 브로커 확장 개발자를 위한 공개 요소

공통 패키지에서 기존 인터페이스와 함께 `PrioritySupport`, `Requeue`, `Reject`,
`validate_priority`를 가져올 수 있습니다. 브로커 구현 시 공통 요소는
`from DefStream.Broker import ...`로 참조하세요.
기존 우선순위 미지원 브로커에 새 인자 구현을 강제하지 않습니다.
