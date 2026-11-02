# RabbitMQ·Redis 지원 범위에 맞는 테스트·워크플로용 Docker 설정 리소스 제공

## 이슈 정보

| 항목 | 내용 |
| --- | --- |
| 출처 | GitHub Issues |
| 저장소 | `yong5eon/DefStream` |
| 원본 이슈 | [#39](https://github.com/yong5eon/DefStream/issues/39) |
| 상태 | Open |
| 유형·레이블 | 작업 (`task`, 원본 이슈에 적용됨) |
| 로컬 진행 상태 | 네 브로커 버전과 Python 3.9·3.10·3.12·3.14의 16개 조합 통과; Actions 실행 #41459408504에서 코어 job은 통과하고 브로커 24개 job은 선택하지 않은 어댑터 import로 실패; import 분리를 로컬 수정했고 Actions 재실행 대기 |
| 작업 브랜치 | `task/39` |
| 분기 기준 | `master` |
| 병합 대상 브랜치 | 미지정 |

## 원본 이슈

## 목적

DefStream의 RabbitMQ와 Redis 지원 범위에 맞는 Docker 설정 리소스를 제공하여, 로컬 테스트와 GitHub Actions 워크플로에서 재현 가능한 브로커 환경을 사용할 수 있도록 합니다. 이 이슈는 추후 수행할 작업을 등록하는 것이며 현재 구성이 제공되었다는 의미는 아닙니다.

## 작업 범위

- 프로젝트의 RabbitMQ와 Redis 지원 버전 및 필요한 구성 범위를 확인하고, 그 범위에 맞는 Docker 설정 리소스를 제공합니다. 지원 범위가 불명확하면 구현 전에 확정하며 임의로 버전을 확대하거나 축소하지 않습니다.
- 테스트에 필요한 브로커 설정, 연결 정보, 준비 상태 확인 방법을 포함하여 일관된 테스트 환경을 구성합니다.
- 로컬 테스트와 GitHub Actions 워크플로에서 해당 리소스를 활용할 수 있도록 연결합니다. 지원 버전별 검증이 필요한 경우 확인된 지원 범위에 맞춰 테스트 구성을 마련합니다.
- 브로커가 준비된 뒤 테스트를 실행하고, 기동 실패·연결 실패·테스트 실패가 성공으로 처리되지 않도록 합니다.
- 테스트 환경의 기동·종료·정리 절차와 실행 방법을 한국어로 문서화하고, 관련 영문 문서는 프로젝트 지침에 따라 동기화합니다.
- 운영 자격 증명을 포함하지 않고, 테스트용 설정과 운영용 설정의 차이를 명확히 합니다. 로컬 사용자 데이터나 다른 컨테이너에 영향을 주지 않도록 테스트 자원을 구분합니다.

## 완료 기준

- [ ] RabbitMQ와 Redis의 지원 버전·구성 범위가 확인되고 Docker 리소스와 대응됨
- [ ] 제공된 리소스로 로컬 브로커 환경을 기동하여 관련 통합 테스트를 실행할 수 있음
- [ ] GitHub Actions에서 같은 지원 범위에 대한 브로커 테스트가 실행됨
- [ ] 브로커 준비 상태 확인, 실패 전파 및 테스트 자원 정리 동작이 검증됨
- [ ] 실행에 필요한 환경·명령·연결 설정·종료 및 정리 방법이 문서화됨
- [ ] 실제 검증한 버전과 테스트 범위, 검증하지 못한 범위가 기록됨

## 추가 요청사항

- RabbitMQ 컨테이너는 다음 플러그인을 활성화하여 생성합니다.
  - `rabbitmq_management`
  - `rabbitmq_prometheus`
  - `rabbitmq_shovel`
  - `rabbitmq_shovel_management`
- RabbitMQ는 각 메이저의 최신 마이너 계열인 `3.13.x`와 `4.4.x`를 지원 대상으로 조사·검증합니다. `3.13.x`는 RabbitMQ 자체의 커뮤니티 지원이 종료된 계열이므로, 이는 DefStream이 별도로 유지할 호환성 범위입니다.
- Redis Streams는 Redis 5.0에서 도입되었지만, DefStream은 기본 소비 복구에 Redis 6.2에서 도입된 `XAUTOCLAIM`을 사용하므로 지원 하한은 `6.2`입니다. Redis CI는 최소 버전인 `6.2`와 현재 CI 검증 버전인 `7.4`를 대상으로 합니다.
- Compose 파일은 `res/docker/rabbitmq/`와 `res/docker/redis/`에 두고, 컨테이너 이름은 각각 `RabbitMQ-3`, `RabbitMQ-4`, `Redis-6`, `Redis-7`로 지정합니다.

## 현재 진행 상태

- 네 Compose 파일, RabbitMQ 플러그인 설정, 통합 테스트 포트 연결과 CI 검증 job을 추가했습니다.
- 코어 테스트는 `tests/`, RabbitMQ 전용 테스트는 `tests/rabbitmq/`, Redis 전용 테스트는 `tests/redis/`로 분리하고 전체 discovery가 하위 테스트를 포함하도록 구성했습니다.
- CI가 저장소 외부에서 테스트를 실행할 때도 동일하게 탐색하도록 top-level 경로를 지정했습니다.
- 저장소 루트의 로컬 egg-info가 설치된 distribution 메타데이터를 가리는 문제를 패키징 테스트에서 해결했습니다. CI와 같은 외부 작업 디렉터리 기준 전체 310개 테스트가 통과했고 15개는 건너뛰었습니다.
- 로컬 Docker에서 네 브로커의 health check와 RabbitMQ 플러그인을 확인하고 16개 브로커 × Python 조합을 통과했습니다. Actions 실행 #41459408504에서는 코어 job이 통과했지만 브로커 job은 공통 메시지 테스트 모듈의 교차 import로 실패했습니다. 공통 fixture와 adapter별 검증을 분리했으며 수정 후 Actions 재실행은 대기 중입니다.

## 작업 기록

- [요구사항 명세서](./REQUIREMENTS.md)
- [작업 계획서](./PLAN.md)
- [RabbitMQ 로컬 테스트 환경](../../../res/docker/rabbitmq/README.md)
- [Redis 로컬 테스트 환경](../../../res/docker/redis/README.md)
- [구현 종합 기록](./IMPLEMENTS.md)
- [고객용 변경 로그](./CHANGELOG.md)
- [패키징 테스트 수정·전체 테스트 검증 기록](./tasks/1793626388737.md)
- [패키징 테스트 메타데이터 선택 수정](./implements/1793626388737.md)
- [브로커 환경 변수 이름 변경 작업 기록](./tasks/1793626820522.md)
- [브로커 테스트 환경 변수 이름 변경 구현 기록](./implements/1793626820522.md)
- [CI 매트릭스 분리 작업 기록](./tasks/1793627348502.md)
- [CI 테스트 job 분리 구현 기록](./implements/1793627348502.md)
- [CI 브로커 job 이름 단순화 기록](./tasks/1793627590185.md)
- [Docker 기반 브로커 × Python 통합 테스트 기록](./tasks/1793628366252.md)
- [RabbitMQ 4 테스트 큐 호환성 수정 기록](./implements/1793628366252.md)
- [브로커별 메시지 테스트 import 격리 검증](./tasks/1793629199998.md)
- [브로커별 메시지 테스트 의존성 분리](./implements/1793629199999.md)
- [테스트 분리·검증 작업 기록](./tasks/1793625269565.md)
- [테스트 분리 구현 기록](./implements/1793625464717.md)
- RabbitMQ 지원 버전 조사: [조사 결과](./TASKS.md), [단계별 기록](./tasks/1793620359610.md), [버전 범위 결정](./tasks/1793621161604.md)
- Redis Streams 최소 버전 조사: [조사 결과](./TASKS.md), [단계별 기록](./tasks/1793621502459.md)
- Redis 최소 버전 및 CI 검증 대상 결정: [단계별 기록](./tasks/1793621903677.md)
