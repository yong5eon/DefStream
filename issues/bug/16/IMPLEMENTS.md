# Inspector Console 사용자 지정 Task 이름 버그 수정 기록

## 구현 개요

[요구사항 명세서](./REQUIREMENTS.md)에 따라 Inspector Console이 작업 목록과
동일한 작업 ID를 사용해 등록된 Task를 찾고, 잘못된 요청의 구체적인 원인을
경고 로그에서 확인할 수 있도록 수정했다.

## 주요 변경

- `Console.execute()`의 Task 검색과 중복 검사를 모두 `task.__name__`에서
  `task.name` 비교로 변경했다. 작업 이름을 사용자 지정한 경우에도
  Specifications 문서와 Console UI가 전달하는 ID로 올바른 Task를 식별한다.
- 잘못된 입력을 거부하는 경고 로그에 예외 종류와 예외 메시지를 함께 기록한다.
- `test_inspector_console.py`에 사용자 지정 ID의 발행 성공, 중복 ID 거부,
  미등록 ID의 오류 로그 내용을 확인하는 회귀 테스트를 추가했다.
- RabbitMQ·Redis 실서버 테스트의 요청 ID도 실제 등록된 하위 Task의 `Live.name`을
  사용하도록 했다. 클래스의 `__name__`(`Live`)와 Worker에 등록하는 유효 작업
  이름은 같다고 가정할 수 없으며, 이전의 하드코딩은 요청을 400으로 거부하게 했다.

## 검증

DefStream 테스트 디렉터리에서 Python 3.12.10으로 다음 명령을 실행했다.

```powershell
$env:PYTHONIOENCODING = 'utf-8'
..\..\.venv\Scripts\python.exe -m unittest test_inspector_console test_inspector_logging
```

Inspector Console 및 로깅 관련 테스트 28개가 통과했고, 선택 통합 테스트 2개는
건너뛰었다. 변경된 두 Python 파일의 `compile()` 문법 검사와
`git diff --check`도 통과했다. 브로커 실서버 통합 검증은 수행하지 않았다.
