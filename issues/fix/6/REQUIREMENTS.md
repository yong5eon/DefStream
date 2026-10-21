# Descriptor Pylance 문제 개선 요구사항 명세서

## 1. 목적과 작업 상태

Descriptor의 실제 입력·반환값과 타입 선언을 일치시켜 정상적인 사용 코드에서
Pylance 오류가 발생하지 않게 한다. 특히 `int = None`과 같은 선언은
`Optional[int] = None`으로 변경한다.

- 조사일: 2026-10-19
- 조사 기준: `fix/6`, 커밋 `c8f48a2`
- 초기 작업은 문제 조사와 명세서 작성으로 제한했으며, 후속 요청에 따라 구현했다.
- 구현 상태: 타입 계약 및 관련 실행 결함 수정 완료. 분석 설정은 변경하지 않았다.
- 관련 문서: [구현 기록](./IMPLEMENTS.md), [변경 로그](./README.md)
- 첨부된 읽기 전용 스냅샷은 참고 자료이며 수정 대상이 아니다.
  진단 위치와 구현 기준은 저장소의 실제 소스를 따른다.

## 2. 조사 범위와 방법

### 2.1. 대상

| 파일 | 조사 대상 |
|---|---|
| [Value.py](../../../src/Descriptor/Value.py) | Descriptor 매핑, 기본 값, 조건, Schema, mapper·encoder 계약 |
| [Types.py](../../../src/Descriptor/Types.py) | 기본 타입, Properties, Object, Array 생성자 |
| [DataObject.py](../../../src/Descriptor/DataObject.py) | dataclass 타입 해석, 스키마 변환, 객체 변환 |
| [공개 API](../../../src/Descriptor/__init__.py) | ToSchema·ToObject의 인자 전달과 직렬화 |
| [기존 테스트](../../../tests/test_specifications.py) | 스키마 조합, dataclass 변환, 기본값과 실패 계약 |

### 2.2. 확인 방법과 환경

- Pylance의 `textDocument/diagnostic`으로 대상 네 파일을 각각 조회했다.
  `openFilesOnly` 설정에서 열린 파일에 표시되는 오류만으로 전체를 추정하지 않았다.
- Pylance hover로 `Properties.__init__`의 가변 키워드 인자 타입을 확인했다.
- 편집기 유효 설정은 `typeCheckingMode=basic`,
  `diagnosticMode=openFilesOnly`, `strictParameterNoneValue=true`이다.
  `diagnosticSeverityOverrides`는 비어 있다.
- Pylance 선택 인터프리터는 `d:\Y5N\DefStream\.venv\Scripts\python.exe`이며,
  해당 인터프리터에서 실행한 Python 버전은 `3.12.10`이다.
- 최초 일반 import는 가상환경의 설치 패키지를 읽었다. 이를 저장소 검증으로
  간주하지 않고, 현재 저장소의 패키지를 명시적으로 로드한 후 재실행했다.
  최종 실행에서 [공개 API](../../../src/Descriptor/__init__.py)의
  `__file__`이 현재 저장소 소스인지 assert로 확인했다.
- 전체 워크스페이스, 브로커 어댑터, strict 모드의 오류 수를 조사한 것은 아니다.
  Pylance 버전 및 다른 Python 버전에서의 실행 결과는 이번에 확인하지 않았다.

## 3. 실제 Pylance 진단 기준선

아래 수치는 조사 시점의 마지막 파일별 진단 결과이다. 위치는 1부터 시작하며,
구현 후 줄 번호는 바뀔 수 있다. 오류 수는 원인 수가 아니라 진단 발생 수이다.

