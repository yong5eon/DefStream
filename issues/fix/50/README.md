# RPC 임시 응답 큐 이름을 요청 큐 기반으로 생성

## 이슈와 작업 정보

- 원본 이슈: [#50](https://github.com/yong5eon/DefStream/issues/50)
- 상태: Open
- 유형: `fix` (원본 레이블에 적용됨)
- 추가 레이블: `rabbitmq`
- 저장소: `yong5eon/DefStream`
- 작업 브랜치: `fix/50`
- 분기 기준: `master` (`origin/master`와 동일)
- 요구사항: [REQUIREMENTS.md](./REQUIREMENTS.md)
- 계획: [PLAN.md](./PLAN.md)
- 구현 종합: [IMPLEMENTS.md](./IMPLEMENTS.md)
- 작업·검증 종합: [TASKS.md](./TASKS.md)
- 변경 로그: [CHANGELOG.md](./CHANGELOG.md)
- 최신 구현 기록: [1793282630353.md](./implements/1793282630353.md)
- 최신 작업 기록: [1793282630354.md](./tasks/1793282630354.md)

## 이슈 원문

### 해결하려는 문제

RabbitMQ RPC가 요청마다 RabbitMQ 자동 생성 이름(`amq.gen-*`)의 임시 응답 큐를 사용해 큐 이름만으로는 어떤 요청 큐의 응답인지 알아보기 어렵습니다.

### 제안하는 해결 방법

`Queue.call()`을 포함해 요청 큐를 대상으로 하는 RPC에서 임시 응답 큐 이름을 `{요청큐}.{uuid4().hex}` 형식으로 생성합니다. 예를 들어 요청 큐가 `orders`이면 응답 큐 이름은 `orders.0123456789abcdef...` 형태입니다. 응답 큐의 exclusive·auto-delete 동작과 요청의 `reply_to`/`correlation_id` 처리 방식은 유지합니다.

### 고려한 대안

RabbitMQ가 생성하는 기본 임시 큐 이름(`amq.gen-*`)을 그대로 사용합니다.

### 추가 정보

Exchange RPC는 특정 요청 큐 이름을 대상으로 하지 않으므로 이번 요청 큐 기반 이름 규칙의 범위에 포함하지 않습니다.
