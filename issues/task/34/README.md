# DefStream #34: 공통 지침 변경으로 인한 CI 룰 변경 및 세부 지침 지정

## 이슈 정보

| 항목 | 내용 |
| --- | --- |
| 출처 | GitHub Issues |
| 저장소 | `yong5eon/DefStream` |
| 원본 이슈 | [#34](https://github.com/yong5eon/DefStream/issues/34) |
| 상태 | Open |
| 유형·레이블 | 작업 (`task`, 원본에 적용됨) |
| 담당자 | `yong5eon` |
| 생성·갱신 | 2026-10-25 |
| 작업 브랜치 | `task/34` |
| 병합 대상 브랜치 | `master` |
| 댓글 | 없음 |

## 원본 이슈

### 작업 목적

- 공통 지침이 변경 됨에 따라 변경로그 파일명이 변경됨
- 프로젝트 별 세부 지침 별 별도 지침을 작성

### 작업 내용 및 대상

- .github/workflows/ci.yml 에서 변경 로그 파일 명 변경
- instructions 에 세부 지침 추가

### 완료 기준

- .github/workflows/ci.yml 에서 변경 로그 파일 명이 변경됨
- instructions 에 세부 지침 추가됨

### 관련 자료 및 주의사항

_No response_

## 이슈 기록

- [요구사항 명세서](./REQUIREMENTS.md)
- [작업 계획](./PLAN.md)
- [구현 및 검증 기록](./IMPLEMENTS.md)
- [변경 로그](./CHANGELOG.md)

## 참고

- CI는 릴리즈 변경 로그로 `issues/{branch}/CHANGELOG.md`를 사용하도록 변경했습니다. 이슈 `README.md`는 원문과 메타데이터를 보관하는 문서입니다.
- 프로젝트별 세부 지침의 대상 문서는 `README.md`, `README.en.md`, `README.setup.md`의 작성 규칙입니다.
- 지침 원본은 프로젝트 루트 `instructions/`에 두며, Windows 작업 환경의 `.github/instructions`는 이를 가리키는 디렉터리 정션으로 연결합니다.
- [요구사항 명세서](./REQUIREMENTS.md)에 문서별 역할과 공통 작성 기준을 구체화했습니다.
