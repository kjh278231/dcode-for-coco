# dcode-assistant

[deepagents-code](https://github.com/langchain-ai/deepagents/tree/main/libs/code)(`dcode`, 0.2.5) 위에 네 가지를 얹은 Coding Assistant다.

1. **계획 게이트.** 코드를 바꾸기 전에 탐색, 계획 파일, AI 리뷰, 사람 승인을 거친다. 승인 전에는 쓰기 도구가 막히고, 승인 뒤에도 계획 범위 밖의 호출은 다시 판정한다.
2. **Memory.** 프로젝트 규칙과 작업 기록을 `.deepagents/memory/`에 파일로 남기고, 새 요청마다 관련 기록을 골라 넣는다.
3. **모니터링.** 요청마다 계획, 리뷰, 판정, 도구 실행, 테스트, 지표를 Langfuse trace로 남기고 `/runs`, `/trace`로 본다.
4. **자기 개선.** 쌓인 지표에서 반복되는 문제를 찾아(`/improve`) 에이전트가 규칙이나 스킬 개선안을 만들고, 평가 실행기로 전후를 비교한 뒤 사람이 반영한다.

판정(예/아니오)은 TypeSafe Jev가 한다. 명세는 [`docs/SPEC.md`](docs/SPEC.md), 진행 기록은 [`PROGRESS.md`](PROGRESS.md), 판단 기록은 [`DECISIONS.md`](DECISIONS.md)다. 새 코드는 `libs/code/deepagents_code/assistant/`, 테스트는 `libs/code/tests/unit_tests/assistant/`에 모여 있다.

## 목차

- [요청 하나가 지나가는 길](#요청-하나가-지나가는-길)
- [설치](#설치)
- [키와 설정](#키와-설정)
- [실행](#실행)
- [테스트 케이스 (채점 순서)](#테스트-케이스-채점-순서)
- [평가 항목과 테스트 케이스](#평가-항목과-테스트-케이스)
- [Jev 보정 결과](#jev-보정-결과)
- [계획 전 읽기 전용 샌드박스](#계획-전-읽기-전용-샌드박스)
- [고친 업스트림 테스트](#고친-업스트림-테스트)
- [알려진 한계](#알려진-한계)
- [릴리스 설치 (선택)](#릴리스-설치-선택)

## 요청 하나가 지나가는 길

```
사람 요청
 → 탐색 서브에이전트(읽기 전용)가 저장소를 읽고 요약
 → Jev J5: 파일을 바꿔야 하는 요청인가?        아니오 → 답하고 끝 (계획 파일 없음)
 → 에이전트가 submit_plan으로 계획 제출 → 게이트가 .deepagents/plans/<id>.md 작성
 → 형식 검사 + Jev J1(완료 조건 검증 가능) J2(범위가 요구사항 안) J3(순서·테스트가 대상에 대응)
 → LLM 리뷰어 의견 → 에이전트가 고쳐 다시 제출 (최대 2회, 리뷰 기록 절에 회차별로 남음)
 → 미결 질문이 있으면 사람에게 질문 화면 → 답은 "결정 사항" 절에
 → 사람 승인 화면 (승인 / 거부 / 고칠 점 입력)
 → 승인 뒤에만 쓰기 도구가 열림. targets 밖 쓰기·승인 뒤 셸은 Jev J4(계획 범위 안인가)로 재판정
 → complete_plan: 게이트가 계획의 test_command를 직접 실행, 통과해야 끝
 → 작업 기록을 Memory에 저장, Langfuse에 점수(지표) 기록
```

계획 파일의 절: `요구사항`, `작업 범위`, `완료 조건`, `작업 순서`(필수, 에이전트가 씀), `참고한 Memory`, `미결 질문`, `결정 사항`, `리뷰 기록`(게이트가 씀). 수정 대상은 frontmatter의 `targets`, 테스트 방법은 `test_command`다.

## 설치

Linux 또는 WSL2, [uv](https://docs.astral.sh/uv/), git이 필요하다. Python 3.14는 uv가 받는다. 검증한 환경은 WSL2(Ubuntu, 커널 6.6), uv 0.13.6이다.

```bash
git clone <이 저장소> dcode-assistant && cd dcode-assistant
export REPO=$PWD
cd libs/code
uv venv --python 3.14 .venv
uv export --frozen --group test --no-hashes --no-emit-project -o requirements-lock.txt
uv pip install --no-config -r requirements-lock.txt                 # uv.lock의 버전 그대로
uv pip install --no-config --no-sources --no-deps -e .              # 이 저장소의 dcode
.venv/bin/dcode --version          # deepagents-code 0.2.5, Editable install: .../libs/code
export PATH=$REPO/libs/code/.venv/bin:$PATH   # 이후 dcode는 이 빌드
```

- 잠금 파일(`uv.lock`)의 버전으로 설치한다. 버전을 풀어 두면 최신 ruff(0.17)가 설치되어 lint가 가짜 실패를 낸다(`check.sh`는 lock의 ruff 0.16만 받는다).
- `--no-sources`가 필요하다. 업스트림 `pyproject.toml`의 `[tool.uv.sources]`가 이 저장소에 없는 폴더(`../deepagents`, `../acp`)를 가리킨다. 같은 이유로 `make test`, `make lint`(`uv run --group test`)는 이 사본에서 그대로 돌지 않는다. 대신 아래의 `scripts/check.sh`를 쓴다 (`BASELINE.md`).
- `-e`(editable)로 설치한다. 보정 사례(`*.jsonl`)와 평가 과제 파일은 wheel의 포함 목록(`.py`, `.md`)에 없어서, editable이 아니면 보정·평가 명령이 파일을 찾지 못한다.
- 이미 설치된 업스트림 `dcode`와 섞이지 않게 위처럼 `PATH` 앞에 이 빌드를 둔다.

검사 명령 (저장소 루트에서):

```bash
bash scripts/check.sh lint      # ruff check, ruff format --diff, 명령 목록 최신 여부, Path.cwd() 사용 검사
bash scripts/check.sh unit      # 우리 테스트(tests/unit_tests/assistant) 전체
bash scripts/check.sh baseline  # 업스트림 포함 단위 테스트 전체(약 5분), 기준선 실패 목록과 비교
bash scripts/check.sh smoke     # 가짜 모델로 dcode -n 한 번 (게이트 끔)
```

`check.sh`는 `make test`와 같은 pytest 옵션(`--disable-socket` 등)을 쓰고, langsmith가 import 때 내는 Python 3.14 사용 중단 경고 하나만 끈다. 업스트림 단위 테스트 전체에는 우리 변경 전부터 실패하는 것이 71건, 오류 16건 있다(원본 사본에서 잰 기준선, `BASELINE.md`, `scripts/baseline_failures.txt`). `baseline`은 그 목록과 비교해 새 실패만 보여준다. `ty` 타입 검사는 원본에서부터 없는 `../deepagents` 경로 때문에 돌지 않는다.

## 키와 설정

| 키 | 용도 | 없을 때 |
|---|---|---|
| 주 모델 키 | dcode 기존 모델 설정(`~/.deepagents/config.toml`, `--model`) | dcode 기존 동작 |
| `OPENROUTER_API_KEY` 또는 `TYPESAFE_API_KEY` | Jev 판정(J1~J6), auto 모드 검토 | **게이트가 시작을 거부한다.** `-n`은 안내 문구와 종료 코드 1, TUI는 서버 시작 실패 화면에 같은 안내 (T1) |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | trace, 지표, `/runs`, `/trace`, `/improve` 관찰, 평가 실행기의 지표 비교 | 기록 없이 정상 동작한다. `/runs`는 키가 없다는 안내만, `/trace`는 업스트림 LangSmith 동작, `/improve`는 관찰을 못 만든다, 평가 실행기는 지표(C) 판정 불가 |

- 키는 셸 환경이나 `~/.deepagents/.env`에 둔다. Jev 키는 작업할 프로젝트의 `.env`에서도 읽히지만, 다른 폴더에서 실행하면 못 찾으니 `~/.deepagents/.env`를 권한다. Langfuse 키는 프로젝트 `.env`에서 읽지 않는다(클론한 저장소가 trace를 다른 곳으로 돌리지 못하게).
- Jev는 OpenRouter 경유면 `typesafe/jev-1.13`, TypeSafe 직접이면 `jev-latest`를 쓴다. 판정 임계값은 `DEEPAGENTS_CODE_PLAN_GATE_JEV_THRESHOLD`(기본 0.5, 아래 보정 결과).

**게이트 끄기.** `DEEPAGENTS_CODE_PLAN_GATE=0`이면 게이트와 Jev 키 검사를 모두 끄고 업스트림 dcode와 같이 동작한다. 용도는 dcode를 서브프로세스로 띄우는 업스트림 통합 테스트와 가짜 모델 점검(`check.sh smoke`)이다. **채점은 이 스위치 없이 한다.**

## 실행

```bash
cd <작업할 git 저장소>
dcode                                              # TUI
dcode -n "<요청>" -S recommended,python3           # 비대화. 승인 화면에서 멈추고 끝난다
dcode -r <thread id> -n "승인" -S recommended,python3   # 같은 thread를 이어서 승인
```

- 비대화(`-n`)에는 승인 화면이 없다. 승인이 필요해지면 계획을 출력하고 끝난다. 헤더의 `Thread: <id>`로 다음 호출을 한다. 승인으로 인정하는 메시지는 정확히 `승인`, `approve`, `approved`, `yes`, `y`, 거부는 `거부`, `reject`, `rejected`, `no`, `n`이다. 그 밖의 글은 고칠 점으로 받아 계획 단계로 돌아간다. 미결 질문이 남아 있으면 다음 메시지는 그 질문의 답으로 받는다.
- `-S recommended,python3`: 비대화에서 셸 명령 허용 목록. 없으면 셸이 꺼져 `complete_plan`이 테스트를 못 돌린다.
- 슬래시 명령(TUI): `/runs`, `/runs <trace id 앞부분>`, `/trace`, `/remember <규칙>`, `/improve`, `/improve list|show <id>|apply <id>|reject <id>`.

## 테스트 케이스 (채점 순서)

채점자가 위에서 아래로 따라 하는 순서다. **실제 모델**이라고 적은 항목만 모델과 Jev를 부른다. 나머지는 가짜 모델 테스트나 모델을 부르지 않는 명령이라 매번 같은 결과가 나온다. 실측 규모는 2026-11-13 WSL2에서 기본 모델 `opengateway:z-ai/glm-5.3-flash-ultrafast`, Jev `typesafe/jev-1.13`(OpenRouter)로 한 번씩 잰 값이다.

| # | 시나리오 | 방법 | 기대 결과 | 평가 항목 | 실측 |
|---|---|---|---|---|---|
| T0 | 코드 품질 | `bash scripts/check.sh lint`, `bash scripts/check.sh unit` | lint 통과, 단위 테스트 전부 통과 | 1-1, 1-2, 1-3 | lint 통과, 657 passed(27초) |
| T1 | 키 없이 실행 | Jev 키 없이 `dcode -n ...`, `dcode` | 안내 문구와 종료 코드 1 / TUI 오류 화면 | 게이트 전제 | 통과 |
| T2 | 코드 읽기 질문 | 가짜 모델 테스트 `-k t2_` | 탐색 결과에 "코드 변경이 필요 없어 보인다", 계획 파일 없음 | 게이트 범위 | 통과 |
| T3 | 버그 수정 전체 흐름 | **실제 모델**, TUI(`dcode -y`)에서 샘플 저장소 버그 수정 | 탐색, 계획 파일, 리뷰 기록, 승인 화면, 코드 변경, 테스트 통과, 계획 `done` | 2-1, 2-2, 2-3, 2-4, 4-1 | 통과. trace 75.5초(사람 승인 대기 포함 114초), 모델 호출 13회, 입력 115K + 캐시 읽기 121K, 출력 3.2K 토큰 |
| T4 | 승인 전 쓰기 차단 | 가짜 모델 테스트 `-k "g1_ or g2_ or g11_"` | 3 passed | 2-4 | 통과 |
| T5 | 범위 변경 시 재검토 | 가짜 모델 테스트 `-k "g6_ or g7_ or g19_"` | 3 passed | 2-4 | 통과 |
| T6 | 모호한 요청과 질문 | 가짜 모델 테스트 `-k "g18_ or g9_ or g10_"` | 3 passed | 2-1, 2-3 | 통과 (실제 모델로는 돌리지 않음) |
| T7 | Memory | **실제 모델**, T3 뒤 `/remember`, TUI를 닫고 다시 열어 관련 요청 | `.deepagents/memory/`의 규칙과 작업 기록, 새 계획의 "참고한 Memory"에 둘 다 | 3-1, 3-2 | 통과. trace 108.4초(승인 대기 포함 146초), 모델 호출 19회, 입력 103K + 캐시 읽기 250K, 출력 5.0K 토큰 |
| T8 | 자기 개선 | 모델 없는 부분만: 단위 테스트, `evalsuite verify`, 시드한 개선안으로 `/improve list/show/apply` | 테스트 통과, 과제 셋 통과, 검증 전 개선안의 반영 거부 | 3-3, 3-4 | 통과. **실제 모델 실행은 현재 한계**(아래) |
| T9 | 모니터링 | T3·T7 뒤 `/runs`, `/runs <id>`, `/trace` | 작업 목록과 지표, 실패 구간, Langfuse 주소 | 4-1, 4-2, 4-3, 4-4 | 통과 |

실제 모델 비용(T3+T7): Jev 약 $0.014(OpenRouter 사용량 차이, auto 모드 검토 포함). 주 모델은 이 공급자가 가격 정보를 주지 않아 금액을 모른다. 토큰은 Langfuse trace의 LLM 호출 합이다(입력과 캐시 읽기를 Langfuse가 나눠 적는다).

### 공통 준비 (T2~T9)

```bash
export REPO=<이 저장소 루트> PATH=$REPO/libs/code/.venv/bin:$PATH
export SAMPLE=/tmp/dcode-sample
T=$REPO/libs/code/deepagents_code/assistant/evalsuite/tasks/fix-median
rm -rf $SAMPLE && mkdir -p $SAMPLE && cp -r $T/repo/. $SAMPLE/ && cp -r $T/tests_regression/tests $SAMPLE/
rm -rf $SAMPLE/tests/__pycache__
cd $SAMPLE && git init -q && git add -A && git -c user.name=demo -c user.email=demo@example.com commit -qm init
python3 -m unittest discover -s tests     # OK (짝수 개 median 테스트는 아직 없다)
```

샘플은 평가 과제 `fix-median`의 시작 상태다. `calc/stats.py`의 `median`이 원소 개수가 짝수일 때 틀린 값을 돌려준다. Langfuse를 쓰려면(T9) 이 셸에 `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`을 넣는다.

### T0. 코드 품질

```bash
cd $REPO
bash scripts/check.sh lint
bash scripts/check.sh unit
```

기대: `lint 통과`, `657 passed`. 업스트림 ruff 설정(모든 규칙, 줄 길이 88, Google docstring)을 그대로 쓴다. 우리 코드는 `libs/code/deepagents_code/assistant/`에 모여 있고 공개 함수마다 한국어 docstring(`Args:`, `Returns:`, `Raises:`)이 있다. 업스트림 포함 전체는 `bash scripts/check.sh baseline`(약 5분, 기준선 대비 새 실패만 표시).

### T1. 키 없이 실행

주 모델은 설정돼 있고 Jev 키만 없는 상태를 만든다. 셸의 값이 `.env`보다 먼저라서, 키가 `~/.deepagents/.env`에 있어도 셸에서 빈 값으로 덮으면 된다.

```bash
cd $SAMPLE && OPENROUTER_API_KEY= TYPESAFE_API_KEY= dcode -n "이 저장소에 뭐가 있나요?"; echo "exit=$?"
```

기대 출력 (종료 코드 1, 서버를 띄우기 전에 끝난다. 앞에 dcode의 `Installing ripgrep...`, `Running task non-interactively...`, `Starting LangGraph server...` 같은 줄이 먼저 나올 수 있다):

```
Error: 계획 게이트에는 Jev 판정 키가 필요하다. TYPESAFE_API_KEY 또는 OPENROUTER_API_KEY를
환경변수나 .env에 설정한다.
게이트 없이 실행하려면 DEEPAGENTS_CODE_PLAN_GATE=0을 설정한다.
exit=1
```

TUI(`OPENROUTER_API_KEY= TYPESAFE_API_KEY= dcode`)는 대화 화면에 `Error: Server failed to start: MissingJevKeyError: 계획 게이트에는 Jev 판정 키가 필요하다. ...`를 보인다(처음 실행이면 이름을 묻는 첫 화면을 Enter로 넘긴 뒤). 주 모델 설정도 없는 빈 환경에서는 dcode의 "No model configured" 안내가 먼저 나온다.

### T2. 코드 읽기 질문

```bash
cd $REPO && bash scripts/check.sh unit tests/unit_tests/assistant/test_gate.py -k t2_
```

가짜 모델이 탐색 서브에이전트를 부르고, 판정기(J5)가 "변경 불필요"(0.1)라고 답한다. 단언: 탐색 결과 끝에 `[판정] 이 요청은 코드 변경이 필요 없어 보인다. 탐색 결과로 답하라.`가 붙고, `.deepagents/plans/`가 없고, phase가 `idle`이다. 실제 모델로는 `dcode -n "calc/stats.py의 median이 어떻게 동작하는지 설명해 줘. 코드는 고치지 마." -S recommended,python3`로 같은 흐름을 볼 수 있다(이번 검증에서는 비용 때문에 돌리지 않았다).

### T3. 버그 수정 전체 흐름 (실제 모델)

```bash
cd $SAMPLE && dcode -y
```

`-y`는 dcode의 auto 모드다(셸·편집 같은 도구 호출을 사람 대신 Jev가 검토). 실측은 auto 모드로 했다. `-y` 없이(manual 모드) 실행하면 계획 승인 뒤의 파일 편집과 셸 명령마다 업스트림 dcode의 도구 승인 창이 추가로 뜬다(이 모드로는 따라 해 보지 않았다). 계획 게이트와 승인 화면은 두 모드에서 같다.

입력:

```
calc/stats.py의 median이 원소 개수가 짝수인 목록에서 틀린 값을 돌려준다. 짝수 개일 때는 정렬한 뒤 가운데 두 값의 평균을 돌려줘야 한다(예: median([4, 1, 3, 2])는 2.5). 홀수 개일 때의 동작과 mean은 바꾸지 마라. 고친 뒤 python3 -m unittest discover -s tests로 확인해라.
```

기대:
1. 탐색 서브에이전트(`explorer`) 호출 뒤 `submit_plan`. `.deepagents/plans/<id>.md`가 생긴다.
2. 승인 화면 "Agent has a question for you"에 계획 전체(frontmatter의 `targets`, `test_command`, 절 `요구사항`, `작업 범위`, `완료 조건`, `작업 순서`, `참고한 Memory`, `미결 질문`, `결정 사항`, `리뷰 기록`)와 `이 계획을 승인하시겠습니까?` 선택지 `승인 / 거부 / Other`.
3. `승인`을 고르면 그때부터 `edit_file`이 열리고 `calc/stats.py`, `tests/test_stats.py`가 바뀐다.
4. `complete_plan`이 `test_command`를 직접 돌려 통과하면 계획 `status: done`, `.deepagents/memory/work-*.md` 작업 기록이 생긴다.

확인:

```bash
grep '^status' .deepagents/plans/*.md        # status: done
sed -n '/## 리뷰 기록/,$p' .deepagents/plans/*.md   # 회차별 J1~J3 판정, 형식 문제, 리뷰어 의견
python3 -m unittest discover -s tests        # OK
```

실측(2026-11-13): 탐색 → 계획 → 리뷰 1회차(J1~J3 통과, 의견 없음) → 승인 → 두 파일 수정 → 테스트 통과. 요청 전체가 trace 하나(`78fb945b`)에 남았다: 75.5초, 모델 호출 13회, 도구 호출 8회, 구간 `cg.explore`, `cg.judge.J5`, `cg.plan.submit`, `cg.judge.J1~J3`, `cg.plan.review`, `cg.plan.approval`, `cg.test.run`, `cg.result`. 사람이 승인을 고르기까지 포함한 경과는 114초. 이 실행에서는 리뷰어가 의견을 내지 않았다. 의견이 반영되는 왕복은 T7 실행(1회차 의견 → 다시 제출 → 2회차 의견 없음)과 T6의 `g10_` 테스트에서 볼 수 있다.

### T4. 승인 전 쓰기 차단

```bash
cd $REPO && bash scripts/check.sh unit tests/unit_tests/assistant/test_gate.py -k "g1_ or g2_ or g11_"
```

기대 `3 passed`. G1: 계획 없이 `write_file` → 파일이 안 생기고 오류 결과. G2: 계획 없이 `execute("rm -rf x")` → `x`가 남는다. G11: 승인 전후 모두 계획 폴더(`.deepagents/plans/`) 직접 쓰기 거부.

### T5. 범위 변경 시 재검토

```bash
cd $REPO && bash scripts/check.sh unit tests/unit_tests/assistant/test_gate.py -k "g6_ or g7_ or g19_"
```

기대 `3 passed`. G6: 승인 뒤 `targets` 밖 쓰기를 J4가 거부하면 파일이 안 생긴다. G7: J4가 통과시키면 파일이 생기고 계획의 `targets`에 그 경로가 더해진다. G19: 승인 뒤 새 사람 메시지가 오면 `targets` 안 쓰기도 J4를 다시 거친다.

### T6. 모호한 요청과 질문

```bash
cd $REPO && bash scripts/check.sh unit tests/unit_tests/assistant/test_gate.py -k "g18_ or g9_ or g10_"
```

기대 `3 passed`. G18: 계획의 `미결 질문`이 있으면 질문 화면이 뜨고, 사람의 답이 계획의 `결정 사항` 절에 그대로 남으며 답이 없는 질문은 `미결 질문`에 남는다. G9: 승인 화면에서 자유 입력("테스트도 추가해 주세요")은 고칠 점으로 받아 계획 단계로 돌아간다. G10: 리뷰어가 두 회차 모두 의견을 내면 두 회차가 `리뷰 기록`에 남고 상한(2회)에서 멈춘다. 실제 모델로는 "calc/stats.py에 결과를 반올림하는 옵션을 추가해 줘"처럼 해석이 둘 이상인 요청에서 볼 수 있지만, 모델이 질문할지는 모델 판단이라 이번 검증에서는 돌리지 않았다(비용 결정).

### T7. Memory (실제 모델)

T3에 이어서, 같은 TUI에서 규칙을 저장한다.

```
/remember 테스트는 python3 -m unittest discover -s tests로 돌린다
```

기대: `규칙을 저장했다: rule-...`. TUI를 닫고(`Ctrl+C` 두 번) 다시 연다.

```bash
cd $SAMPLE && ls .deepagents/memory/     # MEMORY.md, rule-*.md, work-*.md
dcode -y
```

입력:

```
calc/stats.py의 median에 default 키워드 인자를 추가해 줘. 빈 목록이 들어왔을 때 default를 주면 그 값을 돌려주고, 주지 않으면 지금처럼 ValueError를 낸다
```

기대: 새 계획의 `참고한 Memory` 절에 규칙(`rule-...`)과 T3의 작업 기록(`work-...`)이 적힌다. 기억 선택은 Jev J6가 요청마다 하고, 색인(`MEMORY.md`)은 항상 주입된다.

```bash
sed -n '/## 참고한 Memory/,/## 미결 질문/p' $(ls -t .deepagents/plans/*.md | head -1)
```

실측(2026-11-13): trace `62c2632d` 108.4초, 모델 호출 19회(승인 대기 포함 경과 146초). `참고한 Memory`: `rule-python3-m-unittest-discover-s-tests-9396c4 (테스트 실행 명령), work-20261113-072227-calc-stats-py-median-median-4 (이전 median 작업 기록 ...)`. 리뷰 1회차에 리뷰어가 "완료 조건의 테스트 이름과 작업 순서의 메서드 이름이 다르다"는 의견을 냈고, 에이전트가 고쳐 다시 제출해 2회차 의견 없음으로 승인 화면에 왔다(요구사항 절에 "리뷰 반영: ..."). 승인 뒤 테스트 통과, 계획 `done`.

### T8. 자기 개선 (모델 없는 부분만)

```bash
cd $REPO && bash scripts/check.sh unit tests/unit_tests/assistant/test_improve.py tests/unit_tests/assistant/test_evalsuite.py
cd $REPO/libs/code && python -m deepagents_code.assistant.evalsuite verify
```

기대: `47 passed`. `verify`는 과제 셋 `add-slugify`, `fix-median`, `trap-test-command` 모두 `통과`(시작 상태에서 회귀 테스트 통과·목표 테스트 실패, 해법 적용 뒤 둘 다 통과). 테스트가 보는 것: 임계값을 넘은 신호만 관찰로 올리기(`find_observations`), `/improve`가 관찰 표와 지시문을 에이전트에 보내기, `propose_improvement`가 저장만 하고 반영하지 않기, 전후 판정(A 매번 테스트 통과, B 기존 과제 회귀 없음, C 지표가 잡음 폭 밖으로 나빠지지 않음), 검증 전 개선안의 반영 거부.

개선안 화면은 시드한 개선안으로 본다(모델을 부르지 않는다):

```bash
cd $SAMPLE && python -c "
from datetime import UTC, datetime
from pathlib import Path
from deepagents_code.assistant.improve import ImprovementStore
print(ImprovementStore(Path.cwd()).create(kind='rule', name='use-real-test-pattern',
  description='테스트 명령이 0개를 실행하면 실제 파일 패턴에 맞춰 고쳐 돌린다',
  body='저장소 안내의 테스트 명령이 0개를 실행하면(종료 코드 5) 실제 테스트 파일 패턴에 맞춰 고친다.',
  rationale='예시로 시드한 개선안. 실제 관찰에서 나온 것이 아니다.', observations=(), now=datetime.now(UTC)))"
```

TUI에서 `/improve list` → `<id>  proposed  rule  ...`, `/improve show <id>` → 근거, payload(규칙 파일), "검증 전입니다. 실행할 명령: python -m deepagents_code.assistant.evalsuite run --improvement <id>", `/improve apply <id>` → `검증을 통과한 개선안만 반영한다. 지금 상태: proposed`.

**현재 한계.** 함정 과제를 실제 모델로 두 번 수행 → `/improve` → `evalsuite run --improvement`(과제 3개 × 반복 3회 × 전후 = 에이전트 실행 18회) → `/improve apply`의 전체 경로는 실제 모델로 끝까지 돌린 적이 없다. M8의 실제 실행에서 함정 과제는 `cg.test_failures` 1을 만들어 임계값(작업당 2, 작업 2건)에 못 미쳤다(에이전트가 탐색 때 함정을 알아챘다). 그래서 관찰이 생기지 않아 개선안도 생기지 않는다. 신호를 만드는 과제, 임계값, 검증 방식은 다음 자기 개선 작업(`docs/design/self_improvement_v2.md`)에서 다시 설계하고 그때 실제 모델로 돌린다.

### T9. 모니터링

Langfuse 키가 있는 셸에서 T3·T7을 한 뒤(점수가 Langfuse에 보이기까지 수십 초 걸린다), TUI에서:

```
/runs
/runs <위 목록의 trace id 앞 8자>
/trace
```

기대:
- `/runs`: 최근 10건. 시각, 상태(`정상`/`오류 N`), 지표 요약(`llm_calls`, `tool_calls`, `tool_errors`, `gate_denies`), trace id 앞 8자.
- `/runs <id>`: 소요 시간, 실패 구간(경고·오류 수준의 구간 이름과 시각), 지표 전체(`cg.llm_calls`, `cg.tool_calls`, `cg.tool_errors`, `cg.gate_denies`, `cg.jev_denies`, `cg.review_rounds`, `cg.test_failures`, `cg.repeat_failures`), Langfuse 주소.
- `/trace`: 이 대화의 최근 trace 주소를 연다.

실측(2026-11-13), 성공한 T3 실행:

```
작업 78fb945b3dba4a1a186857aeba23bcf0
소요: 75.5초
실패 구간:
- 없음
지표:
- cg.gate_denies: 0
- cg.jev_denies: 0
- cg.llm_calls: 13
- cg.repeat_failures: 0
- cg.review_rounds: 1
- cg.test_failures: 0
- cg.tool_calls: 8
- cg.tool_errors: 0
주소:
https://<langfuse>/project/<id>/traces/78fb945b3dba4a1a186857aeba23bcf0
```

실패가 있던 실행(M8의 함정 과제)에서는 실패 지점과 원인이 나온다:

```
실패 구간:
- 2026-11-13T00:10:08 WARNING cg.gate.deny: out_of_scope
- 2026-11-13T00:10:23 ERROR cg.test.run: -
지표: ... cg.jev_denies: 1, cg.test_failures: 1, cg.tool_errors: 2 ...
```

Langfuse 화면의 trace에는 요청 실행 하나가 구간 트리로 남는다: `cg.explore`(탐색), `cg.memory.inject`(넣은 기억), `cg.judge.J1`~`J6`(Jev 판정과 확률), `cg.plan.submit`, `cg.plan.review`(리뷰어 의견), `cg.human.question`, `cg.plan.approval`, `cg.gate.deny`/`cg.gate.sandbox`/`cg.scope.extend`(게이트 결정과 이유), `cg.test.run`(테스트 명령, 종료 코드), `cg.result`, LLM 호출과 도구 실행(LangChain 콜백), 끝에 지표 점수. 자기 개선은 따로 구간을 두지 않는다: `/improve`가 보낸 지시문과 `propose_improvement` 호출이 그 대화의 trace에 남고, 평가 실행기의 결과는 `.deepagents/improvements/<id>/validation.json`과 작업 폴더의 `results.json`, 과제별 로그에 남는다. 키가 없으면 `/runs`, `/improve`는 `Langfuse 키가 없어 기록이 없습니다`를 보인다.

## 평가 항목과 테스트 케이스

| 평가 항목 | 확인하는 케이스 | 무엇을 보면 되나 |
|---|---|---|
| 1-1 PEP8 스타일 | T0 | `check.sh lint`의 `ruff check`, `ruff format --diff` 통과 |
| 1-2 명명 규칙, import 정리 | T0 | ruff 전체 규칙(N, I, 상대 import 금지 포함) 통과 |
| 1-3 docstring, 주석 | T0 | ruff D 규칙(Google 형식) 통과. `assistant/` 모듈의 docstring |
| 2-1 요구사항, 범위, 완료 조건 정의 | T3, T6 | 계획 파일의 `요구사항`, `작업 범위`, `완료 조건` 절. 형식 검사와 Jev J1(완료 조건 검증 가능), J2(범위) |
| 2-2 수정 대상, 순서, 테스트 방법 | T3 | frontmatter `targets`, `test_command`, `작업 순서` 절. Jev J3 |
| 2-3 AI 리뷰와 반영 | T3, T7, T6 | `리뷰 기록` 절의 회차별 판정·의견, T7의 의견 → 재제출 → 2회차. G10, G18 |
| 2-4 승인 뒤에만 변경, 범위 변경 시 재검토 | T3, T4, T5 | 승인 전 쓰기 거부(G1, G2, G11), 범위 밖은 J4(G6, G7, G19) |
| 3-1 규칙·작업 경험 저장, 세션 뒤 유지 | T7 | `/remember`의 `rule-*.md`, `complete_plan`의 `work-*.md`, TUI를 다시 연 뒤에도 남음 |
| 3-2 관련 Memory 검색과 활용 | T7 | 새 계획의 `참고한 Memory` 절, Langfuse `cg.memory.inject`, J6 판정 |
| 3-3 실패·평가로 개선안 생성 | T8 (모델 없는 부분) | `find_observations`, `/improve` 지시문, `propose_improvement` 테스트, 개선안 저장 형식. 실제 모델 생성은 현재 한계 |
| 3-4 전후 검증, 통과한 개선안 반영 | T8 (모델 없는 부분) | `evalsuite verify`, 판정(A·B·C) 테스트, 검증 전 반영 거부. 실제 모델 검증은 현재 한계 |
| 4-1 요청별 전체 흐름 기록 | T9, T3 | trace 하나에 계획, 리뷰, 판정, 도구, 테스트, 결과 |
| 4-2 LLM, 도구, Memory, 자기 개선의 결과·오류 | T9 | 구간 수준(WARNING/ERROR), `/runs <id>`의 실패 구간 |
| 4-3 시간, 호출 수, 재시도 등 지표 | T9 | `cg.*` 점수와 소요 시간. 재시도류는 `cg.review_rounds`, `cg.repeat_failures`, `cg.test_failures` |
| 4-4 로그·trace로 실패 지점과 원인 확인 | T9 | `/runs <id>`의 실패 구간(구간 이름, 수준, 이유), `/trace`, Langfuse 주소 |

## Jev 보정 결과

Jev 질문 여섯 개의 문구를 정답을 지정해 만든 사례로 맞췄다(SPEC 8장). 코드는 `libs/code/deepagents_code/assistant/calibration/`, 사례는 그 아래 `cases/J1.jsonl`~`J6.jsonl`(질문마다 40건), 확인용 묶음 결과는 `results/holdout.json`(사례별 확률).

| 질문 | 묻는 것 | 더 나쁜 오류 |
|---|---|---|
| J1 | 완료 조건을 실행으로 확인할 수 있는가 | 문제 있는 계획 통과(FP) |
| J2 | 작업 범위가 요구사항 안인가 | FP |
| J3 | 작업 순서·테스트가 수정 대상에 대응하는가 | FP |
| J4 | 이 도구 호출이 승인된 계획 범위 안인가 | 범위 밖 호출 통과(FP). 차단 재현율 우선 |
| J5 | 파일을 바꿔야 하는 요청인가 | 변경 필요를 불필요로(FN) |
| J6 | 이 작업 기록이 요청에 참고가 되는가 | 관련 기억 놓침(FN) |

**절차.** 1) 생성: 질문마다 정답(0/1)과 이유를 지정한 지시문으로 모델이 계획·호출·요청을 쓰게 하고(모델에게 정답을 매기게 하지 않는다), 게이트가 쓰는 것과 같은 state 함수(`question_j1` 등)로 판정 본문을 만든다. 질문마다 dev 24건, holdout 16건, 묶음마다 0과 1이 반씩. 생성 모델은 dcode 모델 설정(`z-ai/glm-5.3-flash` 166건, 같은 계열 `glm-5.3-flash-ultrafast` 74건. SPEC은 Sonnet급을 적었지만 이 환경의 dcode 설정에 없다). 사례는 에이전트가 정답과 내용이 맞는지 훑어봤다(사람 대신). 2) dev로 문구를 고친다. 3) holdout을 한 번 돌리고 그 뒤로 문구를 고치지 않는다.

```bash
cd $REPO/libs/code
python -m deepagents_code.assistant.calibration generate --question J1 --count 40   # 이미 만든 사례는 건너뛴다
python -m deepagents_code.assistant.calibration evaluate --question J1 --split dev --sweep
python -m deepagents_code.assistant.calibration evaluate --all --split holdout --out /tmp/holdout.json
```

**dev.** 처음 문구로 144건 중 140건 맞음(J1 FP 1, J2 FP 1, J4 FP 1, J6 FN 1). J1과 J3의 음성 사례는 0.32~0.46으로 임계값 0.5에 가까웠다. 문구를 한 번 고쳤다: J1 "완료 조건 중 하나라도 '잘 동작한다', '깔끔해진다', '만족한다', '충분하다'처럼 사람의 느낌에 기대거나 수동 확인뿐이면 아니오", J2 "요구하지 않은 옵션, 공개 함수 시그니처 변경이 하나라도 있으면 아니오", J4 "수정 대상과 작업 범위에 없는 파일(작업 범위가 고치지 않겠다고 한 문서 포함)", J6 "바꾸는 내용이 달라도 같은 함수를 다루면 참고가 된다". 고친 뒤 dev 144건 모두 맞음. J3, J5는 고치지 않았다. 임계값은 0.5 그대로 둔다(문구를 고친 J1, J2, J4, J6는 dev에서 0.4~0.6 사이 결과가 같았다. 고치지 않은 J3는 0.4에서 FP 4건이라 0.5 아래로 내리면 안 된다. 임계값은 auto 모드 검토와 함께 쓰는 하나의 값이다).

**holdout (임계값 0.5, 2026-11-13, `typesafe/jev-1.13`).**

| 질문 | n | TP | FP | TN | FN | 정밀도 | 재현율 | 차단 재현율 |
|---|---|---|---|---|---|---|---|---|
| J1 | 16 | 8 | 0 | 8 | 0 | 1.00 | 1.00 | 1.00 |
| J2 | 16 | 8 | 0 | 8 | 0 | 1.00 | 1.00 | 1.00 |
| J3 | 16 | 8 | 1 | 7 | 0 | 0.89 | 1.00 | 0.88 |
| J4 | 16 | 8 | 0 | 8 | 0 | 1.00 | 1.00 | 1.00 |
| J5 | 16 | 8 | 0 | 8 | 0 | 1.00 | 1.00 | 1.00 |
| J6 | 16 | 8 | 0 | 8 | 0 | 1.00 | 1.00 | 1.00 |

양성(1)은 "통과"이고 차단 재현율은 정답이 0인 사례 중 막은 비율이다. 판정 불가(거절, 형식 오류, 전송 실패)는 0건이었다(있었으면 닫힌 쪽, 즉 0으로 셌다). 틀린 하나는 J3-026(테스트 명령이 바뀌는 모듈과 무관한 `tests/test_tokenizer.py`만 도는 계획, 확률 0.78)이다.

**해석의 한계.** 사례가 한 생성 모델이 이유를 듣고 쓴 것이라 분명한 편이고, 실제 계획처럼 애매한 경우는 적다. dev와 holdout은 같은 이유 목록(질문·라벨마다 5개, `SCENARIOS`)에서 나왔고, 생성 지시문에 판정 기준 문구가 들어가며, J1의 고친 문구는 그 이유 목록의 표현('깔끔해진다', '만족한다', '충분하다')을 그대로 쓴다. 그래서 holdout은 같은 분포 안의 확인이지 새 유형의 계획에 대한 검증이 아니다. holdout이 질문마다 16건이라 오류 하나가 6%p다. 보정 비용: Jev 약 450회 $0.023, 생성 모델 호출 240회(성공분 입력 약 9.5만, 출력 약 98만 토큰. 출력 대부분이 추론 토큰).

## 계획 전 읽기 전용 샌드박스

승인 전(탐색, 계획 단계)의 `execute`는 커널이 쓰기를 막는 샌드박스에서 돈다. 모델이 `python -c`, `git log | cat` 같은 읽기 명령을 쓸 수 있게 하면서 파일을 바꾸지 못하게 한다(`assistant/sandbox.py`).

- 방식: user, mount, PID, net, IPC 네임스페이스(자기 uid만 매핑), 루트 파일 시스템 전체를 재귀 읽기 전용으로 다시 마운트, 버리는 tmpfs를 임시 공간으로, seccomp(유닉스·vsock 소켓, ptrace, io_uring, 키링, 코어 덤프 크기 변경 차단). 쓰기는 `Read-only file system`으로 실패하고 네트워크는 닿지 않는다. 호출당 약 30ms.
- 승인 뒤에도 쓰인다. Jev J4가 통과시키지 않은 `execute`와, 보호 폴더(`.deepagents/plans`, `memory`, `improvements`)를 언급한 `execute`는 거부 대신 이 샌드박스에서 돌고 결과 끝에 `[게이트] ... 읽기 전용 샌드박스에서 돌렸다` 한 줄이 붙는다.
- 대체 경로: 프로세스당 한 번 탐침해서 샌드박스를 못 쓰면(비특권 user 네임스페이스 금지, x86_64 아님, 원격 샌드박스 백엔드) 명령 이름 허용 목록 기반의 정적 판정으로 넘어간다. 정적 판정은 `cat`, `ls`, `git log` 같은 읽기 명령만 받고 나머지는 거부한다.
- 끄기: `DEEPAGENTS_CODE_PLAN_SANDBOX=0`이면 샌드박스 없이 정적 판정만 쓴다.
- 플랫폼: WSL2(커널 6.6, x86_64)에서만 확인했다. AppArmor가 비특권 user 네임스페이스를 막는 일반 Ubuntu 23.10 이상(`kernel.apparmor_restrict_unprivileged_userns=1`)에서는 탐침이 실패해 정적 판정으로 넘어갈 것으로 본다(확인 못 함). 동작은 안전하지만 승인 전에 거부되는 셸 명령이 늘어난다.
- 임시 공간: 보통은 `/tmp`에 버리는 tmpfs를 덮는다. 프로젝트나 dcode 설치(가상환경)가 `/tmp` 아래면 덮으면 가려지므로 `/tmp`는 읽기 전용으로 두고 `TMPDIR=/run/tmp`를 쓴다. 이때 `/tmp`에 직접 쓰는 도구는 실패하고, 호스트 `/tmp`의 내용이 (읽기 전용으로) 보인다.
- 막지 못하는 것: 읽기는 막지 않는다(`~/.ssh`, `.env`도 읽힌다). 장치 파일 쓰기는 읽기 전용 마운트로 막히지 않는다.

## 고친 업스트림 테스트

SPEC 9.4가 허락한 경우만 고쳤다. 업스트림 테스트를 지우거나 건너뛰게 표시하지 않았다.

| 파일 | 이유 |
|---|---|
| `tests/unit_tests/test_app.py::TestRememberRequiresMessages` (2건) | `/remember`가 기존 remember 스킬로 넘기는 대신 규칙을 바로 저장한다(SPEC P11). 삭제한 스킬을 직접 검사하던 테스트 |
| `tests/unit_tests/smoke_tests/snapshots/system_prompt_headless_local.md`, `system_prompt_interactive_local.md` | 시스템 프롬프트 스냅숏에서 삭제한 remember 스킬 줄을 뺐다 |
| `tests/integration_tests/test_headless_resume.py` | dcode를 서브프로세스로 띄우는 통합 테스트. 환경변수 사전에 `DEEPAGENTS_CODE_PLAN_GATE=0` 한 줄을 더했다(단언은 그대로) |
| `tests/unit_tests/tui/widgets/test_welcome.py` | 계획 게이트 작업이 아니다. 시작 화면 마스코트 기능(커밋 `fec79c4`)이 시작 화면을 바꾸면서 그 테스트를 갱신했다 |

검사 자료인 `libs/code/scripts/check_process_cwd.py`의 허용 목록도 두 번 바꿨다(토큰 갱신 하나, 샌드박스 런처 항목 하나).

## 알려진 한계

- **자기 개선의 실제 모델 경로를 끝까지 돌린 적이 없다(T8).** 함정 과제가 7.2 임계값을 넘는 신호를 만들지 못해 관찰과 개선안이 생기지 않았다. `evalsuite run --improvement`도 가짜 dcode로만 검증했다. 다음 자기 개선 작업(`docs/design/self_improvement_v2.md`)에서 다시 설계한다.
- **자기 개선 검증은 회귀 검사다.** 개선안이 실제로 도움이 됐는지는 입증하지 않는다. 필수 기준은 "매번 테스트 통과"(A)와 기존 과제 회귀 없음(B)이고, 지표(C)는 반복 3회의 잡음 폭 안이면 통과다. 과제는 3개뿐이다.
- 신호 임계값(SPEC 7.2)과 Jev 임계값 0.5는 근거 없이 정한 시작값이다. Jev 보정은 생성 사례 기준이다(위).
- `/improve`는 프로젝트를 구분하지 않고 Langfuse의 최근 20건을 읽는다. 평가 실행기 실행도 그 창에 들어간다.
- Langfuse 키가 없으면 평가 4번 항목 전체와 자기 개선(관찰, 지표 비교)이 동작하지 않는다.
- 사람에게 되묻는 판단(미결 질문)은 모델에 맡겼다. 놓친 질문은 사람이 승인할 때 잡아야 한다.
- `complete_plan` 없이 남은 계획은 phase가 `executing`으로 유지되고 이후 쓰기는 J4에 기댄다. 계획을 닫는 사용자 명령은 없다.
- 보호 폴더에 대한 셸 검사는 문자열 대조다. 승인 뒤 경로를 변수로 조립하는 명령은 놓칠 수 있다(샌드박스를 쓸 수 있으면 언급이 잡힌 명령은 샌드박스에서 돈다).
- 계획 전 샌드박스는 쓰기와 네트워크만 막는다(읽기는 막지 않는다). WSL2에서만 확인했다. 위 절 참고.
- auto 모드는 게이트보다 먼저 Jev로 승인 대상 호출을 검토한다. Jev 키가 없으면 검토 없이 허용하고(사용자 결정), 키가 있는데 호출이 실패하면 사람 승인으로 넘어간다.
- 프로젝트 `.env`가 `DEEPAGENTS_CODE_PLAN_GATE=0`이나 `DEEPAGENTS_CODE_PLAN_SANDBOX=0`을 넣으면 게이트나 샌드박스가 꺼진다(클론한 저장소를 믿는 전제).
- `MemoryStore` 쓰기에는 잠금이 없다. 두 프로세스가 동시에 저장하면 색인이 한쪽을 빠뜨릴 수 있다(다음 저장 때 맞춰진다).
- J6는 요청문만 보고 기억을 고른다. 짧은 요청에서는 관련 기억을 놓칠 수 있다(색인은 항상 주입된다).
- 서브에이전트 안의 도구 호출은 지표에 들어가지 않는다. 승인 화면에서 멈춘 실행에는 점수가 없다.
- 비대화 `승인`은 미해결 리뷰 의견이 남아도 승인한다.
- 실제 모델 검증은 T3, T7 한 번씩이다(비용 결정). T2, T6의 실제 모델 동작은 가짜 모델 테스트로 갈음했다.

자세한 목록은 `docs/SPEC.md` 14장, 남은 일은 `FOLLOWUPS.md`.

## 릴리스 설치 (선택)

`bash scripts/release.sh [커밋]`은 그 커밋의 `libs/code`를 별도 가상환경에 editable이 아니게 설치하고 `~/.local/bin/dcode-a` 감싸기 스크립트(자동 업데이트 끔)를 만든다. 작업 사본을 고쳐도 `dcode-a`는 바뀌지 않는다. 채점에는 필요 없다. wheel 설치라 보정 사례와 평가 과제 파일이 빠지므로 보정·평가 명령은 위의 editable 빌드로 돌린다.
