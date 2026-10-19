# DefStream

[한국어](./README.md) | **English**

**Just def.**<br>
**Let workers do the work.**<br>
**You don't need to await this.**

DefStream is a synchronous task-processing library that consumes broker messages
and executes ordinary Python task methods in a thread or process pool.
Configure execution, acknowledgements, failure policies, and monitoring without
`async` / `await`.

- **Task definitions**: declare a subscription and handler in a `Run` class.
- **Parallel execution**: choose `ThreadPool` or `ProcessPool`.
- **Broker choice**: install RabbitMQ and Redis Streams adapters separately.
- **Request/reply**: receive task return values through RabbitMQ RPC.
- **Operations**: optionally enable HTTP health checks, Prometheus metrics, a dashboard, and a task console.
- **Input/output contracts**: define schemas and runtime validators and expose AsyncAPI documentation.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Tasks and message handling](#tasks-and-message-handling)
- [Execution pools and shutdown](#execution-pools-and-shutdown)
- [Lifecycle hooks](#lifecycle-hooks)
- [Request/reply contracts and validation](#requestreply-contracts-and-validation)
- [Health checks and task console](#health-checks-and-task-console)
- [Broker selection and operational considerations](#broker-selection-and-operational-considerations)
- [Examples and license](#examples-and-license)

## 로깅 지원

클래스별 표준 로거와 사용자 주도 핸들러 설정을 지원합니다.
샘플은 `Sample` 및 `DefStream` 계층만 출력하며, ProcessPool 자식은 별도 setup 훅으로
출력을 설정합니다. Worker의 시작 배너는 유지됩니다.
로거 이름, 선택 수신, 예외 메시지 주의사항과 프로세스 설정은 [로깅 안내](./README.md#로깅)를 참고하세요.

## Installation

Requires Python **3.9 or newer**. Prepare the broker server you intend to use.

```shell
python -m pip install "DefStream[RabbitMQ]"
```

Choose Redis or both adapters as needed:

```shell
python -m pip install "DefStream[Redis]"
python -m pip install "DefStream[RabbitMQ,Redis]"
```

For the core alone, use `python -m pip install DefStream`.
The core has no broker client dependencies. Installing an adapter directly also installs the core.

| Distribution | Python import path | Guide |
| --- | --- | --- |
| `DefStream` | `DefStream` | This document |
| `DefStream-RabbitMQ` | `DefStream.Broker.Implements.RabbitMQ` | [RabbitMQ guide](https://github.com/yong5eon/DefStream-RabbitMQ/blob/master/README.en.md) |
| `DefStream-Redis` | `DefStream.Broker.Implements.Redis` | [Redis guide](https://github.com/yong5eon/DefStream-Redis/blob/master/README.en.md) |

## Quick start

These examples assume a local RabbitMQ server at `127.0.0.1:5672`.
Save the following three files in the same directory. The `guest` credentials
are for local examples only; use a dedicated account and environment variables
or a secret store in production.

### 1. Define a task: `tasks.py`

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

`parameters` selects the task's queue. A body of `{'a': 10, 'b': 20}` becomes
`run(a=10, b=20)`. This example rejects failures instead of retrying them and
declares an error queue to receive rejected messages.

### 2. Run the Worker: `worker.py`

`Worker` accepts `DefStream.Broker.Connection` directly.
The connection contract only requires `connect()` and `close()`. The worker checks
for `GetConsumer` support internally when it runs. A broker that cannot create
a consumer raises `TypeError`; no worker-specific connection type is needed.

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

The Worker opens its broker connection, runs `Prepare` to declare the queue
and error queue, then starts consuming. Defining a `Run` does not register it:
call `worker.add()` explicitly.

### 3. Send messages: `client.py`

Run this in another terminal while the Worker is running.

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

`emit()` and `request()` **each publish a separate task**. This example performs
the addition twice; `request()` returns `30`. The request timeout is in seconds
and does not cancel work that has already been delivered.

## Tasks and message handling

### Task-directed API

| Function | Purpose | Connection ownership |
| --- | --- | --- |
| `declare(task=..., broker=...)` | Declare task queues and subscription resources | Caller connects and closes |
| `emit(body, task=..., broker=...)` | Publish a one-way message to a task | Caller connects and closes |
| `request(body, task=..., broker=..., timeout=5)` | Request a task result synchronously | Caller connects and closes; RabbitMQ only |

Import these functions from `DefStream.Worker`. They do not connect or close
the supplied connection. Neither `emit()` nor `request()` declares destinations.
Call `declare()` in the receiving Worker's setup or a separate provisioning step.
Reuse a connection for multiple publications on its owning thread.

All three helpers accept the common `Connection` type and check declaration,
emission, or RPC support internally. Unsupported operations raise `NotImplementedError`.
The task helper and connection method previously named `send` are now named `emit`.
Custom brokers should use `Emittable.emit` instead of `TaskSender.send` for task emission.
Low-level `Sendable.send()` and RPC `Callable.call()` on queues, exchanges, and streams
remain unchanged.

Task bodies must be **mappings with string keys**. Return values must be
serializable by the adapter. A Worker cannot register multiple tasks for the
same queue: routing selects tasks by queue, not by a type field in the message.

### Task priorities

For RabbitMQ classic queues, define both the default message `priority` and queue
`max_priority` in the RabbitMQ `Subscription` supplied as the task's `parameters`.
There is no separate `priority` setting on `Run`.
`declare()` reads these settings to provision the priority queue.

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


# broker is a RabbitMQ Connection connected by the caller.
declare(
  task=Add,
  broker=broker,
)
emit(
  {'a': 10, 'b': 20},
  task=Add,
  broker=broker,
)
# RPC requires a separately running Worker.
result = request(
  {'a': 10, 'b': 20},
  task=Add,
  broker=broker,
  priority=5,
)
```

- Omitting the call's `priority` or passing `None` uses the task default.
  An explicit `0` overrides the default with the lowest priority.
- Setting only the task default sets the queue maximum to RabbitMQ's limit of
  `255`. Setting only the maximum leaves the default as `None`; without a
  per-call value either, the message priority property is omitted.
- Values above the task maximum, negative values, non-integers, and `bool` are rejected.
- Specifying priority only at call time validates only the broker range `0..255`.
  The caller must provision a priority queue and respect its actual maximum.
- Child tasks inherit settings and may override them with valid values, but cannot
  clear them.
- Requesting priorities with Redis raises `NotImplementedError`.
  Calls without priorities retain existing Redis behavior.
- Priority affects delivery of waiting messages within the same queue. It does not
  preempt delivered or running tasks or guarantee execution and completion order.

### Success, failures, and retries

- ACK follows successful execution and completion hooks. RabbitMQ RPC also publishes the reply before ACK.
- Failures use the task's `on_error` policy. The default is `Requeue()`; choose `Reject()` explicitly if needed.
- Both policies can be imported from `DefStream.Broker.Policies`.
- Rejection is broker-specific: RabbitMQ dead-letters to a configured DLQ or discards the message;
  Redis acknowledges it for the group while preserving stream history.
- There is no automatic retry-count limit. Choose a policy that avoids endless redelivery of permanently invalid messages.
- Publication and ACK are not one transaction. **Make tasks idempotent and safe to execute more than once.**

The common resource operations below apply when accessing a broker directly.
Not every resource supports every operation.

Use `isinstance` or `issubclass` with `GetExchange`, `GetQueue`, `GetStream`,
or `GetConsumer` to check whether a connection provides `exchange()`, `queue()`,
`stream()`, or `consumer()`, respectively. Import these contracts from `DefStream.Broker`.

| Method | Purpose | Timeout unit |
| --- | --- | --- |
| `send(body)` | Publish a message | Adapter configuration |
| `call(body, timeout=5)` | Synchronous RPC | Seconds |
| `pop(timeout=1000)` | Receive one message | Milliseconds |
| `read(offset=0, timeout=1000)` | Read stream history and new messages | Milliseconds |

For `pop()` and `read()`, `None` or `0` waits indefinitely.
Settle directly consumed processing events with `ack()`, `nack()`, or `reject()`.
Redis history reads are separate from consumer-group processing and cannot be ACKed.
RabbitMQ stream reads are ACKed automatically when iteration advances.

## Execution pools and shutdown

| Pool | Typical use | Considerations |
| --- | --- | --- |
| `ThreadPool(4)` | I/O-bound tasks | Synchronize state shared across execution threads |
| `ProcessPool(4)` | CPU-bound tasks | Classes, inputs, results, and hooks must be picklable |

Import both pools from `DefStream.Worker`. Without an explicit size, they use
the CPU count. Capacity includes submitted, unfinished tasks; there is no
unbounded waiting queue. A full pool causes the Worker to NACK for redelivery.
RabbitMQ's per-task `Subscription.qos` limits unacknowledged deliveries, not pool size.

With `ProcessPool`, define classes and hooks at importable module scope and
create and run the Worker inside `if __name__ == '__main__':`.
Never pass broker connections or events to child processes.

`worker.stop()` stops receiving new work, waits for active tasks and message
settlement, then closes resources. There is currently no forced termination or
shutdown timeout. Register an application `SIGINT` handler as above for graceful
Ctrl+C shutdown. Each Worker, its connection, and its pool belong to a single
run: do not share them with another Worker or restart them.

## Lifecycle hooks

All hook interfaces are exported from `DefStream.Worker`.

| Scope | Hooks | Arguments and execution location |
| --- | --- | --- |
| Task | `RunSetup`, `RunComplete`, `RunError` | `Context`; context and result; context and exception. Inside the pool |
| Pool | `PoolSetup`, `PoolCleanup` | No arguments. Inside each execution thread/process |
| Worker | `WorkerSetup`, `WorkerCleanup` | Worker instance. Parent connection-owning thread |

Declare task hooks with `setups=`, `completes=`, and `errors=` on the `Run` class.
Pass `setups=` and `cleanups=` to Worker or pool constructors.
Each option accepts one hook or an ordered sequence of hooks.
Inspect call arguments through `Context.args` and `Context.kwargs`.

Pool execution environments start lazily and run their setup and cleanup once
per environment. Create and close environment-specific resources, such as DB
connections, there. Worker setup runs after broker connection and before
subscription; cleanup runs after pool shutdown and before consumer/broker closure.
Cleanup must tolerate partial initialization. Hooks are not guaranteed after
forced termination or process crashes.

`RunError` is execution-error code; `on_error` is the message-settlement policy.
Running an error hook does not turn failure into success. If a completion hook
publishes another task, create and close a separate connection in that hook's
thread/process. A later failure does not roll back messages already published.

## Request/reply contracts and validation

`Descriptor` **describes data structure**; `Validator` **validates and transforms
actual values**. Connect both to `Specification` to document and validate tasks.
Place the following examples in the same file, in order.

### 1. Describe a schema with Descriptor

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

`Object` describes an object, `Properties` its fields, and `Integer` an integer.
Fields such as `Integer` are required by default; use `required=False` to mark
an optional field. Use `String`, `Number`, `Boolean`, and `Array` for other types
and nested structures. Wrap a value in `Schema` before passing it to
`DumpSchema()` to obtain a plain JSON Schema dictionary.

This documents `a` and `b` as required integers but **does not validate messages
automatically**. Required fields, defaults, and ranges need corresponding
validation rules if they must also be enforced at runtime.

### 2. Validate values with Validator

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

- `Validator` applies patterns in order and returns the final value.
- `IsObject` checks for the `dict` type, then runs its nested required-key and field-type rules.
- `IsRequiredIn` raises `ValueError` for missing keys; `IsInteger` raises `TypeError`
  for wrong types, including the string `'10'` and boolean `True`.
- `IsMappingOf` validates/transforms configured fields and may update the dictionary
  in place. Pass a copy to preserve the original. It does not remove or reject
  unconfigured extra keys. Extra keys that do not match task arguments make the
  call fail; implement additional restrictions if needed.

### 3. Combine conversion and validation

To accept numeric strings, use an explicit conversion pattern instead of
`IsInteger`. This independent example converts a string to an integer and then
checks that it is non-negative.

```python
from DefStream.Validator import Validator
from DefStream.Validator.Patterns import IsGreaterEqualTo, ToInteger


non_negative_integer = Validator(
  ToInteger(),
  IsGreaterEqualTo(0),
)

print(non_negative_integer('10'))
```

The result is integer `10`, not a string. Invalid strings and negative values
raise `ValueError`. `ToInteger` handles Python numeric-literal strings and
differs from strict type checking. This converter does not change the strict
request validator above. To apply it to a field, set that field's value in
`IsMappingOf` to `non_negative_integer`.

### 4. Connect task request and response contracts

Replace the earlier `Add` with the following class using the schemas and
validators defined above. Once registered with the Worker, inputs are validated
before `run()`, and the return value before completion hooks.

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

- `schema` is documentation metadata: it accepts JSON Schema mappings, Descriptor values/conditions,
  and dataclass types, but does not itself validate values or instantiate models.
- `validator` is a callable validation/transformation function. Its returned value is used for execution.
  A request validator must still return a mapping with string keys.
- Plain JSON Schema dictionaries and custom validation functions can also be passed as `schema` and `validator`.
- `example` is documentation data and is not automatically executed or validated.
- `format` defaults to `application/json`. It changes documented media types, not broker codecs.
- Execution order: setup hooks → request validation → `run()` → response validation → completion hooks → reply/ACK.

Validation exceptions are task failures and follow error hooks and the `on_error`
policy. The example's `Reject()` avoids endlessly retrying invalid inputs.
To preserve failures in a DLQ, also configure `Subscription(error=...)` and
provision it through `declare()`. Schemas and examples appear in Inspector's
AsyncAPI and console; custom Validator patterns are not automatically
reverse-engineered into JSON Schema.

## Health checks and task console

Inspector is optional and uses a Python standard-library HTTP server.
Configure it before starting the Worker and pass `Worker(..., inspector=inspector)`.
This snippet reuses the `Connection` and `Configuration` imports from `worker.py`.

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

| Path | Purpose |
| --- | --- |
| `/status` | Check subscription readiness and consumer-loop responsiveness: 200 when healthy, 503 during startup/shutdown or when unresponsive |
| `/metrics` | Prometheus metrics with the `defstream_` prefix |
| `/dashboard` | Successes, failures, throughput, and duration; register with exactly one `Metrics` |
| `/asyncapi.json` | Registered task request/reply contracts as AsyncAPI JSON |
| `/console` | Browse tasks and schemas, send JSON messages, and execute RPC on supported brokers |

There are no default routes. Metrics describe one Worker and reset on restart.
Execution counts include retries and hooks, not unique messages or ACKs.
The dashboard provides recent 1-second and 60-second windows, not long-term storage.
Declaring a response contract does not add RPC support to Redis.

**Restrict access.** The console example above publishes real tasks without
authentication. For authentication, pass a random token of at least 16 characters
using `Console(token=...)` and enter it in the browser. Load the token from an
environment variable or secret store. Other built-in endpoints remain
unauthenticated: bind to loopback or a trusted management network, and use an
HTTPS reverse proxy with additional access control for remote access.
Inspector has no built-in TLS and is not a public web server.
The console's connection factory must return a new connection on every call,
never the Worker's connection.

Console's `broker` parameter uses the `DefStream.Broker.BrokerFactory` contract.
Its `__call__() -> Connection` takes no arguments and returns a new connection.
Functions such as `create_connection` above and lambdas remain valid without changes.
For a class-based factory, you can inherit `BrokerFactory` and implement `__call__`.

## Broker selection and operational considerations

| Feature | RabbitMQ | Redis Streams |
| --- | --- | --- |
| Queue messaging | Supported | Streams and consumer groups |
| Exchange routing | Supported | Not supported |
| Stream history reads | Supported | Supported |
| Task RPC | Supported | Not supported |
| Error destination | Explicitly declared DLQ | No built-in destination |

- Use RabbitMQ connections/resources only on their owning thread, not from task threads sharing the consumer connection.
- Redis requires **6.2 or newer**. Consumers in one group share deliveries; different groups each receive the stream.
- Redis requeue appends a copy and ACKs the original, making the new message visible to other groups too.
- Redis reclaims pending entries after 60 seconds of idle time by default. Another consumer may reclaim an active long task.
  Direct consumer users can adjust `reclaim_idle` or disable it with `None`; the default Worker uses the default setting.
- Redis ACK/rejection preserves history. Manage retention externally and avoid removing pending entries.
- Do not assume automatic network reconnection or exactly-once execution.
  Design application restart, idempotency, retry, and error-queue policies.

## Examples and license

- [Worker without an external broker](./sample/Worker/Sample.py)
- [RabbitMQ Worker and RPC client](./sample/Worker/RabbitMQ)
- [Redis Worker](./sample/Worker/Redis/Sample.py)
- [Releases and change history](https://github.com/yong5eon/DefStream/releases)

Licensed under GNU GPL v3. See [LICENSE](./LICENSE) for the terms.
