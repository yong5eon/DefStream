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

## 작업 발행은 `emit` 사용

작업을 보내는 함수와 브로커 연결 메서드의 이름이 `send`에서 `emit`으로 바뀌었습니다.
코어와 RabbitMQ·Redis 어댑터를 함께 갱신하세요. 이전 이름은 더 이상 제공하지 않습니다.

```python
from DefStream.Worker import emit


# broker는 호출자가 연결한 브로커이며, Add는 기존 작업 클래스입니다.
emit(
  {'a': 10, 'b': 20},
  task=Add,
  broker=broker,
)
```

직접 `connection.send(body, parameters)`를 호출했다면
`connection.emit(body, parameters)`로 바꾸세요.
큐·Exchange·Stream을 직접 사용하는 `send(body)`와 RPC `call(body)`는 바뀌지 않습니다.

`declare`, `emit`, `request` 모두 공통 `Connection`을 받습니다.
사용하는 쪽에서 기능별 연결 타입을 따로 지정할 필요가 없으며,
지원하지 않는 기능을 호출하면 `NotImplementedError`가 발생합니다.
이 함수들은 여전히 연결을 자동으로 열거나 닫지 않습니다.

사용자 정의 브로커에서 `TaskSender`를 사용했다면 `DefStream.Broker.Emittable`을
가져오고 작업 발행 메서드 이름을 `emit`으로 변경하세요.
선언과 RPC의 계약인 `Declarable.declare`와 `Requestable.request`는 유지됩니다.

## 연결 기능 지원 여부 확인

`GetExchange`, `GetQueue`, `GetStream`도 `GetConsumer`처럼 런타임 검사를 지원합니다.
예를 들어 `isinstance(connection, GetQueue)` 또는
`issubclass(ConnectionClass, GetQueue)`로 큐 생성 기능의 지원 여부를 확인할 수 있습니다.
각 계약은 `DefStream.Broker`에서 가져옵니다.

## 브로커 연결 팩터리 타입

Console에 전달하는 연결 생성 함수의 타입을 `BrokerFactory`라는 이름으로 제공합니다.
`from DefStream.Broker import BrokerFactory`로 가져올 수 있으며,
인자 없는 `__call__()`이 새 `Connection`을 반환하는 계약입니다.

기존 함수나 람다를 전달하는 코드는 바꾸지 않아도 됩니다.
클래스로 팩터리를 구현하려면 `BrokerFactory`를 상속하고 `__call__()`을 구현할 수 있습니다.
호출마다 새 연결을 반환해야 하며 Worker의 연결을 재사용하면 안 됩니다.

## 상세 기록

- [요구사항 명세서](./REQUIREMENTS.md)
- [구현 및 RabbitMQ 검증 기록](./IMPLEMENTS.md)
