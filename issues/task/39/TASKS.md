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

버전 조사 결론은 Compose·CI 구성에 반영했고, 로컬 Docker에서 네 브로커와 16개 브로커 × Python 조합을 검증했다. 교차 import를 수정한 뒤 Actions 실행 #41461742854에서 코어와 브로커 매트릭스 24개 job이 모두 통과했다. PR 리뷰 지적 두 건을 추가로 수정했으며, 해당 수정 후 CI 재실행을 기다리고 있다.

## 검증 작업

- Compose 설정, CI YAML, Python 문법 및 이전 테스트 실행 결과는 [Compose 구성 검증 기록](./tasks/1793623390265.md)에 정리했다.
- 코어·브로커별 테스트 재구성과 최신 테스트 결과는 [테스트 분리·검증 기록](./tasks/1793625269565.md)에 정리했다.

## 테스트 분리·검증 결과

- 코어 테스트는 `tests/` 루트에 유지하고 RabbitMQ·Redis 전용 테스트를 각각 `tests/rabbitmq/`, `tests/redis/`로 분리했다. `tests/__init__.py`와 `tests.*` import 경로를 사용하여 전체 discovery에서 외부 `redis` 라이브러리와 이름이 충돌하지 않게 했다.
- RabbitMQ 전용 discovery는 71개 테스트 중 7개, Redis 전용 discovery는 32개 중 8개를 브로커 미설정으로 건너뛰고 통과했다. 변경된 코어 테스트와 명세·메시지 테스트도 통과했다.
- 저장소 루트의 무시된 `DefStream.egg-info`가 설치된 editable distribution보다 먼저 선택되어 패키징 테스트 4개가 실패하는 원인을 확인했다. 테스트가 저장소 루트 자체의 메타데이터 항목을 제외하고 설치된 distribution을 조회하도록 수정했다.
- CI가 저장소 밖에서 실행하는 전체 테스트 discovery에도 프로젝트 top-level 경로를 지정하도록 수정했다. 미지정 시 하위 테스트의 `tests.*` import가 깨지는 것을 재현했고, 수정 명령으로 전체 310개 테스트가 import 오류 없이 발견됨을 확인했다.
- CI와 같은 외부 작업 디렉터리에서 UTF-8 출력 설정과 프로젝트 top-level 경로를 지정해 전체 310개 테스트를 실행했으며, 15개를 건너뛰고 통과했다. RabbitMQ 71개(7개 건너뜀)와 Redis 32개(8개 건너뜀) 테스트도 각각 통과했다.
- 이 단계에서는 GitHub Actions YAML 파싱과 `git diff --check`를 통과했지만 Docker 엔진이 없어 컨테이너 통합 테스트는 실행하지 못했다. 이후 실행한 로컬 브로커 통합 테스트 결과는 [Docker 기반 브로커 × Python 통합 테스트 기록](./tasks/1793628366252.md)에 정리했다.
- 이후 GitHub Actions 실행 #41459408504에서는 코어 job이 통과하고 브로커 매트릭스 24개 job이 공통 `tests.test_task_messages`를 통한 RabbitMQ·Redis 교차 import로 실패했다. 공통 fixture를 broker-free 모듈로 분리하고 adapter별 API 검증을 각 suite로 옮긴 뒤, 공통 메시지 테스트 8개와 브로커별 import 격리 테스트를 통과시켰다. 수정 후 Actions 재실행은 대기 중이다. 상세 결과는 [브로커별 메시지 테스트 import 격리 검증](./tasks/1793629199998.md)에 기록했다.
- PR 리뷰에서 RabbitMQ 플러그인 부분 문자열 검사로 인한 오탐 가능성과 미사용 import 두 건을 지적받아 수정했다. Inspector Play 테스트 21개와 정확한 전체 줄 비교 동작을 검증했다. 변경 후 CI 결과는 아직 없으며 [PR 리뷰 수정 검증](./tasks/1793631035345.md)에 정리했다.

## 단계별 기록

- [RabbitMQ 지원 버전 및 플러그인 조사](./tasks/1793620359610.md)
- [RabbitMQ 3.x·4.x 지원 범위 결정](./tasks/1793621161604.md)
- [Redis Streams 최소 지원 버전 조사](./tasks/1793621502459.md)
- [Redis 최소 버전 및 CI 검증 대상 결정](./tasks/1793621903677.md)
- [Docker 구성 및 기존 테스트 검증](./tasks/1793623390265.md)
- [브로커별 테스트 분리와 검증](./tasks/1793625269565.md)
- [패키징 테스트 수정 및 전체 테스트 검증](./tasks/1793626388737.md)
- [브로커 테스트 환경 변수 이름 변경 검증](./tasks/1793626820522.md)
- [CI 테스트 job 분리 및 매트릭스 검증](./tasks/1793627348502.md)
- [CI 브로커 job 이름 단순화](./tasks/1793627590185.md)
- [Docker 기반 브로커 × Python 통합 테스트](./tasks/1793628366252.md)
- [브로커별 메시지 테스트 import 격리 검증](./tasks/1793629199998.md)
- [PR 리뷰 수정 검증](./tasks/1793631035345.md)

## Redis 참고 자료

- [Redis Streams 소개](https://redis.io/docs/latest/develop/data-types/streams/)
- [`XGROUP CREATE` — Redis 5.0부터](https://redis.io/docs/latest/commands/xgroup-create/)
- [`XREADGROUP` — Redis 5.0부터](https://redis.io/docs/latest/commands/xreadgroup/)
- [`XACK` — Redis 5.0부터](https://redis.io/docs/latest/commands/xack/)
- [`XAUTOCLAIM` — Redis 6.2부터](https://redis.io/docs/latest/commands/xautoclaim/)
- 저장소 Redis 매뉴얼: [Redis.md](../../../docs/Redis.md)
- Redis 소비 기본값과 자동 회수 호출: [Consumer.py](../../../src/Broker/Implements/Redis/Consumer.py)
