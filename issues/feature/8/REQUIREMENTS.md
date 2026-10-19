# 로깅 지원

## 1. 목적과 범위

- 개발자가 Worker의 시작부터 작업 실행, 메시지 완료 처리, 종료까지 추적할 수 있도록 풍부한 진단 로그를 제공한다.
- Inspector 및 확장의 시작, HTTP 요청 처리, 상태 확인과 내부 실패를 관찰할 수 있게 한다.
- Python 표준 `logging`을 사용하며, 출력 대상·형식·레벨·필터는 사용자 애플리케이션이 결정한다.
- 이 문서는 현재 소스 조사와 사용자 검토를 반영한 요구사항이다. 클래스별 로거 이름과 HTTP 기록 책임은 아래와 같이 확정한다.
- 이 단계에서는 소스 코드를 변경하거나 로깅 초기화 API, 사용자용 `LOG_*` 함수를 구현하지 않는다.
- 브로커 구현체는 별도 명세를 따른다.
  - [DefStream-RabbitMQ 로깅 지원](../../../../DefStream-RabbitMQ/issues/feature/5/REQUIREMENTS.md)
  - [DefStream-Redis 로깅 지원](../../../../DefStream-Redis/issues/feature/5/REQUIREMENTS.md)

## 2. 로거 이름과 사용자 설정

- 모듈 경로를 그대로 사용하는 `getLogger(__name__)` 대신, 클래스마다 명시적으로 정한 고정 이름을 사용한다.
- 로거는 클래스 멤버로 보관한다. 기반 클래스의 공통 메서드는 해당 멤버를 사용하고, 구체 클래스는 필요한 경우 자신의 명시적 로거 멤버를 정의한다.
- Worker 계열 이름은 `DefStream.ClassName` 형식이다.
- Inspector·Server·RequestHandler는 `DefStream.Inspector` 이름을 공유한다.
- 내장 확장은 `DefStream.Inspector.Extensions.ExtensionName` 형식이다.
- 프레임워크 로그의 이름을 사용자 정의 하위 클래스의 모듈·클래스 이름으로 자동 변경하지 않는다.
  - 사용자 `SendEmail`이 `Run`을 상속해도 기반 실행 흐름 로그는 `DefStream.Run`으로 기록한다.
  - 실제 작업의 `모듈명.클래스명`은 별도 문맥으로 남겨 작업들을 구분한다.
- 사용자 정의 작업에서 직접 호출한 로깅의 이름·동작은 변경하지 않는다.
- 클래스별 이름과 상위 `DefStream`, `DefStream.Inspector`에서 선택적으로 수신할 수 있어야 한다.
- 루트 로거로의 기본 전파를 막지 않으며, 라이브러리가 `basicConfig()`, 출력 핸들러, 포매터, 필터, 로그 레벨을 임의로 설정하지 않는다.
- DefStream은 로그 기록만 수행하며 출력 핸들러뿐 아니라 `NullHandler`도 추가하지 않는다. 로그 수신·출력 설정은 사용자 애플리케이션의 책임이다.
- 사용자가 핸들러를 설정하지 않으면 Python 표준 동작인 `logging.lastResort`에 의해 WARNING 이상이 stderr에 출력될 수 있다. 이번 요구사항은 미설정 상태의 완전한 무출력을 보장하지 않는다.

## 3. 현재 상태

- [Worker](../../../src/Worker/Worker.py)의 모듈 로거가 작업 실패, 미확인 메시지를 남긴 종료, 종료 후 메시지 확인 처리 불가를 ERROR로 기록한다.
- [Inspector](../../../src/Inspector/Inspector.py)의 모듈 로거가 HTTP 접근 기록을 INFO로, 서버 실행 실패를 예외 로그로 기록한다.
- [Console](../../../src/Inspector/Extensions/Console.py)은 인증·출처·입력 거부, RPC 실패, 내부 요청 처리 실패를 기록한다.
- [HealthCheck](../../../src/Inspector/Extensions/HealthCheck.py)는 상태 확인 작업 예약 실패를 예외 로그로 기록한다.
- 다른 Worker 모듈과 나머지 Inspector 확장에는 현재 직접적인 로깅 호출이 없다.
- [Startup](../../../src/Worker/Startup.py)은 로거 대신 `print()`로 시작 배너와 구성을 출력한다.

## 4. 클래스별 로거 이름

아래 이름을 사용한다. 확장은 고유한 내부 처리와 진단에 필요한 로그만 기록하며, 공통 HTTP 접근 기록을 반복하지 않는다.

