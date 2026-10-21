# Run 에 이름(name)과 설명(description) 지원 구현 기록

## 1. 구현 개요

[요구사항](./REQUIREMENTS.md)에 따라 Run 클래스 정의에 `name`과 `description`을
추가하고, 이름을 AsyncAPI와 Metrics의 작업 식별자로 연결했다. 이름 미지정 시
`모듈명.__qualname__`을 사용한다. 설명은 AsyncAPI Operation에만 반영한다.

- 구현·검증일: 2026-10-20
- 사용자용 안내: [변경 로그](./README.md)

## 2. 구현 내용

- [Run](../../../src/Worker/Run.py) 클래스 정의에서 `name`과 `description`
  키워드를 받는다. `RunMeta`가 이름을 내부 키워드 `run_name`으로 중계하고,
  `__init_subclass__`가 이름과 설명을 처리한다. 명시적 이름은
  `[A-Za-z0-9_.-]+` 전체 일치로 검사하고, 설명은 문자열 또는 `None`으로 검증한다.
- 클래스 생성 시 이름이 생략되면 해당 클래스의 `__module__`과 `__qualname__`으로
  기본 이름을 만든다. 하위 Run에는 상위 Run의 이름과 설명을 상속하지 않는다.
- [Worker](../../../src/Worker/Worker.py)는 Run 등록 시 동일한 이름이 이미
  등록되어 있는지 검사하고 중복을 `ValueError`로 거부한다. 메시지를 Metrics에
  전달하는 식별자도 `run.name`을 사용한다.
- [Specifications](../../../src/Inspector/Extensions/Specifications.py)은
  `operations` 키에 `task.name`을 사용하고, 지정된 `task.description`을 해당
  Operation에 기록한다. 문서 생성 시에도 중복 Operation 키를 거부한다.
- [Metrics](../../../src/Inspector/Extensions/Metrics.py)는 초기 작업 통계 맵의
  키를 `task.name`으로 만들며, 중복 키를 발견하면 통계 맵을 부분 초기화하지 않고
  `ValueError`를 발생시킨다.
- [Specification](../../../src/Worker/Specification.py)에서 `description` 인자와
  AsyncAPI 메시지 설명 생성을 제거했다. schema, validator, example, format은
  유지한다.
- [RabbitMQ Worker 샘플](../../../samples/Worker/RabbitMQ/Tasks.py)과
  [Redis Worker 샘플](../../../samples/Worker/Redis/Sample.py)에 `add`, `divide`
  이름 및 작업 설명을 지정했다. RabbitMQ 샘플의 request·response
  Specification 설명은 Run의 메타데이터로 옮겼다.
- [한국어 사용 설명서](../../../README.md)와
  [영어 사용 설명서](../../../README.en.md)에 새 선언 방법을 반영했다.

## 3. 사용 방법

```python
from DefStream.Worker import Run, Specification


class Add(
  Run,
  name='add',
  description='Add two integers',
  request=Specification(schema=request_schema),
  response=Specification(schema=response_schema),
):
  def run(
    self,
    a: int,
    b: int,
  ):
    return a + b
```

위 Run은 AsyncAPI `operations`와 Metrics에서 모두 `add`라는 키를 사용한다.
`name`을 생략하면 Run 모듈명과 클래스의 `__qualname__`을 결합한 이름을 사용한다.
`description`은 AsyncAPI Operation에만 나타나며 request·response 메시지 설명에는
적용하지 않는다.

## 4. 호환성 영향

- `Specification(description=...)`는 더 이상 지원하지 않는다. 작업 설명은 Run
  클래스 정의의 `description`으로 옮겨야 한다.
- AsyncAPI Operation 이름을 지정하지 않으면 기존 클래스명 단독 키 대신
  `모듈명.__qualname__`이 사용된다. 이 키를 참조하는 클라이언트는 갱신해야 한다.
- Metrics 작업 키는 기본값에서 기존 `모듈명.__qualname__` 형식을 유지한다.
- 동일한 유효 이름의 Run은 Worker 등록에서 거부한다. Metrics 및 AsyncAPI 문서
  생성 경계에서도 덮어쓰기를 방지하도록 중복을 검사한다.

## 5. 검증 결과

### 자동 테스트 및 정적 진단

- 최초 Python 3.12 검증의 `unittest discover -s test`: **199개 실행 중
  191개 통과, 8개 건너뜀**. 이 결과는 Python 3.9·3.10 호환성 검증을 포함하지 않았다.
- Run 이름·설명, 입력 검증, 기본 이름, 상속 비적용, 등록·문서 충돌,
  AsyncAPI 설명과 Metrics 키의 회귀 테스트를 추가했다.
- 변경한 `Run.py`, `Specification.py`, `Metrics.py`, `Specifications.py`에
  Pylance 진단 오류가 없다.
- `Run.__init_subclass__`의 기존 호출 지점과 새 시그니처가 호환됨을 확인했다.
- RabbitMQ와 Redis 샘플 파일의 `py_compile` 검사를 통과했다.

