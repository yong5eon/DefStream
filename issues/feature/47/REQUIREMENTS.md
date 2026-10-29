# Subscription consumer timeout 지원 요구사항

## 목적

장시간 작업이 정상 실행 중인데도 RabbitMQ의 ACK 대기 한도를 초과하여 채널이 종료되는 문제를 줄이기 위해, 작업 구독 설정에서 해당 큐의 consumer timeout을 지정할 수 있도록 합니다. 브로커 전역 설정이나 작업 완료 후 ACK하는 계약은 변경하지 않습니다.

이슈 원문과 작업 브랜치·병합 대상은 [이슈 기록](./README.md)을 기준으로 합니다. 이 문서는 구현 전 요구사항이며, 아직 기능이 제공된다는 뜻이 아닙니다.

## 분석과 근거

### 이슈에서 요청한 결과

- RabbitMQ `Subscription`에서 ACK 대기 한도를 선택적으로 지정합니다.
- 큐 선언 시 `x-consumer-timeout` 큐 인자로 밀리초 값을 전달합니다.
- 미지정 시 기존처럼 애플리케이션이 한도를 재정의하지 않습니다.
- 수신 직후 ACK하는 우회 방법 대신, 완료 후 ACK·실패 정책·prefetch 계약을 유지합니다.

이슈 예시의 `timeout` 이름과 `timedelta` 타입은 원문에서는 제안입니다. 사용자의 후속 확인에 따라 이번 범위는 `Subscription`의 timeout 설정을 `declare()`에 전달하는 기능으로 한정합니다. API의 세부 구현은 별도의 사용자 결정 사항이나 작업 차단 사유로 두지 않습니다.

### 현재 코드와 차이

- [RabbitMQ Subscription](../../../src/Broker/Implements/RabbitMQ/Subscription.py)은 큐, offset, QoS, 오류 큐 및 우선순위를 표현하고 객체와 Mapping 입력을 지원하지만, consumer timeout 필드는 없습니다.
- [RabbitMQ Connection](../../../src/Broker/Implements/RabbitMQ/Connection.py)의 `declare()`가 작업 큐의 dead-letter 및 최대 우선순위 인자를 구성합니다. 이 경로에서 새 큐 인자를 함께 전달하면 요청을 충족할 수 있습니다.
- [Worker declare](../../../src/Worker/Message.py)는 작업의 구독 설정을 브로커에 전달합니다. 공통 Worker API에 새 timeout 매개변수를 추가할 필요는 없습니다.
- [RabbitMQ Consumer](../../../src/Broker/Implements/RabbitMQ/Consumer.py)의 `subs()`는 큐를 선언하지 않고 구독하며, `complete()`는 성공 처리 후 ACK합니다. 두 계약은 유지해야 합니다.
- [Worker](../../../src/Worker/Worker.py)는 한 Consumer로 여러 작업을 구독하므로 RabbitMQ 소비 채널을 공유합니다. 큐별 timeout을 설정해도 다른 구독의 timeout으로 같은 채널이 종료될 가능성까지 제거하지는 않습니다.

### 외부 제약과 근거의 범위

