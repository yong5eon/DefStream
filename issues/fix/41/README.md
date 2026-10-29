# RabbitMQ INFO 로그 과다 조정

## 이슈와 작업 상태

- 원본: GitHub Issues [yong5eon/DefStream #41](https://github.com/yong5eon/DefStream/issues/41)
- 제목: DefStream.Broker.Implements.RabbitMQ 에서 정보 레벨의 로깅이 너무 지나치게 많음
- 유형: 변경(`fix`), 원본의 `fix` 레이블 적용 상태 재조회 완료
- 작업 대상: `yong5eon/DefStream`, 작업 브랜치 `fix/41`
- 분기 기준: 작업 시작 시 깨끗한 로컬 `master`의 `7e7ea49`
- 병합 대상: 미확정. 기본 브랜치를 병합 대상으로 임의 지정하지 않으며, 병합 준비 전에 확인 필요
- 진행 상태: 분석과 사용자 제공 로그 집계 완료. `Connection`의 정상 연결·자원 작업 성공 로그와 사용자 요청에 따른 `Consumer` 생명주기 로그를 DEBUG로 조정하는 구현과 검증 완료. 커밋·푸시·PR은 수행하지 않음

## 이슈 원문

아래는 조회한 본문 원문이며, 댓글은 없습니다.

### 변경 유형

일반 변경

### 변경 목적

DefStream.Broker.Implements.RabbitMQ 에서 정보 레벨의 로기이 너무 지나치게 많아서 다른 로그를 보기 힘들 수준

### 제안하는 변경 내용

DefStream.Broker.Implements.RabbitMQ 에서 적절한 레벨로 조절

### 영향 범위

_No response_

### 긴급 수정 정보

_No response_

### 완료 기준

_No response_

## 분석

### 변경 전 동작

- [Connection.py](../../../src/Broker/Implements/RabbitMQ/Connection.py)의 `observe()`는 I/O 실패를 ERROR로 기록하고 예외를 다시 발생시키며, 성공은 작업 종류와 관계없이 INFO로 기록합니다. 연결·종료뿐 아니라 작업 큐 선언, Queue·Exchange·Stream 선언·삭제, 바인딩·해제에도 사용합니다.
- `connect()`는 연결 시도와 `observe()`의 성공 기록으로 정상 연결당 INFO 두 건을 남깁니다. 이미 열린 연결 재사용은 DEBUG입니다.
- [Consumer.py](../../../src/Broker/Implements/RabbitMQ/Consumer.py)는 구독 적용, 소비 루프 시작·종료·중지 요청·중지 완료, 소비 채널·RPC 응답 채널 종료를 INFO로 기록합니다.
- [Queue.py](../../../src/Broker/Implements/RabbitMQ/Queue.py), [Exchange.py](../../../src/Broker/Implements/RabbitMQ/Exchange.py), [Stream.py](../../../src/Broker/Implements/RabbitMQ/Stream.py), [Event.py](../../../src/Broker/Implements/RabbitMQ/Event.py)의 정상 메시지·RPC·정산 추적은 이미 DEBUG입니다. RPC 전용 연결 추적도 DEBUG이므로, 모든 연결 생성이 `Connection.connect()`의 INFO를 발생시킨다고 볼 수 없습니다.
- [RabbitMQ 매뉴얼](../../../docs/RabbitMQ.md)은 연결·자원 변경을 INFO로 안내합니다. 현재 INFO는 단순 오타라기보다 기존 로깅 정책을 조정할 대상입니다.
- 라이브러리는 로거 레벨·핸들러·필터를 설정하지 않습니다. 반면 [RabbitMQ 샘플](../../../samples/Broker/RabbitMQ/Sample.py)은 실행 진입점에서 루트와 콘솔을 DEBUG로 설정하므로, INFO를 DEBUG로 내려도 샘플의 전체 출력량은 그대로일 수 있습니다.

### 사용자 제공 로그 분석

사용자가 제공한 애플리케이션 INFO 로그 전체를 집계했습니다. 로그 시각 `06:58:48.860`부터 `06:58:53.112`까지 4.252초 구간에 INFO 로그 336건이 있고, 마지막 셸 프롬프트 한 줄은 로그에서 제외했습니다.

| 구분 | 건수 | 전체 로그 비중 |
| --- | ---: | ---: |
| RabbitMQ 연결 시도 `Connecting to RabbitMQ` | 73 | 21.7% |
| RabbitMQ 연결 성공 `RabbitMQ connection completed` | 72 | 21.4% |
| RabbitMQ 연결 종료 `RabbitMQ connection close completed` | 71 | 21.1% |
| RabbitMQ 합계 | 216 | 64.3% |
| 애플리케이션 로그 | 120 | 35.7% |

RabbitMQ 216건의 로거는 모두 `DefStream.Broker.Implements.RabbitMQ.Connection`입니다. 이 표본에서 Pika나 Consumer 로그가 주원인인 것은 아니며, 정상 연결의 시도·성공·종료 세 단계가 INFO로 반복되는 것이 직접적인 원인입니다. 연결 한 번을 열고 닫을 때 세 건이 발생하는 현재 코드와 메시지가 일치합니다.

앞선 분석은 연결 성공·종료를 INFO에 남기는 방향을 제안했지만, 실제 표본에서는 이 두 종류만 143건입니다. 시도만 DEBUG로 내려도 RabbitMQ INFO가 143건 남으므로 충분한 해결이 아닙니다. 정상 연결의 세 종류를 모두 DEBUG로 내리는 쪽으로 제안을 정정합니다.

이는 첨부 구간의 로그 레벨 문제에 대한 판단입니다. 실제 애플리케이션의 연결 생성 호출부나 사용 버전은 확인하지 않았으므로, 작업마다 새 연결을 만드는 정확한 이유, 재사용 가능성이나 성능 영향까지 확정하지 않습니다. 연결 재사용·풀링은 이번 로깅 변경에 섞지 않습니다.

### 레벨 조정 검토와 적용 결과

아래 표는 검토한 레벨 조정과 실제 적용 결과입니다. Consumer INFO는 제공 표본에 나타나지 않았으나, [추가 조사](./tasks/1793257826068.md) 후 사용자 요청에 따라 함께 DEBUG로 낮췄습니다. Pika 로그는 원래 많은 라이브러리 로그로 보고 다루지 않습니다.

| 로그 종류 | 변경 전 | 적용 결과 |
| --- | --- | --- |
| 정상 연결 시도·성공·종료 | INFO | DEBUG로 변경 |
| 선언·삭제·바인딩·해제 성공 | INFO | `observe()`의 공용 성공 기록과 함께 DEBUG로 변경 |
| Consumer 구독 적용·채널 종료·소비 루프 생명주기 | INFO | DEBUG로 변경 |
| 정상 메시지·RPC·정산 추적 | DEBUG | 유지 |
| 시간 초과·원격 오류·응답 라우팅 불가 | WARNING | 유지 |
| 연결·자원 작업 실패를 포함한 내부 I/O·코덱 오류 | ERROR | 유지 |

현재 표본의 문제를 해결하는 최소 변경은 `connect()`의 연결 시도와 `observe()`의 연결 성공·종료 기록을 DEBUG로 내리는 것입니다. 자원 작업의 성공도 DEBUG로 조정한다면 `observe()`의 성공 기록 자체를 DEBUG로 통일할 수 있어 연결 생명주기를 위한 별도 레벨 분기나 설정은 필요하지 않습니다. 선언·구독 등 다른 INFO는 원래 이슈의 범위에 따라 함께 검토하되 이번 표본의 직접 원인과 구분합니다. 새로운 로깅 프레임워크나 사용자 설정 API는 추가하지 않으며, 상위 로거를 WARNING으로 올려 로그 전체를 숨기는 방식을 근본 해결로 삼지 않습니다.

### 구현 전 검증·문서 영향 검토

아래 항목은 구현 전 검토 내용입니다. 실제 구현과 검증 결과는 [구현 종합](./IMPLEMENTS.md)과 [작업 종합](./TASKS.md)에 정리했습니다.

- [기존 로깅 테스트](../../../tests/test_rabbitmq_logging.py)는 로거 이름·전파·무설정 정책, 메시지 추적, 오류 레벨·전파, 민감정보 비노출과 샘플 설정을 검증합니다.
- 연결·자원 테스트는 INFO가 하나 이상 있다는 사실만 확인하므로 자원별 레벨 배정을 보장하지 않습니다. 후속 구현에서는 정상 연결·종료 시 대상 INFO가 0건이고 DEBUG에서는 시도·성공·종료 세 기록이 유지되는지, 실패 시 ERROR 기록과 예외 전파가 유지되는지 개별 검증해야 합니다. 자원 작업도 내린다면 기존 INFO 기대값을 함께 변경해야 합니다.
- INFO를 DEBUG로 바꾸면 INFO만 수집하는 운영 환경에서 해당 기록이 사라집니다. 오류·경고, 메시지 처리·정산, 공개 API와 애플리케이션의 로깅 설정은 유지해야 합니다.
- 실제 레벨을 변경할 때 [한국어 RabbitMQ 매뉴얼](../../../docs/RabbitMQ.md)과 [영어판](../../../docs/RabbitMQ.en.md)을 함께 갱신해야 합니다. 이번 분석 단계에서는 현행 동작이 바뀌지 않아 매뉴얼을 수정하지 않습니다.

## 남은 확인 사항

- 병합 대상 브랜치
- 변경 배포 후 실제 애플리케이션의 INFO 출력량. 연결 생성 호출부와 연결 재사용은 이번 범위에서 제외

## 제공 자료

- 자료: 사용자가 이 대화에 제공한 애플리케이션 INFO 로그 붙여넣기 첨부
- 수신일: 2026-10-29, 버전 미제공
- 보관·추적: 읽기 전용 대화 첨부에서 직접 집계했으며 원본을 저장소에 복사하거나 Git 추적하지 않음
- 기록 범위: 운영 주소·식별자·셸 경로를 재수록하지 않고 로그 종류별 집계만 보존
- 분석 방법과 한계: [추가 작업 기록](./tasks/1793257216492.md)

## 작업 문서

- [요구사항과 미확정 사항](./REQUIREMENTS.md)
- [진행 계획](./PLAN.md)
- [구현 종합](./IMPLEMENTS.md), [최신 구현 기록](./implements/1793257826069.md)
- [작업 종합](./TASKS.md), [최신 작업 기록](./tasks/1793257826068.md)
- [고객용 변경 로그](./CHANGELOG.md)
