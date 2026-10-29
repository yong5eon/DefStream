# 요구사항

## 분석

- 현재 `Queue.call()`은 RabbitMQ에 빈 큐 이름을 전달해 `amq.gen-*` 임시 응답 큐를 생성한다. 큐 이름만으로는 요청 큐를 식별하기 어렵다.
- `RabbitMQ.Connection.request()`는 `Queue.call()`에 위임하므로 해당 경로도 같은 응답 큐 이름 규칙을 사용해야 한다.
- `Exchange.call()`은 특정 요청 큐를 대상으로 하지 않으며 이 변경 범위에서 제외한다.
- 기존 응답 큐 수명과 RPC 상관관계 계약은 변경하지 않는다.

## 확정 요구사항

1. 요청 큐 기반 RPC의 임시 응답 큐 이름을 `{요청 큐 이름}.{uuid4().hex}` 형식으로 생성한다.
2. 응답 큐를 exclusive 및 auto-delete로 선언하는 기존 동작을 유지한다.
3. 요청의 `reply_to`는 생성한 응답 큐를 가리키고, `correlation_id` 기반 응답 일치 처리는 유지한다.
4. Exchange RPC의 임시 응답 큐 이름과 동작은 변경하지 않는다.
5. RabbitMQ 상세 매뉴얼의 한국어·영어 설명을 일치시켜 갱신한다.

## 인수 기준

- `Queue.call()`이 요청 큐 이름 뒤에 32자리 소문자 16진수 UUID를 붙여 응답 큐를 선언한다.
- 선언된 큐가 `exclusive=True`, `auto_delete=True`이고 요청의 `reply_to`에 사용된다.
- 기존 RPC 성공·오류·타임아웃 및 상관관계 테스트가 유지된다.
- Exchange RPC 동작은 변경되지 않는다.
