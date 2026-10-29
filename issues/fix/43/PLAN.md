# 로거 이름 변경 작업 계획

## 작업 정보

| 항목 | 내용 |
| --- | --- |
| 원본 이슈 | [#43](https://github.com/yong5eon/DefStream/issues/43) |
| 요구사항 | [REQUIREMENTS.md](./REQUIREMENTS.md) |
| 작업 대상 | `yong5eon/DefStream` |
| 작업 브랜치 | `fix/43` |
| 분기 기준 | 로컬 `master`의 `23df707` |
| 병합 대상 브랜치 | 미지정 |
| 진행 상태 | 완료 |

## 진행 원칙

- 변경 범위와 인수 기준은 요구사항 명세를 따른다.
- RabbitMQ·Redis, Worker, Inspector 로거 이름과 계층만 요구된 형식으로 변경하고 로그 메시지·레벨·전파 정책은 유지한다.
- 모듈·import 경로와 공개 API는 유지하고, 로거를 사용하지 않는 Descriptor·Validator는 변경하지 않는다.
- 저장소 전체의 로거 이름 사용 테스트·문서·샘플을 새 계층과 일치시키되 API import 경로는 유지한다.
- 구현 중 영향 범위나 요구사항이 달라지면 이 계획과 요구사항 명세를 함께 갱신한다.
- 병합 대상이 지정되지 않았으므로 임의로 정하거나 병합하지 않는다.

## 작업 순서

| 단계 | 작업 | 관련 기준 | 상태 |
| --- | --- | --- | --- |
| 1 | RabbitMQ·Redis 구현체의 클래스별 로거 선언과 저장소 내 기존 로거 이름 참조를 확인해 변경 대상을 확정한다. | AC-01, AC-02, AC-04 | 완료 |
| 2 | RabbitMQ 클래스 로거 이름을 `Broker.RabbitMQ.<클래스명>`으로, Redis 클래스 로거 이름을 `Broker.Redis.<클래스명>`으로 변경한다. | AC-01, AC-02 | 완료 |
| 3 | 로거 이름, 계층 전파·루트 전파와 로그 캡처를 확인하는 기존 테스트를 새 이름에 맞게 갱신하고, Worker·Inspector 이름 및 import 경로 불변을 확인한다. | AC-03, AC-04 | 완료 |
| 4 | Operations, RabbitMQ, Redis의 한국어·영어 매뉴얼에서 브로커 로거 이름과 사용 예시를 갱신하고, 기존 이름으로 설정한 애플리케이션은 새 이름에 맞춰야 함을 안내한다. | AC-05 | 완료 |
| 5 | 관련 로깅 테스트와 필요한 회귀 테스트를 실행하고, 검색 결과·내부 링크·변경 범위를 확인한다. 발견한 이번 변경의 문제를 수정하고 검증을 반복한다. | AC-01–AC-05 | 완료 |
| 6 | Worker 로거는 `Worker`, Run 로거는 `Task`, Executor·Pool 계열은 `Worker.<클래스명>`으로, Inspector 확장 로거는 `Worker.Inspector.<클래스명>`으로 변경한다. | AC-04, AC-05 | 완료 |
| 7 | Worker·Inspector 이름과 로그 계층을 검증하도록 테스트를 갱신하고, 기존 공개 import 및 비대상 Descriptor·Validator 동작이 유지되는지 확인한다. | AC-04–AC-06 | 완료 |
| 8 | Worker 샘플 필터에 `Task` 계층을 반영하고, Operations·RabbitMQ 한국어·영어 로깅 설명 및 기존 logger 설정 변경 안내를 갱신한다. | AC-07 | 완료 |
| 9 | 브로커·Worker·Inspector 로깅 테스트, 관련 회귀 테스트, 검색 및 문서 링크를 검증하고 결과를 기록한다. | AC-01–AC-07 | 완료 |

## 인수 기준별 검증

| 인수 기준 | 검증 방법 |
| --- | --- |
| AC-01 | RabbitMQ 클래스별 로거 이름 테스트에서 새 형식을 확인하고 `DefStream.`이 없는지 검사한다. |
| AC-02 | Redis 클래스별 로거 이름 테스트에서 새 형식을 확인하고 `DefStream.` 및 `Implements.`가 없는지 검사한다. |
| AC-03 | 새 어댑터 상위 이름과 루트 이름으로 로그를 캡처하여 전파가 유지되고, 기록의 이름으로 필터링할 수 있는지 확인한다. |
| AC-04 | Worker 클래스별 새 이름, Pool 하위 클래스의 기본 이름 상속 및 로그 캡처 테스트를 실행한다. |
| AC-05 | Inspector 공용·확장 로거 이름과 `Worker.Inspector` 계층·루트 전파 테스트를 실행한다. |
| AC-06 | import·공개 API 테스트를 실행하고 Descriptor·Validator에서 로거 변경이 발생하지 않았는지 검색한다. |
| AC-07 | 브로커·Worker·Inspector 로깅 테스트를 실행하고 샘플 및 한국어·영어 매뉴얼의 새 이름과 설정 안내를 대조한다. |

## 검증 범위와 주의사항

- 우선 `tests/test_rabbitmq_logging.py`, `tests/test_redis_logging.py`, `tests/test_logging.py` 및 브로커 패키징·공개 API 관련 테스트에서 새 이름과 유지 계약을 확인한다.
- 저장소 검색으로 기존 브로커 로거 이름을 참조하는 문서·샘플·테스트가 남아 있지 않은지 확인한다. import 경로의 `DefStream.Broker.Implements.*`는 제거 대상이 아니다.
- `DefStream.Worker`·`DefStream.Inspector` import 경로는 유지하고 logger 설정·검증 문자열만 새 이름으로 갱신한다.
- Worker 로그 이름은 `Worker`와 `Task`로 구분되므로 Worker 로그 필터 예제에는 두 계층을 모두 포함한다.
- Descriptor·Validator에는 로거가 없으므로 변경하지 않는다.
- 전체 테스트 실행 여부는 관련 테스트 결과와 환경 의존성을 확인한 뒤 결정하고, 실행하지 않은 검증은 완료로 기록하지 않는다.
- 구현 후 매뉴얼 영향 검토 및 변경 로그 작성은 실제 변경과 결과를 확인한 뒤 진행한다.
- 커밋·푸시·PR 생성은 별도 요청이 있을 때만 수행한다.

## 완료 결과

- 브로커 로거 이름·테스트·샘플·한국어·영어 매뉴얼 변경과 인수 기준 검증을 완료했다.
- 테스트 상세 결과와 패키징 검증 환경 제한은 [작업 기록](./tasks/1793260818661.md)에 기록했다.
- 일반 배포 패키지 메타데이터를 사용하는 `test_broker_packaging.py` 검증은 현재 editable 설치 환경 때문에 완료하지 못했다.

Worker·Inspector 로거 변경 범위까지 확장해 구현과 요구사항 검증을 완료했다. 확장 구현 결과는 [구현 기록](./implements/1793261447018.md), 추가 이름 변경에 맞춘 테스트·샘플·문서 정합성 확인은 최신 [작업 기록](./tasks/1793262314955.md)에 정리했다.
