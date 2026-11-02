# RabbitMQ·Redis 지원 버전 조사

## 조사 결과

- 현재 GitHub Actions 통합 테스트는 `rabbitmq:4.1`과 `redis:7.4`를 사용합니다. 이는 테스트에 고정된 버전이며 프로젝트 전체의 브로커 지원 범위를 선언하지 않습니다.
- RabbitMQ 매뉴얼은 `Subscription.timeout` 기능에 RabbitMQ 3.12 이상이 필요하다고 명시합니다. 이는 해당 기능의 최소 버전이지, 전체 RabbitMQ 어댑터의 지원 최소 버전이라고 확인된 것은 아닙니다.
- 기존 작업 기록에는 RabbitMQ 3.13.7의 어댑터 테스트 검증이 있습니다. 현재 버전까지 포함하는 연속적인 지원 범위나 테스트 매트릭스는 확인되지 않았습니다.
- RabbitMQ 공식 지원 정보에서 조사 시점에 확인한 커뮤니티 지원 계열은 4.3.x와 4.4.x입니다. 4.3.x의 커뮤니티 지원은 2027-01-31, 4.4.x는 2027-07-31까지로 안내되어 있습니다. 3.13.x는 공식 지원표에 없으며, 현재 CI의 4.1도 커뮤니티 지원 계열이 아닙니다.
- 공식 플러그인 문서는 관리 플러그인이 RabbitMQ 배포판에 포함되며, Prometheus 지원과 Shovel도 배포판 플러그인으로 제공됨을 설명합니다. 저장소에는 이 플러그인들을 활성화하는 컨테이너 설정이 아직 없습니다.
- 사용자 결정에 따라 RabbitMQ는 각 메이저의 최신 마이너 계열인 3.13.x와 4.4.x를 대상으로 합니다. 3.13.x는 upstream 커뮤니티 지원 범위를 벗어났지만, DefStream의 호환성 대상으로 유지합니다.
- Redis Streams 자체는 5.0에서 도입됐지만, DefStream 기본 소비 복구 기능은 6.2에서 추가된 `XAUTOCLAIM`에 의존합니다. `reclaim_idle`의 기본값이 60,000ms이므로 옵션을 따로 끄지 않은 기본 Worker 동작을 지원하려면 Redis 6.2 이상이 필요합니다.
- 저장소의 Redis 매뉴얼도 Redis 6.2 이상을 요구하고, GitHub Actions는 `redis:7.4`를 사용합니다. 따라서 6.2는 기능상 하한이고 7.4는 현재 CI 검증 버전이며, 이 정보만으로 지원 상한 또는 모든 버전의 검증을 의미하지는 않습니다.
- 사용자 결정에 따라 Redis 지원 하한을 6.2로 확정하고, CI에서는 Redis 6.2와 현재 검증 버전인 7.4를 대상으로 합니다. Redis 5.0 이상이 Streams를 제공한다는 사실만으로 5.x를 지원 대상으로 포함하지 않습니다.

## 참고 자료

- [RabbitMQ Release Information](https://www.rabbitmq.com/release-information)
- [RabbitMQ Plugins](https://www.rabbitmq.com/docs/plugins)
- [RabbitMQ Management Plugin](https://www.rabbitmq.com/docs/management)
- [RabbitMQ Prometheus Monitoring](https://www.rabbitmq.com/docs/prometheus)
- [RabbitMQ Shovel Plugin](https://www.rabbitmq.com/docs/shovel)
- 저장소 CI: [ci.yml](../../../.github/workflows/ci.yml)
- RabbitMQ 기능별 요구 버전: [RabbitMQ.md](../../../docs/RabbitMQ.md)
- 기존 RabbitMQ 3.13.7 검증 기록: [IMPLEMENTS.md](../../../issues/feature/1/IMPLEMENTS.md)

## 다음 단계

RabbitMQ와 Redis의 범위 결정이 끝났습니다. 확정한 버전 범위와 플러그인 요구사항을 `REQUIREMENTS.md`와 `PLAN.md`에 정리한 뒤 Docker 리소스와 CI 매트릭스에 반영합니다.

## 단계별 기록

- [RabbitMQ 지원 버전 및 플러그인 조사](./tasks/1793620359610.md)
- [RabbitMQ 3.x·4.x 지원 범위 결정](./tasks/1793621161604.md)
- [Redis Streams 최소 지원 버전 조사](./tasks/1793621502459.md)
- [Redis 최소 버전 및 CI 검증 대상 결정](./tasks/1793621903677.md)

## Redis 참고 자료

- [Redis Streams 소개](https://redis.io/docs/latest/develop/data-types/streams/)
- [`XGROUP CREATE` — Redis 5.0부터](https://redis.io/docs/latest/commands/xgroup-create/)
- [`XREADGROUP` — Redis 5.0부터](https://redis.io/docs/latest/commands/xreadgroup/)
- [`XACK` — Redis 5.0부터](https://redis.io/docs/latest/commands/xack/)
- [`XAUTOCLAIM` — Redis 6.2부터](https://redis.io/docs/latest/commands/xautoclaim/)
- 저장소 Redis 매뉴얼: [Redis.md](../../../docs/Redis.md)
- Redis 소비 기본값과 자동 회수 호출: [Consumer.py](../../../src/Broker/Implements/Redis/Consumer.py)
