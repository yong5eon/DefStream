# RabbitMQ

[← 매뉴얼 목차](./README.md)

RabbitMQ 연결, 큐·Exchange, Worker와 RPC 사용법입니다.

## RabbitMQ 사용 방법

Python 3.9 이상과 접속 가능한 RabbitMQ 서버가 필요하며 Pika를 사용합니다.

### 큐에 보내고 받기

로컬 RabbitMQ의 `guest` 계정을 사용하는 예제입니다.
운영에서는 별도 계정과 환경변수·비밀 저장소를 사용하세요.
예제는 `defstream.example.rabbitmq` 큐를 만들며 실행 후에도 큐를 유지합니다.

```python
from DefStream.Broker.Implements.RabbitMQ import Configuration, Connection


connection = Connection(Configuration(
  host='127.0.0.1',
  port=5672,
  username='guest',
  password='guest',
))
try:
  connection.connect()
  connection.create_queue('defstream.example.rabbitmq')
  queue = connection.queue('defstream.example.rabbitmq')
  queue.send({'message': 'Hello, DefStream!'})
  event = queue.pop(timeout=1000)
  if event is not None:
    print(event.body)
    event.ack()
finally:
  connection.close()
```

메시지는 기본 JSON 코덱으로 직렬화됩니다.
`pop()` 제한 시간은 **밀리초**이며, 양수 제한 시간에 메시지가 없으면 `None`을 반환합니다.
`None` 또는 `0`은 무기한 대기입니다.
처리가 성공하면 `ack()`, 재전달하려면 `nack()`, 거부하려면 `reject()`를 호출하세요.
거부한 메시지는 브로커의 dead-letter 설정이 있으면 해당 목적지로, 없으면 폐기됩니다.

### 연결 설정

| 옵션 | 의미 |
| --- | --- |
| `host`, `port` | RabbitMQ 주소와 AMQP 포트 |
| `username`, `password` | 인증 정보 |
| `vhost` | 가상 호스트, 기본값 `/` |
| `ssl` | TLS 사용 여부, 기본값 `False` |
| `timeout` | blocked-connection 제한 시간, 밀리초 |
| `heartbeat` | 현재 구현은 `int(heartbeat * 2 / 1000)`초로 변환하여 Pika에 전달 |
| `encode`, `decode` | 메시지 코덱, 기본값 JSON |

`timeout`은 모든 작업에 대한 전체 실행 제한 시간이 아닙니다.
일반 연결의 heartbeat는 애플리케이션 작업·유휴 시간에 맞게 설정하고 처리되도록 관리하세요.
연결과 그 리소스는 **소유 스레드에서만 사용**해야 하며, 스레드·프로세스 사이에 공유하지 마세요.

### 로깅

여섯 클래스는 `DefStream.Broker.Implements.RabbitMQ.ClassName` 이름의 클래스 멤버
`logger`를 사용합니다(`Connection`, `Consumer`, `Queue`, `Exchange`, `Stream`, `Event`).
하위 클래스는 같은 로거를 상속하며 필요하면 멤버를 재정의할 수 있습니다.
라이브러리는 핸들러·`NullHandler`·레벨·필터를 설정하지 않고 루트로 전파합니다.
미설정 시 표준 `logging.lastResort` 동작을 유지합니다.

연결·자원 변경은 INFO, 메시지·RPC·정산 추적은 DEBUG, RPC 시간 초과·원격 오류·
응답 라우팅 불가는 WARNING, 내부 I/O·코덱 오류는 ERROR입니다.
본문·결과·헤더·인증정보와 예외 문자열·traceback은 기록하지 않으며 예외는 그대로 전파합니다.
애플리케이션이 같은 예외를 다시 기록하면 중복될 수 있습니다.
발행 API 반환은 소비자 처리 완료가 아니며, RPC 응답 시간 초과도 전달된 작업을 취소하지 않습니다.

`samples/Broker/RabbitMQ/*.py`는 실행 진입점에서만 루트 DEBUG 콘솔 출력을 구성합니다.
핸들러의 `Filter('Sample')` 또는 `Filter('DefStream.Broker.Implements.RabbitMQ')`
통과 조건으로 두 이름과 점으로 구분된 하위 로거만 출력하며 Pika·코어 등은 제외합니다.
다른 애플리케이션에서는 원하는 상위 이름(`DefStream`, `DefStream.Broker` 등)이나
클래스 이름을 선택하고 핸들러·레벨·필터를 직접 구성하세요.

### Worker로 작업 처리하기

다음은 큐와 오류 큐를 준비한 후 작업을 소비하는 실행 파일입니다.

