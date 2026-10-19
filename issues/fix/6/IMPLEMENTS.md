# Descriptor Pylance 문제 개선 구현 기록

## 1. 구현 개요

[요구사항 명세서](./REQUIREMENTS.md)에 따라 Descriptor의 타입 선언을 실제 동작에
맞추고, 타입 불일치와 직접 연결된 컬렉션 metadata 변환 결함을 수정했다.

- 대상 브랜치: `fix/6`
- 수정 전 조사 기준: `c8f48a2`
- 구현·검증일: 2026-10-19
- 사용자 관점의 변경 요약: [변경 로그](./README.md)

분석 설정 변경이나 진단 억제 없이 대상 네 파일의 Pylance 오류를
56건에서 0건으로 줄였다.

## 2. 타입 계약 수정

### nullable 선언

[Value.py](../../../src/Descriptor/Value.py),
[Types.py](../../../src/Descriptor/Types.py),
[DataObject.py](../../../src/Descriptor/DataObject.py)의
`None` 기본값과 불일치하던 구체적인 타입 선언 24곳을 `Optional[T]`로 수정했다.
기존 `Any = None`과 dataclass의 `MISSING`은 유지했다.
기본값과 JSON Schema의 null 표현 규칙을 바꾸지는 않았다.

### Descriptor와 가변 인자

- [Descriptor](../../../src/Descriptor/Value.py)는 `Mapping[str, Any]` 계약을
  명시한다. 내부 딕셔너리와 iterator·view의 타입도 명시했다.
- 이종 스키마 키워드를 받는 `Descriptor.__init__`의 `**kwargs`는 개별 값의
  타입을 나타내도록 수정했다.
- [Properties](../../../src/Descriptor/Types.py)는 개별 속성으로
  `Descriptor`, `Condition`, `Schema`를 받는다. Schema를 펼친 값을
  기존 인자 딕셔너리에 다시 대입하지 않고 새 매핑을 구성한다.
- [Condition·OneOf](../../../src/Descriptor/Value.py)의 `*args`는 iterable이
  아니라 인자 하나의 스키마 노드 타입을 나타낸다.
- `get(key, default)`를 지원해 부모 Mapping 계약과 맞췄다.
  기존 `get(key)`의 누락 키 처리 결과인 `None`은 유지한다.

### 스키마 노드와 확장 계약

- [Array](../../../src/Descriptor/Types.py)의 items 선언과
  [변환기](../../../src/Descriptor/DataObject.py)의 반환 타입에
  `Array`·`Object`를 포함한 Descriptor, Condition, Schema를 반영했다.
- [Schema](../../../src/Descriptor/Value.py)는 JSON Schema 매핑, 조건,
  중첩 Schema를 허용한다. Descriptor는 Mapping 계약을 통해 수용한다.
  이는 [Specification](../../../src/Worker/Specification.py)의 기존 매핑 입력을
  보존하기 위한 조치이며, 해당 호출부의 구현 변경은 필요하지 않았다.
- [TypeMapper](../../../src/Descriptor/Value.py)의 반환 계약을
  `Value` 인스턴스가 아닌 `Value` 파생 클래스와 생성 인자 딕셔너리로 수정했다.
  소비 측의 `issubclass()` 및 클래스 생성과 일치시켰다.

## 3. 변환 로직 수정

### 타입 표현식 분석

[DataObjectToSchema](../../../src/Descriptor/DataObject.py)는 입력 타입 표현식을
`object`로 받고, `get_origin()`을 한 번 호출해 별도 변수로 분석한다.
일반 클래스와 typing 표현식을 같은 `type` 변수에 재대입하지 않는다.
사용자 mapper에는 일반 클래스만 전달한다.

타입 인자가 없는 기존 `typing.List`·`Tuple`·`Set`·`Dict`는 원점 타입으로
정규화하여 기존 지원을 유지한다. 상속 계층 재설계나 새로운 타입 처리 의존성은
추가하지 않았다.

### 컬렉션 metadata

