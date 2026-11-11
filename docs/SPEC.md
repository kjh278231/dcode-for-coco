# dcode 기반 Coding Assistant 구현 명세

상태: 구현 전 (2026-11-11). 결정의 배경은 `docs/DESIGN.md`에 있다. 두 문서가 다르면 이 문서가 맞다.

이 문서는 구현자가 추측 없이 만들 수 있도록 쓴다. 메서드마다 시그니처, 계약, 단계, 실패 동작을 적고 본문 코드는 적지 않는다.

## 0. 읽는 법

**경로.** `DC/`는 작업 사본의 `libs/code/deepagents_code/`다. `SDK/`는 설치된 `deepagents` 0.7.34, `LC/`는 설치된 `langchain/agents/middleware/`다. `Day09/`, `Day08/`, `Day04_new/`, `Day05_new/`로 시작하는 경로는 수업 저장소 `/home/sds/workspace/sds_ax_advanced_2026/` 기준이다. 이 폴더(`docs/`)의 다른 문서는 `docs/`로 시작한다.

**줄 번호.** 이 문서의 `DC/파일:줄`은 `Day09/` 사본에서 2026-11-11에 확인한 값이다. 작업 사본에서 `# [해설]` 주석을 지우면 줄이 밀린다. 고치기 직전에 `grep -n`으로 심볼을 다시 찾는다. 줄 번호가 아니라 심볼 이름이 기준이다.

**표시.**

| 표시 | 뜻 |
|---|---|
| [확정] | 사용자와 합의한 결정 |
| [제안] | 코드 조사에서 필요해져 이 문서가 정한 것. 2026-11-11에 사용자가 전부 확정했다. 12장에 모았다 |
| [확인] | 코드를 읽어서 확인한 사실. 대부분 조사 에이전트가 정적으로 읽은 것이고 실행한 것이 아니다 |
| [실행 확인] | 이 문서를 쓰면서 직접 실행해 본 사실 |
| [미확인] | 실행으로 확인하지 못했다. 해당 마일스톤의 첫 작업으로 확인한다 |

**멈추고 묻는 규칙.** [미확인] 항목이 문서와 다르게 동작하면 우회 코드를 쓰지 말고 13장의 절차를 따른다.

## 1. 전체 구조

### 1.1 프로세스 경계 [확인]

dcode는 클라이언트와 서버 두 프로세스다. 무엇이 어디서 도는지 틀리면 동작하지 않는다.

| 위치 | 도는 것 | 근거 |
|---|---|---|
| 서버 | 그래프, 모든 미들웨어, 도구 본문, 체크포인터 | `DC/server_graph.py:1175` `make_graph`, `:601` `create_cli_agent` 호출 |
| 클라이언트 | TUI, 비대화 실행기, 슬래시 명령, 승인·질문 화면 | `DC/app.py`, `DC/tui/textual_adapter.py`, `DC/client/non_interactive.py` |

- 서버 프로세스의 `Path.cwd()`는 임시 폴더다. 프로젝트 루트는 `create_cli_agent`가 받은 `project_context`와 `cwd`에서 얻는다 (`DC/agent.py:2911` 부근 `effective_cwd`).
- 클라이언트가 보내는 설정에서 콜백 객체는 버려진다 (`langgraph/pregel/remote.py:409` `_sanitize_config`). 문자열 metadata와 tags만 서버에 닿는다.
- 사용자의 한 요청은 여러 실행(run)으로 쪼개진다. 멈춤(interrupt) 뒤 재개할 때마다 새 실행이고 `before_agent`가 다시 불린다.

### 1.2 우리 구성 요소의 배치

| 구성 요소 | 위치 | 이유 |
|---|---|---|
| 계획 게이트 미들웨어, 계획 도구, Jev 판정, 리뷰어, Memory 주입, Langfuse 구간 | 서버 | 그래프 상태와 도구 호출을 다룬다 |
| 계획 승인 화면, 사람 질문 화면 | 클라이언트의 기존 `ask_user` 화면 재사용 | 3.6절 |
| `TYPESAFE_API_KEY` 사전 검사 | 클라이언트 `main.py` | 서버를 띄우기 전에 친절한 안내로 끝낸다 |
| `/improve`, `/runs`, `/trace`, `/remember` | 클라이언트 `app.py` | 슬래시 명령 처리기가 거기 있다 |
| 평가 실행기, Jev 보정 스크립트 | 별도 명령 (`python -m`) | 오래 걸리고 TUI와 무관하다 |

### 1.3 패키지 구조 [제안: 패키지 이름 `assistant`]

```
DC/assistant/
  __init__.py          공개 이름만 다시 내보낸다
  options.py           PlanGateOptions, 상수
  frontmatter.py       YAML frontmatter 읽기와 쓰기
  plan.py              Plan, PlanStatus, PlanStore, 형식 검사
  decider.py           Noul, Verdict, Decider, JevDecider, FakeDecider, 질문 J1~J6
  policy.py            순수 함수: 도구 분류, 경로 정규화, 읽기 전용 셸 판정
  reviewer.py          PlanReviewer (LLM 리뷰어)
  gate.py              PlanGateState, PlanGateMiddleware, SubagentWriteBlockMiddleware
  tools.py             submit_plan, request_plan_approval, complete_plan, propose_rule, propose_improvement
  subagents.py         explorer 서브에이전트 사양
  memory.py            MemoryRecord, MemoryStore, MemoryInjectionMiddleware
  tracing.py           Langfuse 초기화, 핸들러, 구간과 점수 도우미
  runs.py              Langfuse 조회, 신호 집계, /runs 출력 문자열
  improve.py           ImprovementStore, 임계값, 반영
  prompts.py           시스템 프롬프트 덧붙임, 리뷰어 지침, 탐색 지침, 되묻기 기준
  evalsuite/
    __main__.py        python -m deepagents_code.assistant.evalsuite
    runner.py          과제 실행과 채점
    tasks/<이름>/      instruction.md, repo/, tests_target/, tests_regression/, task.toml
  calibration/
    __main__.py        python -m deepagents_code.assistant.calibration
    cases/J1.jsonl ... J6.jsonl

libs/code/tests/unit_tests/assistant/
  test_frontmatter.py test_plan.py test_decider.py test_policy.py test_reviewer.py
  test_gate.py test_tools.py test_memory.py test_tracing.py test_runs.py test_improve.py
  test_evalsuite.py fakes.py
```

의존 방향은 한쪽이다. `frontmatter` ← `plan`, `memory`, `improve`. `policy` ← `gate`. `decider` ← `gate`, `tools`, `memory`. `tracing` ← 나머지 전부. `gate`와 `tools`는 서로를 import하지 않는다. 둘이 공유하는 상태 키와 상수는 `options.py`에 둔다.

### 1.4 기존 파일 수정 목록

| 파일 | 수정 | 마일스톤 |
|---|---|---|
| `libs/code/pyproject.toml` | 의존성 `langfuse>=4.15.1,<5` 추가 | M0 |
| `libs/code/uv.lock` | `uv lock`으로 갱신 | M0 |
| `DC/_env_vars.py` | 상수 `PLAN_GATE`, `PLAN_GATE_JEV_THRESHOLD`, `LANGFUSE_TRACING` 추가 | M3 |
| `DC/_paths.py` | `ProjectPaths`에 `plans_dir`, `memory_dir`, `improvements_dir` 추가 | M1 |
| `DC/_server_config.py` | `ServerConfig.plan_gate` 필드와 직렬화 | M3 |
| `DC/client/launch/server_manager.py` | `ServerConfig.from_cli_args` 호출에 `plan_gate` 전달 | M3 |
| `DC/server_graph.py` | `create_cli_agent`에 옵션 전달, `make_graph`에 Langfuse 핸들러 | M3, M6 |
| `DC/agent.py` | `create_cli_agent` 인자, 미들웨어와 서브에이전트 등록, 승인 술어 | M3, M4 |
| `DC/main.py` | 키 사전 검사, LangSmith 기본 끄기 | M3, M6 |
| `DC/config.py` | `build_stream_config`에 Langfuse metadata | M6 |
| `DC/command_registry.py` | `/improve`, `/runs` 등록, `/trace` 설명 변경 | M7 |
| `DC/app.py` | `/improve`, `/runs` 처리기, `/trace`와 `/remember` 교체 | M5, M7 |
| `DC/built_in_skills/remember/SKILL.md` | 삭제 | M5 |
| `libs/code/README.md` | 테스트 케이스와 실행 방법 | M9 |

`DC/tui/` 아래는 고치지 않는다. 승인과 질문은 기존 화면을 쓴다.

## 2. 공통 타입과 상수 (`options.py`)

```python
PLAN_GATE_MIDDLEWARE_NAME: str = "PlanGateMiddleware"

WRITE_PATH_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file", "delete"})
SHELL_TOOLS: frozenset[str] = frozenset({"execute"})
OTHER_MUTATING_TOOLS: frozenset[str] = frozenset(
    {"js_eval", "start_async_task", "update_async_task", "cancel_async_task"}
)
PLAN_TOOLS: frozenset[str] = frozenset(
    {"submit_plan", "request_plan_approval", "complete_plan", "propose_rule", "propose_improvement"}
)
EXPLORER_SUBAGENT_NAME: str = "explorer"
MAX_REVIEW_ROUNDS: int = 2
JEV_THRESHOLD_DEFAULT: float = 0.5
APPROVE_WORDS: frozenset[str] = frozenset({"승인", "approve", "approved", "yes", "y"})
REJECT_WORDS: frozenset[str] = frozenset({"거부", "reject", "rejected", "no", "n"})


@dataclass(frozen=True, slots=True)
class PlanGateOptions:
    """계획 게이트를 조립하는 데 필요한 값 묶음."""

    project_root: Path
    decider: Decider
    reviewer: PlanReviewer
    interactive: bool
    mcp_mutating_tool_names: frozenset[str] = frozenset()
    threshold: float = JEV_THRESHOLD_DEFAULT
```

게이트 대상 도구를 dcode의 승인 맵(`DC/agent.py:2365` `_add_interrupt_on`)에서 얻지 않고 상수로 둔다. [확인] 그 맵은 `--yolo`나 비대화에서 아예 만들어지지 않고 (`DC/agent.py:2969`), `web_search`, `fetch_url`, `task`처럼 쓰기가 아닌 도구도 담는다. MCP 도구만 기존 함수 `gated_mcp_tool_names` (`DC/auto_mode.py:773`)로 얻어 `mcp_mutating_tool_names`에 넣는다.

**단계(phase).** 문자열 리터럴 넷이다.

| 값 | 뜻 | 쓰기 도구 |
|---|---|---|
| `idle` | 계획이 없다. 질문 응답과 탐색 | 막힘 |
| `planning` | 계획을 냈고 수정 중이다 | 막힘 |
| `awaiting_approval` | 사람의 승인이나 답을 기다린다 | 막힘 |
| `executing` | 승인됐다 | 범위 안에서 열림 |

## 3. 계획 게이트

### 3.1 `frontmatter.py`

dcode의 서브에이전트 파서 (`DC/subagents.py:78` `_parse_subagent_file`)와 같은 형식이지만 그 함수는 파일 경로를 받고 서브에이전트 필드를 검증하므로 재사용하지 않는다. 같은 정규식 방식으로 작은 함수 둘을 둔다.

```python
def parse(text: str) -> tuple[dict[str, Any], str]:
    """마크다운 문자열을 frontmatter 사전과 본문으로 나눈다.

    Raises:
        FrontmatterError: `---`로 시작하지 않거나, YAML이 잘못됐거나, 최상위가 사전이 아닐 때.
    """
    # 1) 문자열이 "---\n"로 시작하는지 본다
    # 2) 닫는 "\n---\n"를 찾아 YAML 구간과 본문을 자른다
    # 3) yaml.safe_load로 읽고 dict인지 확인한다
    # 4) (사전, 본문) 반환. 본문 앞의 빈 줄 하나는 제거한다


def render(meta: Mapping[str, Any], body: str) -> str:
    """frontmatter 사전과 본문을 마크다운 문자열로 만든다. parse(render(m, b)) == (m, b)."""
    # yaml.safe_dump(sort_keys=False, allow_unicode=True) 사용


class FrontmatterError(ValueError):
    """frontmatter 형식 오류."""
```

검사: 왕복 동일성, `---` 없는 입력, 잘못된 YAML, 최상위가 리스트인 YAML, 한글 값.

### 3.2 `plan.py`

**파일 형식.** 위치는 `<project_root>/.deepagents/plans/<plan_id>.md`다.

```markdown
---
id: 20261111-153000-fix-login
status: draft
targets:
  - src/auth/login.py
  - tests/test_login.py
test_command: uv run pytest tests/test_login.py -q
review_round: 1
trace_ids: []
created_at: "2026-11-11T15:30:00+09:00"
---

## 요구사항
...
## 작업 범위
...
## 완료 조건
...
## 작업 순서
...
## 참고한 Memory
없음
## 미결 질문
없음
## 결정 사항
없음
## 리뷰 기록
### 1회차
...
```

`targets`는 프로젝트 루트 기준 상대 경로이고 POSIX 구분자를 쓴다.

```python
PlanStatus = Literal["draft", "reviewed", "approved", "done", "failed", "rejected"]

REQUIRED_SECTIONS: tuple[str, ...] = ("요구사항", "작업 범위", "완료 조건", "작업 순서", "참고한 Memory")
OPTIONAL_SECTIONS: tuple[str, ...] = ("미결 질문", "결정 사항", "리뷰 기록")
EMPTY_MARK: str = "없음"


@dataclass(frozen=True, slots=True)
class Plan:
    """계획 한 건. 파일 하나와 일대일로 대응한다."""

    id: str
    status: PlanStatus
    targets: tuple[str, ...]
    test_command: str
    review_round: int
    trace_ids: tuple[str, ...]
    created_at: str
    sections: Mapping[str, str]   # 제목 -> 본문. REQUIRED + OPTIONAL 순서

    def open_questions(self) -> tuple[str, ...]:
        """미결 질문 절의 목록 항목을 돌려준다. 절이 없거나 "없음"이면 빈 튜플."""

    def to_markdown(self) -> str:
        """파일에 쓸 문자열을 만든다."""

    def with_updates(self, **changes: Any) -> Plan:
        """바뀐 필드만 갈아 끼운 새 Plan을 돌려준다."""


def parse_plan(text: str) -> Plan:
    """마크다운 문자열을 Plan으로 읽는다.

    Raises:
        PlanFormatError: frontmatter 오류, 필수 키 누락, 타입 오류, status 값 오류.
    """
    # 1) frontmatter.parse
    # 2) id, status, targets, test_command 필수. 나머지는 기본값
    # 3) 본문을 "## 제목" 기준으로 잘라 sections를 만든다


def validate_plan(plan: Plan) -> list[str]:
    """형식 문제를 사람이 읽는 문장 목록으로 돌려준다. 빈 목록이면 통과다."""
    # 1) REQUIRED_SECTIONS 각각 존재하고 공백 제거 후 비어 있지 않은가
    #    "참고한 Memory"만 "없음"을 허용한다. 나머지 필수 절은 "없음"이면 문제로 본다
    # 2) targets가 한 개 이상인가
    # 3) targets 각 항목이 상대 경로인가: 절대 경로, "..", "~" 금지
    # 4) targets에 ".deepagents/"로 시작하는 경로가 없는가
    # 5) test_command가 비어 있지 않은가
    # 6) targets에 glob 문자(* ? [)가 없는가


def new_plan_id(now: datetime, requirements: str) -> str:
    """"YYYYMMDD-HHMMSS-<슬러그>" 형식의 id를 만든다. 슬러그는 요구사항 첫 줄에서 영숫자만 남겨 30자."""


class PlanStore:
    """계획 파일의 읽기와 쓰기. 계획 폴더에 쓰는 코드는 이 클래스뿐이다."""

    def __init__(self, project_root: Path) -> None:
        """Args: project_root: 프로젝트 루트의 절대 경로."""

    @property
    def directory(self) -> Path:
        """<project_root>/.deepagents/plans"""

    def path_for(self, plan_id: str) -> Path:
        """계획 파일 경로. plan_id에 경로 구분자가 있으면 ValueError."""

    def save(self, plan: Plan) -> Path:
        """계획을 파일에 쓴다. 같은 id가 있으면 덮어쓴다. 임시 파일에 쓰고 os.replace로 바꾼다."""

    def load(self, plan_id: str) -> Plan:
        """Raises: FileNotFoundError, PlanFormatError."""

    def list_ids(self) -> list[str]:
        """id를 이름순으로 돌려준다. 폴더가 없으면 빈 목록."""
```

