# Connection 기반 타이머 작업 계획

## 기준과 현재 상태

- 범위와 공개 계약은 [요구사항](./REQUIREMENTS.md)을 따른다. 작업 브랜치·분기 기준·병합 대상은 [이슈 정보](./README.md)에 모은다.
- 현재는 계획 작성 단계이며 제품 코드·테스트·매뉴얼은 아직 변경하지 않았다. 아래 체크 항목은 수행할 작업이지 완료 결과가 아니다.
- [워커 리팩토링 #63](https://github.com/yong5eon/DefStream/issues/63)과 [Recoverable 명시적 상속 #64](https://github.com/yong5eon/DefStream/issues/64)는 별도 작업이며 이번 선행 조건이 아니다.

## 구현 방향

추가할 동작은 다음 두 경로로 한정한다.

```text
connection.set_timer(cb, seconds)
  → 현재 Pika 연결의 call_later(seconds, cb)
  → 취소 핸들을 보관하는 Timer 반환

timer.remove()
  → 등록 당시 Pika 연결의 remove_timeout(등록 핸들)
```

- 등록 시 콜백과 초 단위 지연 시간을 그대로 전달한다. 콜백을 다른 함수로 감싸거나 소비 시작까지 등록을 미루지 않는다.
- 반환 객체는 기반 연결과 등록 핸들만 보관하는 작은 구현체로 둔다. 호출자는 내부 Pika 객체나 타이머 ID를 다루지 않는다.
- 핸들은 등록 당시의 실제 연결을 참조한다. 취소 시 상위 연결 객체의 현재 연결을 다시 조회하지 않아, 재연결 후 다른 연결에 이전 핸들을 전달하지 않는다.
- `remove`는 기반 취소 API를 호출한다. 실행·취소 상태 플래그, 타이머 목록, 중복 취소 방지, 별도 입력 검증, 자동 정리 계층은 추가하지 않는다.
- 기존 `connected()`와 오류 관찰 관례를 재사용한다. 새 폴백이나 오류를 정상 반환으로 바꾸는 처리는 추가하지 않는다.
- 기존 Consumer의 확인용 타이머, `run`·`stop`·`close`, 연결 종료 처리에는 손대지 않는다.

## 변경 대상

| 대상 | 변경 내용 |
| --- | --- |
| [공통 연결 계약](../../../src/Broker/Connection.py) | `Timer`, `TimerCallback`, `SetTimer`와 `__all__` 등록 |
| [Broker 공개 진입점](../../../src/Broker/__init__.py) | 세 계약의 import와 `__all__` 재노출 |
| [RabbitMQ 연결](../../../src/Broker/Implements/RabbitMQ/Connection.py) | `SetTimer` 명시적 상속, `set_timer`, 취소 핸들 구현 |
| [프로토콜 계약 테스트](../../../tests/test_protocol_contracts.py) | 공개 타입·시그니처·데코레이터·선택적 지원 검증 |
| `tests/rabbitmq/test_rabbitmq_timers.py` 신규 | 등록·취소 위임 단위 테스트와 opt-in 실제 타이머 테스트 |
| [RabbitMQ 한국어 안내](../../../docs/RabbitMQ.md)·[영어 안내](../../../docs/RabbitMQ.en.md) | 지원 범위와 등록·취소·재등록 사용법 |
| [매뉴얼 한국어 진입점](../../../docs/README.md)·[영어 진입점](../../../docs/README.en.md) | 기존 RabbitMQ 안내 항목에 연결 타이머 주제 반영 |
| 이 이슈의 기록 문서 | 진행 상태·검증 결과·최종 변경 로그 기록 |

새 제품 소스 모듈은 만들지 않는 방향으로 진행한다. 구체 타이머는 RabbitMQ 연결 모듈 안에 `Timer` 클래스로 두고 공통 계약을 `BaseTimer`로 import하여 명시적으로 구현한다. 구체 핸들 클래스를 RabbitMQ 패키지의 새 공개 진입점으로 노출할 필요는 없다.

## 수행 순서와 완료 조건

### 1. 공통 계약과 공개 import 추가

선행 조건: 확정 요구사항 확인.

1. 공통 연결 계약 모듈에 다음 선언을 추가한다.
   - `Timer`: `@runtime_checkable`, `remove(self) -> None`에 `@abstractmethod`
   - `TimerCallback`: `__call__(self) -> None`, 추가 데코레이터 없음
   - `SetTimer`: `@runtime_checkable`, `set_timer(self, cb: TimerCallback, seconds: int) -> Timer`에 `@abstractmethod`
2. `cb`, `seconds`는 기본값 없는 위치 또는 키워드 인자로 유지한다. 위치 전용·키워드 전용 제한을 추가하지 않는다.
3. 모듈과 Broker 패키지의 `__all__`·import를 함께 갱신한다. 사용자는 `DefStream.Broker` 및 `DefStream.Broker.Connection`에서 같은 계약을 import할 수 있어야 한다.
4. 기본 `Connection`과 Consumer의 필수 메서드는 변경하지 않는다.
5. 기존 계약 테스트에 공개 경로, 타입 힌트와 시그니처, 런타임 판별, 명시적 상속 시 필수 메서드 미구현 여부를 검증하는 항목을 추가한다.

완료 조건: 요구사항 R1·R2의 선언과 공개 import가 일치하며 기존 계약은 유지된다.

### 2. RabbitMQ 등록·취소 구현

선행 조건: 1단계의 공통 계약 추가.

1. 실제 개발 환경의 Pika `call_later`·`remove_timeout` 선언과 반환 핸들 타입을 확인하고 타입 힌트에 반영한다. 반환 핸들을 임의로 정수 ID로 가정하거나 근거 없는 캐스팅으로 숨기지 않는다.
2. RabbitMQ `Connection`의 기존 상속 목록에 `SetTimer`를 추가한다.
3. `set_timer`는 기존 `connected()`로 연결을 얻고 즉시 `call_later(seconds, cb)`를 호출한다. 설정값 변환·보정·추가 검증은 하지 않는다.
4. 등록 당시 Pika 연결과 반환 핸들을 보관하는 구체 `Timer`를 반환한다.
5. 구체 `Timer.remove()`는 보관한 연결의 `remove_timeout`에 보관한 핸들을 전달한다. 중복 호출과 종료된 연결의 결과도 기반 API에 맡긴다.
6. 등록·취소의 기반 오류는 숨기지 않는다. 콜백은 그대로 전달하여 예외가 기존 Pika 이벤트 처리 경로에서 드러나게 한다.

완료 조건: 요구사항 R1~R3을 만족하며 추가 스레드·이벤트 큐·상태 관리 계층이 없다.

### 3. 직접 영향 범위 검증

선행 조건: 1·2단계 구현.

기존 `unittest`와 `unittest.mock` 관례를 사용한다. 새 검증 라이브러리는 추가하지 않는다.

#### 단위 테스트

| 항목 | 검증 방법과 기대 결과 | 요구사항 |
| --- | --- | --- |
| 공개 계약 | 두 공개 import 경로가 같은 타입을 가리키고 `__all__`에 포함되는지 확인 | R1·R2 |
| 선택적 기능 | RabbitMQ 연결은 `SetTimer`로 판별되고 기본 Connection·Consumer·Redis에는 타이머 의무가 추가되지 않았는지 확인 | R1·R4 |
| 정확한 등록 | 위치·키워드 호출 모두 `call_later(seconds, cb)`에 동일한 값과 같은 콜백 객체를 한 번 전달하는지 확인 | R2·R3 |
| 콜백 계약 | 일반 함수와 `__call__` 객체를 `TimerCallback`으로 사용할 수 있고 등록 자체가 콜백을 호출하지 않는지 확인 | R2 |
| 반환·취소 | 반환 핸들이 `Timer` 계약을 충족하고 `remove_timeout`에 기반 핸들을 그대로 전달하는지 확인 | R2·R3 |
| 연결 대응 | 상위 연결 객체의 연결 참조가 바뀌어도 기존 핸들은 등록 당시 연결에 취소를 요청하는지 확인 | R3 |
| 오류 전파 | 기반 등록·취소 API가 발생시킨 예외를 그대로 관찰할 수 있는지 확인 | R3 |
| 얇은 위임 | 중복 취소를 자체 차단하지 않고 0·음수도 기반 API에 전달하는지 확인. 기반 동작을 새 정책으로 재정의하지 않음 | R3 |

#### 실제 RabbitMQ 테스트

- 신규 타이머 테스트 모듈의 `RabbitMQTimerIntegrationTests`에 기존 `RABBITMQ_TESTS=1` opt-in 방식을 적용한다. 포트는 기존 `rabbitmq_test_port()`를 사용한다.
- 연결·소비·타이머 등록은 같은 소유 스레드에서 수행한다. 다른 스레드의 안전성을 검증한다는 명목으로 제품에 동기화 기능을 추가하지 않는다.
- 테스트 전용 이름의 빈 큐를 구독하여 메시지 없는 소비 대기 중 콜백 실행과 소유 스레드 일치를 확인한다.
- 개별 취소 후 미실행, 콜백 재등록에 의한 반복 실행, 콜백 예외가 `consumer.run()` 호출자에게 전달되는 동작을 확인한다.
- 테스트에 유한 실행 제한을 두고, 테스트가 만든 큐·채널·연결은 테스트의 정리 코드에서 정리한다. 이를 제품의 자동 정리 요구로 옮기지 않는다.
- 실제 서버를 사용할 수 없으면 단위 테스트로 유휴 실행까지 검증했다고 쓰지 않고 통합 검증 미실행으로 기록한다.

완료 조건: 아래 명령과 진단 결과를 실제 수행 기록에 남긴다. 실패가 이번 변경에서 발생했으면 수정하고 관련 없는 기존 실패는 근거와 함께 구분한다.

### 4. 한국어·영어 사용 안내

선행 조건: 3단계에서 공개 동작 확인.

1. 두 RabbitMQ 매뉴얼에 같은 범위의 연결 타이머 절을 추가한다.
2. `isinstance(connection, SetTimer)`로 지원 여부를 확인하고 연결 후 `set_timer`로 등록하는 방법을 안내한다.
3. 빈 큐 소비 중 실행되는 일회성 콜백과 콜백 안의 재등록, `Timer.remove()`를 설명한다. 기존 Consumer API를 그대로 사용하며 제품에 새로운 실행 API를 만들지 않는다.
4. 초 단위·등록 시점 기준·Pika 이벤트 처리 필요·소유 스레드 제약·실행 지연 가능성·호출자의 취소 책임을 명시한다.
5. 예제는 필요한 import·연결·구독·실행·테스트 자원 정리까지 확인 가능하게 작성한다. 종료된 연결의 핸들을 무조건 안전하게 취소할 수 있다고 보장하지 않는다.
6. 두 매뉴얼 진입점의 기존 RabbitMQ 항목에 타이머 주제를 반영한다. 별도 타이머 매뉴얼이나 다이어그램은 단순 등록·취소 설명에 필요하지 않으면 만들지 않는다.
7. 루트 README 요약에 타이머 안내가 필요한지만 확인한다. 필요할 때에만 한국어·영어 요약을 함께 갱신하며, 상세 사용법은 매뉴얼에 둔다.

완료 조건: 요구사항 R5와 실제 구현이 일치하며 미지원 브로커나 추가 스레드 안전성을 보장하는 표현이 없다.

### 5. 결과 정리와 범위 확인

선행 조건: 3·4단계 완료.

1. 변경 파일 목록을 확인하여 Consumer·Worker·Ping·Pool·Executor·Event·Redis 구현이 섞이지 않았는지 확인한다. #63·#64의 작업은 하지 않는다.
2. 구현 단계는 `implements/`, 검증 등 구현 외 작업은 `tasks/`에 실제 수행 시점의 기록을 남긴다.
3. 구현 결과를 `IMPLEMENTS.md`, 작업 결과를 `TASKS.md`에 종합한다. 이 단계에서 아직 없는 구현 문서를 빈 파일로 미리 만들지 않는다.
4. 실제 제공된 타이머 등록·취소 기능과 사용 제약만 이슈의 `CHANGELOG.md`에 작성한다. 내부 계획·문서 작성·테스트 통과를 고객 기능으로 나열하지 않는다.
5. README와 이 계획의 진행 상태를 갱신한다. 필요한 검증이 남았다면 전체 구현 완료로 표시하지 않는다.

## 검증 명령과 환경

명령은 저장소 루트에서 개발 환경에 선택된 `python`으로 실행한다. 아래 신규 테스트 모듈·클래스는 구현 단계에서 추가할 대상이며 현재 존재하는 것으로 간주하지 않는다.

### 먼저 실행할 단위·회귀 검증

실제 RabbitMQ opt-in 환경변수가 꺼진 상태에서 다음 모듈을 한 번의 실행으로 검사한다.

```shell
python -m unittest tests.test_protocol_contracts tests.rabbitmq.test_rabbitmq_timers tests.rabbitmq.test_rabbitmq_broker_methods tests.rabbitmq.test_rabbitmq_logging tests.rabbitmq.test_rabbitmq_timeouts -v
```

- 등록·취소 단위 테스트와 공통 계약, 기존 연결 API·로깅·시간 설정 검증을 포함한다.
- 변경 Python 파일의 구문·타입 진단을 확인한다. 새로운 타입 검사 도구를 설치하거나 저장소 전체의 기존 진단을 정리하지 않는다.
- 이 범위의 결과에서 더 넓은 영향이 확인될 때만 관련 검증으로 확대한다. 전체 Worker·프로세스 테스트를 이번 선행 조건으로 삼지 않는다.
- 설치된 코드가 현재 소스를 가리키는지 먼저 확인한다. 의존성·선택 구현체가 없어서 검증이 실패할 때에만 [기존 개발용 설치 절차](../../../docs/Packaging.md)를 따른다. 이 경우 공통 계약 테스트가 RabbitMQ·Redis를 모두 import한다는 점을 고려하고 기존 선택을 임의로 축소하지 않는다.

### 실제 RabbitMQ 검증

테스트 사용이 허용된 서버에만 접속한다. 기존 `RABBITMQ_PORT` 설정을 이용하며, 테스트를 위해 운영 서버에 큐를 생성하거나 별도 서버를 자동 설치하지 않는다.

다음은 PowerShell에서 opt-in하는 실행 예시이다. 환경변수는 해당 검증 프로세스에서만 설정한다.

```powershell
$env:RABBITMQ_TESTS = '1'
python -m unittest tests.rabbitmq.test_rabbitmq_timers.RabbitMQTimerIntegrationTests -v
```

### 문서·변경 범위 검증

- 한국어·영어 예제와 공개 import·시그니처를 대조하고 상대 링크·코드 펜스를 검사한다.
- 이슈 문서에는 로컬 절대 경로를 남기지 않는다.
- `git diff --check`와 변경 파일 목록을 확인한다. 현재 단계에서는 계획 문서만 검증하고 제품 테스트 결과와 구분한다.

## 진행 상태

- [x] 확정 요구사항과 현재 구현·공개 경로·기존 테스트·문서 위치 확인
- [x] 범위에 맞는 구현·검증 계획 작성
- [ ] 공통 계약·공개 import와 계약 테스트 추가
- [ ] RabbitMQ 등록·취소와 단위 테스트 구현
- [ ] 단위·회귀·실제 RabbitMQ 검증
- [ ] 한국어·영어 매뉴얼 갱신
- [ ] 종합 결과·고객 변경 로그 작성 및 최종 범위 확인