- 반복 가능한 후보를 튜플로 정규화한 뒤 각 후보를 한 번만 변환한다.
- 단일 후보는 직접 items가 되고, 복수 후보는 `OneOf`가 된다.
- `Iterable`에 직접 `len()`이나 인덱싱을 요구하지 않는다.
- metadata 딕셔너리를 변경하지 않으므로 동일 모델의 반복 변환 결과가 유지된다.
- `Annotated[List[int], {'format': int}]`에서 발생하던 `TypeError`를 해결했다.
- 타입 인자와 metadata의 format이 동시에 있으면 타입 인자를 우선한다.
  이전에 중복 인자 전달이나 재변환으로 실패할 수 있던 조합을 테스트로 고정했다.
- 미지원 후보는 기존처럼 명시적으로 실패하며, 빈 스키마 등의 폴백은 추가하지 않았다.

### dataclass 인스턴스 경계

[DataObjectToObject](../../../src/Descriptor/DataObject.py)는
dataclass 클래스와 인스턴스를 구분하고, 인스턴스만 `asdict()`에 전달한다.
클래스·비-dataclass 입력은 맥락을 알 수 있는 `TypeError`로 거부한다.
공개 `ToObject()`의 기존 입력 계약과 성공 결과는 유지한다.

## 4. 테스트와 실행 방식

[test_descriptor.py](../../../test/test_descriptor.py)에 회귀 테스트 11개를 추가했다.

- nullable 기본값과 타입 힌트의 일치
- 중첩 object·array·Schema와 조건 조합
- 매핑 조회·수정·삭제·view 및 기본값을 받는 `get()`
- 기본 dataclass 타입과 타입 인자 없는 typing 컨테이너
- Optional·Union·중첩 dataclass와 기본값
- metadata 단일·복수·반복 가능한 후보, 원본 보존 및 반복 변환
- 미지원 metadata 후보의 명시적 실패
- 사용자 mapper·encoder
- dataclass 클래스·인스턴스 입력 경계
- format·경계·명시적 `None`
- JSON Schema 매핑과 Specification 호환성

기존 [스키마 테스트](../../../test/test_specifications.py)의 다음 두 테스트를
함께 실행했다.

- `test_original_descriptor_and_validator_api_without_datamodel`
- `test_schema_conditions_bounds_defaults_and_unsupported_values`

VS Code 테스트 도구에서는 테스트를 찾지 못해 `unittest`를 직접 실행했다.
가상환경에 설치된 과거 패키지가 검증되지 않도록 `importlib.util`의
`spec_from_file_location()`과 `submodule_search_locations`로 현재 저장소의
패키지를 로드하고 `sys.modules`에 등록했다.
테스트 전에 Descriptor의 `__file__`이 현재 저장소 소스인지 assert로 확인했다.

## 5. 검증 결과

| 검증 항목 | 결과 |
|---|---|
| Python 3.12.10 | 신규 11개와 기존 2개, 총 13개 통과 |
| Python 3.9.13 | 동일한 13개 통과 |
| Descriptor 네 파일 Pylance 오류 | 56건 → 0건 |
| Descriptor 미사용 힌트 | 5건 → 4건. 미사용 import를 정리하고 추상·미구현 메서드 인자는 유지 |
| Specification 및 신규 테스트 Pylance 진단 | 오류·경고 0건 |
| 호출 호환성 | Descriptor·Schema·Properties·Array·OneOf 및 변환기의 조회된 호출부 호환 확인 |
| 잘못된 타입 입력 | 임시 검사 파일의 `Properties(a=123)`·`Array(format=123)`에서 각각 `reportArgumentType` 확인 |
| 정상 타입 입력 | 같은 임시 파일의 정상 Properties·Schema·Array 사용에 오류 없음 |
| 문법 | 수정한 Python 파일 4개 검사 통과 |
| 공백 | `git diff --check` 통과 |

임시 타입 검사 파일은 검증 후 삭제했다.
Pylance 유효 설정은 기존 `basic`, `openFilesOnly`,
`strictParameterNoneValue=true`를 유지했다.

전체 프로젝트 테스트, 브로커 실서버 테스트 및 Python 3.10·3.11·3.13·3.14 실행은
수행하지 않았다. 위 결과는 해당 범위까지 검증했다는 의미가 아니다.
커밋·배포·패키지 재설치는 수행하지 않았다.
