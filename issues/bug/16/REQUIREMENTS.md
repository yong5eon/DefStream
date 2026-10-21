# Inspector Console의 사용자 지정 Task 이름 처리 요구사항

## 목적

Inspector Console이 Task 목록에 표시한 작업 ID로 등록된 Task를 찾아 실행하도록 한다. Task에 사용자 지정 이름이 지정되어 있어도 요청이 잘못 거부되거나 큐 발행 전에 중단되지 않아야 한다.

## 배경

`Specifications.document()`은 `task.name`을 작업 ID로 사용하고, Console UI는 이 ID를 요청에 포함한다. 그러나 `Console.execute()`는 등록된 작업을 찾을 때 `task.__name__`과 요청의 작업 ID를 비교한다.

예를 들어 `Split.name`이 `ETL.OBS.Split`이고 `Split.__name__`이 `Split`이면, 요청 ID `ETL.OBS.Split`과 비교 값이 달라 `Unknown registered task` 오류가 발생한다. 이 오류는 브로커 연결 및 메시지 발행 전에 발생하므로 요청이 큐에 도달하지 않는다.

## 요구사항

1. Console은 요청의 작업 ID와 등록된 Task의 `task.name`을 비교해 실행할 Task를 찾아야 한다.
2. 중복 작업 ID 검사도 `task.name`을 기준으로 수행해야 한다. 같은 이름을 가진 등록 Task가 중복으로 허용되어서는 안 된다.
3. 목록에 표시된 사용자 지정 작업 ID로 요청하면, 해당 Task를 찾지 못했다는 오류로 거부하지 않고 정상적인 실행 절차를 진행해야 한다.
4. 요청 처리 중 오류가 발생하면 경고 로그에 예외 종류뿐 아니라 구체적인 오류 메시지도 기록해야 한다.

## 완료 기준

- `task.name`과 `task.__name__`이 다른 Task를 목록의 작업 ID로 요청해도 올바른 Task가 선택된다.
- 중복 검사와 Task 검색이 모두 `task.name`을 기준으로 일관되게 동작한다.
- 유효한 사용자 지정 작업 ID 요청은 큐 발행 단계까지 진행되며, 해당 요청이 `Unknown registered task` 오류로 중단되지 않는다.
- 오류 로그에서 예외 종류와 구체적인 원인을 확인할 수 있다.
