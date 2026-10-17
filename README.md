# PinkStream

## Installation

```shell
pip install PinkStream
pip install "PinkStream[RabbitMQ]"
pip install "PinkStream[Redis]"
pip install "PinkStream[RabbitMQ,Redis]"
```

The base package has no broker client dependencies. Extras install `pika` and/or
`redis`; adapter source files are always included. Import only the adapters whose
extras are installed. For development, use `pip install -e ".[RabbitMQ,Redis]"`.

```python
from PinkStream.Worker import Worker
from PinkStream.Broker.Implements.RabbitMQ import Connection as RabbitConnection
```

There is no combined `PinkStream.Broker.Broker` interface. Implementations expose
a concrete `Connection` class without a `Broker` compatibility alias.

Create broker connections directly with the implementation's configuration and
call `connect()` before use. Call `close()` when finished. Connection registries
or helpers, if needed, belong in application code.

RabbitMQ resource methods use snake_case: `create_exchange`, `delete_exchange`,
`bind_exchange_to_exchange`, `unbind_exchange_to_exchange`, `create_queue`,
`delete_queue`, `bind_exchange_to_queue`, `unbind_exchange_to_queue`,
`create_stream`, and `delete_stream`. The former camelCase names are removed.

## Connection capabilities

`PinkStream.Broker.Connection` defines independent `typing.Protocol` contracts,
also exported from `PinkStream.Broker`. Implementations explicitly inherit only
the capabilities they provide:

| Protocol | Contract | RabbitMQ | Redis |
| --- | --- | --- | --- |
| `Connection` | `connect()`, `close()` | Yes | Yes |
| `GetExchange` | `exchange(name) -> Sendable` | Yes | No |
| `GetQueue` | `queue(name) -> Sendable` | Yes | Yes |
| `GetStream` | `stream(name) -> Sendable` | Yes | Yes |
| `GetConsumer` | `consumer(handler=None) -> Consumer` | Yes | Yes |

For example, RabbitMQ's Connection inherits `Connection`,
`GetExchange`, `GetQueue`, `GetStream`, and
`GetConsumer`. Redis omits GetExchange and uses its Queue for both
GetQueue and GetStream. Unsupported methods are absent rather than stubs raising
NotImplementedError.

These are plain Protocols without generic type parameters. Resource factories
promise the shared Sendable contract; concrete adapter methods retain their
specific return annotations for adapter-specific operations.
The common resource-name argument is positional-only to accommodate existing
adapter argument names; call `provider.queue('name')` through a generic contract.
Concrete implementations retain their existing keyword arguments and can add
optional settings. The contracts intentionally do not promise arbitrary
`**kwargs`. Missing connection/factory implementations prevent instantiation of
explicit subclasses through `@abstractmethod`.

`PinkStream.Worker.WorkerConnection` composes only Connection and
GetConsumer. Worker does not require queues, streams or exchanges.
Application connections can inherit these protocols explicitly or satisfy them
structurally without inheritance. Protocols are for static checking, not
`isinstance` capability checks.

Events (including the RPC failed-request wrapper), error policies and Redis JSON
codecs also explicitly inherit their existing Event, EventError, Encoder and
Decoder protocols. Message objects explicitly inherit Sendable, Callable,
Poppable and/or Readable as appropriate. Consumer, Run, configuration and
lifecycle-hook ABCs are retained: this change does not replace implementation
base classes or introduce new contracts for every callable.

## Message capabilities

Common message I/O contracts now live in `PinkStream.Broker.Protocol` and are
also exported from `PinkStream.Broker`:

| Protocol | Operation | Timeout |
| --- | --- | --- |
| `Sendable` | `send(body)` | Implementation-specific |
| `Callable` | `call(body, timeout=5)` | Seconds |
| `Poppable` | `pop(timeout=None)` | Milliseconds, preserving the existing API |
| `Readable` | `read(offset=0, timeout=None)` | Milliseconds, preserving the existing API |

