# DefStream

## CI and PyPI releases

The `CI` workflow runs on pull requests targeting `master` and pushes to
`master`. Python 3.9 through 3.14 build the distributions, install the wheels in
a clean virtual environment, and run this repository's tests against RabbitMQ
4.1 and Redis 7.4 service containers. The core JavaScript UI tests also run.
Every successful `master` push publishes to PyPI; PRs only run tests.
Source additions,
deletions, and renames are detected across the entire push range; the first
push compares against an empty tree. A failed or unavailable base comparison
fails the workflow rather than assuming that there were no source changes.
Release versions and tags use `MAJOR.MINOR.PATCH.BUILD`, for example
`0.1.3.123`. Changes to `src/**` increment PATCH by one; changes only to tests,
documentation, samples, workflows, or `setup.py` keep MAJOR.MINOR.PATCH.
BUILD is the Actions run number in both cases:
`0.1.3.123` -> `0.1.3.124` (docs) -> `0.1.4.125` (source).
The entire four-part value is the public PyPI version, not hidden metadata.
Every upload has a distinct version; PyPI files are never overwritten.
Older three-part and `v`-prefixed tags remain readable; new tags have no prefix.

The workflow checks out the current repository's event commit and the other
two `yong5eon/DefStream*` repositories at `master`, recording all commit IDs in
the log. Those repositories must be accessible and have a `master` branch.
All three packages are built locally, so the first release does not depend on
existing PyPI releases. This tests the source combination, not compatibility
with previously published dependency versions.

There is no `VERSION` or `pyproject.toml` file. `setup.py` declares
`setuptools-scm` through `setup_requires` and configures the tag format.
Build with `python -m build`, which resolves that build dependency in an
isolated environment; the legacy declaration may emit a deprecation warning.
`setuptools-scm` derives the package version from Git tags using full history.
On every master push, CI creates a local candidate tag
`<RELEASE_SERIES>.<PATCH>.<github.run_number>` (for example, `0.1.4.125`).
`RELEASE_SERIES` is configured in the workflow; change it to start a new
major/minor series. PATCH is calculated from the highest matching version tag
in the pre-push history, increasing only when source files change.
The planner uses tags reachable from the push's `before` commit so reruns do
not accidentally base themselves on their own new tag. PR builds use the
existing Git-derived development version without creating candidate tags.
No version commit or version-update PR is created. A new release series starts
at PATCH 0 on a source-changing push; non-source pushes require an existing
matching release tag. Build counter regressions fail rather than uploading an
older build. Legacy `.postN` tags are still accepted when determining PATCH;
four-part numeric builds sort above post releases of a three-part base.

After all tests pass, the publish job pushes the release tag to the exact
tested commit, then uploads the verified distributions. A tag can therefore
exist before a failed upload is retried; check PyPI or the job result for
publication status. An existing tag on another commit is an error and is
never overwritten. Run numbers can have gaps; check for collisions before
renaming/replacing this workflow.

After PyPI upload succeeds (or a rerun confirms the version is already fully
published), CI creates a GitHub Release with the same version as its title and
tag, automatically generated release notes, and the verified wheel and sdist
as assets. New releases stay in draft until both assets are uploaded. If this
step fails, rerun the workflow: it reuses the existing release and replaces
matching assets with the verified files before publishing. A failed PyPI
upload never proceeds to GitHub Release creation. PyPI's project links include
the GitHub Releases page for change history. No additional GitHub token secret
is needed; release creation uses the job's write-enabled `GITHUB_TOKEN`.

Local release checkouts use their tag version. Commits after a tag produce
development versions, and dirty trees get a local version suffix. Fetch tags
with `git fetch --tags`; build from a Git checkout or the published sdist,
not a GitHub source ZIP without Git metadata. The sdist carries the version
in its package metadata and can be rebuilt without `.git`. Query installed
versions with `importlib.metadata.version('DefStream')`.

After every Python matrix entry passes, the publish job downloads the exact
Python 3.13 distributions already built and tested. A fully published version
is skipped only on a rerun; first-attempt collisions and partially published
versions fail explicitly. Network errors are not treated as missing releases.
Concurrent runs are serialized without cancelling the active run; GitHub may
supersede an older pending run when more pushes arrive.

