# DefStream

**한국어** | [English](./README.en.md)

**Just def.**<br>
**Let workers do the work.**<br>
**You don't need to await this.**

DefStream은 메시지 브로커에서 받은 작업을 일반 Python 함수처럼 작성하고,
스레드 또는 프로세스 풀에서 실행하는 동기식 작업 처리 라이브러리입니다.
`async` / `await` 없이 작업 실행, 처리 확인(ACK), 실패 정책, 상태 모니터링을 구성할 수 있습니다.

- **작업 정의**: `Run` 클래스에 구독 대상과 처리 함수를 선언합니다.
- **병렬 실행**: `ThreadPool` 또는 `ProcessPool`을 선택합니다.
- **브로커 선택**: RabbitMQ와 Redis Streams 구현체를 포함하며 필요한 클라이언트만 선택 설치합니다.
- **요청·응답**: RabbitMQ에서 작업의 반환값을 RPC 응답으로 받을 수 있습니다.
- **운영 도구**: HTTP 상태 확인, Prometheus 지표, 대시보드, 작업 콘솔을 선택적으로 제공합니다.
- **입출력 계약**: 스키마와 런타임 검증을 정의하고 AsyncAPI 문서로 노출합니다.

## 목차

- [설치](#설치)
- [빠르게 시작하기](#빠르게-시작하기)
- [작업과 메시지 처리](#작업과-메시지-처리)
- [실행 풀과 종료](#실행-풀과-종료)
- [생명주기 훅](#생명주기-훅)
- [요청·응답 계약과 검증](#요청응답-계약과-검증)
- [상태 확인과 작업 콘솔](#상태-확인과-작업-콘솔)
- [로깅](#로깅)
- [RabbitMQ 사용 방법](#rabbitmq-사용-방법)
- [Redis 사용 방법](#redis-사용-방법)
- [브로커 선택과 운영 주의사항](#브로커-선택과-운영-주의사항)
- [예제와 라이선스](#예제와-라이선스)

## 로깅

DefStream은 표준 `logging`으로 기록하며 핸들러·포매터·레벨을 설정하지 않습니다.
애플리케이션에서 필요한 출처만 선택해 출력하세요. 샘플은 `Sample`과 `DefStream`
이름 및 그 하위 로거만 출력하며, 샘플의 `print()`는 로그로 대체했습니다.
Worker의 기존 시작 배너는 로깅 설정과 무관하게 그대로 출력됩니다.

```python
from logging import DEBUG, Filter, Formatter, StreamHandler, getLogger

sources = (Filter('Sample'), Filter('DefStream'))
handler = StreamHandler()
handler.setFormatter(Formatter(
  '%(asctime)s %(processName)s %(name)s %(levelname)s %(message)s'
))
handler.addFilter(lambda record: any(source.filter(record) for source in sources))
root = getLogger()
root.setLevel(DEBUG)
root.addHandler(handler)

logger = getLogger('Sample')
logger.info('Application started')
```

필터는 루트 로거가 아닌 **핸들러**에 적용합니다. `Filter('DefStream')`은
`DefStream`과 `DefStream.` 하위 이름을 포함하지만 `DefStreamExtra`는 포함하지 않습니다.
위 설정은 독립 실행 애플리케이션을 위한 예제이며, 이미 있는 다른 핸들러의 출력은 바꾸지 않습니다.
브로커만 보고 싶으면 `DefStream` 대신 `DefStream.Broker.Implements.RabbitMQ` 또는
`DefStream.Broker.Implements.Redis`를 선택할 수 있습니다.

- 클래스 멤버 `logger`에 `DefStream.Worker`, `DefStream.Run`, `DefStream.Executor`,
  `DefStream.Pool`, `DefStream.ThreadPool`, `DefStream.ProcessPool`을 사용합니다.
- Pool 공통 메서드도 실제 풀의 로거 멤버를 사용합니다. 사용자 하위 클래스는 기본 이름을
  상속하며 원하면 `logger`를 명시적으로 재정의할 수 있습니다.
- Inspector·Server·RequestHandler는 `DefStream.Inspector`를 공유합니다.
  HTTP 요청 수신은 DEBUG, 응답 상태와 전송 결과는 INFO입니다.
  확장 고유 로그는 `DefStream.Inspector.Extensions.<확장 이름>`을 사용합니다.
- 정상 메시지별 처리 흐름은 DEBUG, 생명주기는 INFO, 주의할 사건은 WARNING,
  처리 실패는 ERROR로 기록합니다. 본문·결과·인증정보는 기본 로그에 포함하지 않습니다.
- 핸들러가 전혀 없으면 Python의 `lastResort`에 의해 WARNING 이상이 stderr에 나올 수 있습니다.
  사용자 예외 메시지에는 민감한 값을 넣지 마세요. 실패 traceback에 예외 메시지가 포함됩니다.

ProcessPool은 `spawn` 자식 프로세스를 사용하므로 부모의 핸들러가 자동으로 전달되지 않습니다.
자식도 로그를 출력하려면 import 가능한 `PoolSetup` 구현에서 같은 설정을 적용하고
`ProcessPool(..., setups=...)`로 전달하세요. 자식 초기화 훅이 실행되기 전의 DEBUG·INFO는
그 설정으로 수신할 수 없습니다.
[RabbitMQ 작업 예제의 LoggingSetup](./samples/Worker/RabbitMQ/Tasks.py)과
[부모·자식 설정 예제](./samples/Worker/RabbitMQ/Worker.py)를 참고하세요.
기존 애플리케이션에서는 이미 설정한 핸들러를 반복 추가하지 않도록 초기화 위치를 관리해야 합니다.

## 설치

Python **3.9 이상**이 필요합니다. 실제 메시지 처리를 위해 사용할 브로커 서버도 준비하세요.

```shell
python -m pip install "DefStream[RabbitMQ]"
```

Redis를 사용하거나 두 어댑터를 모두 설치하려면 다음과 같이 선택합니다.

```shell
python -m pip install "DefStream[Redis]"
python -m pip install "DefStream[RabbitMQ,Redis]"
```

코어만 필요하면 `python -m pip install DefStream`을 사용합니다.
두 브로커 구현체는 모두 DefStream 배포본에 포함되지만, 기본 설치에는 브로커 클라이언트가 포함되지 않습니다.
`RabbitMQ` extra는 `pika>=1.3.2`, `Redis` extra는 `redis>=5.1.1`을 설치합니다.

| 선택 설치 | Python import 경로 | 사용 안내 |
| --- | --- | --- |
| `DefStream` | `DefStream` | 이 문서 |
| `DefStream[RabbitMQ]` | `DefStream.Broker.Implements.RabbitMQ` | [RabbitMQ 사용 방법](#rabbitmq-사용-방법) |
| `DefStream[Redis]` | `DefStream.Broker.Implements.Redis` | [Redis 사용 방법](#redis-사용-방법) |

기존 `DefStream-RabbitMQ`와 `DefStream-Redis` 패키지의 별도 배포는 종료하며,
기존 프로젝트는 삭제 예정입니다. 기존 패키지와의 하위 호환성은 지원하지 않습니다.
새 환경에 위 명령으로 통합 패키지를 설치하세요. 기존 환경을 전환한다면 먼저
`python -m pip uninstall DefStream-RabbitMQ DefStream-Redis`로 별도 어댑터를 제거한 후
통합된 DefStream을 다시 설치하세요. 같은 import 경로의 파일을 제공하므로 함께 설치하지 마세요.
기존 환경에서 재설치할 때는 `python -m pip install --force-reinstall "DefStream[RabbitMQ,Redis]"`를
사용하고, 실제 사용하는 브로커에 맞게 extra를 선택하세요.

## 빠르게 시작하기

로컬 RabbitMQ가 `127.0.0.1:5672`에서 실행 중이라고 가정합니다.
아래 세 파일을 같은 디렉터리에 저장하세요. `guest` 계정은 로컬 실행 예제이며,
운영에서는 별도 계정과 환경변수·비밀 저장소를 사용하세요.

### 1. 작업 정의: `tasks.py`

```python
from DefStream.Broker.Implements.RabbitMQ import Reject, Subscription
from DefStream.Worker import Run


class Add(
  Run,
  parameters=Subscription(
    queue='defstream.example.add',
    qos=4,
    error='defstream.example.add.error',
  ),
  on_error=Reject(),
):
  def run(
    self,
    a: int,
    b: int,
  ):
    result = a + b
    print(result)
    return result
```

`parameters`는 작업이 소비할 큐를 지정합니다. 메시지 본문 `{'a': 10, 'b': 20}`은
`run(a=10, b=20)`으로 전달됩니다. 이 예제는 실패 시 재시도 대신 거부하며,
거부된 메시지를 받을 오류 큐도 선언합니다.

### 2. Worker 실행: `worker.py`

`Worker`는 `DefStream.Broker.Connection`을 직접 받습니다.
연결 계약은 `connect()`, `close()`만 요구하며, 워커 실행 시 내부에서
`GetConsumer` 지원 여부를 검사합니다. 컨슈머를 생성할 수 없는 브로커는 `TypeError`를 발생시키며,
워커 전용 연결 타입은 필요하지 않습니다.

```python
from signal import SIGINT, signal

from DefStream.Broker.Implements.RabbitMQ import Configuration, Connection
from DefStream.Worker import ThreadPool, Worker, WorkerSetup, declare
from tasks import Add


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

```shell
python worker.py
```

Worker가 브로커 연결을 열고, `Prepare`가 큐와 오류 큐를 선언한 뒤 구독을 시작합니다.
`Run`을 정의하는 것만으로 등록되지는 않으며 `worker.add()`가 필요합니다.

### 3. 메시지 보내기: `client.py`

Worker가 실행 중인 상태에서 다른 터미널에서 실행하세요.

```python
from DefStream.Broker.Implements.RabbitMQ import Configuration, Connection
from DefStream.Worker import emit, request
from tasks import Add


connection = Connection(Configuration(
  host='127.0.0.1',
  port=5672,
  username='guest',
  password='guest',
))
try:
  connection.connect()
  message_id = emit(
    {'a': 10, 'b': 20},
    task=Add,
    broker=connection,
  )
  print(message_id)
  result = request(
    {'a': 10, 'b': 20},
    task=Add,
    broker=connection,
    timeout=5,
  )
  print(result)
finally:
  connection.close()
```

```shell
python client.py
```

`emit()`와 `request()`는 **각각 별도의 작업을 발행**합니다. 위 예제는 덧셈을 두 번 실행하며,
`request()`의 결과는 `30`입니다. `request()`의 제한 시간은 초 단위이고,
시간이 초과되어도 이미 전달된 작업은 취소되지 않습니다.

## 작업과 메시지 처리

### 작업을 대상으로 하는 API

| 함수 | 역할 | 연결 관리 |
| --- | --- | --- |
| `declare(task=..., broker=...)` | 작업의 큐·구독 리소스 선언 | 호출자가 연결·종료 |
| `emit(body, task=..., broker=...)` | 작업 목적지로 단방향 메시지 발행 | 호출자가 연결·종료 |
| `request(body, task=..., broker=..., timeout=5)` | 작업 결과를 동기 RPC로 요청 | 호출자가 연결·종료; RabbitMQ만 지원 |

세 함수는 `DefStream.Worker`에서 가져옵니다. 전달된 연결을 자동으로 열거나 닫지 않으며,
`emit()`와 `request()`는 목적지를 자동 선언하지 않습니다.
수신 Worker 또는 별도의 준비 단계에서 먼저 `declare()`를 호출하세요.
하나의 연결을 같은 소유 스레드에서 여러 발행에 재사용할 수 있습니다.

세 함수 모두 공통 `Connection`을 받고, 내부에서 선언·발행·RPC 지원 여부를 확인합니다.
지원하지 않는 기능은 `NotImplementedError`로 실패합니다.
기존 작업 발행 함수와 연결의 `send`는 `emit`으로 이름이 바뀌었습니다.
사용자 정의 브로커의 작업 발행 계약도 `TaskSender.send` 대신 `Emittable.emit`을 사용하세요.
큐·Exchange·Stream의 저수준 `Sendable.send()`와 RPC `Callable.call()`은 그대로입니다.

작업 본문은 **문자열 키를 가진 매핑**이어야 하며, 반환값은 어댑터가 직렬화할 수 있어야 합니다.
하나의 Worker에서는 같은 큐에 여러 작업을 중복 등록할 수 없습니다.
메시지 유형을 보고 여러 `Run` 중 하나를 고르는 방식이 아니라 큐별로 작업을 선택합니다.

### 작업 우선순위

RabbitMQ classic 큐에서는 작업 `parameters`의 RabbitMQ `Subscription`에
`priority`로 기본 메시지 우선순위, `max_priority`로 큐 최대값을 함께 정의합니다.
`Run`에 별도의 `priority` 설정을 두지 않습니다.
`declare()`가 이 설정을 읽어 우선순위 큐를 준비합니다.

```python
from DefStream.Broker.Implements.RabbitMQ import Subscription
from DefStream.Worker import (
  Run,
  declare,
  request,
  emit,
)


class Add(
  Run,
  parameters=Subscription(
    queue='defstream.example.priority.add',
    max_priority=5,
    priority=2,
  ),
):
  def run(
    self,
    a: int,
    b: int,
  ):
    return a + b


# broker는 호출자가 연결한 RabbitMQ Connection입니다.
declare(
  task=Add,
  broker=broker,
)
emit(
  {'a': 10, 'b': 20},
  task=Add,
  broker=broker,
)
# RPC에는 별도로 실행 중인 Worker가 필요합니다.
result = request(
  {'a': 10, 'b': 20},
  task=Add,
  broker=broker,
  priority=5,
)
```

- 호출의 `priority`가 생략되거나 `None`이면 작업 기본값을 사용합니다.
  명시적 `0`은 가장 낮은 우선순위이며 기본값을 덮어씁니다.
- 작업 기본값만 지정하면 큐 최대값은 RabbitMQ 상한 `255`입니다.
  최대값만 지정하면 기본값은 `None`이며, 호출값도 없으면 메시지 속성을 생략합니다.
- 작업 최대값을 초과하는 값, 음수, 정수가 아닌 값과 `bool`은 거부합니다.
- 작업 설정 없이 호출에서만 지정하면 브로커 범위 `0..255`만 검증합니다.
  우선순위 큐의 사전 선언과 실제 큐 최대값 준수는 호출자 책임입니다.
- 자식 작업은 설정을 상속하고 유효한 값으로 재정의할 수 있지만 해제할 수는 없습니다.
- Redis에 우선순위를 요청하면 `NotImplementedError`가 발생합니다.
  우선순위 미지정 시 기존 Redis 동작은 유지합니다.
- 우선순위는 같은 큐의 대기 메시지 전달에 적용됩니다. 이미 전달·실행 중인
  작업을 선점하거나 여러 작업의 실행·완료 순서를 보장하지 않습니다.

### 성공, 실패와 재시도

- 작업 실행과 완료 훅이 성공한 뒤 ACK합니다. RabbitMQ RPC는 응답 발행도 ACK보다 먼저 수행합니다.
- 실패 시 `on_error` 정책을 적용합니다. 기본값은 `Requeue()`이며, `Reject()`를 명시할 수 있습니다.
- `Requeue`와 `Reject`는 공통으로 `DefStream.Broker.Policies`에서 가져올 수 있습니다.
- `Reject()`의 실제 효과는 브로커에 따라 다릅니다. RabbitMQ는 설정된 DLQ로 보내거나 폐기하며,
  Redis는 해당 그룹에서 ACK하고 스트림 이력은 유지합니다.
- 재시도 횟수의 자동 제한은 없습니다. 영구적인 오류가 무한 재전달되지 않도록 정책을 선택하세요.
- 전송과 ACK는 하나의 트랜잭션이 아닙니다. **중복 실행에 안전한 멱등 작업**을 작성해야 합니다.

브로커 리소스를 직접 사용할 때의 공통 메서드는 다음과 같습니다.
모든 리소스가 모든 메서드를 지원하는 것은 아닙니다.

연결의 `exchange()`·`queue()`·`stream()`·`consumer()` 지원 여부는 각각
`GetExchange`·`GetQueue`·`GetStream`·`GetConsumer`로 `isinstance` 또는 `issubclass`
검사할 수 있습니다. 이 계약들은 `DefStream.Broker`에서 가져옵니다.

| 메서드 | 의미 | 제한 시간 단위 |
| --- | --- | --- |
| `send(body)` | 메시지 발행 | 어댑터별 설정 |
| `call(body, timeout=5)` | 동기 RPC | 초 |
| `pop(timeout=1000)` | 한 메시지 수신 | 밀리초 |
| `read(offset=0, timeout=1000)` | 스트림 이력·새 메시지 읽기 | 밀리초 |

`pop()`과 `read()`에서 `None` 또는 `0`은 무기한 대기입니다.
직접 수신한 처리용 이벤트는 `ack()`, `nack()`, `reject()`로 정산하세요.
Redis 이력 읽기는 그룹 처리와 다르며 ACK 대상이 아닙니다.
RabbitMQ 스트림 읽기는 이터레이터가 다음 단계로 진행될 때 자동 ACK합니다.

## 실행 풀과 종료

| 풀 | 권장 용도 | 주의사항 |
| --- | --- | --- |
| `ThreadPool(4)` | I/O 대기 중심 작업 | 실행 스레드 사이에 공유하는 상태 보호 |
| `ProcessPool(4)` | CPU 연산 중심 작업 | 클래스·입력·결과·훅은 pickle 가능해야 함 |

두 풀은 `DefStream.Worker`에서 가져옵니다. 크기를 생략하면 CPU 수를 사용하며,
공유 풀의 용량은 제출되어 처리 중인 작업을 포함합니다. 무제한 대기열은 없습니다.
풀이 가득 차면 Worker는 메시지를 재전달하도록 NACK합니다.
RabbitMQ의 작업별 `Subscription.qos`는 미확인 메시지 수 제한이며 풀 크기와는 다릅니다.

`ProcessPool`을 사용할 때는 클래스와 훅을 import 가능한 모듈 최상위에 정의하고,
Worker 생성·실행을 `if __name__ == '__main__':` 안에 두세요.
브로커 연결이나 이벤트 객체를 자식 프로세스로 넘기지 마세요.

`worker.stop()`은 새 작업 수신을 멈추고 실행 중인 작업과 메시지 정산을 기다린 후 자원을 닫습니다.
현재 강제 종료나 종료 대기 시간 제한은 없습니다. 위 예제처럼 애플리케이션에서
`SIGINT`를 연결하면 Ctrl+C로 정상 종료할 수 있습니다.
Worker와 주입한 연결·풀은 한 번의 실행 전용이며 다른 Worker와 공유하거나 재시작하지 않습니다.

## 생명주기 훅

훅 인터페이스는 모두 `DefStream.Worker`에서 가져옵니다.

| 범위 | 훅 | 전달값 및 실행 위치 |
| --- | --- | --- |
| 작업 | `RunSetup`, `RunComplete`, `RunError` | `Context`; `Context`와 결과; `Context`와 예외. 풀 안에서 실행 |
| 풀 | `PoolSetup`, `PoolCleanup` | 인자 없음. 각 실행 스레드·프로세스 안에서 실행 |
| Worker | `WorkerSetup`, `WorkerCleanup` | Worker 인스턴스. 부모의 연결 소유 스레드에서 실행 |

`Run` 클래스에는 `setups=`, `completes=`, `errors=`를 지정합니다.
Worker와 풀 생성자에는 `setups=`, `cleanups=`를 지정합니다.
각 옵션은 하나의 훅 또는 순서 있는 훅 시퀀스를 받습니다.
`Context.args`, `Context.kwargs`에서 호출 인자를 확인할 수 있습니다.

풀의 각 실행 환경은 첫 작업 때 생성되며 초기화·정리 훅을 한 번씩 실행합니다.
DB 연결처럼 실행 환경에 종속된 자원은 여기서 생성·종료하세요.
Worker 초기화 훅은 브로커 연결 후 구독 전에 실행되고,
정리 훅은 풀 종료 후 소비자·브로커가 닫히기 전에 실행됩니다.
초기화 도중 실패할 수도 있으므로 정리 훅은 부분 초기화 상태를 고려해야 합니다.
프로세스 강제 종료나 충돌 시 정리 훅 실행은 보장되지 않습니다.

`RunError`는 오류 처리용 코드이고 `on_error`는 메시지 정산 정책입니다.
오류 훅을 실행했다고 작업이 성공으로 바뀌지는 않습니다.
완료 훅에서 다음 작업을 발행할 때는 그 훅의 스레드·프로세스에서 별도 연결을 열고 닫으세요.
일부 발행 후 실패하더라도 이미 보낸 메시지는 롤백되지 않습니다.

## 요청·응답 계약과 검증

`Descriptor`는 **데이터의 구조를 설명**하고, `Validator`는 **실제 값을 검증·변환**합니다.
두 도구를 `Specification`에 연결하면 작업의 문서와 실행 시 검증을 함께 구성할 수 있습니다.
다음 예제들은 위에서부터 같은 파일에 이어서 작성하세요.

### 1. Descriptor로 스키마 작성

```python
from DefStream.Descriptor import DumpSchema, Integer, Object, Properties, Schema


request_schema = Object(
  description='Addition request',
  properties=Properties(
    a=Integer('First operand'),
    b=Integer('Second operand'),
  ),
)
response_schema = Integer('Sum')

print(DumpSchema(Schema(
  'AddRequest',
  request_schema,
)))
```

`Object`는 객체, `Properties`는 필드, `Integer`는 정수를 설명합니다.
`Integer` 등의 필드는 기본적으로 필수이며 `required=False`로 선택 필드를 표시할 수 있습니다.
`String`, `Number`, `Boolean`, `Array` 등으로 다른 타입과 중첩 구조도 표현합니다.
`DumpSchema()`에는 `Schema`로 감싼 값을 전달하여 일반 JSON Schema 딕셔너리를 얻습니다.

이 스키마는 `a`, `b`를 정수 필수 필드로 문서화하지만 **메시지를 자동 검증하지는 않습니다.**
스키마의 필수 여부·기본값·범위를 실제 실행에서도 적용하려면 대응하는 검증 규칙이 필요합니다.

### 2. Validator로 값 검증

```python
from DefStream.Validator import Validator
from DefStream.Validator.Patterns import IsInteger, IsObject
from DefStream.Validator.Patterns.Object import IsMappingOf, IsRequiredIn


request_validator = Validator(
  IsObject(
    IsRequiredIn(
      'a',
      'b',
    ),
    IsMappingOf({
      'a': IsInteger(),
      'b': IsInteger(),
    }),
  ),
)
response_validator = Validator(IsInteger())

print(request_validator({'a': 10, 'b': 20}))
```

- `Validator`는 패턴을 지정한 순서대로 적용하고 마지막 값을 반환합니다.
- `IsObject`는 `dict` 타입을 확인하고, 내부 패턴으로 필수 키와 각 필드의 타입을 검사합니다.
- `IsRequiredIn`은 키 누락 시 `ValueError`, `IsInteger`는 잘못된 타입에 `TypeError`를 발생시킵니다.
  문자열 `'10'`이나 불리언 `True`를 정수로 인정하지 않습니다.
- `IsMappingOf`는 지정한 필드를 검증·변환하며 딕셔너리를 직접 갱신할 수 있습니다.
  원본 보존이 필요하면 복사본을 전달하세요. 지정하지 않은 추가 키를 제거하거나 거부하지는 않습니다.
  추가 키가 작업 함수의 인자와 맞지 않으면 호출이 실패하므로 필요한 제한을 별도로 작성하세요.

### 3. 검증과 변환 조합

숫자 문자열을 허용하려면 `IsInteger` 대신 명시적인 변환 패턴을 사용합니다.
아래는 문자열을 정수로 변환한 후 0 이상인지 검사하는 독립적인 예제입니다.

```python
from DefStream.Validator import Validator
from DefStream.Validator.Patterns import IsGreaterEqualTo, ToInteger


non_negative_integer = Validator(
  ToInteger(),
  IsGreaterEqualTo(0),
)

print(non_negative_integer('10'))
```

결과는 문자열이 아닌 정수 `10`입니다. 변환할 수 없는 문자열이나 음수는 `ValueError`가 발생합니다.
`ToInteger`는 Python 숫자 리터럴 형식의 문자열을 처리하며, 엄격한 타입 검사와 동작이 다릅니다.
이 변환기는 위의 엄격한 요청 검증기를 바꾸지 않습니다. 필드에 적용하려면
`IsMappingOf`의 해당 값에 `non_negative_integer`를 넣으세요.

### 4. 작업의 요청·응답에 연결

앞에서 만든 스키마와 검증기를 사용하여 기존 `Add`를 다음처럼 대체합니다.
이 클래스를 Worker에 등록하면 요청은 `run()` 전에, 반환값은 완료 훅 전에 검증합니다.

```python
from DefStream.Broker.Implements.RabbitMQ import Reject, Subscription
from DefStream.Worker import Run, Specification


class Add(
  Run,
  parameters=Subscription(queue='defstream.example.validated-add'),
  on_error=Reject(),
  request=Specification(
    schema=request_schema,
    validator=request_validator,
    example={'a': 10, 'b': 20},
  ),
  response=Specification(
    schema=response_schema,
    validator=response_validator,
    example=30,
  ),
  name='add',
  description='Add two integers',
):
  def run(
    self,
    a: int,
    b: int,
  ):
    return a + b
```

- `schema`는 문서용입니다. JSON Schema 매핑, Descriptor 값·조건, dataclass 타입 등을 받지만,
  그 자체로 런타임 검증이나 모델 생성을 수행하지 않습니다.
- `validator`는 호출 가능한 검증·변환 함수이며 반환한 값을 실제 실행에 사용합니다.
  요청 검증 결과도 문자열 키를 가진 매핑이어야 합니다.
- 일반 JSON Schema 딕셔너리와 직접 작성한 검증 함수도 각각 `schema`, `validator`에 전달할 수 있습니다.
- `example`은 문서용 값이며 자동 실행·검증하지 않습니다.
- `format`의 기본값은 `application/json`입니다. 문서의 미디어 타입만 바꾸며 브로커 코덱은 별도 설정입니다.
- Run의 `name`은 AsyncAPI Operation 키와 Metrics 작업 키에 함께 사용합니다.
  생략하면 `모듈명.__qualname__`을 사용하며, Run의 `description`은 AsyncAPI Operation에 표시됩니다.
  명시적 이름은 `[A-Za-z0-9_.-]+` 형식이며 공백·한국어는 허용하지 않습니다.
  대소문자와 입력값을 그대로 보존합니다.
- 실행 순서는 초기화 훅 → 요청 검증 → `run()` → 응답 검증 → 완료 훅 → 응답 발행·ACK입니다.

검증 예외는 작업 실패로 처리되어 오류 훅과 `on_error` 정책을 따릅니다.
예제의 `Reject()`는 잘못된 입력을 무한 재시도하지 않게 합니다. DLQ에 보관하려면
`Subscription(error=...)`도 지정하고 `declare()`로 해당 큐를 준비하세요.
스키마·예제는 Inspector의 AsyncAPI와 콘솔에 표시되며,
사용자 정의 Validator 패턴을 자동으로 JSON Schema로 역변환하지는 않습니다.

## 상태 확인과 작업 콘솔

선택 기능인 Inspector는 Python 표준 라이브러리 HTTP 서버를 사용합니다.
다음 코드를 Worker 실행 전에 구성하고 `Worker(..., inspector=inspector)`로 전달하세요.
앞의 `worker.py`에서 `Connection`, `Configuration` import를 그대로 사용합니다.

```python
from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import (
  Console,
  Dashboard,
  HealthCheck,
  Metrics,
  Specifications,
)


def create_connection():
  return Connection(Configuration(
    host='127.0.0.1',
    port=5672,
    username='guest',
    password='guest',
  ))


inspector = Inspector(
  host='127.0.0.1',
  port=9999,
  exts=(
    HealthCheck('/status'),
    Metrics('/metrics'),
    Dashboard('/dashboard'),
    Specifications('/asyncapi.json'),
    Console(
      '/console',
      broker=create_connection,
      title='DefStream',
    ),
  ),
)
```

| 경로 | 용도 |
| --- | --- |
| `/status` | 구독 준비와 소비자 루프 응답성을 검사. 정상 200, 시작·종료·응답 불가 상태 503 |
| `/metrics` | `defstream_` 접두사의 Prometheus 지표 |
| `/dashboard` | 처리 성공·실패·처리량·소요 시간. `Metrics` 하나와 함께 등록 |
| `/asyncapi.json` | 등록 작업의 요청·응답 계약을 AsyncAPI JSON으로 제공 |
| `/console` | 작업 목록·스키마 조회, JSON 메시지 발행, 지원 브로커의 RPC 실행 |

기본으로 등록되는 경로는 없습니다. 지표는 한 Worker 기준이며 재시작 시 초기화됩니다.
처리 횟수는 재시도와 훅을 포함한 실행 시도 기준이지 고유 메시지 수나 ACK 수가 아닙니다.
대시보드는 최근 1초·60초 구간을 제공하지만 장기 지표 저장소를 대신하지 않습니다.
응답 계약을 선언해도 Redis에 RPC 기능이 생기지는 않습니다.

**접근을 제한하세요.** 위 콘솔 예제는 인증 없이 실제 작업을 발행합니다.
인증이 필요하면 `Console`에 `token=`으로 무작위 16자 이상 토큰을 전달하고,
브라우저에서 입력하세요. 토큰은 환경변수나 비밀 저장소에서 읽으세요.
다른 기본 엔드포인트는 인증되지 않으므로 신뢰할 수 있는 관리망이나 루프백에만 바인딩하고,
원격 접근은 HTTPS 역방향 프록시 및 별도 접근 제어를 사용하세요.
Inspector 자체는 TLS를 제공하지 않으며 공개 웹 서버가 아닙니다.
콘솔의 연결 팩터리는 호출마다 새 연결을 반환해야 하고 Worker 연결을 공유하면 안 됩니다.

Console의 `broker` 인자는 `DefStream.Broker.BrokerFactory` 계약을 사용합니다.
이 계약의 `__call__() -> Connection`은 인자 없이 새 연결을 반환합니다.
위의 `create_connection` 같은 함수나 람다도 그대로 전달할 수 있으며,
클래스로 구현할 때는 `BrokerFactory`를 상속하고 `__call__`을 구현할 수 있습니다.

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

- [Sample.py](./samples/Broker/RabbitMQ/Sample.py)
- [Sample.Stream.py](./samples/Broker/RabbitMQ/Sample.Stream.py)
- [Sample.RPC.py](./samples/Broker/RabbitMQ/Sample.RPC.py)

## Redis 사용 방법

Python 3.9 이상과 Redis 6.2 이상이 필요하며 redis-py의 Streams를 사용합니다. Pub/Sub이나 List 기반 큐가 아닙니다.

### 메시지 보내고 받기

로컬 Redis가 `127.0.0.1:6379`에서 실행 중이라고 가정합니다.
예제는 `defstream.example.redis` 스트림과 `DefStream` 그룹을 만들고 실행 후에도 유지합니다.

```python
from DefStream.Broker.Implements.Redis import Configuration, Connection


connection = Connection(Configuration(
  host='127.0.0.1',
  port=6379,
))
try:
  connection.connect()
  connection.create_queue(
    'defstream.example.redis',
    group='DefStream',
  )
  queue = connection.queue(
    'defstream.example.redis',
    group='DefStream',
  )
  message_id = queue.send({'message': 'Hello, DefStream!'})
  print(message_id)
  event = queue.pop(timeout=1000)
  if event is not None:
    print(event.id, event.body)
    event.ack()
finally:
  connection.close()
```

`connect()`는 PING으로 연결을 확인하며 오류를 숨기지 않습니다.
기본 코덱은 UTF-8 JSON이며 스트림의 `body` 필드에 메시지 전체를 저장합니다.
기존 field-per-value 방식 스트림과는 호환되지 않습니다.
사용자 정의 코덱은 `Configuration(encode=..., decode=...)`로 지정합니다.

### 연결 설정

| 옵션 | 기본값·의미 |
| --- | --- |
| `host`, `port` | `127.0.0.1`, `6379` |
| `username`, `password` | 인증 정보. 비밀번호만 사용하는 인증도 지원 |
| `secure` | TLS 사용 여부, 기본값 `False` |
| `database` | DB 번호, 기본값 0 |
| `type` | `ConnectionType.Pool` 또는 `ConnectionType.Cluster` |
| `max` | 최대 연결 수, 기본값 10 |
| `timeout` | 연결·소켓 제한 시간, **초** 단위, 기본값 5 |

`ConnectionType`은 어댑터 패키지에서 가져옵니다.
기본 Pool은 redis-py 연결 풀을 사용합니다.
Cluster는 Redis Cluster를 사용하며 `database=0`이어야 합니다.
운영 인증 정보는 환경변수·비밀 저장소에서 읽으세요.

### 로깅

`Connection`, `Consumer`, `Queue`, `Event`는 각각
`DefStream.Broker.Implements.Redis.<클래스명>` 로거를 사용하며 상위
`DefStream` 로거와 루트 로거로 전파합니다. 라이브러리는 핸들러나 로그 수준을
설정하지 않으므로 애플리케이션에서 필요한 출력 대상과 필터를 구성하세요.
기록에는 메시지 본문과 인증 정보가 포함되지 않으며, 오류 로그 후에도 기존
예외는 호출자에게 전파됩니다. 호출자가 같은 실패를 다시 기록할 수 있으므로
traceback은 담당 경계 한 곳에서만 남기세요. 예제는 실행 진입점에서만 `Sample`
및 Redis 로거 계층을 DEBUG로 출력하도록 설정합니다.

### 소비자 그룹과 이력

- `connection.queue(name, group='DefStream')`과 `connection.stream(name, group='DefStream')`은
  같은 스트림 기반 `Queue`를 반환합니다.
- `create_queue()`와 `create_stream()`은 스트림과 그룹을 준비합니다.
  발행·구독 시에도 필요한 리소스를 지연 생성할 수 있습니다.
- 새 그룹은 `0-0`부터 시작합니다. 구독 전에 발행된 메시지도 그룹에서 소비할 수 있습니다.
- 같은 그룹의 소비자는 메시지를 나눠 받고, 다른 그룹은 각각 메시지를 받습니다.
  기존 배포의 처리 위치와 pending 상태를 이어가려면 그룹 이름을 유지하세요.
- `pop(timeout=1000)`은 그룹 메시지 하나를 기다립니다. 제한 시간은 **밀리초**이며,
  양수 제한 시간에 메시지가 없으면 `None`을 반환합니다. `None` 또는 `0`은 무기한 대기입니다.

그룹 상태를 바꾸지 않고 스트림 이력을 읽을 수도 있습니다.
다음은 위 직접 연결 예제에서 `connect()`와 `close()` 사이에 사용하는 코드입니다.

```python
for event in connection.stream('defstream.example.redis').read(
  offset=0,
  timeout=1000,
):
  print(event.id, event.body)
```

`read()`는 기존 이력과 새 메시지를 읽으며 제한 시간은 총 밀리초입니다.
`None` 또는 `0`이면 계속 대기합니다. 읽기를 끝내려면 이터레이터를 닫으세요.
이력 이벤트는 그룹 처리용이 아니므로 ACK하거나 재큐잉하지 않습니다.
문자열 스트림 ID를 `offset`에 전달하면 해당 ID **이후**부터 읽습니다.

### Worker로 작업 처리하기

다음 실행 파일은 작업 스트림과 그룹을 준비한 뒤 소비합니다.

```python
from signal import SIGINT, signal

from DefStream.Broker.Policies import Reject
from DefStream.Broker.Implements.Redis import Configuration, Connection, Subscription
from DefStream.Worker import Run, ThreadPool, Worker, WorkerSetup, declare


class Add(
  Run,
  parameters=Subscription(
    queue='defstream.example.redis.add',
    group='DefStream',
  ),
  on_error=Reject(),
):
  def run(
    self,
    a: int,
    b: int,
  ):
    print(a + b)


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
      port=6379,
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

다른 프로세스에서 같은 스트림에 `{'a': 10, 'b': 20}`을 보내면 처리됩니다.
Worker는 실행과 완료 훅이 끝난 뒤 ACK합니다. 반환값을 RPC 응답으로 보내지는 않습니다.
`on_error` 생략 시 기본값은 `Requeue()`이며 예제는 `Reject()`를 명시합니다.
Task API인 `emit(body, task=Add, broker=connection)`도 사용할 수 있고,
연결은 호출자가 열고 닫아야 합니다.

기존 작업 발행 함수와 `connection.send(body, parameters)`는 `emit`으로 이름이
바뀌었습니다. `connection.emit(body, parameters)`를
사용하세요. 저수준 `queue.send(body)`는 그대로입니다.

### ACK, 거부와 재시도

| 동작 | 효과 |
| --- | --- |
| `ack()` | 그룹에서 XACK. 스트림 이력은 유지 |
| `reject()` / `Reject()` | 그룹에서 XACK. 기본 DLQ 없음, 이력 유지 |
| `nack()` / `Requeue()` | 새 메시지를 추가하고 원래 pending 메시지를 ACK |

재큐잉은 단일 키 Lua 스크립트로 원자적으로 처리하지만, 복사본은 새 스트림 ID를 가집니다.
**새 메시지는 실패한 그룹뿐 아니라 다른 모든 그룹에도 보입니다.**
그룹별로 격리된 재시도가 필요하면 별도의 재시도 스트림을 설계하세요.
자동 재시도 횟수 제한이나 기본 오류 스트림은 제공하지 않습니다.

직접 소비자를 생성할 때 다음 설정을 사용할 수 있습니다.

| 옵션 | 의미 |
| --- | --- |
| `connection.consumer(qos=1)` | 모든 구독에 걸친 로컬 미확인 메시지 수 제한 |
| `reclaim_idle=60000` | 유휴 pending 항목을 재확보하기까지의 밀리초, 기본값 60초 |
| `reclaim_idle=None` | 자동 pending 복구 비활성화 |

기본 Worker는 기본 소비자 설정을 사용합니다.
긴 작업은 처리 중에도 다른 소비자가 재확보할 수 있으므로 작업 시간과 복구 정책을 함께 설계하세요.
종료 시 끝나지 않은 작업은 ACK하지 않고, 나중에 복구할 수 있도록 pending 상태로 남깁니다.

### 운영 시 주의사항

- 최소 한 번(at-least-once) 전달입니다. 부수 효과가 중복 실행되어도 안전하도록 설계하세요.
- ACK·거부 후에도 이력이 남고 재시도는 항목을 추가합니다. 보존 정책을 외부에서 관리하세요.
  처리 중인 pending 항목을 무분별하게 trim하지 마세요.
- `delete_queue()`와 `delete_stream()`은 스트림 키 자체를 삭제합니다.
  공유 스트림·그룹을 정리 코드에서 무단 삭제하지 마세요.
- 연결·디코딩·핸들러 오류는 호출자에게 전파하며 자동 재연결하지 않습니다.
- Exchange와 RPC는 지원하지 않습니다. `request()`와 콘솔 RPC를 사용할 수 없습니다.
- Redis Cluster 구성은 지원하지만 현재 통합 테스트 대상은 standalone Redis입니다.
- Worker의 연결과 풀은 한 번의 실행 전용입니다. `worker.stop()`은 작업을 기다린 뒤 자원을 닫습니다.

### 샘플

- [Sample.py](./samples/Broker/Redis/Sample.py)
- [Sample.Stream.py](./samples/Broker/Redis/Sample.Stream.py)

## 브로커 선택과 운영 주의사항

| 기능 | RabbitMQ | Redis Streams |
| --- | --- | --- |
| 큐 송수신 | 지원 | 스트림과 소비자 그룹 사용 |
| Exchange 라우팅 | 지원 | 미지원 |
| 스트림 이력 읽기 | 지원 | 지원 |
| 작업 RPC | 지원 | 미지원 |
| 오류 메시지 목적지 | 명시적으로 선언한 DLQ | 기본 제공하지 않음 |

- RabbitMQ 연결과 리소스는 소유 스레드에서만 사용하세요. 소비자 연결을 작업 스레드와 공유하지 마세요.
- Redis는 **6.2 이상**이 필요합니다. 같은 소비자 그룹은 메시지를 나눠 받고, 다른 그룹은 각각 받습니다.
- Redis 재큐잉은 복사본을 추가하고 원본을 ACK하므로 새 메시지는 다른 그룹에도 보입니다.
- Redis는 기본 60초 유휴 pending 메시지를 재확보합니다. 긴 작업에서는 다른 소비자와 중복 실행될 수 있습니다.
  직접 소비자를 만들 때 `reclaim_idle`을 조정하거나 `None`으로 끌 수 있으며, 기본 Worker는 기본값을 사용합니다.
- Redis ACK·거부는 이력을 삭제하지 않습니다. 보존 정책은 외부에서 관리하고 pending 메시지 삭제를 피하세요.
- 네트워크 오류의 자동 재연결이나 exactly-once 실행을 가정하지 마세요.
  애플리케이션에서 재시작 전략, 멱등성, 재시도·오류 큐 정책을 설계하세요.

## 예제와 라이선스

- [브로커 없이 실행하는 Worker 예제](./samples/Worker/Sample.py)
- [RabbitMQ Worker·RPC 클라이언트 예제](./samples/Worker/RabbitMQ)
- [Redis Worker 예제](./samples/Worker/Redis/Sample.py)
- [릴리즈와 변경 내역](https://github.com/yong5eon/DefStream/releases)

GNU GPL v3 라이선스를 사용합니다. 자세한 조건은 [LICENSE](./LICENSE)를 확인하세요.