```python
from signal import SIGINT, signal

from DefStream.Broker.Implements.RabbitMQ import (
  Configuration,
  Connection,
  Reject,
  Subscription,
)
from DefStream.Worker import Run, ThreadPool, Worker, WorkerSetup, declare


class Add(
  Run,
  parameters=Subscription(
    queue='defstream.example.rabbitmq.add',
    qos=4,
    error='defstream.example.rabbitmq.add.error',
  ),
  on_error=Reject(),
):
  def run(
    self,
    a: int,
    b: int,
  ):
    return a + b


class Prepare(WorkerSetup):
  def __call__(
    self,
    worker: Worker,
  ) -> None:
    for task in worker.tasks:
      declare(
        task=task,
        broker=worker.broker,
      )


if __name__ == '__main__':
  worker = Worker(
    Connection(Configuration(
      host='127.0.0.1',
      port=5672,
      username='guest',
      password='guest',
    )),
    ThreadPool(4),
    setups=Prepare(),
  )
  worker.add(Add)
  signal(
    SIGINT,
    lambda *_: worker.stop(),
  )
  worker.run()
```

다른 프로세스에서 같은 큐에 `{'a': 10, 'b': 20}`을 보내면 처리됩니다.
Worker는 실행과 완료 훅이 끝난 뒤 ACK하고, 실패하면 지정한 정책을 적용합니다.
`on_error`를 생략하면 기본값은 `Requeue()`입니다.

`Subscription` 옵션:

- `queue`: 작업 큐 이름.
- `qos`: 이 구독의 미확인 메시지 수 제한. 기본 소비자 값은 1이며, 0은 무제한입니다.
  Worker의 공유 풀 크기와 별개입니다.
- `error`: `declare()`가 생성하고 연결할 오류 큐 이름. 거부된 메시지의 DLQ입니다.
- `offset`: RabbitMQ 스트림 구독에 사용할 정수 오프셋.
- `max_priority`: classic 작업 큐의 최대 우선순위. 정수 `1..255` 또는 `None`.
- `priority`: 기본 메시지 우선순위. 정수 `0..max_priority` 또는 `None`.
  이 값만 지정하면 `max_priority`는 `255`로 설정됩니다.

`Subscription` 객체 생성이나 `consumer.subs()`는 큐를 선언하지 않습니다.
작업용 `declare()`는 일반 durable 큐와 선택적 DLQ를 준비하며,
스트림 큐나 Exchange 바인딩을 자동 생성하지 않습니다.
기존 큐의 선언 옵션이 다르면 실패하며 자동 삭제·재생성하지 않습니다.

### 워커 작업 우선순위

작업을 발행할 때는 `DefStream.Worker.emit` 또는
`connection.emit(body, parameters)`을 사용합니다. 기존 작업 발행 이름 `send`는
`emit`입니다.
큐·Exchange·Stream의 저수준 `send()`와 RPC `call()`은 변경하지 않습니다.

작업에 지정한 `Subscription`에 기본값 `priority`와 큐 최대값 `max_priority`를
함께 설정합니다. `Run`에는 별도의 `priority` 설정을 두지 않습니다.

```python
class PriorityAdd(
  Add,
  parameters=Subscription(
    queue='defstream.example.rabbitmq.priority.add',
    qos=1,
    max_priority=5,
    priority=2,
  ),
):
  pass
```

- 워커 API `declare(task=PriorityAdd, broker=connection)`는 큐에
  `x-max-priority=5`를 반영합니다. 기존 DLQ 설정도 보존합니다.
- `emit(..., task=PriorityAdd, broker=connection)` 및
  `request(..., task=PriorityAdd, broker=connection)`는 작업 기본값 `2`를 사용합니다.
  호출에 `priority=0` 또는 다른 유효한 값을 지정하여 재정의할 수 있습니다.
- 기본값만 정의하면 큐 최대값은 `255`, 최대값만 정의하면 기본값은 `None`입니다.
  호출별 값도 없으면 AMQP 우선순위 속성을 생략합니다.
- 워커 경로는 작업의 유효 최대값으로 검증합니다. 작업 설정 없이 호출에서만
  지정하면 `0..255` 범위만 검증하며, 우선순위 큐 사전 선언은 호출자 책임입니다.
- 기존 저수준 `Queue.send`, `Exchange.send`와 `Queue.call`도 `priority=`를 받습니다.
  이 경로는 작업 정의를 받지 않으므로 작업별 최대값은 검증하지 않습니다.
  정수 `0..255`만 허용하며 `bool`은 거부합니다.
- 최대값을 늘릴수록 자원 비용이 증가하므로 필요한 수준만 지정하는 것을 권장합니다.
- 동일 큐를 여러 작업 정의에서 선언한다면 최대값을 동일하게 맞춰야 합니다.
  기존 일반 큐나 최대값이 다른 큐를 재선언하면 RabbitMQ 오류가 전파됩니다.
  자동 삭제하지 않으므로, 새 큐로 전환하거나 미처리 메시지를 보존한 후 운영자가
  안전하게 재생성하고 생산자·소비자를 함께 전환해야 합니다.
