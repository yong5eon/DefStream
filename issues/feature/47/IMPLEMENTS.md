# Subscription timeout 구현 결과

[요구사항](./REQUIREMENTS.md)과 [계획](./PLAN.md)에 따라 RabbitMQ 구독 설정의 timeout을 작업 큐 선언에 전달하도록 구현했습니다.

## 주요 변경과 유지한 계약

- [Subscription](../../../src/Broker/Implements/RabbitMQ/Subscription.py)에 마지막 선택 필드 `timeout: Optional[Union[int, timedelta]] = None`을 추가했습니다. 기존 위치 인자는 유지하며 객체와 Mapping으로 지정할 수 있습니다.
- 밀리초 단위의 양수 `int`와 정수 밀리초 정밀도의 양수 `timedelta`를 허용합니다. `bool`·잘못된 타입은 `TypeError`, 0·음수·밀리초 미만 정밀도는 `ValueError`로 처리합니다.
- 구독 생성 시 부동소수점 없이 정수 밀리초로 정규화합니다. [Connection.declare](../../../src/Broker/Implements/RabbitMQ/Connection.py)는 해당 값을 작업 큐의 `x-consumer-timeout`에만 전달하며 생략·`None`이면 기존 인자 구성을 유지합니다.
- DLQ·최대 우선순위·durable 선언은 함께 유지합니다. 오류 큐에 timeout을 전파하지 않으며 Consumer·Worker·Redis 및 ACK·실패 정책은 변경하지 않았습니다.
- 한국어·영어 RabbitMQ 매뉴얼을 갱신했습니다. 기존 큐 변경이나 운영 조치를 자동 수행하지 않습니다.

## 검증과 제한

새 timeout 테스트 9개를 포함해 관련 테스트 92개 중 88개가 통과하고 4개가 생략됐습니다. 변경한 Python 파일의 Pylance 진단은 없고, 양쪽 매뉴얼 예제의 설정 생성도 확인했습니다. 정수 입력·정규화 변경 후 재검증 결과는 [최신 검증 기록](./tasks/1793272077066.md), 최초 검증의 환경 제한은 [기존 검증 기록](./tasks/1793271819682.md)을 참고하세요.

전체 테스트 스위트와 실제 RabbitMQ 운영 환경·기존 큐 변경은 검증하지 않았습니다. 요청 범위의 미구현 사항은 없습니다. 커밋·푸시·PR 생성은 수행하지 않았습니다.

## 구현 기록

- [timeout의 큐 선언 전달](./implements/1793271568985.md)
- [정수 밀리초 입력과 정규화](./implements/1793272077065.md)
