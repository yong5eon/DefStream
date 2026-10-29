# 요구사항 명세서

## 분석 요약

- 이슈 원문은 Copilot PR 리뷰의 조치 대상 지적 사항을 한국어 이슈로 자동 등록하는 워크플로 추가를 요청한다.
- 사용자는 DefPixel 저장소에서 이미 구현·사전 검증된 자동화 전체(워크플로 2개와 스크립트·테스트)를 이 저장소에 그대로 적용하도록 범위를 확정했다. 이슈 원문보다 범위가 넓다는 점을 사용자가 인지하고 지시했다.
  - `create-pr-from-issue.yml`: 이슈 브랜치(`bug/**`, `fix/**`, `feature/**`, `task/**`) push 시 기본 브랜치 대상 PR 자동 생성
  - `create-issues-from-reviews.yml`: PR 리뷰 제출 시 미해결 리뷰 스레드의 조치 대상 코멘트를 한국어 이슈로 자동 등록
- DefPixel 구현은 리뷰 작성자를 Copilot으로 제한하지 않고 모든 작성자의 미해결 스레드 최초 코멘트를 처리한다. 원문의 "Copilot 리뷰 대상" 요구를 포함하는 상위 집합이며, 이 동작 차이는 DefPixel에서 확정된 계약으로 그대로 적용한다.
- 중복 방지에 대해 DefPixel 구현은 과거 이슈 검색 기반 자동 중복 제거를 수행하지 않고, 재실행·재리뷰로 생긴 중복은 사람이 정리하는 방식을 채택했다. 이 제한도 그대로 적용하며 운영 안내 문서에 명시되어 있다.

## 확정 요구사항

- DefPixel의 다음 파일을 수정 없이 동일하게 적용한다.
  - `.github/workflows/create-pr-from-issue.yml`
  - `.github/workflows/create-issues-from-reviews.yml`
  - `.github/scripts/create-pr-from-issue.mjs`
  - `.github/scripts/create-issues-from-reviews.mjs`
  - `.github/scripts/tests/create-pr-from-issue.test.mjs`
  - `.github/scripts/tests/create-issues-from-reviews.test.mjs`
- 필요한 권한, 설정, 동작 범위와 실패 확인 방법을 문서화한다. DefPixel에서 검증된 운영·설정 안내 문서를 이 이슈의 `docs/`로 가져와 유지한다.
- 스크립트 테스트(`node --test`)가 이 저장소에서 통과해야 한다.

## 제외 범위

- 스크립트·워크플로의 동작 변경이나 저장소별 커스터마이징은 하지 않는다. 테스트 목(mock) 데이터의 DefPixel 예시 URL도 동작과 무관하므로 수정하지 않는다.
- 프로젝트 소스 코드, CI 워크플로(`ci.yml`)와 이슈·PR 템플릿은 변경하지 않는다.

## 확인이 필요한 사항

- 저장소 Actions Variables의 `PR_APP_CLIENT_ID`, Secrets의 `PR_APP_PRIVATE_KEY` 등록과 GitHub App의 이 저장소 설치는 저장소 관리자 권한이 필요한 외부 설정이다. 적용 여부를 별도로 확인해야 하며, 미설정 시 두 워크플로는 토큰 발급 단계에서 실패한다.
- 실제 리뷰 제출로 이슈가 생성되는 끝단 동작(end-to-end)은 push·PR·리뷰가 발생해야 검증할 수 있다. 시험 방법은 [GitHub 사전 설정 및 시험 안내](./docs/CopilotReviewIssuesSetup.md)를 따른다.

## 인수 기준

- 두 워크플로와 스크립트·테스트 6개 파일이 DefPixel 원본과 동일한 내용으로 저장소에 존재한다.
- `node --test`로 두 테스트 파일이 모두 통과한다.
- 권한·설정·동작 범위·실패 확인 방법이 이슈 문서에서 확인된다.