`save`는 같은 입력으로 여러 번 불려도 결과가 같아야 한다. 도구가 멈춤 뒤 재개되면 본문이 처음부터 다시 실행되기 때문이다.

검사: 예시 파일 왕복, `validate_plan`의 여섯 규칙 각각에 반례 하나, `open_questions`의 "없음" 처리, `save` 두 번 뒤 파일 동일.

### 3.3 `decider.py`

Jev는 `httpx`로 직접 부른다. [확인] `httpx`는 dcode 잠금 파일에 이미 있다. 수업 코드와 같은 방식이다 (`Day04_new/cap_lab/decisions.py:96`, `Day08_new/guard_lab/decisions.py:131`). `langchain-typesafe` 패키지는 쓰지 않는다. 로컬 설치본(0.0.1a2)과 스킬 문서(0.0.1a3)의 호출 형태가 다르다.

[확인] Jev의 `noul` 답은 0과 1 사이의 확률이다. "0 또는 1로만 답한다"는 결정은 코드에서 `확률 >= 임계값`으로 자르는 것으로 구현한다. 임계값은 0.5로 시작하고 보정 단계에서 조정한다. 이 값은 사람이 잰 값이 아니다.

```python
@dataclass(frozen=True, slots=True)
class Noul:
    """예 또는 아니오 질문 하나."""

    name: str            # "J1" ~ "J6", 또는 J6의 경우 "J6:<기억 이름>"
    instructions: str    # 무엇을 판정하는지
    true: str            # 1로 답해야 하는 경우의 기준
    false: str           # 0으로 답해야 하는 경우의 기준


@dataclass(frozen=True, slots=True)
class Verdict:
    """질문 하나의 판정 결과."""

    name: str
    probability: float | None   # 판정 불가이면 None
    passed: bool                # probability가 유효하고 임계값 이상일 때만 True
    reason: Literal["ok", "below_threshold", "refused", "invalid", "transport_error"]


class DeciderError(RuntimeError):
    """Jev 호출 실패. 메시지에 키나 요청 본문을 넣지 않는다."""


class Decider(Protocol):
    """판정기. 테스트에서는 FakeDecider를 주입한다."""

    def judge(self, state: str, questions: Sequence[Noul]) -> list[Verdict]:
        """state를 근거로 questions 각각을 판정한다. 결과 순서는 questions와 같다.

        호출이 통째로 실패해도 예외를 던지지 않는다. 모든 질문을 transport_error로 돌려준다.
        """


class JevDecider:
    """TypeSafe Jev를 부르는 판정기."""

    URL: ClassVar[str] = "https://api.typesafe.ai/v1/systemone"
    MODEL: ClassVar[str] = "jev-latest"
    TIMEOUT_S: ClassVar[float] = 15.0
    MAX_QUESTIONS_PER_CALL: ClassVar[int] = 32

    def __init__(
        self,
        api_key: str,
        *,
        threshold: float = JEV_THRESHOLD_DEFAULT,
        client: httpx.Client | None = None,
    ) -> None:
        """Raises: ValueError: api_key가 비었을 때."""

    def judge(self, state: str, questions: Sequence[Noul]) -> list[Verdict]:
        # 1) questions를 MAX_QUESTIONS_PER_CALL개씩 나눈다
        # 2) 묶음마다 본문을 만든다:
        #    {"model": MODEL, "state": state,
        #     "questions": {q.name: {"type": "noul", "instructions": q.instructions,
        #                            "criteria": {"true": q.true, "false": q.false}}}}
        # 3) POST URL, headers={"Authorization": "Bearer " + api_key}, timeout=TIMEOUT_S
        # 4) HTTP 오류나 예외면 그 묶음 전체를 transport_error로 채운다
        # 5) 응답의 answers[q.name]["noul"]을 float로 읽는다
        #    답이 없으면 refused, 숫자가 아니거나 NaN이거나 0~1 밖이면 invalid
        # 6) 유효한 확률은 threshold와 비교해 passed를 정한다
        # 7) 호출마다 tracing.record_judgment로 기록한다 (6장)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> JevDecider:
        """환경에서 TYPESAFE_API_KEY와 임계값을 읽어 만든다.

        Raises: DeciderError: 키가 없을 때. 메시지는 키 이름만 말한다.
        """


class FakeDecider:
    """대본으로 답하는 판정기. 테스트와 가짜 모델 실행에 쓴다."""

    def __init__(self, script: Mapping[str, float] | None = None, *, default: float = 1.0) -> None:
        """script는 질문 이름 접두사 -> 확률. "J6"는 "J6:..." 전부에 맞는다."""

    calls: list[tuple[str, tuple[str, ...]]]   # (state, 질문 이름들) 기록
```

**실패는 닫힌 쪽으로 처리한다.** `passed`가 False인 모든 경우(임계값 미만, 거절, 형식 오류, 전송 실패)를 호출 쪽은 "통과 못 함"으로 다룬다. 예외가 하나 있다. J6(기억 선택)는 통과 못 하면 그 기억을 주입하지 않을 뿐이라 흐름을 막지 않는다.

**질문 정의.** 모듈 상수로 둔다. 문구는 보정에서 바뀐다.

```python
def question_j1(plan: Plan) -> tuple[str, Noul]: ...   # 완료 조건이 실행해서 확인할 수 있는가
def question_j2(plan: Plan) -> tuple[str, Noul]: ...   # 작업 범위가 요구사항 안에 있는가
def question_j3(plan: Plan) -> tuple[str, Noul]: ...   # 작업 순서와 테스트 방법이 수정 대상에 대응하는가
def question_j4(plan: Plan, tool_name: str, summary: str) -> tuple[str, Noul]: ...   # 이 호출이 승인된 계획 범위 안인가
def question_j5(request: str, exploration: str) -> tuple[str, Noul]: ...   # 이 요청이 코드 변경을 필요로 하는가
def questions_j6(request: str, records: Sequence[MemoryRecord]) -> tuple[str, list[Noul]]: ...   # 기억마다 하나
```

각 함수는 `(state 문자열, 질문)`을 돌려준다. `state`는 판정에 필요한 본문만 담고 4,000자에서 자른다. J4의 `summary`는 도구 이름과 인자 요약이고 경로와 명령만 담는다. 파일 내용은 넣지 않는다.

검사: `httpx.MockTransport`로 본문 형태와 인증 헤더 확인, 확률 0.49와 0.5의 경계, `noul`이 문자열인 응답, 500 응답, 시간 초과, 질문 40개의 두 묶음 분할, 오류 메시지에 키가 없는지.

### 3.4 `policy.py`

순수 함수만 둔다. 그래프와 Jev에 의존하지 않는다.

```python
def tool_name_of(tool: BaseTool | Mapping[str, Any]) -> str | None:
    """도구 객체나 사전에서 이름을 꺼낸다. 공급자 내장 도구는 사전으로 온다."""


def normalize_tool_path(raw: object, project_root: Path) -> Path | None:
    """도구 인자의 경로를 실제로 쓰일 절대 경로로 바꾼다. 바꿀 수 없으면 None."""
    # 1) raw가 비지 않은 str인가
    # 2) deepagents.backends.utils.validate_path(raw)로 도구와 똑같이 정규화한다
    #    ValueError면 None
    # 3) Path(...).resolve()로 심볼릭 링크를 푼다. OSError면 None


def relative_target(path: Path, project_root: Path) -> str | None:
    """프로젝트 루트 기준 POSIX 상대 경로. 루트 밖이면 None."""


def is_protected(path: Path, project_root: Path) -> bool:
    """경로가 .deepagents/plans, .deepagents/memory, .deepagents/improvements 안이거나 그 상위인가."""
    # delete는 상위 폴더 삭제도 잡아야 한다. 보호 폴더가 path의 하위이면 True


def is_read_only_shell(command: object, project_root: Path) -> bool:
    """셸 명령이 읽기 전용으로 확인되는가. 확신이 없으면 False."""
    # 1) str이 아니거나 비면 False
    # 2) deepagents_code.config.is_shell_command_allowed(
    #        command, list(RECOMMENDED_SAFE_SHELL_COMMANDS))가 True면 True
    # 3) deepagents_code.auto_mode._fixed_repo_command_allowed(command, project_root)가 True면 True
    # 4) 그 밖은 False


def mentions_protected(command: str) -> bool:
    """명령 문자열에 보호 폴더 경로가 있는가. 문자열 대조다."""


def summarize_call(tool_name: str, args: Mapping[str, Any]) -> str:
    """J4와 기록에 쓸 한 줄 요약. 경로와 명령만 담고 200자에서 자른다."""


Decision = Literal["allow", "deny", "needs_scope_check"]


def classify_call(
    *,
    phase: str,
    tool_name: str,
    args: Mapping[str, Any],
    targets: Sequence[str],
    project_root: Path,
    mcp_mutating: frozenset[str],
    fresh_approval: bool,
) -> tuple[Decision, str]:
    """도구 호출 하나를 Jev 없이 분류한다. 두 번째 값은 사유 코드다."""
```

`classify_call`의 규칙표다. 위에서부터 처음 맞는 줄을 쓴다.

| # | 조건 | 결과 | 사유 코드 |
|---|---|---|---|
| 1 | 도구가 `PLAN_TOOLS`에 있다 | allow | `plan_tool` |
| 2 | `WRITE_PATH_TOOLS`이고 경로를 정규화할 수 없다 | deny | `bad_path` |
| 3 | `WRITE_PATH_TOOLS`이고 `is_protected`다 | deny | `protected_path` |
| 4 | `execute`이고 `is_read_only_shell`이다 | allow | `read_only_shell` |
| 5 | `execute`이고 `mentions_protected`다 | deny | `protected_path` |
| 6 | 도구가 쓰기 계열이 아니다 (아래 정의) | allow | `not_mutating` |
| 7 | `phase`가 `executing`이 아니다 | deny | `no_approved_plan` |
| 8 | `WRITE_PATH_TOOLS`이고 상대 경로가 `targets`에 있고 `fresh_approval`이다 | allow | `in_targets` |
| 9 | 그 밖 | needs_scope_check | `scope_check` |

쓰기 계열은 `WRITE_PATH_TOOLS | SHELL_TOOLS | OTHER_MUTATING_TOOLS | mcp_mutating`이다.

[확인] `is_shell_command_allowed` (`DC/config.py:4537`)와 `_fixed_repo_command_allowed` (`DC/auto_mode.py:2480`)는 인자만 쓰는 순수 함수다. 앞의 것은 첫 토큰 이름만 보고 리다이렉션과 명령 치환을 거부한다. 뒤의 것은 읽기 전용 git 하위 명령만 통과시킨다. 뒤의 것은 이름이 `_`로 시작하는 비공개 함수다. 같은 패키지 안에서 import하고, 그 줄에 이유를 주석으로 적는다.

검사: 규칙표 아홉 줄 각각에 사례 하나 이상. `cat a > b`는 4번에 걸리지 않아야 한다. 상대 경로 `docs/x.md`가 `/docs/x.md`로 정규화되어 루트 밖으로 판정되는지. 심볼릭 링크로 보호 폴더를 가리키는 경로.

### 3.5 `reviewer.py`

LLM 리뷰어는 서브에이전트가 아니라 게이트 코드가 직접 부르는 모델 호출이다. [제안] 이유는 둘이다. 서브에이전트로 두면 리뷰가 일어났는지를 모델의 선택에 맡기게 된다. 코드가 부르면 "항상 리뷰"가 구조로 보장된다.

```python
@dataclass(frozen=True, slots=True)
class ReviewResult:
    """리뷰 한 회의 결과."""

    comments: tuple[str, ...]     # 수정 의견. 없으면 빈 튜플
    questions: tuple[str, ...]    # 사람에게 물어야 하는 것. 7장 기준
    error: str | None = None      # 리뷰 호출이 실패했을 때의 사유


class PlanReviewer:
    """계획을 읽고 수정 의견을 쓰는 리뷰어."""

    def __init__(self, model: BaseChatModel) -> None:
        """Args: model: 세션의 주 모델. create_cli_agent가 해석한 객체를 받는다."""

    async def areview(self, plan: Plan, verdicts: Sequence[Verdict], format_issues: Sequence[str]) -> ReviewResult:
        """계획 하나를 리뷰한다. 예외를 던지지 않는다."""
        # 1) prompts.REVIEWER_SYSTEM + 계획 마크다운 + Jev 결과(통과 못 한 질문 이름) + 형식 문제를 메시지로 만든다
        # 2) model.with_structured_output(스키마)로 한 번 부른다
        #    스키마: {"comments": [str], "questions": [str]}
        # 3) 실패하면 ReviewResult(comments=(), questions=(), error=<예외 종류 이름>)
        # 4) tracing.span("cg.plan.review", ...)로 기록한다
```

리뷰 호출이 실패하면 계획은 "리뷰 못 함" 상태로 사람에게 넘어간다. 승인 화면에 그 사실을 보여준다. 리뷰 실패를 리뷰 통과로 세지 않는다.

`FakeReviewer`를 `tests/unit_tests/assistant/fakes.py`에 둔다. 회차별 `ReviewResult` 목록을 대본으로 받는다.

### 3.6 `tools.py`

도구 다섯 개를 만든다. 대화형과 비대화형에서 등록되는 도구 집합은 같고, `request_plan_approval`과 `propose_rule`의 동작만 다르다.

```python
def build_plan_tools(options: PlanGateOptions) -> list[BaseTool]:
    """계획 도구 다섯 개를 만든다. PlanGateMiddleware.tools가 이 목록을 쓴다."""
```

도구는 `ToolRuntime`으로 상태를 읽고 `Command(update=...)`로 상태와 `ToolMessage`를 함께 돌려준다. 본보기는 `DC/ask_user.py:368` `_ask_user`다.

**중요한 제약.** [확인] 도구 안에서 `interrupt()`를 부르면 재개할 때 도구 본문이 처음부터 다시 실행된다. 그래서 Jev와 리뷰어를 부르는 일과 사람에게 묻는 일을 한 도구에 넣지 않는다. `submit_plan`은 멈추지 않고, `request_plan_approval`은 멈추기 전에 비용이 드는 일을 하지 않는다.

#### `submit_plan`

