# Descriptor 타입 선언과 Pylance 오류 개선

## 변경 요약

Descriptor의 타입 선언을 실제 입력·반환값에 맞췄습니다.
조사 대상 네 파일의 Pylance 오류는 **56건에서 0건**으로 줄었습니다.
분석 설정이나 진단 억제 설정은 변경하지 않았습니다.

## 타입 선언 수정

- `None`을 기본값으로 받는 구체적인 타입 선언 24곳에 `Optional[T]`를 적용했습니다.
- Properties의 `**kwargs`와 조건의 `*args`가 개별 스키마 노드를 나타내도록
  수정했습니다.
- 중첩 object·array·조건·Schema의 입력과 반환 타입을 일치시켰습니다.
- 사용자 mapper가 `Value` 인스턴스가 아니라 파생 클래스를 반환한다는 계약을
  타입 선언에 반영했습니다.
- 기존 JSON Schema 매핑 입력과 Python 3.9 이상 지원 범위를 유지했습니다.

## 실행 동작 수정

- 컬렉션 metadata의 단일 후보를 중복 변환하던 오류를 해결했습니다.
  `Annotated[List[int], {'format': int}]`를 스키마로 변환할 수 있습니다.
- 변환 과정에서 원본 metadata 딕셔너리를 변경하지 않습니다.
- 타입 인자와 metadata의 format이 함께 있으면 타입 인자를 우선합니다.
- Descriptor에 `get(key, default)`를 지원합니다.
  기존 `get(key)`에서 누락 키에 `None`을 반환하는 동작은 그대로입니다.
- 내부 객체 변환기에 dataclass 클래스를 전달하면 인스턴스가 필요하다는
  맥락의 `TypeError`로 거부합니다.

## 호환성 안내

기존 공개 이름이나 import 경로를 변경하지 않았으므로, 정상적인 기존 호출은
수정할 필요가 없습니다. `required`, 기본값, format, 경계, 조건 및 JSON Schema의
null 의미도 유지합니다.

사용자 정의 mapper의 타입 힌트를 작성한다면 반환값은
`Tuple[type[Value], Dict[str, Any]]` 계약에 맞추면 됩니다.
실제 구현도 `String()` 같은 인스턴스가 아니라 `String` 같은 클래스를 반환해야 합니다.
이는 기존 소비 코드가 기대하던 동작을 타입 선언에 반영한 것입니다.

## 검증

- Python 3.12.10 및 3.9.13에서 각각 테스트 **13개 통과**
  - 신규 Descriptor 회귀 테스트 11개
  - 기존 스키마 테스트 2개
- Descriptor 네 파일의 Pylance 오류 0건
- 직접 관련된 Specification·신규 테스트의 Pylance 오류·경고 0건
- 잘못된 스키마 노드 입력을 Pylance가 거부하는지 확인
- 변경 Python 파일의 문법 검사와 `git diff --check` 통과

설치된 과거 패키지가 아닌 현재 저장소 소스를 로드해 검증했습니다.
전체 프로젝트·브로커 실서버 테스트와 다른 Python 버전 실행은 수행하지 않았습니다.

## 상세 기록

- [요구사항 명세서](./REQUIREMENTS.md)
- [구현 및 검증 기록](./IMPLEMENTS.md)
- [Descriptor 회귀 테스트](../../../tests/test_descriptor.py)
