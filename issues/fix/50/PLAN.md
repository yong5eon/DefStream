# 작업 계획

## 대상과 순서

1. 완료: `src/Broker/Implements/RabbitMQ/Queue.py`에서 요청 큐 이름 기반 응답 큐를 선언했다.
2. 완료: `tests/test_rabbitmq_rpc.py`에 응답 큐 형식, 기존 선언 옵션과 `reply_to` 연결을 검증하는 회귀 테스트를 추가했다.
3. 완료: `docs/RabbitMQ.md`와 `docs/RabbitMQ.en.md`의 동기 RPC 설명을 함께 갱신했다.
4. 완료: RPC 테스트를 실행하고 결과를 기록했다.
5. 완료: 종합 문서, 단계별 기록과 `CHANGELOG.md`를 실제 결과에 맞춰 정리했다.

## 검증

- `tests/test_rabbitmq_rpc.py`의 Queue 및 Exchange RPC 테스트로 요청 큐 경로와 Exchange 제외 범위를 확인한다.
- RPC 테스트에서 응답 큐 이름 형식, exclusive·auto-delete 옵션, `reply_to` 연결 및 기존 성공·실패 처리를 확인한다.
- 문서 링크와 한국어·영어 동기화 여부를 확인한다.
