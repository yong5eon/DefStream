# 요구사항 명세

## 목적

RabbitMQ와 Redis 지원 범위의 경계 버전에서 통합 테스트를 실행할 수 있도록 버전별 Docker Compose 리소스를 제공한다.

## 확정 요구사항

- RabbitMQ는 `3.13.x`와 `4.4.x`, Redis는 `6.2` 이상을 지원 대상으로 한다.
- 버전별 Compose 파일을 다음 위치에 분리한다.
  - `res/docker/rabbitmq/rabbitmq-3.yml`
  - `res/docker/rabbitmq/rabbitmq-4.yml`
  - `res/docker/redis/redis-6.yml`
  - `res/docker/redis/redis-7.yml`
- RabbitMQ 컨테이너는 각각 `RabbitMQ-3`, `RabbitMQ-4`로 생성하고 다음 플러그인을 활성화한다.
  - `rabbitmq_management`
  - `rabbitmq_prometheus`
  - `rabbitmq_shovel`
  - `rabbitmq_shovel_management`
- RabbitMQ 포트는 다음처럼 호스트 loopback에 게시한다.

  | 컨테이너 | AMQP | Management | Prometheus |
  | --- | --- | --- | --- |
  | `RabbitMQ-3` | `55630:5672` | `55631:15672` | `55632:15692` |
  | `RabbitMQ-4` | `55640:5672` | `55641:15672` | `55642:15692` |

- Redis 컨테이너는 `Redis-6`, `Redis-7`로 생성하고 다음 포트를 호스트 loopback에 게시한다.
  - `Redis-6`: `56376:6379`
  - `Redis-7`: `56377:6379`
- 모든 컨테이너는 시작 준비 상태를 확인하는 health check를 제공한다.
- Docker Compose 리소스는 테스트용이며 운영 자격 증명이나 호스트 전체 인터페이스에 대한 포트 공개를 포함하지 않는다.
- GitHub Actions에서 `test`는 `tests/` 루트의 코어 테스트만 실행한다. `test-rabbitmq`와 `test-redis`는 각각 해당 브로커 전용 테스트와 Worker 호환성 테스트를 실행한다.
- RabbitMQ `3.13.x`·`4.4.x`, Redis `6.2`·`7.4` 각각에 대해 지원 Python 버전 `3.9`~`3.14`를 조합해 검증한다. 브로커별 검증은 브로커 버전과 Python 버전의 전체 조합으로 실행한다.
- 코어 테스트는 `tests/` 루트에 두고, RabbitMQ 전용 테스트와 Redis 전용 테스트는 각각 `tests/rabbitmq/`, `tests/redis/`에 분리한다. 전체 테스트 discovery는 세 위치의 테스트를 모두 포함해야 한다.

## 완료 기준

- 각 Compose 파일이 해당 컨테이너 이름, 이미지 계열, 호스트 포트와 health check를 선언한다.
- RabbitMQ 컨테이너 시작 시 네 플러그인이 모두 활성화된다.
- 동일 브로커의 버전별 컨테이너를 겹치지 않는 포트로 실행할 수 있다.
- Docker Compose 설정 검증이 성공하고, Docker 엔진이 사용 가능한 환경에서 컨테이너 기동·health check와 플러그인 활성화를 확인한다.
- GitHub Actions가 코어 테스트와 브로커별 테스트를 분리하고, 브로커마다 지원 버전과 Python 버전의 모든 조합을 검증한다.
- `tests/` 루트에는 코어 테스트만 남고, 브로커 전용 테스트는 각 브로커 디렉터리에서 독립적으로 발견·실행된다.

## 통합 테스트 연결 설정

- RabbitMQ 통합 테스트는 `RABBITMQ_PORT`를 사용하고, 미설정 시 기존 기본 포트 `5672`를 사용한다.
- Redis 통합 테스트는 `REDIS_PORT`를 사용하고, 미설정 시 기존 기본 포트 `6379`를 사용한다.
- RabbitMQ·Redis 통합 테스트는 각각 `RABBITMQ_TESTS`, `REDIS_TESTS`가 `'1'`일 때 활성화한다.
- Compose 컨테이너 이름은 `RabbitMQ-3`, `RabbitMQ-4`, `Redis-6`, `Redis-7`이며, 컨테이너를 동시에 실행할 수 있도록 호스트 포트 매핑을 구분한다.

## 확인된 제한사항

- 로컬 환경의 Docker 엔진이 실행되지 않으면 실제 이미지 pull, 컨테이너 기동과 플러그인 상태를 검증할 수 없다. 이 경우 Compose 정적 설정 검증과 미실행 사유를 구분해 기록한다.
