# DefStream #34 작업 계획

## 목표와 기준

- 근거: [원본 이슈 및 메타데이터](./README.md), [요구사항 명세서](./REQUIREMENTS.md)
- 프로젝트: DefStream
- 작업 브랜치: `task/34`
- 병합 대상 브랜치: `master`
- 대상 CI: [`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml)

이 계획에 따라 CI 변경 로그 경로와 프로젝트별 README 지침을 갱신한다. 상세 매뉴얼이나 README 본문 자체는 이 작업 범위에 포함하지 않는다.

## 수행 순서

1. 프로젝트 루트의 `instructions/` 디렉터리에 `README.instructions.md`와 `DOCS.instructions.md`를 각각 작성해 루트 README와 상세 매뉴얼 지침을 분리한다.
2. Windows 환경에서 `.github/instructions`를 루트 `instructions/`를 가리키는 디렉터리 정션으로 연결한다. Git이 정션 내부 파일을 중복 표시하지 않도록 `.gitignore` 제외 규칙을 유지한다.
3. CI에서 현재 사용 중인 `issues/{branch}/README.md` 참조와 관련 검증 코드를 확인한다.
4. 릴리즈 동작은 유지하면서 변경 로그 입력 경로를 `issues/{branch}/CHANGELOG.md`로 변경한다.
5. 관련 CI·워크플로 테스트를 실행하고 변경 경로, 빈 파일 오류 처리, 릴리즈 노트 전달이 유지되는지 검증한다.
6. 두 지침 파일의 적용 범위와 정션 대상, Git 변경 목록에서 중복 노출되지 않는지 확인한다.
7. 변경 사항과 검증 결과를 이슈 기록에 반영한다.

## 검증 계획

- 저장소의 기존 워크플로 테스트에서 변경 로그 파일 경로와 누락·빈 내용 검사를 검증한다.
- 관련 테스트 파일과 CI 설정 검증을 실행한다.
- 수정하지 않은 릴리즈 조건·버전 산정·배포 경로가 유지되는지 차이를 확인한다.
- 두 지침 파일의 경로, 이름, frontmatter 적용 범위와 요구된 작성 규칙을 검토한다.
- 상세 매뉴얼의 한국어 원본과 동일 이름 `.en.md` 영어판, 초보자 대상 설명, 실행 가능한 예제 및 설명을 보조하는 Mermaid 다이어그램 지침을 확인한다.
- 이번 작업에서 실제 README 및 상세 매뉴얼은 생성하지 않았는지 확인한다.

## 수행 결과

- DefStream CI가 병합된 작업 브랜치의 `issues/{branch}/CHANGELOG.md`를 읽도록 변경했다.
- DefStream의 릴리즈 워크플로 회귀 테스트 fixture와 경로 기대값을 새 파일명에 맞게 갱신했다.
- `instructions/README.instructions.md`와 `instructions/DOCS.instructions.md`를 분리해 추가했다. 상세 매뉴얼은 한국어를 기준으로 하고 영어판 파일명에 `.en.md`를 붙이며, 초보자용 단계별 설명, 충분한 실행 가능 예제, 이해를 돕는 Mermaid 다이어그램을 요구한다.
- `.github/instructions`를 `instructions/`를 가리키는 디렉터리 정션으로 만들었다. Git은 이를 일반 디렉터리로 보기 때문에 중복 경로 제외 규칙을 유지한다.
- 구현 및 검증 세부 결과는 [구현 기록](./IMPLEMENTS.md)에 기록한다.
