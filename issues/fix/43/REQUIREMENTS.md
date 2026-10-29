# 로거 이름 변경 요구사항

## 분석

이슈는 로그 이름이 길어 가독성이 떨어지는 문제를 제기하고, `DefStream.` 프리픽스와 브로커 구현체의 `Implements.`를 제거하도록 제안합니다. 이슈 댓글은 없습니다.

현재 브로커 구현 로거는 클래스별 이름을 사용합니다. RabbitMQ는 `DefStream.Broker.RabbitMQ.<클래스명>`, Redis는 `DefStream.Broker.Implements.Redis.<클래스명>`입니다. Worker 로거도 `DefStream.Worker`, `DefStream.Run`, `DefStream.Executor`, `DefStream.Pool` 등의 이름을 사용하며 Inspector는 `DefStream.Inspector` 및 그 하위 이름을 사용합니다.

로거 이름은 Python 표준 `logging`의 계층과 필터링에 쓰이며 현재 테스트·샘플·매뉴얼도 기존 이름을 기준으로 합니다. 요구된 이름으로 바꾸면 Worker와 Inspector의 로그는 `Worker` 계층, RabbitMQ와 Redis 로그는 각각 `Broker` 계층으로 분리됩니다. Descriptor와 Validator에는 현재 로거 선언이 없어 이름 변경 대상이 아닙니다. 제품·문서의 공개 import 경로는 로거 이름과 별개이므로 유지합니다.

## 확정 요구사항

### 목적과 범위

- Worker 및 Inspector 로그 이름에서 `DefStream.` 접두사를 제거하고, RabbitMQ 및 Redis 브로커 로그 이름도 짧게 하여 체계별 독립 계층을 사용합니다.
- RabbitMQ·Redis 클래스별 로거 이름은 어댑터 및 클래스별 구분을 유지합니다.
- Worker 클래스 로거 이름에서 `DefStream.`을 `Worker.`로 바꿉니다.
- Inspector·Server·RequestHandler 및 Inspector 확장 로거는 `Worker.Inspector` 계층을 사용합니다.
- Descriptor와 Validator는 로거를 사용하지 않으므로 이번 변경 대상에서 제외합니다.

### 요구 동작

- RabbitMQ 구현체의 클래스별 로거 이름은 `Broker.RabbitMQ.<클래스명>` 형식을 사용합니다.
- Redis 구현체의 클래스별 로거 이름은 `Broker.Redis.<클래스명>` 형식을 사용합니다.
- Worker 로거는 `Worker`, Run 로거는 `Task`를 사용하고, Executor·Pool·ThreadPool·ProcessPool 로거는 각각 `Worker.Executor`, `Worker.Pool`, `Worker.ThreadPool`, `Worker.ProcessPool`을 사용합니다.
- Inspector·Server·RequestHandler 로거는 `Worker.Inspector`, 확장 로거는 `Worker.Inspector.<클래스명>`을 사용합니다.
- 로거 이름 변경 외의 로깅 동작은 유지합니다. 로그 레벨, 메시지, 전파, 핸들러·필터 설정, 민감정보 비노출 및 예외 전파 동작은 이슈 범위에 없으므로 변경하지 않습니다.
- 구현체의 모듈 경로, 공개 import 경로와 API는 유지합니다.
- 테스트·샘플·한국어·영어 매뉴얼에서 변경된 로거 계층을 사용하도록 갱신합니다.

### 호환성과 제약

- 애플리케이션이 기존 `DefStream.Broker.RabbitMQ` 또는 `DefStream.Broker.Implements.Redis` 이름을 지정해 구성한 로거 필터·핸들러는 새 이름에 자동으로 적용되지 않습니다. 사용자는 각 어댑터의 새 로거 이름에 맞춰 설정을 갱신해야 합니다.
- 애플리케이션이 기존 `DefStream.Worker`, `DefStream.Run`, `DefStream.Executor`, `DefStream.Pool`, `DefStream.ThreadPool`, `DefStream.ProcessPool` 또는 `DefStream.Inspector` 계층을 지정해 설정했다면 각각 `Worker`, `Task`, `Worker.*` 또는 `Worker.Inspector` 이름에 맞춰야 합니다.
- 브로커·Worker·Inspector의 모듈 import 이름은 변경하지 않습니다.

