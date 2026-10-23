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
- **Broker choice**: RabbitMQ and Redis Streams implementations are included; install only the clients you need.
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
- [Logging](#logging)
- [Broker selection and operational considerations](#broker-selection-and-operational-considerations)
- [RabbitMQ usage](#rabbitmq-usage)
- [Redis usage](#redis-usage)
- [Examples and license](#examples-and-license)

## Logging

DefStream records messages through standard `logging` without configuring handlers,
formatters, or levels. Select the sources your application needs. The samples
output only the `Sample` and `DefStream` logger hierarchies, replacing their
`print()` calls with logging. The Worker's existing startup banner is still
printed regardless of logging configuration.

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

Apply filters to the **handler**, not the root logger. `Filter('DefStream')`
includes `DefStream` and names below `DefStream.`, but not `DefStreamExtra`.
This configuration is an example for a standalone application; it does not change
output from other handlers already installed. To receive only broker logs, select
`DefStream.Broker.Implements.RabbitMQ` or `DefStream.Broker.Implements.Redis`
instead of `DefStream`.

- The class member `logger` uses `DefStream.Worker`, `DefStream.Run`,
  `DefStream.Executor`, `DefStream.Pool`, `DefStream.ThreadPool`, and
  `DefStream.ProcessPool`.
- Shared Pool methods also use the concrete pool's logger member. User subclasses
  inherit the default name and can explicitly override `logger`.
- Inspector, Server, and RequestHandler share `DefStream.Inspector`.
  HTTP request receipt is DEBUG; response status and transmission results are INFO.
  Extension-specific logs use `DefStream.Inspector.Extensions.<extension name>`.
- Normal per-message processing is DEBUG, lifecycle events are INFO, events
  requiring attention are WARNING, and processing failures are ERROR.
  Bodies, results, and credentials are excluded from the default log context.
- Without any handlers, Python's `lastResort` may write WARNING and higher to
  stderr. Do not put sensitive values in user exception messages: failure
  tracebacks include those messages.

ProcessPool uses `spawn` child processes, so parent handlers are not automatically
inherited. To receive child logs, apply the same configuration in an importable
`PoolSetup` implementation and pass it through `ProcessPool(..., setups=...)`.
That configuration cannot capture DEBUG and INFO logs emitted before the child
setup hook runs. See
[LoggingSetup in the RabbitMQ task example](./samples/Worker/RabbitMQ/Tasks.py)
and the [parent/child configuration example](./samples/Worker/RabbitMQ/Worker.py).
In existing applications, choose the initialization location carefully to avoid
adding the same handlers repeatedly.

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
Both broker implementations are included in the DefStream distribution, but the default
installation has no broker client dependencies. The `RabbitMQ` extra installs `pika>=1.3.2`;
the `Redis` extra installs `redis>=5.1.1`.

| Installation choice | Python import path | Guide |
| --- | --- | --- |
| `DefStream` | `DefStream` | This document |
| `DefStream[RabbitMQ]` | `DefStream.Broker.Implements.RabbitMQ` | [RabbitMQ usage](#rabbitmq-usage) |
| `DefStream[Redis]` | `DefStream.Broker.Implements.Redis` | [Redis usage](#redis-usage) |

Separate releases of `DefStream-RabbitMQ` and `DefStream-Redis` are discontinued,
and their projects are scheduled for deletion. Backward compatibility with those
packages is not supported. Install the merged package in a new environment using
the commands above. To migrate an existing environment, first run
`python -m pip uninstall DefStream-RabbitMQ DefStream-Redis`, then reinstall the
merged DefStream. Do not install them together: they provide files at the same import paths.
For an existing environment, use
`python -m pip install --force-reinstall "DefStream[RabbitMQ,Redis]"`,
selecting extras for the brokers you actually use.

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

- `schema` is documentation metadata: it accepts JSON Schema mappings, Descriptor values/conditions,
  and dataclass types, but does not itself validate values or instantiate models.
- `validator` is a callable validation/transformation function. Its returned value is used for execution.
  A request validator must still return a mapping with string keys.
- Plain JSON Schema dictionaries and custom validation functions can also be passed as `schema` and `validator`.
- `example` is documentation data and is not automatically executed or validated.
- `format` defaults to `application/json`. It changes documented media types, not broker codecs.
- Run's `name` is used as both the AsyncAPI Operation key and the Metrics task key.
  When omitted, `module.__qualname__` is used; Run's `description` appears on the AsyncAPI Operation.
  Explicit names must match `[A-Za-z0-9_.-]+`; whitespace and Korean characters are not allowed.
  Names are case-sensitive and preserved exactly as provided.
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
  Metrics,
  Ping,
  Specifications,
  Status,
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
    Ping('/ping'),
    Metrics('/metrics'),
    Status('/status'),
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
| `/ping` | Check subscription readiness and consumer-loop responsiveness: 200 when healthy, 503 during startup/shutdown or when unresponsive |
| `/metrics` | Prometheus metrics with the `defstream_` prefix |
| `/status` | Successes, failures, throughput, and duration; register with exactly one `Metrics` |
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

## RabbitMQ usage

Requires Python 3.9 or newer and a reachable RabbitMQ server; uses Pika.

### Send and receive queue messages

This example uses a local RabbitMQ server's `guest` account. Use a dedicated
account and environment variables or a secret store in production.
It creates `defstream.example.rabbitmq` and leaves the queue in place.

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

The default codec serializes messages as JSON.
The `pop()` timeout is in **milliseconds**; a positive timeout returns `None`
if no delivery arrives. `None` or `0` waits indefinitely.
Call `ack()` on success, `nack()` for redelivery, or `reject()` to reject.
Rejected messages go to the broker-configured dead-letter destination or are
discarded when none is configured.

### Logging

`Connection`, `Consumer`, `Queue`, `Exchange`, `Stream`, and `Event` expose a class
member `logger` named `DefStream.Broker.Implements.RabbitMQ.ClassName`. Subclasses
inherit that logger unless they explicitly override it. The library adds no handlers
(including `NullHandler`), levels, or filters; propagation and `logging.lastResort`
keep their standard behavior.

Lifecycle and resource changes use INFO, per-message/RPC/settlement tracing uses DEBUG,
expected RPC anomalies use WARNING, and internal I/O or codec failures use ERROR.
Payloads, results, headers, credentials, exception text, and tracebacks are omitted.
Exceptions still propagate; application-side logging may duplicate a library record.
A publish return does not mean consumer processing completed, and an RPC response
timeout does not cancel delivered work.

The Python samples configure a root DEBUG console handler only in their main entry
points. Its filter accepts `Filter('Sample')` **or**
`Filter('DefStream.Broker.Implements.RabbitMQ')`, including dotted descendants only;
Pika and core logs are excluded. Applications configure their own handlers, levels,
and filters at a chosen ancestor (`DefStream`, `DefStream.Broker`, etc.) or class.

### Connection configuration

| Option | Meaning |
| --- | --- |
| `host`, `port` | RabbitMQ address and AMQP port |
| `username`, `password` | Credentials |
| `vhost` | Virtual host; defaults to `/` |
| `ssl` | Enable TLS; defaults to `False` |
| `timeout` | Blocked-connection timeout, in milliseconds |
| `heartbeat` | The current implementation passes `int(heartbeat * 2 / 1000)` seconds to Pika |
| `encode`, `decode` | Message codecs; JSON by default |

`timeout` is not a whole-operation deadline.
Configure and service connection heartbeats appropriately for task and idle periods.
Use connections and their resources **only on the owning thread**; do not
share them across threads or processes.

### Process tasks with a Worker

This executable example provisions a task queue and error queue, then consumes tasks.

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

Send `{'a': 10, 'b': 20}` to the same queue from another process.
The Worker ACKs after execution and completion hooks finish, and applies
the selected failure policy on error. Omitting `on_error` defaults to `Requeue()`.

`Subscription` options:

- `queue`: task queue name.
- `qos`: this subscription's unacknowledged-delivery limit. The consumer default
  is 1; 0 means unlimited. This is separate from shared Worker pool capacity.
- `error`: error queue to create and bind through `declare()`; a DLQ for rejected messages.
- `offset`: integer offset for RabbitMQ stream subscriptions.
- `max_priority`: maximum priority for a classic task queue; an integer in `1..255` or `None`.
- `priority`: default message priority; an integer in `0..max_priority` or `None`.
  Setting only this value sets `max_priority` to `255`.

Constructing a `Subscription` or calling `consumer.subs()` does not declare queues.
Task `declare()` provisions ordinary durable queues and an optional DLQ,
not stream queues or Exchange bindings. Incompatible existing queue options
fail explicitly; queues are not automatically deleted and recreated.

### Worker task priorities

Publish tasks with `DefStream.Worker.emit` or `connection.emit(body, parameters)`.
The task publication API is `emit`. Low-level `send()` and RPC `call()` on queues, exchanges,
and streams remain unchanged.

Set the default `priority` and queue `max_priority` together in the task's
`Subscription`. There is no separate `priority` setting on `Run`.

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

- The Worker API `declare(task=PriorityAdd, broker=connection)` declares the queue
  with `x-max-priority=5` while preserving existing DLQ settings.
- `emit(..., task=PriorityAdd, broker=connection)` and
  `request(..., task=PriorityAdd, broker=connection)` use the task default of `2`.
  Pass `priority=0` or another valid value to override it for an individual call.
- Setting only the default sets the queue maximum to `255`. Setting only the
  maximum leaves the default as `None`. Without a per-call value either, the AMQP
  priority property is omitted.
- Worker calls validate against the task's effective maximum. If priority is
  specified only at call time, only the `0..255` range is validated; the caller
  must provision a priority queue beforehand.
- The existing low-level `Queue.send`, `Exchange.send`, and `Queue.call` also
  accept `priority=`. These APIs do not receive a task definition and therefore
  do not validate against a task-specific maximum. They accept integers in
  `0..255` and reject `bool`.
- Larger maximum values increase resource costs; configure only the levels you need.
- Task definitions declaring the same queue must use the same maximum.
  Redeclaring an ordinary queue or a queue with a different maximum propagates
  a RabbitMQ error. Queues are not automatically deleted. Switch to a new queue,
  or preserve pending messages before safely recreating the queue and migrating
  producers and consumers together.
- Higher values are delivered first, but prefetched messages and running tasks
  are not preempted. Redelivery and multiple consumers prevent guarantees about
  completion order, and lower-priority messages can wait indefinitely.
  Streams and quorum queues are outside the scope of this feature.

### Synchronous RPC

Call a queue served by a running Worker to receive the result of `Run.run()`.
Use the following between `connect()` and `close()` in the direct-connection example.

```python
result = connection.queue('defstream.example.rabbitmq.add').call(
  {'a': 10, 'b': 20},
  timeout=5,
)
print(result)
```

- `timeout` is in **seconds**. Missing replies raise `TimeoutError`.
  This does not cancel delivered work or strictly bound total connection and cleanup time.
- Each call owns a dedicated connection and temporary reply queue, cleaned up on exit.
- Server rejection raises `DefStream.Broker.RemoteError`.
  Requeue can retry without sending a final error response.
- Reply publication and request ACK are not atomic. Handle duplicate execution with RPC too.

Applications sharing a `Run` class can also use the core helper
`request(body, task=Add, broker=connection, timeout=5)`.

### Exchanges and streams

- `connection.exchange(name)` provides `send()` and `call()`.
  `event=` selects the routing key. Declare the Exchange, queues, and bindings first.
- Exchange RPC routed to several queues can execute at every destination and
  returns only the first matching reply. Use a single destination for ordinary RPC.
- Configure routing with `create_exchange()`, `bind_exchange_to_queue()`, and
  `bind_exchange_to_exchange()`. Corresponding `delete_...` or `unbind_...` methods are available.
- Use `create_stream()` to provision a stream queue, then access
  `connection.stream(name)` with `send()` and `read(offset=0, timeout=1000)`.
  The read timeout is in milliseconds.
  Read events are ACKed automatically when iteration advances.
- `delete_queue()`, `delete_stream()`, and `delete_exchange()` remove resources;
  use them only for resources owned by your application.

### Operational considerations

- Design idempotent tasks for at-least-once delivery.
- Unlimited requeue can repeatedly execute permanently invalid messages. Plan DLQ and retry policies.
- Execute long tasks in the Worker's pool rather than on the consumer connection.
- When publishing from task hooks, create a separate producer connection inside the hook's thread/process.
- `worker.stop()` waits for in-flight tasks and ACKs before closing the connection and pool.
  There is no forced termination or shutdown timeout.

### Samples

- [Sample.py](./samples/Broker/RabbitMQ/Sample.py)
- [Sample.Stream.py](./samples/Broker/RabbitMQ/Sample.Stream.py)
- [Sample.RPC.py](./samples/Broker/RabbitMQ/Sample.RPC.py)

## Redis usage

Requires Python 3.9 or newer and Redis 6.2 or newer. Uses redis-py Streams, not Pub/Sub or list-based queues.

### Send and receive messages

This example assumes a local Redis server at `127.0.0.1:6379`.
It creates the `defstream.example.redis` stream and `DefStream` group and leaves
them in place.

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

`connect()` verifies connectivity with PING and propagates failures.
The default codec stores the entire message as UTF-8 JSON in a single `body`
stream field. Legacy field-per-value streams are not compatible.
Set custom codecs through `Configuration(encode=..., decode=...)`.

### Connection configuration

| Option | Default and purpose |
| --- | --- |
| `host`, `port` | `127.0.0.1`, `6379` |
| `username`, `password` | Credentials; password-only authentication is supported |
| `secure` | Enable TLS; defaults to `False` |
| `database` | Database number; defaults to 0 |
| `type` | `ConnectionType.Pool` or `ConnectionType.Cluster` |
| `max` | Maximum connections; defaults to 10 |
| `timeout` | Connect/socket timeout in **seconds**; defaults to 5 |

Import `ConnectionType` from the adapter package.
The default Pool mode uses redis-py's connection pool.
Cluster mode uses Redis Cluster and requires `database=0`.
Read production credentials from environment variables or a secret store.

### Logging

`Connection`, `Consumer`, `Queue`, and `Event` each use a class-level logger named
`DefStream.Broker.Implements.Redis.<ClassName>`. Records propagate to the parent
`DefStream` logger and the root logger. The library does not configure handlers
or logging levels; configure output destinations and filters in your application.
Records exclude message bodies and credentials, and existing exceptions still
propagate to callers after an error is logged. Since callers may log the same
failure again, keep traceback logging at the boundary responsible for that failure.
The examples configure output only at their execution entry points, selecting
the `Sample` and Redis logger hierarchies at DEBUG level.

### Consumer groups and history

- `connection.queue(name, group='DefStream')` and `connection.stream(name, group='DefStream')`
  return the same stream-backed `Queue` type.
- `create_queue()` and `create_stream()` prepare the stream and group.
  Publishing/subscribing can also create the required resources lazily.
- New groups start at `0-0`, so messages published before subscription can be consumed.
- Consumers in the same group share messages; separate groups each receive them.
  Preserve the group name to continue an existing deployment's position and pending state.
- `pop(timeout=1000)` waits for one group delivery. Its timeout is in **milliseconds**.
  A positive timeout returns `None` when no delivery arrives; `None` or `0` waits indefinitely.

Read stream history without changing group state using this snippet between
`connect()` and `close()` in the direct-connection example:

```python
for event in connection.stream('defstream.example.redis').read(
  offset=0,
  timeout=1000,
):
  print(event.id, event.body)
```

`read()` reads existing history and new messages with a total millisecond timeout.
`None` or `0` tails indefinitely. Close the iterator to stop reading.
History events are not group deliveries and cannot be ACKed or requeued.
A string stream ID as `offset` resumes **after** that ID.

### Process tasks with a Worker

This executable example prepares a task stream and group, then consumes tasks.

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

Send `{'a': 10, 'b': 20}` to the same stream from another process.
The Worker ACKs after execution and completion hooks finish; it does not return
the result as an RPC reply. The default failure policy is `Requeue()` if
`on_error` is omitted; this example selects `Reject()`.
You can also use the task API `emit(body, task=Add, broker=connection)`;
the caller must connect and close the connection.

The task helper and `connection.send(body, parameters)` have been renamed to `emit`.
Use `connection.emit(body, parameters)`.
Low-level `queue.send(body)` remains unchanged.

### ACK, rejection, and retries

| Operation | Effect |
| --- | --- |
| `ack()` | XACK for the group; preserves stream history |
| `reject()` / `Reject()` | XACK for the group; no built-in DLQ; preserves history |
| `nack()` / `Requeue()` | Append a new message and ACK the original pending entry |

Requeue uses an atomic single-key Lua script, but the copy has a new stream ID.
**The new message is visible to every group, not only the failing group.**
Use separate retry streams if retries need group isolation.
There is no automatic retry-count limit or built-in error stream.

Direct consumer users can configure:

| Option | Meaning |
| --- | --- |
| `connection.consumer(qos=1)` | Total local unacknowledged-delivery limit across subscriptions |
| `reclaim_idle=60000` | Idle milliseconds before pending-entry reclamation; defaults to 60 seconds |
| `reclaim_idle=None` | Disable automatic pending recovery |

The default Worker uses the default consumer settings.
Another consumer may reclaim a long task while it is still running; plan task
duration and recovery together. Shutdown leaves unfinished deliveries pending,
without ACK, for later recovery.

### Operational considerations

- Delivery is at least once. Make side effects safe to execute more than once.
- ACK/rejection preserves history; retries add entries. Manage retention externally
  and do not indiscriminately trim pending entries.
- `delete_queue()` and `delete_stream()` delete the stream key itself.
  Do not remove shared streams/groups in cleanup code without ownership.
- Connection, decoding, and handler failures propagate; there is no automatic reconnection.
- Exchanges and RPC are not supported. Do not use `request()` or console RPC.
- Redis Cluster is implemented, but current integration tests cover standalone Redis.
- The Worker's connection and pool belong to one run. `worker.stop()` waits for tasks and closes resources.

### Samples

- [Sample.py](./samples/Broker/Redis/Sample.py)
- [Sample.Stream.py](./samples/Broker/Redis/Sample.Stream.py)

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

- [Worker without an external broker](./samples/Worker/Sample.py)
- [RabbitMQ Worker and RPC client](./samples/Worker/RabbitMQ)
- [Redis Worker](./samples/Worker/Redis/Sample.py)
- [Releases and change history](https://github.com/yong5eon/DefStream/releases)

Licensed under GNU GPL v3. See [LICENSE](./LICENSE) for the terms.