- 높은 값이 먼저 전달되지만 이미 prefetch된 메시지나 실행 중인 작업은 선점하지
  않습니다. 재전달, 다중 소비자에서는 완료 순서를 보장하지 않으며 낮은 우선순위
  메시지가 오래 대기할 수 있습니다. Stream 및 Quorum 큐는 이번 지원 대상이 아닙니다.

### 동기 RPC

실행 중인 Worker가 있는 큐에 `call()`을 사용하면 `Run.run()`의 반환값을 받습니다.
아래 코드는 앞의 직접 연결 예제에서 `connect()`와 `close()` 사이에 사용하세요.

```python
result = connection.queue('defstream.example.rabbitmq.add').call(
  {'a': 10, 'b': 20},
  timeout=5,
)
print(result)
```

- `timeout`은 **초** 단위이며 응답이 없으면 `TimeoutError`가 발생합니다.
  이미 전달된 서버 작업을 취소하거나 전체 연결·정리 시간을 엄격히 제한하는 값은 아닙니다.
- 각 호출은 전용 연결과 임시 응답 큐를 사용하고 종료 시 정리합니다.
- 서버가 요청을 거부하면 `DefStream.Broker.RemoteError`가 발생합니다.
  재큐잉은 최종 오류 응답 없이 재시도할 수 있습니다.
- 응답 발행과 요청 ACK는 원자적이지 않습니다. RPC에서도 중복 실행에 대비하세요.

공유 `Run` 클래스를 사용하는 애플리케이션은 코어의
`request(body, task=Add, broker=connection, timeout=5)`도 사용할 수 있습니다.

```mermaid
sequenceDiagram
  participant P as 생산자
  participant Q as 작업 큐
  participant W as Worker
  participant R as 응답 큐
  P->>Q: 작업 발행 (RPC 메타데이터 선택)
  Q->>W: 작업 전달
  W->>W: 작업 및 완료 훅 실행
  alt RPC 요청
    W->>R: 성공 응답 발행
  end
  W->>Q: 전달 메시지 ACK
  R-->>P: RPC 결과 반환
```

응답 발행과 요청 ACK는 원자적이지 않습니다. 응답이 발행된 뒤 ACK 전에 실패하면 작업이 재전달되어 중복 실행될 수 있습니다.

### Exchange와 스트림

- `connection.exchange(name)`은 `send()`와 `call()`을 제공합니다.
  `event=`가 라우팅 키입니다. Exchange와 큐·바인딩을 먼저 선언하세요.
- Exchange RPC가 여러 큐로 라우팅되면 여러 곳에서 실행될 수 있으며,
  클라이언트는 첫 일치 응답만 받습니다. 일반 RPC에는 단일 목적지를 사용하세요.
- `create_exchange()`, `bind_exchange_to_queue()`, `bind_exchange_to_exchange()`로 라우팅을 구성합니다.
  각각에 대응하는 `delete_...` 또는 `unbind_...` 메서드도 있습니다.
- `create_stream()`으로 스트림 큐를 만든 뒤 `connection.stream(name)`의
  `send()`와 `read(offset=0, timeout=1000)`을 사용합니다. 읽기 제한 시간은 밀리초입니다.
  읽은 이벤트는 이터레이터가 다음 단계로 진행될 때 자동 ACK합니다.
- `delete_queue()`, `delete_stream()`, `delete_exchange()`는 리소스를 삭제하므로
  애플리케이션 소유 리소스에만 사용하세요.

### 운영 시 주의사항

- 최소 한 번(at-least-once) 전달을 전제로 멱등 작업을 작성하세요.
- 무제한 재큐잉은 영구 오류 메시지의 반복 실행을 만들 수 있습니다. DLQ와 재시도 정책을 설계하세요.
- 소비자 연결에서 긴 작업을 직접 실행하지 말고 Worker의 풀을 사용하세요.
- 작업 훅에서 발행하려면 훅이 실행되는 스레드·프로세스 안에 별도 생산자 연결을 만드세요.
- `worker.stop()`은 처리 중인 작업과 ACK를 기다린 뒤 연결과 풀을 닫습니다.
  강제 종료 또는 종료 대기 시간 제한은 제공하지 않습니다.

### 샘플

- [Sample.py](../samples/Broker/RabbitMQ/Sample.py)
- [Sample.Stream.py](../samples/Broker/RabbitMQ/Sample.Stream.py)
- [Sample.RPC.py](../samples/Broker/RabbitMQ/Sample.RPC.py)
