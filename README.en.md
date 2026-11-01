# DefStream

Synchronous event/message processing with pluggable broker adapters

**Just def.**<br>
**Let workers do the work.**<br>
**You don't need to await this.**

[한국어](./README.md) | **English**

DefStream is a synchronous library for processing broker messages with ordinary Python methods. Configure task execution, acknowledgements, failure policies, and thread or process pools without `async` / `await`.

- RabbitMQ and Redis Streams broker adapters
- One-way task publishing and synchronous RabbitMQ RPC
- Request/reply contract validation, health checks, and operational Inspector tools

## Requirements and installation

Requires Python 3.9 or later. Install the client extra for the broker you use, and provide the broker server separately.

```shell
python -m pip install "DefStream[RabbitMQ]"
python -m pip install "DefStream[Redis]"
```

To install both adapters, use `python -m pip install "DefStream[RabbitMQ,Redis]"`. To install the core without broker clients, use `python -m pip install DefStream`.
The base installation also excludes broker implementation code. Each extra installs a separate, same-version implementation distribution and its client.
To modify the source code, see [installation isolation, development and distribution](./docs/Packaging.en.md).

## Quick start

This example uses a local RabbitMQ server at `127.0.0.1:5672`. The credentials are for local development only; use dedicated credentials in production.

```python
from signal import SIGINT, signal

from DefStream.Broker.Implements.RabbitMQ import Configuration, Connection, Reject, Subscription
from DefStream.Worker import Run, ThreadPool, Worker, WorkerSetup, declare


class Add(
  Run,
  parameters=Subscription(queue='example.add', error='example.add.error'),
  on_error=Reject(),
):
  def run(self, a: int, b: int):
    print(a + b)
    return a + b


class Prepare(WorkerSetup):
  def __call__(self, worker: Worker) -> None:
    for task in worker.tasks:
      declare(task=task, broker=worker.broker)


if __name__ == '__main__':
  worker = Worker(
    Connection(Configuration(host='127.0.0.1', port=5672, username='guest', password='guest')),
    ThreadPool(4),
    setups=Prepare(),
  )
  worker.add(Add)
  signal(SIGINT, lambda *_: worker.stop())
  worker.run()
```

The Worker waits for tasks on the `example.add` queue. See the [detailed guide](./docs/README.en.md) for publishing tasks, declaring queues, RPC, and broker-specific configuration.

## Documentation and releases

- [Detailed guide (English)](./docs/README.en.md)
- [Releases and change history](https://github.com/yong5eon/DefStream/releases)

DefStream is licensed under GNU GPL v3. See the repository's `LICENSE` file for the terms.
