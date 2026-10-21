# Validator `IsOptional` 변경 구현 기록

## 1. 구현 개요

[요구사항 명세서](./REQUIREMENTS.md)에 따라 Validator 패턴의 공개 이름을
`IsToNone`에서 `IsOptional`로 변경했다. 패턴의 입력 처리와 후속 패턴 실행
동작은 유지하고 기존 이름은 제거했다.

- 구현·검증일: 2026-10-21
- 사용자 관점의 변경 요약: 선택적 값을 처리하는 Validator 패턴 이름을 `IsOptional`로 통일

## 2. 변경 내용

- [Common.py](../../../src/Validator/Patterns/Common.py)에서 클래스를
  `IsToNone`에서 `IsOptional`로 변경하고 모듈의 `__all__`을 갱신했다.
- [Patterns/__init__.py](../../../src/Validator/Patterns/__init__.py)에서
  `IsOptional`을 가져오고 패키지 `__all__`에 공개했다.
- 기존 클래스명과 호환 별칭은 제공하지 않는다. 기존 `IsToNone`을 import하는
  코드는 `IsOptional`로 변경해야 한다.
- `None`이면 후속 패턴을 실행하지 않고 그대로 반환하며, 그 외 값에는 전달된
  패턴을 순서대로 적용한다. `repr`은 새 클래스명을 표시한다.
- [test_validator_patterns.py](../../../tests/test_validator_patterns.py)에
  `None` 처리, 패턴 적용 순서, 예외 전파, 공개 export 및 표현 결과를 확인하는
  테스트 5개를 추가했다.

## 3. 검증 결과

| 검증 항목 | 결과 |
|---|---|
| 신규 Validator 패턴 단위 테스트 | 5개 통과 |
| 테스트 파일 직접 실행 도구 | 테스트를 찾지 못함 |
| Python unittest 직접 실행 | 통과. 저장소의 `src` 패키지를 `DefStream` 이름으로 등록해 테스트 실행 |
| 기존 이름 검색 | 소스의 구현 및 공개 export에서 제거 확인. 테스트는 미노출을 검증하기 위해 이름을 참조 |

테스트는 `python -m unittest discover`의 기본 import 방식으로는 저장소 패키지
이름을 찾지 못해 실행되지 않았다. 테스트 코드에서 현재 소스 패키지를
`DefStream`으로 등록한 뒤 unittest discovery를 실행하여 검증했다. 다른 테스트
파일이나 전체 테스트 스위트는 실행하지 않았다.
