# 요구사항 명세서

## 분석 요약

- CI 실행 #41075016156의 `Test Python 3.9` 작업은 `actions/setup-python` 단계에서 실패했다. 로그는 `The version '3.9' with architecture 'x64' was not found for Ubuntu 26.04`라고 보고했고, 테스트 단계에는 도달하지 않았다.
- 현재 `.github/workflows/ci.yml`은 `test` 작업의 모든 Python 매트릭스 항목에 `ubuntu-latest`를 사용한다.
- 문제는 프로젝트의 Python 3.9 지원 선언이나 제품 코드가 아니라, 최신 Ubuntu 이미지에 Python 3.9 런타임이 준비되지 않은 CI 환경 조합이다.
- Python 3.9만 Ubuntu 24.04에서 실행하고 나머지 Python 버전은 현재 설정을 유지하면 최소 범위로 실패 원인을 회피할 수 있다.

## 확정 요구사항

- `test` 매트릭스의 Python 3.9 항목은 `ubuntu-24.04`에서 실행한다.
- Python 3.10 이상 항목은 `ubuntu-latest`에서 실행한다.
- Python 지원 범위, 패키지 메타데이터, 다른 작업의 러너 설정은 변경하지 않는다.

## 제외 범위

- Python 3.9 지원 중단 또는 `setup.py`의 Python 요구사항·분류자 변경
- `changes`, `publish` 등 Python 매트릭스 테스트 외 작업의 러너 변경
- 제품 코드 및 테스트 코드 변경

## 인수 기준

- 워크플로 매트릭스에서 Python 3.9은 `ubuntu-24.04`를 선택한다.
- Python 3.10, 3.11, 3.12, 3.13, 3.14는 `ubuntu-latest`를 선택한다.
- GitHub Actions에서 Python 3.9 테스트가 실제 시작하고, 관련 테스트 및 나머지 CI 결과를 확인한다.

## 검증 제약

마지막 인수 기준은 변경된 워크플로가 GitHub Actions에서 실행된 뒤에만 확정할 수 있다. 로컬에서는 YAML 구조와 매트릭스 매핑을 검토할 수 있지만, 로컬 정적 검증만으로 GitHub-hosted runner에서 실제 Python 설치 및 테스트 실행을 보증할 수 없다.
