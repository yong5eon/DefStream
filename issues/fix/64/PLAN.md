# RabbitMQ Consumer의 Recoverable 명시적 상속 작업 계획

## 목표와 선행 조건

[요구사항 명세](./REQUIREMENTS.md)의 R1~R5를 충족하고 기존 Consumer 생성, 런타임 판별과 오류 분류를 유지한다. 작업 대상과 분기 기준은 [이슈 기록](./README.md)을 따른다.

- 작업 전과 파일 수정 묶음 직전에 실제 브랜치가 `fix/64`인지 확인한다.
- 기존 사용자 변경을 보존하고 이번 이슈와 무관한 변경을 포함하지 않는다.
- 명세 범위를 벗어나는 계약 변경이 필요하면 구현을 중단하고 요구사항을 먼저 확인한다.

## 변경 대상

| 대상 | 변경 내용 |
| --- | --- |
| [RabbitMQ Consumer](../../../src/Broker/Implements/RabbitMQ/Consumer.py) | `Recoverable` import와 `Consumer(BaseConsumer, Recoverable)` 선언 |
| [Protocol 계약 테스트](../../../tests/test_protocol_contracts.py) | 직접 상속, 인스턴스 생성과 런타임 판별 검증 |
| 이슈 문서와 실행 기록 | 실제 구현·검증 결과, 진행 상태와 고객용 변경 로그 기록 |

[오류 분류 테스트](../../../tests/test_worker_recovery.py)는 기존 회귀 검증에 활용한다. 새 검증이 필요하지 않으면 수정하지 않는다.

## 수행 순서

1. **직접 관련된 회귀 테스트 보강 — R1, R2, R4, R5**
   - 기존 `test_recovery_capability_is_structural_and_opt_in`에 `Recoverable in RabbitConsumer.__bases__` 검증을 추가한다.
   - 기존 Mock 기반 생성 패턴을 사용해 RabbitMQ Consumer가 생성되고 `isinstance(consumer, Recoverable)`가 `True`임을 검증한다. 테스트 종료 시 Consumer를 정리한다.
   - 기존 구조적 구현체, 공통 Consumer와 Redis Consumer에 대한 검증을 유지한다.
   - 제품 코드 변경 전 보강한 테스트를 실행해 직접 상속 검증이 실패하는지 확인한다.
2. **명시적 상속 적용 — R1, R3**
   - 기존 `DefStream.Broker` import에 `Recoverable`을 추가한다.
   - 클래스 선언만 `Consumer(BaseConsumer, Recoverable)`로 변경한다.
   - 생성자, `is_recoverable` 구현과 Worker·Executor는 변경하지 않는다.
3. **인수 기준과 기존 동작 검증 — R1~R5**
   - 아래의 관련 테스트를 한 번의 실행으로 검증한다.
   - 소스 차이에서 생성자와 오류 분류 구현이 유지되고 import·상속 선언 및 직접 관련 테스트만 변경되었는지 확인한다.
   - 실패하면 원인을 구분한다. 이번 변경에 직접 관련된 문제만 해결하고, 근거 없이 전체 테스트나 외부 RabbitMQ 통합 검증으로 범위를 확대하지 않는다.
4. **결과와 문서 정리**
   - 의미 있는 구현 단계는 `implements/`, 테스트와 확인 결과는 `tasks/`에 기록한다.
   - 구현 후 `IMPLEMENTS.md`와 `TASKS.md`에 실제 결과와 제한사항을 정리하고 README와 이 계획의 상태를 갱신한다.
   - 공개 API·사용법·운영 절차 변경 여부를 확인한다. 영향이 없으면 상세 매뉴얼을 억지로 수정하지 않고 근거를 기록한다.
   - 실제 반영 내용만 `CHANGELOG.md`에 작성한다. 요구사항·계획 작성이나 테스트 통과 자체를 고객 변경 사항으로 나열하지 않는다.

## 인수 기준별 검증

| 검증 내용 | 방법 | 요구사항 |
| --- | --- | --- |
| 명시적 직접 상속 | 클래스 선언 및 `Recoverable in RabbitConsumer.__bases__` 확인 | R1, R5 |
| 기존 생성과 런타임 판별 | Mock 연결로 생성한 인스턴스와 `isinstance` 확인 | R2, R4 |
| 구조적 구현체 지원과 공통·Redis Consumer 비지원 | 기존 Protocol 계약 테스트 유지 및 실행 | R4 |
| 복구 가능·불가능 오류와 콜백 오류 분류 유지 | 기존 오류 분류 테스트 실행 및 구현 불변 확인 | R3 |
| ACK 시간 초과 감지와 복구 가능 판정 유지 | 기존 채널 종료 감지 테스트 실행 | R3 |

저장소 루트에서 프로젝트 의존성이 설치된 환경의 `python`으로 다음 명령을 실행한다. 기존 Windows 콘솔 인코딩 문제를 피하기 위해 UTF-8 모드를 사용한다. 선택한 테스트는 실제 RabbitMQ 서버 연결을 요구하지 않는다.

```shell
python -X utf8 -m unittest tests.test_protocol_contracts tests.test_worker_recovery.RecoveryTests.test_ack_timeout_and_exception_classification tests.test_worker_recovery.RecoveryTests.test_closed_idle_channel_is_detected_without_settlement
```

문서 완료 시 상대 링크와 경로 표기를 검사하고 `git diff --check`로 공백 오류를 확인한다. 전체 변경 목록에서 무관한 파일, 임시 산출물과 민감정보가 포함되지 않았는지도 확인한다.

## 진행 상태

- [x] 요구사항 분석과 명세 작성
- [x] 작업 계획 수립
- [x] 회귀 테스트 보강과 변경 전 실패 확인
- [x] 명시적 상속 적용
- [x] 인수 기준 검증
- [x] 결과 기록과 변경 로그 정리

계획의 구현·검증과 결과 기록을 완료했다. 변경 전 실패 및 변경 후 테스트 14개 통과를 실제 실행으로 확인했다. 수행 결과와 제한사항은 [구현 결과](./IMPLEMENTS.md) 및 [작업 결과](./TASKS.md)를 따른다. 커밋·푸시·병합·이슈 종료는 수행하지 않았다.