```python
def submit_plan(
    requirements: str,
    scope: str,
    done_criteria: str,
    steps: str,
    targets: list[str],
    test_command: str,
    memory_refs: str,
    open_questions: list[str],
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[Any, Any],
) -> Command[Any]:
    """계획을 제출한다. 형식 검사, Jev 판정, 리뷰를 거쳐 계획 파일을 쓴다."""
    # 1) 상태에서 phase, plan_id, review_round, explored를 읽는다
    # 2) phase가 awaiting_approval이면 거부: "사람의 답을 기다리는 중이다"
    #    phase가 executing이면 재검토로 본다: 기존 plan_id를 유지하고 status를 draft로 되돌린다
    # 3) explored가 False면 거부: "먼저 task(subagent_type='explorer')로 탐색하라"
    # 4) plan_id가 없으면 new_plan_id로 만든다
    # 5) Plan을 만들고 validate_plan을 돌린다
    # 6) 형식 문제가 없으면 decider.judge로 J1~J3을 한 번에 묻는다
    #    형식 문제가 있으면 Jev를 부르지 않는다
    # 7) reviewer.areview(plan, verdicts, format_issues)
    # 8) review_round를 1 올리고 "리뷰 기록" 절에 이번 회차를 덧붙인다
    #    "미결 질문" = 파일에 남아 있던 질문 + 모델이 낸 open_questions + 리뷰어의 questions (중복 제거)
    #    "결정 사항"과 "리뷰 기록"은 파일에 있던 것을 그대로 옮긴다. 모델의 인자로 받지 않는다
    # 9) 다음 상태를 정한다 (아래 표)
    # 10) PlanStore.save
    # 11) Command(update={상태 키들, "messages": [ToolMessage(...)]})
```

9단계의 표다.

| 조건 | plan.status | phase | 도구 결과가 모델에게 말하는 것 |
|---|---|---|---|
| 형식 문제가 있다 | draft | planning | 문제 목록. 고쳐서 다시 제출하라 |
| 의견이 있고 회차가 `MAX_REVIEW_ROUNDS` 미만이다 | draft | planning | 의견 목록. 반영해서 다시 제출하라 |
| 그 밖 (의견이 없거나, 회차가 상한이거나, 리뷰 실패) | reviewed | planning | `request_plan_approval`을 불러라 |

회차가 상한에 닿았는데 의견이 남으면 그 의견은 계획 파일의 "리뷰 기록"에 남아 사람에게 보인다.

**게이트가 소유하는 절.** "미결 질문", "결정 사항", "리뷰 기록" 셋은 게이트 코드만 쓴다. 모델은 질문을 더할 수 있지만 뺄 수 없다. 질문은 사람이 답해야 없어진다. "결정 사항"은 사람의 답을 코드가 적은 것이고 모델이 고칠 인자가 없다. 이 절이 작업 기록의 "사용자 결정"으로 저장되기 때문이다 (5.2절).

비동기 구현(`coroutine`)을 반드시 함께 둔다. 서버 그래프는 비동기 경로를 쓴다.

#### `request_plan_approval`

```python
def request_plan_approval(
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[Any, Any],
) -> Command[Any]:
    """검토가 끝난 계획을 사람에게 보여주고 답을 받는다."""
    # 1) 상태의 plan_id로 계획을 읽는다. status가 reviewed가 아니면 거부
    # 2) 미결 질문이 있으면 "질문 모드", 없으면 "승인 모드"
    # 3) options.interactive가 False면 비대화 분기 (아래)
    # 4) interrupt(AskUserRequest 모양의 사전)으로 멈춘다
    # 5) 재개 값을 해석한다 (아래 표)
    # 6) 계획 파일과 상태를 갱신하고 Command를 돌려준다
```

**멈춤 신호의 모양.** [확인] TUI는 신호의 `type`이 `"ask_user"`인지와 `AskUserRequest` 모양만 본다 (`DC/tui/textual_adapter.py:2701`). 어느 도구가 냈는지는 보지 않는다. 질문 본문은 마크다운으로 그려진다 (`DC/tui/widgets/ask_user.py:786`). 그래서 TUI를 고치지 않고 계획 승인 화면을 띄운다.

```python
# 승인 모드
{"type": "ask_user", "tool_call_id": tool_call_id, "questions": [
    {"question": <계획 마크다운 전문 + "\n\n이 계획을 승인하시겠습니까?">,
     "type": "multiple_choice",
     "choices": [{"value": "승인"}, {"value": "거부"}]}]}
# 선택지 밖의 자유 입력("Other")은 수정 요청으로 본다.

# 질문 모드: 미결 질문마다 text 질문 하나. 첫 질문 앞에 계획 요약을 붙인다.
```

재개 값은 `{"answers": [str, ...]}`다. 해석은 `DC/ask_user.py:117` `_parse_answers`의 규칙(길이 일치, `status` 키)을 따르되 그 함수를 부르지는 않는다. 그 함수는 결과 메시지의 도구 이름을 `ask_user`로 고정한다.

| 모드 | 답 | plan.status | phase | 모델에게 말하는 것 |
|---|---|---|---|---|
| 승인 | `APPROVE_WORDS`에 있다 | approved | executing | 승인됐다. 계획대로 진행하고 끝나면 `complete_plan`을 불러라. `_cg_approved_human_id`에 현재 요청의 id를 적는다 |
| 승인 | `REJECT_WORDS`에 있다 | rejected | idle | 거부됐다. 코드 변경을 하지 말고 사용자에게 다음 지시를 물어라 |
| 승인 | 그 밖의 글 | draft | planning | 수정 요청 원문. 반영해서 다시 제출하라. `review_round`는 0으로 되돌린다 |
| 질문 | 답 목록 | draft | planning | 질문과 답. "결정 사항"에 반영해서 다시 제출하라 |
| 둘 다 | 취소 또는 오류 | 그대로 | planning | 답을 받지 못했다. 다시 `request_plan_approval`을 불러라 |

질문 모드에서 받은 답은 도구가 직접 계획 파일의 "결정 사항" 절에 `- 질문: ... / 답: ...` 형식으로 적고 "미결 질문"을 "없음"으로 바꾼다. 도구 결과에 질문과 답의 원문을 실어 모델이 계획 본문에 반영하게 한다.

**비대화 분기.** [확정] 계획과 질문을 출력하고 끝낸다. 멈추지 않는다.

- phase를 `awaiting_approval`로 바꾼다.
- 도구 결과로 계획 전문과 질문을 돌려주고, "이 내용을 그대로 최종 답변으로 출력하고 턴을 끝내라"고 지시한다.
- 답은 다음 호출의 사람 메시지로 온다. 해석은 게이트 미들웨어가 한다 (3.7절 `abefore_agent`). 모델이 부를 수 있는 승인 도구는 만들지 않는다. 모델이 스스로 승인할 길을 두지 않기 위해서다.

[확인] 서비스가 `dcode -r <thread_id> -n "승인"`으로 부르면 같은 대화를 이어받는다 (`DC/main.py:2657`). 새 대화로 부르면 phase가 `idle`이라 승인으로 인식되지 않는다. README에 이 호출 형식을 적는다.

#### `complete_plan`

```python
def complete_plan(
    summary: str,
    abandon: bool = False,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    runtime: ToolRuntime[Any, Any] = None,
) -> Command[Any]:
    """작업을 끝낸다. 게이트 코드가 test_command를 직접 실행해 결과를 기록한다."""
    # 1) phase가 executing이 아니면 거부
    # 2) abandon이면 status=failed, phase=idle. 테스트를 돌리지 않는다
    # 3) 백엔드의 execute로 plan.test_command를 실행한다. 제한 시간 600초
    #    백엔드는 미들웨어가 받은 CompositeBackend를 쓴다
    # 4) 종료 코드 0이면 status=done, phase=idle
    #    작업 기록을 MemoryStore.save_work_record로 저장한다 (5장)
    # 5) 0이 아니면 status와 phase를 그대로 두고 test_failures를 1 올린다
    #    출력의 끝 4,000자를 모델에게 돌려준다
    # 6) tracing.span("cg.test.run", ...)과 tracing.span("cg.result", ...)
```

테스트 통과를 모델의 주장이 아니라 게이트가 실행한 결과로 기록한다. 평가 4-1의 "테스트"와 "최종 결과"가 이 구간이다.

[미확인] `test_command`를 게이트 코드가 백엔드로 실행하는 정확한 호출(동기인지 비동기인지, 반환 타입)은 M3에서 `SDK/backends/`의 `execute` 시그니처를 읽고 확정한다.

#### `propose_rule`, `propose_improvement`

5장과 7장에서 설명한다.

### 3.7 `gate.py`

#### 상태

```python
class PlanGateState(AgentState):
    """계획 게이트가 그래프 상태에 두는 값. 전부 비공개 채널이다."""

    _cg_phase: NotRequired[Annotated[str, PrivateStateAttr]]
    _cg_plan_id: NotRequired[Annotated[str | None, PrivateStateAttr]]
    _cg_review_round: NotRequired[Annotated[int, PrivateStateAttr]]
    _cg_explored: NotRequired[Annotated[bool, PrivateStateAttr]]
    _cg_needs_change: NotRequired[Annotated[bool | None, PrivateStateAttr]]
    _cg_last_human_id: NotRequired[Annotated[str | None, PrivateStateAttr]]
    _cg_approved_human_id: NotRequired[Annotated[str | None, PrivateStateAttr]]
    _cg_request_text: NotRequired[Annotated[str, PrivateStateAttr]]
    _cg_counters: NotRequired[Annotated[dict[str, int], PrivateStateAttr, _merge_counters]]
```

`_merge_counters`는 사전의 키별로 더하는 리듀서다. 훅은 증가분만 돌려준다. 값을 0으로 되돌릴 때는 `{"__reset__": 1}`을 돌려주고 리듀서가 빈 사전으로 바꾼다.

[확인] `PrivateStateAttr`가 붙은 필드는 서브에이전트로 넘어가지 않고 서브에이전트에서 돌아오지도 않는다 (`SDK/middleware/subagents.py:785`, `:853`). 서브에이전트가 단계를 `executing`으로 바꿔 돌려주는 길이 막힌다. 선언 본보기는 `DC/local_context.py:718`이다.

`_cg_counters`의 키는 `tool_calls`, `tool_errors`, `gate_denies`, `jev_denies`, `test_failures`, `repeat_failures`다. 요청이 시작될 때 0으로 되돌린다.

`_cg_approved_human_id`는 계획이 승인된 요청의 사람 메시지 id다. 승인이 그 요청 안에서만 "방금 받은 승인"으로 통하게 하는 데 쓴다 (아래 `awrap_tool_call`).

#### `PlanGateMiddleware`

```python
class PlanGateMiddleware(AgentMiddleware):
    """계획 승인 전의 코드 변경을 막고, 승인 뒤에는 범위를 검사한다."""

    state_schema = PlanGateState
    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(self, options: PlanGateOptions, backend: BackendProtocol) -> None:
        """self.tools에 build_plan_tools(options)를 넣는다."""

    @property
    def name(self) -> str:
        """PLAN_GATE_MIDDLEWARE_NAME을 돌려준다."""

    async def abefore_agent(self, state, runtime) -> dict[str, Any] | None: ...
    def before_agent(self, state, runtime) -> dict[str, Any] | None: ...
    async def awrap_model_call(self, request, handler): ...
    def wrap_model_call(self, request, handler): ...
    async def awrap_tool_call(self, request, handler): ...
    def wrap_tool_call(self, request, handler): ...
    async def aafter_agent(self, state, runtime) -> dict[str, Any] | None: ...
    def after_agent(self, state, runtime) -> dict[str, Any] | None: ...
```

[확인] 서버 그래프는 비동기다. 동기 훅만 구현하면 비동기 경로에서 `NotImplementedError`가 난다. 훅마다 동기와 비동기 둘 다 구현하고, 공통 로직은 비공개 메서드 하나로 모은다. Jev 호출은 동기 HTTP이므로 비동기 훅에서는 `asyncio.to_thread`로 부른다 (본보기 `DC/memory_guard.py:450`).

**`abefore_agent` (요청의 시작을 알아본다).**

```
1) 상태의 messages에서 마지막 HumanMessage를 찾는다. 없으면 None 반환
2) 그 id가 _cg_last_human_id와 같으면 None 반환 (재개된 실행이다. 아무것도 하지 않는다)
3) 새 요청이다. 갱신할 값을 모은다:
   _cg_last_human_id = 새 id
   _cg_request_text = 메시지 본문 (4,000자에서 자른다)
   _cg_counters = 전부 0
4) phase가 없으면 "idle"로 둔다
5) phase가 "awaiting_approval"이면 비대화 답을 해석한다 (아래)
6) phase가 "idle"이면 _cg_explored=False, _cg_needs_change=None
   (phase가 planning이나 executing이면 진행 중인 계획을 이어간다. explored를 지우지 않는다)
7) tracing.begin_request(...) (6장)
8) 모은 값을 dict로 반환
```

5단계의 해석. 메시지 본문을 앞뒤 공백 제거와 소문자 변환 뒤에 본다.

| 본문 | 처리 |
|---|---|
| `APPROVE_WORDS`에 있고 계획에 미결 질문이 없다 | 계획 status=approved, phase=executing |
| `REJECT_WORDS`에 있다 | 계획 status=rejected, phase=idle |
| 그 밖 | 미결 질문이 있으면 답으로 보고 "결정 사항"에 적는다. phase=planning, review_round=0 |

이 해석은 `options.interactive`가 False일 때만 한다. 대화형에서 phase가 `awaiting_approval`인 채로 새 메시지가 오는 경우는 없어야 한다. 있으면 phase를 `planning`으로 되돌린다.

**`awrap_model_call` (모델에게 보이는 것을 정한다).**

```
1) phase를 읽는다
2) phase가 executing이 아니면 request.tools에서
   WRITE_PATH_TOOLS | OTHER_MUTATING_TOOLS | mcp_mutating 이름을 가진 도구를 뺀다
   execute는 빼지 않는다 (읽기 전용 명령은 허용한다)
   도구 이름은 policy.tool_name_of로 꺼낸다
3) 시스템 프롬프트에 prompts.gate_prompt(phase, plan 요약)을 덧붙인다
   deepagents.middleware._utils.append_to_system_message 사용
4) request.override(tools=..., system_message=...)로 새 요청을 만들어 handler에 넘긴다
```

[확인] `request.tools = ...`처럼 직접 대입하면 경고가 난다. `override`만 쓴다 (`LC/types.py:203`). 본보기는 `SDK/middleware/_tool_exclusion.py:46`이다.

[확인] 목록에서 뺀 도구도 실행 노드에는 등록돼 있다. 모델이 이름을 지어내 부르면 실행된다. 그래서 다음 훅의 거부가 반드시 있어야 한다.

**`awrap_tool_call` (호출 직전에 막는다).**

```
1) name, args를 꺼낸다. counters.tool_calls를 1 올릴 준비를 한다
2) 탐색 서브에이전트 호출이면 (name == "task" 이고 args["subagent_type"] == "explorer") 3.8절로 간다
3) name == "task"이고 subagent_type이 explorer가 아니면:
   phase가 executing이 아니면 거부 (사유 no_approved_plan)
4) policy.classify_call(...)을 부른다
5) allow면 handler를 부르고 결과를 6)으로 넘긴다
   deny면 거부 메시지를 만든다 (handler를 부르지 않는다)
   needs_scope_check면:
     a) 계획을 읽고 decider.judge(J4)를 to_thread로 부른다
     b) 통과면 handler를 부른다. WRITE_PATH_TOOLS였으면 targets에 경로를 추가하고
        PlanStore.save, tracing.span("cg.scope.extend")
     c) 통과 못 하면 거부한다. 사유 out_of_scope. counters.jev_denies를 1 올린다
        메시지: "승인된 계획의 범위 밖이다. 필요하면 submit_plan으로 계획을 고쳐 재검토를 받아라"
6) 결과가 오류 상태이면 counters.tool_errors를 1 올린다
   같은 (name, args 요약)이 직전에도 오류였으면 counters.repeat_failures를 1 올린다
7) 거부했으면 counters.gate_denies를 1 올리고 tracing.span("cg.gate.deny")
8) 카운터 갱신을 결과에 싣는다 (아래)
```

