# 워커 브로커 연결 타입 단순화 구현 기록

## 1. 구현 개요

[요구사항 명세서](./REQUIREMENTS.md)에 따라 워커 전용 합성 Protocol을 제거하고,
공통 연결 타입과 내부 기능 검사를 사용하도록 변경했다.
대상 브랜치는 `fix/3`이다.

## 2. 구현 내용

### 공통 브로커 계약

- [Connection.py](../../../src/Broker/Connection.py)의 `Connection`은 기존처럼
  `connect()`와 `close()`만 요구한다.
- `GetConsumer`에 `@runtime_checkable`을 추가했다.
- 두 계약은 독립적으로 유지한다. 컨슈머가 없는 발행 전용 연결도 공통
  `Connection`을 구현할 수 있다.

### 워커와 공개 API

- [Worker.py](../../../src/Worker/Worker.py)의 생성자 입력을
  `broker: Connection`으로 변경했다.
- `WorkerConnection` 클래스와 불필요한 `Protocol` import를 제거했다.
- [공개 export](../../../src/Worker/__init__.py)에서도 `WorkerConnection`을 제거했다.
- `run()`에서 기존 순서대로 브로커 연결 및 setup을 실행한 다음,
  `consumer()` 호출 직전에 `isinstance(self.broker, GetConsumer)`를 검사한다.
- 미지원이면 `TypeError('Worker broker must support consumer creation')`를
  발생시킨다. 검사는 기존 `try/finally` 안에 있어 실패해도 종료 처리를 유지한다.
- 작업 실행, ACK/NACK, 실패 정책, RPC, Inspector와 실행 풀 로직은 변경하지 않았다.

### 테스트와 사용자 문서

- [계약 테스트](../../../tests/test_protocol_contracts.py)에서 생성자 타입,
  공개 export 제거, 구조적 연결 및 두 어댑터의 수용, 미지원 연결의 실패를 검증한다.
- 워커·수명 주기·시작 배너·Inspector·작업 훅 테스트의 브로커 Mock은
  `consumer`를 생성 인자로 명시하도록 수정했다.
  Python 3.12의 런타임 Protocol 검사에서 동적으로 만들어지는 Mock 속성에
  의존하지 않게 하기 위한 변경이며, 제품 코드에 Mock 전용 우회는 추가하지 않았다.
- [한국어 사용 설명서](../../../README.md)와 [영어 사용 설명서](../../../README.en.md)에
  공통 연결 입력과 내부 검사 동작을 동일하게 반영했다.

## 3. Docker RabbitMQ 검증 환경

| 항목 | 값 |
|---|---|
| 검증일 | 2026-10-19 |
| 운영체제 | Windows |
| Python | 3.12.10, 작업 폴더의 `.venv` |
| 컨테이너 | `defstream-rabbitmq` |
| 로컬 이미지 | `rabbitmq:3.13.7-compose` |
| 실제 서버 버전 | `rabbitmq-diagnostics -q server_version`: `3.13.7` |
| AMQP 접속 | `127.0.0.1:5672`, 기본 테스트 사용자 `guest` |
| 포트 공개 범위 | 호스트 loopback으로 제한 |
| 연동 옵션 | `DEFSTREAM_RABBITMQ_TESTS=1` |
| 출력 인코딩 | `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1` |

기존에 같은 이름의 컨테이너가 없어 테스트 전용 컨테이너를 생성했다.
다른 애플리케이션의 RabbitMQ 컨테이너는 변경하지 않았다.

작업 폴더 루트에서 실행한 Docker 명령은 다음과 같다.

```powershell
docker run -d --name defstream-rabbitmq -p 127.0.0.1:5672:5672 rabbitmq:3.13.7-compose
docker exec defstream-rabbitmq rabbitmq-diagnostics -q ping
docker exec defstream-rabbitmq rabbitmq-diagnostics -q server_version
```

`running true`, `Ping succeeded`, AMQP listener 시작을 확인한 뒤 테스트했다.

## 4. 소스 선택과 실행 방식

가상환경에는 별도로 설치된 패키지가 있어 단순 `unittest discover`만으로는
현재 변경을 검증할 수 없다. 임시 검증 스크립트에서 `importlib.util`의
`spec_from_file_location`과 `submodule_search_locations`로 다음 패키지를 직접 로드했다.

| 패키지 | 작업 폴더 루트 기준 소스 |
|---|---|
| `DefStream` | `DefStream\src` |
| `DefStream.Broker.Implements.RabbitMQ` | `DefStream-RabbitMQ\src` |
| `DefStream.Broker.Implements.Redis` | `DefStream-Redis\src` |

로드한 모듈은 `sys.modules`에 등록했다. 스크립트의 최상위에서 소스를 로드하여
Windows의 프로세스 풀 자식 프로세스도 같은 소스를 사용하게 했다.
테스트 실행은 `if __name__ == '__main__'` 안에서 수행했다.
실행 로그에 코어와 RabbitMQ 어댑터의 실제 로드 경로를 출력해 확인했다.