## 인수 기준

| ID | 인수 기준 |
| --- | --- |
| AC-01 | RabbitMQ의 각 브로커 구현 로거 이름이 `Broker.RabbitMQ.<클래스명>`이고 `DefStream.`을 포함하지 않는다. |
| AC-02 | Redis의 각 브로커 구현 로거 이름이 `Broker.Redis.<클래스명>`이고 `DefStream.` 및 `Implements.`를 포함하지 않는다. |
| AC-03 | 브로커 로그는 해당 어댑터의 새 상위 로거와 루트 로거로 계속 전파되고, 로그 이름으로 필터링·캡처할 수 있다. |
| AC-04 | Worker 로거가 `Worker`, Run 로거가 `Task`, Executor·Pool 계열 로거가 `Worker.<클래스명>`을 사용하고, 풀 하위 클래스의 기본 이름 상속 동작을 유지한다. |
| AC-05 | Inspector·Server·RequestHandler 로거가 `Worker.Inspector`, Inspector 확장 로거가 `Worker.Inspector.<클래스명>`을 사용하고 새 상위 이름과 루트로 전파된다. |
| AC-06 | Descriptor·Validator는 로거 이름 변경이 없고, 모든 대상의 모듈 import 경로와 공개 API가 유지된다. |
| AC-07 | 관련 로깅 테스트가 통과하고 샘플·한국어·영어 매뉴얼이 새 이름 및 기존 사용자 설정의 갱신 필요성을 설명한다. |

## 근거와 검증 대상

- RabbitMQ 로거 선언: [Connection.py](../../../src/Broker/Implements/RabbitMQ/Connection.py), [Consumer.py](../../../src/Broker/Implements/RabbitMQ/Consumer.py), [Queue.py](../../../src/Broker/Implements/RabbitMQ/Queue.py), [Exchange.py](../../../src/Broker/Implements/RabbitMQ/Exchange.py), [Stream.py](../../../src/Broker/Implements/RabbitMQ/Stream.py), [Event.py](../../../src/Broker/Implements/RabbitMQ/Event.py)
- Redis 로거 선언: [Connection.py](../../../src/Broker/Implements/Redis/Connection.py), [Consumer.py](../../../src/Broker/Implements/Redis/Consumer.py), [Queue.py](../../../src/Broker/Implements/Redis/Queue.py), [Event.py](../../../src/Broker/Implements/Redis/Event.py)
- 기존 로거 이름 및 로그 동작 테스트: [test_rabbitmq_logging.py](../../../tests/test_rabbitmq_logging.py), [test_redis_logging.py](../../../tests/test_redis_logging.py), [test_logging.py](../../../tests/test_logging.py)
- Worker·Inspector 로거 선언 및 테스트: [Worker.py](../../../src/Worker/Worker.py), [Run.py](../../../src/Worker/Run.py), [Pool.py](../../../src/Worker/Pool.py), [Executor.py](../../../src/Worker/Executor.py), [Inspector.py](../../../src/Inspector/Inspector.py), [test_logging.py](../../../tests/test_logging.py), [test_inspector_logging.py](../../../tests/test_inspector_logging.py)
- 로깅 안내: [Operations.md](../../../docs/Operations.md), [Operations.en.md](../../../docs/Operations.en.md), [RabbitMQ.md](../../../docs/RabbitMQ.md), [RabbitMQ.en.md](../../../docs/RabbitMQ.en.md), [Redis.md](../../../docs/Redis.md), [Redis.en.md](../../../docs/Redis.en.md)

## 확인된 미확정 사항

- 없음. 이슈의 접두사 제거 제안을 기준으로 새 로거 이름을 명시했습니다.
