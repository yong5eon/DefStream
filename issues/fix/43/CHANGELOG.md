# 로그 이름 계층 정리

RabbitMQ와 Redis 로그 이름은 각각 `Broker.RabbitMQ.<클래스명>`과 `Broker.Redis.<클래스명>`으로 변경했습니다. Worker 로거는 `Worker`, 작업 실행 로그는 `Task`, 풀·실행기 로거는 `Worker` 계층을 사용합니다. Inspector 확장 로그는 `Worker.Inspector.<확장 이름>`으로 구분됩니다.

기존 `DefStream.*` 이름으로 구성한 Broker·Worker·Inspector 로그 필터·핸들러는 새 이름 계층에 맞춰 갱신해야 합니다. 제품 모듈 import 경로와 공개 API는 변경되지 않았습니다.
