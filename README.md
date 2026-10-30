# DefStream

Synchronous event/message processing with pluggable broker adapters

**Just def.**<br>
**Let workers do the work.**<br>
**You don't need to await this.**

**한국어** | [English](./README.en.md)

DefStream은 메시지 브로커에서 받은 작업을 일반 Python 메서드로 처리하는 동기식 라이브러리입니다. `async` / `await` 없이 작업 실행, ACK와 실패 정책, 스레드·프로세스 풀을 구성할 수 있습니다.

- RabbitMQ와 Redis Streams 브로커 어댑터
- 단방향 작업 발행과 RabbitMQ 동기 RPC
- 요청·응답 계약 검증, 상태 확인과 운영용 Inspector

## 요구 사항 및 설치

Python 3.9 이상이 필요합니다. 사용할 브로커의 클라이언트 extra를 설치하고, 별도로 브로커 서버를 준비하세요.

```shell
python -m pip install "DefStream[RabbitMQ]"
python -m pip install "DefStream[Redis]"
```

두 어댑터가 모두 필요하면 `python -m pip install "DefStream[RabbitMQ,Redis]"`를 사용하세요. 브로커 클라이언트 없이 코어만 설치하려면 `python -m pip install DefStream`을 사용합니다.
기본 설치에는 브로커 구현체 코드도 포함되지 않습니다. 각 extra는 동일 버전의 별도 구현체 패키지와 클라이언트를 설치합니다.
소스 코드를 수정하고 싶다면 [설치 격리와 개발·배포](./docs/Packaging.md)를 참고하세요.

## 빠르게 시작하기

다음 예제는 로컬 RabbitMQ(`127.0.0.1:5672`)를 사용합니다. 사용자 이름과 암호는 로컬 개발용 예시이며 운영 환경에서는 전용 자격 증명을 사용하세요.

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

Worker는 `example.add` 큐에서 작업을 기다립니다. 작업 발행, 큐 선언, RPC 및 브로커별 설정은 [상세 매뉴얼](./docs/README.md)에서 확인하세요.

## 문서와 릴리즈

- [상세 매뉴얼 (한국어)](./docs/README.md)
- [릴리즈와 변경 내역](https://github.com/yong5eon/DefStream/releases)

DefStream은 GNU GPL v3 라이선스를 사용합니다. 자세한 조건은 저장소의 `LICENSE` 파일을 확인하세요.
