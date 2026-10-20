# Run 에 이름(name)과 설명(description) 지원

## 변경 요약

Run 정의에서 `name`과 `description`을 지정할 수 있습니다. 지정한 이름은 AsyncAPI
`operations`와 Metrics의 작업 키에서 함께 사용됩니다. `name`을 생략하면
`모듈명.__qualname__`이 기본 이름입니다.

## 사용 방법

```python
from DefStream.Worker import Run, Specification


class Add(
  Run,
  name='add',
  description='Add two integers',
  request=Specification(schema=request_schema),
  response=Specification(schema=response_schema),
):
  def run(
    self,
    a: int,
    b: int,
  ):
    return a + b
```

Run 등록 후 AsyncAPI Operation 키와 Metrics 작업 식별자는 `add`입니다.
명시적 이름은 영문 대소문자·숫자·`_`·`.`·`-`로만 구성된 한 글자 이상의 문자열입니다
(`Orders.create-v2_Job` 등). 위치 제한은 없고 Python 예약어도 허용합니다.
공백·한국어·그 외 문자는 허용하지 않으며, 입력을 변환하지 않고 대소문자를
구분합니다. Worker에 같은 이름을 가진 Run을 함께 등록할 수 없습니다.

## 기존 코드에 미치는 영향

- `Specification(description=...)`는 제거되었습니다. 설명을 Run의
  `description`으로 옮기세요. 설명은 AsyncAPI Operation에 반영되며 메시지 설명에는
  적용하지 않습니다.
- AsyncAPI Operation의 기본 키는 클래스명에서 `모듈명.__qualname__`으로
  변경됩니다. Operation 키를 사용하는 클라이언트 설정도 갱신하세요.
- Metrics의 기본 작업 키는 기존 qualified 클래스 이름 형식과 같습니다.
- Run 하위 클래스는 상위 Run의 `name`이나 `description`을 상속하지 않습니다.
