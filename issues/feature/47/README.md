# Subscription 작업별 consumer timeout 지원

## 이슈와 작업 상태

- 원본: GitHub Issues [#47](https://github.com/yong5eon/DefStream/issues/47)
- 제목: Subscription 작업별 consumer timeout 지원
- 상태: Open
- 유형·레이블: 기능 (`feature`), `rabbitmq` (원본에 적용됨)
- 담당자: `yong5eon`
- 작업 대상: `yong5eon/DefStream`, 작업 브랜치 `feature/47`
- 분기 기준: 깨끗한 로컬 `master`의 `15ffbdc`
- 병합 대상: `master`
- 로컬 진행 상태: 요구사항 명세 및 작업 범위 정리, 추가 사용자 결정 사항 없음, 구현 전
- 댓글: 없음

## 작업 문서

- [요구사항 명세](./REQUIREMENTS.md)
- [작업 종합](./TASKS.md)
- [최신 작업 기록](./tasks/1793271384432.md)

## 이슈 원문

### 해결하려는 문제

- RabbitMQ는 소비자가 전달받은 메시지를 `consumer_timeout`(기본 30분) 안에 ACK하지 않으면 채널을 `PRECONDITION_FAILED`로 닫고 미확인 메시지를 재큐잉함
- 작업 완료 후 ACK하는 구조에서는 수 시간 이상 걸리는 작업이 이 한도를 넘기면 정상 실행 중인데도 채널이 닫힘
- 브로커 전역 `consumer_timeout`을 늘리면 짧은 작업의 멈춤 감지까지 함께 늦어지므로, 장시간 작업의 큐에만 한도를 늘릴 방법이 필요함
- 현재 `Subscription`에는 큐별 consumer timeout을 지정할 수단이 없음

### 제안하는 해결 방법

- `Subscription`에 작업별 timeout을 지정할 수 있도록 지원
- RabbitMQ 구현에서는 큐 선언 시 이 값을 `x-consumer-timeout`(ms) 큐 인자로 전달
  - `Subscription.error` → `x-dead-letter-*`, `max_priority` → `x-max-priority`를 구성하는 `queue_declare` 인자 처리와 같은 위치
- 지정하지 않으면 기존과 동일하게 브로커 전역 설정을 따름

```python
Subscription(queue='etl.split', error='etl.split.error', timeout=timedelta(hours=24))
```

> 위 예시의 `timeout` 이름과 타입은 제안이며 구현 시 확정

### 고려한 대안

- 메시지를 받자마자 ACK하는 정책(이전의 `AckPolicy.BEFORE_RUN`)
  - at-most-once가 되어 작업 실패나 프로세스 종료 시 메시지가 유실됨
  - 오류 시 오류 큐로 보내는 정책(`Reject`)·dead-letter와 prefetch에 의한 동시 처리 제한 계약이 깨짐
- 브로커 전역 `consumer_timeout` 상향: 모든 큐의 멈춤 감지가 늦어짐
- 소비 시점(`basic.consume`)에 지정하는 timeout: RabbitMQ가 지원하지 않음
  - 지원 방식은 전역 설정, 큐 인자 `x-consumer-timeout`, policy `consumer-timeout`뿐임
- AMQP 0-9-1에는 처리 중인 메시지의 ACK 기한을 연장하는 기능이 없음

### 추가 정보

RabbitMQ 3.13.7 실측 결과(전역 `consumer_timeout=60000`, ACK하지 않고 메시지 보유)

| 큐 설정 | 채널 종료까지 | 브로커 로그의 `Timeout value used` |
|---|---|---|
| 없음 | 120초 | 60000 ms |
| 큐 인자 `x-consumer-timeout=240000` | 240초 | 240000 ms |
| policy `consumer-timeout=240000` | 240초 | 240000 ms |

- 전역보다 큰 큐 인자·policy 값도 적용됨
- 만료 검사는 약 1분 간격이므로 실제 종료는 설정값보다 최대 약 1분 늦을 수 있음
- 이미 존재하는 큐를 다른 `x-consumer-timeout` 값으로 재선언하면 오류 없이 성공하지만 값은 변경되지 않음
  - 기존 큐는 삭제 후 재생성하거나 policy로 적용해야 함
- 참고: [RabbitMQ Consumers - Delivery Acknowledgement Timeout](https://www.rabbitmq.com/docs/consumers#acknowledgement-timeout)