These are structural `typing.Protocol` contracts, not runtime capability
checks. Implementations can expose additional optional broker-specific
arguments. The former common `Queue`, `Stream`, and `Exchange` base classes and
their modules have been removed. Concrete RabbitMQ classes retain their names:
Exchange is Sendable/Callable, Queue is Sendable/Callable/Poppable, and Stream is
Sendable/Readable. If `typing.Callable` is needed alongside the message
`Callable`, import the typing symbol as `PyCallable`.
`Event`, `EventHandler`, and `EventError` live together in `Broker.Event`
and are exported from `PinkStream.Broker`. EventHandler is a Protocol with
`__call__(event: Event) -> None`; explicitly inheriting handlers must implement
it. The former standalone `Broker.EventHandler` module has been removed.
`EventError` is a failure-policy contract, not an I/O capability.

## RabbitMQ RPC

Both RabbitMQ Queue and Exchange explicitly inherit `Callable` and implement
`call()` directly, including request publication, reply matching, and timeout
handling; there is no shared RabbitMQ Rpc module.
Obtain them through `broker.queue()` or `broker.exchange()` so the
decoder and dedicated RPC connection parameters are available.

For Exchange RPC, `event` selects the routing key, just as with `send()`:

```python
result = broker.exchange('operations').call(
	{
		'a': 10,
		'b': 20,
	},
	timeout=5,
	event='add',
)
```

Bind the exchange to the server queue before calling. An omitted event uses
the empty routing key. If the exchange routes to multiple queues, each may
execute the request; the client returns the first matching response, not an
aggregate. Use a single destination for ordinary RPC to avoid duplicate
side effects. Unroutable requests raise UnroutableError.

Use a queue obtained from `broker.queue(name)` for synchronous request/reply:

```python
result = broker.queue('add').call(
	{
		'a': 10,
		'b': 20,
	},
	timeout=5,
)
```

An ordinary Run serves both one-way messages and RPC requests. For RPC, its
return value (including None) is published after RunComplete hooks succeed,
then the request is ACKed. Run/hooks still execute in the selected pool;
response publication and message settlement execute on the connection owner
thread. No connection or event object is passed to ProcessPool children.

Each call opens its own connection and an exclusive, auto-delete response
queue, subscribes before publishing, and matches responses by correlation ID.
It closes that connection and response queue on success, timeout, or failure.
This initial implementation favors simple ownership over connection reuse:
there is no persistent Rpc client or asynchronous/multiplexed call API yet.
The queue object's existing connection/channel must still only be used by its
owner thread. Do not block the Worker consumer thread waiting for a call to
itself; invoke RPC from a separate client.

Requests use reply_to, correlation_id, and a TTL based on the remaining
timeout. Calls raise TimeoutError if no response arrives before the deadline;
this does not cancel work already delivered. Connection establishment uses
bounded socket/stack timeouts. Blocking broker operations and connection
cleanup mean the timeout is not a hard wall-clock limit on the entire call.
Both request and response publishers use confirms and mandatory routing.
An unavailable request queue raises Pika's UnroutableError instead of waiting.

Requeue sends no final response, allowing retry. When the selected EventError
calls reject(), the server sends an error envelope before rejecting the request
(and preserving configured dead-letter routing). The client raises
`PinkStream.Broker.RemoteError` with code `ProcessingError` and a generic message;
server exception details stay in server logs. Custom EventError implementations
must settle via the supplied event's ack/nack/reject methods.

A response destination may disappear when a caller times out. An unroutable
response is logged as a warning and the original request is settled normally;
the Worker keeps running. Other response publication/serialization failures
propagate without ACK/Reject, close the Worker, and leave unconfirmed requests
for broker redelivery. Response publication and request ACK are not atomic:
crashes can cause duplicate execution/replies, so side-effecting Runs must be
idempotent. RPC does not provide exactly-once delivery.

The RabbitMQ worker sample shares its Add and Divide tasks in
`sample/Worker/RabbitMQ/Tasks.py`. To try RPC, start
`sample/Worker/RabbitMQ/Worker.py`, then run
`sample/Worker/RabbitMQ/Client.py` in another terminal. The client uses
`request(body, task=..., broker=...)` with these shared tasks and shows
successful addition/division and a rejected division by zero.
For a standalone broker-only example, run
`sample/Broker/Implements/RabbitMQ/Sample.RPC.py`. It starts a responder on its
own connection/thread, demonstrates Queue and Exchange RPC plus RemoteError,
then removes only its uniquely named queue and exchange. A local RabbitMQ
server is required, but no separate Worker process is needed.