거부 메시지의 형태. [확인] 본보기는 `DC/auto_mode.py:4711` `HeadlessMCPGuardMiddleware._rejection`이다.

```python
ToolMessage(content=<사유 문장>, name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"], status="error")
```

카운터를 상태에 싣는 방법. `handler`의 결과는 `ToolMessage`이거나 `Command`다. `ToolMessage`이면 `Command(update={"messages": [msg], "_cg_counters": 새 값})`로 감싼다. `Command`이면 `update`에 `_cg_counters`를 더한 새 `Command`를 만든다.

[실행 확인] `awrap_tool_call`이 `Command(update=...)`를 돌려주면 상태가 갱신된다. 한 단계에서 도구 둘이 병렬로 거부됐을 때 덧셈 리듀서가 붙은 값이 2가 됐다. 거부된 도구의 본문은 실행되지 않았다. 도구 안의 `interrupt`와 재개도 이 훅을 거쳐 동작했다. `PrivateStateAttr` 값은 실행 결과에 나오지 않았다. 실험은 `Day09/.venv`에서 `create_agent`, `_ToolBindingFakeModel`, `InMemorySaver`로 했다. 리듀서 본보기는 `DC/auto_mode.py:674` `_merge_temp_artifacts`다.

**승인의 유효 범위.** [제안] 승인은 승인받은 요청 안에서만 `targets` 지름길을 연다. `_cg_last_human_id`가 `_cg_approved_human_id`와 다르면(승인 뒤에 사용자가 새 메시지를 보냈으면) `classify_call`에 `fresh_approval=False`를 넘긴다. 그러면 `targets` 안의 쓰기도 J4를 거친다. J4의 state에는 계획과 새 요청문을 함께 넣는다. 이유는 이렇다. 작업이 `complete_plan` 없이 끝나면 phase가 `executing`으로 남는다. 다음에 온 무관한 요청이 옛 `targets`를 계획도 판정도 없이 고칠 수 있으면 안 된다.

**`aafter_agent` (요청의 끝을 기록한다).**

```
1) counters와 LLM 호출 수를 모은다
   LLM 호출 수는 상태의 _session_cost_breakdown["request_count"]에서 읽는다
   이 값은 대화 전체 누적이다. 요청 시작 때 값을 _cg_counters["llm_base"]에 적어 두고 차이를 쓴다
2) tracing.end_request(counters, phase, plan_id)로 지표를 trace에 점수로 붙인다
3) None 반환
```

[확인] LLM 호출 수는 기존 비용 집계가 센다 (`DC/cost_tracking.py:128` `CostBreakdown.request_count`). 도구 호출 수는 dcode가 세지 않아 게이트가 센다.

#### `SubagentWriteBlockMiddleware`

[제안] 서브에이전트는 항상 읽기 전용이다. 승인 뒤에도 쓰기는 주 에이전트만 한다.

이유. [확인] 서브에이전트는 따로 조립된 그래프라서 주 에이전트의 `wrap_tool_call`이 닿지 않는다 (`DC/agent.py:2989` `_subagent_cli_middleware`). 서브에이전트는 비공개 상태를 받지 못해 단계와 `targets`를 알 수 없다. 범위 검사를 서브에이전트 안에서 할 방법이 없으므로 쓰기를 통째로 막는다.

```python
class SubagentWriteBlockMiddleware(AgentMiddleware):
    """서브에이전트의 쓰기 계열 도구 호출을 항상 거부한다."""

    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(self, project_root: Path, mcp_mutating_tool_names: frozenset[str] = frozenset()) -> None: ...

    @property
    def name(self) -> str:
        """PLAN_GATE_MIDDLEWARE_NAME을 돌려준다. PlanGateMiddleware와 같은 이름이다."""

    # wrap_model_call / awrap_model_call: 쓰기 계열 도구와 PLAN_TOOLS를 목록에서 뺀다
    # wrap_tool_call / awrap_tool_call:
    #   쓰기 계열이면 거부. 단 execute는 policy.is_read_only_shell이면 통과
    #   PLAN_TOOLS와 task도 거부
```

이름을 주 게이트와 같게 두는 이유. [확인] 기본 `general-purpose` 서브에이전트는 fork 모드라서 부모의 미들웨어를 물려받는다. 사양에 같은 이름의 미들웨어가 있으면 사양 쪽이 부모 것을 대신한다 (`SDK/graph.py:774`). 같은 이름으로 두면 물려받은 `PlanGateMiddleware`가 `SubagentWriteBlockMiddleware`로 바뀐다. 계획 도구가 서브에이전트에 노출되지 않는다.

[미확인] fork 서브에이전트의 최종 미들웨어와 도구 목록. M4에서 그래프를 만든 뒤 서브에이전트의 도구를 열거해 확인한다.

### 3.8 탐색 서브에이전트 (`subagents.py`)

```python
def build_explorer_subagent(
    backend: BackendProtocol,
    extra_middleware: Sequence[AgentMiddleware],
) -> SubAgent:
    """읽기 도구만 가진 탐색 서브에이전트 사양을 만든다."""
    # {"name": EXPLORER_SUBAGENT_NAME,
    #  "description": prompts.EXPLORER_DESCRIPTION,
    #  "system_prompt": prompts.EXPLORER_SYSTEM,
    #  "tools": [],                      # 부모의 일반 도구(fetch_url, MCP 등)를 물려받지 않는다
    #  "middleware": [
    #      FilesystemMiddleware(backend=backend, tools=["ls", "read_file", "glob", "grep"]),
    #      *extra_middleware],           # _subagent_cli_middleware의 결과 + SubagentWriteBlockMiddleware
    #  "interrupt_on": {}}
```

[확인] 사양의 `tools` 필드는 파일 도구를 제한하지 못한다. 파일 도구는 `FilesystemMiddleware`가 붙인다. 제한은 `FilesystemMiddleware(tools=[...])`를 사양의 `middleware`에 넣어 기본 것을 바꾸는 방식으로 한다 (`SDK/middleware/subagents.py:151`의 설명).

탐색 서브에이전트에는 `execute`를 주지 않는다. [확인] SDK의 `execute`에는 읽기 전용 모드가 없다.

`prompts.EXPLORER_SYSTEM`의 요지. 저장소와 `.deepagents/memory/`를 읽고 다음 형식으로 답한다. 요청과 관련된 파일 목록(경로와 한 줄 이유), 테스트 실행 방법, 관련 Memory 이름, 코드 변경이 필요해 보이는지와 그 근거. 600단어 안.

**J5 연결.** `PlanGateMiddleware.awrap_tool_call`의 2단계다.

```
1) handler를 불러 탐색 요약을 받는다
2) 결과에서 요약 문자열을 꺼낸다 (Command면 update["messages"]의 마지막 ToolMessage)
3) decider.judge(question_j5(_cg_request_text, 요약))을 to_thread로 부른다
4) 상태 갱신: _cg_explored=True, _cg_needs_change=<통과 여부>
5) 요약 끝에 한 줄을 덧붙인다:
   통과: "[판정] 이 요청은 코드 변경이 필요하다. submit_plan으로 계획을 제출하라."
   통과 못 함: "[판정] 이 요청은 코드 변경이 필요 없어 보인다. 탐색 결과로 답하라."
6) tracing.span("cg.explore"), record_judgment("J5")
```

J5가 "변경 불필요"라고 해도 `submit_plan`을 막지 않는다. J5는 흐름을 안내하고, 보장은 쓰기 도구 차단이 맡는다. 판정과 실제 행동이 어긋나면 `cg.judge.mismatch`로 기록한다.

### 3.9 `DC/agent.py` 연결

**시그니처.** `create_cli_agent` (`DC/agent.py:2622`)에 키워드 인자 하나를 더한다.

```python
plan_gate: PlanGateOptions | None = None,
```

`None`이면 게이트와 관련된 것을 아무것도 넣지 않는다. 업스트림의 기존 테스트는 이 인자를 주지 않으므로 그대로 통과한다. 이것이 기존 기능 보존의 핵심이다.

**메인 미들웨어.** 승인 미들웨어 블록 (`DC/agent.py:3525` ~ `:3558`) 바로 뒤, `ServerHooksMiddleware` 추가 (`:3569`) 앞에 넣는다.

```python
if plan_gate is not None:
    agent_middleware.append(PlanGateMiddleware(plan_gate, composite_backend))
```

[확인] 이 자리의 이유. `wrap_model_call`은 목록 앞쪽이 바깥이다. 게이트가 `FilesystemMiddleware`보다 안쪽이라 파일 도구가 붙은 뒤의 목록을 본다. [확인] `composite_backend`는 `:3506` 부근에서 만들어지므로 그 뒤여야 한다. [확인] `CostTrackingMiddleware`와 `ReliableRubricMiddleware` 사이에는 끼우지 않는다 (`:3237`의 순서 제약).

**서브에이전트.** `_subagent_cli_middleware` (`DC/agent.py:2989`)가 돌려주는 목록의 끝에 더한다.

```python
if plan_gate is not None:
    middleware.append(SubagentWriteBlockMiddleware(plan_gate.project_root, plan_gate.mcp_mutating_tool_names))
```

이 함수는 사용자 정의 서브에이전트와 `general-purpose` 양쪽에 쓰이므로 한 곳에서 모두 덮인다.

탐색 서브에이전트는 `composite_backend`가 만들어진 뒤에 `custom_subagents`에 더한다. `_inject_fs_tools_into_subagents` 호출 (`:3619`) 앞이다.

**`--allow-fs-tools` 충돌.** [확인] 이 옵션이 켜지면 `_inject_fs_tools_into_subagents` (`DC/agent.py:288`)가 모든 서브에이전트의 미들웨어 끝에 `FilesystemMiddleware`를 덧붙여 탐색 서브에이전트의 읽기 전용 구성을 덮는다. 이 함수에서 이름이 `EXPLORER_SUBAGENT_NAME`인 사양은 건너뛰게 고친다.

**기존 승인 화면과의 순서.** [확인] dcode의 승인은 모델 응답 직후(`after_model`)에 멈춘다. 게이트가 거부할 호출에 대해 사용자가 먼저 승인 화면을 보게 된다. 승인 술어 `_should_interrupt_tool_call` (`DC/agent.py:2223`)의 첫머리에 한 줄을 넣는다.

```python
if precheck_denies(request.state, request.tool_call):
    return False
```

`precheck_denies`는 `gate.py`의 모듈 함수다. 상태에 `_cg_phase`가 없으면(게이트가 꺼져 있으면) False다. 있으면 `policy.classify_call`이 `deny`인지 본다. Jev가 필요한 경우는 False로 둔다. 그 경우 사용자가 승인한 뒤 J4가 거부할 수 있고, 그것은 받아들인다.

**승인 모드와의 관계.** 계획 게이트는 `--yolo`, 자동 승인, 세션 중 "항상 승인"과 무관하게 동작한다. 그 모드들은 도구별 승인 화면만 줄인다.

**`js_eval`.** 인터프리터가 켜져 있으면 승인 전에는 목록에서 빠지고 호출이 거부된다. 승인 뒤에는 J4를 거친다. [확인] `js_eval`은 승인 없이 서브에이전트를 띄울 수 있지만 (`langchain_quickjs/middleware.py:263`) 서브에이전트가 읽기 전용이라 쓰기로 이어지지 않는다.

### 3.10 서버 설정과 키 검사

**설정 전달.** [확인] 클라이언트가 서버에 값을 넘기는 통로는 `ServerConfig`의 환경변수 직렬화다.

| 파일 | 수정 |
|---|---|
| `DC/_env_vars.py` | `PLAN_GATE = "DEEPAGENTS_CODE_PLAN_GATE"`, `PLAN_GATE_JEV_THRESHOLD = "DEEPAGENTS_CODE_PLAN_GATE_JEV_THRESHOLD"` |
| `DC/_server_config.py:429` `ServerConfig` | 필드 `plan_gate: bool = False`. `enable_ask_user` (`:482`)와 같은 방식이다 |
| 같은 파일 `to_env` (`:848`), `from_env` (`:933`), `from_cli_args` (`:993`) | 키 추가. 읽기는 `_read_env_bool` (`:185`) |
| 같은 파일 `to_workspace_payload` (`:595`) | 정책 값으로 추가 |
| `DC/client/launch/server_manager.py:441` | `from_cli_args` 호출에 전달 |
| `DC/main.py:3613` 부근, `DC/client/non_interactive.py:3188` 부근 | 실제 실행 진입점 둘에서 `plan_gate=<스위치 값>`으로 켠다. `enable_ask_user`를 넘기는 자리다 |
| `DC/server_graph.py:601` | `create_cli_agent(..., plan_gate=<옵션 또는 None>)` |

[확인] `ServerConfig`의 모든 필드는 분류 넷 중 하나에 속해야 한다. 아니면 `classified_config_fields()` (`:1171`)가 오류를 낸다. 검사 테스트는 `tests/unit_tests/test_server_config.py:222`다.

[확인] `DEEPAGENTS_CODE_*` 문자열을 소스에 직접 쓰면 `tests/unit_tests/test_env_vars.py`가 실패한다. `_env_vars.py`의 상수만 쓴다.

**옵션 조립.** `DC/server_graph.py`에 함수를 더한다.

```python
def _build_plan_gate_options(config: ServerConfig, *, model: BaseChatModel, project_root: Path,
                             mcp_tools: Sequence[BaseTool], environ: Mapping[str, str]) -> PlanGateOptions | None:
    """서버 설정으로 계획 게이트 옵션을 만든다. 게이트가 꺼져 있으면 None."""
    # 1) config.plan_gate가 False면 None
    # 2) JevDecider.from_environment(environ). DeciderError는 그대로 올린다 (서버 기동 실패)
    # 3) PlanReviewer(model)
    # 4) PlanGateOptions(project_root=..., decider=..., reviewer=..., interactive=config.interactive,
    #                    mcp_mutating_tool_names=frozenset(gated_mcp_tool_names(mcp_tools)))
```

환경은 `os.environ`이 아니라 `active_environment()` (`DC/config.py:575`)로 읽는다. 프로젝트 루트는 `project_context.project_root or project_context.user_cwd`다 (`DC/server_graph.py:266`의 관례). [확인] git 저장소가 아니면 `find_project_root`가 None이다.

[미확인] 모델 객체를 `create_cli_agent` 밖에서 얻을 수 있는지. 안 되면 `PlanGateOptions.reviewer`를 `create_cli_agent` 안에서 채우도록 옵션을 "판정기와 설정"까지만 담게 바꾼다. M3에서 정한다.

**키 사전 검사.** `DC/main.py`의 서브커맨드 분기 시작 (`:6571` `if args.command == "help":`) 바로 앞에 넣는다.

```python
def _require_typesafe_key(args: argparse.Namespace, environ: Mapping[str, str]) -> None:
    """Jev 키가 없으면 안내를 출력하고 종료 코드 1로 끝낸다."""
    # 1) args.command가 None이 아니면 반환 (threads, skills, mcp 같은 하위 명령은 검사하지 않는다)
    # 2) 계획 게이트가 꺼져 있으면 반환 (PLAN_GATE 환경변수가 "0" 또는 "false")
    # 3) environ에 TYPESAFE_API_KEY가 있고 비어 있지 않으면 반환
    # 4) stderr에 안내를 쓰고 sys.exit(1)
```

[확인] 이 자리는 `--version` (`:5620`), `auth` (`:5774`), 설정과 진단 명령, 업데이트 명령이 이미 끝난 뒤다. `.env`도 이미 읽혔다 (`:5756`). 대화형과 비대화형이 모두 이 자리를 지난다.

안내 문구는 키의 이름과 설정 방법만 말한다. 키 값을 출력하지 않는다.

