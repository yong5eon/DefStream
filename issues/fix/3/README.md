# 워커에 공통 브로커 연결 타입 사용

## 달라진 점

이전에는 워커에 전달할 연결의 타입을 표시하려면 워커 전용 `WorkerConnection`을
사용해야 했습니다. 이제 `DefStream.Broker.Connection`을 사용하면 됩니다.
워커를 위해 별도의 연결 타입을 가져오거나 정의할 필요가 없습니다.

RabbitMQ·Redis 연결 객체를 `Worker`에 전달하는 기존 코드는 그대로 사용할 수 있습니다.
메시지 처리, ACK/NACK, 실패 정책, RPC와 스레드·프로세스 풀의 동작도 동일합니다.

## 기존 코드에서 바꿀 부분

`WorkerConnection`을 직접 가져오거나 타입 힌트에 사용했다면 공통 `Connection`으로
변경하세요. `WorkerConnection`은 더 이상 제공하지 않습니다.

변경 전:

```python
from DefStream.Worker import WorkerConnection
```

변경 후:

```python
from DefStream.Broker import Connection
```

해당 타입을 사용한 매개변수·반환값·변수의 타입 힌트도 `Connection`으로 바꾸면 됩니다.
브로커 객체만 전달하고 있었다면 수정할 필요가 없습니다.

## 직접 만든 브로커를 사용하는 경우

워커에서 사용할 연결에는 `connect()`, `close()` 외에 컨슈머를 만드는 `consumer()`가
있어야 합니다. 호출자가 별도로 검사하거나 워커 전용 타입을 상속할 필요는 없습니다.

워커가 연결과 setup을 마친 뒤 `consumer()` 지원 여부를 확인합니다.
지원하지 않으면 `TypeError: Worker broker must support consumer creation`으로
실패하고 종료 처리를 수행합니다. 메시지 발행만 가능한 연결은 워커에 사용할 수 없습니다.

공통 `Connection` 자체에는 `consumer()` 구현을 강제하지 않으므로,
워커에 사용하지 않는 발행 전용 연결은 변경할 필요가 없습니다.

## 상세 기록

- [요구사항 명세서](./REQUIREMENTS.md)
- [구현 및 RabbitMQ 검증 기록](./IMPLEMENTS.md)