Before enabling automatic releases:

1. In each repository, add `PYPI_API_TOKEN` under **Settings > Secrets and
   variables > Actions**, or as a secret in the `pypi` environment. Use the
   appropriate PyPI project scope once the project exists. Never commit tokens.
2. Configure the `pypi` environment to allow deployments only from `master`.
   Do not require manual approval if fully automatic deployment is desired.
   Allow the workflow's `GITHUB_TOKEN` to write repository contents so the
   publish job can create numeric version tags. Tag rulesets must permit this
   workflow for four-part version tags.
3. Protect `master`, require PRs, and require all six `Test Python 3.x` checks.
   Do not require `Publish PyPI`, which intentionally does not run on PRs.
4. Keep the workflow filename/name stable and review changes to workflows and
   packaging carefully: merging to `master` authorizes a public release.

Dependencies still need to be published before end users can install adapters
from PyPI. For the initial release, publish DefStream before its adapters.
Before migrating to SCM versions, tag each already published release's exact
source commit as `<its-PyPI-version>` and push those tags. Do not point a
release tag at an unrelated newer commit. The shared CI builds sibling
`master` sources: an untagged SCM dependency can resolve to `0.1.dev...`, below
its required minimum. These initial tags supply the starting PATCH when
migration changes no source files. For example, tag the commit used to publish
`0.1.3` as `0.1.3`; a later docs-only run 123 produces `0.1.3.123`.
This tag is a historical source/version link, not a source edit or a new PyPI
upload. Never invent that link by tagging an arbitrary current commit.

**Just def.**<br>
**Let workers do the work.**<br>
**You don't need to await this.**

## Installation

```shell
pip install DefStream
pip install "DefStream[RabbitMQ]"
pip install "DefStream[Redis]"
pip install "DefStream[RabbitMQ,Redis]"
```

The base package has no broker client dependencies and does not include adapter
source files. Extras install the separate `DefStream-RabbitMQ` and/or
`DefStream-Redis` distributions, which depend on `pika` and `redis`, respectively.
You can also install the adapters directly:

```shell
pip install DefStream-RabbitMQ
pip install DefStream-Redis
```

The Python import paths remain `DefStream.Broker.Implements.RabbitMQ` and
`DefStream.Broker.Implements.Redis`. For local development of all three projects,
see the editable installation instructions below.

The project is now named DefStream. Distribution/import names use `DefStream`,
Prometheus metric names use `defstream_`, and integration-test environment
variables use `DEFSTREAM_`. Redis's default consumer group is now `DefStream`;
when continuing an existing deployment, explicitly keep its previous group name
to preserve consumer-group position and pending messages. Queue names explicitly
configured by applications are unchanged.

```python
from DefStream.Worker import Worker
from DefStream.Broker.Implements.RabbitMQ import Connection as RabbitConnection
```

There is no combined `DefStream.Broker.Broker` interface. Implementations expose
a concrete `Connection` class without a `Broker` compatibility alias.

Create broker connections directly with the implementation's configuration and
call `connect()` before use. Call `close()` when finished. Connection registries
or helpers, if needed, belong in application code.

RabbitMQ resource methods use snake_case: `create_exchange`, `delete_exchange`,
`bind_exchange_to_exchange`, `unbind_exchange_to_exchange`, `create_queue`,
`delete_queue`, `bind_exchange_to_queue`, `unbind_exchange_to_queue`,
`create_stream`, and `delete_stream`. The former camelCase names are removed.

## Connection capabilities

`DefStream.Broker.Connection` defines independent `typing.Protocol` contracts,
also exported from `DefStream.Broker`. Implementations explicitly inherit only
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

`DefStream.Worker.WorkerConnection` composes only Connection and
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

