# 설치 격리와 개발·배포

[English](./Packaging.en.md) · [매뉴얼 목차](./README.md)

## 무엇이 설치되는가

`DefStream` 코어에는 브로커 구현체가 없습니다. `RabbitMQ`와 `Redis` extras는 각각 동일 버전 `DefStream-RabbitMQ`, `DefStream-Redis` 배포물과 외부 클라이언트를 설치합니다. 기존 Python import 경로는 유지합니다.

새 환경에서는 선택하지 않은 구현체 파일과 클라이언트가 설치되지 않습니다. 나중에 extra를 생략해도 이미 설치한 구현체는 제거되지 않으므로 필요 없다면 해당 구현체 배포물을 명시적으로 제거하세요.

```mermaid
flowchart LR
  A["DefStream[Redis] 설치"] --> B["코어"]
  A --> C["동일 버전 Redis 구현체"]
  C --> D["redis 클라이언트"]
```

## 기존 환경 전환

기존 통합 배포나 과거 별도 어댑터는 같은 import 경로의 파일을 제공할 수 있습니다. 새 가상환경을 권장합니다. 기존 환경에서는 모두 제거한 뒤 실제 사용하는 extras를 선택하여 파일 소유권 충돌을 피하세요.

```shell
python -m pip uninstall DefStream DefStream-RabbitMQ DefStream-Redis
python -m pip install "DefStream[RabbitMQ,Redis]"
python -m pip check
```

새 구현체 배포물은 같은 저장소·버전으로 코어와 함께 관리합니다. 이전 버전으로 되돌릴 때도 새 배포물을 먼저 제거하고 사용하던 버전을 명시하여 재설치합니다.

## 로컬 editable 개발

저장소 루트의 개발용 가상환경에서 실행하세요. 정션·심볼릭 링크를 직접 만들 필요가 없습니다. 명령마다 현재 로컬 소스로 코어와 선택 구현체의 메타데이터·연결을 갱신합니다.

```shell
python -m pip install -e .
```

옵션을 생략하면 이전 선택도 해제하여 코어만 남깁니다. 구현체를 함께 개발하려면 같은 명령에 `EXTRAS`를 지정하세요. Windows와 POSIX 셸에서 동일합니다.

```shell
python -m pip install -e . --config-settings EXTRAS=Redis
python -m pip install -e . --config-settings EXTRAS=RabbitMQ,Redis
```

각 명령은 누적이 아니라 지정한 목록으로 교체합니다. 이름은 대소문자를 구분하지 않으며 잘못된 이름은 오류입니다. 남아 있는 `DEF_BUILD_TARGET`은 editable에서 무시합니다. 원격 소스를 가져오거나 외부 라이브러리를 강제 업그레이드하지는 않으며, 선택에서 빠진 외부 라이브러리는 자동 삭제하지 않습니다.

이전 코어·구현체 분리 editable 또는 일반 설치에서 처음 전환할 때는 기존 배포물을 한 번 제거한 뒤 위 명령으로 설치하세요. 새 editable은 코어 배포물 하나가 선택 코드를 소유하므로 별도 구현체 배포물과 섞으면 오류가 발생합니다.

```shell
python -m pip uninstall DefStream DefStream-RabbitMQ DefStream-Redis
python -m pip install -e . --config-settings EXTRAS=RabbitMQ,Redis
python -m pip check
```

editable 설치는 가상환경의 `site-packages/__editable_defstream_view/`에 코어와 설치된 구현체의 파일만 링크하고, 이 경로를 `.pth`에 기록합니다. IDE는 import hook 없이 같은 파일 트리를 탐색할 수 있습니다. Python 시작 시 설치 메타데이터와 링크 상태를 확인하고 변경된 구성을 반영합니다. 두 가상환경이 같은 소스를 사용해도 선택 구성은 섞이지 않습니다.

코어를 먼저 별도로 설치할 필요가 없습니다. 새 파일 추가나 패키지 구성 변경 후에는 원하는 `EXTRAS`를 포함해 같은 명령을 다시 실행하세요. 링크 트리는 자동 관리되며 `build/`에 의존하지 않습니다. Windows에서는 파일 심볼릭 링크를 우선 사용하고 권한이 없으면 하드 링크를 사용합니다. 후자는 소스와 가상환경이 같은 볼륨에 있어야 합니다.

`pip install -e ".[Redis]"`의 표준 extras는 외부 의존성만 선택하므로 구현체 코드 선택에는 반드시 `--config-settings EXTRAS=Redis`를 사용하세요. 일반 배포의 `pip install "DefStream[Redis]"`는 기존대로 별도 구현체 wheel을 설치합니다.

전환 후 Language Server를 재시작하세요. IDE 전용 검색 경로나 경고 숨김은 필요하지 않습니다. 일반 wheel 설치에는 링크 관리 코드가 포함되지 않습니다. `pyproject.toml`의 로컬 백엔드는 editable 훅의 `EXTRAS`만 해석하며 pip를 중첩 호출하거나 가상환경을 직접 수정하지 않습니다.

## 빌드와 검증

하나의 `src`와 `setup.py`를 공유하며 `DEF_BUILD_TARGET`은 `core`(기본값), `RabbitMQ`, `Redis`입니다. 잘못된 값은 오류입니다.

저장소 루트에서 전체 배포물을 빌드·검사합니다.

```shell
python -m pip install "pip>=23" build "setuptools>=77" "setuptools-scm>=8,<10" wheel twine
python scripts/build_distributions.py
python scripts/check_distributions.py --editable
python -m twine check --strict dist/*
```

빌드 스크립트는 버전을 고정하고 대상별 wheel과 sdist를 `dist/`에 만듭니다. 다른 버전 산출물이 섞이지 않은 디렉터리를 사용하세요. `--outdir`로 다른 위치를, `--wheel`로 wheel 전용 빌드를 선택할 수 있습니다.

각 sdist에는 `.distribution-target`이 포함되어 별도 환경변수 없이 `python -m build`로 같은 배포물을 재생성합니다. sdist의 대상 변경은 거부합니다.

sdist는 공통 소스 트리를 포함합니다. 선택하지 않은 구현체의 파일을 제외하는 경계는 빌드된 wheel과 최종 설치 파일이며, sdist 원본 소스의 배포까지 분리하는 구조는 아닙니다.

CI는 지원 Python별 빌드·설치 격리를 검사하며, 릴리즈에서 이름·버전·빌드 번호를 확인하고 구현체를 먼저, 코어를 나중에 게시합니다. PyPI 게시 권한과 토큰은 세 배포 이름을 지원해야 합니다. 로컬 빌드만으로 게시하지는 않습니다.
