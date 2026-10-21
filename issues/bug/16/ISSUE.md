# Inspector Console에서 사용자 지정 Task 이름으로 요청 시 큐 발행 전에 거부됨

## 버전

0.1.12

## 내용

Inspector Console이 Task 목록에 표시하는 이름과 실제 Task를 찾는 기준이 다릅니다.

Specifications.document()은 task.name을 작업 ID로 사용합니다. Console UI는 이 ID를 선택해 요청을 보내지만, Console.execute()는 등록된 작업을 찾을 때 task.__name__과 요청의 task 값을 비교합니다.

예를 들어 Orbis Split은 Split.name이 ETL.OBS.Split이고 Split.__name__은 Split입니다. 따라서 UI에서 선택한 작업 ID ETL.OBS.Split과 Console의 비교 값 Split이 일치하지 않아 Unknown registered task 오류가 발생합니다. 이 검사는 브로커에 연결하거나 메시지를 발행하기 전에 수행되므로 요청은 큐에 도달하지 않습니다.

또한 Console 경고 로그에는 구체적인 오류 메시지 대신 예외 종류만 기록되어 원인을 파악하기 어렵습니다.

기대 동작: Console이 Task 목록을 만들 때와 동일하게 task.name을 기준으로 작업을 찾아야 합니다. 중복 여부 검사도 같은 기준을 사용해야 합니다.

실제 동작: Console이 task.__name__을 기준으로 작업을 찾아 사용자 지정 이름을 사용하는 Task를 거부합니다.
