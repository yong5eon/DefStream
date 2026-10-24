# PyPI용 독립 설명 문서 작성 구현 기록

## 구현 개요

[요구사항 명세](./REQUIREMENTS.md)에 따라 PyPI 설명용 영어 문서
`README.setup.md`를 추가하고, 패키지 장문 설명이 이 문서를 UTF-8로 읽도록
`setup.py`를 변경했다. 기존 `README.en.md`의 자체 포함된 주요 설명과 사용법을
반영하고, PyPI에서 접근할 수 없는 외부 및 저장소 상대 링크는 일반 텍스트로 바꿨다.

- 구현·검증일: 2026-10-24
- 사용자용 안내: [변경 로그](./README.md)

## 구현 내용

- 저장소 루트의 `README.setup.md`는 `README.en.md`의 설치, 빠른 시작, 작업 처리,
  풀과 종료, 생명주기 훅, 검증, Inspector, RabbitMQ, Redis, 로깅 및 운영 안내를
  포함하는 독립된 PyPI 문서다.
- PyPI에서 깨질 수 있는 외부 링크와 저장소 상대 링크를 제거하거나 설명 텍스트로
  바꾸고, 문서 내부 목차 링크는 유지했다. 로깅 안내는 필요한 설정 동작을 인라인으로
  설명했으며, 저장소의 샘플 경로 목록은 본문 예제가 이미 다루므로 제외했다.
- LICENSE 파일 경로 참조를 제거하고 GPL v3의 핵심 의무와 무보증을 요약해 문서 안에
  표시했다.
- `setup.py`의 `long_description` 입력을 `README.setup.md`로 변경하고 UTF-8 설정은 유지했다.
- 다른 패키지 메타데이터, 의존성, 런타임 동작은 변경하지 않았다.

## 검증 결과

- `python setup.py --long-description`의 출력을 `README.setup.md`와 비교해 장문 설명 내용이
  일치함을 확인했다.
- `README.setup.md`에 외부 HTTP 링크가 없고, README.en.md의 주요 섹션과 설치 안내,
  사용 예제 및 운영 정보가 반영됐음을 확인했다.
- `git diff --check`를 실행해 추적 중인 변경의 공백 오류가 없음을 확인했다.
- 패키지 메타데이터 확인은 성공했으며, 실행 시 setuptools의 기존 `setup_requires`
  사용에 대한 폐기 예정 경고가 출력됐다.
