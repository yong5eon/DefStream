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

- [계약 테스트](../../../test/test_protocol_contracts.py)에서 생성자 타입,
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
