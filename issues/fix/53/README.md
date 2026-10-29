# 선택 구현체 배포 분리 및 extras 설치 격리

- 원본: [DefStream #53](https://github.com/yong5eon/DefStream/issues/53)
- 제목: 단일 src·setup.py를 유지하는 선택 구현체 배포 분리 및 extras 설치 격리
- 유형·레이블: `fix` (원본 적용 확인)
- 대상 저장소: DefStream
- 작업 브랜치: `fix/53`
- 분기 기준·병합 대상: 사용자 확인에 따른 `master`
- [요구사항](./REQUIREMENTS.md) · [계획](./PLAN.md)
- [구현 결과](./IMPLEMENTS.md) · [작업·검증 결과](./TASKS.md) · [변경 로그](./CHANGELOG.md)
- 최신 [구현 기록](./implements/1793301829543.md) · [검증 기록](./tasks/1793301829546.md)
- 상태: EXTRAS 단일 editable과 승인된 개발 환경 전환·검증 완료, 외부 서비스·원격 CI·게시 권한 검증은 미수행

## 원본 이슈 본문

```text
# 단일 src·setup.py를 유지하면서 선택 구현체의 설치 격리

## 목표와 현재 문제

현재 `setup.py`는 `find_packages('src')`로 모든 하위 패키지를 포함한다. `RabbitMQ`, `Redis` extras는 외부 의존성만 선택하므로, 선택하지 않은 브로커 어댑터 코드도 기본 배포 패키지에 포함된다.

선택하지 않은 구현체는 설치 파일 자체에 포함되지 않도록 배포 경계를 분리한다. 단순히 import를 막거나 외부 의존성만 제외하는 것으로 대체하지 않는다.

## 요구사항

- 같은 저장소, 하나의 `src`, 하나의 `setup.py`를 유지한다.
- 기존 `DefStream[...]` 설치 인터페이스와 선택한 구현체의 import 경로를 유지한다.
- 표준 pip와 사전 빌드 wheel 설치에서도 동일한 격리를 제공한다.
- 코어의 기본 API와 선택한 구현체의 기존 동작을 유지한다.

새로운 격리 환경에서 기대하는 설치 결과는 다음과 같다.

| 설치 명령 | 포함할 브로커 구현체 |
| --- | --- |
| `pip install DefStream` | 없음 |
| `pip install "DefStream[RabbitMQ]"` | RabbitMQ만 |
| `pip install "DefStream[Redis]"` | Redis만 |
| `pip install "DefStream[RabbitMQ,Redis]"` | RabbitMQ와 Redis |

이미 설치한 extra를 다른 설치 명령에서 생략한다고 자동 제거되는 동작은 요구하지 않는다.

## 사전 조사 결과

- extras는 추가 의존성을 선언하는 기능이며, 동일 wheel 안의 파일을 선택적으로 설치하는 기능은 아니다.
- PEP 517 빌드 인터페이스에는 사용자가 선택한 extras를 전달하는 표준 인자가 없다. `config_settings`로 명시적인 빌드 설정을 전달하는 것과 설치 시 extras를 자동 감지하는 것은 별개이다.
- wheel 설치에서는 `setup.py`가 실행되지 않는다. 따라서 설치 시 `setup.py`에서 extras를 감지하여 파일을 제외하는 접근은 채택하지 않는다.
- 별도 최소 재현 패키지를 Python 3.15.0, pip 26.2.2, setuptools 84.0.0에서 검사했다. 기본 설치와 `[feature]`의 소스 빌드 모두 `setup.py` 인자에 extra가 없었고, 생성된 wheel의 파일 목록과 내용이 같았다. 동일 wheel을 두 방식으로 설치했을 때 모두 선택 구현체가 포함됐으며, 설치 중 `setup.py` 실행은 없었다.
- 이 검증은 extras의 동작 확인이며, 아래 다중 배포 설계를 실제 프로젝트에서 검증한 결과는 아니다.

## 제안하는 구현 방향

단일 소스를 공유하되, 배포 전에 빌드 대상을 명시하여 같은 `setup.py`로 코어와 구현체별 배포물을 각각 만든다.

| 배포 이름 예시 | 포함 범위 |
| --- | --- |
| `DefStream` | 공통 코드, 선택 브로커 어댑터 제외 |
| `DefStream-RabbitMQ` | `DefStream.Broker.Implements.RabbitMQ` 하위 코드와 필요한 리소스 |
| `DefStream-Redis` | `DefStream.Broker.Implements.Redis` 하위 코드와 필요한 리소스 |

코어의 extras는 해당 구현체 배포 패키지를 의존성으로 연결한다. 구현체 패키지는 호환되는 코어와 자신의 외부 의존성에 의존한다. 최종 배포 이름, 버전 결합 정책과 빌드 대상 전달 방법은 구현 전에 확정한다.

공통 부모의 `__init__.py`는 코어만 소유하고 구현체 배포물은 자신의 하위 파일만 소유하도록 한다. 같은 설치 파일을 여러 wheel의 `RECORD`에 중복 등록하지 않는다. 저장소나 소스 디렉터리를 구현체별로 나누는 것은 요구하지 않는다.

## 구현 시 확인할 사항

- 빌드 대상별 패키지 선택, 리소스 포함 및 빌드 잔여물 혼입 방지
- sdist를 제공한다면 각 sdist의 독립 재빌드 시 배포 이름·대상·메타데이터 재현
- 표준 빌드 도구에서의 동작, wheel 캐시와 배포 대상 구분
- 구현체별 코어 의존성, 릴리즈 순서와 배포 자동화
- 기존 단일 배포 버전에서 업그레이드할 때 파일 소유권 변경과 안전한 전환 안내
- 설치 문서, 한국어·영어 README 및 관련 테스트 갱신

## 완료 기준

- [ ] 단일 `src`와 단일 `setup.py`로 각 배포물을 재현 가능하게 빌드한다.
- [ ] 네 가지 설치 조합을 각각 깨끗한 환경에서 검사하고, 선택하지 않은 어댑터 파일과 해당 배포 패키지가 없음을 확인한다.
- [ ] 코어 API 및 선택한 어댑터의 기존 import 경로와 기능을 검증한다.
- [ ] 코어와 구현체 wheel 간 설치 파일 소유권이 중복되지 않음을 확인한다.
- [ ] 사전 빌드 wheel 설치와 제공하는 sdist의 재빌드를 검증한다.
- [ ] 추가 extra 설치, 업그레이드 및 구현체 패키지 제거가 다른 설치 구성요소를 손상시키지 않음을 검증한다.
- [ ] 지원 Python 범위, 필요한 외부 의존성과 설치·전환 문서를 확인한다.

## 참고

- [extras 명세](https://packaging.python.org/en/latest/specifications/dependency-specifiers/#extras)
- [PEP 517 빌드 인터페이스](https://peps.python.org/pep-0517/#build-backend-interface)
- [pip wheel 캐시](https://pip.pypa.io/en/stable/topics/caching/#locally-built-wheels)

```
