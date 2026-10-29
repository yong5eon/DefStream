# 작업 계획서

## 수행 순서

1. DefPixel의 워크플로 2개, 스크립트 2개, 테스트 2개를 `.github/` 아래 같은 경로로 복사한다.
2. DefPixel에서 검증된 운영·설정 안내 문서를 이 이슈의 `docs/`로 가져온다.
3. `node --test`로 두 테스트 파일을 실행하여 통과를 확인한다.
4. 구현·검증 기록과 변경 로그를 작성한다.

## 검증 계획

- 복사된 파일이 DefPixel 원본과 동일한지 해시 비교로 확인한다.
- 저장소 루트에서 `node --test .github/scripts/tests/create-pr-from-issue.test.mjs .github/scripts/tests/create-issues-from-reviews.test.mjs`를 실행한다. Node.js 24 기준이다.
- 실제 워크플로 실행(끝단 동작)은 GitHub App 설정 후 [시험 안내](./docs/CopilotReviewIssuesSetup.md)의 절차로 별도 확인한다.

## 선행 조건과 주의사항

- 워크플로 동작에는 저장소 Actions 변수 `PR_APP_CLIENT_ID`, Secret `PR_APP_PRIVATE_KEY`와 GitHub App 설치가 필요하다. 코드 반영과 별개로 저장소 관리자가 설정해야 한다.
- 리뷰 이슈 등록 워크플로는 기본 브랜치의 스크립트를 checkout하므로, 기본 브랜치에 병합되어야 실제 동작한다. PR 생성 워크플로는 push된 작업 브랜치의 파일을 사용한다.

## 진행 상태

- 파일 적용, 문서 반입, 테스트 검증 완료. 기록 작성 완료.
- 저장소 Actions 변수 `PR_APP_CLIENT_ID`와 Secret `PR_APP_PRIVATE_KEY`의 등록은 확인했다.
- 남은 항목: 커밋·푸시(별도 요청 시), 기본 브랜치 병합 후 실제 동작 시험.
