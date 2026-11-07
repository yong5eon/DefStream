# 에이전트 작업 지침

이 파일은 DefStream에서 작업하는 CLI 및 원격 에이전트의 지침 진입점이다. 특정 에이전트나 실행 환경에 한정하지 않는다.

## 세부 지침

작업 전에 공통 에이전트 지침 [`.instructions.assistant/`](.instructions.assistant/)와 DefStream 전용 지침 [`.instructions/`](.instructions/)을 다음 순서로 확인한다. 각 지침의 적용 범위와 참조 자료도 확인하고 작업에 필요한 지침을 직접 읽는다. 목록에 없는 지침이 새로 추가된 경우에도 관련 여부를 확인한다.

1. 모든 작업은 [`INSTRUCTIONS.instructions.md`](.instructions.assistant/INSTRUCTIONS.instructions.md)에서 지침 탐색과 작업 권한을 확인한다.
2. 모든 실제 작업은 [`TASK.instructions.md`](.instructions.assistant/TASK.instructions.md)에서 작업 절차, 기록과 검증 지침을 확인한다.
3. 코드 작업은 [`DEV.instructions.md`](.instructions.assistant/DEV.instructions.md)의 개발 원칙과 검증 기준을 확인하고, 대상에 맞는 지침을 함께 읽는다.
   - [`CODE.instructions.md`](.instructions/CODE.instructions.md): DefStream 코드의 독스트링·주석·오류 메시지 등 영어 작성 정책
   - [`DEV.Python.instructions.md`](.instructions.assistant/DEV.Python.instructions.md): Python 코드 스타일, 타입 힌트와 구현 규칙
   - [`DEV.Javascript.instructions.md`](.instructions.assistant/DEV.Javascript.instructions.md): JavaScript 모듈, 실행 흐름, 오류와 테스트
   - 코드 변경 시 변경 로그 작성 전에 [`DOCS.instructions.md`](.instructions/DOCS.instructions.md)와 [`README.instructions.md`](.instructions/README.instructions.md)를 확인해 상세 매뉴얼과 프로젝트 루트 README의 영향 여부를 검토한다. 영향이 있는 문서는 해당 지침에 따라 갱신하고, 갱신이 불필요하면 이유를 작업 기록에 남긴다.
4. 문서 작업은 [`MARKDOWN.instructions.md`](.instructions.assistant/MARKDOWN.instructions.md)의 Markdown 작성 규칙을 확인하고, 대상에 맞는 지침을 함께 읽는다.
   - [`README.instructions.md`](.instructions/README.instructions.md): 프로젝트 루트 README의 역할과 언어별 작성 규칙
   - [`DOCS.instructions.md`](.instructions/DOCS.instructions.md): 상세 매뉴얼과 한국어·영어 문서의 동기화
5. 커밋 메시지를 작성하거나 검토할 때는 [`GIT.COMMIT.MESSAGE.instructions.md`](.instructions.assistant/GIT.COMMIT.MESSAGE.instructions.md)를 확인한다.

위 순서는 지침을 찾아 읽는 순서이며 그 자체가 지침 간 우선순위를 뜻하지 않는다. 공통 규칙과 프로젝트별 적용 범위·예외를 함께 따른다. 예를 들어 코드 내 문구는 공통 개발 지침의 한국어 규칙 대신 프로젝트의 영어 정책을 적용한다.

## 작업 범위와 미확정 사항

- 확인된 요구사항의 범위에서 작업하고, 추측으로 기능이나 작업 범위를 확대하지 않는다.
- 영향이 작은 구현 선택은 기존 코드와 지침을 근거로 판단하고, 필요한 경우 선택 이유를 기록한다.
- 결과나 호환성 등에 중대한 영향을 주는 사항이 미확정이면 해당 부분을 임의로 구현하지 않는다. 독립적으로 진행할 수 있는 확정된 작업은 계속한다.
- 즉시 확인받기 어려운 환경에서는 세부 지침의 사용자 확인 요청을 기다리는 대신, 해당 부분을 보류하고 미확정 내용과 이유, 필요한 결정을 작업 기록과 PR 등 제공 가능한 결과에 남긴다. 이슈 유형이나 필수 지침을 확인할 수 없는 경우처럼 작업 전체의 전제가 불명확하면 작업을 진행하지 않는다.
- 필요한 지침을 읽을 수 없거나 지침 충돌을 해결할 수 없으면 영향받는 작업을 보류하고 원인과 영향을 기록한다. 해결되지 않은 사항이나 미완료 작업을 완료한 것처럼 보고하지 않는다.