| 구분 | 클래스와 소스 | 로거 이름 | 필요한 관찰 범위 |
| --- | --- | --- | --- |
| 우선 대상 | [Worker](../../../src/Worker/Worker.py) | `DefStream.Worker` | 등록·시작·수신·완료·실패·종료의 전체 조정 |
| 공통 구현 | [Pool](../../../src/Worker/Pool.py) | `DefStream.Pool` (직접 생성 시) | 제출 수락·포화·슬롯 반환·완료 대기를 기록하며, 내장 구체 풀에서는 구체 클래스의 로거 멤버를 사용 |
| 우선 대상 | [ThreadPool](../../../src/Worker/Pool.py) | `DefStream.ThreadPool` | 스레드 풀 구성 및 상속받은 Pool 공통 동작 |
| 우선 대상 | [ProcessPool](../../../src/Worker/Pool.py) | `DefStream.ProcessPool` | 프로세스 풀 구성 및 상속받은 Pool 공통 동작 |
| 우선 대상 | [Executor](../../../src/Worker/Executor.py) | `DefStream.Executor` | 실행 환경 시작·종료, 작업 전달·결과 회수, 실행 환경 장애 |
| 우선 대상 | [Run](../../../src/Worker/Run.py) | `DefStream.Run` | 사용자 작업을 감싸는 훅·검증·실행 단계 |
| 우선 대상 | [Inspector](../../../src/Inspector/Inspector.py) | `DefStream.Inspector` | 확장 등록·시작, HTTP 서버 생명주기와 요청 처리 |
| 보조 대상 | [Server](../../../src/Inspector/Inspector.py) | `DefStream.Inspector` (공유) | HTTP 서버의 연결 처리 문맥. Inspector와 중복되는 생명주기 로그는 제외 |
| 보조 대상 | [RequestHandler](../../../src/Inspector/Inspector.py) | `DefStream.Inspector` (공유) | 공통 HTTP 요청 수신(DEBUG)과 응답 상태를 포함한 전송 결과(INFO) |
| 우선 대상 | [HealthCheck](../../../src/Inspector/Extensions/HealthCheck.py) | `DefStream.Inspector.Extensions.HealthCheck` | 상태 확인 작업 예약·응답·시간 초과·상태 변화 |
| 우선 대상 | [Console](../../../src/Inspector/Extensions/Console.py) | `DefStream.Inspector.Extensions.Console` | 요청 검증·발행·RPC·접근 거부·내부 오류 |
| 우선 대상 | [Metrics](../../../src/Inspector/Extensions/Metrics.py) | `DefStream.Inspector.Extensions.Metrics` | 수집 초기화, 작업 관측 시작·종료, 스냅샷·응답 생성 |
| 우선 대상 | [Dashboard](../../../src/Inspector/Extensions/Dashboard.py) | `DefStream.Inspector.Extensions.Dashboard` | Metrics 연결, HTML·JSON 응답 생성 |
| 우선 대상 | [Specifications](../../../src/Inspector/Extensions/Specifications.py) | `DefStream.Inspector.Extensions.Specifications` | 작업 목록의 AsyncAPI 문서 생성과 응답 |

### 4.1. 독립 로거를 우선 추가하지 않을 대상

| 대상 | 판단 근거와 기록 책임 |
| --- | --- |
| [Specification](../../../src/Worker/Specification.py) | 독립 로깅 대상에서 제외한다. 입력·출력 검증 단계와 실패는 Run·Worker에서 관찰한다. Inspector의 Specifications 확장과는 별개이다. |
| [Handler](../../../src/Worker/Worker.py) | Worker의 `receive()`로 전달하는 어댑터이다. 수신 로그는 Worker에서 기록한다. |
| [WorkerSetup·WorkerCleanup](../../../src/Worker/Worker.py), [PoolSetup·PoolCleanup](../../../src/Worker/Pool.py), [RunSetup·RunComplete·RunError](../../../src/Worker/Run.py) | 사용자 구현용 추상 계약이다. 호출 전후를 프레임워크의 호출 지점에서 기록하며 구현체 내부 로그는 사용자가 정한다. |
| [Context](../../../src/Worker/Run.py), [PoolFull](../../../src/Worker/Pool.py) | 문맥 보관 객체와 예외 타입이다. 생성 자체를 별도 로깅하지 않는다. |
| [Extension](../../../src/Inspector/Extension.py) | 기본 훅은 동작이 없거나 구체 확장으로 위임한다. 등록·호출은 Inspector, 구체 동작은 해당 확장에서 기록한다. |
| [Response](../../../src/Inspector/Response.py), [TaskMetrics·스냅샷 타입](../../../src/Inspector/Extensions/Metrics.py) | 응답·집계·데이터 표현 객체이다. 생성이나 필드별 갱신을 별도 로거로 기록하지 않는다. |
| [Broker 계약](../../../src/Broker/Connection.py)과 [기본 Consumer](../../../src/Broker/Consumer.py) | 인터페이스 및 공통 위임이다. 실제 I/O 로그는 구현체에서 기록한다. |
| [Requeue·Reject](../../../src/Broker/Policies.py) | Event의 `nack()`·`reject()`로 위임한다. Worker/Consumer에서 정책 선택, 구현체 Event에서 실제 처리 결과를 기록한다. |
| [Descriptor](../../../src/Descriptor)·[Validator](../../../src/Validator) 계열 | 값 변환·검증의 세부 재귀 호출마다 로그를 추가하지 않는다. 작업 경계의 Run에서 단계와 실패를 추적한다. |

