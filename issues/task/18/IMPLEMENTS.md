# 변경 제안 및 핫픽스 이슈 양식 구현 기록

## 구현 내용

[요구사항](./REQUIREMENTS.md)에 따라
[03.fix.yml](../../../.github/ISSUE_TEMPLATE/03.fix.yml)을 추가했다.
요청자가 가벼운 변경과 핫픽스를 구분하고, 목적과 변경 내용은 필수로,
영향 범위·긴급 배경·완료 기준은 필요한 경우 선택적으로 작성하도록 구성했다.
기존 버그/오류 제보와 기능 제안 양식은 변경하지 않았다.

## 검증

Python 가상환경의 PyYAML로 양식 YAML을 파싱하고, 필수·선택 필드와 필드 ID의
중복 여부를 확인했다. `git check-ignore`에서 새 양식이 제외되지 않는 것과
`git diff --check`를 확인했다. GitHub 웹 UI 렌더링은 확인하지 않았다.

## 소스 코드 외 작업 양식

[04.task.yml](../../../.github/ISSUE_TEMPLATE/04.task.yml)에 리소스 변경과
문서화 등 소스 코드 변경이 아닌 작업을 위한 양식을 추가했다.
작업 목적, 작업 내용 및 대상, 완료 기준은 필수로 작성하며 관련 자료 및
주의사항은 선택적으로 작성할 수 있다. 기존 이슈 양식은 수정하지 않았다.

PyYAML로 YAML 구문, 양식 이름·제목, 필수 입력 항목과 필드 ID 중복 여부를
검증했다. 새 파일의 Git 제외 여부 및 공백 검사와 `git diff --check`도 통과했다.
GitHub 웹 UI에서의 양식 렌더링은 확인하지 않았다.

## 이슈 레이블 자동 지정

네 이슈 양식의 최상위 `labels` 배열에 각각 `feature`, `bug`, `fix`, `task`를
지정했다. 사용자가 수정한 빈 제목과 기존 입력 항목은 유지했다.
저장소에 레이블이 미리 존재해야 한다는 운영 조건은 [변경 로그](./README.md)에
명시했다. 원격 저장소의 레이블 생성이나 존재 여부 확인은 수행하지 않았다.

PyYAML로 네 파일의 레이블 배열이 지정된 이름 하나만 포함하는지, 빈 제목과
필드 ID 중복 없음이 유지되는지 검증했다. `git diff --check`도 통과했다.

## 양식 선택 화면 미표시 수정

GitHub 공식 유효성 문서는 문자열 항목에 빈 문자열을 허용하지 않으며,
선택 항목은 값을 비우는 대신 항목 자체를 생략하도록 안내한다.
네 양식의 `title: ""`를 제거하여 제목 접두어 없이 작성하는 의도를 유지했다.
번호가 포함된 파일명, 레이블과 입력 항목은 변경하지 않았다.
앞선 YAML 구문 검증은 이 GitHub 제약을 확인하지 못했다.

공식 근거: [Issue Forms 유효성 오류](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/common-validation-errors-when-creating-issue-forms).
로컬 검증에서 네 양식의 빈 최상위 문자열 없음, `title` 생략, 레이블 매핑과
입력 필드 ID를 확인했다. GitHub 화면에서의 복구 확인은 수행하지 않았다.
