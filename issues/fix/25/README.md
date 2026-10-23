# RabbitMQ·Redis 브로커 통합

## 하나의 패키지로 설치

RabbitMQ와 Redis 구현체를 DefStream 배포 패키지에 함께 포함합니다. 본체와 어댑터의 버전을 별도로 맞출 필요 없이 하나의 DefStream 버전으로 사용합니다.

필요한 브로커 클라이언트만 선택해서 설치하세요.

```shell
python -m pip install "DefStream[RabbitMQ]"
python -m pip install "DefStream[Redis]"
python -m pip install "DefStream[RabbitMQ,Redis]"
```

기본 `DefStream` 설치는 브로커 클라이언트를 필수로 설치하지 않습니다. 공개 import 경로는 `DefStream.Broker.Implements.RabbitMQ` 및 `DefStream.Broker.Implements.Redis`를 유지합니다.

## 기존 어댑터 패키지 사용 시 주의사항

`DefStream-RabbitMQ`와 `DefStream-Redis`의 별도 배포는 종료하며, 기존 프로젝트는 삭제 예정입니다. 기존 패키지에 대한 하위 호환성은 지원하지 않습니다.

가급적 새 가상환경에 통합 패키지를 설치하세요. 기존 환경을 전환한다면 공유 경로의 파일이 삭제될 수 있으므로 기존 어댑터를 먼저 제거하고 DefStream을 재설치해야 합니다.

```shell
python -m pip uninstall DefStream-RabbitMQ DefStream-Redis
python -m pip install --force-reinstall "DefStream[RabbitMQ,Redis]"
```

실제로 사용하는 브로커에 맞게 extra를 선택하세요. 기존 별도 어댑터 패키지와 통합 DefStream을 함께 설치하지 마세요.

## 사용 안내와 샘플

브로커별 연결 설정, 송수신, Worker 연동, 운영 제약은 [한국어 사용 안내](../../../README.md)와 [영어 사용 안내](../../../README.en.md)에서 확인할 수 있습니다.

- [RabbitMQ 브로커 샘플](../../../samples/Broker/RabbitMQ)
- [Redis 브로커 샘플](../../../samples/Broker/Redis)
- [요구사항](./REQUIREMENTS.md)
- [상세 구현](./IMPLEMENTS.md)
- [분석 및 검증 기록](./TASK.md)