**기본값은 꺼짐이고 실제 실행에서만 켠다.** `ServerConfig.plan_gate`의 기본값은 False다. `server_graph`나 `create_cli_agent`를 직접 부르는 기존 테스트는 아무것도 바꾸지 않아도 게이트 없이 돈다. 사용자가 `dcode`를 실행하는 두 진입점(TUI, `-n`)만 게이트를 켠다.

**게이트 끄기 스위치.** [제안] `DEEPAGENTS_CODE_PLAN_GATE=0`이면 두 진입점이 게이트를 켜지 않고 키 검사도 건너뛴다. 용도는 `dcode`를 서브프로세스로 띄우는 통합 테스트와 가짜 모델 점검 스크립트다. [확인] 그 테스트들은 서브프로세스에 환경변수 넷만 넘기고 (`tests/integration_tests/test_headless_resume.py:129`), 가짜 모델 점검은 빈 프로필로 돈다. 스위치 없이 키를 강제하면 전부 깨진다. README에 "채점은 스위치 없이 한다"고 적는다. 이 스위치는 "키가 없으면 못 쓴다"는 결정의 예외다. 사용자가 이 예외를 확정했다.

## 4. 시스템 프롬프트 (`prompts.py`)

문자열 상수와 조립 함수만 둔다.

```python
GATE_BASE: str            # 모든 단계 공통: 흐름 설명
EXPLORER_DESCRIPTION: str
EXPLORER_SYSTEM: str
REVIEWER_SYSTEM: str
ASK_HUMAN_CRITERIA: str   # 되묻기 기준 9개와 묻지 않는 것 3개

def gate_prompt(phase: str, plan_summary: str | None) -> str:
    """단계에 맞는 지침을 돌려준다."""
```

`GATE_BASE`의 요지.

1. 요청을 받으면 먼저 `task(subagent_type="explorer")`로 탐색한다.
2. 코드를 바꿔야 하면 `submit_plan`으로 계획을 낸다. 쓰기 도구는 승인 전까지 쓸 수 없다.
3. 리뷰 의견이 오면 반영해 다시 제출한다.
4. `request_plan_approval`로 사람의 승인을 받는다.
5. 승인되면 계획의 `targets` 안에서 작업하고, 끝나면 `complete_plan`을 부른다.
6. 계획에 없는 파일을 고쳐야 하면 `submit_plan`으로 계획을 고친다.
7. `.deepagents/plans`, `.deepagents/memory`는 직접 고치지 않는다.

`ASK_HUMAN_CRITERIA`는 `docs/DESIGN.md` 7장의 표를 그대로 옮긴다. `GATE_BASE`와 `REVIEWER_SYSTEM` 양쪽에 넣는다. 미결 질문마다 묻는 이유 한 줄, 선택지, 권하는 답을 붙이라고 지시한다.

## 5. Memory (`memory.py`)

### 5.1 파일 형식

위치는 `<project_root>/.deepagents/memory/`다.

```markdown
---
name: rule-use-uv-pytest
kind: rule
description: 테스트는 uv run pytest로 실행한다
created_at: "2026-11-11T15:30:00+09:00"
source: user
---

테스트는 `uv run pytest`로 실행한다. `python -m pytest`는 의존성을 찾지 못한다.
```

`kind`는 `rule`(프로젝트 규칙) 또는 `work`(작업 기록)다. `source`는 `user`, `agent-approved`, `plan:<plan_id>`, `improvement:<id>` 가운데 하나다. 파일 이름은 `<name>.md`다.

`MEMORY.md`는 같은 폴더에 두는 색인이다. 코드가 만든다.

```markdown
<!-- 이 파일은 자동 생성된다. 직접 고치지 않는다. -->
## 프로젝트 규칙
- rule-use-uv-pytest: 테스트는 uv run pytest로 실행한다
## 작업 기록
- work-20261111-153000-fix-login: 로그인 실패 시 500 대신 401을 돌려주도록 수정
```

[확인] SDK의 메모리 주입은 HTML 주석을 지우고 넣지만 (`SDK/middleware/memory.py:172`) 우리 주입은 그 경로를 쓰지 않는다. 주입할 때 첫 줄의 주석을 직접 뺀다.

### 5.2 `MemoryStore`

```python
MemoryKind = Literal["rule", "work"]


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """기억 한 건."""

    name: str
    kind: MemoryKind
    description: str
    created_at: str
    source: str
    body: str


class MemoryStore:
    """기억 파일과 색인의 읽기와 쓰기. 기억 폴더에 쓰는 코드는 이 클래스뿐이다."""

    def __init__(self, project_root: Path) -> None: ...

    @property
    def directory(self) -> Path:
        """<project_root>/.deepagents/memory"""

    def list_records(self, kind: MemoryKind | None = None) -> list[MemoryRecord]:
        """기억을 이름순으로 돌려준다. 형식이 깨진 파일은 건너뛰고 경고를 남긴다. 폴더가 없으면 빈 목록."""

    def load(self, name: str) -> MemoryRecord:
        """Raises: FileNotFoundError, MemoryFormatError."""

    def save(self, record: MemoryRecord) -> Path:
        """기억을 쓰고 색인을 다시 만든다. 같은 이름이 있으면 덮어쓴다."""
        # 1) name 검증: 소문자 영숫자와 하이픈만, kind 접두사("rule-" 또는 "work-")로 시작
        # 2) description 검증: 한 줄, 200자 이하
        # 3) 임시 파일에 쓰고 os.replace
        # 4) rebuild_index()

    def delete(self, name: str) -> None:
        """기억을 지우고 색인을 다시 만든다. 없으면 아무 일도 하지 않는다."""

    def rebuild_index(self) -> Path:
        """모든 기억의 frontmatter를 읽어 MEMORY.md를 다시 쓴다."""

    def read_index(self) -> str:
        """MEMORY.md 내용에서 첫 줄 주석을 뺀 문자열. 파일이 없으면 빈 문자열."""

    def save_rule(self, description: str, body: str, *, source: str, now: datetime) -> MemoryRecord:
        """프로젝트 규칙을 저장한다. 이름은 "rule-" + description에서 만든 슬러그다."""

    def save_work_record(self, plan: Plan, summary: str, *, now: datetime) -> MemoryRecord:
        """끝난 계획에서 작업 기록을 만든다. 모델을 부르지 않는다."""
        # name = "work-" + plan.id
        # description = 요구사항 절의 첫 줄 (150자에서 자른다)
        # body = "## 요청\n<요구사항 절>\n## 사용자 결정\n<결정 사항 절>\n"
        #        "## 최종 설계\n<작업 범위 절>\n<작업 순서 절>\n수정 대상: <targets>\n"
        #        "## 결과\n<summary>\n계획: .deepagents/plans/<plan.id>.md"
```

[확정] 작업 기록에 담는 것은 사용자의 요청, 사용자가 내린 결정, 최종 설계안이다. 계획이 없는 요청은 저장하지 않는다. `save_work_record`는 `complete_plan`이 성공했을 때만 불린다.

### 5.3 `MemoryInjectionMiddleware`

[확인] SDK의 `MemoryMiddleware`에 `MEMORY.md`를 얹을 수 없다. 한 번 읽으면 같은 대화에서 다시 읽지 않는다 (`SDK/middleware/memory.py:293`). 세션 중에 생긴 기억이 반영되지 않는다. 모델 호출마다 디스크를 읽는 미들웨어를 따로 둔다.

```python
class MemoryInjectionState(AgentState):
    _cg_selected_memories: NotRequired[Annotated[list[str], PrivateStateAttr]]
    _cg_memory_human_id: NotRequired[Annotated[str | None, PrivateStateAttr]]


class MemoryInjectionMiddleware(AgentMiddleware):
    """색인과 프로젝트 규칙을 항상 주입하고, 작업 기록은 Jev가 고른 것만 주입한다."""

    state_schema = MemoryInjectionState
    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(self, store: MemoryStore, decider: Decider) -> None: ...

    async def abefore_agent(self, state, runtime) -> dict[str, Any] | None:
        # 1) 마지막 HumanMessage의 id가 _cg_memory_human_id와 같으면 None (재개된 실행)
        # 2) store.list_records("work")를 to_thread로 읽는다
        # 3) 없으면 선택 목록은 빈 목록
        # 4) 있으면 decider.judge(questions_j6(요청 본문, 기록들))을 to_thread로 부른다
        #    질문 이름은 "J6:<기억 이름>". 통과한 것의 이름만 모은다
        # 5) tracing.span("cg.memory.inject", output={"selected": [...], "candidates": n})
        # 6) {"_cg_selected_memories": [...], "_cg_memory_human_id": 새 id} 반환

    async def awrap_model_call(self, request, handler):
        # 1) store.read_index(), 규칙 전부, 선택된 작업 기록을 to_thread로 읽는다
        # 2) 문자열을 만든다:
        #    <project_memory>
        #    ## 색인
        #    <색인>
        #    ## 프로젝트 규칙 (항상 적용)
        #    ### <name>
        #    <body>
        #    ## 이번 요청과 관련된 작업 기록
        #    ### <name>
        #    <body>
        #    </project_memory>
        #    + 안내: 색인에 있지만 여기 없는 기억은 read_file로 열 수 있다.
        #            사용한 기억은 계획의 "참고한 Memory" 절에 적는다
        # 3) 기억이 하나도 없으면 주입하지 않는다
        # 4) append_to_system_message로 붙여 handler에 넘긴다
```

J6는 요청당 한 번만 돈다. 재개된 실행에서 다시 돌지 않게 사람 메시지의 id를 기억한다.

[확정] 프로젝트 규칙은 판정 없이 항상 주입한다. 작업 기록만 J6가 고른다. Jev 호출은 작업 기록 32개당 한 번이다.

주입 크기 상한을 둔다. 규칙과 선택된 기록의 본문 합이 20,000자를 넘으면 뒤의 것부터 본문을 빼고 이름과 설명만 남긴다. 뺀 사실을 구간에 기록한다.

**등록.** `DC/agent.py`의 `if enable_memory:` 블록 (`:3254` ~ `:3283`) 끝에 넣는다. `plan_gate`가 있을 때만이다.

```python
if plan_gate is not None:
    memory_injection = MemoryInjectionMiddleware(MemoryStore(plan_gate.project_root), plan_gate.decider)
    agent_middleware.append(memory_injection)
```

서브에이전트 스택에는 넣지 않는다. 탐색 서브에이전트는 기억 파일을 직접 읽는다.

### 5.4 기존 Memory 기능과의 정리

[확인] 기존 기능 둘이 에이전트에게 `AGENTS.md`를 직접 고쳐 기억을 저장하라고 시킨다. 우리 설계와 충돌한다.

| 기존 | 처리 |
|---|---|
| SDK 기본 메모리 지침 (`SDK/middleware/memory.py:104`) | `plan_gate`가 있으면 `MemoryMiddleware`를 `system_prompt=_MEMORY_READONLY_SYSTEM_PROMPT`로 만든다 (`DC/agent.py:183`의 기존 상수). `AGENTS.md` 읽기는 유지된다 |
| `/remember` 명령 (`DC/app.py:18291`) | 스킬 호출 대신 `MemoryStore.save_rule`을 클라이언트에서 직접 부른다 |
| remember 스킬 (`DC/built_in_skills/remember/`) | 삭제한다. `_STATIC_SKILL_ALIASES` (`DC/command_registry.py:536`)에서도 뺀다 |

`/remember <글>`의 새 동작. 사용자가 직접 말한 규칙이므로 확인 없이 저장한다. 설명은 글의 첫 줄, 본문은 전체다. 인자가 없으면 "저장할 규칙을 함께 적어 주세요"를 출력한다. 프로젝트 루트는 클라이언트의 프로젝트 컨텍스트에서 얻는다.

### 5.5 `propose_rule` 도구

에이전트가 규칙 후보를 제안하는 길이다. [확정] 사람이 확인한 뒤에만 저장한다.

```python
def propose_rule(
    description: str,
    body: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[Any, Any],
) -> Command[Any]:
    """프로젝트 규칙 후보를 사람에게 보여주고, 승인되면 저장한다."""
    # 1) 비대화이면 저장하지 않는다. "비대화 실행에서는 규칙을 저장할 수 없다"를 돌려준다
    # 2) interrupt(ask_user 모양: 규칙 내용 + 선택지 "저장", "버림")
    # 3) "저장"이면 store.save_rule(..., source="agent-approved")
    # 4) 결과를 ToolMessage로 돌려준다
```

멈추기 전에 비용이 드는 일을 하지 않는다. 저장은 재개 뒤에 한 번만 일어난다. `save_rule`이 같은 이름을 덮어쓰므로 다시 실행돼도 안전하다.

### 5.6 경로 추가

`DC/_paths.py`의 `ProjectPaths` (`:161`)에 필드 셋을 더하고 `project_paths` (`:215`)의 반환부를 고친다.

```python
plans_dir: Path          # config_dir / "plans"
memory_dir: Path         # config_dir / "memory"
improvements_dir: Path   # config_dir / "improvements"
```

[확인] `ProjectPaths(...)`를 직접 만드는 곳은 `_paths.py:231` 한 곳이다.

## 6. 모니터링 (`tracing.py`, `runs.py`)

### 6.1 의존성과 초기화

`langfuse>=4.15.1,<5`로 고정한다. [확인] 4.15.1은 Python 3.14에서 `import langfuse`가 경고 없이 된다 (`python -W error`로 확인). 키가 없으면 예외 없이 아무것도 보내지 않는 클라이언트가 된다. 버전을 지정하지 않으면 5.2.0이 설치되는데, 이 문서의 API 이름은 4.15.1에서 확인한 것이다.

[확인] 4.15.1에 `update_current_trace`는 없다. 세션과 태그는 `propagate_attributes` 또는 LangChain 설정의 metadata 키(`langfuse_session_id`, `langfuse_tags`)로 넣는다 (`langfuse/langchain/CallbackHandler.py:485`).

```python
def is_enabled(environ: Mapping[str, str]) -> bool:
    """LANGFUSE_PUBLIC_KEY와 LANGFUSE_SECRET_KEY가 둘 다 있고 LANGFUSE_TRACING이 꺼져 있지 않은가."""


def init(environ: Mapping[str, str]) -> bool:
    """서버 프로세스에서 한 번 부른다. Langfuse 클라이언트를 가림 함수와 함께 만든다. 켜졌는지 돌려준다."""
    # 1) is_enabled가 False면 False
    # 2) Langfuse(public_key=..., secret_key=..., host=..., mask=_mask) 를 만든다
    #    이후 get_client()가 이 설정을 쓴다
    # 3) 예외는 잡아서 경고를 남기고 False


def _mask(*, data: Any, **_: Any) -> Any:
    """Langfuse로 보내기 전에 비밀값을 가린다."""
    # deepagents_code._trace_redaction.create_cached_secret_anonymizer()가 만든 함수를 data에 적용한다
    # 예외가 나면 "[MASK_FAILED]" 문자열을 돌려준다 (원본을 보내지 않는다)


def callback_handler() -> BaseCallbackHandler | None:
    """실행 하나에 붙일 Langfuse 콜백. 꺼져 있으면 None. 부를 때마다 새로 만든다."""
```

[확인] `create_cached_secret_anonymizer` (`DC/_trace_redaction.py:135`)는 문자열이나 중첩 구조를 받아 가린 값을 돌려주는 함수를 만든다. Langfuse의 `mask`는 `(*, data, **kwargs) -> Any` 형태다 (`langfuse/types.py:51`).

[미확인] `mask`가 `CallbackHandler`가 보내는 LLM 입출력에도 적용되는지. M6에서 가짜 키 형태의 문자열을 넣은 실행으로 확인한다. 적용되지 않으면 `mask_otel_spans` 옵션을 쓴다.