Common message I/O contracts now live in `DefStream.Broker.Protocol` and are
also exported from `DefStream.Broker`:

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
and are exported from `DefStream.Broker`. EventHandler is a Protocol with
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
`DefStream.Broker.RemoteError` with code `ProcessingError` and a generic message;
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
from DefStream.Broker.Implements.Redis import (
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

Workers accept `Subscription(queue='add', group='DefStream')` from the Redis
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
Enable the real Redis integration tests with `DEFSTREAM_REDIS_TESTS=1`; they use
localhost:6379 and create/delete only uniquely named test streams.

## Workers

### Inspector: HTTP health checks and metrics

Inspector uses only the Python standard library: a threaded WSGI HTTP server
managed by the Worker. It starts before broker connection/setup, and closes
after pool draining, cleanup and broker closure, including startup failures.
An occupied HTTP port fails Worker startup explicitly. Inspector is optional;
workers without one keep their existing behavior.

```python
from DefStream.Inspector import Inspector
from DefStream.Inspector.Extensions import (
	HealthCheck,
	Metrics,
)
from DefStream.Worker import (
	ThreadPool,
	Worker,
)

worker = Worker(
	connection,
	ThreadPool(10),
	inspector=Inspector(
		host='127.0.0.1',
		port=9999,
		exts=(
			HealthCheck('/status'),
			Metrics('/metrics'),
		),
	),
)
worker.add(Sample)
worker.run()
```

- `GET /status` returns JSON with `status`. It returns 200 only
  after subscriptions are ready and the consumer loop answers a thread-safe
  callback within `HealthCheck(timeout=1)` seconds (default 1). Idle workers are healthy.
  Starting, stopping, stopped and unresponsive workers return 503 while HTTP
  remains open. A terminated process/server fails the HTTP connection instead.
  The probe checks consumer-loop responsiveness, not every dependency or a
  hung individual task; choose a timeout above normal consumer-loop latency.
  Repeated/concurrent checks share an outstanding probe rather than filling
  a stalled consumer's callback queue.
- `GET /metrics` returns Prometheus text format, **200 even when not ready**,
  so failures and shutdown can still be observed. Metrics include
  `defstream_worker_running`, `defstream_worker_uptime_seconds`,
  `defstream_tasks_active`, `defstream_tasks_total` (success/failure), and
  `defstream_task_duration_seconds` (summary count/sum). The running gauge
  describes lifecycle state; use `/status` for the responsiveness probe.
  Task labels use module-qualified class names; no message body/ID is exposed.
  Counters describe completed execution attempts, including retries and hooks,
  not confirmed ACKs or unique messages. Invalid bodies, pool-full requeues and
  failed submissions do not count as task executions. Duration includes pool
  wait and hooks. Metrics are local to one Worker process and reset on restart.
- Paths are explicit extensions; there are no default routes. Both endpoints
  support HEAD. Unknown paths return 404 and unsupported methods return 405.
  Extensions default to GET/HEAD; request-aware extensions can declare `methods`
  and override `handle(inspector, environ)` without changing existing endpoints.
  Additional endpoints can inherit `Extension` and return `Response`, both
  exported from `DefStream.Inspector`. Built-in extensions are exported from
  `DefStream.Inspector.Extensions`.
- Each extension owns its behavior and state: HealthCheck owns the consumer
  probe, lock and timeout; Metrics owns counters, execution timing and output.
  Inspector owns only HTTP serving, Worker attachment, routing and event
  dispatch. Unregistered extensions do not collect data or create probe state.
  `Extension.start(inspector)` initializes an extension before HTTP startup.
  `begin(task)` returns an extension-owned context; `end(task, context, success)`
  receives it on completion. `success=None` means submission was rejected and
  must not count as a completed attempt. These hooks execute in the parent
  process and may run on different threads; extensions must synchronize state.
- Inspector is attached to one Worker and cannot be restarted or shared.
  Task execution remains in the existing ThreadPool/ProcessPool; the HTTP
  server and metric aggregation stay in the parent process.
- This is a small operational HTTP interface, not a public web server. No
  TLS is provided. Health, metrics and Specifications routes are unauthenticated;
  the optional Console extension supports an optional Bearer token for task data
  and execution. Keep Inspector on loopback or a trusted management network.

The RabbitMQ and Redis Worker samples enable `/status` and `/metrics` on
`127.0.0.1:9999`; use different ports if running both at once. For Docker,
use `host='0.0.0.0'` to expose it outside the container (restrict network access).
A health command inside the container needs no curl dependency:

```dockerfile
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:9999/status', timeout=2).close()"
```

### Live dashboard

Register `Dashboard` together with exactly one `Metrics` extension:

```python
from DefStream.Inspector.Extensions import (
	Dashboard,
	Metrics,
)

inspector = Inspector(exts=(
	Metrics('/metrics'),
	Dashboard(
		'/dashboard',
		title='DefStream',
		description='Worker activity',
	),
))
```

Open `/dashboard` for a lightweight, dependency-free status page. Both Worker
samples register this route. The page reads the existing Metrics collector;
there is no second collector, broker connection or server-side history.
`title` defaults to `DefStream`; optional `description` is the subtitle.
HTML changes take effect on refresh without restarting.

- Shows worker lifecycle, uptime, in-flight submissions, cumulative success
  and failure counts, total throughput, and per-task throughput and average time.
- Select **Last second** or **Last minute** for real server-side 1/60-second
  completion windows, not a per-second value multiplied by 60. Windows end at
  the last fully elapsed monotonic second (less than one second behind live
  totals). The minute window advances every second, not once per calendar minute.
  Startup windows include only data since startup, without extrapolation.
  History is available immediately on page load and after reconnect.
- Selected-window metrics include completed success/failure counts, failure
  percentage, average and maximum duration, both overall and per task. An empty
  window shows zero completions and `--` for failure percentage/average/maximum.
  Oldest in-flight age is measured from submission, including pool wait.
- Averages use the duration of attempts completed in the selected window,
  including pool wait and hooks; these are not p95 latency. Retries count
  as separate attempts; pool-full/rejected submissions do not count as completed.
  In flight includes submitted work waiting in the pool, not broker queue depth.
- Lifecycle is not consumer responsiveness. Use `HealthCheck` for health probes.
  Requests time out after five seconds; failed polls mark totals as stale and
  clear current rates. Pause/resume is available; hidden tabs stop polling.
- `GET /dashboard` with `Accept: application/json` returns a detached snapshot
  (`instance`, `sampled_at`, `uptime`, `running`, `tasks`). Tasks are keyed by
  module-qualified name with cumulative `active`, `success`, `failure`, `duration`
  (seconds), `oldest_active` (seconds), and `windows` keyed by `"1"`/`"60"` with
  `success`, `failure`, `duration`, `max_duration`. `window_end` is the monotonic
  exclusive end of both windows. Metrics keeps at most 61 one-second buckets per
  task (including the current incomplete second), not individual completion
  records. Pending submission timestamps are retained only until completion.
  Prometheus also exposes `defstream_tasks_window` by `window_seconds`/`outcome`,
  `defstream_task_window_duration_seconds_sum`,
  `defstream_task_window_duration_seconds_max`, and
  `defstream_task_oldest_active_seconds`. No p95 is collected.
  Prometheus and Dashboard use the same lock-protected snapshot.
- Like Metrics, Dashboard is unauthenticated. Restrict access at the application,
  network or proxy layer. It shows one Worker only, resets on restart, and is
  not a replacement for Prometheus/Grafana history or alerting.

### Request/response specifications

`DefStream.Descriptor` and `DefStream.Validator` reuse the local Liquirizia
Description/Validator APIs under the repository's GPLv3 license. Descriptor has
**no DataModel dependency**: manual schemas and dataclass `ToSchema`/`ToObject`
remain available. The original temporary sources are unchanged. Existing names
and implementation style are retained in the ported modules to minimize drift.
DataModel-only conversions and `IsDataModel` are not included.

```python
from DefStream.Descriptor import (
	Integer,
	Object,
	Properties,
)
from DefStream.Validator import Validator
from DefStream.Validator.Patterns import (
	IsInteger,
	IsObject,
)
from DefStream.Validator.Patterns.Object import (
	IsMappingOf,
	IsRequiredIn,
)
from DefStream.Worker import (
	Run,
	Specification,
)

class Add(
	Run,
	parameters={'queue': 'add'},
	request=Specification(
		schema=Object(
			properties=Properties(
				a=Integer('First operand'),
				b=Integer('Second operand'),
			),
		),
		validator=Validator(IsObject(
			IsRequiredIn(
				'a',
				'b',
			),
			IsMappingOf({
				'a': IsInteger(),
				'b': IsInteger(),
			}),
		)),
		example={
			'a': 10,
			'b': 20,
		},
	),
	response=Specification(
		schema=Integer('Sum'),
		validator=Validator(IsInteger()),
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

`Specification` accepts `schema`, `validator`, `example`, `description`, and
`format` (default `application/json`).
For example, `format='text/plain'` sets
the message's AsyncAPI `contentType`. Request and response can declare different
media types. This is contract metadata; it does not change broker codecs or the
JSON content type of the specifications HTTP endpoint. Configure compatible
broker encoders/decoders separately when using a different wire format.
`schema` can be a Descriptor value, Schema/condition, JSON-schema mapping, or
dataclass type. It describes the wire data; **it does not automatically validate
or instantiate a model**. Use Validator for runtime rules and transformations.
Custom validator rules are not reverse-engineered into JSON Schema. Examples
are documentation values, not automatically executed or validated.

Execution order is setup hooks, request validation/transformation, `run`,
response validation/transformation, completion hooks, then RPC response/ACK.
Request validation must return a mapping with string keys; specified tasks
accept keyword arguments. Output can be any existing broker-serializable value.
The returned validator value is used, not discarded. Validation failures invoke
RunError hooks and the existing `on_error` policy; configure Reject where
permanent invalid messages must not be requeued indefinitely. Request and
response contracts are inherited. Tasks without contracts retain their behavior.
The send/request helpers do not run the validators again.

Necessary changes from the source: `AllOf` dumps as `allOf`; string `min`/`max`
dump as `minLength`/`maxLength`; unsupported schema values/references fail
explicitly. Conversion patterns use `ast.literal_eval`, not `eval`: numeric
literal strings still work but executable expressions are rejected. `Validate`
supports functions without defaults and positional-only arguments.

### AsyncAPI JSON

```python
from DefStream.Inspector.Extensions import Specifications

# Add to Inspector(exts=(...)).
specifications = Specifications(
	'/asyncapi.json',
	version='1.0.0',
	description='Worker task contracts',
	format='application/json',
)
```

`Specifications.format` sets the document's `defaultContentType` and defaults to
`application/json`. Messages without a request Specification inherit this default;
each declared Specification's `format` remains an explicit message-level override
(it also defaults to JSON). This does not change broker codecs or the JSON HTTP
response format of this endpoint.

`GET /asyncapi.json` serves an AsyncAPI **3.1.0** document generated from that
Worker's registered tasks, without a global registry or broker connection.
The document is available during startup/shutdown while HTTP remains open.
It describes Worker-side **receive** operations, queue addresses, input message
schemas/examples. Operation descriptions come from `request.description`;
when it is None, the field is omitted without falling back to task docstrings.
Unspecified inputs have an object payload
with no additional constraints. Queue names can come from strings, subscription
mappings or subscription objects; missing addresses fail explicitly.
Operation keys are task class names (without modules). Receive channel keys are
the actual queue names, preserved without replacement; JSON Pointer references
escape `/` and `~`. Request messages are defined directly under each channel,
referenced as `#/channels/<queue>/messages/request`. Specification has no
`channel` option; subscription parameters determine the queue.
Output contracts generate a standard operation **`reply`**, referencing the same
channel and its `response` message at `#/channels/<queue>/messages/response`.
Request and response definitions live together under the channel's `messages`;
the receive operation selects only `request`, and its reply selects only
`response`. No separate `.completion` channel is generated. Duplicate operation
or queue channel keys fail explicitly.
This describes the declared request/reply contract, not broker capabilities:
declaring an output does not turn Redis into RPC, and ordinary sends do not
request replies. Dynamic RabbitMQ reply address extraction, correlation and
transport bindings are not modeled yet. No server credentials are exposed. This extension
serves JSON only; the optional Console extension provides the interactive task UI.

The RabbitMQ Worker sample declares contracts for Add and Divide and serves
them at `/asyncapi.json`. The Redis sample exposes the same endpoint, with
unconstrained inputs for tasks that have no contract yet.

### Interactive task console

`Console` provides a self-contained Swagger-style screen: registered tasks,
descriptions, request/response schemas, editable JSON examples and execution
results. It has no CDN or JavaScript package dependencies. It is not Swagger UI
(which consumes OpenAPI); it displays the same generated AsyncAPI contracts.
Schemas are displayed as expandable field trees with types, required markers,
descriptions and constraints. Nested objects, array items and composition
branches are shown separately; the complete raw JSON schema remains available.
Local schema references are expanded with recursion detection; external
references are labeled without fetching them. Deep models are limited to
12 nesting levels in the tree, with the full schema preserved in the raw view.
The bundled HTML is read on each page request with caching disabled. Editing
`Console.html` takes effect on browser refresh without restarting the Worker;
Python code and task contract changes still require a restart.

```python
from DefStream.Inspector.Extensions import Console
from DefStream.Broker.Implements.RabbitMQ import (
	Connection,
	Configuration,
)

def create_connection() -> Connection:
	return Connection(Configuration(
		host='127.0.0.1',
		port=5672,
		username='guest',
		password='guest',
	))

# Add to Inspector(exts=(...)).
console = Console(
	'/console',
	broker=create_connection,
	title='DefStream',
	description='Task contracts & interactive messaging',
	timeout=5,
)
```

`Console.title` defaults to `DefStream` and sets both the HTML document title
and header name without a suffix. Optional `description` is the subtitle;
omitting it hides the subtitle. Both values are escaped as plain text.
After loading tasks, the document version is displayed beneath the subtitle.
Console uses the first registered `Specifications` extension, including its
version, description and media type settings. Without one, it generates a
default document with version `1.0.0`.
Inspector has no `name` option: health responses contain status only, metrics
have no worker-name label, and Specifications uses `DefStream` as its info title.

The factory must return a **new, independently owned producer connection**
on every call, never the Worker's consumer connection or a shared singleton.
The extension connects for execution and closes in finally, including failed
connect/publish/RPC. Catalog loading inspects a separate, unconnected producer's
RPC capability and closes it. It never declares/deletes queues or calls Run
directly. Validators run on the actual Worker, not again in the HTTP thread.

- Open `/console`. With `token` omitted or `None`, no authentication is required:
  tasks load automatically and the token controls are hidden. To enable Bearer
  authentication, pass `token='your-random-token-at-least-16-characters'`,
  enter it in the page, then choose **Load tasks**. HTML is a public,
  static shell with no embedded token or task data; when authentication is
  enabled, task metadata and execution
  both require `Authorization: Bearer <token>`. Tokens must have at least 16
  characters; use a randomly generated strong token. The page keeps the token
  only in memory, never browser storage; Clear token removes it.
- **Send** invokes the existing task `send` helper and displays the message ID.
  **RPC** invokes `request` and displays the result. RPC is enabled only when
  the producer supports Requestable (currently RabbitMQ, not Redis); it does
  not depend on a response contract. Redis still supports Send.
- `GET /console` with `Accept: application/json` returns the catalog (authenticated
  only when a token is configured).
  `POST /console` accepts JSON
  `{"task":"Add","mode":"send","body":{"a":10,"b":20}}`;
  use `"mode":"request"` for RPC. Only registered, unambiguous task names are
  accepted. Body must be a JSON object; arbitrary queues cannot be selected.
- Unknown/invalid inputs return 400, unauthorized calls 401, cross-origin
  requests 403, bodies above 64 KiB 413, non-JSON requests 415, excess concurrent
  calls 429 (four slots), stopped/not-ready Workers 503, unsupported RPC 501,
  remote task errors 502 and RPC timeouts 504. Infrastructure failures are
  logged and return a generic 500 without exposing connection details.
- Timeouts **do not cancel already delivered work**. Send/RPC are not retried
  by the UI. These operations can produce real side effects; use test queues
  and idempotent tasks. Configure broker connection/socket timeouts as well as
  RPC timeout; metadata `Specification.format` does not change producer codecs.
- No CORS is enabled. Calls with an Origin must match the HTTP Host. Remote
  access must use HTTPS through a trusted reverse proxy to protect the token;
  do not expose the standard-library WSGI server directly to the Internet.
  Other Inspector extensions remain unauthenticated.

Both Worker samples enable `/console` without a token. Authentication, access
control, token configuration and secret management are the application's
responsibility.

### Task-directed messages and declarations

`declare`, `send` and `request` are exported from `DefStream.Worker`. They resolve the
destination from a concrete Run class's `parameters`; the sending application
does not need a Worker or global task registry. Bodies must be mappings with
string keys, matching `run(**body)`. A scalar Run result must be wrapped in a
mapping before forwarding to another task.

Connections are **borrowed**: callers must connect and close them. Neither helper
connects, declares destinations, nor closes the passed connection, including on
failure. One connection can publish many records:

```python
from DefStream.Worker import (
	declare,
	send,
	request,
)
from DefStream.Broker.Implements.RabbitMQ import (
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
from DefStream.Worker import (
	declare,
	Run,
	ThreadPool,
	Worker,
	WorkerSetup,
)
from DefStream.Broker.Implements.RabbitMQ import (
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
and `Context` interfaces are exported from `DefStream.Worker`.
`errors` contains execution-error hooks (`RunError`), while `on_error` selects
the failed-event policy (`EventError`, exported from `DefStream.Broker`).
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

All hook interfaces are exported from `DefStream.Worker`:

| Scope | Hooks | Arguments |
| --- | --- | --- |
| Run | `RunSetup`, `RunComplete`, `RunError` | Context; context and result; context and exception |
| Pool | `PoolSetup`, `PoolCleanup` | No arguments; executed inside each pool thread/process |
| Worker | `WorkerSetup`, `WorkerCleanup` | The Worker instance |

`Runner` has been renamed to `Run`, in the `DefStream.Worker.Run` module.
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
`DefStream.Broker.Event` is the common event contract (`body`, `ack`, `nack`,
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

Install the core and both adapters before running the test suite. Tests use the
installed `DefStream` package rather than importing the source directory as `src`.
Run unit tests with `python -m unittest discover -s test -p "test_*.py"`.
The core suite retains shared Worker, Inspector, and cross-adapter contract
tests. Adapter-specific unit and integration tests live in each adapter's
`test` directory. From the common parent directory, run all three suites:

```powershell
python -m unittest discover -s .\DefStream\test -p "test_*.py"
python -m unittest discover -s .\DefStream-RabbitMQ\test -p "test_*.py"
python -m unittest discover -s .\DefStream-Redis\test -p "test_*.py"
```

To include local RabbitMQ integration tests, set `DEFSTREAM_RABBITMQ_TESTS=1`
first. They use `127.0.0.1:5672` with guest credentials and create/delete only
uniquely named test queues. Redis integration tests are enabled separately with
`DEFSTREAM_REDIS_TESTS=1`.

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

The core sources remain in `src/Worker` and `src/Broker`. RabbitMQ and Redis
implementation files live directly under `src` in the sibling
`DefStream-RabbitMQ` and `DefStream-Redis` projects. Their distributions provide
only their adapter packages, not the parent packages owned by the core.

From the common parent directory, install all three projects into the workspace
virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install `
  --config-settings editable_mode=strict -e .\DefStream
.\.venv\Scripts\python.exe -m pip install `
  -e .\DefStream-RabbitMQ `
  -e .\DefStream-Redis
```

Select that virtual environment as VS Code's Python interpreter. No manual
`site-packages/DefStream` symbolic link or junction is needed. Remove an existing
link before installing the split projects: otherwise installing adapter files
under that link can write into the core source directory.

Use strict editable mode for the core and default editable mode for the
adapters. The default adapter finders provide parent namespace entries, which
can otherwise mask the core's default editable finder. Strict mode exposes the
core as regular packages through a link tree under its `build` directory.
Keep that link tree while using the editable installation.

Edits to existing source files are reflected without reinstalling. Reinstall
the core after adding or removing its modules. Reinstall the relevant project
after changing package metadata or dependencies, recreating the virtual
environment, or moving a project directory.