### 4.2. 클래스가 아닌 처리의 귀속

- [Startup.startup()](../../../src/Worker/Startup.py): 기존 `print()` 시작 배너와 구성 출력을 유지한다. 로그로 대체하거나 동일한 배너를 중복 로깅하지 않는다. Worker의 생명주기 로그는 별도로 기록한다.
- [Executor의 execute_loop()·initialize_process()](../../../src/Worker/Executor.py): 스레드·프로세스 내부 실행 로그는 `DefStream.Executor`에 귀속하는 후보로 둔다.
- [Executor의 run_cleanups()](../../../src/Worker/Executor.py): Worker 종료와 실행 환경 종료에서 함께 사용한다. 훅 호출 주체의 로거에서 기록하여 중복을 피한다.
- [Message의 declare()·emit()·request()](../../../src/Worker/Message.py): 클래스가 없는 공통 API이므로 새 클래스나 임의의 로거 이름을 만들지 않는다. 이번 초안에서는 실제 브로커 구현체와 Console 호출 지점에서 기록한다.
- Pool 공통 메서드의 `self`는 실제 ThreadPool·ProcessPool 인스턴스이므로 구체 풀에 명시적으로 지정한 로거를 사용한다. 두 내장 풀의 공통 동작이 `DefStream.Pool`로 기록되지 않도록 한다.
- 사용자 하위 클래스는 기반 ThreadPool·ProcessPool의 명시적 이름을 유지한다. 단순히 `type(self).__name__`으로 로거 이름을 자동 생성하지 않는다.
- Pool은 추상 클래스가 아니며 외부 executor를 받아 직접 생성할 수 있는 기존 공개 API이다. 클래스 멤버의 이름은 `DefStream.Pool`로 두고, ThreadPool·ProcessPool은 각각 자신의 명시적 로거 멤버를 정의한다. 별도 이름 판별·주입 API를 추가하지 않는다.

## 5. 레벨별 기록 요구사항

### 5.1. Worker

- INFO: 시작 시도, 구독을 마치고 수신 가능한 상태, 최초 종료 요청, 실행 중 작업 정리 대기, 실제 자원 정리를 마친 종료.
- DEBUG: 작업 등록, broker 연결·Consumer 생성 단계, setup·cleanup 호출 전후, 구독 적용, 메시지 수신, Pool 제출, 결과 콜백 예약, 성공·실패 정책 적용, 미완료 작업 수 변화.
- DEBUG: 종료 중 수신 메시지의 `nack()`, Pool 포화에 따른 `nack()` 등 정상 흐름 제어.
- WARNING: Mapping이 아닌 메시지 본문처럼 실행 전에 거부하는 잘못된 메시지. 해당 사건을 기존 ERROR 경로와 이중 기록하지 않는다.
- ERROR: 사용자 작업·훅·검증 실패, Consumer 종료 시 남은 미확인 메시지, Consumer 종료 후 결과 도착으로 확인 처리 불가.
- 완료 로그는 작업 실행 성공과 Consumer 완료 처리의 성공을 구분한다. 브로커 재전달·영속화까지 보장한 것처럼 표현하지 않는다.

### 5.2. Pool·ThreadPool·ProcessPool·Executor

