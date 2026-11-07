# GitHub 에이전트용 공통 지침 연결 및 AGENTS.md 추가

## 이슈 메타데이터

- 원본 이슈: [yong5eon/DefStream #67](https://github.com/yong5eon/DefStream/issues/67)
- 유형·레이블: 작업 (`task`), 적용 확인
- 작업 저장소: `yong5eon/DefStream`
- 작업 브랜치: `task/67`
- 병합 대상 및 분기 기준: `master`
- 공통 지침 원본: `yong5eon/Instructions`, 커밋 `8706862712c800682f38af3c86e74f768345d811`
- 진행 상태: PR 리뷰 후속 수정 및 로컬 검증 완료. 이번 수정의 실제 GitHub Actions 검증 대기.

## 후속 요청

사용자가 csvd2c의 지침과 PR 자동화를 이 프로젝트에 맞게 적용하고 기존 이슈와 브랜치에서 이어서 작업·기록하도록 지정했다. 이 요청은 원문의 커밋 메시지 지침 제외와 공통 지침 위치를 변경한다.

PR 리뷰 분석 후 사용자는 들여쓴 `Changes:` 처리와 변경 로그의 일반 파일 검사를 수정하고, 3,000개 파일 제한과 App 권한 구조는 유지하도록 요청했다.

## 이슈 원문

### 배경

GitHub에서 할당된 에이전트는 이슈가 속한 저장소를 작업 대상으로 삼으므로, 로컬 작업 환경의 외부 링크나 `Instructions` 저장소를 자동으로 읽는다고 가정할 수 없습니다. 공통 작업 지침과 이 저장소별 지침이 에이전트에 실제 전달되도록 해야 합니다.

### 목표

`DefStream` 저장소에 Codex와 Copilot의 GitHub 에이전트가 공통 지침을 읽고 적용할 수 있는 루트 `AGENTS.md`와 저장소 내 공통 지침 사본을 제공합니다. 원본은 `yong5eon/Instructions`이며 `GIT.COMMIT.MESSAGE.instructions.md`는 제외합니다. 기존 프로젝트별 `instructions/` 지침도 함께 적용합니다.

### 요구사항

- 루트 `AGENTS.md`에서 작업 시작 전 공통 지침과 프로젝트별 지침을 확인하고, 요청 범위·권한·이슈 절차·작업 근거 기록·검증 원칙을 따르도록 안내합니다.
- GitHub 에이전트가 외부 로컬 링크나 외부 저장소 clone에 의존하지 않도록 공통 지침 원문을 저장소 내 추적되는 위치에 둡니다.
- 공통 지침은 원본과 구분 가능하게 보관하며, 커밋 메시지 전용 지침은 포함하지 않습니다.
- 프로젝트별 지침의 범위와 예외를 보존하고 공통 지침과 충돌하는 경우 임의로 우선순위를 정하지 않도록 합니다.
- 이슈 작업의 PR 준비 전 `issues/{branch}/CHANGELOG.md`가 존재하고 비어 있지 않은지 확인합니다. 문서·내부 변경으로 고객 영향이 없으면 해당 지침에 맞춰 이를 명시합니다. CI의 changelog 요구를 확인하고 빠뜨리지 않습니다.
- 이슈와 브랜치, 기록 경로는 저장소의 기존 절차에 따르며 기존 파일이나 로컬 지침 링크를 덮어쓰지 않습니다.

### 완료 기준

- 에이전트가 루트 `AGENTS.md`에서 필요한 지침 파일을 찾고 읽을 수 있습니다.
- 안내된 모든 공통 지침 파일과 프로젝트별 지침의 경로가 저장소 내 실제 파일과 일치합니다.
- `CHANGELOG.md` 필수 여부·위치를 PR 전에 검증하도록 안내되어 있고, 이 저장소 CI와 일치합니다.
- 기존 기능 코드에는 불필요한 변경을 하지 않습니다.

## 작업 기록

- 요구사항: [REQUIREMENTS.md](./REQUIREMENTS.md)
- 계획과 상태: [PLAN.md](./PLAN.md)
- 구현 종합: [IMPLEMENTS.md](./IMPLEMENTS.md)
- 작업 종합: [TASKS.md](./TASKS.md)
- PR 문서: [IR.md](./IR.md)
- 변경 로그: [CHANGELOG.md](./CHANGELOG.md)
- 단계별 기록: [context/](./context/), [implements/](./implements/), [tasks/](./tasks/)
- 최신 기록: [context/1794083646073.md](./context/1794083646073.md), [implements/1794083646073.md](./implements/1794083646073.md), [tasks/1794083646073.md](./tasks/1794083646073.md)