## Redis Streams

The Redis adapter uses Redis Streams, not Pub/Sub or lists. Install the Redis
extra and use Redis 6.2 or newer (including `XAUTOCLAIM` support):

```python
from PinkStream.Broker.Implements.Redis import (
	Connection,
	Configuration,
)

broker = Connection(Configuration(
	host='127.0.0.1',
	port=6379,
))
broker.connect()
try:
	queue = broker.queue('add')
	queue.send({
		'a': 10,
		'b': 20,
	})
	event = queue.pop(timeout=1000)
	if event is not None:
		print(event.id, event.body)
		event.ack()
finally:
	broker.close()
```

`broker.queue()` and `broker.stream()` return the same `Queue`, implementing
Sendable, Poppable and Readable. Resource methods are `create_queue`,
`delete_queue`, `create_stream`, and `delete_stream`. Creating a queue creates
the stream and consumer group; sending or subscribing can create them lazily.
Group creation starts at `0-0`, so messages published before subscription are
not lost. Use the concrete `Connection` class directly. Exchanges and RPC are not
supported; Redis Connection neither inherits GetExchange nor exposes `exchange()`.

Configuration supports username/password (including password-only auth),
`database`, TLS (`secure=True`), connection limit (`max`, default 10), and socket
timeout (`timeout`, seconds, default 5). The default `ConnectionType.Pool`
uses redis-py's managed connection pool; `ConnectionType.Cluster` uses
RedisCluster and requires database 0. Cluster mode is implemented but the local
integration suite exercises standalone Redis only. Connection failures propagate
from `connect()`, which verifies connectivity with PING.

Bodies use a single stream field named `body` containing UTF-8 JSON, preserving
nested mappings, lists, numbers, booleans and null. Pass callable `encode` and
`decode` configuration values for a different byte codec. Legacy field-per-value
streams are not wire-compatible and are not decoded using `eval`.

`pop(timeout=...)` waits for one group delivery; timeout is in milliseconds.
`None` or zero waits indefinitely, matching the existing RabbitMQ convention.
Positive timeouts return None when no delivery arrives.
`read(offset=0, timeout=...)` yields history followed by new events until its total
millisecond timeout; None or zero tails indefinitely. Redis offsets may be
stream-ID strings, such as `'1720000000000-0'`; the offset is exclusive.
History reads do not participate in consumer groups, so their events cannot be
acknowledged/requeued. Closing the iterator stops reading.

Workers accept `Subscription(queue='add', group='PinkStream')` from the Redis
adapter; a queue-name string or equivalent mapping also works. Consumers within
one group compete for messages; separate groups each receive the stream.
`broker.consumer(qos=1)` limits total unacknowledged local deliveries across all
subscriptions. Owner-thread callbacks handle pool completion and shutdown,
including ThreadPool and ProcessPool workers. Redis Run return values are
acknowledged normally but are not sent back as RPC responses.

- `ack()` and `reject()` use XACK without deleting history. Reject has no built-in
  dead-letter destination.
- Default failure handling uses Requeue. `nack()` atomically appends a copy to the
  stream and acknowledges the original pending entry using a single-key Lua
  script. The retry has a new stream ID and is visible to **all groups**, not only
  the failing group. Separate retry streams are needed for group-isolated retry.
- Consumers reclaim abandoned pending entries with XAUTOCLAIM after 60 seconds
  of idle time by default. Set `reclaim_idle` on `broker.consumer()` to a larger
  millisecond value for long tasks, or None to disable automatic recovery.
  Long-running active tasks can otherwise be reclaimed by another consumer.
  The default Worker uses the default consumer settings.
- Shutdown does not acknowledge unfinished work. Connection failures and
  decoding/handler/callback errors propagate; there is no automatic reconnect.
  Unconfirmed entries remain pending for later reclamation.

