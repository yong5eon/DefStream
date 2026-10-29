# RabbitMQ 작업 큐별 ACK 대기 한도 설정

장시간 작업에 맞춰 RabbitMQ의 ACK 대기 한도를 큐별로 지정할 수 있습니다. 전역 설정이나 완료 후 ACK 동작을 바꾸지 않고 `Subscription.timeout`으로 설정합니다.

```python
from datetime import timedelta

from DefStream.Broker.Implements.RabbitMQ import Subscription

subscription = Subscription(
  queue='etl.split',
  error='etl.split.error',
  timeout=timedelta(hours=24),
)
```

작업에 지정한 구독 설정으로 `declare()`를 호출하면 작업 큐에 `x-consumer-timeout=86400000`이 전달됩니다. 생략하거나 `None`을 지정하면 기존 동작을 유지합니다.

- `timeout=86400000`처럼 밀리초 단위의 양수 정수도 사용할 수 있습니다. `timedelta`는 생성 시 정수 밀리초로 정규화됩니다.
- `bool`·잘못된 타입·0·음수·밀리초 미만 정밀도는 오류로 처리합니다.
- 큐별 ACK timeout을 지원하는 RabbitMQ 3.12 이상이 필요합니다.
- 구독만으로 설정을 적용하지 않으며 기존 큐 변경·재생성·policy 적용은 운영 측 책임입니다.
- 작업 실행 제한 시간이나 RPC 응답 대기시간은 변경하지 않습니다.

구체적인 선언 예시는 [RabbitMQ 매뉴얼](../../../docs/RabbitMQ.md#장시간-작업의-ack-대기-한도)을 참고하세요.
