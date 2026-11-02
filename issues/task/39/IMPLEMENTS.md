# 구현 결과

RabbitMQ 3.13·4.4와 Redis 6.2·7.4의 버전별 테스트용 Compose 환경을 추가하고, 로컬 테스트와 GitHub Actions가 각 버전의 포트에 연결하도록 구성했다. RabbitMQ 네 플러그인, 브로커 health check, 별도 컨테이너 이름 및 loopback 한정 포트 공개를 포함한다.

통합 테스트의 환경변수 포트 지정은 기존 기본 포트를 보존한다. CI는 `test`에서 코어 테스트만 실행하고, `test-rabbitmq`와 `test-redis`에서 해당 브로커 전용 테스트와 Worker 호환성 테스트를 각각 실행한다. 브로커 job은 브로커 버전과 Python 3.9~3.14의 전체 조합을 매트릭스로 사용하고 해당 Compose project만 정리한다. 로컬 실행 절차는 [RabbitMQ 안내](../../../res/docker/rabbitmq/README.md)와 [Redis 안내](../../../res/docker/redis/README.md)에 각각 정리했다.

코어 테스트는 `tests/` 루트에, RabbitMQ와 Redis 전용 테스트는 각각 `tests/rabbitmq/`, `tests/redis/`에 분리했다. `tests`를 패키지로 탐색하고 지원 모듈을 `tests.*`로 가져와 `redis` 테스트 디렉터리가 외부 Redis 클라이언트 import를 가리지 않게 했다. 이동한 로그 테스트의 샘플 경로도 프로젝트 루트를 기준으로 조정했다.

`tests/test_broker_packaging.py`는 저장소 루트의 무시된 `DefStream.egg-info` 대신 실제 설치된 distribution 메타데이터를 선택하도록 수정했다. 전체 310개 테스트가 통과하고 15개가 건너뛰어졌으며, 브로커별 테스트도 각각 통과했다. 상세 내용은 [패키징 테스트 수정 구현 기록](./implements/1793626388737.md)과 [전체 테스트 검증 기록](./tasks/1793626388737.md)에 정리했다.

브로커 통합 테스트 활성화·포트 변수에서 `DEFSTREAM_` 접두사를 제거하고 CI, 테스트 지원 코드와 로컬 실행 안내를 함께 갱신했다. 새 환경 변수 이름을 사용하는 전체 테스트 310개가 통과하고 15개가 건너뛰어졌다. 자세한 내용은 [환경 변수 이름 변경 구현 기록](./implements/1793626820522.md)과 [검증 기록](./tasks/1793626820522.md)을 참고한다.

CI 테스트를 코어·RabbitMQ·Redis job으로 나누고 RabbitMQ 3.13·4.4, Redis 6.2·7.4 각각을 Python 3.9~3.14 전체 조합으로 검증하도록 매트릭스를 확장했다. 코어 전용 테스트 러너로 저장소 루트 테스트 207개 통과를 확인했다. 상세 변경과 제한은 [CI job 분리 구현 기록](./implements/1793627348502.md) 및 [검증 기록](./tasks/1793627348502.md)에 정리했다.

브로커 job ID는 `test-rabbitmq`, `test-redis`로 단순화했다. 별도 job의 기능과 매트릭스 구성은 그대로 유지했다.

실제 RabbitMQ 4.4 테스트에서 transient non-exclusive queue 선언 실패를 확인했다. 통합 테스트가 제품 기본 설정(`durable=True`)과 동일한 큐를 만들도록 수정했고, RabbitMQ 4.4 suite 전체가 통과했다. 자세한 내용은 [RabbitMQ 4 테스트 큐 호환성 수정](./implements/1793628366252.md)을 참고한다.

브로커별 CI job이 선택한 adapter만 설치하는 점에 맞춰 공통 메시지 fixture에서 RabbitMQ 전용 `Reject`와 Redis 연결 import를 제거했다. RabbitMQ와 Redis connection API 검증도 각 전용 suite로 옮겨 다른 adapter가 설치되지 않은 환경에서 테스트를 import할 수 있게 했다. 상세 변경은 [브로커별 메시지 테스트 의존성 분리](./implements/1793629199999.md)에 기록했다.

로컬 Docker에서 네 브로커의 health check와 RabbitMQ 플러그인 상태를 확인하고 Python 3.9·3.10·3.12·3.14 조합 16개를 통과했다. Actions 실행 #41459408504에서는 코어 job은 통과했지만 RabbitMQ·Redis 24개 job이 교차 import로 실패했다. 해당 import 문제는 수정했으며 수정 후 CI 재실행은 아직 확인하지 않았다. 실패 원인과 로컬 검증은 [브로커별 메시지 테스트 import 격리 검증](./tasks/1793629199998.md)에 정리했다.

Compose 설정과 이전 정적 검증은 [기존 작업 기록](./tasks/1793623390265.md)에, 테스트 분리와 검증은 [테스트 분리 작업 기록](./tasks/1793625269565.md)에 정리했다.

## 단계별 구현 기록

- [버전별 RabbitMQ·Redis 테스트 환경 추가](./implements/1793623390266.md)
- [코어·브로커 테스트 분리](./implements/1793625464717.md)
- [패키징 테스트 메타데이터 선택 수정](./implements/1793626388737.md)
- [브로커 테스트 환경 변수 이름 변경](./implements/1793626820522.md)
- [CI 테스트 job 분리와 버전 매트릭스](./implements/1793627348502.md)
- [브로커별 메시지 테스트 의존성 분리](./implements/1793629199999.md)
