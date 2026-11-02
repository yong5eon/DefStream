# 작업 계획

## 대상 요구사항

- RabbitMQ `3.13.x`·`4.4.x` 및 지정된 네 플러그인
- Redis `6.2`·`7.4` 경계 버전 검증
- 브로커별·버전별 Compose 파일, 컨테이너 이름, loopback 포트와 health check
- `tests/`의 코어 테스트와 `tests/rabbitmq/`, `tests/redis/`의 브로커 전용 테스트 분리
- 로컬 및 GitHub Actions 통합 테스트 실행

## 수행 순서

1. `res/docker/rabbitmq/`와 `res/docker/redis/`에 버전별 Compose 파일을 작성하고 RabbitMQ의 활성 플러그인 설정을 추가한다.
2. 구성 파일의 이미지, 고정 컨테이너 이름, 포트, health check와 플러그인 설정을 정적으로 검증한다.
3. 테스트가 Compose가 게시하는 RabbitMQ 포트 `55630`·`55640`, Redis 포트 `56376`·`56377`에 연결할 수 있도록 기존 통합 테스트 설정을 확인하고 필요한 부분만 조정한다.
4. 코어 테스트를 `tests/` 루트에 두고 RabbitMQ·Redis 전용 테스트를 각각 하위 디렉터리에 분리한다. 전체 discovery에서 외부 `redis` 클라이언트 패키지가 테스트 디렉터리에 가려지지 않도록 패키지 경로를 설정한다.
5. GitHub Actions에서 `test` job은 코어 테스트만 실행하고, `test-rabbitmq`·`test-redis` job은 각 브로커의 전용 테스트와 Worker 호환성 테스트를 수행하도록 분리한다. 각 브로커 job은 해당 브로커의 지원 버전과 Python `3.9`~`3.14`의 전체 조합을 매트릭스로 실행한다.
6. Docker 엔진이 사용 가능하면 각 Compose 리소스를 기동하여 health check, RabbitMQ 플러그인 활성화와 통합 테스트를 검증한다. 사용할 수 없으면 실행하지 못한 범위를 기록한다.
7. 로컬 실행·종료 방법과 포트·플러그인 정보를 작업 기록 및 필요한 문서에 반영하고 상대 링크를 검증한다.

## 진행 상태

- [x] 버전별 Compose 파일, 컨테이너 이름, 포트, health check와 RabbitMQ 플러그인 설정 추가
- [x] 네 Compose 파일의 구문·이미지·컨테이너 이름·포트 검증
- [x] 통합 테스트 포트 환경변수 연결
- [x] 코어·RabbitMQ·Redis 테스트 디렉터리 분리 및 전체 discovery 연결
- [x] 코어·RabbitMQ·Redis CI job 분리, 브로커 버전 × Python 버전 전체 매트릭스와 플러그인 검사·정리 절차 추가
- [ ] 실제 컨테이너 기동·health check·플러그인 및 브로커 통합 테스트: 로컬 Docker 엔진을 사용할 수 없어 미실행
- [x] 로컬 실행 문서와 작업 기록 갱신

## 검증 방법

- Docker Compose 설정 검증 명령으로 네 Compose 파일을 각각 확인한다.
- 통합 테스트를 RabbitMQ `3.13.x`와 `4.4.x`, Redis `6.2`와 `7.4`에 연결하여 실행한다.
- RabbitMQ `rabbitmq-plugins list --enabled` 결과에서 네 플러그인을 확인한다.
- 저장소의 기존 CI 테스트 범위와 패키지 검증이 유지되는지 확인한다.

## 실행 결과

- `docker compose config --format json`으로 네 Compose 파일의 구문을 검사하고 각 이미지, Compose project 이름, 컨테이너 이름과 포트 매핑을 확인했다.
- 코어 테스트를 `tests/`, RabbitMQ 테스트를 `tests/rabbitmq/`, Redis 테스트를 `tests/redis/`에 분리했다. 패키지 경로 기반 unittest discovery와 `tests/redis` 이름 충돌 방지 설정을 적용했다.
- 브로커별 discovery는 RabbitMQ 71개(7개 건너뜀), Redis 32개(8개 건너뜀)로 통과했다. 변경된 코어 Inspector·Play·runner hook 테스트 40개, 명세 테스트 28개, 메시지 테스트 11개(3개 건너뜀)도 통과했다.
- 저장소 루트의 로컬 egg-info가 설치된 distribution보다 우선 선택되는 문제를 패키징 테스트에서 해결했다. CI와 같은 외부 작업 디렉터리에서 전체 discovery를 실행해 310개 테스트 통과와 15개 건너뜀을 확인했다.
- RabbitMQ 71개(7개 건너뜀), Redis 32개(8개 건너뜀) 테스트와 GitHub Actions YAML 파싱, `git diff --check`도 통과했다. 상세 결과는 [패키징 테스트 수정 및 전체 테스트 검증 기록](./tasks/1793626388737.md)을 참고한다.
- 브로커 테스트 환경 변수 이름에서 `DEFSTREAM_` 접두사를 제거하고 CI, 테스트, 로컬 실행 안내와 요구사항 명세를 갱신했다. 새 포트 변수 조회 및 전체 310개 테스트(15개 건너뜀)를 통과했다. 자세한 내용은 [브로커 테스트 환경 변수 이름 변경 검증](./tasks/1793626820522.md)에 기록했다.
- CI에서 코어 테스트를 루트 테스트 모듈로 제한하고 RabbitMQ·Redis job을 각각 분리했다. 각 브로커 job은 두 지원 버전과 Python 3.9~3.14의 12개 조합을 실행하도록 구성했다. 전용 core runner에서 코어 테스트 207개가 통과했으며 YAML 구조상 총 6개 코어 조합과 브로커별 12개 조합이 확인됐다. Docker 엔진이 없어 매트릭스의 실제 브로커 실행은 검증하지 못했다. 자세한 내용은 [CI 테스트 매트릭스 분리 기록](./tasks/1793627348502.md)을 참고한다.
- 브로커 job ID를 `test-rabbitmq`, `test-redis`로 단순화하고 publish 의존 관계와 이슈 기록을 갱신했다. 변경 내용은 [CI 브로커 job 이름 단순화 기록](./tasks/1793627590185.md)에 기록했다.
- RabbitMQ 3.13·4.4와 Redis 6.2·7.4를 기동해 health check를 통과시켰고 RabbitMQ 필수 플러그인을 확인했다. 설치된 Python 3.9·3.10·3.12·3.14 각 버전에서 네 브로커 테스트를 실행해 16개 조합을 통과했다. 최초 RabbitMQ 4.4 실행에서 확인된 transient non-exclusive queue 호환성 문제는 테스트 큐를 제품 기본 계약과 일치하도록 durable하게 선언해 해결했다. 상세 결과는 [Docker 기반 통합 테스트 기록](./tasks/1793628366252.md), 수정 내용은 [구현 기록](./implements/1793628366252.md)을 참고한다.
- Python 3.11 및 3.13 인터프리터는 로컬에 없어 실제 테스트를 수행하지 못했다. 두 버전을 포함한 전체 24개 브로커 × Python 조합의 완료 여부는 GitHub Actions 결과를 확인해야 한다.
