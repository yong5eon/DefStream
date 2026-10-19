# 워커 브로커 연결 타입 단순화 요구사항 명세서

## 1. 목적

사용자가 워커 전용 연결 타입을 알아야 하는 부담을 없앤다.
`Worker`는 공통 브로커의 `Connection`을 받고, 컨슈머 생성 기능의 지원 여부는
워커 내부에서 확인한다.

대상 브랜치는 `fix/3`이며, 구현 내용과 검증 결과는
[구현 기록](./IMPLEMENTS.md), 변경 요약은 [변경 로그](./README.md)에 기록한다.

## 2. 변경 전과 변경 후

| 구분 | 변경 전 | 변경 후 |
|---|---|---|
| 생성자 입력 타입 | 워커 전용 `WorkerConnection` | 공통 `DefStream.Broker.Connection` |
| 컨슈머 생성 계약 | `WorkerConnection`에서 두 Protocol 합성 | 독립적인 `GetConsumer` 유지 |
| 기능 지원 검사 | 워커의 명시적인 런타임 검사 없음 | 컨슈머 생성 직전 `isinstance` 검사 |
| 미지원 연결 | 컨슈머 호출 단계에서 기능 부재 오류 | 원인을 설명하는 `TypeError` |

## 3. 기능 요구사항

| ID | 요구사항 |
|---|---|
| WCON-01 | `Worker.__init__`의 `broker` 타입은 공통 `Connection`이어야 한다. |
| WCON-02 | `WorkerConnection` 정의와 공개 export를 제거한다. 같은 목적의 워커 전용 합성 타입을 새로 추가하지 않는다. |
| WCON-03 | `Connection`은 `connect()`와 `close()`만 요구하며, `GetConsumer` 상속을 강제하지 않는다. |
| WCON-04 | `GetConsumer`를 런타임 검사 가능한 Protocol로 제공한다. 명시적 상속 없이 필요한 기능을 구현한 객체도 지원한다. |
| WCON-05 | 워커는 연결 및 setup 완료 후, 컨슈머 생성 직전에 `isinstance(self.broker, GetConsumer)`를 검사한다. 호출자에게 별도 검사나 타입 변환을 요구하지 않는다. |
| WCON-06 | 미지원 연결은 `TypeError('Worker broker must support consumer creation')`로 실패한다. 실패를 무시하거나 대체 컨슈머를 생성하지 않는다. |
| WCON-07 | 검사 실패도 기존 종료 경로를 거쳐 실행 풀 종료, cleanup, 연결 종료와 실행 완료 상태 처리를 수행한다. |
| WCON-08 | 기존 RabbitMQ·Redis 브로커, 작업 등록, 메시지 처리, ACK/NACK, 실패 정책, RPC와 실행 풀 동작을 유지한다. |

## 4. 범위와 제한

- 변경 대상은 코어의 연결 계약, 워커, 직접 관련된 테스트와 문서이다.
- RabbitMQ·Redis 어댑터는 아래 추가 요구사항에 따라 작업 발행 이름을 함께 변경한다.
- 사용자 정의 연결에 `GetConsumer`의 명시적 상속을 강제하지 않는다.
- 런타임 Protocol 검사는 기능의 구조적 지원 여부를 확인한다.
  메서드 매개변수·반환 타입이나 실제 실행 성공까지 검증하는 기능은 아니다.
- 브랜치 생성, 커밋, 배포, 버전 번호 변경은 본 작업에 포함하지 않는다.

## 5. 인수 기준

| ID | 검증 시나리오 |
|---|---|
| WCAT-01 | 생성자 타입 힌트가 공통 `Connection`이며 공개 export에 `WorkerConnection`이 없다. |
| WCAT-02 | 명시적 Protocol 상속이 없는 구조적 연결과 RabbitMQ·Redis 연결을 워커에 그대로 전달할 수 있다. |
| WCAT-03 | `connect()`·`close()`만 구현한 연결은 인스턴스화할 수 있지만, 작업을 등록하고 워커를 실행하면 명시적인 `TypeError`로 실패한다. 실행 풀은 종료되고 완료 상태가 설정된다. |
| WCAT-04 | 기존 워커 수명 주기, setup·cleanup, 스레드·프로세스 실행 테스트가 통과한다. |
| WCAT-05 | Docker의 `defstream-rabbitmq`를 사용하여 실제 소비·재전달·거부·종료, RPC, Inspector 연동을 검증한다. RabbitMQ 테스트를 건너뛴 결과를 실서버 검증으로 간주하지 않는다. |
| WCAT-06 | 설치된 과거 패키지가 아니라 현재 브랜치의 코어 소스와 로컬 RabbitMQ 어댑터를 로드해 검증한다. |

## 6. 연결 기능 검사와 작업 발행 이름 추가 요구사항

- `GetExchange`, `GetQueue`, `GetStream`에도 `@runtime_checkable`을 적용한다.
- `TaskSender`는 `Emittable`로, 작업 발행 메서드와 워커 도우미 `send`는
  `emit`으로 변경한다. 기존 이름의 호환 별칭은 추가하지 않는다.
- `declare`, `emit`, `request`는 모두 `broker: Connection`을 받고 내부에서
  각각 `Declarable`, `Emittable`, `Requestable`을 검사한다.
- 미지원 기능은 기존 방식의 `NotImplementedError`로 명시적으로 실패한다.
  RPC 검사는 우선순위 유무와 무관하게 수행한다.
- 우선순위 기능 계약과 RabbitMQ·Redis 구현체의 작업 발행 이름도 `emit`으로 맞춘다.
- 큐·Exchange·Stream의 저수준 `Sendable.send()`와 `Callable.call()`은 유지한다.
- Inspector Console의 브로커 팩터리도 공통 `Connection`을 반환하도록 단순화한다.
  기존 HTTP `mode="send"`와 화면 동작은 유지하고 내부 호출만 `emit`으로 바꾼다.
- 테스트, 예제, 한영 사용 설명서 및 각 프로젝트 현재 브랜치 문서를 갱신한다.
- 생성자와 도우미 타입 힌트, 기능별 성공·실패, 우선순위, 실제 RabbitMQ 연동과
  Redis 회귀 테스트로 검증한다.

## 7. 브로커 팩터리 계약

- 공통 브로커에 `BrokerFactory` Protocol을 공개하며 `__call__(self) -> Connection`을 정의한다.
- Console의 `broker` 입력 타입은 `Callable[[], Connection]` 대신 `BrokerFactory`를 사용한다.
- 기존 함수·람다와 호출 가능한 클래스도 구조적으로 사용할 수 있어야 한다.
  명시적 상속이나 어댑터를 호출자에게 강제하지 않는다.
- 호출마다 독립적인 새 연결을 반환하는 계약을 문서화한다.
  Console의 기존 호출 가능 여부 검사와 연결 생성·종료 동작은 유지한다.