### Docker 브로커 실행

로컬 Docker에 임시 RabbitMQ `3.13-management`와 Redis `7.4-alpine`을 실행하고
각 Worker 샘플을 실제 브로커에 연결했다. Redis는 샘플 기본 연결 설정을 사용했고,
RabbitMQ는 로컬 guest 계정을 사용했다.

| 샘플 | AsyncAPI·Health | Metrics 처리 결과 | 브로커 상태 |
|---|---|---|---|
| RabbitMQ | `/status` 200, Operation 키 `add`, `divide` 및 설명 확인 | 격리 확인에서 각 작업 5건 성공, active 0 | 두 큐의 ready·unacknowledged 모두 0 |
| Redis | `/status` 200, Operation 키 `add`, `divide` 및 설명 확인 | Add 5건 성공, Divide 4건 성공·1건 실패, active 0 | 각 스트림에 샘플 메시지 5건 기록 |

Redis의 Divide 실패는 샘플이 의도적으로 넣는 0 나눗셈 입력에서 발생했다.
각 샘플이 모두 Inspector 기본 포트 `9999`를 사용하므로 HTTP 응답은 워커를
하나씩 분리하여 확인했다. 검증 후 Worker 프로세스와 임시 컨테이너를 종료하고
샘플 프로세스 및 포트 리스너가 남지 않았음을 확인했다.

전체 테스트 중 8개는 선택적 통합 테스트로 건너뛰었다. 이번 로컬 Docker 실행은
브로커와 샘플의 실제 연동 검증이며, 전체 브로커 어댑터 테스트 스위트 실행으로
간주하지 않는다.

## 6. Python 3.9·3.10 호환성 수정

Python 3.9.13과 3.10.11에서 클래스 정의의 `name=` 키워드가
`ABCMeta.__new__(mcls, name, bases, namespace, **kwargs)`의 클래스 이름 인자와
충돌하는 것을 재현했다. 이 경우 `Run.__init_subclass__`에 도달하기 전에
`TypeError: __new__() got multiple values for argument 'name'`이 발생한다.

`ABCMeta`를 상속한 `RunMeta`를 추가하여 공개 `name=`을 내부 `run_name` 키워드로
변환한 뒤 기존 추상 클래스 생성 경로로 전달한다. 이름의 기본값·검증·상속 비적용
처리는 계속 `Run.__init_subclass__`가 담당한다. 사용자 클래스 정의 문법은
변경하지 않으며 `ABCMeta`의 추상 메서드 검사도 유지한다.

[Worker 테스트](../../../tests/test_worker.py)에 이름을 지정한 추상 Run의 생성 거부,
구체 하위 Run의 이름 재정의 및 실행을 검증하는 회귀 테스트를 추가했다.

| Python | 전체 코어 테스트 결과 |
|---|---|
| 3.9.13 | 200개 실행, 192개 통과, 8개 건너뜀 |
| 3.10.11 | 200개 실행, 192개 통과, 8개 건너뜀 |
| 3.12.10 | 200개 실행, 192개 통과, 8개 건너뜀 |
| 3.14.5 | 200개 실행, 192개 통과, 8개 건너뜀 |

구버전 테스트는 개발 환경의 Redis 8.x 클라이언트가 해당 버전과 호환되지 않아
세션 전용 경로에 Redis 5.3.1과 의존성을 설치하여 실행했다. 프로젝트의
의존성 선언과 공용 가상환경은 변경하지 않았다.
Python 3.9의 첫 전체 실행에서는 무관한 Console HTTP 테스트에 Windows
`ConnectionAbortedError`가 발생했으나, 해당 테스트의 단독 실행과 전체 재실행은
통과했다. 변경한 Run 소스의 Pylance 진단에도 오류가 없다.

## 7. 명시적 이름의 허용 문자 변경

Python 식별자 제한을 제거하고 영문 대소문자·숫자·`_`·`.`·`-`를 하나 이상
허용하도록 변경했다. 위치 제한은 없으며 Python 예약어도 허용한다.
빈 문자열, 공백·개행, 한국어 등 다른 문자는 거부한다.
대소문자 변환이나 공백 제거 없이 지정한 이름을 그대로 사용한다.
미지정 이름의 `모듈명.__qualname__` 생성 규칙과 중복 검사는 유지한다.

허용·거부 문자 조합과 입력값 보존, AsyncAPI Operation 키 및 Metrics
스냅샷·Prometheus 레이블의 동일 이름 사용을 회귀 테스트로 검증한다.

- Python 3.12.10: 전체 201개 실행, 193개 통과, 선택적 테스트 8개 건너뜀.
- Python 3.9.13·3.10.11: 각 관련 테스트 43개 실행, 40개 통과, 3개 건너뜀.
- 변경한 Run 소스의 Pylance 진단 및 변경 파일 공백 검사 통과.
