# 구현 내용

## 관련 요구사항

- [요구사항 명세서](./REQUIREMENTS.md)

## 변경 내용

- Inspector 공개 확장을 `Status`와 `Ping`으로 교체하고 확장 모듈 및 Status HTML 리소스 경로를 새 이름으로 변경했습니다.
- Status의 Metrics JSON·HTML 동작과 Ping의 상태 확인 응답은 유지하면서 각 확장의 새 경로를 문서, 샘플 및 테스트에 반영했습니다.
- 기존 이름을 호환 별칭으로 노출하지 않도록 공개 내보내기를 갱신했습니다.
- 한국어·영어 README 예제와 Inspector 엔드포인트 설명을 수정했습니다.

## 영향 범위

- `Dashboard`와 `HealthCheck`의 기존 import 및 `/dashboard`, 기존 상태 확인 경로를 사용하는 설정은 새 공개 이름과 URL로 변경해야 합니다.
- Status HTML 정적 리소스 경로는 `Status.html`로 변경되었습니다.

## 검증

- `python -m unittest discover -s tests -p test_status.py`: 8개 통과
- `python -m unittest discover -s tests -p test_inspector.py`: 14개 통과, 2개 건너뜀
- `python -m unittest discover -s tests -p test_inspector_logging.py`: 5개 통과
- `node --test tests/test_status_ui.cjs`: 5개 통과
- Pylance 진단: Python 오류 없음. 미사용 인자·변수 경고만 확인됨
