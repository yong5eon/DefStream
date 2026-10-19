# 로깅 지원 구현 기록

## 1. 구현 개요

[요구사항](./REQUIREMENTS.md)에 따라 Worker 실행 흐름과 Inspector에 Python 표준
`logging`을 적용했다. 출력 정책은 애플리케이션에 맡기고 클래스별 명시적 로거로
관찰 지점을 제공한다.

- 구현·검증일: 2026-10-20
- 사용자용 안내: [변경 로그](./README.md)
- 연계 구현: [RabbitMQ](../../../../DefStream-RabbitMQ/issues/feature/5/IMPLEMENTS.md),
  [Redis](../../../../DefStream-Redis/issues/feature/5/IMPLEMENTS.md)

## 2. 클래스별 로거와 기록 책임

로거는 클래스 멤버 `logger`로 정의하고 공통 메서드는 `self.logger`를 사용한다.
사용자 하위 클래스의 이름을 자동으로 사용하지 않으며, 명시적으로 재정의할 수 있다.

| 대상 | 로거 이름 | 구현한 관찰 지점 |
| --- | --- | --- |
| [Worker](../../../src/Worker/Worker.py) | `DefStream.Worker` | 작업 등록, 연결·구독·훅, 수신·제출, 성공·실패 정책, 종료·미확인 메시지 |
| [Pool](../../../src/Worker/Pool.py) | `DefStream.Pool` | 제출, 포화, 슬롯 반환, 완료 대기와 종료 |
| ThreadPool·ProcessPool | `DefStream.ThreadPool`·`DefStream.ProcessPool` | 구체 풀 구성과 상속받은 공통 동작 |
| [Executor](../../../src/Worker/Executor.py) | `DefStream.Executor` | 실행 환경 시작·종료, 작업·결과 전달과 실행 환경 장애 |
| [Run](../../../src/Worker/Run.py) | `DefStream.Run` | 작업 전체 이름, 훅·입출력 검증·실행 단계와 소요 시간 |
| [Inspector·Server·RequestHandler](../../../src/Inspector/Inspector.py) | `DefStream.Inspector` | 확장 등록·시작, 서버 생명주기, HTTP 수신·응답과 내부 오류 |
| [Inspector 확장](../../../src/Inspector/Extensions) | `DefStream.Inspector.Extensions.<클래스 이름>` | HealthCheck·Console·Metrics·Dashboard·Specifications의 고유 처리 |

ThreadPool·ProcessPool의 공통 처리는 구체 클래스의 로거로 기록한다.
`Specification`에는 독립 로거를 추가하지 않았다.

## 3. 레벨과 실패 처리

- INFO: Worker·풀·실행 환경·서버의 생명주기와 HTTP 응답 전송 결과.
- DEBUG: 메시지별 정상 처리, 작업 실행·검증·훅, 풀 포화와 확장 고유 진단.
- WARNING: 잘못된 메시지, 명시적 완료 대기의 시간 초과와 Console 요청 거부 등.
- ERROR: 작업·실행 환경·서버·확장 내부 실패와 종료 후 확인 처리 불가.

Worker로 전달되는 작업 실패의 최종 ERROR와 traceback은 Worker가 담당한다.
Run·Pool·Executor의 일반 작업 실패 추적은 DEBUG로 기록해 중복을 줄였다.
Mapping이 아닌 메시지의 거부는 WARNING으로 구분하고 기존 실패 정책 호출은 유지했다.
Run을 직접 호출했을 때의 예외 전파도 유지한다.

## 4. Inspector의 HTTP 기록

기본 WSGI 요청 처리 경계를 확장하여 다음을 기록한다.

- 파싱한 요청 수신: DEBUG, HTTP 메서드와 쿼리를 제외한 경로.
- 응답 전송 결과: INFO, 메서드·경로·상태 코드·응답 크기·소요 시간.
- WSGI·연결 처리 실패: ERROR, 예외 타입과 프레임의 파일·줄·함수 위치.