- INFO: 구체 풀의 동시 실행 수와 실행 방식, Executor 실행 환경 시작·종료, Pool 종료 시작·완료.
- DEBUG: 작업 제출·회수, 내부 작업 키, 사용 슬롯·대기 작업 수, Future 완료, 결과·예외 전달 단계, 실행 단위별 setup·cleanup.
- DEBUG: 정상적인 풀 포화, 취소·미제출 등 기존 흐름상 발생 가능한 상태. 포화가 발생할 때마다 WARNING을 출력하지 않는다.
- WARNING: 명시적으로 요청한 완료 대기의 시간 초과. 정상적인 내부 큐 조회의 `Empty`는 경고가 아니다.
- ERROR: 실행 환경 시작 실패, 실행 단위 비정상 종료, 결과 수집 루프 장애, 작업 결과 직렬화 실패.
- 사용자 작업 예외를 Pool과 Executor에서도 반복 ERROR로 출력하지 않는다. Worker로 전달되는 경로에서는 최종 작업 실패 로그를 Worker가 담당한다.
- 프로세스 실행의 로그에는 프로세스 구분이 가능해야 한다. 부모의 핸들러 설정이 `spawn` 자식에게 자동으로 전달된다고 가정하지 않으며 기존 setup 훅을 이용한 자식 로깅 설정 방법을 문서화한다.

### 5.3. Run

- DEBUG: 작업의 전체 이름, setup·입력 검증·실행·출력 검증·complete/error 훅의 시작·완료·실패 단계.
- DEBUG: 실행 소요 시간은 시작과 종료의 대응이 가능한 범위에서 기록한다. Run 실행 시간과 Worker 전체 처리 시간은 구분한다.
- INFO: 메시지마다 반복되는 정상 실행 로그를 기본적으로 올리지 않는다.
- 작업 실패의 최종 ERROR와 traceback은 Worker에서 기록한다. Run 단계 로그는 실패가 발생한 위치를 식별하는 역할을 한다.
- Run을 Worker 밖에서 직접 실행했을 때는 예외가 기존대로 호출자에게 전파된다. 로깅을 위해 예외를 삼키지 않는다.
- 검증 대상 값, 스키마 전체, 예제 값은 출력하지 않는다.

### 5.4. Inspector·Server·RequestHandler

- INFO: 실제 바인딩된 주소·포트와 서버 시작·종료. 포트 `0`을 요청한 경우 실제 할당 포트를 기록한다.
- DEBUG: 확장 클래스·경로 등록, 확장 시작, 라우팅 대상 및 HTTP 요청 수신 시 메서드·안전한 경로.
- INFO: HTTP 응답 전송 결과를 상태 코드와 함께 기록한다. 가능한 경우 응답 크기·처리 시간도 포함한다. 모든 확장의 공통 접근 기록은 이 경계에서 담당한다.
- 응답 생성과 실제 전송 완료를 구분한다. 전송 도중 실패한 응답을 정상 전송 완료로 기록하지 않으며, 기본 WSGI 접근 기록과 추가 로그가 중복되지 않도록 한다.
- WARNING: 비정상 요청 거부는 HTTP 상태와 사유를 구분하되, 정상적인 404·405를 일괄 경고로 취급하지 않는다.
- ERROR: 서버 바인딩·실행 실패, 확장 시작·요청 처리 중 내부 오류. 이미 전파되는 예외의 의미와 Worker 중지 동작을 보존한다.

### 5.5. Inspector 확장

| 클래스 | INFO | DEBUG | WARNING / ERROR |
| --- | --- | --- | --- |
| HealthCheck | 관측 상태 변화와 복구만 기록하는 후보 | probe 예약·응답·시간 초과, 판정 상태 | 정상 실행 중 응답 불가 전환은 WARNING 후보, 예약 중 예외는 ERROR. 정상 시작·종료 상태의 503은 장애와 구분 |
| Console | 초기화 및 관리용 작업 발행·RPC 요청의 접수·성공 요약 | 카탈로그 생성, producer 생성·연결·정리, 작업·모드·소요 시간 | 인증·출처·입력 거부, 동시 요청 제한, RPC 시간 초과·원격 오류는 WARNING. 내부 요청 처리 실패는 ERROR |
| Metrics | 수집 초기화와 관측 대상 작업 수 | 작업 관측 시작·종료, 스냅샷·렌더링 요약 | 집계·렌더링 내부 오류. 측정 대상 작업 실패를 Metrics에서 다시 ERROR로 출력하지 않음 |
| Dashboard | Metrics 확장 연결 | HTML·JSON 응답 생성·소요 시간 | 필수 Metrics 연결 실패, 리소스 읽기·응답 생성 실패 |
| Specifications | 확장 시작 시 경로 등 등록 요약은 Inspector가 담당 | 문서 생성 시작·완료, 작업·채널 수 | 중복 식별자·주소 오류·스키마 문서 생성 실패 |

