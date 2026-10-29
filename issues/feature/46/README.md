# RabbitMQ Consumer 소비 채널 종료 시 최대 횟수 내 복구와 한도 초과 시 프로세스 종료

## 이슈와 작업 상태

- 원본: GitHub Issues [#46](https://github.com/yong5eon/DefStream/issues/46)
- 제목: RabbitMQ Consumer 소비 채널 종료 시 최대 횟수 내 복구와 한도 초과 시 프로세스 종료
- 상태: Open
- 유형·레이블: 기능 (`feature`), `rabbitmq` (원본에 적용됨)
- 작업 대상: `yong5eon/DefStream`, 작업 브랜치 `feature/46`
- 분기 기준: 깨끗한 로컬 `master`의 `85174f0`
- 병합 대상: `master`
- 로컬 진행 상태: 구현·매뉴얼·기능 회귀 완료, 패키징 환경 검사 실패 및 실제 브로커 검증 미실행
- 댓글: 없음

## 관련 이슈

- [#47 Subscription 작업별 consumer timeout 지원](https://github.com/yong5eon/DefStream/issues/47): ACK timeout 자체를 다루는 별도 이슈

## 작업 문서

- [요구사항 명세](./REQUIREMENTS.md)
- [작업 계획](./PLAN.md)
- [구현 종합](./IMPLEMENTS.md)
- [작업 종합](./TASKS.md)
- [변경 로그](./CHANGELOG.md)
- [최신 구현 기록](./implements/1793276075771.md)
- [최신 작업 기록](./tasks/1793276099601.md)

## 이슈 원문

### 해결하려는 문제

- RabbitMQ `Consumer`의 소비 채널이 브로커에 의해 닫히면 소비가 그대로 끝나고 다시 시작되지 않음
- `Worker`는 모든 `Run`을 하나의 `Consumer`와 소비 채널로 구독하므로, 한 큐의 문제로 채널이 닫혀도 **모든 큐의 소비가 중단**됨
- 소비가 끝난 뒤 `finally`의 `Pool.stop()`이 `Executor.shutdown(wait=True)`로 실행 중인 작업을 기한 없이 기다리므로, 프로세스는 종료되지 않고 소비만 멈춘 상태로 남음
- 그 사이 완료된 작업은 정산할 수 없어 `Cannot confirm delivery after Consumer exit` 로그만 반복됨

실제 발생 사례(RabbitMQ 3.13.7)

1. 장시간 작업이 전역 `consumer_timeout`(3시간)을 넘김
2. 브로커가 `PRECONDITION_FAILED - delivery acknowledgement on channel 1 timed out`으로 채널 종료
3. 해당 채널의 모든 미확인 메시지는 브로커가 Ready로 재큐잉
   - 작업 예외가 아니라서 `on_error=Reject()` 등 오류 정책이 적용되지 않음
4. 이후 `nack failed ... ChannelClosedByBroker` → `Consumption loop ended` → `Consumer exited with unconfirmed deliveries`
5. 프로세스는 살아 있으나 모든 소비가 중단되고 헬스 체크는 계속 503 반환

### 제안하는 해결 방법

- 복구 가능한 브로커·연결 계층 예외로 소비가 끝나면 지정한 최대 횟수 안에서 소비를 복구
  - 대상 예: `ChannelClosedByBroker`, `ConnectionClosedByBroker`, `StreamLostError`
  - `stop()` 호출에 의한 정상 종료와 구분
  - 복구 순서는 연결·채널 재생성 → `basic_qos` → 기존 구독 재등록
- 최대 횟수를 넘거나 복구할 수 없는 예외이면 소비 실패를 전파하여 프로세스가 자연스럽게 종료되도록 처리
  - 종료 시 실행 중인 작업의 대기 시간에 상한 필요
  - 닫힌 채널의 delivery는 어차피 정산할 수 없으므로 기한 없이 기다리지 않음
- 이전 채널의 delivery tag는 새 채널에서 정산하지 않고 폐기
  - 새 채널에 이전 tag로 `ack`·`nack`하면 `PRECONDITION_FAILED - unknown delivery tag`로 새 채널도 닫힘
  - 채널 세대를 구분하여 이전 세대의 완료·실패 정산은 경고 로그 후 무시
- ACK timeout(`PRECONDITION_FAILED` + `acknowledgement ... timed out`)으로 닫힌 경우는 일반 연결 끊김과 구분하여 경고
  - 해당 작업이 timeout을 넘겼다는 사실과 큐를 로그로 확인할 수 있어야 함
- 채널 종료 감지는 정산 시점의 예외에 의존하지 않음
  - 실측 결과 `process_data_events()` 대기 중에는 브로커가 채널을 닫아도 예외가 발생하지 않아 종료를 놓칠 수 있음
  - `on_close` 콜백 또는 `channel.is_closed` 확인 필요

### 고려한 대안

- 컨테이너 재시작 정책만으로 복구
  - 현재는 프로세스가 종료되지 않아 재시작 정책이 동작하지 않음
  - 복구 한도를 넘었을 때 프로세스를 종료시키는 부분은 이 방식과 함께 사용 가능
- ACK timeout 자체를 피하는 방법은 작업별 consumer timeout 지원 이슈에서 별도로 다룸

### 추가 정보

- 복구 후 같은 메시지가 재전달되면 이전 작업 스레드가 아직 실행 중이어서 중복 실행될 수 있음. 메시지 처리의 멱등성은 사용하는 쪽에서 보장해야 함
- 참고: [RabbitMQ Consumers - Delivery Acknowledgement Timeout](https://www.rabbitmq.com/docs/consumers#acknowledgement-timeout)
