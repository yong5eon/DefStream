# Python 3.9 CI 테스트 러너를 Ubuntu 24.04로 고정

## 이슈 정보

- 원본 이슈: [#57](https://github.com/yong5eon/DefStream/issues/57) (GitHub Issues, 열림)
- 유형 및 레이블: 작업 (`task` 레이블 적용됨)
- 작업 브랜치: `task/57`
- 병합 대상 브랜치: `master`
- 기준 커밋: `5a4d155` (`master`)
- 관련 실행: [GitHub Actions 실행 #41075016156](https://github.com/yong5eon/DefStream/actions/runs/41075016156)

## 작업 문서

- [요구사항 명세서](./REQUIREMENTS.md)
- [작업 계획서](./PLAN.md)
- [구현 결과](./IMPLEMENTS.md)
- [검증 결과](./TASKS.md)
- [이슈 변경 로그](./CHANGELOG.md)
- [원인 조사](./tasks/1793395003713.md)

## 최신 단계별 기록

- [CI 설정 구현](./implements/1793395003714.md)
- [로컬 검증과 남은 원격 확인](./tasks/1793395058100.md)

## 이슈 원문

### 변경 유형

작업

### 변경 목적

Python 3.9 테스트가 GitHub Actions에서 실행되기 전에 실패합니다. 실행 로그상 `ubuntu-latest`가 선택한 Ubuntu 26.04에서 `actions/setup-python`이 Python 3.9 x64를 찾지 못했습니다.

실행 기록: https://github.com/yong5eon/DefStream/actions/runs/41075016156

### 제안하는 변경 내용

- Python 버전별 테스트 매트릭스에서 Python 3.9만 `ubuntu-24.04`를 사용하도록 설정
- Python 3.10 이상 테스트와 다른 CI 작업은 기존 러너 설정 유지
- Python 3.9 지원 범위와 패키지 메타데이터는 변경하지 않음

### 영향 범위

GitHub Actions 테스트 환경 설정만 변경합니다. 제품 코드와 공개 API에는 영향이 없습니다.

### 긴급 수정 정보

해당 없음

### 완료 기준

- Python 3.9 테스트가 Ubuntu 24.04에서 실제 실행됨
- Python 3.10 이상 매트릭스 테스트는 기존과 같이 `ubuntu-latest`에서 실행됨
- 전체 CI 결과를 확인하고 기존 테스트 동작이 유지됨
