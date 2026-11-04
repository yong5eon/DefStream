# 연결 타이머 등록과 취소

## 추가된 기능

RabbitMQ 연결에서 `set_timer(cb, seconds)`로 일회성 콜백을 예약하고,
반환된 `Timer`의 `remove()`로 취소할 수 있습니다.
호출자는 Pika 연결이나 내부 타이머 ID를 직접 다루지 않아도 됩니다.

`SetTimer`는 연결의 선택적 기능이며, `Timer`, `TimerCallback`과 함께
`DefStream.Broker` 및 `DefStream.Broker.Connection`에서 import할 수 있습니다.
반복 실행은 콜백에서 다음 타이머를 등록하는 방식으로 구성합니다.

[실행 가능한 타이머 샘플](../../../samples/Broker/RabbitMQ/Sample.Timer.py)에서
취소와 재등록을 확인할 수 있습니다. 기존 Stream 샘플의 소비 중단도
외부 스레드 타이머 대신 연결 타이머를 사용합니다.

## 사용 조건

- 지연 시간은 등록 시점부터 정수 초 단위로 지정합니다.
- RabbitMQ 소비 루프 등 Pika의 이벤트 처리가 진행되어야 콜백이 실행됩니다.
- 등록·취소는 연결 소유 스레드에서 수행하며, 긴 이벤트 처리로 실행이 지연될 수 있습니다.
- Consumer 종료 시 예약을 자동 취소하지 않습니다. 취소 시점과 연결의 사용 순서는 호출자가 관리합니다.
- 중복 취소·종료된 연결·음수·0초 등의 동작과 오류는 기반 Pika API를 따릅니다.
- Redis 타이머 지원이나 기존 Consumer·Worker API 변경은 포함하지 않습니다.

자세한 사용법은 [RabbitMQ 연결 타이머 안내](../../../docs/RabbitMQ.md#연결-타이머)를 참고하세요.
