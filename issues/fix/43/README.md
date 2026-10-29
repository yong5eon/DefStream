# 로거 이름 변경

## 이슈와 작업 상태

- 원본: GitHub Issues [#43](https://github.com/yong5eon/DefStream/issues/43)
- 제목: 로거 이름 변경
- 유형: 변경(`fix`), 원본의 `fix` 레이블 적용 상태 확인 완료
- 작업 대상: `yong5eon/DefStream`, 작업 브랜치 `fix/43`
- 분기 기준: 깨끗한 로컬 `master`의 `23df707`
- 병합 대상: 미지정
- 진행 상태: Broker·Worker·Task·Inspector 로거 이름에 맞춘 테스트·샘플·매뉴얼 변경 및 관련 검증 완료. 패키징 검증은 현재 editable 설치 환경에서 완료하지 못함. 커밋·푸시·PR은 수행하지 않음

## 작업 문서

- [요구사항 명세](./REQUIREMENTS.md)
- [작업 계획](./PLAN.md)
- [구현 종합](./IMPLEMENTS.md)
- [작업·검증 종합](./TASKS.md)
- [변경 로그](./CHANGELOG.md)
- 최신 [구현 기록](./implements/1793261447018.md) 및 [검증 기록](./tasks/1793262314955.md)

## 이슈 원문

### 변경 유형

일반 변경

### 변경 목적

로그 이름이 너무 길어서 로그를 보기에 불편

### 제안하는 변경 내용

DefStream. 프리픽스 제거
브로커 구현체에서 Implements. 제거
