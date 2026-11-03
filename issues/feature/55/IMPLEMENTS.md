# Worker 메시지 발행·요청 재시도 구현

## 결과

[요구사항 명세](./REQUIREMENTS.md)에 따라 [Worker 메시지 함수](../../../src/Worker/Message.py)의 `emit()`과 `request()`에 `retry`와 `interval` 키워드 인자를 추가했습니다. 기본값은 각각 `None`과 1초입니다. `None` 또는 `0`은 한 번 호출하며, `N`은 최초 호출 후 최대 `N`번 추가 호출합니다.

입력 설정은 브로커 호출 전에 검증합니다. 재시도는 브로커의 `emit()`·`request()` 호출에만 적용하고, 실패 후 시도가 남은 때만 대기하며, 최종 예외를 그대로 전파합니다. `request()`의 `timeout`과 두 API의 기존 우선순위 전달을 재시도마다 유지합니다. 모든 `Exception`을 대상으로 하므로 `RemoteError`도 재시도되며, 중복 요청·작업 실행 방지는 제공하지 않습니다.

브로커 인터페이스나 구현체, 연결 생성·종료 동작은 변경하지 않았습니다.

PR 리뷰 후 `interval`을 `threading.TIMEOUT_MAX` 이하로 제한하고 범위 비교를 실수 변환보다 먼저 수행하도록 보완했습니다. 지나치게 큰 간격은 브로커 호출 전에 `ValueError`로 거부합니다. 경계값 테스트 2개를 추가하여 현재 메시지 API 테스트 15개가 통과했습니다.

초기 구현 후 공개 인자명을 `retry`와 `interval`로 변경했습니다. 현재 API와 문서에는 이전 이름을 남기지 않았습니다.

## 검증

- [메시지 API 회귀 테스트](../../../tests/test_task_messages.py): 15개 테스트 통과. 재시도 횟수·대기, 기본값·0회, 중간 성공, 최종 예외 객체 보존, `RemoteError`, priority·timeout, 입력 검증과 간격 경계값을 확인했습니다.
- Pylance 함수 시그니처 호환성 검사에서 `emit()`·`request()`의 기존 호출부가 각각 호환됨을 확인했습니다.
- Pylance 진단에서 오류가 없고, 변경한 Python 소스와 테스트의 syntax 검사도 통과했습니다.
- 한국어·영어 작업 매뉴얼과 고객용 [변경 로그](./CHANGELOG.md)를 갱신했습니다.
- 실제 RabbitMQ·Redis 연결 장애에 대한 통합 검증은 수행하지 않았습니다.

## 단계별 기록

- [Worker 재시도 구현](./implements/1793714914193.md)
- [재시도 간격 오버플로 사전 차단](./implements/1793717149425.md)