- 매번 같은 실패 상태를 반복하는 probe나 HTTP 조회로 WARNING·ERROR가 무제한 반복되지 않도록 기록 지점과 빈도를 검토한다.
- 표의 오류는 각 클래스의 관찰 대상이다. 공통 Inspector 경계에서 기록한다면 동일 예외를 확장에서도 다시 ERROR로 기록하지 않는다.
- 공통 HTTP 수신·응답 기록은 확장에서 반복하지 않는다. 단순 응답 생성이라는 이유만으로 독립 로그를 의무화하지 않고 확장 고유의 처리 단계가 있을 때 DEBUG를 기록한다.

## 6. 기록 품질과 호환성

- 로그 문구는 한국어로 작성하고 API·클래스·작업 식별자는 원문을 유지한다.
- 최소 문맥은 사건명, 처리 단계, 작업의 전체 이름이며 해당 시점에 실제로 알 수 있는 값만 기록한다.
- 메시지 식별자가 필요한 경우 브로커별 속성을 임의로 가정하지 않는다. 공통 Event 계약을 확장할지는 별도 결정하며, 현 단계에서는 가짜 식별자를 만들지 않는다.
- 비밀번호, 인증 토큰·다이제스트, 전체 연결 설정, 메시지 본문, 결과 값, HTTP 요청 본문·헤더 전체, 쿼리 문자열을 기록하지 않는다.
- 객체의 `repr()`나 예외 문자열에 본문·인증정보가 포함될 수 있으므로 무조건 출력하지 않는다. traceback 기록도 예외 메시지에 민감정보가 포함될 가능성을 검토한다.
- 같은 예외의 traceback은 한 처리 경계에서 기록한다. 예외를 로깅하기 위해 추가한 포착 구문은 기존 전파·정리·재시도 동작을 바꾸지 않는다.
- DEBUG 비활성 상태에서 로그만을 위한 직렬화·전체 순회·추가 I/O를 하지 않는다. 메시지 치환은 지연 평가를 활용한다.
- 로그 추가를 이유로 제출 순서, 슬롯 반환, ack/nack/reject, 종료 대기, 훅 실행 횟수, 스레드·프로세스 소유권을 바꾸지 않는다.

## 7. 확정 사항과 구현 원칙

1. `print()` 시작 배너와 구성 출력을 유지한다.
2. 로거는 클래스 멤버로 보관하고, Pool 공통 동작은 구체 클래스의 로거 멤버로 기록한다. 직접 생성한 Pool은 `DefStream.Pool`을 사용한다.
3. 상태 확인 반복 실패의 빈도 제어는 중복·과도한 출력 방지 원칙에 따라 구현 시 구체화한다. 별도 설정 API를 미리 추가하지 않는다.
4. 핸들러 주입·로거 교체 API를 추가하지 않으며, 명시적 이름과 상속 시 이름 유지 계약을 지킨다.

## 8. 구현 후 수용 기준

- 확정된 각 클래스 이름으로 LogRecord가 생성되고, 사용자 Run 하위 클래스 때문에 프레임워크 로거 이름이 달라지지 않는다.
- ThreadPool·ProcessPool의 상속받은 공통 메서드도 각각 `DefStream.ThreadPool`·`DefStream.ProcessPool`로 기록하며 사용자 하위 클래스에서도 명시적 이름을 유지한다.
- Inspector·Server·RequestHandler가 `DefStream.Inspector`를 공유하고, 요청 수신은 DEBUG, 응답 전송 결과와 상태 코드는 INFO로 한 번씩 기록한다.
- Specification에 독립 로거를 추가하지 않는다.
- 기존 `print()` 시작 배너·구성 출력의 내용과 동작을 유지하고, 로그 설정 여부로 이를 비활성화하지 않는다.
- Worker 정상 처리·실패·풀 포화·종료, Executor 실행 환경 장애, Inspector 및 확장 정상·실패 경로의 레벨과 문맥을 검사한다.
- `DefStream` 상위 로거 및 루트 핸들러에서 전파를 수신하고, 클래스·확장별 설정으로 선택 수신할 수 있다.
- 사용자 핸들러·레벨·필터·포매터를 임의로 변경하지 않고, DefStream이 출력 핸들러 또는 NullHandler를 추가하지 않는다.
- INFO에서 메시지별 DEBUG 로그가 나오지 않으며, 정상 포화·폴링·시작 및 종료 상태가 경고로 반복 출력되지 않는다.
- 동일 실패의 중복 traceback과 민감정보 누출이 없고, 기존 Worker·Pool·Run·Inspector 테스트가 보장하는 동작을 유지한다.
- ProcessPool의 부모·자식 로그 수집 조건과 설정 예제를 문서화하고, 프로세스별 로깅 설정을 적용한 경우를 검증한다.