Delivery is at least once: make side effects idempotent. History is retained
after settlement and retries add entries; configure Redis retention externally
without trimming pending entries. The adapter does not silently trim/delete
messages or destroy groups.

Run `sample/Broker/Redis/Sample.py` for a finite send/pop/history demo.
`sample/Broker/Redis/Sample.Stream.py` uses `broker.stream()` to publish three
events, read from the beginning, and resume after the first event's stream ID.
These history reads do not require ACK. Each read uses a 1000 ms timeout, and
the sample deletes only its uniquely named stream and closes the connection.
`sample/Worker/Redis/Sample.py` uses Prepare to create each registered queue and
consumer group and publish five messages per Run before consuming `add` and
`divide`. Operands range from 0 to 99; the first Divide message always uses a
zero divisor to demonstrate logged ZeroDivisionError and Reject without endless
requeue. Other divisors are random and may also be zero. Successful messages
continue processing. It runs until Ctrl+C, then drains work and runs Cleanup.
Cleanup logs completion without deleting shared queues or stream history.
You can publish more `{'a': 10, 'b': 20}` messages from another process.
Enable the real Redis integration tests with `PINKSTREAM_REDIS_TESTS=1`; they use
localhost:6379 and create/delete only uniquely named test streams.

## Workers

### Task-directed messages and declarations

`declare`, `send` and `request` are exported from `PinkStream.Worker`. They resolve the
destination from a concrete Run class's `parameters`; the sending application
does not need a Worker or global task registry. Bodies must be mappings with
string keys, matching `run(**body)`. A scalar Run result must be wrapped in a
mapping before forwarding to another task.

Connections are **borrowed**: callers must connect and close them. Neither helper
connects, declares destinations, nor closes the passed connection, including on
failure. One connection can publish many records:

```python
from PinkStream.Worker import (
	declare,
	send,
	request,
)
from PinkStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
)

connection = Connection(Configuration(
	host='127.0.0.1',
	port=5672,
	username='guest',
	password='guest',
))
connection.connect()
try:
	# Sample is an application Run class with subscription parameters.
	declare(
		task=Sample,
		broker=connection,
	)
	for index in range(1000):
		send(
			{
				'a': index,
				'b': 1,
			},
			task=Sample,
			broker=connection,
		)
	response = request(
		{
			'a': 10,
			'b': 20,
		},
		task=Sample,
		broker=connection,
		timeout=5,
	)
finally:
	connection.close()
```

`send` returns the published message ID. RabbitMQ uses one reusable publisher
channel per connection, publisher confirms and mandatory routing; an absent
destination raises rather than silently dropping a task. Redis uses XADD.
The former task-directed `emit` name has been removed without an alias.
`emit` is reserved for a future exchange/event publishing API, not implemented yet.
RabbitMQ `request` delegates to Queue RPC, returning its result or propagating
TimeoutError/RemoteError/publication errors. Redis `request` raises
NotImplementedError. RPC still opens a dedicated request/reply connection per
call internally; the caller-owned connection remains open. This is not pooled
or multiplexed RPC.

`worker.tasks` replaces `worker.runs` and contains registered Run classes.
Declarations remain explicit, not a side effect of subscribing or sending:

```python
class Declare(WorkerSetup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		for task in worker.tasks:
			declare(
				task=task,
				broker=worker.broker,
			)
```

Pass `setups=Declare()` to Worker. Its broker is already connected before setup
runs. `declare(task=task, broker=connection)` delegates to
`connection.declare(task.parameters)` without opening or closing the connection.
It can be used without a Worker; there is no `worker.declare()` method.
RabbitMQ declares durable queues and, when `error` is provided, the durable DLQ
and dead-letter routing through the default exchange. Redis creates the stream
and named consumer group. Existing incompatible RabbitMQ declarations fail
explicitly; no queue is deleted/recreated automatically. This initial task
declaration API provisions ordinary queues, not RabbitMQ stream queues or
exchange bindings.

Adapters explicitly implement the optional Declarable, TaskSender and Requestable
protocols in `Broker.Connection` (also exported from `Broker`). These three
protocols support runtime capability checks so helpers can report unsupported
operations. Other connection protocols remain static contracts. A normal Worker
still requires only connect/close/consumer; declaration is optional.