| 파일 | 오류 | 힌트 | 진단 코드별 오류 수 |
|---|---:|---:|---|
| [Types.py](../../../src/Descriptor/Types.py) | 19 | 0 | `reportArgumentType` 19 |
| [Value.py](../../../src/Descriptor/Value.py) | 6 | 3 | `reportArgumentType` 6 |
| [DataObject.py](../../../src/Descriptor/DataObject.py) | 28 | 2 | `reportArgumentType` 17, `reportAssignmentType` 1, `reportReturnType` 8, `reportIndexIssue` 1, `reportGeneralTypeIssues` 1 |
| [공개 API](../../../src/Descriptor/__init__.py) | 3 | 0 | `reportArgumentType` 3 |
| 합계 | **56** | **5** | 오류 56건, 별도의 미사용 힌트 5건 |

### 3.1. 원인별 문제 목록

| ID | 우선순위 | 위치 | 확인된 문제와 영향 |
|---|---|---|---|
| DSP-01 | 높음 | [Types.py](../../../src/Descriptor/Types.py#L26), [Value.py](../../../src/Descriptor/Value.py#L78), [DataObject.py](../../../src/Descriptor/DataObject.py#L44) | `None` 기본값을 비-nullable 타입에 지정했다. 생성자·변환 함수의 선언 자체에서 `reportArgumentType`이 발생한다. 직접적인 선언 불일치는 총 24곳이다. |
| DSP-02 | 높음 | [Descriptor 생성자](../../../src/Descriptor/Value.py#L24), [Properties 생성자](../../../src/Descriptor/Types.py#L186) | `**kwargs: Dict[str, T]`가 각 키워드의 값을 `Dict`로 선언한다. 키워드 전체의 딕셔너리 타입을 선언한 것이 아니다. `type=Type.Object`, `properties=Properties()`, `a=Integer()` 같은 정상 인자와 Schema를 펼친 값의 재대입에서 `reportArgumentType`이 발생한다. |
| DSP-03 | 높음 | [Schema](../../../src/Descriptor/Value.py#L103), [Array](../../../src/Descriptor/Types.py#L214), [Properties](../../../src/Descriptor/Types.py#L185), [변환 반환 타입](../../../src/Descriptor/DataObject.py#L53) | 스키마로 사용하는 타입을 `Value` 중심으로 제한했다. `Array`와 `Object`는 `Value`가 아니라 `Descriptor`의 직접 하위 클래스이며, `OneOf`는 `Condition`이다. 실제 반환 분기와 선언이 달라 `reportReturnType` 8건 및 인자 오류가 발생한다. |
| DSP-04 | 높음 | [OneOf](../../../src/Descriptor/Value.py#L114) | `*args: Iterable[Union[Value, Schema]]`는 각 위치 인자를 iterable로 요구한다. 실제 호출은 개별 스키마 노드를 전달하므로 `OneOf(*fs)`에서 `reportArgumentType`이 발생한다. |
| DSP-05 | 높음 | [타입 원점 해석](../../../src/Descriptor/DataObject.py#L62) | `o: type`에 `get_origin()` 결과를 다시 대입하며 `Union` 같은 typing 표현식도 전달한다. 일반 클래스와 타입 표현식의 계약이 섞여 `reportAssignmentType`, `reportArgumentType`이 발생한다. |
| DSP-06 | 높음 | [컬렉션 metadata 처리](../../../src/Descriptor/DataObject.py#L259) | `Iterable`만 확인하고 `len()`과 인덱싱을 사용한다. 같은 metadata 값을 타입 목록과 변환된 노드로 바꿔 재사용해 `reportArgumentType`, `reportIndexIssue`, `reportGeneralTypeIssues`가 발생한다. 실행 오류도 재현됐다. |
| DSP-07 | 높음 | [TypeMapper](../../../src/Descriptor/Value.py#L125), [mapper 사용](../../../src/Descriptor/DataObject.py#L326) | 반환 타입은 `Value` 인스턴스인데 소비 코드는 `issubclass(V, Value)` 및 `V(**kwargs)`로 클래스를 기대한다. `issubclass`에 대한 `reportArgumentType`이 발생한다. |
| DSP-08 | 중간 | [Descriptor.get](../../../src/Descriptor/Value.py#L61) | `key: object`를 문자열 키로 추론된 내부 dict의 `get()`에 전달해 `reportArgumentType`이 발생한다. 매핑의 키·값 타입과 상속 계약을 함께 검토해야 한다. |
| DSP-09 | 중간 | [DataObjectToObject](../../../src/Descriptor/DataObject.py#L376) | `is_dataclass()`만으로는 dataclass 클래스와 인스턴스를 구분하지 못한다. `asdict()`에 클래스가 전달될 가능성 때문에 `reportArgumentType`이 발생한다. |
| DSP-10 | 중간 | [ToSchema](../../../src/Descriptor/__init__.py#L157), [ToObject](../../../src/Descriptor/__init__.py#L172) | 공개 함수의 인자는 이미 `Optional`이지만 내부 수신 인자는 그렇지 않아 전달 지점에서 `reportArgumentType` 3건이 발생한다. 호출자 측 문제가 아닌 내부 계약의 불일치이다. |

### 3.2. 오류와 구분할 항목

- [Value.py](../../../src/Descriptor/Value.py)의 미사용 `Sequence` import 및
  추상 호출 메서드의 `o` 매개변수, [SchemaToDataObject](../../../src/Descriptor/DataObject.py#L44)의
  미사용 `o`·`name`은 총 5건의 힌트이다. 오류 56건과 합산해 오류라고 표현하지 않는다.
- `Dict`, `Iterable`, `Iterator`, 각종 view의 타입 인자가 생략된 곳이 있다.
  타입 정보 개선 대상이지만, 이번 basic 진단에서 모두 독립적인 오류로 보고된 것은 아니다.
- `SchemaToDataObject()`는 기존부터 `NotImplementedError`를 발생시킨다.
  이번 타입 개선을 이유로 역변환 기능을 새로 구현하지 않는다.

## 4. 로컬 소스로 확인한 실행 사실

다음은 현재 동작을 확인한 소규모 실행 결과이며, 전체 회귀 테스트 통과를 뜻하지 않는다.

| 입력·경로 | 확인 결과 | 명세상 취급 |
|---|---|---|
| `Object(properties=Properties(items=Array(format=Object())))`를 Schema로 감싸 직렬화 | 중첩 object·array의 스키마를 생성한다. 바깥 `required`는 `['items']`이다. | 현재 성공하는 사용법을 타입 계약도 허용해야 한다. |
| dataclass의 `value: Optional[int] = None`을 `ToSchema()`로 변환 | integer 속성에 `default: None`이 있고, 바깥 `required`는 빈 목록이다. | 기존 결과를 보존한다. 이번 작업에서 JSON Schema null 허용 의미를 재설계하지 않는다. |
| dataclass의 `value: Union[int, str]`을 `ToSchema()`로 변환 | integer와 string을 멤버로 하는 `oneOf`가 생성된다. | 정상 반환값인 `Condition` 계열을 타입 선언에도 반영한다. |
| dataclass의 `value: Annotated[List[int], {'format': int}]`을 `ToSchema()`로 변환 | `TypeError: type is not a supported type`이 발생한다. | DSP-06의 관련 실행 결함이다. 기대하는 array item 타입을 고정하는 재현 테스트를 작성한 뒤 개선한다. |
| 내부 변환기 `DataObjectToObject()(DataclassClass)` | `TypeError: asdict() should be called on dataclass instances`가 발생한다. | 클래스는 변환 대상이 아니다. 공개 API와 내부 변환기의 인스턴스 계약을 일치시킨다. |

## 5. 기능·타입 요구사항

### 5.1. nullable 선언

| ID | 요구사항 |
|---|---|
| DSR-01 | `None`을 허용하는 구체적인 타입은 `Optional[T]`로 선언한다. 예: `int = None` → `Optional[int] = None`, `str = None` → `Optional[str] = None`. `T \| None` 표기로 대체하지 않는다. |
| DSR-02 | `Union` 타입도 `Optional[Union[...]]`로 감싼다. 값의 생략 가능성과 `None` 허용 여부를 구분하며, 기본값과 실행 로직은 타입 수정만을 이유로 변경하지 않는다. |
| DSR-03 | nullable 수정을 내부 수신 함수까지 연결해 DSP-10의 전파 오류도 제거한다. `Any = None`은 이미 `None`을 허용하므로 기계적으로 `Optional[Any]`로 바꾸지 않는다. `MISSING`도 `None`으로 바꾸지 않는다. |

반드시 검토할 직접적인 선언 불일치 24곳은 다음과 같다.

| 파일 | 대상 | 수 |
|---|---|---:|
| [Types.py](../../../src/Descriptor/Types.py) | `Boolean.description`; `Integer`·`Number`·`String`의 `description`, `format`; `BinaryBase64Encoded`·`Binary`의 `description`, `default`; `Object.default`; `Array.description`, `default` | 14 |
| [Value.py](../../../src/Descriptor/Value.py) | `Value.description`, `Value.format`, `Schema.format`, `OneOf.discriminator` | 4 |
| [DataObject.py](../../../src/Descriptor/DataObject.py) | `SchemaToDataObject.name`, `DataObjectToSchema.mapper`, `__value__.format`, `__value__.description`, `__call__.description`, `DataObjectToObject.encoder` | 6 |

`int = None`은 변경 원칙의 예시이며, 조사 대상에 해당 선언이 실제로 있었다는 뜻은 아니다.

### 5.2. 스키마 노드와 가변 인자 계약

| ID | 요구사항 |
|---|---|
| DSR-04 | `Descriptor.__init__`의 `**kwargs`는 각 스키마 키워드 값의 타입을 나타낸다. `type`, 설명, 속성, 조건, 기본값 등의 이종 값을 보관할 수 있어야 하며, 키워드 전체를 `Dict` 값으로 요구하지 않는다. |
| DSR-05 | `Properties.__init__`의 `**kwargs`는 각 속성의 스키마 노드를 나타낸다. `Value`뿐 아니라 `Array`·`Object`를 포함하는 `Descriptor`, `Condition`, `Schema`를 허용한다. `Schema`를 펼친 값을 다른 타입의 변수에 잘못 재대입하지 않는다. |
| DSR-06 | `Schema.format`, `Array.format`, 조건의 멤버 및 `__value__()`의 반환 타입은 실제 생성하는 노드를 빠짐없이 표현한다. `Schema.format=None`이라는 기존 생략 가능한 선언을 임의로 필수화하지 않는다. |
| DSR-07 | `OneOf`의 `*args`는 인자 하나의 노드 타입으로 선언한다. `Condition`·`AllOf`도 같은 입력 단위와 일치시킨다. 노드를 불필요한 리스트로 감싸는 등 호출부를 잘못된 선언에 맞추지 않는다. |
| DSR-08 | `TypeMapper.__call__`은 인스턴스가 아니라 생성 가능한 `Value` 파생 클래스와 키워드 인자 딕셔너리를 반환하는 계약에 맞춘다. 소비 측의 `issubclass`·생성 처리와 호환되어야 하며, 미지원 타입에 대한 기존의 명시적 실패를 유지한다. |

### 5.3. 내부 구현과의 일치

| ID | 요구사항 |
|---|---|
| DSR-09 | 일반 Python 클래스와 `Union`·`Annotated`·제네릭 등의 타입 표현식을 구분한다. `get_origin()` 결과를 한 번 조회해 지역 변수로 좁히고, `None`일 수 있는 값을 `type` 변수에 재대입하지 않는다. 모두 일괄적으로 `Any`로 바꿔 해결한 것으로 처리하지 않는다. |
| DSR-10 | 컬렉션 처리에서는 반복 가능함과 길이 조회·인덱싱 가능함을 구분한다. 입력 타입 표현식, 정규화한 후보 목록, 생성한 스키마 노드를 별도 지역 변수로 다룬다. 단일 후보를 변환한 뒤 다시 후보 목록처럼 반복하지 않는다. |
| DSR-11 | DSP-06의 metadata 경유 단일 후보는 한 번만 변환한다. 재현 입력에서 생성하는 속성은 `type: array`, `items: {'type': 'integer'}`이어야 한다. metadata 지정과 타입 인자의 우선순위는 기존 성공 예시를 테스트로 고정하고, 별도 승인 없이 변경하지 않는다. |
| DSR-12 | `Descriptor`의 문자열 키·이종 값 매핑 타입을 명시하고, `get()`을 포함한 메서드를 부모 `Mapping` 계약과 일치시킨다. 기존 단일 인자 호출에서 키 누락 시 `None`을 반환하는 동작은 유지한다. 현재 사용자 정의 `get()`은 `default` 인자를 받지 않으므로, 부모 계약에 맞추는 과정의 차이를 구현 시 명시하고 검증한다. |
| DSR-13 | `DataObjectToObject`는 dataclass 클래스와 인스턴스를 구분한다. 클래스·비-dataclass 입력은 맥락을 알 수 있는 `TypeError`로 거부하며, `asdict()`에는 dataclass 인스턴스만 전달한다. 공개 `ToObject()`의 기존 입력 거부와 성공 결과를 유지한다. |
| DSR-14 | 생략된 컨테이너 타입 인자, 변경하는 공개 시그니처의 반환 타입, 콜백 계약을 필요한 범위에서 명시한다. 스키마 키워드나 JSON 경계에서 실제 이종 값을 다루는 `Any`까지 일괄 금지하지 않는다. |

## 6. 호환성과 범위 제한

- [setup.py](../../../setup.py)에 선언된 Python 3.9 이상 지원 범위를 유지한다.
  최신 Python 전용 타입 문법을 도입해 지원 하한을 올리지 않는다.
- 공개 클래스명, export, 위치·키워드 인자명, 기본값을 유지한다.
  `Object`·`Array`를 `Value`의 파생으로 바꾸는 등의 계층 재설계는 하지 않는다.
- `required`, `default`, `minimum`·`maximum`, `minLength`·`maxLength`,
  enum·format, 중첩, `oneOf`·`allOf`의 기존 출력을 유지한다.
- `None` 타입 주석 수정과 JSON Schema의 null 표현 추가는 별개 변경이다.
  nullable 스키마, Union의 의미, default 채택 규칙을 함께 재설계하지 않는다.
- `# type: ignore`, 진단 비활성화, 분석 모드 변경, 근거 없는 cast,
  모든 인자를 `Any`로 만드는 방식으로 진단을 숨기지 않는다.
- 예외 무시나 빈 스키마 등의 성공처럼 보이는 폴백을 추가하지 않는다.
- 노드 타입 공통화가 필요하더라도 순환 import를 피하는 최소한의 타입 정의로 제한한다.
  범용 타입 처리 프레임워크나 새로운 의존성을 추가하지 않는다.
- 변경 대상은 Descriptor, 직접 영향받는 호출부, 관련 테스트와 문서로 제한한다.
  Worker·Validator 전체 타입 수정이나 RabbitMQ·Redis 어댑터의 일괄 수정은 범위 밖이다.
- 기존 미사용 힌트는 이번 필수 완료 조건으로 삼지 않는다.
  추상 메서드의 인자명을 힌트 제거만을 목적으로 바꾸지 않는다.
- 브랜치 생성, 커밋, 빌드 패키지 재설치, 배포는 이번 명세서 작성 작업에 포함하지 않는다.

## 7. 구현 후 인수 기준

| ID | 검증 | 합격 조건 |
|---|---|---|
| DSA-01 | 동일한 유효 설정에서 네 대상 파일을 개별 Pylance 재진단 | 대상 파일의 severity 1 진단이 56건에서 0건이 된다. 새로운 경고·오류를 만들지 않는다. 힌트 수와 분리해 기록한다. |
| DSA-02 | nullable 선언 목록과 타입 힌트 검증 | 24곳에 `Optional`을 적용하고, 이미 nullable인 수신·전달부도 일치한다. 명시적 `None`과 인자 생략을 모두 검증한다. |
| DSA-03 | 공개 API를 사용하는 타입 검사 코드 | `Properties(a=Integer())`, `Schema('Object', Object())`, `Array(format=Object())`, `OneOf(Integer(), String())`, `AllOf(Integer(), Integer())`, Schema를 포함한 중첩이 타입 오류가 되지 않는다. |
| DSA-04 | 반환 분기 포괄 | 기본형, 배열, 객체, Union, dataclass를 반환하는 분기가 선언과 일치한다. 타입 주석을 좁히려고 성공 분기를 삭제하지 않는다. |
| DSA-05 | mapper·encoder 회귀 | `Value` 파생 클래스를 반환하는 사용자 mapper와 기존 JSON encoder 경로가 성공하고, 미지원 입력은 명시적으로 실패한다. |
| DSA-06 | 컬렉션 metadata 재현 테스트 | `Annotated[List[int], {'format': int}]`이 DSR-11의 출력이 된다. 단일·복수 후보의 기존 성공 경로도 유지한다. 잘못된 입력의 예외를 숨기지 않는다. |
| DSA-07 | 매핑 계약 | 조회·설정·삭제, 반복, 길이, 각 view, 기존 `get(key)`, 누락 키 및 부모 계약과의 일치를 확인한다. |
| DSA-08 | dataclass 경계 | dataclass 인스턴스의 `ToObject()`는 기존처럼 성공한다. 클래스와 비-dataclass 입력은 공개 API·내부 변환기에서 `TypeError`가 된다. |
| DSA-09 | 기존 스키마 출력 | 중첩, Optional, Union, forward reference, dataclass의 `default_factory`, 경계, 조건의 기존 출력이 일치하고 미지원 값은 실패한다. |
| DSA-10 | 검증 대상과 지원 버전 | 설치된 과거 패키지가 아니라 수정한 소스를 검증했다는 증거를 남긴다. Python 3.9 호환성을 확인하고 실행한 버전과 미실행 버전을 구분한다. |

타입 검사 코드는 잘못된 입력을 실수로 허용하지 않는지도 확인한다.
예를 들어 `Properties(a=123)`이나 `Array(format=123)`을 정상 노드로
취급하지 않는다. 실행 시점의 검증만으로 정적 타입 계약 검증을 대체하지 않는다.

## 8. 구현·검증 순서

1. 구현 전에 네 파일의 진단을 다시 수집하고 현재 변경 사항과 본 기준선을 비교한다.
2. 노드 타입·가변 인자·nullable·mapper 선언을 일치시키고 호출 호환성을 확인한다.
3. 타입 표현식 좁히기, metadata 정규화, dataclass 인스턴스 판정을 수정한다.
4. 대응하는 최소 타입 검사 예제와 회귀 테스트를 추가한다.
5. [기존 Descriptor 관련 테스트](../../../tests/test_specifications.py)의
   `test_original_descriptor_and_validator_api_without_datamodel`과
   `test_schema_conditions_bounds_defaults_and_unsupported_values`를 먼저 실행한다.
   추가 테스트도 함께 검증하고, 필요하면 관련 Specification 테스트로 넓힌다.
6. 네 파일과 수정한 직접 호출부를 Pylance로 재진단하고 건수와 규칙을 기록한다.

초기 명세서 작성 단계에서는 회귀 테스트나 수정 후 진단 검증을 실행하지 않았다.
제4절은 수정 전 조사 증거이며, 후속 구현 결과는 다음 절에 구분해 기록한다.

## 9. 구현 결과와 검증 기록

### 9.1. 변경 사항

- [Value.py](../../../src/Descriptor/Value.py): 문자열 키·이종 값 매핑을 명시하고
  `get(key, default)`를 지원한다. 기존 `get(key)` 동작은 그대로 유지한다.
  nullable 선언, 조건의 개별 인자 타입, mapper의 클래스 반환 계약을 수정했다.
- [Types.py](../../../src/Descriptor/Types.py): nullable 선언과 가변 키워드 인자를
  수정하고, 중첩 object·array·조건을 허용한다. Properties를 구성할 때 입력 인자
  딕셔너리에 다른 타입의 값을 다시 대입하지 않는다.
- [DataObject.py](../../../src/Descriptor/DataObject.py): 타입 표현식은 `object`로
  받고 `get_origin()`을 별도 변수로 분석한다. 실제 반환하는 Descriptor·Condition·Schema를
  선언에 포함하고, mapper 호출 전에는 일반 클래스인지 확인한다.
  타입 인자가 없는 기존 `typing.List`·`Tuple`·`Set`·`Dict`도 원점 타입으로
  정규화하여 기존 지원을 유지한다.
- 컬렉션 metadata는 후보 목록으로 정규화한 뒤 한 번만 변환한다.
  metadata 딕셔너리를 변경하지 않으며, 단일 후보는 직접 items가 되고
  복수 후보는 `OneOf`가 된다. 반복 가능한 후보에는 길이·인덱싱을 직접 요구하지 않는다.
- dataclass 인스턴스만 `asdict()`에 전달한다. 내부 변환기도 클래스·비-dataclass
  입력을 맥락이 있는 `TypeError`로 거부한다.
- 시그니처 호환성 검사에서 [Specification](../../../src/Worker/Specification.py)의
  기존 JSON Schema 매핑 입력 경로를 확인했다. 이 계약을 유지하도록 `Schema.format`은
  `Mapping[str, Any]`도 허용한다. Descriptor도 이 Mapping 계약을 만족한다.
  이미 실행 가능했던 중첩 `Schema`도 타입에 포함했다.
- metadata와 타입 인자의 format이 동시에 존재하면 타입 인자를 우선한다.
  변경 전 이 조합은 중복 format 전달이나 잘못된 재변환으로 실패할 수 있었으므로,
  기존 구조에서 의도한 명시적 format 우선 경로를 구현하고 테스트로 고정했다.
  기존 성공 출력이나 JSON Schema null 의미는 변경하지 않았다.

### 9.2. 검증 결과

| 항목 | 결과 |
|---|---|
| 대상 네 파일의 Pylance 오류 | **56건 → 0건** |
| 대상 네 파일의 미사용 힌트 | 5건 → 4건. 사용하지 않는 import 1개를 정리했고, 미구현·추상 메서드 인자는 유지했다. |
| 직접 호출부 | Specification의 Pylance 오류 0건 |
| 신규 테스트 파일 | [test_descriptor.py](../../../tests/test_descriptor.py)의 Pylance 오류·경고 0건 |
| 문법·공백 | 변경한 Python 파일 4개의 문법 검사 및 `git diff --check` 통과 |
| Python 3.12.10 | 신규 회귀 테스트 11개 및 기존 스키마 테스트 2개, 총 **13개 통과** |
| Python 3.9.13 | 동일한 테스트 **13개 통과** |
| 잘못된 타입 입력 | 임시 타입 검사 파일에서 `Properties(a=123)` 및 `Array(format=123)`가 각각 `reportArgumentType`으로 거부됨을 확인했다. 정상 노드 3개 사용에는 오류가 없었고, 검사 파일은 삭제했다. |
| 검증 소스 | 두 Python 실행 모두 현재 저장소의 Descriptor를 명시적으로 로드하고 `__file__` 경로를 assert로 검증했다. 설치된 과거 패키지를 테스트하지 않았다. |

신규 테스트는 nullable 선언, 중첩 노드·조건, 기본값과 format, 매핑 계약,
기본 dataclass 타입별 반환 분기, Optional·Union, metadata 변환·원본 보존,
사용자 mapper·encoder, dataclass 입력 경계와 JSON Schema 매핑 호환성을 검증한다.

VS Code 테스트 실행 도구에서는 테스트를 찾지 못해, 동일한 인터프리터의
`unittest`를 직접 실행했다. 전체 프로젝트·브로커 실서버 테스트와
Python 3.10·3.11·3.13·3.14 실행은 이번 검증 범위에 포함하지 않았다.
