# RabbitMQ 로컬 테스트 환경

각 Compose 파일은 한 가지 RabbitMQ 버전의 컨테이너를 생성합니다. 명령은 저장소 루트에서 실행하세요. 필요한 버전만 실행하거나 두 버전을 동시에 띄울 수 있습니다.

## 기동과 종료

```shell
docker compose -f res/docker/rabbitmq/rabbitmq-3.yml up -d --wait
docker compose -f res/docker/rabbitmq/rabbitmq-4.yml up -d --wait
```

종료할 때는 기동에 사용한 Compose 파일에 `down`을 실행합니다.

```shell
docker compose -f res/docker/rabbitmq/rabbitmq-3.yml down
docker compose -f res/docker/rabbitmq/rabbitmq-4.yml down
```

## 컨테이너와 포트

| 컨테이너 | 이미지 계열 | 호스트 포트 |
| --- | --- | --- |
| `RabbitMQ-3` | `rabbitmq:3.13-management` | AMQP `55630`, Management `55631`, Prometheus `55632` |
| `RabbitMQ-4` | `rabbitmq:4.4-management` | AMQP `55640`, Management `55641`, Prometheus `55642` |

포트는 모두 `127.0.0.1`에만 게시됩니다. 테스트 계정은 `guest`이며, 저장소의 `enabled_plugins` 설정에서 다음 플러그인을 활성화합니다.

- `rabbitmq_management`
- `rabbitmq_prometheus`
- `rabbitmq_shovel`
- `rabbitmq_shovel_management`

활성화 상태는 다음 명령으로 확인할 수 있습니다.

```shell
docker compose -f res/docker/rabbitmq/rabbitmq-3.yml exec -T rabbitmq rabbitmq-plugins list --enabled
docker compose -f res/docker/rabbitmq/rabbitmq-4.yml exec -T rabbitmq rabbitmq-plugins list --enabled
```

## 통합 테스트

RabbitMQ 통합 테스트를 활성화하고 Compose 포트를 지정하세요.
Windows에서 기본 콘솔 인코딩이 UTF-8이 아니면 테스트 전에 `PYTHONIOENCODING`도 UTF-8로 설정합니다.

```powershell
$env:RABBITMQ_TESTS = '1'
$env:RABBITMQ_PORT = '55630'
$env:PYTHONIOENCODING = 'utf-8'
python -m unittest discover -s tests -t . -p 'test_*.py'
```

RabbitMQ 4를 대상으로 할 때는 `RABBITMQ_PORT`를 `55640`으로 바꿉니다. Docker Compose health check가 통과한 뒤 테스트를 실행하세요.

RabbitMQ 전용 테스트만 실행하려면 저장소 루트에서 다음 명령을 사용합니다.

```shell
python -m unittest discover -s tests/rabbitmq -t .
```
