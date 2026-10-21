# Inspector Console 사용자 지정 Task 이름 처리

Inspector Console이 작업 목록에 표시한 ID로 Task를 찾도록 수정했습니다.
따라서 `ETL.OBS.Split`처럼 클래스 이름과 다른 사용자 지정 Task 이름으로도
요청을 보낼 수 있습니다. 동일한 작업 ID가 중복 등록된 경우에는 모호한 작업
실행을 막기 위해 요청을 거부합니다.

잘못된 요청은 기존처럼 거부되며, 경고 로그에 예외 종류와 구체적인 원인이 함께
기록됩니다.

세부 내용은 [요구사항 명세서](./REQUIREMENTS.md)와
[구현 및 검증 기록](./IMPLEMENTS.md)을 참고하세요.
