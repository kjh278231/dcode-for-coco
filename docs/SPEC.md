# dcode 기반 Coding Assistant 구현 명세

상태: M5까지 구현 (2026-11-11). 진행과 명세에서 벗어난 점은 `PROGRESS.md`에 적는다. 결정의 배경은 `docs/DESIGN.md`에 있다. 두 문서가 다르면 이 문서가 맞다.

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
| Jev 키(`TYPESAFE_API_KEY` 또는 `OPENROUTER_API_KEY`) 사전 검사 | 클라이언트 `main.py` | 서버를 띄우기 전에 친절한 안내로 끝낸다 |
| `/improve`, `/runs`, `/trace`, `/remember` | 클라이언트 `app.py` | 슬래시 명령 처리기가 거기 있다 |
| 평가 실행기, Jev 보정 스크립트 | 별도 명령 (`python -m`) | 오래 걸리고 TUI와 무관하다 |

### 1.3 패키지 구조 [제안: 패키지 이름 `assistant`]

```
DC/assistant/
  __init__.py          공개 이름만 다시 내보낸다
  options.py           상수, Phase, PlanGateOptions(M2에서 추가)
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
| `DC/_env_vars.py` | 상수 `PLAN_GATE_JEV_THRESHOLD` 추가 (`JevDecider.from_environment`가 읽는다) | M2 |
| `DC/_env_vars.py` | 상수 `PLAN_GATE` 추가 (M3). [M6] `LANGFUSE_TRACING = "DEEPAGENTS_CODE_LANGFUSE_TRACING"` 추가 (M3에서 빠져 있었다) | M3, M6 |
| `DC/_paths.py` | `ProjectPaths`에 `plans_dir`, `memory_dir`, `improvements_dir` 추가 | M1 |
| `DC/_server_config.py` | `ServerConfig.plan_gate` 필드와 직렬화 | M3 |
| `DC/client/launch/server_manager.py` | `ServerConfig.from_cli_args` 호출에 `plan_gate` 전달 | M3 |
| `DC/server_graph.py` | `create_cli_agent`에 옵션 전달, `make_graph`에 `tracing.run_config(config, runtime.model_environment)` | M3, M6 |
| `DC/agent.py` | `create_cli_agent` 인자, 미들웨어와 서브에이전트 등록, 승인 술어. [M4] `_subagent_cli_middleware`에 `SubagentWriteBlockMiddleware`, 확장 도구 이름을 `plan_gate.mcp_mutating_tool_names`에 더함 | M3, M4 |
| `DC/main.py` | LangSmith 기본 끄기, `--no-tracing`이 `LANGFUSE_TRACING`도 끈다 (M6). [M5] 키 검사는 `client/launch/server_manager.py`로 옮겼다 | M3, M6 |
| `DC/client/launch/server_manager.py` | `start_server_and_get_agent`에서 Jev 키 검사 (3.10) | M5 |
| `DC/client/non_interactive.py` | `server_session` 호출에 `plan_gate` 전달 | M3 |
| `libs/code/scripts/check_process_cwd.py` | `run_non_interactive`의 `Path.cwd` 허용 항목 토큰 `99c1d085` → `86fa45ed` (사유 문구 그대로). 같은 문장에 `plan_gate=`를 더해 토큰이 바뀌었다 | M3 |
| `scripts/smoke_dcode.sh`, `tests/integration_tests/test_headless_resume.py` | `DEEPAGENTS_CODE_PLAN_GATE=0` | M3 |
| `DC/config.py` | `build_stream_config`에 Langfuse metadata, `_PROJECT_DOTENV_DENIED_ENV_KEYS`에 `LANGFUSE_*` 넷 (O9) | M6 |
| `DC/command_registry.py` | `/remember` 설명과 인자 표시, `_STATIC_SKILL_ALIASES`에서 `remember` 제거 | M5 |
| `libs/code/COMMANDS.md` | `generate_commands_catalog.py`로 다시 만듦 | M5 |
| `DC/_env_vars.py`, `DC/agent.py` docstring | "the `remember` skill" → "`/remember`" | M5 |
| `tests/unit_tests/smoke_tests/snapshots/system_prompt_*_local.md`, `tests/unit_tests/test_app.py::TestRememberRequiresMessages` | 삭제한 remember 스킬을 직접 검사 (9.4) | M5 |
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
# [M4] 원격 서브에이전트를 시작하거나 지시를 바꾸는 도구. 단계와 관계없이 거부한다
ASYNC_SUBAGENT_TOOLS: frozenset[str] = frozenset({"start_async_task", "update_async_task"})
# [M4] 서브에이전트 허용 목록. 그 밖은 거부. execute는 읽기 전용 명령만
SUBAGENT_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {"ls", "read_file", "glob", "grep", "execute", "ask_user", "compact_conversation",
     "fetch_url", "web_search", "get_current_thread_id"}
)
PLAN_TOOLS: frozenset[str] = frozenset(
    {"submit_plan", "request_plan_approval", "complete_plan", "propose_rule", "propose_improvement"}
)
EXPLORER_SUBAGENT_NAME: str = "explorer"
MAX_REVIEW_ROUNDS: int = 2
JEV_THRESHOLD_DEFAULT: float = 0.5
APPROVE_WORDS: frozenset[str] = frozenset({"승인", "approve", "approved", "yes", "y"})
REJECT_WORDS: frozenset[str] = frozenset({"거부", "reject", "rejected", "no", "n"})
PROTECTED_DIRS: tuple[str, ...] = (
    ".deepagents/plans", ".deepagents/memory", ".deepagents/improvements"
)  # 프로젝트 루트 기준. policy와 gate가 같이 쓴다
Phase = Literal["idle", "planning", "awaiting_approval", "executing"]


# Decider와 PlanReviewer는 TYPE_CHECKING 아래에서만 import한다. 두 모듈이 options를 import한다.


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

게이트 대상 도구를 dcode의 승인 맵(`DC/agent.py:2365` `_add_interrupt_on`)에서 얻지 않고 상수로 둔다. [확인] 그 맵은 `--yolo`나 비대화에서 아예 만들어지지 않고 (`DC/agent.py:2969`), `web_search`, `fetch_url`, `task`처럼 쓰기가 아닌 도구도 담는다. MCP 도구만 기존 함수 `gated_mcp_tool_names` (`DC/auto_mode.py:773`)로 얻어 `mcp_mutating_tool_names`에 넣는다. [M4, 사용자 결정] 확장 도구(`extension_registry.tool_units()`, `DEEPAGENTS_CODE_EXPERIMENTAL`일 때만)의 이름도 `create_cli_agent` 첫머리에서 이 필드에 더한다. 주석 없는 MCP처럼 승인 전에는 거부하고 승인 뒤에는 J4를 거친다. 내장 도구의 분류는 그대로다. 확장이 내장 도구와 같은 이름으로 덮어쓰면 그 이름도 쓰기 계열이 된다.

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
    # 3) 본문을 "## 제목" 기준으로 잘라 sections를 만든다. "### "는 절을 나누지 않는다
    #    정해진 절은 REQUIRED, OPTIONAL 순서로, 알 수 없는 절은 버리지 않고 그 뒤에 둔다
    #    첫 "##" 앞의 글은 버린다. 같은 제목이 두 번 나오면 PlanFormatError


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
        #    noul이 bool이나 문자열이면 invalid. 본문이 JSON이 아니거나 answers가 사전이 아니면
        #    그 묶음 전체가 transport_error. 실패는 그 묶음의 질문에만 번진다
        # 7) 질문마다 tracing.record_judgment로 기록한다 (6장) [M6]

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> JevDecider:
        """환경에서 키와 임계값을 읽어 만든다.

        TYPESAFE_API_KEY가 있으면 URL, MODEL을 쓴다. 없고 OPENROUTER_API_KEY가 있으면
        OPENROUTER_URL ("https://openrouter.ai/api/alpha/decisions"),
        OPENROUTER_MODEL ("typesafe/jev-1.13")을 쓴다. 본문과 응답 형식은 같다.
        2026-11-11 사용자 결정: Jev 키는 OPENROUTER_API_KEY로 넣는다.

        Raises: DeciderError: 키가 없거나, PLAN_GATE_JEV_THRESHOLD가 (0, 1] 밖이거나 수가 아닐 때.
                메시지는 변수 이름만 말한다. 임계값 변수가 없으면 0.5.
        """


class FakeDecider:
    """대본으로 답하는 판정기. 테스트와 가짜 모델 실행에 쓴다."""

    def __init__(self, script: Mapping[str, float | None] | None = None, *, default: float = 1.0,
                 threshold: float = JEV_THRESHOLD_DEFAULT) -> None:
        """script는 질문 이름 접두사 -> 확률. "J6"는 "J6:..." 전부에 맞는다.
        값이 None이면 그 질문은 transport_error다 (G16)."""

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
def questions_j6(request: str, records: Sequence[MemoryRecord]) -> tuple[str, list[Noul]]: ...   # 기억마다 하나 (M5). state는 요청뿐이고 기록의 이름과 설명은 질문마다 넣는다
```

각 함수는 `(state 문자열, 질문)`을 돌려준다. `state`는 판정에 필요한 본문만 담고 4,000자에서 자른다. 넘치면 각 부분(호출 요약, 요청, 절)을 같은 몫으로 잘라 긴 절 하나가 나머지를 밀어내지 않게 한다. 판정 대상(J4의 호출 요약, J5의 요청)을 앞에 둔다. J4의 `summary`는 도구 이름과 인자 요약이고 경로와 명령만 담는다. 파일 내용은 넣지 않는다.

검사: `httpx.MockTransport`로 본문 형태와 인증 헤더 확인, 확률 0.49와 0.5의 경계, `noul`이 문자열인 응답, 500 응답, 시간 초과, 질문 40개의 두 묶음 분할, 오류 메시지에 키가 없는지.

### 3.4 `policy.py`

순수 함수만 둔다. 그래프와 Jev에 의존하지 않는다.

