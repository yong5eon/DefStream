# 연결 타이머 구현 결과

## 구현 내용

- [공통 연결 계약](../../../src/Broker/Connection.py)에 `Timer`, `TimerCallback`, `SetTimer`를 추가하고 [Broker 공개 진입점](../../../src/Broker/__init__.py)에서도 노출했다.
- `Timer`, `SetTimer`의 런타임 검사·추상 메서드 선언과 `set_timer(cb: TimerCallback, seconds: int) -> Timer` 시그니처를 확정 명세대로 구현했다.
- [RabbitMQ 연결](../../../src/Broker/Implements/RabbitMQ/Connection.py)은 `SetTimer`를 명시적으로 상속한다. 기존 연결 확인 후 즉시 `call_later(seconds, cb)`로 일회성 예약을 등록하므로 지연 시간은 등록 시점부터 계산된다.
- 반환하는 구체 `Timer`는 등록 당시 실제 연결과 불투명 핸들만 보관한다. `remove()`는 해당 연결의 `remove_timeout`에 직접 위임하여 상위 연결 객체가 재연결되어도 취소 대상이 바뀌지 않는다.
- 콜백 래퍼·스레드·추가 동기화·상태 검사·자동 정리 계층은 추가하지 않았다. 스레드 제약·취소·입력값·오류 동작은 Pika API를 따른다.
- 한국어·영어 [RabbitMQ 사용 안내](../../../docs/RabbitMQ.md)에 일회성·취소·재등록 예제와 사용 제약을 반영했다.
- 실행 가능한 [타이머 샘플](../../../samples/Broker/RabbitMQ/Sample.Timer.py)을 추가하고, [Stream 샘플](../../../samples/Broker/RabbitMQ/Sample.Stream.py)의 별도 스레드 타이머와 중계 함수를 연결의 `set_timer(consumer.stop, 1)`로 교체했다.

## 유지한 범위

Consumer·Worker·Ping·Pool·Executor·Event·Redis 구현과 연결·소비 종료 처리는 변경하지 않았다. 기본 Connection 계약에 타이머를 강제하지 않으며, 별도 이슈 #63·#64의 리팩터링을 포함하지 않았다.

## 검증과 제한

샘플 검증 추가 후 단위·회귀 45개가 통과했으며 실제 브로커 테스트 4개는 기본 실행에서 건너뛰었다. 별도 유휴 실행 테스트는 로컬 RabbitMQ 연결 실패로 동작 검증까지 진행하지 못했다. 타입·구문 진단과 사용 예제 검증 결과는 [작업 종합](./TASKS.md)에 구분하여 기록했다.

구현은 반영했지만 유휴 실행·실제 소유 스레드·취소·재등록·콜백 예외의 실제 브로커 인수 확인은 남아 있다.

## 구현 기록

- [연결 타이머 계약과 RabbitMQ 등록·취소 구현](./implements/1793777682327.md)
- [실행 가능한 연결 타이머 샘플 추가](./implements/1793778339166.md)