확장에서는 공통 HTTP 접근 로그를 반복하지 않는다. 전송 중단을 정상 전송으로
기록하지 않으며, 오류 기록에는 예외 문자열과 소스 코드 줄을 포함하지 않는다.
HealthCheck는 probe 예약·응답·판정과 응답 생성을 DEBUG로 기록하고,
예약 실패를 ERROR로 기록한다. 상태 변화 전용 INFO·WARNING은 추가하지 않았다.

## 5. 출력 설정과 샘플

- 라이브러리는 핸들러·NullHandler·포매터·필터·레벨을 설정하지 않는다.
- 루트 로거까지 기본 전파를 유지하며, 미설정 시 표준 `logging.lastResort`가
  WARNING 이상을 stderr에 출력할 수 있다.
- 런타임 로그 메시지는 영어로 작성하고 한국어 문서·주석은 유지한다.
- 본문·결과·인증정보를 기본 문맥에 넣지 않는다. 단, Worker의 작업 실패
  traceback에는 사용자 예외 메시지가 포함될 수 있으므로 사용자가 주의해야 한다.
- [Worker 샘플](../../../sample/Worker)과 [Broker 샘플](../../../sample/Broker)은
  `Sample`과 `DefStream` 계층만 핸들러 필터로 선택한다.
- 샘플의 `print()`는 로그로 전환하고 라이브러리 시작 배너는 유지했다.
- [RabbitMQ Worker 샘플](../../../sample/Worker/RabbitMQ/Worker.py)은 부모 진입점과
  ProcessPool의 `setups`에 [LoggingSetup](../../../sample/Worker/RabbitMQ/Tasks.py)을
  적용한다. `spawn` 자식이 부모의 핸들러를 자동 상속한다고 가정하지 않는다.

## 6. 검증 결과

Python 3.13.16에서 실제 RabbitMQ·Redis가 실행 중인 환경으로 검증했다.

| 검증 범위 | 결과 |
| --- | --- |
| 코어 로깅·Inspector·Worker·풀·훅·프로세스·메시지 관련 테스트 | 151개 통과 |
| RabbitMQ 연계 테스트 | 52개 통과 |
| Redis 연계 테스트 | 25개 통과 |
| 세 프로젝트 소스·샘플의 로그 및 observe 호출 문자열 | 376곳 점검, 한국어 문자열 없음 |
| 세 프로젝트 소스·샘플 `compileall` 및 `git diff --check` | 통과 |

[로깅 테스트](../../../test/test_logging.py)는 클래스 멤버·상속·사용자 재정의,
레벨·본문 제외·작업 실패 traceback 중복 방지·배너 유지·샘플 필터·spawn 설정을
검증한다. [Inspector 로깅 테스트](../../../test/test_inspector_logging.py)는 실제 HTTP
요청에서 수신·응답 각 1회 기록, 쿼리·본문 제외, WSGI 500과 전송 중단을 검증한다.
기존 테스트의 이전 모듈 로거 기대값도 새 이름과 레벨에 맞췄다.

위 228개는 선택해 실행한 관련 테스트의 합계이며 코어 전체 테스트 실행을 뜻하지 않는다.
모든 Python 버전·모든 파일의 정적 타입 검사나 배포 검증을 완료한 것은 아니다.

### 재검증

개발 가상환경과 로컬 브로커가 준비된 작업공간 루트에서 실행한다.
통합 테스트는 브로커에 테스트 자원을 생성·정리하므로 운영 환경을 사용하지 않는다.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:DEFSTREAM_RABBITMQ_TESTS = '1'
$env:DEFSTREAM_REDIS_TESTS = '1'
Set-Location .\DefStream\test
& ..\..\.venv\Scripts\python.exe -m unittest test_logging test_inspector_logging test_worker test_worker_startup test_pool_callbacks test_runner_hooks test_lifecycle_hooks test_process_signals test_inspector test_inspector_console test_dashboard test_specifications test_protocol_contracts test_task_messages
```

브로커별 재검증 명령은 각 구현 기록을 참고한다.