- [RabbitMQ 3.13 공식 문서](https://www.rabbitmq.com/docs/3.13/consumers#acknowledgement-timeout)에 따르면 큐별 설정은 RabbitMQ 3.12부터 지원하며, 큐 인자 단위는 밀리초입니다. 만료 여부는 약 1분 간격으로 검사합니다.
- 같은 문서는 1분 미만을 지원하지 않고 5분 미만은 권장하지 않는다고 설명합니다. 이는 브로커의 운영 제약이며, 이를 이유로 운영 설정 확인이나 별도의 사용자 승인을 이번 작업의 선행 조건으로 추가하지 않습니다.
- 기존 큐를 다른 값으로 재선언해도 값이 바뀌지 않았다는 내용은 이슈 작성자의 RabbitMQ 3.13.7 실측 보고입니다. 이번 분석에서 직접 재현한 결과나 모든 버전·큐 유형에 대한 보장은 아닙니다.
- 미지정 시 브로커가 적용하는 전역 설정이나 기존 policy를 따릅니다. 라이브러리가 브로커 기본값을 중복 설정하지 않습니다.

## 확정 요구사항

### 포함 범위

| ID | 요구사항 |
| --- | --- |
| R-01 | RabbitMQ `Subscription`에서 큐별 consumer timeout을 선택적으로 지정할 수 있어야 합니다. 기존 객체 입력과 Mapping 입력 양쪽에서 사용할 수 있어야 합니다. |
| R-02 | 명시된 값은 기존 작업 큐 선언 경로에서 정수 밀리초의 `x-consumer-timeout` 인자로 전달해야 합니다. |
| R-03 | 생략 또는 `None`이면 `x-consumer-timeout` 인자를 보내지 않아야 합니다. 브로커 기본값을 라이브러리에서 고정하거나 timeout 비활성화로 해석하지 않아야 합니다. |
| R-04 | 오류 큐와 우선순위를 함께 지정해도 기존 `x-dead-letter-*`, `x-max-priority` 및 durable 선언을 유지해야 합니다. 작업 구독에 설정한 timeout을 부수적으로 선언하는 오류 큐에 전파하지 않아야 합니다. |
| R-05 | 잘못된 타입이나 정수 밀리초로 표현할 수 없는 값을 브로커 I/O 전에 명시적인 오류로 거부해야 합니다. 기본값 대체, 조용한 무시 또는 브로커 전역 설정으로의 폴백을 하지 않아야 합니다. 필요한 입력 검증과 변환 기준은 기존 관례에 맞춰 구현하고 테스트로 명시하며, 별도의 운영 요구사항을 추가하지 않습니다. |
| R-06 | `Subscription` 생성과 `Consumer.subs()`는 큐를 자동 선언하지 않아야 합니다. timeout 적용도 기존 명시적 `declare()` 경로를 사용해야 합니다. |
| R-07 | 완료 후 ACK, 오류 시 `Requeue`·`Reject`, dead-letter, QoS·prefetch 및 RPC의 기존 처리 계약을 유지해야 합니다. 이 값으로 작업을 강제 중단하거나 RPC 응답 대기시간을 변경하지 않아야 합니다. |
| R-08 | 기존 `Subscription` 호출의 위치 인자 순서와 미지정 시 동작을 유지해야 합니다. 공통 Worker 및 Redis API에 timeout 지원을 추가하지 않아야 합니다. |
| R-09 | 기존 큐를 자동 삭제·재생성하거나 policy·브로커 설정을 변경하지 않아야 합니다. 큐 선언에서 발생한 오류는 기존 로깅·예외 전파 계약에 따라 드러내야 합니다. |
| R-10 | 구현 시 한국어·영어 RabbitMQ 매뉴얼에 설정 방법, 명시적 선언 필요성 및 미지정 동작을 반영해야 합니다. 기존 큐 변경은 운영 측 책임임을 간결히 알리고 운영 절차를 이번 작업에서 작성하거나 수행하지 않습니다. |

### 운영상 의미와 제한

- 설정 대상은 개별 메시지나 작업 실행 인스턴스가 아니라 작업이 소비하는 큐입니다. 같은 큐의 소비자마다 서로 다른 한도를 제공하는 기능은 아닙니다.
- consumer timeout은 브로커가 메시지를 전달한 뒤 ACK를 기다리는 한도입니다. 작업 코드의 실행 시간 제한, 메시지 TTL, 연결 timeout, RPC 응답 대기시간과 구분해야 합니다.
- 실제 채널 종료 시점이 설정값과 정확히 일치한다고 보장하지 않습니다.
- 다른 큐의 미확인 메시지로 공유 채널이 종료될 수 있습니다. 큐별 설정만으로 작업 간 장애 격리를 보장하지 않습니다.
- 기존 큐의 설정 변경·반영 여부 확인·재생성·policy 적용은 운영 측 책임이며, 이번 구현이나 완료 검증의 대상이 아닙니다.
- 새 설정을 사용하는 환경에는 큐별 timeout을 지원하는 RabbitMQ가 필요합니다. 구버전에서 동일한 효과를 보장하거나 전역 설정 변경으로 대신 처리하지 않습니다.

### 제외 범위

- 조기 ACK 및 `AckPolicy.BEFORE_RUN` 재도입
- 실행 중 메시지의 ACK 기한 연장, 재시도·중복 제거 기능 추가
- Worker의 채널·연결 분리 및 실행 풀·동시성 구조 변경
- Redis용 timeout, 공통 timeout 추상화, 별도 capability 인터페이스 추가
- 저수준 큐 생성·Stream·Exchange API로 설정 범위 확대
- RabbitMQ policy 관리, 기존 큐 마이그레이션 자동화 및 운영 데이터 변경

## 구현 판단과 사용자 확인 사항

- 추가로 사용자에게 확정을 요청할 사항은 없습니다.
- 공개 필드는 이슈 예시의 `timeout`, 타입은 `Optional[timedelta]`, 기본값은 `None`을 구현 기준으로 사용합니다. 앞선 분석의 `consumer_timeout`은 권장안이었으며 필수 요구가 아닙니다.
- 정수 밀리초 변환과 필요한 입력 검증은 구현 세부사항으로 처리하고 실제 구현·테스트와 문서에 동일하게 반영합니다. 별도의 설정 옵션이나 호환성 계층을 추가하지 않습니다.
- 기존 큐의 변경이나 실제 운영 환경의 timeout 적용 상태를 조사하지 않습니다.

## 인수 기준

아래 기준은 구현 후 검증할 목표이며, 현재 통과했다는 의미가 아닙니다.

| ID | 관련 요구사항 | 검증 기준 |
| --- | --- | --- |
| AC-01 | R-01, R-02 | 최종 API의 객체·Mapping 입력 모두에서 24시간 설정이 작업 큐 선언의 정수 `86400000` 밀리초로 전달됩니다. |
| AC-02 | R-03, R-08 | 생략 및 명시적 `None`일 때 `x-consumer-timeout`이 없고, 기존 위치 인자와 선언 옵션이 유지됩니다. |
| AC-03 | R-04 | timeout·오류 큐·최대 우선순위를 함께 설정하면 작업 큐 인자에 모두 반영되고, 오류 큐에는 해당 timeout을 전달하지 않습니다. |
| AC-04 | R-05 | 확정한 타입·범위·정밀도 기준의 정상값과 경계값을 검증하고, 잘못된 값에서는 브로커 I/O 없이 오류가 발생합니다. |
| AC-05 | R-06 | 구독 객체 생성과 소비자 등록에서 큐 선언이 발생하지 않고, `basic.consume`에 timeout 큐 인자를 잘못 전달하지 않습니다. |
| AC-06 | R-07 | 기존 성공 후 ACK, 실패 정책, prefetch 및 RPC 관련 회귀 테스트가 유지됩니다. RPC 호출 timeout은 별도 값으로 계속 동작합니다. |
| AC-07 | R-09 | 큐 선언 오류가 전파되며 큐 자동 삭제·재생성 및 policy 변경을 하지 않습니다. |
| AC-08 | R-10 | 한국어·영어 매뉴얼이 구현된 API와 동일한 예시·단위·선언 방법을 설명하고, 기존 큐 변경이 운영 측 책임임을 명시합니다. |

이번 기능의 완료 검증은 기존 Mock 기반 선언 테스트를 이용해 `x-consumer-timeout`의 정확한 전달·생략과 기존 선언 인자·구독 계약의 유지를 확인하는 데 집중합니다. 실제 ACK 만료 대기, 기존 큐의 재선언·변경 실측 및 운영 환경 검증은 수행 범위에 포함하지 않습니다. Mock 검증이나 원문의 실측 보고를 이번 변경의 실제 브로커 검증 결과로 표현하지 않습니다.

## 관련 검증·문서

- 구독 설정·소비 계약: [test_rabbitmq_worker.py](../../../tests/test_rabbitmq_worker.py)
- 큐 선언 인자·오류 전파: [test_rabbitmq_priorities.py](../../../tests/test_rabbitmq_priorities.py)
- 작업 선언 경로: [test_task_messages.py](../../../tests/test_task_messages.py)
- 실제 브로커 연동: [test_rabbitmq_integration.py](../../../tests/test_rabbitmq_integration.py)
- 사용자 안내: [RabbitMQ.md](../../../docs/RabbitMQ.md), [RabbitMQ.en.md](../../../docs/RabbitMQ.en.md)