Completion hooks can forward work:

```python
class SendNext(RunComplete):
	def __call__(
		self,
		context,
		completion,
	) -> None:
		connection = Connection(Configuration(
			host='127.0.0.1',
			port=5672,
			username='guest',
			password='guest',
		))
		connection.connect()
		try:
			for record in completion:
				send(
					record,
					task=Sample2,
					broker=connection,
				)
		finally:
			connection.close()
```

Here completion is an iterable of mappings. For one mapping, call send once
instead. Use `completes=SendNext()` on the source Run. Both destinations must
already be declared. Hooks execute inside the pool thread/process: open their
producer connection there, never share the consumer connection or a live
connection across processes/threads. For ProcessPool, hook and Run classes must
be defined at module scope. Connections can be reused within a batch; reuse
across multiple Runs can be managed by application PoolSetup/PoolCleanup hooks.
Keep RabbitMQ heartbeats serviced during long idle/compute periods.

Hook publication failures propagate as task failures and prevent success ACK.
Earlier publications in a partially completed batch are not rolled back.
Publication and source ACK are not atomic: retries/crashes may duplicate
downstream messages, so recipients must be idempotent. Blocking requests from a
hook to the same exhausted pool can deadlock until timeout; use separate
capacity/workers for such dependencies.

Workers receive a broker and a bounded execution pool. Register Run classes
explicitly; importing or defining a Run does not register it globally.
`EventContext`, `EventProperties`, `EventRunner`, worker `Factory`, `Invoker`,
and automatic module loading have been removed.

```python
from PinkStream.Worker import (
	declare,
	Run,
	ThreadPool,
	Worker,
	WorkerSetup,
)
from PinkStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
	Subscription,
	Reject,
)

class Add(
	Run,
	parameters=Subscription(
		queue='add',
	),
	on_error=Reject(),
):
	def run(
		self,
		a: int,
		b: int,
	):
		print(a + b)

class DeclareQueues(WorkerSetup):
	def __call__(
		self,
		worker: Worker,
	) -> None:
		broker = worker.broker
		if not isinstance(
			broker,
			Connection,
		):
			raise TypeError('A RabbitMQ broker is required')
		for task in worker.tasks:
			declare(
				task=task,
				broker=broker,
			)

broker = Connection(Configuration(
	host='127.0.0.1',
	port=5672,
	username='guest',
	password='guest',
))
worker = Worker(
	broker,
	ThreadPool(10),
	setups=DeclareQueues(),
)
worker.add(Add)
worker.run()
```

Provision queues in `WorkerSetup` or separately before starting. Worker connects
the injected broker, runs its setup hooks, creates its consumer, and subscribes
only registered Runs. It owns that broker
connection and pool for one run and closes both on exit; do not share them with
another Worker. Call `worker.stop()` to stop accepting work, finish outstanding
tasks and message confirmations, then close resources. Shutdown currently waits
for running tasks without a timeout.
`Pool.submit(RunClass, body)` replaces event-name-based submission.
It accepts `callback(result)` and `error_callback(exception)` keyword arguments,
like `apply_async`, while retaining the executor implementation and returned
Future. Only one outcome callback runs, after the Run and its hooks finish.
These callbacks stay in the parent process, including with ProcessPool; they
must schedule broker operations through `Consumer.call`, not execute them
directly. Worker uses these callbacks for ACK and the Run's failure policy.
Both `Pool.stop()` and `Pool.shutdown()` wait for tasks; forced termination is
not provided by this executor-based implementation.
Worker is not an event handler or callable. It creates the consumer without a
default handler and supplies a Run-specific handler for each subscription.
For standalone broker consumers, `consumer(handler)` and `subs(queue)` remain
available for standalone consumption.
There is one subscription method: `subs(queue_or_settings, handler=None)`.
It accepts a queue name, a RabbitMQ `Subscription`, or a settings dict.
An explicit handler overrides the consumer's default handler; one of them is
required. Queue-name calls retain the consumer's default offset and QoS.
The separate `subscribe` method has been removed.

