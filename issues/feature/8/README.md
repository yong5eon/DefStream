# 로깅 지원

## 변경 요약

Worker와 Inspector의 동작을 클래스별 표준 로거로 관찰할 수 있습니다.
라이브러리는 로그를 기록하며, 출력 대상·형식·레벨·필터는 애플리케이션이 정합니다.
런타임 로그 메시지는 영어입니다.

## 추가한 기록

- `DefStream.Worker`: 등록·시작·수신·완료·실패·종료.
- `DefStream.Run`: 작업별 훅·입출력 검증·실행 단계.
- `DefStream.Pool`, `DefStream.ThreadPool`, `DefStream.ProcessPool`,
  `DefStream.Executor`: 실행 환경·제출·결과 회수·대기·종료.
- `DefStream.Inspector`: 서버 생명주기, 요청 수신(DEBUG), 응답 상태·크기·시간(INFO).
- `DefStream.Inspector.Extensions.<클래스 이름>`: 각 확장 고유 진단.

정상 메시지별 상세 흐름은 DEBUG, 주요 생명주기는 INFO로 확인할 수 있습니다.
잘못된 메시지와 대기 시간 초과는 WARNING, 작업·내부 처리 실패는 ERROR로 구분합니다.
Pool 공통 동작도 실제 ThreadPool·ProcessPool의 로거 이름으로 기록됩니다.

## 사용자 설정과 호환성

- 기존 `DefStream.Worker.Worker` 등 모듈 경로 기반 이름으로 필터링했다면
  새 클래스별 이름으로 바꾸세요. `DefStream` 계층 전체 수신도 가능합니다.
- 클래스 멤버 `logger`를 상속하며 사용자 하위 클래스에서 재정의할 수 있습니다.
  사용자 작업이 직접 생성한 로거 이름은 프레임워크가 바꾸지 않습니다.
- 핸들러·NullHandler·레벨을 자동 설정하지 않습니다.
  핸들러가 없으면 Python의 `lastResort`로 WARNING 이상이 출력될 수 있습니다.
- 본문·결과·인증정보는 기본 로그 문맥에서 제외합니다. 사용자 예외 메시지는
  Worker의 실패 traceback에 포함될 수 있으므로 민감정보를 넣지 마세요.
- 작업 처리·정산·종료 계약과 기존 시작 배너는 유지합니다.

## 샘플 변경

샘플은 `print()` 대신 `Sample` 로거를 사용하며 `Sample`과 `DefStream` 계층만
출력합니다. [RabbitMQ Worker 샘플](../../../sample/Worker/RabbitMQ/Worker.py)은
부모와 spawn 자식에 [LoggingSetup](../../../sample/Worker/RabbitMQ/Tasks.py)을 적용합니다.
실제 애플리케이션도 ProcessPool 자식의 로깅을 별도로 설정해야 합니다.
설정 예제는 [사용 설명서](../../../README.md#로깅)를 참고하세요.
