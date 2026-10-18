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
- **브로커 선택**: RabbitMQ와 Redis Streams 어댑터를 별도로 설치합니다.
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
- [브로커 선택과 운영 주의사항](#브로커-선택과-운영-주의사항)
- [예제와 라이선스](#예제와-라이선스)

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
코어에는 브로커 클라이언트가 포함되지 않습니다. 어댑터를 직접 설치해도 코어가 함께 설치됩니다.

| 배포 패키지 | Python import 경로 | 사용 안내 |
| --- | --- | --- |
| `DefStream` | `DefStream` | 이 문서 |
| `DefStream-RabbitMQ` | `DefStream.Broker.Implements.RabbitMQ` | [RabbitMQ 안내](https://github.com/yong5eon/DefStream-RabbitMQ#readme) |
| `DefStream-Redis` | `DefStream.Broker.Implements.Redis` | [Redis 안내](https://github.com/yong5eon/DefStream-Redis#readme) |

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
from DefStream.Worker import request, send
from tasks import Add


connection = Connection(Configuration(
  host='127.0.0.1',
  port=5672,
  username='guest',
  password='guest',
))
try:
  connection.connect()
  message_id = send(
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

`send()`와 `request()`는 **각각 별도의 작업을 발행**합니다. 위 예제는 덧셈을 두 번 실행하며,
`request()`의 결과는 `30`입니다. `request()`의 제한 시간은 초 단위이고,
시간이 초과되어도 이미 전달된 작업은 취소되지 않습니다.

## 작업과 메시지 처리

### 작업을 대상으로 하는 API

| 함수 | 역할 | 연결 관리 |
| --- | --- | --- |
| `declare(task=..., broker=...)` | 작업의 큐·구독 리소스 선언 | 호출자가 연결·종료 |
| `send(body, task=..., broker=...)` | 작업 목적지로 단방향 메시지 발행 | 호출자가 연결·종료 |
| `request(body, task=..., broker=..., timeout=5)` | 작업 결과를 동기 RPC로 요청 | 호출자가 연결·종료; RabbitMQ만 지원 |

세 함수는 `DefStream.Worker`에서 가져옵니다. 전달된 연결을 자동으로 열거나 닫지 않으며,
`send()`와 `request()`는 목적지를 자동 선언하지 않습니다.
수신 Worker 또는 별도의 준비 단계에서 먼저 `declare()`를 호출하세요.
하나의 연결을 같은 소유 스레드에서 여러 발행에 재사용할 수 있습니다.

작업 본문은 **문자열 키를 가진 매핑**이어야 하며, 반환값은 어댑터가 직렬화할 수 있어야 합니다.
하나의 Worker에서는 같은 큐에 여러 작업을 중복 등록할 수 없습니다.
메시지 유형을 보고 여러 `Run` 중 하나를 고르는 방식이 아니라 큐별로 작업을 선택합니다.

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
    description='Add two integers',
  ),
  response=Specification(
    schema=response_schema,
    validator=response_validator,
    example=30,
  ),
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

- [브로커 없이 실행하는 Worker 예제](./sample/Worker/Sample.py)
- [RabbitMQ Worker·RPC 클라이언트 예제](./sample/Worker/RabbitMQ)
- [Redis Worker 예제](./sample/Worker/Redis/Sample.py)
- [릴리즈와 변경 내역](https://github.com/yong5eon/DefStream/releases)

GNU GPL v3 라이선스를 사용합니다. 자세한 조건은 [LICENSE](./LICENSE)를 확인하세요.
