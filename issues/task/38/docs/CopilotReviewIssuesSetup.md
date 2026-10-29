# PR 리뷰 이슈 자동 등록 설정하기

이 안내는 PR 리뷰 제출로 리뷰 코멘트 이슈 자동 등록을 실행하기 전에 확인할 항목과 시험 방법을 설명합니다.

## 시작 전 확인

- 리뷰 이슈 등록 워크플로와 스크립트는 저장소 기본 브랜치에 반영되어 있어야 합니다. PR 생성 워크플로는 작업 브랜치에 존재해야 하며, 해당 push가 실행 대상으로 사용됩니다.
- `bug/{이슈번호}`, `fix/{이슈번호}`, `feature/{이슈번호}`, `task/{이슈번호}` 형식의 브랜치에 push하면, 대응하는 `issues/{유형}/{이슈번호}/`의 작업 문서로 기본 브랜치 대상 PR을 자동 생성합니다.
- PR 제목은 이슈 디렉터리 `README.md`의 유효한 첫 제목을 우선 사용하고, 없거나 너무 길면 원본 GitHub 이슈 제목을 사용합니다. 본문은 존재하고 내용이 있는 이슈 문서만 전체 본문과 링크로 반영합니다. 문서가 모두 없거나 비어 있어도 원본 이슈 본문과 링크로 생성하며 특정 섹션명은 요구하지 않습니다. 커밋 메시지는 사용하지 않습니다.
- `.github/PULL_REQUEST_TEMPLATE.md`의 누락이나 안내 문구·체크박스 변경은 PR 생성을 막지 않습니다. 본문이 길이 제한을 넘으면 원문 링크로 제공하고 이유를 표시합니다. 파일 부재 외 읽기 오류와 API·권한 오류는 실패로 표시합니다.
- 본문의 상대 Markdown 링크는 원본 문서와 push SHA 기준 URL로 변환합니다. squash 병합 후에도 base와 push 커밋의 tree가 같으면 새 PR을 만들지 않습니다. 기존 Contents 읽기 권한을 사용하며 추가 인증은 필요하지 않습니다.
- PR에는 대응하는 GitHub 이슈의 레이블과 담당자를 적용합니다. 이미 열린 PR도 워크플로 재실행 시 동기화하며, 원본 이슈에 담당자가 없으면 PR 담당자를 변경하지 않습니다.
- PR 생성 workflow는 GitHub GraphQL API로 대응 이슈와 PR 사이에 closing reference를 명시적으로 연결합니다. Development에 표시되며, PR을 저장소 기본 브랜치에 병합하면 원본 이슈가 자동으로 닫힙니다. 연결 API가 실패하면 workflow도 실패합니다.
- 같은 head/base 조합의 열린 PR이 있으면 중복 생성만 건너뛰고 메타데이터를 적용합니다. 이전 PR이 병합된 뒤 base와 비교해 변경 파일이 있으면 같은 브랜치로 새 PR을 만들 수 있습니다.
- PR 생성 workflow는 Copilot 리뷰를 요청하지 않습니다. 리뷰가 필요하면 GitHub의 수동 요청 또는 적용 가능한 자동 리뷰 설정을 사용합니다. App bot 작성 PR에 대한 개인 설정 적용 여부는 별도 확인합니다.
- 자동 PR 작성자는 설치한 GitHub App의 bot입니다. PR 작성자와 관계없이 리뷰 제출로 리뷰 이슈 등록 워크플로가 실행됩니다.
- `pull_request_review.submitted` 이벤트에서 실행하며 리뷰 상태·작성자 관계로 제한하지 않습니다. PR의 `Approve` 리뷰는 필요하지 않습니다. GitHub가 Actions 실행 승인을 요구하면 권한 있는 사용자가 허용해야 하며, 이 승인은 PR 코드 승인과 별개입니다.
- 리뷰 제출 시 실제 GitHub 이슈가 만들어질 수 있으므로, 시험할 PR과 부모 이슈를 먼저 확인합니다.
- 이 workflow는 기본 브랜치의 스크립트를 checkout합니다. PR 승인 필터 제거를 실제 적용하려면 workflow뿐 아니라 스크립트 변경도 기본 브랜치에 반영해야 합니다. 과거 실행의 재실행은 최신 workflow 적용을 보장하지 않습니다.
- 저장소 Actions Variables에 `PR_APP_CLIENT_ID`, Secrets에 `PR_APP_PRIVATE_KEY`를 등록합니다. 비공개 키는 PEM 전체 내용을 저장하며 코드나 로그에 기록하지 않습니다.
- App은 해당 저장소에 설치하고 Repository permissions에서 Contents 읽기, Issues 읽기·쓰기, Pull requests 읽기·쓰기를 허용합니다.

