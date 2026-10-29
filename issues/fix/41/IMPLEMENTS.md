# RabbitMQ 로그 레벨 조정 구현

## 결과

사용자 제공 INFO 로그 4.252초 구간에서 RabbitMQ 로그 216건(전체 336건 중 64.3%)이 모두 `Connection`의 정상 연결 시도·성공·종료였습니다. 이 기록을 만드는 `Connection.connect()`의 시도 로그와 `Connection.observe()`의 성공 로그를 DEBUG로 낮췄습니다. 이어서 사용자 요청에 따라 `Consumer`의 생명주기 INFO 7곳도 DEBUG로 낮췄습니다.

- RabbitMQ 구현은 정상 동작을 INFO로 기록하지 않습니다. 작업마다 연결을 열고 닫아도 INFO가 늘지 않습니다.
- 큐·Exchange·Stream 선언·삭제·바인딩 성공 기록도 같은 `observe()` 경로이므로 DEBUG가 됩니다.
- Consumer 구독 적용·소비 루프 시작·중지·종료·채널 종료도 DEBUG입니다. Worker 생명주기 INFO는 `DefStream.Worker` 로거에 남습니다.
- 실패 시 ERROR 기록과 예외 전파, WARNING 정책은 그대로입니다.
- 로거 이름·전파·무설정 정책과 공개 API는 바뀌지 않습니다. Pika 로그는 다루지 않습니다.

상세 변경 내용은 [Connection 구현 기록](./implements/1793257519898.md)과 [Consumer 구현 기록](./implements/1793257826069.md)을 참고하세요.

## 검증

- RabbitMQ 테스트 52개 통과, opt-in 통합 테스트 3개 건너뜀
- 로깅 테스트 40개 통과
- 연결·종료 3회 반복 시 INFO 0건, DEBUG 9건
- Consumer 구독·소비·중지·종료 경로에서 INFO 이상 0건
- 전체 테스트는 UTF-8 콘솔에서 변경 전후 모두 실패 3, 건너뜀 15로 같습니다. 실패는 editable 설치 환경의 패키징 검사로 기존 문제입니다. Consumer 변경 후 첫 실행에서 한 번 나온 오류 1건은 이후 3회 실행에서 재현되지 않았습니다.

명령과 상세 결과는 [Connection 검증 기록](./tasks/1793257519899.md)과 [Consumer 구현 기록](./implements/1793257826069.md)에 있습니다. 실제 애플리케이션과 RabbitMQ 서버에서는 검증하지 않았습니다.

## 영향

INFO만 수집하던 환경에서는 RabbitMQ 연결·자원 선언·Consumer 생명주기 기록이 보이지 않습니다. 필요하면 `DefStream.Broker.RabbitMQ` 로거나 하위 로거를 DEBUG로 설정해 확인할 수 있습니다.

## 로거 이름 변경

사용자 요청에 따라 RabbitMQ 클래스 6개의 로거 이름을 `DefStream.Broker.Implements.RabbitMQ.ClassName`에서 `DefStream.Broker.RabbitMQ.ClassName`으로 바꿨습니다. 모듈·import 경로는 바꾸지 않았습니다. 이 이름을 쓰는 테스트·샘플 필터·매뉴얼(`docs/RabbitMQ*.md`, `docs/Operations*.md`)도 함께 고쳤습니다. 기존 이름으로 로거를 설정한 애플리케이션은 설정을 새 이름으로 바꿔야 합니다. Redis 로거 이름은 바꾸지 않았습니다.