```python
def tool_name_of(tool: BaseTool | Mapping[str, Any]) -> str | None:
    """도구 객체나 사전에서 이름을 꺼낸다. 공급자 내장 도구는 사전으로 온다."""


def normalize_tool_path(raw: object) -> Path | None:
    """도구 인자의 경로를 실제로 쓰일 절대 경로로 바꾼다. 바꿀 수 없으면 None."""
    # 프로젝트 루트는 쓰지 않는다. 백엔드가 virtual_mode=False라 결과는 루트와 무관하다
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
    # 1) str이 아니거나 비면 False. [F1 리뷰] `\(\s*\)`(함수 정의 `cat () ( touch x ) && cat`)가 있어도 False
    # 2) deepagents_code.config.is_shell_command_allowed(
    #        command, list(RECOMMENDED_SAFE_SHELL_COMMANDS))가 True면 True
    # 3) deepagents_code.auto_mode._fixed_repo_command_allowed(command, project_root)가 True면 True
    #    [F1 리뷰] 단 glob 문자(`*?[`)가 없을 때만. `git diff *`는 `--output=x`라는 파일 이름을 옵션으로 펼친다
    #    [F5] `{`, `$`도 없을 때만(`git log {--output=f,HEAD}`, `git log $@--output=f`가 옵션을 만든다).
    #    맨 앞이 `git -C <경로>`이고 경로가 절대 경로이며 glob 문자 없이 프로젝트 루트 자체로
    #    풀리면 `-C <경로>`를 떼고 본다. `-C`가 둘이면 두 번째에서 거부된다
    #    [F5 리뷰] 떼기 전 원문에 줄바꿈·`;`·`|`·`&`·`<>`·백틱이 있으면 거부한다. shlex로 다시 짜면
    #    줄바꿈이 공백이 되어 `git -C <루트> status\ntouch x`가 지나갔다
    # 4) [F1] 조합 명령을 조각마다 본다 (_read_only_chain). 모두 맞으면 True
    #    a) 스페이스나 문자열 끝으로 떨어진 `2>&1`, `2>/dev/null` 토큰만 지운다
    #       (유니코드 공백은 bash가 나누지 않으므로 경계로 보지 않는다)
    #       [F5] `>/dev/null`, `1>/dev/null`도 지운다. 토큰 뒤는 스페이스, 끝,
    #       `;`, `|`, `&&`이어야 한다(단독 `&`가 붙으면 지우지 않아 b에서 거부).
    #       `&>/dev/null`은 지우지 않는다. 실행 셸 sh(dash)에서는 `cmd &` + `>/dev/null 다음명령`이다
    #    b) 남은 문자열이 config.contains_dangerous_patterns면 False (다른 리다이렉트, &, $, 치환)
    #    c) 업스트림과 같은 &&, ||, |, ; 로 나눈다. 빈 조각이 있으면 False
    #    d) 첫 조각이 `cd <절대 경로>`이면 그 조각은 건너뛴다
    #       (상대 경로, `~`, `-`, glob 문자는 받지 않는다. 맨 앞이 아닌 cd는 받지 않는다)
    #    e) 남은 조각마다 is_shell_command_allowed(조각, RECOMMENDED_SAFE_SHELL_COMMANDS + ["echo"])
    #       또는 [F5] find 검사(_find_read_only)
    #       또는 3)의 git 검사(glob 문자 없음 + _fixed_repo_command_allowed).
    #       뒤의 것(git)은 cd가 없거나 cd 대상이 프로젝트 루트 자체일 때만 쓴다
    #    f) [F5] find 검사: 첫 토큰이 `find`이고, 역슬래시, `$`, `{`가 없고, 따옴표 구간을 뺀
    #       나머지에 `*?[`와 짝 없는 따옴표가 없고, shlex로 따옴표를 푼 어떤 토큰도
    #       `-exec`, `-ok`, `-delete`, `-fprint`, `-fls`, `-rm`으로 시작하지 않는다
    #       (앞부분 일치라 -execdir, -okdir, -fprint0, -fprintf도 잡는다. -rm은 bfs의 별칭)
    # 5) 그 밖은 False


def mentions_protected(command: str) -> bool:
    """명령 문자열에 보호 폴더 경로가 있는가. 문자열 대조다."""
    # is_protected처럼 상위도 잡는다. ".deepagents" 자체(뒤에 끝, 공백, 따옴표,
    # 셸 구분자, glob 문자)와 ".deepagents/plans" 같은 보호 폴더 셋이 대상이다.
    # ".deepagents/skills/x", ".deepagents/plans-old"는 걸리지 않는다


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
| 1a | 도구가 `ASYNC_SUBAGENT_TOOLS`에 있다 [M4] | deny | `async_subagent` |
| 2 | `WRITE_PATH_TOOLS`이고 경로를 정규화할 수 없다 | deny | `bad_path` |
| 3 | `WRITE_PATH_TOOLS`이고 `is_protected`다 | deny | `protected_path` |
| 4 | `execute`이고 `is_read_only_shell`이다 | allow | `read_only_shell` |
| 5 | `execute`이고 `mentions_protected`다 | deny | `protected_path` |
| 6 | 도구가 쓰기 계열이 아니다 (아래 정의) | allow | `not_mutating` |
| 7 | `phase`가 `executing`이 아니다 | deny | `no_approved_plan` |
| 8 | `WRITE_PATH_TOOLS`이고 상대 경로가 `targets`에 있고 `fresh_approval`이다 | allow | `in_targets` |
| 9 | 그 밖 | needs_scope_check | `scope_check` |

쓰기 계열은 `WRITE_PATH_TOOLS | SHELL_TOOLS | OTHER_MUTATING_TOOLS | mcp_mutating`이다. `mcp_mutating`에는 확장 도구 이름도 들어 있다 [M4].

[M4] 1a의 이유. 원격 비동기 서브에이전트(`start_async_task`, `update_async_task`)는 다른 서버에서 돌아 쓰기 차단이 없고, J4는 `summarize_call`로 도구 이름만 받아 범위를 판단할 수 없다. P3에 맞춰 승인 뒤에도 거부한다. `cancel_async_task`는 쓰기를 늘리지 않으므로 9번(J4)에 남는다.

[확인] `is_shell_command_allowed` (`DC/config.py:4537`)와 `_fixed_repo_command_allowed` (`DC/auto_mode.py:2480`)는 인자만 쓰는 순수 함수다. 앞의 것은 첫 토큰 이름만 보고 리다이렉션과 명령 치환을 거부한다. 뒤의 것은 읽기 전용 git 하위 명령만 통과시킨다. 뒤의 것은 이름이 `_`로 시작하는 비공개 함수다. 같은 패키지 안에서 import하고, 그 줄에 이유를 주석으로 적는다.

[F1] 4)를 더한 이유. dcode-a 실사용에서 `echo probe`, `ls <경로> && echo "---" && head -60 <파일>`, `cd <루트> && git log --oneline -3 2>&1 | head -5`가 `no_approved_plan`으로 거부됐고 모델이 셸 명령만 바꿔 가며 다시 시도했다. 판정은 업스트림 두 검사를 조각마다 다시 쓴 것이고 새로 허용한 것은 `echo`, 두 리다이렉트, 맨 앞의 `cd <절대 경로>`뿐이다. `cd` 뒤의 git을 루트로 갈 때만 받는 이유는 업스트림이 git을 신뢰한 저장소 밖에서 돌리지 않기 때문이다(`-C`가 허용 옵션에 없다). 다른 저장소(하위 폴더의 중첩 저장소 포함)의 설정은 `git status`, `git diff`에서 프로그램을 돌릴 수 있다. `cd` 뒤의 `ls`, `cat` 같은 명령은 어디서든 절대 경로로도 읽을 수 있어 막지 않는다. 같은 함수를 `SubagentWriteBlockMiddleware`도 쓰므로 서브에이전트의 `execute`도 같이 넓어진다. 판단 기록 O17.

[F5] 3), 4a), 4f)를 더한 이유. 릴리스본 dcode-a(glm-5.3-flash)가 `ls /root/a.py 2>/dev/null; ls /root/b.py`(`;` 앞 토큰을 못 지움, 버그), `ls /root/README.md >/dev/null && echo ok`, `git -C <루트> status --short --branch && git -C <루트> log --oneline -3`, `find /root -maxdepth 3 -name "pyvenv.cfg"`를 `no_approved_plan`으로 거부당했다. 안전 근거: /dev/null로 가는 출력은 버려지고, 단독 `&`와 다른 리다이렉트는 업스트림 검사에 남는다. `execute`는 `subprocess.run(shell=True)`, 즉 `/bin/sh`(여기서는 dash)로 돈다. dash에서 `&>`는 `&`(백그라운드)와 `>`로 나뉘어 `echo a &>/dev/null touch pw`가 `touch`를 실행하므로 `&>/dev/null`은 받지 않는다. `git -C <루트>`는 루트로 간 `cd` 뒤의 git과 같은 저장소 설정을 읽는다. find는 실행하거나 쓰는 식만 위험하고, 셸 펼침(glob, 중괄호, `$@`)이 식을 만들 수 있어 그 문자를 막는다. 같은 펼침이 git 허용 옵션 검사도 우회해서(`git log {--output=f,HEAD}`, 전부터 있던 우회) `{`, `$`를 git에도 막았다. 따옴표 안의 glob(`-name "*.py"`)은 펼쳐지지 않아 받는다. 판단 기록 O19, O20, O21.

검사: 규칙표 아홉 줄 각각에 사례 하나 이상. `cat a > b`는 4번에 걸리지 않아야 한다. [F1] 위 세 명령은 4번에 걸리고, 쓰기가 가능한 닮은꼴(`2>&1>out`, `2>/dev/nullx`, `2> out`, `>&2`, `| tee`, `| xargs rm`, `sed -i`, `cd /tmp && git status`, `cd <루트>/src && git status`, 상대 경로 `cd`, 유니코드 공백이 붙은 `2>/dev/null`, 맨 앞이 아닌 `cd`, 쓰는 git 하위 명령, `python3`, 허용 이름의 함수 정의 `cat () ( touch x ) && cat`, glob이 붙은 git `git diff *`)은 걸리지 않는다 (`test_policy.py` `test_f1_*`). [F5] 위 네 명령은 4번에 걸리고, 닮은꼴(구분자 앞 `2>/dev/null&`, `>/dev/nullx`, `>/dev/null/x`, `>|`, `>>`, `3>/dev/null`, `1>&2`, 루트가 아닌·상대·하위 경로나 두 번 쓴 `git -C`, `-C` 뒤의 `-c`·`--git-dir`·`--output`, 중괄호와 `$@`로 만든 git 옵션, find의 위험한 식 전부와 따옴표·역슬래시로 숨긴 형태, 따옴표 밖 glob, `find … | xargs rm`)은 걸리지 않는다 (`test_policy.py` `test_f5_*`, 실제 셸 `test_gate.py` `test_f5_*`). 상대 경로 `docs/x.md`가 `/docs/x.md`로 정규화되어 루트 밖으로 판정되는지. 심볼릭 링크로 보호 폴더를 가리키는 경로.

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
        # 4) tracing.span("cg.plan.review", ...)로 기록한다 [M6]. output: 의견 수, 질문 수, error. error면 level=ERROR
        # 구조화 출력이 None이거나 스키마에 맞지 않으면 error로 돌려준다. 빈 의견으로 세지 않는다
```

리뷰 호출이 실패하면 계획은 "리뷰 못 함" 상태로 사람에게 넘어간다. 승인 화면에 그 사실을 보여준다. 리뷰 실패를 리뷰 통과로 세지 않는다.

`FakeReviewer`를 `tests/unit_tests/assistant/fakes.py`에 둔다. 회차별 `ReviewResult` 목록을 대본으로 받는다.

### 3.6 `tools.py`

도구 다섯 개를 만든다. 대화형과 비대화형에서 등록되는 도구 집합은 같고, `request_plan_approval`과 `propose_rule`의 동작만 다르다.

```python
def build_plan_tools(options: PlanGateOptions, backend: BackendProtocol) -> list[BaseTool]:
    """계획 도구를 만든다. PlanGateMiddleware.tools가 이 목록을 쓴다."""
```

[M3] `backend`는 `complete_plan`이 `test_command`를 돌리는 데 쓴다. `submit_plan`과 `complete_plan`은 비동기 구현만 있다 (`PlanReviewer`가 `areview`만 있다). `request_plan_approval`은 둘 다 있다. 비동기 판은 파일 읽기와 쓰기를 `asyncio.to_thread`로 돌리고 `interrupt()`는 이벤트 루프에서 부른다.

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
    # 4) phase가 idle이면(끝났거나 거부된 뒤) new_plan_id로 새 계획을 만든다. 아니면 상태의 plan_id
    #    phase가 idle(새 계획)이나 executing(승인 뒤 재검토)이면 review_round를 0에서 센다 [M3]
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
| 형식 문제가 있다 | draft | planning | 문제 목록. 고쳐서 다시 제출하라. 도구 결과 status는 `error` |
| 의견이 있고 회차가 `MAX_REVIEW_ROUNDS` 미만이다 | draft | planning | 의견 목록. 반영해서 다시 제출하라. 정상 흐름이라 status는 `success` [M3] |
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

**멈춤 신호의 모양.** [실행 확인, M3: `test_textual_adapter`의 가짜 스트림과 실제 TUI]  TUI는 신호의 `type`이 `"ask_user"`인지와 `AskUserRequest` 모양만 본다 (`DC/tui/textual_adapter.py:2701`). 어느 도구가 냈는지는 보지 않는다. 질문 본문은 마크다운으로 그려진다 (`DC/tui/widgets/ask_user.py:786`). 그래서 TUI를 고치지 않고 계획 승인 화면을 띄운다.

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

[실행 확인, M3] `await backend.aexecute(test_command, timeout=600)`. 반환은 `ExecuteResponse(output, exit_code, truncated)`. 셸이 없는 백엔드는 `NotImplementedError`를 내고, 이것과 `exit_code`가 0이 아닌 경우(None 포함)를 실패로 본다.

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

[M3] `_cg_counters`와 카운터 갱신, `aafter_agent`는 M6에서 `tracing.py`와 함께 넣었다. [M6] 연속 실패를 세려고 비공개 키 `_cg_last_error`(직전 실패 호출의 `summarize_call` 요약, 성공하면 None)를 더했다. 요청 시작 때 `_cg_counters`는 `{"__reset__": 1, "llm_base": <request_count>}`로 되돌린다. `complete_plan`의 테스트 실패는 도구가 `_cg_counters: {"test_failures": 1}`를 직접 싣고, 게이트가 자기 증가분과 더한다. [M6 리뷰] `_cg_last_error`에도 리듀서(나중 값이 이김)를 달았다. 없으면 한 AI 메시지의 도구 호출이 둘 이상일 때 `InvalidUpdateError`("Can receive only one value per step")가 났다. 병렬 호출 안에서 어느 값이 남는지는 순서에 달렸다. 테스트 `test_parallel_tool_calls_in_one_step`(병렬 거부 둘, 병렬 허용 둘). `ask_user`의 결과는 감싸지 않고 세지 않는다 (14장).

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
7) [M6] begin_request는 두지 않았다. trace id는 make_graph가 정한다 (6.2). 할 일이 없다
8) 모은 값을 dict로 반환
```

5단계의 해석. 메시지 본문을 앞뒤 공백 제거와 소문자 변환 뒤에 본다.

| 본문 | 처리 |
|---|---|
| `APPROVE_WORDS`에 있고 계획에 미결 질문이 없다 | 계획 status=approved, phase=executing |
| `REJECT_WORDS`에 있다 | 계획 status=rejected, phase=idle |
| 그 밖 | 미결 질문이 있으면 답으로 보고 "결정 사항"에 적는다 (메시지 하나를 질문 전부의 답으로 한 줄에 적는다 [M3]). phase=planning, review_round=0 |

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
     b) 통과면 handler를 부른다. WRITE_PATH_TOOLS였고 결과가 오류가 아니면 targets에 경로를 추가하고
        PlanStore.save, tracing.span("cg.scope.extend")
        [M3] 추가는 handler 뒤에 한다. 계획을 다시 읽고 미들웨어의 잠금 안에서 저장해 병렬 쓰기가 서로의 대상을 덮지 않는다
     c) 통과 못 하면 거부한다. 사유 out_of_scope. counters.jev_denies를 1 올린다
        메시지: "승인된 계획의 범위 밖이다. 필요하면 submit_plan으로 계획을 고쳐 재검토를 받아라"
6) 결과가 오류 상태이면 counters.tool_errors를 1 올린다
   같은 (name, args 요약)이 직전에도 오류였으면 counters.repeat_failures를 1 올린다
7) 거부했으면 counters.gate_denies를 1 올리고 tracing.span("cg.gate.deny")
8) 카운터 갱신을 결과에 싣는다 (아래)
```

[F1] `no_approved_plan` 문장은 다음 행동을 알려 준다. 승인 전 `execute`는 읽기 전용 명령과 그 조합만 통과하니 셸 명령을 바꿔 다시 시도하지 말고, 읽기는 `read_file`, `glob`, `grep`이나 `task(subagent_type="explorer")`로 하라는 것이다. 사유 코드는 그대로다(추적, 카운터, 규칙표가 쓴다). 셸 명령만 바꿔 가며 거부되는 반복은 `repeat_failures`에 잡히지 않는다(요약에 명령이 들어가 서명이 다르다). `gate_denies`가 세고 7.2 임계값(작업당 3)이 자기 개선에서 잡는다. 실행 중에 단계를 올리는 장치는 두지 않았다.

거부 메시지의 형태. [확인] 본보기는 `DC/auto_mode.py:4711` `HeadlessMCPGuardMiddleware._rejection`이다.

```python
ToolMessage(content=<사유 문장>, name=request.tool_call["name"],
            tool_call_id=request.tool_call["id"], status="error")
```

카운터를 상태에 싣는 방법. `handler`의 결과는 `ToolMessage`이거나 `Command`다. `ToolMessage`이면 `Command(update={"messages": [msg], "_cg_counters": 새 값})`로 감싼다. `Command`이면 `update`에 `_cg_counters`를 더한 새 `Command`를 만든다.

[실행 확인] `awrap_tool_call`이 `Command(update=...)`를 돌려주면 상태가 갱신된다. 한 단계에서 도구 둘이 병렬로 거부됐을 때 덧셈 리듀서가 붙은 값이 2가 됐다. 거부된 도구의 본문은 실행되지 않았다. 도구 안의 `interrupt`와 재개도 이 훅을 거쳐 동작했다. `PrivateStateAttr` 값은 실행 결과에 나오지 않았다. 실험은 `Day09/.venv`에서 `create_agent`, `_ToolBindingFakeModel`, `InMemorySaver`로 했다. 리듀서 본보기는 `DC/auto_mode.py:674` `_merge_temp_artifacts`다.

[M3] J4의 새 요청문은 `question_j4(plan, tool_name, summary, request="")`의 선택 인자로 넘긴다.

**승인의 유효 범위.** [제안] 승인은 승인받은 요청 안에서만 `targets` 지름길을 연다. `_cg_last_human_id`가 `_cg_approved_human_id`와 다르면(승인 뒤에 사용자가 새 메시지를 보냈으면) `classify_call`에 `fresh_approval=False`를 넘긴다. 그러면 `targets` 안의 쓰기도 J4를 거친다. J4의 state에는 계획과 새 요청문을 함께 넣는다. 이유는 이렇다. 작업이 `complete_plan` 없이 끝나면 phase가 `executing`으로 남는다. 다음에 온 무관한 요청이 옛 `targets`를 계획도 판정도 없이 고칠 수 있으면 안 된다.

**`aafter_agent` (요청의 끝을 기록한다).**

```
1) counters와 LLM 호출 수를 모은다
   LLM 호출 수는 상태의 _session_cost_breakdown["request_count"]에서 읽는다
   이 값은 대화 전체 누적이다. 요청 시작 때 값을 _cg_counters["llm_base"]에 적어 두고 차이를 쓴다
2) tracing.end_request(counters=, llm_calls=, review_rounds=, phase=, plan_id=)로 지표를 trace에 점수로 붙인다
   [M6] 승인 화면에서 멈춘 실행에는 after_agent가 돌지 않는다. 요청이 끝나는 실행에서 요청 전체의 값으로 붙는다
3) None 반환
```

[확인] LLM 호출 수는 기존 비용 집계가 센다 (`DC/cost_tracking.py:128` `CostBreakdown.request_count`). 도구 호출 수는 dcode가 세지 않아 게이트가 센다.

#### `SubagentWriteBlockMiddleware`

[제안] 서브에이전트는 항상 읽기 전용이다. 승인 뒤에도 쓰기는 주 에이전트만 한다.

이유. [확인] 서브에이전트는 따로 조립된 그래프라서 주 에이전트의 `wrap_tool_call`이 닿지 않는다 (`DC/agent.py:2989` `_subagent_cli_middleware`). 서브에이전트는 비공개 상태를 받지 못해 단계와 `targets`를 알 수 없다. 범위 검사를 서브에이전트 안에서 할 방법이 없으므로 쓰기를 통째로 막는다.

```python
class SubagentWriteBlockMiddleware(AgentMiddleware):
    """서브에이전트에 허용 목록의 도구만 열어 둔다."""

    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(self, project_root: Path, read_only_tool_names: frozenset[str] = frozenset()) -> None: ...
    # [M4] 허용 목록 = SUBAGENT_ALLOWED_TOOLS | read_only_tool_names(읽기 전용 주석이 맞는 MCP 이름).
    # 처음 설계는 거부 목록이었다. 목록에 없는 도구(확장 도구, update_goal 등)가 통과해 허용 목록으로 바꿨다

    @property
    def name(self) -> str:
        """PLAN_GATE_MIDDLEWARE_NAME을 돌려준다. PlanGateMiddleware와 같은 이름이다."""

    # wrap_model_call / awrap_model_call: 허용 목록 밖의 도구를 목록에서 뺀다 (execute는 남는다)
    # wrap_tool_call / awrap_tool_call:
    #   허용 목록 밖이면 거부 (쓰기, PLAN_TOOLS, task, 확장 도구 포함)
    #   execute는 policy.is_read_only_shell일 때만 통과
```

이름을 주 게이트와 같게 두는 이유. [확인] 기본 `general-purpose` 서브에이전트는 fork 모드라서 부모의 미들웨어를 물려받는다. 사양에 같은 이름의 미들웨어가 있으면 사양 쪽이 부모 것을 대신한다 (`SDK/graph.py:774`). 같은 이름으로 두면 물려받은 `PlanGateMiddleware`가 `SubagentWriteBlockMiddleware`로 바뀐다. 계획 도구가 서브에이전트에 노출되지 않는다.

[실행 확인, M4] fork 서브에이전트의 최종 미들웨어와 도구 목록. `create_cli_agent(plan_gate=...)`로 그래프를 만들고 SDK의 `create_agent`를 감싸 서브에이전트별 미들웨어와 도구 노드를 열거했다.
- 고치기 전: fork `general-purpose`가 `PlanGateMiddleware`를 이름 그대로 물려받아 `submit_plan`, `request_plan_approval`, `complete_plan`이 도구 노드에 있었다. 도구는 `ask_user, compact_conversation, delete, edit_file, execute, glob, grep, ls, read_file, task, update_goal, write_file`과 계획 도구 셋.
- 고친 뒤: 그 자리가 `SubagentWriteBlockMiddleware`로 바뀌고 계획 도구가 빠졌다. `write_file`, `edit_file`, `delete`, `execute`, `task`는 `FilesystemMiddleware`와 `_ForkTaskToolMiddleware`가 붙여 도구 노드에 남는다. 모델 목록에서 빠지고 호출은 거부된다.
- fork가 아닌 `general-purpose`와 사용자 선언형 서브에이전트에도 `SubagentWriteBlockMiddleware`가 들어간다. 탐색 서브에이전트의 도구는 `glob, grep, ls, read_file`뿐이다.

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
    read_only_mcp = {t.name for t in mcp_tools} - plan_gate.mcp_mutating_tool_names
    middleware.append(SubagentWriteBlockMiddleware(plan_gate.project_root, frozenset(read_only_mcp)))
```

이 함수는 사용자 정의 서브에이전트와 `general-purpose` 양쪽에 쓰이므로 한 곳에서 모두 덮인다.

탐색 서브에이전트는 `composite_backend`가 만들어진 뒤에 `custom_subagents`에 더한다. [M3] 게이트가 켜져 있는데 사용자 서브에이전트 이름이 `explorer`이면 `ValueError`로 서버 기동을 멈춘다. 메시지는 이름을 바꾸거나 `DEEPAGENTS_CODE_PLAN_GATE=0`을 쓰라고 말한다. SDK의 "Duplicate subagent name"보다 원인이 분명하다. `_inject_fs_tools_into_subagents` 호출 (`:3619`) 앞이다.

**`--allow-fs-tools` 충돌.** [확인] 이 옵션이 켜지면 `_inject_fs_tools_into_subagents` (`DC/agent.py:288`)가 모든 서브에이전트의 미들웨어 끝에 `FilesystemMiddleware`를 덧붙여 탐색 서브에이전트의 읽기 전용 구성을 덮는다. 이 함수에서 이름이 `EXPLORER_SUBAGENT_NAME`인 사양은 건너뛰게 고친다.

**기존 승인 화면과의 순서.** [확인] dcode의 승인은 모델 응답 직후(`after_model`)에 멈춘다. 게이트가 거부할 호출에 대해 사용자가 먼저 승인 화면을 보게 된다. 승인 술어 `_should_interrupt_tool_call` (`DC/agent.py:2223`)의 첫머리에 한 줄을 넣는다.

```python
if precheck_denies(request.state, request.tool_call):
    return False
```

`precheck_denies`는 `gate.py`의 모듈 함수다. 상태에 `_cg_phase`가 없으면(게이트가 꺼져 있으면) False다. [M3] 승인 술어에서는 프로젝트 루트를 알 수 없어서 `classify_call`을 부르지 않고, 루트 없이 확정되는 거부만 True로 한다. phase가 executing이 아니고 도구가 `WRITE_PATH_TOOLS | OTHER_MUTATING_TOOLS`인 경우, 그리고 [M4] phase와 관계없이 `ASYNC_SUBAGENT_TOOLS`인 경우다. `execute`, MCP, 승인 뒤의 보호 경로는 승인 화면을 거친 뒤 게이트가 거부한다. Jev가 필요한 경우는 False로 둔다. 그 경우 사용자가 승인한 뒤 J4가 거부할 수 있고, 그것은 받아들인다.

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

[실행 확인, M3] 모델 객체는 `server_graph`의 `result.model`(`create_model`의 결과)로 `create_cli_agent` 밖에서 얻는다. 환경은 `workspace_env`를 쓴다. 프로젝트 루트는 `project_context.project_root or project_context.user_cwd`이고, `project_context`가 None이면 `config.cwd`로 물러선다. 셋 다 없으면 `RuntimeError`.

**키 검사.** [M5, O5 개정] 서버 기동 경로 한 곳에서 한다. `DC/client/launch/server_manager.py`의 `start_server_and_get_agent` 첫머리, `plan_gate`가 True일 때 `_preflight_validate_mcp_config` 앞이다. TUI(`PrespawnedServer`, 앱의 서버 시작)와 `-n`(`server_session`)이 모두 이 함수를 지나고, 서버 프로세스와 그래프를 만들기 전이다.

```python
class MissingJevKeyError(ValueError): ...   # decider.py. 메시지는 변수 이름만

def require_jev_key(environ: Mapping[str, str]) -> None:
    """TYPESAFE_API_KEY와 OPENROUTER_API_KEY가 모두 비었으면 MissingJevKeyError."""
```

호출은 `require_jev_key(os.environ)`이다. 클라이언트가 `.env`를 읽은 뒤다. 비대화형은 `run_non_interactive`의 `ValueError` 처리로 "Error: <안내>"를 출력하고 종료 코드 1이다(실행 확인). TUI는 기존 서버 시작 실패 처리(`ServerStartFailed`)로 대화 화면에 안내를 보인다. 하위 명령(threads, skills 등)은 서버를 띄우지 않으므로 검사하지 않는다.

[M5] 처음(M3)에는 `cli_main`의 하위 명령 분기 앞에서 `sys.exit(1)`했다. 그 자리는 `--yolo` 확인, MCP 서버 선택 같은 시작 프롬프트보다 앞이라, 그 프롬프트를 시험하는 `test_main.py::TestStartupAutoUpdate`가 키 없는 환경에서 1로 끝났다. 키가 있는지는 테스트 순서에 달렸다: `.env`는 프로세스당 한 번 부트스트랩이 `os.environ`에 넣는데 `tests/unit_tests/conftest.py`의 `_restore_os_environ`이 테스트마다 환경을 되돌린다. 그래서 자리를 옮겼다. 키가 없다는 안내는 이제 시작 프롬프트와 시작 업데이트 뒤에 나온다(받아들임).

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

1. 요청을 받으면 먼저 `task(subagent_type="explorer")`로 탐색한다. [F5] 승인 전에는 셸 명령 대신 `read_file`, `glob`, `grep`이나 탐색 서브에이전트로 읽는다.
2. 코드를 바꿔야 하면 `submit_plan`으로 계획을 낸다. 쓰기 도구는 승인 전까지 쓸 수 없다.
3. 리뷰 의견이 오면 반영해 다시 제출한다.
4. `request_plan_approval`로 사람의 승인을 받는다.
5. 승인되면 계획의 `targets` 안에서 작업하고, 끝나면 `complete_plan`을 부른다.
6. 계획에 없는 파일을 고쳐야 하면 `submit_plan`으로 계획을 고친다.
7. `.deepagents/plans`, `.deepagents/memory`는 직접 고치지 않는다.
8. [M5] 저장소에 계속 적용할 규칙을 알게 되면 `propose_rule`로 제안한다. 사람이 확인해야 저장된다.

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
        # 2) description 검증: 한 줄, 200자 이하. [M5 리뷰] `splitlines()`가 1줄이어야 한다("\r" 등도 막는다)
        # [M5 리뷰] 쓰기(save, delete, rebuild_index) 전에 기억 폴더가 resolve 뒤에도 프로젝트 루트 안인지 본다.
        #   밖이면(심볼릭 링크) PermissionError. 폴더 경로는 ProjectPaths.memory_dir
        # 3) 임시 파일에 쓰고 os.replace
        # 4) rebuild_index()

    def delete(self, name: str) -> None:
        """기억을 지우고 색인을 다시 만든다. 없으면 아무 일도 하지 않는다."""

    def rebuild_index(self) -> Path:
        """모든 기억의 frontmatter를 읽어 MEMORY.md를 다시 쓴다."""

    def read_index(self) -> str:
        """MEMORY.md 내용에서 첫 줄 주석을 뺀 문자열. 파일이 없으면 빈 문자열."""

    def save_rule(self, description: str, body: str, *, source: str, now: datetime) -> MemoryRecord:
        """프로젝트 규칙을 저장한다. 이름은 "rule-" + description의 영숫자 슬러그 + "-" + description 해시 6자리.
        [M5] 한글만 있는 설명은 슬러그가 비어 서로 덮어쓰므로 해시를 붙인다. 슬러그가 비면 "rule-<해시>".
        같은 설명은 같은 이름이라 다시 저장하면 덮어쓴다."""

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
        #    [M5 리뷰] phase가 idle이 아니고 계획이 있으면 요청 본문은 "계획의 요구사항 + 빈 줄 + 새 메시지"다.
        #    "승인", "계속해" 같은 짧은 메시지만으로 고르면 관련 기록이 빠진다
        #    질문 이름은 "J6:<기억 이름>". 통과한 것의 이름만 모은다
        # 5) tracing.record("cg.memory.inject", output={"candidates": n, "selected": [...], "body_dropped": [...], "truncated": bool})  [M6]
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

주입 크기 상한을 둔다. 규칙과 선택된 기록의 본문 합이 20,000자를 넘으면 뒤의 것부터 본문을 빼고 이름과 설명만 남긴다. 뺀 사실을 구간에 기록한다 [M6: `cg.memory.inject`의 `body_dropped`(본문을 뺀 기억 이름), 최종 자르기면 `truncated`. 요청 시작 때 한 번 계산한다]. [M5 리뷰] 상한은 틀 안 전체(색인, 생략 줄 포함)에 건다. 색인은 5,000자를 넘으면 앞(오래된) 줄을 빼고 최근 줄을 남긴다. 본문을 뺀 뒤에도 넘으면 20,000자에서 자르고 잘렸다고 적는다. 주입하는 글의 `<project_memory`, `</project_memory`는 `&lt;`로 바꿔 틀을 닫거나 새로 열지 못하게 한다. [M5] 규칙도, 선택된 기록도, 색인 항목도 없으면 주입하지 않는다(MEMORY.md가 없어도 선택된 기록은 넣는다). 동기 `before_agent`, `wrap_model_call`도 같은 동작으로 둔다.

**등록.** `DC/agent.py`의 `if enable_memory:` 블록 (`:3254` ~ `:3283`) 끝에 넣는다. `plan_gate`가 있을 때만이다.

```python
if plan_gate is not None:
    memory_injection = MemoryInjectionMiddleware(MemoryStore(plan_gate.project_root), plan_gate.decider)
    agent_middleware.append(memory_injection)
```

서브에이전트 스택에는 넣지 않는다. 탐색 서브에이전트는 기억 파일을 직접 읽는다. [M5 확인] 다만 fork `general-purpose`는 SDK가 부모 미들웨어를 이름 그대로 물려받게 해서(`SDK/graph.py` fork 분기, 부모 프롬프트를 다시 만들려는 설계) `MemoryInjectionMiddleware`가 들어간다. 비공개 상태가 넘어가지 않아 fork 작업마다 J6가 한 번 더 돈다(작업 기록이 있을 때). 쓰기는 막혀 있다. **예외로 둔다** (DECISIONS O3): fork는 부모 프롬프트를 그대로 재구성하는 설계라 빼지 않는다. 비용은 fork 호출마다 J6 한 번이다.

### 5.4 기존 Memory 기능과의 정리

[확인] 기존 기능 둘이 에이전트에게 `AGENTS.md`를 직접 고쳐 기억을 저장하라고 시킨다. 우리 설계와 충돌한다.

| 기존 | 처리 |
|---|---|
| SDK 기본 메모리 지침 (`SDK/middleware/memory.py:104`) | `plan_gate`가 있으면 `MemoryMiddleware`를 `system_prompt=_MEMORY_READONLY_SYSTEM_PROMPT`로 만든다 (`DC/agent.py:183`의 기존 상수). `AGENTS.md` 읽기는 유지된다 |
| `/remember` 명령 (`DC/app.py:18291`) | 스킬 호출 대신 `MemoryStore.save_rule`을 클라이언트에서 직접 부른다 |
| remember 스킬 (`DC/built_in_skills/remember/`) | 삭제한다. `_STATIC_SKILL_ALIASES` (`DC/command_registry.py:536`)에서도 뺀다 |

`/remember <글>`의 새 동작. 사용자가 직접 말한 규칙이므로 확인 없이 저장한다. 같은 설명의 규칙이 있으면 "덮어썼다"로 알린다. 설명은 글의 첫 줄(200자에서 자른다), 본문은 전체다. [M5] 프로젝트 루트는 `hooks.trust.project_root_for(cwd)`(프로젝트 루트, 없으면 cwd)로 서버 게이트와 같게 얻는다. 게이트가 꺼진 세션에서도 저장하지만 그때는 주입되지 않는다. 명령 설명은 "Save a project rule to .deepagents/memory", 인자 표시는 `<rule>`이다. 인자가 없으면 "저장할 규칙을 함께 적어 주세요"를 출력한다. 프로젝트 루트는 클라이언트의 프로젝트 컨텍스트에서 얻는다.

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
    #    [M5 리뷰] 같은 설명의 규칙이 이미 있으면 질문이 "기존 규칙 <이름>을 바꿀까요?"다. 답은 strip해서 본다
    # 3) "저장"이면 store.save_rule(..., source="agent-approved")
    # 4) 결과를 ToolMessage로 돌려준다
    # [M5] 동기 함수와 비동기 함수를 모두 둔다(request_plan_approval과 같다). "저장" 밖의 답, 취소는 버림이다
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
    # LANGFUSE_TRACING = "DEEPAGENTS_CODE_LANGFUSE_TRACING" (_env_vars.py). 0/false/no/off면 끔


def init(environ: Mapping[str, str]) -> bool:
    """워크스페이스 환경을 받아, 그 워크스페이스의 실행을 내보내도 되는지 돌려준다."""
    # 1) is_enabled(environ)가 False면 False (워크스페이스마다 다르다)
    # 2) 처음이면 Langfuse(public_key=..., secret_key=..., base_url=LANGFUSE_BASE_URL 또는 LANGFUSE_HOST,
    #    mask_otel_spans=_mask_otel_spans)를 만들고 (public_key, base_url)을 기억한다. 클라이언트는 프로세스에 하나
    # 3) 이미 만들었으면 (public_key, base_url)이 같을 때만 True. 다르면 경고하고 False(내보내지 않음)
    # 4) 예외는 잡아서 경고를 남기고 False


def _mask_otel_spans(*, params) -> MaskOtelSpansResult:
    """내보내기 직전 span 속성(문자열, 문자열 열)마다 비밀값을 가린다."""
    # deepagents_code._trace_redaction.create_cached_secret_anonymizer()가 만든 함수를 속성 값에 적용한다
    # 바뀐 속성만 OtelSpanPatch(set_attributes=...)로 돌려준다
    # 예외가 나면 Langfuse가 그 내보내기 묶음을 통째로 버린다 (원본을 보내지 않는다)


def run_config(config: Mapping[str, Any] | None, environ: Mapping[str, str]) -> dict[str, Any] | None:
    """make_graph가 실행에 붙일 설정. init(environ)이 False면 None."""
    # environ은 그 워크스페이스 런타임의 model_environment
    # trace_id = Langfuse.create_trace_id(seed=f"{thread_id}:{turn_id 또는 run_id}")
    # {"callbacks": [CallbackHandler(trace_context={"trace_id": trace_id})],
    #  "metadata": {"cg_trace_id": trace_id}}
```

[M6 리뷰, DECISIONS O9] `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`, `LANGFUSE_HOST`는 `DC/config.py`의 `_PROJECT_DOTENV_DENIED_ENV_KEYS`에 있다. 클론한 저장소의 프로젝트 `.env`가 추적 전송을 다른 Langfuse로 돌리지 못한다. 키는 셸 환경과 사용자 `~/.deepagents/.env`에서만 온다 (테스트 `test_project_dotenv_cannot_set_langfuse_keys`, 실제 요청에서 프로젝트 `.env`의 `LANGFUSE_BASE_URL=https://evil.invalid`가 무시되고 원래 Langfuse로 간 것을 확인). 그래서 한 서버 프로세스의 워크스페이스들은 같은 키를 보고, 워크스페이스마다 다를 수 있는 것은 꺼짐 스위치뿐이다.

[확인] `create_cached_secret_anonymizer` (`DC/_trace_redaction.py:135`)는 문자열이나 중첩 구조를 받아 가린 값을 돌려주는 함수를 만든다.

[실행 확인, M6] `mask`는 `CallbackHandler`의 LLM 입출력을 다 덮지 못한다. 가짜 키 `AKIAIOSFODNN7EXAMPLE`을 사람 메시지에 넣은 실행에서 LangGraph `model` 노드(CHAIN)의 입출력에 원문이 올라갔다. 상태 안의 LangChain 메시지 객체를 가림 함수가 들여다보지 못한다. 그래서 `mask` 대신 `mask_otel_spans`를 쓴다. 직렬화된 속성 문자열에 걸리므로 모든 관측이 덮인다. 같은 가짜 키로 실제 서버 실행을 다시 돌려 trace 어디에도 원문이 없는 것을 확인했다.

### 6.2 핸들러를 붙이는 자리

[확인] 콜백은 서버에서만 붙일 수 있다. `make_graph` (`DC/server_graph.py`)는 실제 실행일 때만 `runtime.execution_runtime`이 채워진다.

```python
# make_graph의 실행 분기 끝, 그래프를 돌려주기 직전
runtime = await _workspace_runtime(binding)
run_config = tracing.run_config(config, runtime.model_environment or {})
return runtime.agent.with_config(run_config) if run_config else runtime.agent
```

[확인] `Pregel.with_config`는 `Pregel`을 돌려주므로 서버의 타입 검사를 통과한다 (`langgraph/pregel/main.py:991`). `recursion_limit`은 이 경로로 건드리지 않는다 (`DC/agent.py:3913`의 주석).

[실행 확인, M6] 서버는 한 요청 안에서 `make_graph`를 여러 번 부른다 (`-n` 한 번에 같은 `turn_id`, 다른 `run_id`로 두 번). 부를 때마다 새 trace id를 만들면 한 요청이 trace 19개로 쪼개졌다. 그래서 trace id는 실행 설정의 `metadata.thread_id`와 `metadata.turn_id`(없으면 `configurable.run_id`)를 seed로 `create_trace_id(seed=...)`에서 만든다. 같은 요청이면 몇 번 불러도 같은 trace다. 고친 뒤 실제 요청 하나가 trace 하나(관측 35개)로 모였다. [미확인] 승인 화면 뒤 재개한 실행이 같은 `turn_id`를 받아 같은 trace에 붙는지는 확인하지 않았다. [M6 리뷰] `turn_id`가 없는 실행(예: TUI의 `graph_input` 실행)은 `run_id`로 묶이므로 실행마다 trace가 갈린다. 그때 `after_agent`가 돈 실행의 trace에만 점수가 붙는다.

[M6 리뷰] `init`은 `_configure_server_tracing` 옆이 아니라 `run_config` 안에서 실행마다 그 워크스페이스의 환경으로 부른다. 처음 켜진 워크스페이스가 클라이언트를 만들고, 꺼짐 스위치를 켠 워크스페이스는 `run_config`가 None이라 콜백도 구간도 보내지 않는다 (구간은 trace id가 있는 실행 안에서만 보낸다, 6.3).

[실행 확인, M6] 서버는 워크스페이스 환경(`_preview_dotenv_environ`, 런타임의 `model_environment`)을 `init`에 넘기므로 서버 프로세스의 `os.environ`과 관계없이 키를 읽는다 (`active_environment()` 대안과 같은 효과). 처음 확인 때는 워크스페이스 `.env`의 키도 들어갔지만 O9로 막았다 (6.1). 실제 서버 서브프로세스의 `os.environ`은 확인하지 않았다.

**세션과 태그.** 클라이언트의 `build_stream_config` (`DC/config.py:2852`)가 만드는 metadata에 키를 더한다.

```python
metadata["langfuse_session_id"] = thread_id
metadata["langfuse_tags"] = ["dcode-assistant"]
```

[확인] metadata의 문자열과 리스트는 서버로 전달된다. 한 대화의 요청들이 같은 세션으로 묶인다.

### 6.3 구간과 점수

```python
def current_trace_id() -> str | None:
    """langgraph.config.get_config()의 metadata["cg_trace_id"]. 실행 밖이면 None."""


@contextmanager
def span(name: str, *, input: Any = None, metadata: Mapping[str, Any] | None = None,
         as_type: str = "span") -> Iterator[SpanHandle]:
    """구간 하나를 연다. Langfuse가 꺼져 있으면 아무것도 하지 않는 핸들을 준다."""
    # client.start_observation(..., trace_context={"trace_id": current_trace_id()})
    # 현재 문맥(current span)을 쓰지 않는다. 끝나면 end()


def record(name: str, *, input=None, output=None, level=None, status_message=None,
           as_type="span") -> None:
    """곧바로 닫히는 구간 하나 (사건 기록)."""


class SpanHandle:
    def update(self, *, output: Any = None, metadata: Mapping[str, Any] | None = None,
               level: Literal["DEFAULT", "WARNING", "ERROR"] | None = None,
               status_message: str | None = None) -> None: ...


def record_judgment(question: str, state_chars: int, verdict: Verdict) -> None:
    """Jev 판정 하나를 "cg.judge.<질문>" 구간으로 남긴다. as_type="guardrail"."""
    # J6:<기억 이름>은 구간 이름 cg.judge.J6, 전체 이름은 input에
    # input: 질문 이름과 state 길이만. state 원문은 넣지 않는다
    # output: probability, passed, reason


def end_request(*, counters: Mapping[str, int], llm_calls: int, review_rounds: int,
                phase: str, plan_id: str | None) -> None:
    """요청의 지표를 현재 trace에 점수로 붙인다."""
    # client.create_score(trace_id=current_trace_id(), name="cg.<키>", value=..., metadata={phase, plan_id})
    # 전송은 데몬 스레드의 client.flush()로 비우고 최대 2초(FLUSH_WAIT_S)만 기다린다 [M6 리뷰]
    # flush는 force_flush(30초)와 점수 큐 join이라 그대로 부르면 요청 끝이 수십 초 막힐 수 있다.
    # 아예 비우지 않으면 비대화 실행이 끝나 서버가 내려갈 때 점수가 사라졌다 (실제 요청으로 확인)

def is_active() -> bool:
    """클라이언트가 있고 run_config가 붙은 실행 안인가. 구간과 점수는 이때만 보낸다."""
```

모든 함수는 예외를 밖으로 던지지 않는다. 추적 실패가 작업을 막으면 안 된다.

[실행 확인, M6] 실행 문맥은 미들웨어 훅까지 이어지지 않는다. `abefore_agent`, `awrap_tool_call`, `aafter_agent`에서 `start_as_current_observation`으로 연 구간이 각각 새 trace가 됐고, `aafter_agent`의 `score_current_trace`는 "No active span"으로 점수를 남기지 못했다. 그래서 6.2의 trace id를 콜백의 `trace_context`와 모든 `cg.*` 구간의 `trace_context`에 같이 넘기고, 점수는 `create_score(trace_id=...)`로 붙인다. 훅과 `asyncio.to_thread` 안에서 `get_config()`의 metadata로 id를 읽는다 (`test_tracing.py`). `cg.*` 구간은 trace 안의 별도 최상위 관측으로 보인다.

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

[M6] 표와 다르게 한 것. `cg.human.question`은 대화형에서 답을 받았을 때만 남긴다(`interrupt` 재개 때 도구 본문이 처음부터 다시 돌아 "냈을 때"가 두 번 찍힌다). 비대화는 질문을 낼 때(`asked`)와 다음 메시지로 답할 때(`answered`) 남긴다. `cg.judge.mismatch`는 J5가 "변경 불필요"인데 `submit_plan`이 불린 쪽만 잡는다. 반대쪽(J5가 "변경 필요"인데 계획 없이 끝남)은 아직 없다. `cg.result`는 `complete_plan`의 성공(`done`)과 포기(`failed`)에 남긴다. 테스트 실패는 `cg.test.run`의 ERROR다.

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

### 6.4 `runs.py`

Langfuse API를 읽는 코드를 여기에 모은다. 클라이언트(슬래시 명령)와 평가 실행기가 함께 쓴다.

[실행 확인, M6] v1 조회 API는 쓰지 않는다. 이 계정(2026-09-16 뒤 만든 조직)에서 `api.trace.list`, `api.trace.get`, `api.sessions.list`, `api.scores.get_many`가 HTTP 410 `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`이다. Langfuse Cloud 전체에서도 2026-11-16에 없어진다. 쓰는 것은 v2 `api.observations.get_many`, `api.scores_v3.get_many_v3`, `get_trace_url` 셋이다 (DECISIONS O7).

```python
@dataclass(frozen=True, slots=True)
class RunSummary:
    trace_id: str
    timestamp: str          # trace 관측 중 가장 이른 시작
    name: str
    session_id: str | None
    latency_s: float | None # 가장 이른 시작부터 가장 늦은 끝까지
    scores: Mapping[str, float]
    error_count: int        # level이 ERROR인 관측 수
    url: str | None         # get_trace_url. v1의 htmlPath 대신


@dataclass(frozen=True, slots=True)
class Failure:
    span_name: str
    level: str
    status_message: str
    start_time: str


class RunsClient:
    """Langfuse에서 작업 기록을 읽는다."""

    def __init__(self, environ: Mapping[str, str], *, client=None) -> None:
        """Raises: TracingUnavailableError: 키가 없을 때. 클라이언트는 tracing_enabled=False로 만든다."""

    def list_runs(self, *, limit: int = 10, session_id: str | None = None) -> list[RunSummary]:
        # api.observations.get_many(fields="core,basic", limit=100, cursor=..., filter=JSON)
        #   filter: traceTags any of ["dcode-assistant"], startTime >= 지금-30일, (sessionId = session_id)
        # 태그는 콜백이 만든 루트 행에만 붙는다. trace id로 묶어 새것부터 limit개
        # 각 trace는 observations.get_many(trace_id=...)로 시각, 소요, 오류 수를 재고,
        # scores_v3.get_many_v3(trace_id=...)로 cg.* 점수를, get_trace_url로 주소를 얻는다

    def failures(self, trace_id: str) -> list[Failure]:
        # api.observations.get_many(trace_id=..., from_start_time=지금-30일, limit=100, cursor=...)를 끝까지 읽는다
        # level이 ERROR 또는 WARNING인 것, 이름이 "cg.gate.deny"인 것을 시간순으로 돌려준다

    def signals(self, trace_ids: Sequence[str]) -> dict[str, dict[str, float]]:
        """trace별 cg.* 점수 (scores_v3). 자기 개선과 평가 실행기가 쓴다."""

    def wait_for(self, trace_id: str, *, attempts: int = 6, delay_s: float = 5.0) -> bool:
        """trace가 조회될 때까지 기다린다. 끝내 안 보이면 False."""


def format_run_list(runs: Sequence[RunSummary]) -> str:
    """/runs 목록 화면의 문자열."""


def format_run_detail(run: RunSummary, failures: Sequence[Failure]) -> str:
    """/runs <id> 화면의 문자열. 실패 구간, 원인, 지표, Langfuse 주소."""
```

[M6] `format_*`는 `host` 인자를 받지 않는다. 주소는 `RunSummary.url`에 있다. 쪽 수는 조회 하나에 20쪽(2,000행)까지 읽는다. 공유 프로젝트라 태그 필터를 늘 건다. 쓰기는 비동기라 전송을 비운 뒤에도 수십 초 뒤에 보일 수 있다 (실제 요청은 40초 뒤 조회에서 보였다).

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

[M7] 실제로는 `_handle_command`의 `/trace` 분기에서 나눈다. Langfuse 키가 있으면(`tracing.is_enabled(os.environ)`) 새 처리기 `_handle_langfuse_trace_command`가 `runs.latest_trace`(이 대화의 thread id = Langfuse 세션 id로 `list_runs(limit=1, session_id=)`)의 주소를 연다. 없으면 업스트림 LangSmith 처리기를 그대로 부른다. 업스트림 `TestTraceCommand` 16건이 LangSmith 주소와 문구를 단언하고, 9.4는 그 테스트를 고치는 것을 허락하지 않는다. 바쁠 때 출력을 미루는 끝부분은 `_mount_trace_output`으로 빼서 둘이 같이 쓴다. 처리기 로직은 `runs.runs_command`(`/runs`, `/runs <앞부분>`은 최근 50건에서 찾는다)와 `runs.latest_trace`에 있다.

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
payload/           kind=rule이면 rule-<name>.md (5.1 형식. [M7] 기억 이름 규칙 `rule-…`에 맞춘다)
                   kind=skill이면 <name>/SKILL.md
validation.json    평가 실행기가 쓴다. 없으면 검증 전이다
```

`status`는 `proposed`, `validated`, `failed`, `applied`, `rejected` 가운데 하나다.

[M7] `name`은 영소문자, 숫자, `-`로 64자 이하, `description`은 200자 이하의 한 줄이다. 모델이 정하는 값이라 `create`가 검사하고, 개선안 폴더와 스킬 폴더가 심볼릭 링크로 프로젝트 밖을 가리키면 쓰지 않는다. proposal.md frontmatter에 `description`도 둔다. 본문은 `## 근거`(근거와 기대 효과)다. `record_validation`은 `result["passed"]`가 참이면 `validated`다(M8 `judge`의 결과에 이 키를 둔다). 이미 `applied`인 개선안은 `reject`하지 않는다.

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

[실행 확인, M7] 슬래시 명령 처리기에서 `_handle_user_message`를 부르면 사람 메시지로 화면에 붙고 `_send_to_agent`가 실행 worker를 띄운다. `/skill:`이 이미 같은 길(`_send_to_agent`)을 쓴다. `/improve`는 `QUEUED`라 에이전트가 쉬고 있을 때만 돈다. 바쁠 때 넣은 명령도 큐에서 꺼낼 때 같은 길로 지시문을 한 번 보내고, 뒤의 메시지도 이어서 처리됐다(pilot 실험).

[M7] 처리기 로직은 `improve.improve_command(args, project_root, environ) -> (화면 글, 지시문 | None)`에 있다. `/improve`는 최근 20건(`RECENT_RUNS`)의 `RunSummary.scores`로 관찰을 만든다. 예상 규모는 "모델 호출 약 1 + 2×관찰 수회"로 적는다(근거 없는 어림). `propose_improvement`는 관찰을 받지 않으므로 `observations=()`로 저장하고, 근거는 `rationale`에 적게 한다.

**알림.** TUI가 시작될 때 백그라운드에서 `find_observations`를 한 번 돌리고, 관찰이 있으면 "개선할 관찰이 N건 있습니다. /improve로 시작하세요"를 띄운다. 실패는 조용히 넘긴다. [M7] 실제 실행(`run_textual_app`)이 켜 둔 경우에만, 첫 서버 연결(`ServerReady`) 뒤에 한 번 돈다. `on_mount`에 두면 앱을 띄우는 업스트림 테스트마다 Langfuse를 부른다(이 셸에는 키가 있다). 조회는 데몬 스레드에서 한다. `asyncio.to_thread`면 종료가 그 조회를 기다려 61초 걸렸다.

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

[확인, M8] (원래 [미확인]) `dcode -n`의 출력에서 thread id를 얻는 방법. M8에서 `DC/client/non_interactive.py`의 출력 형식을 확인한다. `--output-format json` 같은 기계용 출력이 있으면 그것을 쓴다.

[M8] 확인 결과. `-n`에는 기계용 출력이 없다(`--json`은 하위 명령 전용). 헤더 줄 `Thread: <uuid7>`(`_build_non_interactive_header`, `--quiet`이면 안 나옴)에서 정규식으로 읽는다. Rich가 줄을 바꿔 `Thread:` 앞에서 갈리므로 공백·줄바꿈을 허용하고 `COLUMNS=400`을 준다. 승인은 `dcode -r <thread> -n "승인"`으로 실제 실행에서 G14대로 `executing` → `complete_plan` → 계획 `done`이 됐다.

[M8] 구현에서 정한 것.
- 셸: `-n`은 `-S`가 없으면 셸이 꺼지고 백엔드가 `FilesystemBackend`라서 `complete_plan`이 `test_command`를 못 돈다. 실행기는 `-S recommended,python3`을 준다.
- 과제 테스트는 표준 라이브러리 `unittest`다. 에이전트 셸의 PATH에는 `python3`만 있고 pytest가 없다. 채점은 실행기의 `sys.executable -I -B -c <unittest.main 호출> <파일들>`이다. 테스트 폴더의 최상위 항목(`tests/`)을 지우고 원본을 복사한 뒤 돌리고, 환경은 `PATH`만 넘긴다(에이전트가 둔 `tests/__init__.py`나 `unittest/`가 채점을 바꾸지 못하게). dcode가 시간을 넘기면 SIGTERM부터 보낸다(바로 SIGKILL이면 dcode가 띄운 서버가 남는다). 실행 전후로 과제 폴더의 테스트 파일 해시가 다르면 테스트를 돌리지 않고 실패로 기록한다(승인 뒤 프로젝트 밖 쓰기는 J4에만 기대므로). `tests_regression/`은 시작 저장소에도 넣는다(작업 저장소 = `repo/` + `tests_regression/`). `task.toml`에 `answers`(미결 질문의 답 목록)를 둔다. 과제 코드는 `tasks/ruff.toml`로 기본 규칙(E, F, W, I)만 건다.
- 승인 왕복은 모델 출력 문장이 아니라 작업 저장소의 가장 최근 계획 파일로 정한다. `reviewed`이고 미결 질문이 없으면 "승인", 있으면 `answers`의 다음 답(없으면 실패), 그 밖의 상태나 계획 없음이면 끝. dcode 호출은 상한 5회. 에이전트가 회귀 테스트 파일을 바꿨는지(`tests_untouched`)는 기록만 하고 채점은 원본으로 덮어써서 한다.
- 신호: trace id는 `thread_id:turn_id`로 만들어져 실행기가 알 수 없다. `wait_for(trace_id)` 대신 `list_runs(session_id=thread_id)`로 dcode 호출 수만큼 trace가 보이고 모두 점수가 붙을 때까지 기다린다(점수는 끝나고 1분 가까이 늦게 보였다. 5초 x 24회). 신호는 그 trace들의 점수 합이다(`cg.review_rounds`는 계획의 누적 회차라 최댓값). 끝내 다 보이지 않으면 일부로 계산하지 않고 빈 사전이다.
- candidate의 개선안은 `improve.install`(`apply`에서 뺀 함수)로 작업 저장소의 기억이나 스킬 폴더에 넣는다. 개선안 상태는 바꾸지 않는다.
- `TrialResult`에 `thread_id`, `calls`, `elapsed_s`를 더했다. dcode 출력은 `<작업 폴더>.log`, 결과는 `results.json`에 남는다. 작업 폴더는 지우지 않는다.
- 판정: A는 목표와 회귀 테스트 통과만 본다. B의 "통과하던 과제"는 baseline 반복이 모두 통과한 과제다. C가 판정 가능하고 "나빠짐"이면 떨어진다(P8). C는 `cg.*` 가운데 7.2 임계값 신호(클수록 나쁨)만 비교한다. `limits`의 과제 수와 반복 수는 실제 값으로 적는다. `--baseline-only`는 `judge`와 `record_validation`을 부르지 않는다. `--improvement`는 `proposed`인 개선안만 받는다(검증 기록을 덮어쓰지 않는다).
- Jev 키는 실행기를 띄운 환경에서 dcode로 그대로 넘어간다. 작업 저장소는 임시 폴더라 프로젝트 `.env`가 없다. 키는 셸 환경이나 `~/.deepagents/.env`에 있어야 한다.

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

`scripts/check_process_cwd.py`의 허용 목록은 테스트가 아니라 검사 자료다. 우리 변경이 `Path.cwd()`가 든 문장을 바꿔 토큰만 달라지면, 사용자 승인을 받고 토큰을 바꾼다 (M3에서 한 번: `run_non_interactive`, `99c1d085` → `86fa45ed`).

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

검사: `dcode --version`이 작업 사본의 경로를 보여준다. 가짜 모델 점검(`scripts/smoke_dcode.sh`)이 통과한다. `BASELINE.md`가 있다.

이후 마일스톤의 검사는 `scripts/check.sh`(`unit`, `lint`, `baseline`, `smoke`)로 돌린다. `baseline`은 단위 테스트 전체의 실패 목록을 `scripts/baseline_failures.txt`와 비교한다.

### M1. 순수 모듈

`options.py`(상수와 `Phase`), `frontmatter.py`, `plan.py`, `policy.py`, `_paths.py` 수정.

검사: `test_frontmatter.py`, `test_plan.py`, `test_policy.py` 통과. 이 세 파일에 대한 lint 통과.

### M2. 판정기와 리뷰어

`decider.py`, `reviewer.py`, `prompts.py`, `tests/.../fakes.py`, `options.py`의 `PlanGateOptions`.

검사: `test_decider.py`, `test_reviewer.py` 통과. 실제 Jev 한 번 호출로 응답 형태 확인(질문 하나, 비용 미미).

### M3. 게이트와 계획 도구

`gate.py`의 `PlanGateMiddleware`, `tools.py`의 계획 도구 셋, `agent.py`와 `server_graph.py`와 `_server_config.py`와 `main.py`의 연결.

먼저 확인할 [미확인]: `ask_user` 모양의 멈춤이 다른 도구 이름으로도 TUI에서 뜨는지(가장 먼저. 안 되면 3.6절의 승인 화면 설계가 바뀐다), 백엔드 `execute` 호출 형태, 모델 객체를 얻는 자리.

검사: 9.3절의 G1~G11, G14~G19 통과. 기준선의 단위 테스트가 그대로 통과. TUI에서 실제 모델로 한 번 돌려 승인 화면이 뜨는지 눈으로 확인.

[실행 확인, M3] 탐색 서브에이전트(`subagents.py`, `create_cli_agent` 등록, `_inject_fs_tools_into_subagents`에서 건너뛰기)를 M3로 당겼다. 없으면 `task(explorer)`가 "does not exist" 문자열을 돌려주고 게이트가 그것을 탐색 결과로 받는다. 사용자가 확정했다.

M3에서 확인한 열린 길 (M4에서 닫는다): 승인 뒤(phase executing) 게이트는 `task`를 `targets`와 J4 없이 통과시킨다 (`gate.py`의 `_decide`). 사용자 정의 선언형 서브에이전트와, `DEEPAGENTS_CODE_FORKED_SUBAGENTS=0`일 때의 `general-purpose`는 부모 게이트를 물려받지 않아 범위 밖 파일을 쓸 수 있다. M4의 `SubagentWriteBlockMiddleware`가 이 길을 닫는다. [M4] 닫았다. 같은 자리의 `task` 분기가 값 둘을 돌려줘 `awrap_tool_call`이 `ValueError`로 죽던 버그도 G12가 찾아 고쳤다.

M3에서 미룬 것: `_cg_counters`와 `aafter_agent`는 소비자인 `tracing.py`와 함께 M6. `propose_rule`은 M5, `propose_improvement`는 M7.

### M4. 서브에이전트

`SubagentWriteBlockMiddleware`, `_subagent_cli_middleware` 수정. 탐색 서브에이전트와 `_inject_fs_tools_into_subagents` 수정은 M3에서 했다.

먼저 확인할 [미확인]: fork 서브에이전트의 최종 도구 목록.

검사: G12, G13 통과. 그래프를 만든 뒤 탐색 서브에이전트의 도구 목록이 `ls`, `read_file`, `glob`, `grep`뿐인지 단언하는 테스트.

### M5. Memory

`memory.py`, `propose_rule`, `agent.py`의 메모리 블록 수정, `/remember` 교체, remember 스킬 삭제, `decider.py`의 `questions_j6` (M2에서 미룸).

검사: `test_memory.py` 통과. 그래프 테스트 둘. 작업 기록 두 건 중 판정기가 고른 한 건만 시스템 프롬프트에 들어가는지. 세션 중에 저장한 규칙이 다음 모델 호출에 들어가는지.

### M6. 추적

`tracing.py`, `runs.py`, `make_graph` 수정, `build_stream_config` 수정, LangSmith 기본 끄기. M2에서 미룬 `JevDecider.judge`의 `record_judgment`와 `PlanReviewer.areview`의 `cg.plan.review` 구간.

먼저 확인할 [미확인]: 구간이 같은 trace에 들어가는지, `mask`의 적용 범위, 서버 환경에 키가 닿는지.

검사: `test_tracing.py`, `test_runs.py` 통과(가짜 클라이언트). 실제 Langfuse 키로 요청 하나를 돌리고 `RunsClient.list_runs`와 `failures`가 결과를 돌려주는지. 가짜 비밀값이 가려져 올라갔는지.

[M6] 확인 결과로 바꾼 것: 같은 trace는 seed로 만든 trace id를 콜백과 구간에 같이 넘긴다(6.2, 6.3). 가림은 `mask_otel_spans`(6.1). 키는 워크스페이스 환경으로 `run_config`가 `init`을 부른다(6.2). 프로젝트 `.env`의 `LANGFUSE_*`는 막는다(6.1, O9). 조회는 v2 관측 API와 v3 점수 API(6.4, DECISIONS O7). 점수는 `create_score(trace_id=...)`.

### M7. 슬래시 명령과 개선안

`improve.py`, `propose_improvement`, `/runs`, `/improve`, `/trace`.

검사: `test_improve.py` 통과. `make commands-catalog` 뒤 `make lint` 통과. TUI에서 `/runs`와 `/improve list`가 뜨는지 눈으로 확인.

[M7] 확인 결과로 바꾼 것: `/trace`는 Langfuse 키가 있을 때만 새 처리기로 나눈다(6.5). 규칙 payload 이름은 `rule-<name>.md`(7.3). 알림은 실제 실행의 첫 서버 연결 뒤(7.4).

### M8. 평가 실행기와 과제

`evalsuite/`, 과제 셋.

검사: `python -m ...evalsuite verify` 통과. `test_evalsuite.py`의 `judge` 테스트 통과. `--baseline-only --trials 1` 한 번 실행.

[M8] 확인 결과로 바꾼 것: thread id는 비대화 헤더에서 읽는다. 실행기는 `-S recommended,python3`을 준다. 과제 테스트는 `unittest`다. 신호는 세션(thread)의 trace 점수 합이다. C가 "나빠짐"이면 떨어진다(7.5).

### M9. 보정과 README

`calibration/`, 사례 생성과 평가, 문구 조정, README.

검사: `holdout` 결과가 README에 있다. README의 테스트 케이스를 처음부터 끝까지 한 번 따라 한다.

## 11. README 테스트 케이스

채점자가 따라 할 순서다. 각 항목에 명령, 기대하는 결과, 대응하는 평가 항목을 적는다. 실제 모델을 부르는 항목에는 예상 규모를 적는다. 규모는 M9에서 재서 채운다.

| # | 시나리오 | 방법 | 평가 항목 |
|---|---|---|---|
| T0 | 코드 품질 | `make lint`, `make test` | 1-1, 1-2, 1-3 |
| T1 | 키 없이 실행 | `TYPESAFE_API_KEY`, `OPENROUTER_API_KEY` 없이 `dcode` | 게이트 전제 |
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
| P3 | 서브에이전트는 승인 뒤에도 항상 읽기 전용이다 | 승인 뒤 쓰기 허용 | 대안은 서브에이전트 안에서 범위 검사를 할 수 없다. 제안은 쓰기 위임을 못 쓰게 한다. [M4] 원격 비동기 서브에이전트의 시작과 지시 변경(`start_async_task`, `update_async_task`)도 승인 뒤까지 거부한다. 서브에이전트 차단은 허용 목록이다 |
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
- `MemoryStore`의 쓰기와 `rebuild_index`는 잠금이 없다. 두 프로세스(서버의 `complete_plan`, 클라이언트의 `/remember`)가 동시에 저장하면 색인이 한쪽 기억을 빠뜨릴 수 있다. 다음 저장이 색인을 다시 만들면 맞춰진다. 기억 파일 자체는 원자적으로 쓴다.
- J6는 요청문만 보고 기억을 고른다(계획 진행 중이면 계획의 요구사항도). 짧은 요청에서는 관련 기억을 놓칠 수 있다. 색인이 항상 주입되므로 모델이 직접 열 수 있다.
- Langfuse 키가 없으면 평가 4번 항목과 자기 개선 전체가 동작하지 않는다.
- 자기 개선 검증은 회귀 검사다. 개선안이 실제로 도움이 됐는지는 입증하지 않는다.
- 신호의 임계값과 Jev 임계값의 시작값은 근거 없이 정했다.
- 평가 방법론 조사의 인용은 원문 대조를 거치지 못했다.
- [M6] 게이트는 도구 결과를 카운터와 함께 `Command`로 감싼다. 게이트 바깥 미들웨어가 `ToolMessage`를 기대하면 동작이 바뀐다. `ask_user`는 `AskUserMiddleware`의 인자 거절 경고가 `ToolMessage`를 봐야 해서 감싸지 않는다(그래서 `cg.tool_calls`에 들어가지 않는다). `MemoryGuardMiddleware`가 관리 블록을 되돌리며 결과를 오류 `ToolMessage`로 바꾸면 그 호출의 카운터 증가분이 사라진다.
- [M6] 추적이 켜진 실행에서는 `cg.memory.inject`에 상한으로 뺀 기억을 적으려고 요청 시작 때 주입 글을 한 번 더 만든다. 추적이 꺼져 있으면 만들지 않는다.
- [M6] 서브에이전트 안의 도구 호출은 카운터에 들어가지 않는다. 승인 화면에서 멈춘 실행에는 `after_agent`가 돌지 않아 점수가 없다.
- [F1] 승인 전 `execute`의 읽기 전용 판정은 명령 이름 허용 목록이다. `cat`, `head`, `ls`는 프로젝트 밖 파일도 읽는다(전부터 그랬다). `cd`는 맨 앞의 절대 경로 하나만(그 뒤의 git은 루트로 갈 때만), `2>&1`과 `2>/dev/null` 밖의 리다이렉트는 받지 않는다. `(cd x && ls)`처럼 괄호로 묶은 명령, `printf`, `sed -n`, `rg`는 여전히 거부된다. [F5] `>/dev/null`, `1>/dev/null`(같이 쓰는 `2>&1` 포함. `&>/dev/null`은 sh에서 백그라운드라 거부), 루트로 가는 `git -C <절대 경로>`, 위험한 식이 없는 `find`를 더 받는다. find는 역슬래시(`\(`), `{`, `$`, 따옴표 밖 glob이 있으면 거부되고 `find`도 `cat`처럼 프로젝트 밖을 읽는다. git은 `{`, `$`가 있으면 거부된다(`HEAD@{1}` 포함).
- [F2] auto 모드(`AutoModeHITLMiddleware`)는 게이트보다 먼저 판단한다. 분류기는 주 모델 응답을 감싸는 `awrap_model_call`에서, 승인 맵에 든 도구(`execute` 등) 중 결정적 허용(`_fixed_repo_command_allowed`, 설정한 좁은 셸 허용 목록) 밖의 호출을 모두 검토한다. 게이트는 그 뒤 도구 실행 때(`awrap_tool_call`) 판단한다. 그래서 게이트가 어차피 거부할 호출도 분류기를 거치고, 분류기가 거부하면(시간 초과 포함) 그 메시지(`Auto denied [...]`)가 게이트의 안내 문장 대신 모델에 간다. 분류기는 `_SHELL_CONTROL_RE`로 조합 명령을 결정적 허용에서 빼므로 F1에서 넓힌 읽기 명령도 분류기를 거친다. 게이트의 허용을 분류기의 허용으로 넘기지 않는다(우리 판정기가 분류기 우회로가 된다). 안전은 둘이 따로 막으므로 줄지 않는다. 비용과 지연, 메시지가 달라질 뿐이다.
- [F2] 분류기 시간 제한은 기본 20초(`config_manifest.AUTO_CLASSIFIER_TIMEOUT_SECONDS_DEFAULT`)이고, 재시도 대기도 이 안에 든다. 분류기 모델은 지정하지 않으면 주 모델이다. 바꾸는 법: `DEEPAGENTS_CODE_AUTO_CLASSIFIER_TIMEOUT`이나 `config.toml` `[models].auto_classifier_timeout`(1~300초, 다음 시작부터), `DEEPAGENTS_CODE_AUTO_CLASSIFIER_MODEL`이나 `[models].auto_classifier`나 `--auto-classifier-model`(더 빠른 별도 모델). 프로젝트 `.env`로는 둘 다 정할 수 없다. 시간 초과는 그 호출을 거부하고(실행하지 않음), 연속 2번 뒤의 검토부터는 사람 승인으로 넘어간다(`_CONSECUTIVE_UNAVAILABLE_FALLBACK`). 실사용에서 본 20초 초과는 재현하지 못했다. 같은 모델 `glm-5.3-flash-ultrafast`로 체크포인트에 남은 분류기 요청 다섯 개(성공한 것들. 시간 초과 난 요청은 판정 뒤에만 저장돼 남지 않는다)를 세 번씩 0.7~4.9초, 시간 초과 난 호출을 직전 기록과 앞선 호출로 재구성한 요청은 여섯 번 3.5~7.9초(모두 거부 판정)였다. 재구성이고 새로 만든 모델 객체라 실행 당시의 모델 설정과는 다를 수 있다.
