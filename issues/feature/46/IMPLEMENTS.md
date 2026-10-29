# Worker 내부 소비 복구 구현 결과

## 동작과 변경 이유

이전에는 RabbitMQ 소비 루프가 끝나면 Worker가 최종 정리로 진입하고 `Pool.stop()`의 무기한 대기 때문에 소비만 멈춘 채 프로세스가 남을 수 있었습니다. 이제 RabbitMQ 소비 장애를 정상 stop과 구분하고 Worker 안에서 실행기·연결·구독을 복구합니다.

- `src/Worker/Worker.py`: keyword-only `recovery_attempts=5`, `recovery_interval=60`을 추가했습니다. 첫 복구는 즉시 시도하며 실패한 시도 사이에만 대기합니다. 전체 구독 복구 성공 시 다음 장애의 한도를 초기화합니다. 복구 중 준비 상태를 해제하고 최종 실패는 이전 작업 완료를 기다리지 않고 전파합니다.
- `src/Worker/Pool.py`: 기존 Pool 객체를 유지하는 `restart()`와 장애용 `stop(abort=True)`를 추가했습니다. 이전 Future·슬롯을 별도 세대로 유지해 늦은 콜백이 새 실행기를 오염시키지 않게 했습니다.
- `src/Worker/Executor.py`: 공개 multiprocessing Process API로 실행 프로세스를 소유·추적하여 사설 executor 속성 없이 강제 종료합니다. ThreadPool은 이전 작업을 기다리지 않고 폐기 경로를 반환하되 작업 완료 후 실행 스레드·monitor가 정리됩니다. setup·cleanup 오류는 부모 Future와 종료 경로로 전파합니다.
- `src/Broker/Protocol.py`의 `Recoverable`을 공개하고 Worker가 `isinstance(consumer, Recoverable)`로 지원 여부를 판별합니다. 별도 지원 플래그와 기본 Consumer의 `recoverable()`은 제거하여 비지원 Consumer의 기존 동작을 유지했습니다. RabbitMQ `Consumer.py`에 예상치 못한 소비 루프 종료, 주기적 이벤트 깨우기, ACK timeout 진단과 오류 분류를 추가했습니다. 연결 재생성은 Worker가 기존 브로커의 close/connect를 호출하므로 Connection·Event의 구현 변경은 필요하지 않았습니다.
- 이전 작업은 세대 검사로 정산·RPC 응답·새 pending·Inspector 상태에서 격리합니다. 이전 미완료 Inspector context는 폐기 상태로 마무리합니다.

## 유지한 계약과 제한

정상 stop의 graceful drain, 정상 ACK·오류 정책·RPC, 명시적 큐 선언, Redis 동작은 유지합니다. 사용자 지정 executor를 사용하는 Pool은 복구를 지원하지 않으며 명시적 오류를 냅니다. 초기 연결·구독 오류는 즉시 전파합니다.

기존 ThreadPool 작업은 강제 종료하지 않습니다. 완료 후 정리되지만 무한 대기 작업은 남을 수 있고, 재전달 작업과의 중복 실행 및 외부 부작용은 사용자 측 멱등성으로 다뤄야 합니다. Worker 실패 전파가 Python 프로세스의 강제 종료를 보장하지는 않습니다. 강제 종료한 ProcessPool 작업의 cleanup 실행도 보장하지 않습니다.

## 문서 및 검증

한국어·영어 RabbitMQ·생명주기·운영 매뉴얼을 갱신했습니다. 최종 기능 회귀는 294개 중 279개 통과·15개 생략이며, 패키징 환경 검사와 실제 브로커 검증의 제한은 [최종 검증 기록](./tasks/1793275501812.md)에 정리했습니다. 커밋·푸시·PR 생성은 수행하지 않았습니다.

## 구현 기록

- [실행기 세대 교체와 Worker 복구](./implements/1793274693488.md)
- [훅 오류 전파 및 매뉴얼 반영](./implements/1793275218996.md)
- [복구 지원 Protocol 전환](./implements/1793275899489.md)
- [복구 가능 판별 메서드 이름 변경](./implements/1793276075771.md)
