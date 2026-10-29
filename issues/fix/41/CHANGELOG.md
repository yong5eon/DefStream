# 변경 사항

## 동작 변경

RabbitMQ 연결을 자주 열고 닫는 애플리케이션에서 INFO 로그가 RabbitMQ 기록으로 가득 차던 문제를 줄였습니다.

- 변경 전: `Connection`의 정상 연결 시도·성공·종료와 큐·Exchange·Stream 선언·삭제·바인딩 성공, `Consumer`의 구독 적용·소비 루프 시작·중지·종료·채널 종료가 INFO로 기록되었습니다. 작업마다 연결을 열면 연결 한 번에 INFO 세 건이 쌓였습니다.
- 변경 후: RabbitMQ 구현의 정상 동작 기록은 모두 DEBUG로 남습니다. Worker 시작·준비·종료는 계속 `DefStream.Worker` 로거의 INFO로 확인할 수 있습니다.
- 연결·자원 작업 실패는 계속 ERROR로 기록되고 예외도 그대로 전달됩니다. RPC 시간 초과 등 주의할 사건의 WARNING도 유지됩니다.

RabbitMQ 기록이 필요하면 해당 로거만 DEBUG로 설정하세요.

```python
from logging import DEBUG, getLogger

getLogger('DefStream.Broker.RabbitMQ').setLevel(DEBUG)
```

로거 이름이 `DefStream.Broker.Implements.RabbitMQ.*`에서 `DefStream.Broker.RabbitMQ.*`로 바뀌었습니다. 기존 이름으로 레벨·핸들러·필터를 설정했다면 새 이름으로 변경하세요. import 경로 `DefStream.Broker.Implements.RabbitMQ`는 그대로입니다.

핸들러 레벨이 INFO이면 DEBUG 기록이 출력되지 않으므로 핸들러 레벨도 함께 확인하세요.
