# Redis 로컬 테스트 환경

각 Compose 파일은 한 가지 Redis 버전의 컨테이너를 생성합니다. 명령은 저장소 루트에서 실행하세요. 필요한 버전만 실행하거나 두 버전을 동시에 띄울 수 있습니다.

## 기동과 종료

```shell
docker compose -f res/docker/redis/redis-6.yml up -d --wait
docker compose -f res/docker/redis/redis-7.yml up -d --wait
```

종료할 때는 기동에 사용한 Compose 파일에 `down`을 실행합니다.

```shell
docker compose -f res/docker/redis/redis-6.yml down
docker compose -f res/docker/redis/redis-7.yml down
```

## 컨테이너와 포트

| 컨테이너 | 이미지 계열 | 호스트 포트 |
| --- | --- | --- |
| `Redis-6` | `redis:6.2` | Redis `56376` |
| `Redis-7` | `redis:7.4` | Redis `56377` |

포트는 모두 `127.0.0.1`에만 게시됩니다.

## 통합 테스트

Redis 통합 테스트를 활성화하고 Compose 포트를 지정하세요.
Windows에서 기본 콘솔 인코딩이 UTF-8이 아니면 테스트 전에 `PYTHONIOENCODING`도 UTF-8로 설정합니다.

```powershell
$env:REDIS_TESTS = '1'
$env:REDIS_PORT = '56376'
$env:PYTHONIOENCODING = 'utf-8'
python -m unittest discover -s tests -t . -p 'test_*.py'
```

Redis 7을 대상으로 할 때는 `REDIS_PORT`를 `56377`로 바꿉니다. Docker Compose health check가 통과한 뒤 테스트를 실행하세요.

Redis 전용 테스트만 실행하려면 저장소 루트에서 다음 명령을 사용합니다.

```shell
python -m unittest discover -s tests/redis -t .
```