RabbitMQ subscription settings can be a
`Subscription(queue=..., offset=..., qos=..., error=None)`

`error` optionally records a non-empty dead-letter queue name. Subscription
itself does not provision resources. Explicit `declare(task=task, broker=connection)` (or
`connection.declare(task.parameters)`) creates the DLQ and configures the source
queue to dead-letter to it. `consumer.subs()` still never declares resources.
Reject sends to the DLQ; Requeue does not. Existing queues with conflicting
declaration arguments raise the broker error rather than being silently changed.
or a dict with those fields. Unknown settings are rejected, not ignored.
Set `qos` in each Run's subscription (mapped to RabbitMQ's `prefetch_count`) to limit its unacknowledged
deliveries independently (`global_qos=False`). Omitted/None uses the Consumer's
`qos` default (1); 0 means unlimited, and valid values are 0 through 65535.
The limit includes execution and hooks until ACK or failure settlement.
It is not a per-Run execution pool size: Runs share the Worker pool.
Redis Streams `COUNT` and Kafka `max.poll.records` are batch-return limits,
not equivalent broker-enforced unacknowledged-message limits; they are not
exposed as a universal Run QoS setting.
Duplicate queue registrations are rejected: this version associates one queue
with one Run, not message-type-based routing. `queue.error` is not implemented;
configure dead-letter routing on the broker separately.

Each delivery creates a Run instance and calls it with `instance(**body)`;
`Run.__call__` manages hooks and delegates to `run`. Bodies must be
mappings with string keys. Pool capacity includes submitted/running tasks and
has no unbounded waiting queue. The default pool size is the CPU count (or 1).
A full pool causes NACK with `requeue=True`. Successful tasks are ACKed only
after completion. Failures are logged and use the Run's `on_error` policy:
RabbitMQ defaults to `Requeue()`, or use `Reject()` for `requeue=False`.
Requeue does not guarantee placement at the tail and may cause rapid repeated
delivery. Reject uses the broker's dead-letter routing if configured, otherwise
the message is discarded. Delivery is at-least-once; handlers must tolerate
duplicates. `NoAck` is not a failure policy.

Run classes also accept `setups`, `completes`, and `errors`, each as a single
hook or an ordered sequence. The `RunSetup`, `RunComplete`, `RunError`,
and `Context` interfaces are exported from `PinkStream.Worker`.
`errors` contains execution-error hooks (`RunError`), while `on_error` selects
the failed-event policy (`EventError`, exported from `PinkStream.Broker`).
These are separate responsibilities: error hooks run in the pool, then the
event policy runs on the connection owner thread. The former `FailurePolicy`
and `error_policy` names have been replaced by `EventError` and `on_error`.
RunSetup hooks receive `Context` (`args` and `kwargs`), completion hooks
receive that context and the result, and error hooks receive context
and the exception. Setups run before `run`; completes
run after success; errors run after `run` failure. RunError hooks
do not turn failure into success. If any hook raises, remaining hooks stop
immediately and the failure policy applies (no recursive error-hook execution).
Run instances are constructed at submission, after capacity is acquired.
Constructor exceptions are submission errors, not execution errors.
The hook/execution lifecycle runs in the pool, and only then is ACK or the failure
policy applied on the connection thread. Pool capacity remains occupied until
hooks finish. Hooks used with ProcessPool must also be picklable.
### Lifecycle hooks

All hook interfaces are exported from `PinkStream.Worker`:

| Scope | Hooks | Arguments |
| --- | --- | --- |
| Run | `RunSetup`, `RunComplete`, `RunError` | Context; context and result; context and exception |
| Pool | `PoolSetup`, `PoolCleanup` | No arguments; executed inside each pool thread/process |
| Worker | `WorkerSetup`, `WorkerCleanup` | The Worker instance |

`Runner` has been renamed to `Run`, in the `PinkStream.Worker.Run` module.
The old `Setup`, `Complete`, `Error`, and `Initializer` names have been replaced
by the scoped names above; there are no compatibility aliases.