### 6.2 핸들러를 붙이는 자리

[확인] 콜백은 서버에서만 붙일 수 있다. `make_graph` (`DC/server_graph.py:1175`)는 실행마다 불리고, 실제 실행일 때만 `runtime.execution_runtime`이 채워진다.

```python
# make_graph의 끝, 그래프를 돌려주기 직전
handler = tracing.callback_handler() if execution is not None else None
if handler is not None:
    agent = agent.with_config({"callbacks": [handler]})
```

[확인] `Pregel.with_config`는 `Pregel`을 돌려주므로 서버의 타입 검사를 통과한다 (`langgraph/pregel/main.py:991`). `recursion_limit`은 이 경로로 건드리지 않는다 (`DC/agent.py:3913`의 주석).

`tracing.init`은 서버 추적 설정 함수 `_configure_server_tracing` (`DC/server_graph.py:143`) 옆에서 한 번 부른다.

[미확인] 워크스페이스의 `.env`에 둔 `LANGFUSE_*`가 서버 프로세스의 환경에 닿는지. M6에서 확인한다. 닿지 않으면 `active_environment()`에서 읽어 `Langfuse(...)`에 직접 넘긴다.

**세션과 태그.** 클라이언트의 `build_stream_config` (`DC/config.py:2852`)가 만드는 metadata에 키를 더한다.

```python
metadata["langfuse_session_id"] = thread_id
metadata["langfuse_tags"] = ["dcode-assistant"]
```

[확인] metadata의 문자열과 리스트는 서버로 전달된다. 한 대화의 요청들이 같은 세션으로 묶인다.

### 6.3 구간과 점수

```python
@contextmanager
def span(name: str, *, input: Any = None, metadata: Mapping[str, Any] | None = None,
         as_type: str = "span") -> Iterator[SpanHandle]:
    """구간 하나를 연다. Langfuse가 꺼져 있으면 아무것도 하지 않는 핸들을 준다."""


class SpanHandle:
    def update(self, *, output: Any = None, metadata: Mapping[str, Any] | None = None,
               level: Literal["DEFAULT", "WARNING", "ERROR"] | None = None,
               status_message: str | None = None) -> None: ...


def record_judgment(question: str, state_chars: int, verdict: Verdict) -> None:
    """Jev 판정 하나를 "cg.judge.<질문>" 구간으로 남긴다. as_type="guardrail"."""
    # input: 질문 이름과 state 길이만. state 원문은 넣지 않는다
    # output: probability, passed, reason


def begin_request(*, thread_id: str | None, human_id: str | None) -> None: ...
def end_request(*, counters: Mapping[str, int], llm_calls: int, phase: str, plan_id: str | None) -> None:
    """요청의 지표를 현재 trace에 점수로 붙인다."""
    # score_current_trace(name="cg.llm_calls", value=...) 등
```

모든 함수는 예외를 밖으로 던지지 않는다. 추적 실패가 작업을 막으면 안 된다.

**구간 이름.** 평가 4-1과 4-2가 이 표다.

| 이름 | 언제 | 담는 것 |
|---|---|---|
| `cg.explore` | 탐색 서브에이전트가 돌아왔을 때 | 요약 길이 |
| `cg.judge.J1` ~ `J6` | Jev 판정마다 | 확률, 통과 여부, 사유 |
| `cg.judge.mismatch` | J5와 실제 행동이 어긋날 때 | J5 결과와 호출된 도구 |
| `cg.plan.submit` | `submit_plan`마다 | plan_id, 회차, 형식 문제 수, 다음 상태 |
| `cg.plan.review` | 리뷰어 호출마다 | 의견 수, 질문 수, 오류 |
| `cg.human.question` | 사람 질문을 냈을 때와 답을 받았을 때 | 질문 수 |
| `cg.plan.approval` | 승인, 거부, 수정 요청 | 결과 |
| `cg.gate.deny` | 게이트가 도구를 거부할 때 | 도구 이름, 사유 코드. level=WARNING |
| `cg.scope.extend` | J4가 목록 밖 경로를 통과시킬 때 | 추가된 경로 |
| `cg.memory.inject` | 요청 시작 때 | 후보 수, 선택된 이름 |
| `cg.test.run` | `complete_plan`의 테스트 실행 | 명령, 종료 코드, 출력 끝부분. 실패면 level=ERROR |
| `cg.result` | 작업이 끝났을 때 | 계획 상태, 요약 |
| `cg.improve.*` | 자기 개선 단계 | 7장 |

LLM 호출과 도구 실행은 `CallbackHandler`가 자동으로 남긴다. 코드 변경은 `write_file`과 `edit_file`의 도구 실행 기록이다.

**지표.** 평가 4-3이다. 요청이 끝날 때 trace에 점수로 붙인다.

| 점수 이름 | 출처 |
|---|---|
| `cg.llm_calls` | 비용 집계의 `request_count` 차이 |
| `cg.tool_calls`, `cg.tool_errors` | 게이트의 카운터 |
| `cg.repeat_failures` | 같은 호출이 연달아 실패한 수 |
| `cg.gate_denies`, `cg.jev_denies` | 게이트의 카운터 |
| `cg.review_rounds` | 계획의 `review_round` |
| `cg.test_failures` | `complete_plan`의 실패 수 |

실행 시간은 Langfuse가 trace와 구간마다 잰다.

[미확인] 우리 구간이 `CallbackHandler`가 만든 trace 안에 들어가는지. 비동기 그래프에서 실행 문맥이 미들웨어 훅까지 이어져야 한다. M6에서 trace 하나를 조회해 `cg.*` 구간이 같은 trace id를 갖는지 확인한다. 이어지지 않으면 `CallbackHandler(trace_context=...)`와 구간의 `trace_context`에 같은 trace id를 넘긴다. id는 요청 시작 때 만들어 상태에 둔다.

### 6.4 `runs.py`

Langfuse API를 읽는 코드를 여기에 모은다. 클라이언트(슬래시 명령)와 평가 실행기가 함께 쓴다.

```python
@dataclass(frozen=True, slots=True)
class RunSummary:
    trace_id: str
    timestamp: str
    name: str
    session_id: str | None
    latency_s: float | None
    scores: Mapping[str, float]
    error_count: int
    html_path: str | None


@dataclass(frozen=True, slots=True)
class Failure:
    span_name: str
    level: str
    status_message: str
    start_time: str


class RunsClient:
    """Langfuse에서 작업 기록을 읽는다."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        """Raises: TracingUnavailableError: 키가 없을 때."""

    def list_runs(self, *, limit: int = 10, session_id: str | None = None) -> list[RunSummary]:
        # client.api.trace.list(limit=..., session_id=..., tags=["dcode-assistant"], fields="core,scores,metrics")

    def failures(self, trace_id: str) -> list[Failure]:
        # client.api.observations.get_many(trace_id=..., limit=100, cursor=...)를 끝까지 읽는다
        # level이 ERROR 또는 WARNING인 것, 이름이 "cg.gate.deny"인 것을 시간순으로 돌려준다

    def signals(self, trace_ids: Sequence[str]) -> dict[str, dict[str, float]]:
        """trace별 cg.* 점수를 돌려준다. 자기 개선과 평가 실행기가 쓴다."""

    def wait_for(self, trace_id: str, *, attempts: int = 6, delay_s: float = 5.0) -> bool:
        """trace가 조회될 때까지 기다린다. 끝내 안 보이면 False."""


def format_run_list(runs: Sequence[RunSummary], host: str) -> str:
    """/runs 목록 화면의 문자열."""


def format_run_detail(run: RunSummary, failures: Sequence[Failure], host: str) -> str:
    """/runs <id> 화면의 문자열. 실패 구간, 원인, 지표, Langfuse 주소."""
```

[확인] 조회 API와 반환 필드는 `langfuse/api/trace/client.py:37`, `:124`와 `langfuse/api/observations/client.py:28`에 있다. 수업의 사용 예는 `Day05_new/eval_lab/evidence.py:65`다. 쓰기는 비동기라 전송을 비운 뒤에도 15~30초 뒤에 보일 수 있다.

[확정] 신호의 출처는 Langfuse API뿐이다. 로컬 기록 파일은 두지 않는다. 키가 없으면 `/runs`와 `/improve`는 "Langfuse 키가 없어 기록이 없습니다"를 출력한다.

### 6.5 슬래시 명령

[확인] 등록은 `DC/command_registry.py:78` `COMMANDS`에 `SlashCommand` 한 항목이다. 처리는 `DC/app.py:17888` `_handle_command`의 분기에 한 줄과 처리기 메서드다. 서버를 부르지 않고 끝나는 본보기는 `/tokens` (`DC/app.py:18239`)다.

| 명령 | 동작 |
|---|---|
| `/runs` | 최근 10건의 목록. 시각, 상태, 지표 요약, trace id 앞 8자 |
| `/runs <id 앞부분>` | 그 작업의 실패 구간과 원인, 지표, Langfuse 주소 |
| `/trace` | 이 대화의 가장 최근 trace 주소를 연다 |

처리기는 `RunsClient`를 `asyncio.to_thread`로 부르고 `format_*`의 결과를 `AppMessage`로 띄운다. 처리기에는 로직을 두지 않는다. 문자열을 만드는 일은 `runs.py`가 하고 거기서 테스트한다.

`/trace`는 기존 처리기 `_handle_trace_command` (`DC/app.py:14508`)의 주소를 만드는 부분만 바꾼다.

[확인] `COMMANDS.md`는 자동 생성물이다. 명령을 더한 뒤 `make commands-catalog`를 돌린다. `make lint`가 이 파일의 최신 여부를 검사한다.

### 6.6 LangSmith

[확정] LangSmith는 쓰지 않는다. `DC/main.py`의 `--no-tracing` 처리 (`:5645`) 옆에서 기본값을 끈다.

```python
os.environ.setdefault("DEEPAGENTS_CODE_LANGSMITH_TRACING", "false")
```

LangSmith 코드는 지우지 않는다. [확인] 끄면 `GitTraceMiddleware`는 기록할 곳이 없어 아무 일도 하지 않는다. `--no-tracing`은 Langfuse도 끈다. 같은 자리에서 `LANGFUSE_TRACING` 상수의 환경변수를 `false`로 둔다.

## 7. 자기 개선 (`improve.py`, `evalsuite/`)

### 7.1 흐름

```
작업이 쌓인다 → /improve (신호 집계, 관찰, 개선안 생성)
            → python -m ...evalsuite (전후 검증)
            → /improve apply <id> (사람 승인 뒤 반영)
```

[확정] 관찰은 자동으로 쌓이고, 기준을 넘으면 알림만 띄우며, 개선은 명령으로 시작한다. 검증을 통과한 개선안은 사람이 승인해야 반영한다.

관찰을 따로 저장하지 않는다. 신호는 trace의 점수로 이미 Langfuse에 있다. 관찰은 `/improve`를 부를 때 그 점수를 모아 만든다.

### 7.2 신호와 임계값

```python
@dataclass(frozen=True, slots=True)
class Threshold:
    signal: str          # 점수 이름
    per_run: float       # 한 작업에서 이 값 이상이면 "해당"으로 센다
    min_runs: int        # 해당 작업이 이 수 이상이면 관찰로 올린다


THRESHOLDS: tuple[Threshold, ...] = (
    Threshold("cg.repeat_failures", per_run=2, min_runs=2),
    Threshold("cg.tool_errors", per_run=5, min_runs=2),
    Threshold("cg.test_failures", per_run=2, min_runs=2),
    Threshold("cg.review_rounds", per_run=2, min_runs=3),
    Threshold("cg.jev_denies", per_run=2, min_runs=2),
    Threshold("cg.gate_denies", per_run=3, min_runs=2),
)


@dataclass(frozen=True, slots=True)
class Observation:
    signal: str
    run_count: int               # 해당한 작업 수
    total_runs: int              # 본 작업 수
    worst_trace_ids: tuple[str, ...]   # 값이 큰 순서로 3개


def find_observations(signals: Mapping[str, Mapping[str, float]],
                      thresholds: Sequence[Threshold] = THRESHOLDS) -> list[Observation]:
    """trace별 신호에서 임계값을 넘은 관찰을 찾는다. 순수 함수다."""
```

이 임계값은 근거 없이 정한 시작값이다. README에 그렇게 적는다.

[확정] 코드가 세고 모델이 적는다. `find_observations`가 센 결과만 모델에게 넘긴다.

### 7.3 개선안 저장

위치는 `<project_root>/.deepagents/improvements/<id>/`다.

```
proposal.md        frontmatter: id, kind(rule|skill), name, status, created_at, observations
                   본문: 근거, 기대 효과
payload/           kind=rule이면 <name>.md (5.1 형식)
                   kind=skill이면 <name>/SKILL.md
validation.json    평가 실행기가 쓴다. 없으면 검증 전이다
```

`status`는 `proposed`, `validated`, `failed`, `applied`, `rejected` 가운데 하나다.

```python
class ImprovementStore:
    """개선안 폴더의 읽기와 쓰기."""

    def __init__(self, project_root: Path) -> None: ...
    def create(self, *, kind: Literal["rule", "skill"], name: str, description: str, body: str,
               rationale: str, observations: Sequence[Observation], now: datetime) -> str:
        """개선안을 저장하고 id를 돌려준다. status는 proposed."""
    def load(self, improvement_id: str) -> Improvement: ...
    def list_ids(self) -> list[str]: ...
    def record_validation(self, improvement_id: str, result: Mapping[str, Any]) -> None:
        """validation.json을 쓰고 status를 validated 또는 failed로 바꾼다."""
    def apply(self, improvement_id: str, memory: MemoryStore, skills_dir: Path) -> None:
        """개선안을 반영한다.

        Raises: ImprovementStateError: status가 validated가 아닐 때.
        """
        # rule: memory.save(...) with source="improvement:<id>"
        # skill: payload/<name>/ 를 skills_dir/<name>/ 로 복사
        # status를 applied로 바꾼다
    def reject(self, improvement_id: str) -> None: ...
```

[확정] 고칠 수 있는 대상은 프로젝트 규칙과 Skills 둘이다. 소스 안의 시스템 프롬프트와 Jev 질문 문구는 대상이 아니다. `create`는 `kind`가 그 둘이 아니면 거부한다.

떨어진 개선안의 폴더는 지우지 않는다. `status`가 `failed`로 남는다.

[확인] 세션 중에 추가된 스킬은 `/reload`나 새 대화 전에는 보이지 않는다 (`DC/plugins/adapters/skills_middleware.py:119`). `apply` 뒤에 그 안내를 출력한다.

### 7.4 `propose_improvement` 도구와 `/improve`

```python
def propose_improvement(
    kind: Literal["rule", "skill"],
    name: str,
    description: str,
    body: str,
    rationale: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    runtime: ToolRuntime[Any, Any],
) -> Command[Any]:
    """개선안 하나를 저장한다. 반영하지 않는다."""
    # ImprovementStore.create(...)를 부르고 id와 다음 단계 안내를 돌려준다
    # 멈추지 않는다
```

`/improve`의 하위 명령이다.

| 명령 | 동작 |
|---|---|
| `/improve` | 1) `RunsClient`로 최근 작업의 신호를 읽는다. 2) `find_observations`. 3) 관찰이 없으면 그렇다고 출력하고 끝. 4) 관찰 표와 예상 규모("모델 호출 약 N회")를 출력한다. 5) 관찰 표를 담은 지시문을 `_handle_user_message`로 에이전트에게 보낸다. 에이전트가 `propose_improvement`를 부른다 |
| `/improve list` | 개선안 목록과 상태 |
| `/improve show <id>` | 개선안 내용과 검증 결과. 검증 전이면 실행할 명령을 보여준다 |
| `/improve apply <id>` | 검증 결과를 다시 보여주고 `ImprovementStore.apply`를 부른다. `validated`가 아니면 거부 |
| `/improve reject <id>` | `status`를 `rejected`로 바꾼다 |