각 패키지의 테스트는 별도 Python 프로세스에서
`unittest.TestLoader().discover(..., pattern='test_*.py')`와
`unittest.TextTestRunner(verbosity=2)`로 실행했다.
코어 테스트 디렉터리는 `DefStream\test`, 어댑터 테스트 디렉터리는
`DefStream-RabbitMQ\test`이다. 테스트 전에 다음 환경 변수를 설정했다.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:DEFSTREAM_RABBITMQ_TESTS = '1'
```

## 5. 검증 결과

| 검증 대상 | 전체 | 통과 | 건너뜀 | 실패·오류 | 소요 시간 |
|---|---:|---:|---:|---:|---:|
| 코어 전체 Python 테스트 | 160 | 156 | 4 | 0 | 42.870초 |
| RabbitMQ 어댑터 전체 Python 테스트 | 60 | 60 | 0 | 0 | 7.345초 |
| 합계 | 220 | 216 | 4 | 0 | 50.215초 |

코어에서 건너뛴 4개는 Redis 전용 통합 테스트이다.
RabbitMQ 선택적 통합 테스트는 활성화되어 실제 서버에 접속했다.

다음 경로의 성공을 확인했다.

- 워커 전용 타입 없이 구조적 연결과 RabbitMQ·Redis 연결 수용.
- 컨슈머 미지원 연결의 명시적 실패와 실행 풀 종료·완료 상태.
- 실제 RabbitMQ 메시지 소비, 재전달, 거부 및 워커 종료.
- 스레드 풀과 프로세스 풀을 통한 실제 작업 처리.
- RPC 성공, 빈 결과, 재전달, 원격 오류, 타임아웃과 라우팅 불가 처리.
- Inspector의 실제 RabbitMQ 프로세스 풀 상태·메트릭 및 Console 전송·RPC.
- 실제 RPC에서 요청 검증과 응답 변환.
- 우선순위 관련 어댑터 회귀 테스트.

수정한 코어의 `Worker.py`, `Broker/Connection.py`는 Pylance 진단 오류가 없었다.
`git diff --check`도 통과했다. 전체 저장소의 정적 분석 통과를 의미하지는 않는다.

검증 후 기본 vhost의 잔여 큐가 없음을 확인하고 테스트 컨테이너를
`docker stop defstream-rabbitmq`로 종료했다. 컨테이너는 재사용할 수 있도록 보존한다.
다시 사용할 때는 `docker start defstream-rabbitmq` 후 준비 상태를 확인한다.

## 6. 호환성 안내

기존처럼 브로커 인스턴스를 `Worker`에 전달하면 된다.
`WorkerConnection`을 직접 import하거나 타입 힌트에 쓰던 코드는
`from DefStream.Broker import Connection`으로 변경해야 한다.
컨슈머 없는 연결은 워커 생성 시점이 아니라 실행 중 컨슈머 생성 직전에 거부된다.

## 7. 기능별 연결 검사와 작업 발행 이름 통일

추가 요구사항에 따라 다음을 반영했다.

- `GetExchange`, `GetQueue`, `GetStream`에 `@runtime_checkable`을 추가했다.
- `TaskSender`를 `Emittable`로, `send` 작업 도우미와 브로커 메서드를 `emit`으로
  변경했다. 공개 export·우선순위 계약·RabbitMQ·Redis 어댑터도 함께 변경했다.
  기존 이름의 호환 별칭은 제공하지 않는다.
- `declare`, `emit`, `request`의 입력을 모두 `broker: Connection`으로 통일했다.
  내부에서 각각 `Declarable`, `Emittable`, `Requestable`을 검사한다.
- `request`의 잘못된 `TaskSender` 타입을 제거하고 RPC만 가능한 연결도 지원한다.
  RPC 지원 검사는 우선순위 처리 전에 수행한다.
- `PrioritySupport`는 이미 제공하던 발행·RPC 계약을 상속 관계로도 표현하도록
  `Emittable`, `Requestable`을 상속한다. 선택적 `priority` 인자를 정적 분석에서도
  올바르게 해석하게 하며, RabbitMQ는 중복 상속을 제거했다.
- Inspector Console의 별도 `Producer` 합성 타입을 제거하고 팩터리가
  `Connection`을 반환하도록 변경했다. 내부 발행은 `emit`을 사용하지만
  HTTP의 `mode="send"`와 기존 화면은 유지했다.
- 저수준 `Sendable.send()`·`Callable.call()`은 유지한다.
- 관련 테스트와 예제, 코어·어댑터의 한영 README 및 연결된 사용 예제를 갱신했다.

### 추가 검증 결과

현재 소스를 직접 로드하는 동일한 검증 방식으로 Docker `defstream-rabbitmq`를
재시작하고 `DEFSTREAM_RABBITMQ_TESTS=1`로 실행했다.

| 대상 | 전체 | 통과 | 건너뜀 | 실패·오류 |
|---|---:|---:|---:|---:|
| 코어 | 164 | 160 | 4 | 0 |
| RabbitMQ 어댑터 | 60 | 60 | 0 | 0 |
| Redis 어댑터 | 36 | 32 | 4 | 0 |
| 합계 | 260 | 252 | 8 | 0 |

- 건너뛴 8개는 Redis 실서버 전용 테스트이다. Redis 실제 서버 테스트는 실행하지 않았다.
- 생성자와 도우미 타입, 기능별 지원·거부, RPC 전용 연결, `emit` 공개 이름과
  기존 작업 `send` 제거, 런타임 Protocol 검사를 검증했다.
- 기존 우선순위 테스트와 실제 RabbitMQ 발행·RPC·소비·실패 처리·Inspector가 통과했다.
- `Message.py`, `Broker/Connection.py`와 양쪽 공개 export는 Pylance 오류가 없었다.
  Console에는 기존 미사용 매개변수 안내만 남아 있다.
- Pylance가 해석한 `emit` 호출 위치는 시그니처와 호환됐다.
  테스트 도구에서는 테스트를 찾지 못해 기존 `unittest`로 검증했다.
- 검증 후 테스트용 RabbitMQ를 종료하고 재사용 가능한 컨테이너는 보존했다.

## 8. Redis·RabbitMQ 동시 실서버 검증

2026-10-19에 Redis 전용 Docker 컨테이너를 추가하고, 이전에 건너뛴 Redis
통합 테스트까지 모두 실행했다. 위의 Redis 미검증 기록은 이 재검증 이전 결과이다.

- 컨테이너: `defstream-redis`, 이미지: `redis:7`, 실제 Redis 버전: `7.4.11`.
- 포트는 `127.0.0.1:6379`에만 공개했고 `redis-cli ping`의 `PONG`을 확인했다.
- `defstream-rabbitmq`도 다시 시작하고 `rabbitmq-diagnostics -q ping`을 확인했다.
- `DEFSTREAM_REDIS_TESTS=1`과 `DEFSTREAM_RABBITMQ_TESTS=1`을 동시에 설정했다.
- 가상환경에 설치된 이전 패키지가 아니라 현재 코어·어댑터 소스를 직접 로드해
  각 프로젝트의 전체 `unittest`를 별도 Python 프로세스에서 실행했다.

```powershell
docker run -d --name defstream-redis -p 127.0.0.1:6379:6379 redis:7
docker exec defstream-redis redis-cli ping
docker start defstream-rabbitmq
docker exec defstream-rabbitmq rabbitmq-diagnostics -q ping
$env:DEFSTREAM_REDIS_TESTS = '1'
$env:DEFSTREAM_RABBITMQ_TESTS = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
```

| 대상 | 전체 | 통과 | 건너뜀 | 실패·오류 | 소요 시간 |
|---|---:|---:|---:|---:|---:|
| 코어 | 164 | 164 | 0 | 0 | 32.319초 |
| RabbitMQ 어댑터 | 60 | 60 | 0 | 0 | 5.546초 |
| Redis 어댑터 | 36 | 36 | 0 | 0 | 2.198초 |
| 합계 | 260 | 260 | 0 | 0 | 40.063초 |

Redis의 발행·소비·이력 읽기·원자적 재전달, QoS·콜백·정상 종료, 방치된 pending
회수와 실행 풀 연동을 검증했다. 코어의 Redis 발행·완료 훅·Inspector 상태·메트릭·Console
통합 테스트도 통과했다. RabbitMQ 통합 테스트 역시 활성화된 상태로 통과했다.

검증 후 Redis `DBSIZE`가 `0`임을 확인했다. 두 컨테이너 모두 종료했고
`exited`, `running=false` 상태를 확인했다. 컨테이너는 보존하여
`docker start defstream-redis defstream-rabbitmq`로 재사용할 수 있다.

## 9. 브로커 팩터리 계약 명명

- `Broker/Connection.py`에 `BrokerFactory` Protocol을 정의하고
  `DefStream.Broker`에서 공개했다.
- `__call__(self) -> Connection`으로 인자 없는 새 연결 생성 계약을 명시했다.
  독립적인 연결을 매번 반환해야 한다는 책임을 독스트링에 기록했다.
- Console의 `broker` 타입을 `Callable[[], Connection]`에서 `BrokerFactory`로
  변경했다. 기존 `callable` 검사와 연결 생성·종료 흐름은 변경하지 않았다.
- 함수·람다·명시적 상속 클래스·구조적 호출 클래스 모두 사용할 수 있도록 유지했다.
- 타입 힌트, 공개 export, 불완전한 구현의 인스턴스화 거부, 네 가지 팩터리 형태와
  호출마다 서로 다른 연결을 반환하는 동작을 테스트했다.
- 한영 README와 사용자용 변경 로그에 계약과 기존 코드 호환성을 설명했다.
- 현재 소스를 직접 로드해 계약·Console 테스트 31개 중 29개 통과,
  실서버 전용 2개 건너뜀을 확인했다. 이번 타입 명명 변경에서는 Docker 실서버
  테스트를 재실행하지 않았으며, 이전 260개 실서버 검증과 구분한다.
- `Broker/Connection.py`의 Pylance 진단에 오류가 없었다.
  Console에는 기존 미사용 매개변수 안내만 남아 있다.