Pass `setups=` and `cleanups=` to Worker, ThreadPool, or ProcessPool. Each accepts
a single hook or an ordered sequence. Worker setup hooks run after broker
connection and before subscriptions; `worker.tasks` contains the registered Run
classes. Use these hooks to declare queues/DLQs or check application dependencies.
Worker cleanup hooks run after the pool has shut down and before the consumer
and broker are closed, including when connection, setup, subscription, or
consumption fails. They must tolerate partially initialized resources.

Pool execution environments start lazily on the first submission. Each runs its
setup hooks once, processes tasks, and runs its cleanup hooks in the same
thread/process on graceful shutdown. An unused pool runs neither hook.
Cleanup runs only after all setup hooks in that environment succeed, including
when a task fails; a failing setup must release its own partially acquired
resources. Initialize actual task DB connections here, not in the parent process.
ProcessPool uses spawned processes; hooks and their configuration must be
picklable. Pool setup and cleanup hooks do not receive the Worker or broker.

Persistent execution loops run on the standard executors so that cleanup executes
in `finally` inside the owning environment, rather than submitting arbitrary
cleanup tasks that might all land on one worker. Futures, bounded capacity, and
parent-side completion callbacks are retained. A ProcessPool also owns a
management process for task/result transport, closed during shutdown.

Cleanup hooks run in registration order. A cleanup failure does not skip later
cleanup hooks or resource closure; failures propagate with exception chaining.
Pool environment failures fail outstanding Futures and are also raised by
`stop()`/`shutdown()`. Ordinary Run failures do not break the pool.
Cleanup cannot be guaranteed after forced termination or a process crash.

Broker confirmations run on the connection owner thread, not pool threads.
`PinkStream.Broker.Event` is the common event contract (`body`, `ack`, `nack`,
`reject`); RabbitMQ's `Event` implements it and retains its broker metadata.
Worker and failure policies use this contract; there is no separate `Delivery`.
Only the Run instance and body are sent to ProcessPool children; Run classes
must be importable at module scope and instances/inputs/results must be picklable.
Use the `if __name__ == '__main__':` guard with ProcessPool.
For graceful Ctrl+C shutdown, register a parent-side `SIGINT` handler that calls
`worker.stop()` (as in the RabbitMQ sample). Pool child processes ignore SIGINT
so they can finish active work and run PoolCleanup instead of raising
KeyboardInterrupt. The parent drains message confirmations, stops the pool,
runs WorkerCleanup, and closes broker resources. The library does not replace
the application's parent-side signal handler.

Run unit tests with `python -m unittest discover -s test -p "test_*.py"`.
To include local RabbitMQ integration tests, set `PINKSTREAM_RABBITMQ_TESTS=1`
first. They use `127.0.0.1:5672` with guest credentials and create/delete only
uniquely named test queues.

Examples are organized under:

- `sample/Worker/Sample.py` for a self-contained in-memory broker and worker.
  It declares a queue and publishes two messages in `WorkerSetup`, processes
  them with a ThreadPool, confirms deliveries on the consumer thread, then
  exits automatically after draining the queue and runs `WorkerCleanup`.
  No RabbitMQ server is required. This finite sample consumes one message at
  a time and rejects failed messages by default; it is not a persistent broker.
- `sample/Worker/RabbitMQ` for RabbitMQ-backed workers
- `sample/Broker/Implements/RabbitMQ` for RabbitMQ queues, exchanges, and streams
- `sample/Broker` for a small in-memory broker

RabbitMQ examples require a reachable RabbitMQ server and pre-existing queues
unless a Worker setup provisions them.

## Development in VS Code

Sources remain in `src/Worker` and `src/Broker`. On Windows, install the package
into the workspace virtual environment, then create a directory junction named
`PinkStream` in its `site-packages` directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
New-Item -ItemType Junction `
  -Path .\.venv\Lib\site-packages\PinkStream `
  -Target (Resolve-Path .\src).Path
```

Select that virtual environment as VS Code's Python interpreter. Python and
Pylance can resolve `PinkStream` directly through the junction, without extra
search paths or a generated build tree.

Source edits and added or removed modules are reflected without reinstalling.
Reinstall after changing package metadata or dependencies. Recreate the junction
when recreating the virtual environment or moving the source directory; do not
create it over an existing `PinkStream` directory.