에이전트에게 보내는 지시문의 요지. 관찰 표, 가장 나빴던 작업의 trace id, "원인을 추정하고 프로젝트 규칙이나 스킬 하나로 고칠 수 있는 것만 `propose_improvement`로 제안하라. 근거가 약하면 제안하지 마라."

[미확인] 슬래시 명령 처리기에서 `_handle_user_message` (`DC/app.py:19342`)로 지시문을 보내는 경로의 실제 동작. M7에서 확인한다.

**알림.** TUI가 시작될 때 백그라운드에서 `find_observations`를 한 번 돌리고, 관찰이 있으면 "개선할 관찰이 N건 있습니다. /improve로 시작하세요"를 띄운다. 실패는 조용히 넘긴다.

### 7.5 평가 실행기 (`evalsuite/`)

이 절의 설계는 평가 방법론 조사를 반영했다. 그 조사는 출처 원문 대조를 통과하지 못했다 (스냅샷 38건이 모두 차단됐다). 아래 근거는 조사 에이전트가 읽은 요약 수준이고 검증된 인용이 아니다. 조사 산출물은 `docs/research/agent_eval_methodology_20261111_152903/`에 있다.

조사가 여러 축에서 같은 방향으로 가리킨 것.

- 과제 서너 개를 한 번씩 돌린 전후 비교는 개선을 입증하지 못한다. 그 크기의 묶음은 "깨지지 않았는지"를 보는 회귀 검사다.
- 에이전트 실행은 온도 0에서도 흔들린다. 과제당 여러 번 돌리고, 필수 조건은 "매번 통과"로 본다.
- 과제마다 고치기 전에 실패하는 목표 테스트와 원래 통과하는 회귀 테스트를 나눈다.
- 테스트와 채점 코드는 에이전트가 고칠 수 없는 곳에 둔다.

**과제 형식.** `evalsuite/tasks/<이름>/`

```
task.toml           name, instruction_file, test_target, test_regression, timeout_s
instruction.md      에이전트에게 줄 요청문. 검증이 보는 것을 빠짐없이 적는다
repo/               시작 상태의 작은 저장소
tests_target/       고치기 전에는 실패하고 고친 뒤에는 통과해야 하는 테스트
tests_regression/   고치기 전에도 통과하는 테스트
solution.patch      참조 해법
```

과제는 셋이다. [제안] 버그 수정 하나, 함수 추가 하나, 함정 과제 하나. 함정 과제는 저장소의 문서에 틀린 테스트 명령이 적혀 있어 반복 실패가 생기기 쉬운 과제다. README의 T8에서 자기 개선을 재현하는 데 쓴다.

**과제 자체의 검사.** 실행기가 과제를 쓰기 전에 확인한다.

```python
def verify_task(task: Task) -> list[str]:
    """과제 정의의 문제를 문장 목록으로 돌려준다. 모델을 부르지 않는다."""
    # 1) repo/ 상태에서 tests_regression이 통과하는가
    # 2) repo/ 상태에서 tests_target이 실패하는가
    # 3) solution.patch를 적용하면 둘 다 통과하는가
```

**실행.**

```python
@dataclass(frozen=True, slots=True)
class TrialResult:
    task: str
    variant: Literal["baseline", "candidate"]
    trial: int
    target_passed: bool
    regression_passed: bool
    tests_untouched: bool
    signals: Mapping[str, float]
    trace_id: str | None
    error: str | None


def run_trial(task: Task, variant: str, trial: int, *, improvement: Improvement | None,
              dcode: Path, workdir: Path, runs: RunsClient | None) -> TrialResult:
    """과제를 한 번 실행하고 채점한다."""
    # 1) workdir에 task.repo를 복사하고 git init, 커밋 하나 (이력 누출 방지)
    # 2) candidate이면 개선안의 payload를 그 저장소의 .deepagents/memory 또는 .deepagents/skills에 넣는다
    # 3) dcode -n "<instruction>" 실행. 출력에서 thread id를 얻는다
    # 4) 계획 승인: dcode -r <thread> -n "승인" 실행
    #    미결 질문이 나오면 task.toml의 answers를 차례로 준다. 없으면 실패로 기록한다
    #    왕복 상한 5회
    # 5) 채점: tests_target과 tests_regression을 과제 폴더에서 workdir로 복사해 실행한다
    #    에이전트가 쓴 같은 이름의 파일이 있으면 덮어쓴다
    # 6) runs가 있으면 wait_for로 trace를 기다려 signals를 읽는다. 없거나 안 보이면 빈 사전
```

[확정] 비대화 실행은 계획과 질문을 출력하고 끝나며, 답은 다시 호출해서 준다. 평가 실행기가 그 "서비스" 역할을 한다.

[미확인] `dcode -n`의 출력에서 thread id를 얻는 방법. M8에서 `DC/client/non_interactive.py`의 출력 형식을 확인한다. `--output-format json` 같은 기계용 출력이 있으면 그것을 쓴다.

**통과 기준.** [제안]

```python
def judge(results: Sequence[TrialResult], *, trials: int) -> dict[str, Any]:
    """전후 결과에서 통과 여부를 정한다. 순수 함수다."""
```

| 조건 | 내용 |
|---|---|
| A. 필수 | candidate의 모든 과제, 모든 반복에서 목표 테스트와 회귀 테스트가 통과한다 |
| B. 필수 | baseline에서 통과하던 과제가 candidate에서 한 번이라도 실패하면 탈락이다 (A에 포함되지만 사유를 따로 적는다) |
| C. 지표 | 과제별로 신호의 평균을 전후로 비교한다. candidate 평균이 baseline 평균 + 잡음 폭 이하이면 "나빠지지 않음"이다 |

잡음 폭은 baseline 반복들의 최댓값과 최솟값의 차이다. 반복 수 기본값은 3이다. 반복이 1이면 잡음 폭을 잴 수 없으므로 C를 "판정 불가"로 적고 A만으로 판정한다.

신호를 읽지 못했으면(Langfuse 키 없음) C는 "판정 불가"다. A는 Langfuse 없이 판정된다.

결과에 한계를 그대로 적는다. `validation.json`의 `limits` 필드에 "과제 3개, 반복 3회의 회귀 검사다. 개선의 통계적 입증이 아니다"를 넣는다.

**명령.**

```
python -m deepagents_code.assistant.evalsuite verify
python -m deepagents_code.assistant.evalsuite run --improvement <id> [--trials 3] [--project <경로>]
python -m deepagents_code.assistant.evalsuite run --baseline-only [--trials 1]
```

`run`은 시작할 때 규모를 출력한다. "과제 3개 × 반복 3회 × 전후 2 = 에이전트 실행 18회, Jev 호출 약 N회". 끝나면 `ImprovementStore.record_validation`을 부른다.

`--baseline-only`는 README의 T3에 쓴다.

## 8. Jev 보정 (`calibration/`)

[확정] 보정 사례는 Sonnet급 모델이 만들고, Jev로 평가한 뒤 질문 문구를 고친다. 정답은 생성할 때 지정한다. 문구를 고치는 묶음과 확인용 묶음을 나눈다.

**사례 형식.** `calibration/cases/J<n>.jsonl`, 한 줄에 하나다.

```json
{"id": "J1-007", "split": "dev", "label": 0, "state": "...", "note": "완료 조건이 '잘 동작한다'뿐이다"}
```

`split`은 `dev`(문구를 고칠 때 본다) 또는 `holdout`(확인에만 쓴다)이다. `label`은 0 또는 1이다.

질문마다 40건을 만든다. [제안] `dev` 24건, `holdout` 16건이고 각 묶음에서 0과 1이 절반씩이다. 조사에서 판정 게이트는 차단해야 할 사례와 허용해야 할 사례를 모두 넣으라고 했다.

**생성.** 사례 파일은 저장소에 커밋하는 산출물이다. 생성은 한 번 하고, 사람이 일부를 훑어본다.

```
python -m deepagents_code.assistant.calibration generate --question J1 --count 40
```

생성 지시문은 "정답이 0인 계획을 써라: 완료 조건이 검증 불가능하다"처럼 정답과 이유를 지정한다. 생성 모델에게 정답을 매기게 하지 않는다. 모델과 키는 dcode의 모델 설정을 쓴다. 실행 전에 규모를 출력한다.

**평가.**

```
python -m deepagents_code.assistant.calibration evaluate --question J1 --split dev
python -m deepagents_code.assistant.calibration evaluate --all --split holdout
```

```python
@dataclass(frozen=True, slots=True)
class CalibrationReport:
    question: str
    split: str
    n: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    threshold: float

    @property
    def precision(self) -> float | None: ...
    @property
    def recall(self) -> float | None: ...


def evaluate(question: str, cases: Sequence[Case], decider: Decider) -> CalibrationReport:
    """사례 묶음에 판정기를 돌려 혼동 행렬을 만든다."""
```

**절차.** `dev`로 문구와 임계값을 고친다. 고칠 때마다 `dev` 결과를 본다. 끝나면 `holdout`을 한 번 돌려 README에 적는다. `holdout` 결과를 보고 문구를 다시 고치지 않는다.

질문별로 무엇이 더 나쁜 오류인지가 다르다.

| 질문 | 더 나쁜 오류 | 이유 |
|---|---|---|
| J1~J3 | 문제 있는 계획을 통과 | 다만 리뷰어와 사람이 뒤에 있다 |
| J4 | 범위 밖 호출을 통과 | 뒤에 아무도 없다. 재현율을 우선한다 |
| J5 | 변경 필요를 불필요로 판정 | 쓰기 차단이 뒤에 있다. 안내만 틀린다 |
| J6 | 관련 기억을 놓침 | 색인이 뒤에 있다 |

## 9. 테스트 전략

### 9.1 원칙

- 반드시 지켜져야 하는 동작은 가짜 모델로 테스트한다. 결과가 매번 같고 비용이 없다.
- 실제 모델 실행은 README의 통합 확인 몇 개로만 둔다.
- 사용자가 볼 수 있는 동작을 단언한다. 도구가 실행됐는지, 파일이 생겼는지, 어떤 메시지가 돌아왔는지.

### 9.2 테스트 도구

`tests/unit_tests/assistant/fakes.py`

```python
class FakeReviewer: ...      # 회차별 ReviewResult 대본
def scripted_model(messages: Sequence[AIMessage]) -> BaseChatModel:
    """대본대로 답하는 모델. deepagents_code._fake_models._ToolBindingFakeModel을 쓴다."""
def tool_call(name: str, args: Mapping[str, Any], call_id: str) -> AIMessage: ...
def make_options(tmp_path: Path, *, decider: Decider | None = None, reviewer=None, interactive: bool = True) -> PlanGateOptions: ...
```

[확인] 가짜 모델의 기반은 이미 있다 (`DC/_fake_models.py:40` `_ToolBindingFakeModel`). 대본은 `messages=iter([AIMessage(...)])`로 넣는다. 도구 호출 대본의 본보기는 `tests/unit_tests/hooks/test_server_lifecycle.py:322`다.

[확인] 미들웨어 하나만 테스트하는 가장 싼 방법은 그래프 없이 `wrap_tool_call`을 직접 부르는 것이다. 본보기는 `tests/unit_tests/test_memory_guard.py:35`다. 그래프를 실제로 돌리는 본보기는 `tests/unit_tests/test_end_to_end.py:140`이고, `ainvoke`를 쓴다.

[확인] 멈춤과 재개를 테스트하려면 체크포인터(`InMemorySaver`)와 `thread_id`가 필요하다. 첫 `ainvoke`가 멈춤에서 끝나고, 두 번째 `ainvoke(Command(resume=...))`로 재개한다.

### 9.3 반드시 있어야 하는 테스트

게이트의 불변 조건이다. 각각 `test_gate.py`에 그래프를 실제로 돌리는 테스트로 둔다.

| # | 대본 | 단언 |
|---|---|---|
| G1 | 가짜 모델이 계획 없이 `write_file`을 부른다 | 파일이 생기지 않는다. 결과 메시지가 오류 상태다 |
| G2 | 가짜 모델이 계획 없이 `execute("rm -rf x")`를 부른다 | 실행되지 않는다 |
| G3 | 가짜 모델이 계획 없이 `execute("ls")`를 부른다 | 실행된다 |
| G4 | 탐색 없이 `submit_plan`을 부른다 | 거부된다. 계획 파일이 없다 |
| G5 | 탐색, 제출, 승인 요청, 재개 값 "승인", `targets` 안의 `write_file` | 파일이 생긴다. 계획 status가 approved다 |
| G6 | G5 뒤에 `targets` 밖의 `write_file`. 판정기 J4=0 | 파일이 생기지 않는다 |
| G7 | G5 뒤에 `targets` 밖의 `write_file`. 판정기 J4=1 | 파일이 생긴다. 계획의 `targets`에 경로가 추가된다 |
| G8 | 승인 요청, 재개 값 "거부" | phase가 idle이다. 이후 `write_file`이 거부된다 |
| G9 | 승인 요청, 재개 값 "테스트도 추가해 주세요" | phase가 planning이다. 모델이 그 문장을 받는다 |
| G10 | 리뷰어가 1회차에 의견, 2회차에 의견 | 두 번째 제출 뒤 status가 reviewed다. 리뷰 기록에 두 회차가 있다 |
| G11 | 승인 전 `write_file(".deepagents/plans/x.md")`와 승인 뒤 같은 호출 | 둘 다 거부된다 |
| G12 | 승인 전 `task(subagent_type="general-purpose")` | 거부된다 |
| G13 | 서브에이전트 스택의 미들웨어에 `write_file` 호출을 직접 넣는다 | 거부된다 |
| G14 | 비대화. 승인 요청 뒤 새 실행에 사람 메시지 "승인" | phase가 executing이다 |
| G15 | 비대화. 승인 요청 뒤 새 실행에 사람 메시지 "다시 생각해 보자" | phase가 planning이다. `write_file`이 거부된다 |
| G16 | 판정기가 전송 실패를 돌려준다 | J4가 필요한 호출이 거부된다 |
| G17 | `plan_gate=None`으로 만든 에이전트에서 `write_file` | 실행된다 (기존 동작 보존) |
| G18 | 사람이 질문에 답한 뒤 모델이 `open_questions=[]`로 다시 제출. 그 전에 리뷰어가 낸 질문은 아직 답이 없다 | 계획 파일의 "결정 사항"에 사람의 답이 그대로 있다. 답이 없는 질문이 "미결 질문"에 남아 있다 |
| G19 | 승인 뒤 `complete_plan` 없이 턴이 끝난다. 새 사람 메시지 뒤에 `targets` 안의 `write_file`. 판정기 J4=0 | 파일이 바뀌지 않는다 |

G1과 G5는 README의 T4와 T3에 대응한다.

### 9.4 기존 테스트

업스트림 테스트는 고치지 않는다. 지우거나 건너뛰게 표시하지 않는다. 우리 변경으로 깨지는 테스트가 있으면 13장의 절차를 따른다.

고쳐도 되는 경우는 셋이다. 삭제한 remember 스킬을 직접 검사하는 테스트, 명령 목록이나 `ProjectPaths` 필드 수를 고정값으로 단언하는 테스트, `dcode`를 서브프로세스로 띄우는 통합 테스트(`tests/integration_tests/` 아래)의 환경변수 사전에 `DEEPAGENTS_CODE_PLAN_GATE=0`을 더하는 것. 세 번째는 테스트의 단언을 바꾸지 않는다. 고친 테스트와 이유를 README에 적는다.