## 권한과 Copilot CLI 정책

두 workflow 모두 `actions/create-github-app-token@v3`로 현재 저장소에 한정된 임시 App 토큰을 발급합니다.

- PR 생성 App 토큰: `contents: read`, `issues: write`, `pull-requests: write`
- 리뷰 이슈 등록 App 토큰: `issues: write`, `pull-requests: read`
- 기본 `GITHUB_TOKEN`: checkout의 `contents: read`, 리뷰 작업의 `copilot-requests: write`

스크립트의 `GITHUB_TOKEN`에는 App 토큰을 전달합니다. 리뷰 스크립트에는 별도로 `COPILOT_GITHUB_TOKEN`을 전달하고, Copilot CLI 자식 프로세스에만 기본 `GITHUB_TOKEN`을 제공합니다. Copilot 인증이 없으면 App 토큰으로 대체하지 않고 실패합니다.

App 토큰으로 생성된 PR은 기본 `GITHUB_TOKEN`으로 생성한 PR의 승인 필요 제한을 받지 않습니다. 다른 저장소·조직 정책에 따른 제한까지 해제하는 것은 아닙니다. 기존 PR의 작성자는 변경되지 않습니다.

저장소, 조직 또는 엔터프라이즈가 해당 권한이나 Copilot CLI 사용을 제한하면 실행이 실패할 수 있습니다. 조직 저장소는 관리자에게 Copilot CLI 사용 정책과 사용량 청구 주체를 확인하세요. 별도 토큰을 추가하거나 권한 제한을 우회하지 마세요.

## 안전하게 시험

1. 위 형식의 작업 브랜치에 PR 생성 workflow·스크립트가 있는지, 대응하는 GitHub 이슈가 존재하는지 확인합니다. 이슈 문서는 선택 사항이며 존재하면 해당 push 커밋의 내용을 사용합니다.
2. 해당 브랜치에 push하여 자동 생성된 PR의 head·base·제목·본문과 원본 이슈의 메타데이터를 확인합니다. 번호는 실제 부모 이슈여야 합니다. 다시 push하면 PR은 중복 생성되지 않고 메타데이터를 적용해야 합니다. Copilot 리뷰는 workflow와 별도로 관리합니다.
3. 해당 PR에 미해결 리뷰 스레드의 최초 줄별 코멘트가 있는지 확인합니다. 리뷰 작성자는 제한하지 않으며, 이미 `Resolved`인 스레드와 답글은 처리 대상이 아닙니다.
4. Copilot 또는 사람이 리뷰를 제출합니다. GitHub가 실행 승인을 요구하는 경우 Actions에서 허용합니다. PR의 `Approve` 제출은 필요하지 않습니다.
5. 저장소의 **Actions** 탭에서 **Create issues from PR reviews** 실행을 확인합니다.
6. 제목·본문의 한국어 요약, 분류 레이블, 원본 PR·리뷰·코멘트와 코드 위치, 부모 이슈 관계를 확인합니다.

리뷰 제출은 리뷰 이슈 생성을 실제로 수행합니다. 운영 이슈가 생성되어도 괜찮은 PR로 시험하세요. 같은 워크플로를 재실행하거나 새 리뷰를 제출하면 중복 이슈가 생길 수 있으며, 자동으로 정리되지 않으므로 생성 결과를 확인하고 사람이 정리해야 합니다.

## 실패했을 때

- Actions 실행에서 실패한 작업과 로그를 확인합니다.
- 대상 부모 이슈를 찾지 못하면 PR head 브랜치 형식과 이슈 존재 여부를 확인합니다.
- Copilot 요청, 토큰 권한, 이슈 생성 또는 부모 연결 오류는 실행 실패로 나타납니다.
- Copilot CLI 오류의 구체적인 원인은 Actions 실패 로그의 제한된 표준 오류 진단을 확인합니다. 토큰 문자열은 로그에서 가려집니다.
- 이슈 생성 뒤 부모 연결이 실패한 경우 이슈가 이미 만들어졌을 수 있습니다. 재실행 전에 먼저 생성된 이슈를 확인하세요.

세부 동작과 테스트 명령은 [운영 안내](./CopilotReviewIssues.md)를 참고하세요.
