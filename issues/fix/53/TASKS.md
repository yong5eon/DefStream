# 작업 결과

## 로컬 검증

후속 EXTRAS 단일 editable은 Python 3.9에서 빌드·독립 sdist·선택 교체·생략·로컬 버전 갱신·오류 입력 후 기존 선택 보존·두 환경 격리를 통과했다. 패키징 단위 테스트 19개와 타입 검사도 통과했다. 제품 패키징 테스트는 일반 wheel과 editable에서 각각 4개 통과했다. 사용자 승인으로 Python 3.13 공용 개발 환경을 기존 RabbitMQ/Redis 선택을 유지해 전환했고 실제 import·정적 경로 탐색·의존성을 확인했다. [상세 검증](./tasks/1793301829546.md).

아래 표는 앞선 일반 배포·제품 테스트 결과이며 이번 후속 작업에서 제품 전체 테스트를 반복하지는 않았다.

| 검증 | 결과 |
| --- | --- |
| Python 3.9·3.13 대상별 wheel/sdist | 각 버전에서 3개씩 빌드 성공 |
| 네 설치 조합·파일 소유권·독립 sdist 재빌드 | 통과 |
| 추가 extra·동일 버전 재설치·구현체 제거 | 통과 |
| editable 격리·기존 소스 반영·새 코어 파일 재설치 | 통과 |
| 기존 제품 unittest, Python 3.13 | UTF-8 환경에서 311개 실행, 통과(15개 건너뜀) |
| 릴리즈 준비 단위 테스트 | Python 3.9·3.13 각각 6개 통과 |
| 이전 통합 배포 제거 후 RabbitMQ만 설치 | 통과 |
| 잘못된 대상·sdist 대상 변경 거부 | 통과 |
| wheel 전용 재빌드·twine strict 검사 | 통과 |
| YAML·내장 Python·Markdown·차이 검사 | 통과 |

첫 제품 테스트의 cp949 출력 실패는 기존 Unicode 배너에 의한 것이며 `PYTHONUTF8=1`로 재실행해 통과했다. 제품 코드는 이를 이유로 수정하지 않았다.

검증용 버전은 환경변수로만 지정했다. 릴리즈 준비 검사는 PyPI 응답 모킹을 사용했으며 실제 게시하지 않았다. 주요 재현 진입점은 저장소 루트에서 `python scripts/build_distributions.py --no-isolation`, `python scripts/check_distributions.py --editable` 및 `python -m unittest discover -s scripts/tests -t scripts -p test_release.py`이다. 필요한 빌드 도구는 [매뉴얼](../../../docs/Packaging.md)에 있다.

## 남은 검증과 상태

Windows에서 Python 3.9·3.13을 검증했다. 실제 RabbitMQ/Redis 서버 연결, 지원 Python 전체 CI 매트릭스 및 실제 PyPI 이름 소유권·토큰 권한은 검증하지 않았다. 원격 CI와 게시 전 관리자의 확인이 필요하다.

후속 editable 정적 분석 호환성은 선택 링크 트리로 변경해 검증했다. 최소 지원 Python에서 파일 기반 탐색·설치/제거·두 환경 격리와 단위 테스트 12개를 통과했다. 같은 구조의 DefPixel은 Pylance 밑줄 해소까지 사용자 확인을 받았다. 선택 격리와 부모 API를 유지하며 커밋·푸시·PR·병합·게시·원본 이슈 종료는 하지 않았다.

## 단계별 기록

1. [요구사항 분석과 작업 준비](./tasks/1793294230195.md)
2. [배포 조합과 기존 동작 검증](./tasks/1793295445976.md)
3. [최소 지원 버전과 이전 배포 전환 검증](./tasks/1793295838893.md)
4. [이동한 릴리즈 테스트 검증](./tasks/1793296500299.md)
5. [editable 정적 분석 호환성 조사](./tasks/1793297795667.md)
6. [선택 editable 링크 트리 검증](./tasks/1793299630939.md)
7. [EXTRAS 설치 검증과 개발 환경 전환](./tasks/1793301829546.md)
