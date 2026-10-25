# DefStream #34 구현 및 검증 기록

## 구현 내용

- [CI 워크플로](../../../.github/workflows/ci.yml)에서 병합된 작업 브랜치의 릴리즈 변경 로그 경로를 `issues/{branch}/README.md`에서 `issues/{branch}/CHANGELOG.md`로 변경했다. 파일 누락·빈 내용 검사와 릴리즈 이벤트 조건은 유지했다.
- 루트 README 작성 지침 [README.instructions.md](../../../instructions/README.instructions.md)와 상세 매뉴얼 작성 지침 [DOCS.instructions.md](../../../instructions/DOCS.instructions.md)를 별도 파일로 추가했다. 상세 매뉴얼은 한국어 기준 및 동일 이름 `.en.md` 영어판, 초보자용 단계별 설명, 충분하고 실행 가능한 예제, 이해를 돕는 Mermaid 다이어그램을 요구한다.
- `.github/instructions`를 루트 `instructions/` 대상 디렉터리 정션으로 연결했다. 정션은 Git에서 링크로 추적되지 않으므로 `.gitignore` 제외 규칙을 유지해 중복 경로를 숨긴다.
- 지침은 문서 생성 규칙을 정의하며, 요청 범위에 따라 실제 루트 README와 상세 매뉴얼은 만들지 않았다.
- [릴리즈 워크플로 회귀 테스트](../../../tests/test_release_workflow.py)의 변경 로그 fixture와 경로 기대값을 새 파일명으로 갱신했다.

요청 범위에 따라 실제 README나 상세 매뉴얼은 생성·수정하지 않았다.

## 검증 결과

| 검증 | 결과 |
| --- | --- |
| `python -m unittest discover -s tests -p 'test*release_workflow.py' -v` | 통과, 71개 테스트 |
| 두 CI 워크플로의 릴리즈 로그 경로 확인 | `issues/{branch}/CHANGELOG.md` 사용, 이전 README 경로 참조 없음 |
| 두 워크플로의 내장 Python 스크립트 구문 컴파일 | 통과 |
| README 지침 frontmatter 확인 | `instructions/README.instructions.md`는 루트 README, `instructions/DOCS.instructions.md`는 `docs/**/*.md`에 적용 |
| `.github/instructions` 정션 확인 | 두 저장소의 정션이 루트 `instructions/`를 가리키며, 두 지침 파일이 링크 경로에서 확인됨 |
| DefStream `git diff --check` | 통과 |

DefEssential 저장소에는 별도의 릴리즈 워크플로 회귀 테스트가 없어, 양쪽 워크플로의 경로 및 내장 Python 구문을 직접 확인했다.

Windows 디렉터리 정션은 Git에서 일반 디렉터리처럼 취급되어 링크 자체가 저장소에 기록되지 않는다. 따라서 정션은 현재 작업 환경에서만 만들었으며 새 체크아웃에서는 필요 시 다시 생성해야 한다.
