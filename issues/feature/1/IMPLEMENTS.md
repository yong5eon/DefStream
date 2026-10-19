# 워커 작업 우선순위 구현 기록

## 1. 구현 범위

[요구사항](./REQUIREMENTS.md)에 따라 작업 정의, 선언, 전송, RPC 요청에 우선순위를 연결했다.
Redis 구현, 실행 풀 스케줄링, 작업 선점은 변경하지 않았다.

## 2. 주요 변경

- [Run](../../../src/Worker/Run.py)은 기존 `parameters`의 구독 설정에서
  `priority`와 `max_priority`를 읽는다. 별도의 `Run.priority` 속성이나
  클래스 선언 키워드는 제공하지 않는다. 구독 객체와 매핑을
  모두 지원하며, 기본값과 최대값의 타입·하한 및 상호 범위를 검증한다.
- 자식 작업은 부모 구독 설정을 상속한다. 구독 설정을 재정의할 때 상속된 기본값이나
  최대값을 제거하면 오류로 거부한다. 변경하려면 유지할 값도 새 구독 설정에 명시한다.
- [메시지 API](../../../src/Worker/Message.py)의 `send`, `request`에 키워드 전용
  `priority`를 추가했다. 호출값이 `None`이면 작업 기본값을 사용하며 `0`을 보존한다.
- [PrioritySupport](../../../src/Broker/Connection.py) 계약으로 지원 브로커의
  구독 정규화와 우선순위 발행을 구분한다. 기존 브로커 계약은 유지한다.
- 우선순위를 전혀 사용하지 않는 경로는 기존 인자 형태로 호출한다.
  미지원 브로커에 우선순위를 요청하면 선언·발행 전에 `NotImplementedError`를 발생시킨다.
- [공유 검증 함수](../../../src/Broker/Priority.py)를 작업 및 RabbitMQ 경로에서
  재사용한다. 정수가 아닌 값과 `bool`은 `TypeError`, 범위 오류는 `ValueError`로 처리한다.

## 3. 브로커 연계

- RabbitMQ `Subscription` 생성·파싱 시 기본값만 있으면 최대값을 `255`로
  정규화한다. 원본 매핑은 변경하지 않으며 기존 구독 객체는 그대로 재사용한다.
- 작업 최대값이 있으면 이를 우선 사용한다. 호출에서만 지정하면 브로커 허용 범위만
  검증하고 큐 선언·변경·조회는 수행하지 않는다.
- 작업 본문, 스키마, ACK 및 실행 풀의 처리 흐름은 변경하지 않았다.

## 4. 검증 결과

- 가상 환경의 Python과 기존 `unittest` 러너로 전체 코어 테스트 137개를 실행했다.
  129개 통과, 선택적 통합 테스트 등 8개 건너뜀.
- 새 우선순위 테스트 7개로 기본값, 최대값, `0`, 호출 재정의, RPC 전달,
  Redis 거부·기존 전송, 상속 및 잘못된 설정을 검증했다.
- Windows 기본 CP949 출력에서는 기존 시작 배너가 인코딩 오류를 발생시켜,
  `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`로 실행하여 통과했다.
  관련 없는 시작 배너 코드는 수정하지 않았다.
- 변경한 코어 소스의 Pylance 진단에 오류가 없음을 확인했다.
- Redis 회귀 테스트도 14개 중 10개 통과, 선택적 통합 테스트 4개 건너뜀으로 확인했다.
- 테스트 도구에서 테스트를 발견하지 못하여 저장소의 `unittest discover`로 검증했다.
- 후속 Docker RabbitMQ 3.13.7 검증에서 어댑터 전체 35개 테스트가 모두 통과했다.
  코어 메시지·우선순위 테스트도 실제 RabbitMQ 옵션을 활성화하여 18개 중
  16개 통과, Redis 전용 통합 테스트 2개 건너뜀을 확인했다.
- 기본값을 `Subscription.priority`로 통합한 뒤 전체 코어 테스트를 재실행했다.
  RabbitMQ 실서버 옵션을 활성화하여 137개 중 133개 통과, 4개 건너뜀을 확인했다.
  Redis 회귀 테스트는 14개 중 10개 통과, 4개 건너뜀이다.
- 코어의 수정된 소스는 Pylance 오류가 없었다. RabbitMQ 원본 경로는 기존 상대
  import 해석 문제 등이 남아 있어 전체 정적 분석 통과로 간주하지 않는다.

실행 명령은 작업 폴더 루트 기준이다.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m unittest discover -s .\DefStream\test
```

## 5. 공통 브로커 참조 경로 통일

- 구현체가 공통 인터페이스와 요소를 `from DefStream.Broker import ...`로 참조하도록 공개 경로를 통일했다.
- 공통 패키지에서 `Requeue`, `Reject`, `validate_priority`를 추가로 공개했다.
- RabbitMQ와 Redis 구현체의 상위 상대 import를 제거했다. 구현체 내부 import는 유지했다.
- RabbitMQ 실서버 테스트 38개 통과, Redis 테스트 10개 통과·4개 건너뜀,
  코어 메시지 테스트 16개 통과·2개 건너뜀을 확인했다.

## 6. 관련 문서

- [사용 설명서](../../../README.md)
- [RabbitMQ 구현 기록](../../../../DefStream-RabbitMQ/issues/feature/1/IMPLEMENTS.md)