[확인] pytest 설정은 예상하지 못한 경고를 실패로 처리한다 (`pyproject.toml:363` `filterwarnings = ["error", ...]`). 단위 테스트는 소켓이 막힌다 (`Makefile:23`의 `--disable-socket`). Jev와 Langfuse를 부르는 코드는 테스트에서 가짜로 바꿔야 한다. `langfuse`는 `tracing.py` 안에서만, 함수 안에서 늦게 import한다. 모듈 상단에서 import하지 않는다.

### 9.5 lint

[확인] ruff는 모든 규칙을 켜고 (`pyproject.toml:259`) 줄 길이는 88이다. 한글은 폭 2로 센다. 한국어 docstring에서 확인된 것.

| 통과 | 걸림 |
|---|---|
| 한글, `…`, `→` | EN DASH (`RUF002`), 전각 괄호와 전각 콜론 (`RUF003`) |
| Google 형식의 `Args:`, `Returns:`, `Raises:` | 88자를 넘는 줄 (`E501`). 한글 44자가 한 줄이다 |

- 상대 import는 금지다 (`ban-relative-imports = "all"`). `from deepagents_code.assistant.plan import Plan`처럼 쓴다.
- 요약 줄은 마침표로 끝낸다.
- `make lint`는 `ruff check`, `ruff format --diff`, 타입 검사 `ty`, 명령 목록 검사, 작업 폴더 사용 검사를 돈다 (`Makefile:57`). [확인] 마지막 검사는 `Path.cwd()` 사용을 잡는다. 서버 코드에서 `Path.cwd()`를 쓰지 않는다.

## 10. 마일스톤

각 마일스톤은 실행해서 확인하는 검사로 끝난다. 검사가 통과하기 전에 다음으로 넘어가지 않는다. 순서는 의존성 순이다. 순수 모듈이 먼저다.

### M0. 작업 사본과 기준선

1. 커밋 `08a7e5a1`의 `Day09/deepagents/libs/code/`를 `/home/sds/workspace/dcode-assistant/libs/code/`로 복사한다. `git init`하고 첫 커밋을 만든다.
2. 복사 원본은 주석을 달기 전의 커밋이다. `git archive 08a7e5a1 Day09/deepagents/libs/code`로 꺼낸다. 수업 저장소의 작업 트리는 건드리지 않는다.
3. Python 3.14 가상환경을 만들고 dcode와 테스트 도구를 설치한다. [확인] `pyproject.toml`의 `[tool.uv.sources]`는 이 사본에 없는 폴더를 가리킨다. `uv pip install --no-sources -e .`와 `[dependency-groups]`의 `test` 그룹 패키지를 따로 설치한다. `make test`와 `make lint`가 `uv run --group test`를 쓰므로 그대로는 돌지 않을 수 있다. 돌지 않으면 Makefile의 명령을 가상환경의 `pytest`와 `ruff`로 직접 실행한다.
4. 기준선을 잰다. 단위 테스트 전체와 lint를 한 번 돌려 결과를 `BASELINE.md`에 적는다. 실패가 있으면 목록을 적는다. 이후 "기존 기능이 깨지지 않았다"는 이 목록과의 비교다.
5. `langfuse>=4.15.1,<5`를 의존성에 더하고 `uv lock`을 돌린다.

검사: `dcode --version`이 작업 사본의 경로를 보여준다. 가짜 모델 점검(`Day09/scripts/smoke_dcode.sh`를 작업 사본용으로 옮긴 것)이 통과한다. `BASELINE.md`가 있다.

### M1. 순수 모듈

`options.py`, `frontmatter.py`, `plan.py`, `policy.py`, `_paths.py` 수정.

검사: `test_frontmatter.py`, `test_plan.py`, `test_policy.py` 통과. 이 세 파일에 대한 lint 통과.

### M2. 판정기와 리뷰어

`decider.py`, `reviewer.py`, `prompts.py`, `tests/.../fakes.py`.

검사: `test_decider.py`, `test_reviewer.py` 통과. 실제 Jev 한 번 호출로 응답 형태 확인(질문 하나, 비용 미미).

### M3. 게이트와 계획 도구

`gate.py`의 `PlanGateMiddleware`, `tools.py`의 계획 도구 셋, `agent.py`와 `server_graph.py`와 `_server_config.py`와 `main.py`의 연결.

먼저 확인할 [미확인]: `ask_user` 모양의 멈춤이 다른 도구 이름으로도 TUI에서 뜨는지(가장 먼저. 안 되면 3.6절의 승인 화면 설계가 바뀐다), 백엔드 `execute` 호출 형태, 모델 객체를 얻는 자리.

검사: 9.3절의 G1~G11, G14~G19 통과. 기준선의 단위 테스트가 그대로 통과. TUI에서 실제 모델로 한 번 돌려 승인 화면이 뜨는지 눈으로 확인.

### M4. 서브에이전트

`SubagentWriteBlockMiddleware`, `subagents.py`, `_subagent_cli_middleware`와 `_inject_fs_tools_into_subagents` 수정.

먼저 확인할 [미확인]: fork 서브에이전트의 최종 도구 목록.

검사: G12, G13 통과. 그래프를 만든 뒤 탐색 서브에이전트의 도구 목록이 `ls`, `read_file`, `glob`, `grep`뿐인지 단언하는 테스트.

### M5. Memory

`memory.py`, `propose_rule`, `agent.py`의 메모리 블록 수정, `/remember` 교체, remember 스킬 삭제.

검사: `test_memory.py` 통과. 그래프 테스트 둘. 작업 기록 두 건 중 판정기가 고른 한 건만 시스템 프롬프트에 들어가는지. 세션 중에 저장한 규칙이 다음 모델 호출에 들어가는지.

### M6. 추적

`tracing.py`, `runs.py`, `make_graph` 수정, `build_stream_config` 수정, LangSmith 기본 끄기.

먼저 확인할 [미확인]: 구간이 같은 trace에 들어가는지, `mask`의 적용 범위, 서버 환경에 키가 닿는지.

검사: `test_tracing.py`, `test_runs.py` 통과(가짜 클라이언트). 실제 Langfuse 키로 요청 하나를 돌리고 `RunsClient.list_runs`와 `failures`가 결과를 돌려주는지. 가짜 비밀값이 가려져 올라갔는지.

### M7. 슬래시 명령과 개선안

`improve.py`, `propose_improvement`, `/runs`, `/improve`, `/trace`.

검사: `test_improve.py` 통과. `make commands-catalog` 뒤 `make lint` 통과. TUI에서 `/runs`와 `/improve list`가 뜨는지 눈으로 확인.

### M8. 평가 실행기와 과제

`evalsuite/`, 과제 셋.

검사: `python -m ...evalsuite verify` 통과. `test_evalsuite.py`의 `judge` 테스트 통과. `--baseline-only --trials 1` 한 번 실행.

### M9. 보정과 README

`calibration/`, 사례 생성과 평가, 문구 조정, README.

검사: `holdout` 결과가 README에 있다. README의 테스트 케이스를 처음부터 끝까지 한 번 따라 한다.

## 11. README 테스트 케이스

채점자가 따라 할 순서다. 각 항목에 명령, 기대하는 결과, 대응하는 평가 항목을 적는다. 실제 모델을 부르는 항목에는 예상 규모를 적는다. 규모는 M9에서 재서 채운다.

| # | 시나리오 | 방법 | 평가 항목 |
|---|---|---|---|
| T0 | 코드 품질 | `make lint`, `make test` | 1-1, 1-2, 1-3 |
| T1 | 키 없이 실행 | `TYPESAFE_API_KEY` 없이 `dcode` | 게이트 전제 |
| T2 | 코드 읽기 질문 | 샘플 저장소에서 질문. 탐색 뒤 답변, 계획 파일 없음 | 게이트 범위 |
| T3 | 버그 수정 전체 흐름 | 샘플 저장소에서 수정 요청. 탐색, 계획 파일, 리뷰 기록, 승인 화면, 코드 변경, 테스트 | 2-1 ~ 2-4 |
| T4 | 승인 전 쓰기 차단 | `pytest tests/unit_tests/assistant/test_gate.py -k "G1 or G2 or G11"` | 2-4 |
| T5 | 범위 변경 시 재검토 | `pytest ... -k "G6 or G7"` | 2-4 |
| T6 | 모호한 요청 | 해석이 둘인 요청. 질문 화면이 뜨고 답이 계획의 "결정 사항"에 적힌다 | 2-1, 2-3 |
| T7 | Memory | T3 뒤 TUI를 닫고 다시 열어 관련 요청. `.deepagents/memory/`의 작업 기록, 새 계획의 "참고한 Memory" 절 | 3-1, 3-2 |
| T8 | 자기 개선 | 함정 과제를 두 번 수행, `/improve`, 평가 실행기, `/improve apply` | 3-3, 3-4 |
| T9 | 모니터링 | `/runs`, `/runs <id>`, `/trace` | 4-1 ~ 4-4 |

T4와 T5는 가짜 모델 테스트다. 모델을 유도하지 않으므로 매번 같은 결과가 나온다. T3에서 같은 동작을 실제 모델로도 볼 수 있다.

README에 함께 적는 것. 필요한 키와 없을 때의 동작, 게이트 끄기 스위치와 그 용도, 비대화 호출 형식, 고친 업스트림 테스트 목록, 알려진 한계, 자기 개선 검증의 한계, Jev 보정 결과.

## 12. 코드 조사 뒤에 정한 것

코드 조사에서 필요해져 이 문서가 제안했고, 사용자가 2026-11-11에 P1~P13 전부를 확정했다. 본문의 [제안] 표시는 모두 [확정]으로 읽는다.

| # | 제안 | 대안 | 영향 |
|---|---|---|---|
| P1 | 계획은 에이전트가 `submit_plan` 도구로 내용을 넘기고 게이트 코드가 파일을 쓴다 | 에이전트가 파일을 직접 쓴다 | 대안은 계획 폴더 쓰기 금지와 충돌한다 |
| P2 | LLM 리뷰어는 게이트 코드가 직접 부르는 모델 호출이다 | 리뷰어 서브에이전트 | 대안은 리뷰 실행을 모델의 선택에 맡긴다 |
| P3 | 서브에이전트는 승인 뒤에도 항상 읽기 전용이다 | 승인 뒤 쓰기 허용 | 대안은 서브에이전트 안에서 범위 검사를 할 수 없다. 제안은 쓰기 위임을 못 쓰게 한다 |
| P4 | `DEEPAGENTS_CODE_PLAN_GATE=0`으로 게이트와 키 검사를 끌 수 있다 | 스위치 없음 | 대안은 `dcode`를 서브프로세스로 띄우는 통합 테스트와 가짜 모델 점검이 깨진다. 제안은 "키 없으면 못 쓴다"에 구멍을 낸다 |
| P5 | Jev 임계값 0.5에서 시작해 보정으로 조정한다 | 고정 | Jev의 답이 확률이라 자르는 기준이 필요하다 |
| P6 | 작업의 끝은 `complete_plan` 도구이고 게이트가 `test_command`를 직접 실행한다 | 모델이 테스트 결과를 보고한다 | 제안은 테스트 통과를 실행 결과로 기록한다 |
| P7 | 관찰을 따로 저장하지 않고 `/improve` 때 Langfuse 점수에서 만든다 | 작업 끝마다 관찰 문장을 저장 | Langfuse 조회가 15~30초 늦어 작업 끝에 바로 셀 수 없다 |
| P8 | 자기 개선 검증은 과제 3개 × 반복 3회이고, 필수 기준은 "매번 테스트 통과"다. 지표는 잡음 폭 안이면 통과다 | 반복 1회 | 제안은 에이전트 실행이 18회로 는다. 반복 1회는 지표를 판정할 수 없다 |
| P9 | 비대화에서 승인은 다음 호출의 사람 메시지가 정확히 "승인"류일 때만 인정한다 | Jev나 모델이 답을 해석 | 제안은 결정론적이다. 서비스가 정해진 단어를 보내야 한다 |
| P10 | 새 패키지 이름은 `assistant`다 | 다른 이름 | 없음 |
| P11 | `/remember`는 규칙을 바로 저장하고, 기존 remember 스킬은 지운다 | 스킬을 고쳐 유지 | 기존 스킬은 `AGENTS.md`를 직접 고치게 한다 |
| P12 | Langfuse는 4.15.x로 고정한다 | 최신 5.x | 이 문서의 API는 4.15.1에서 확인했다 |
| P13 | 승인 뒤에 사용자가 새 메시지를 보내면 `targets` 안의 쓰기도 J4를 거친다 | 새 메시지마다 재승인, 또는 그대로 허용 | 재승인은 "계속해" 한마디에도 승인 화면이 뜬다. 그대로 허용은 끝나지 않은 계획의 승인이 무관한 요청에 쓰인다 |

2026-11-11에 함께 확정한 것.

- 작업 폴더는 `/home/sds/workspace/dcode-assistant`다.
- `# [해설]` 주석은 넣지 않는다. 주석을 달기 전의 원본 커밋 `08a7e5a1`의 `Day09/deepagents/libs/code`를 복사한다. 업스트림과의 차이가 우리 변경만 남는다.
- 탐색 서브에이전트는 주 모델과 같은 모델을 쓴다. 사양에 `model`을 넣지 않는다.

## 13. 멈추고 묻는 절차

구현 중에 다음을 만나면 우회하지 않는다. 무엇을 봤는지 적고 사용자에게 묻는다.

1. [미확인] 항목이 이 문서의 가정과 다르게 동작한다.
2. 업스트림 테스트가 우리 변경으로 깨지고, 9.4절의 두 경우에 해당하지 않는다.
3. 게이트를 지나가는 새 경로를 찾았다 (쓰기가 가능한데 `classify_call`이 `allow`를 주는 도구).
4. `DC/tui/` 아래를 고쳐야만 동작한다.
5. 이 문서의 [확정] 결정과 코드의 제약이 충돌한다.

하지 않는 것.

- 테스트를 지우거나 건너뛰게 표시하지 않는다.
- 판정 실패를 통과로 처리하지 않는다.
- 평가 과제의 기대 결과를 코드에 박아 넣지 않는다.
- 실패한 평가 결과나 떨어진 개선안의 기록을 지우지 않는다.
- 키 값을 기록, 오류 메시지, 결과 파일에 남기지 않는다.

## 14. 알려진 한계

- 사람에게 되묻는 판단은 모델에 맡겼다. 놓친 질문은 사람이 승인할 때 잡아야 한다.
- 계획이 `complete_plan` 없이 남으면 phase가 `executing`으로 유지된다. 이후 요청의 쓰기는 전부 J4에 기댄다. 사용자가 계획을 닫을 명령은 아직 없다.
- 보호 폴더에 대한 `execute` 검사는 문자열 대조다. 경로를 변수로 조립하는 명령은 놓칠 수 있다. 승인 전에는 읽기 전용 명령만 통과하므로 그때는 안전하다. 승인 뒤에는 J4가 남은 방어다.
- J6는 요청문만 보고 기억을 고른다. 짧은 요청에서는 관련 기억을 놓칠 수 있다. 색인이 항상 주입되므로 모델이 직접 열 수 있다.
- Langfuse 키가 없으면 평가 4번 항목과 자기 개선 전체가 동작하지 않는다.
- 자기 개선 검증은 회귀 검사다. 개선안이 실제로 도움이 됐는지는 입증하지 않는다.
- 신호의 임계값과 Jev 임계값의 시작값은 근거 없이 정했다.
- 평가 방법론 조사의 인용은 원문 대조를 거치지 못했다.
