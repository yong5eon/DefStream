# DefStream

Synchronous event/message processing with pluggable broker adapters

DefStream processes broker messages with ordinary Python task methods and can run them in thread or process pools. It requires Python 3.9 or later.

## Installation

Install the client extra for the broker you use. A broker server must be available separately.

```shell
python -m pip install "DefStream[RabbitMQ]"
```

For Redis Streams, install `DefStream[Redis]`. To install both clients, use `DefStream[RabbitMQ,Redis]`. The plain `DefStream` installation includes neither broker client.

## Quick start

The following worker listens to a local RabbitMQ server at `127.0.0.1:5672`. The example credentials are for local development only.

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

Run the script after starting RabbitMQ. The worker declares its task queue and waits for messages. Store production credentials outside source code.

## License

See the `LICENSE` file included with the source distribution for the license terms.