## 이슈 작업

- 이슈의 유형 레이블은 `feature`, `fix`, `bug`, `task` 중 하나여야 한다.
- 유형 레이블이 없으면 이슈 원문과 관련 자료를 근거로 유형을 확정하고, 해당 레이블을 이슈 URL의 원본 이슈에 적용한 뒤 결과를 확인한다. 유형을 확정할 수 없거나 레이블을 적용할 수 없으면 임의로 진행하지 않고 원본 이슈의 댓글에 사유와 필요한 조치를 남긴다. 댓글을 작성할 수 없으면 드래프트 PR이나 작업 결과에 작성하지 못한 이유와 필요한 조치를 남긴다.
- 이슈 작업 시 `issues/<레이블>/<이슈번호>/`를 만들고 작업 기록을 남긴다.
- 해당 디렉터리에 `CHANGELOG.md`를 작성한다.
- 이슈 작업의 PR 생성·갱신 전에 [변경 적용 요청 문서 지침](.instructions.assistant/TASK.instructions.md#변경-적용-요청-문서)에 따라 `IR.md`를 작성한다. 제목은 256자 이하여야 한다.
- 이슈 브랜치의 자동화가 푸시된 `IR.md`의 첫 줄을 PR 제목으로, 나머지를 본문으로 사용한다. 해결한 이슈의 `Closes`를 각각 기록하고 마지막 비어 있지 않은 줄에 `- Changes: issues/<레이블>/<이슈번호>/CHANGELOG.md`를 기록한다. 파일이나 유효한 제목·본문·마지막 항목이 없으면 자동 생성·갱신이 실패한다.
- `copilot/**`, `codex/**` 브랜치는 열린 PR의 변경 파일에서 이슈 `IR.md` 하나를 찾아 제목과 본문을 갱신한다. 파일이 없거나 여러 개면 자동 갱신이 실패한다.
- PR을 작성하거나 갱신할 때 본문 마지막에 `- Changes: issues/<레이블>/<이슈번호>/CHANGELOG.md` 형식으로 변경 로그 파일 경로를 명시한다.

## 이슈가 없는 작업

- 이슈가 없는 실제 작업은 이슈를 임의로 만들거나 식별자를 추측하지 않고, 저장소 루트의 `tasks/<UNIX_TIMESTAMP>/`에 기록한다. 단순 질문·설명·의견 검토에는 작업 기록을 만들지 않는다.
- 디렉터리 이름은 작업을 식별하는 Unix epoch 밀리초 숫자다. 기존 이름과 충돌하지 않도록 확인하고 기존 기록을 덮어쓰지 않는다.
- `README.md`에 작업의 목적과 범위, 진행 상태 및 관련 기록을 정리한다.
- 이슈 작업과 같이 `REQUIREMENTS.md`, `PLAN.md`, `CHANGELOG.md`와 해당하는 종합 실행 기록을 작성한다.
- PR을 작성하거나 갱신할 때 본문 마지막에 `- Changes: tasks/<UNIX_TIMESTAMP>/CHANGELOG.md` 형식으로 실제 변경 로그 경로를 명시한다.
- 의미 있는 작업 단위의 근거, 구현, 구현 외 작업은 필요에 따라 각각 `context/`, `implements/`, `tasks/`에 기록한다. 작업 단위별 파일명에 Unix epoch 밀리초를 사용하며, 같은 작업 단위의 기록은 세 디렉터리에서 동일한 타임스탬프를 사용한다.
- 디렉터리의 타임스탬프는 작업 전체를 식별하고, 단계별 기록의 타임스탬프는 각 작업 단위를 식별한다. 단계별 기록의 내용과 타임스탬프 생성은 [작업 지침의 단계별 기록 규칙](.instructions.assistant/TASK.instructions.md#단계별-근거구현작업-기록)을 따른다.

## 원격 에이전트

원격 플랫폼에서 이슈를 할당받은 에이전트는 제공된 작업 브랜치를 사용한다. 이 경우 세부 지침의 브랜치 명명·전환 및 브랜치와 기록 경로 일치 규칙 대신 이슈의 유형과 번호로 기록 경로를 정한다. 플랫폼의 작업 흐름에 필요한 커밋·푸시와 PR 작성·갱신을 수행하되, 병합·배포 등 별도 승인이 필요한 조치는 세부 지침을 따른다.
