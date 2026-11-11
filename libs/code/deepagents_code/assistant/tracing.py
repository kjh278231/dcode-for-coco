"""Langfuse 추적: 초기화, 실행 설정, 구간, 판정 기록, 요청 점수.

`langfuse`는 이 모듈의 함수 안에서만 늦게 import한다 (SPEC 9.4). 모든 공개 함수는
예외를 밖으로 던지지 않는다. 추적 실패가 작업을 막으면 안 된다.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal

from deepagents_code._env_vars import LANGFUSE_TRACING, is_env_truthy

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from deepagents_code.assistant.decider import Verdict

logger = logging.getLogger(__name__)

TRACE_ID_KEY = "cg_trace_id"
"""실행 설정 metadata에서 이 실행의 trace id를 담는 키."""

FLUSH_WAIT_S = 2.0
"""요청 끝에서 전송을 기다리는 최대 초."""

TAG = "dcode-assistant"
"""우리 trace의 태그. 같은 Langfuse 프로젝트를 쓰는 다른 도구와 구분한다."""

COUNTER_KEYS = (
    "tool_calls",
    "tool_errors",
    "repeat_failures",
    "gate_denies",
    "jev_denies",
    "test_failures",
)
"""게이트가 세는 요청 단위 카운터 (SPEC 3.7). 점수 이름은 `cg.<키>`다."""

Level = Literal["DEFAULT", "WARNING", "ERROR"]

_state: dict[str, Any] = {"enabled": False, "anonymizer": None, "settings": None}


def is_enabled(environ: Mapping[str, str]) -> bool:
    """키 둘이 있고 `DEEPAGENTS_CODE_LANGFUSE_TRACING`이 꺼져 있지 않은가.

    Args:
        environ: 환경변수 사전.

    Returns:
        Langfuse로 보낼 수 있으면 True.
    """
    return (
        bool(environ.get("LANGFUSE_PUBLIC_KEY", "").strip())
        and bool(environ.get("LANGFUSE_SECRET_KEY", "").strip())
        and is_env_truthy(LANGFUSE_TRACING, default=True, environ=environ)
    )


def client_kwargs(environ: Mapping[str, str]) -> dict[str, Any]:
    """`Langfuse(...)`에 넘길 접속 인자.

    Args:
        environ: 환경변수 사전.

    Returns:
        public_key, secret_key, base_url.
    """
    return {
        "public_key": environ["LANGFUSE_PUBLIC_KEY"].strip(),
        "secret_key": environ["LANGFUSE_SECRET_KEY"].strip(),
        "base_url": environ.get("LANGFUSE_BASE_URL")
        or environ.get("LANGFUSE_HOST")
        or None,
    }


def api_client(environ: Mapping[str, str]) -> Any:  # noqa: ANN401
    """조회 전용 Langfuse 클라이언트. 아무것도 보내지 않는다 (`runs.py`가 쓴다).

    Args:
        environ: 키가 있는 환경.

    Returns:
        `tracing_enabled=False`인 Langfuse 클라이언트.
    """
    from langfuse import Langfuse

    return Langfuse(**client_kwargs(environ), tracing_enabled=False)


def init(environ: Mapping[str, str]) -> bool:
    """가림 함수를 단 Langfuse 클라이언트를 프로세스에 하나 만든다.

    워크스페이스 환경을 받는다. 그 워크스페이스에서 추적이 꺼져 있으면 False다.
    클라이언트는 프로세스에 하나라서, 이미 다른 키나 주소로 만들어졌으면 이
    워크스페이스는 내보내지 않는다 (False). 프로젝트 `.env`는 `LANGFUSE_*`를 넣을
    수 없어서 (SPEC 6.1) 실제로는 꺼짐 스위치만 워크스페이스마다 다를 수 있다.

    Args:
        environ: 워크스페이스 환경.

    Returns:
        이 워크스페이스의 실행을 내보내도 되는지.
    """
    if not is_enabled(environ):
        return False
    kwargs = client_kwargs(environ)
    settings = (kwargs["public_key"], kwargs["base_url"])
    if _state["enabled"]:
        if settings != _state["settings"]:
            logger.warning("Langfuse 설정이 처음 워크스페이스와 달라 추적하지 않는다")
            return False
        return True
    try:
        from langfuse import Langfuse

        Langfuse(**kwargs, mask_otel_spans=_mask_otel_spans)
    except Exception as exc:  # noqa: BLE001  # 추적 실패가 기동을 막으면 안 된다
        logger.warning("Langfuse 추적을 켜지 못했다: %s", type(exc).__name__)
        return False
    _state["enabled"] = True
    _state["settings"] = settings
    return True


def _anonymizer() -> Callable[[Any], Any]:
    if _state["anonymizer"] is None:
        from deepagents_code._trace_redaction import create_cached_secret_anonymizer

        _state["anonymizer"] = create_cached_secret_anonymizer()
    return _state["anonymizer"]


def _mask_otel_spans(*, params: Any) -> Any:  # noqa: ANN401  # langfuse 타입은 늦게 import
    """내보내기 직전 span 속성의 비밀값을 가린다.

    `mask`는 LangChain 메시지 객체를 들여다보지 못해 원문이 새었다 (M6 확인).
    직렬화된 속성 문자열에 거는 이 함수가 모두 덮는다. 예외가 나면 Langfuse가
    그 묶음을 통째로 버리므로 원문은 나가지 않는다.

    Returns:
        span별 속성 패치.
    """
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    anon = _anonymizer()
    patches = {}
    for ident, span in params.spans.items():
        changed: dict[str, Any] = {}
        for key, value in span.attributes.items():
            if isinstance(value, str):
                masked: Any = anon(value)
            elif isinstance(value, (list, tuple)) and all(
                isinstance(v, str) for v in value
            ):
                masked = tuple(anon(v) for v in value)
                value = tuple(value)  # noqa: PLW2901  # 비교용
            else:
                continue
            if masked != value:
                changed[key] = masked
        if changed:
            patches[ident] = OtelSpanPatch(set_attributes=changed)
    return MaskOtelSpansResult(span_patches=patches)


def _client() -> Any:  # noqa: ANN401
    if not _state["enabled"]:
        return None
    from langfuse import get_client

    return get_client()


def is_active() -> bool:
    """지금 실행이 추적 중인가 (클라이언트가 있고 run_config가 붙은 실행 안).

    Returns:
        구간과 점수를 보낼 곳이 있으면 True.
    """
    return _client() is not None and current_trace_id() is not None


def _seed(config: Mapping[str, Any] | None) -> str | None:
    # 요청(사용자 프롬프트 하나)마다 같은 값. 서버는 한 실행 안에서도 make_graph를
    # 여러 번 부르고, 승인 뒤 재개는 새 실행이다 (M6 확인)
    config = config or {}
    metadata = config.get("metadata") or {}
    configurable = config.get("configurable") or {}
    thread_id = metadata.get("thread_id") or configurable.get("thread_id")
    turn = metadata.get("turn_id") or configurable.get("run_id")
    return f"{thread_id}:{turn}" if thread_id and turn else None


def run_config(
    config: Mapping[str, Any] | None, environ: Mapping[str, str]
) -> dict[str, Any] | None:
    """실행에 붙일 설정. 이 워크스페이스에서 꺼져 있으면 None.

    콜백과 우리 구간이 같은 trace에 들어가도록 trace id를 콜백의 `trace_context`와
    metadata에 함께 둔다. 실행 문맥은 미들웨어 훅까지 이어지지 않는다 (M6 확인).
    id는 실행 설정의 thread id와 turn id(없으면 run id)에서 만든다. 같은 요청이면
    make_graph를 몇 번 불러도 같은 trace다. turn id가 없으면 run id라서 실행마다
    trace가 갈린다.

    Args:
        config: make_graph가 받은 실행 설정.
        environ: 그 실행의 워크스페이스 환경. `init`에 넘긴다.

    Returns:
        `{"callbacks": [...], "metadata": {TRACE_ID_KEY: id}}` 또는 None.
    """
    if not init(environ):
        return None
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        trace_id = Langfuse.create_trace_id(seed=_seed(config))
        handler = CallbackHandler(trace_context={"trace_id": trace_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse 콜백을 만들지 못했다: %s", type(exc).__name__)
        return None
    return {"callbacks": [handler], "metadata": {TRACE_ID_KEY: trace_id}}


def current_trace_id() -> str | None:
    """지금 도는 그래프 실행의 trace id. 실행 밖이거나 추적이 꺼졌으면 None.

    Returns:
        32자 trace id 또는 None.
    """
    try:
        from langgraph.config import get_config

        value = (get_config().get("metadata") or {}).get(TRACE_ID_KEY)
    except RuntimeError:  # 실행 문맥 밖
        return None
    return value if isinstance(value, str) and value else None


class SpanHandle:
    """열린 구간. 추적이 꺼져 있으면 아무것도 하지 않는다."""

    def __init__(self, observation: Any = None) -> None:  # noqa: ANN401
        """핸들을 만든다.

        Args:
            observation: Langfuse 관측 객체. 없으면 아무것도 하지 않는다.
        """
        self._observation = observation

    def update(
        self,
        *,
        output: Any = None,  # noqa: ANN401
        metadata: Mapping[str, Any] | None = None,
        level: Level | None = None,
        status_message: str | None = None,
    ) -> None:
        """구간에 결과를 적는다."""
        if self._observation is None:
            return
        fields = {
            "output": output,
            "metadata": metadata,
            "level": level,
            "status_message": status_message,
        }
        try:
            self._observation.update(
                **{k: v for k, v in fields.items() if v is not None}
            )
        except Exception:
            logger.debug("구간 갱신 실패", exc_info=True)


@contextmanager
def span(
    name: str,
    *,
    input: Any = None,  # noqa: A002, ANN401  # Langfuse 인자 이름
    metadata: Mapping[str, Any] | None = None,
    as_type: str = "span",
) -> Iterator[SpanHandle]:
    """구간 하나를 연다. 끝나면 닫는다.

    Args:
        name: 구간 이름 (`cg.*`).
        input: 입력.
        metadata: 메타데이터.
        as_type: Langfuse 관측 종류.

    Yields:
        구간 핸들.
    """
    observation = None
    client = _client()
    trace_id = current_trace_id()
    # run_config가 붙지 않은 실행(추적이 꺼진 워크스페이스, 그래프 밖)은 보내지 않는다
    if client is not None and trace_id is not None:
        try:
            observation = client.start_observation(
                name=name,
                as_type=as_type,
                input=input,
                metadata=metadata,
                trace_context={"trace_id": trace_id},
            )
        except Exception:
            logger.debug("구간 열기 실패", exc_info=True)
    try:
        yield SpanHandle(observation)
    finally:
        if observation is not None:
            try:
                observation.end()
            except Exception:
                logger.debug("구간 닫기 실패", exc_info=True)


def record(
    name: str,
    *,
    input: Any = None,  # noqa: A002, ANN401
    output: Any = None,  # noqa: ANN401
    level: Level | None = None,
    status_message: str | None = None,
    as_type: str = "span",
) -> None:
    """곧바로 닫히는 구간 하나를 남긴다 (사건 기록)."""
    with span(name, input=input, as_type=as_type) as handle:
        handle.update(output=output, level=level, status_message=status_message)


def record_judgment(question: str, state_chars: int, verdict: Verdict) -> None:
    """Jev 판정 하나를 `cg.judge.<질문>` 구간으로 남긴다. state 원문은 넣지 않는다.

    J6의 `J6:<기억 이름>`은 구간 이름을 `cg.judge.J6`로 두고 전체 이름은 입력에 둔다.

    Args:
        question: 질문 이름.
        state_chars: 판정 state 길이.
        verdict: 판정 결과.
    """
    record(
        f"cg.judge.{question.split(':', 1)[0]}",
        input={"question": question, "state_chars": state_chars},
        output={
            "probability": verdict.probability,
            "passed": verdict.passed,
            "reason": verdict.reason,
        },
        as_type="guardrail",
    )


def end_request(
    *,
    counters: Mapping[str, int],
    llm_calls: int,
    review_rounds: int,
    phase: str,
    plan_id: str | None,
) -> None:
    """요청의 지표를 지금 trace에 `cg.*` 점수로 붙인다. 전송은 최대 2초 기다린다.

    Args:
        counters: 게이트 카운터.
        llm_calls: 이번 요청의 LLM 호출 수.
        review_rounds: 계획의 리뷰 회차.
        phase: 요청이 끝났을 때의 단계.
        plan_id: 계획 id.
    """
    client = _client()
    trace_id = current_trace_id()
    if client is None or trace_id is None:
        return
    values = {k: counters.get(k, 0) for k in COUNTER_KEYS}
    values |= {"llm_calls": llm_calls, "review_rounds": review_rounds}
    meta = {"phase": phase, "plan_id": plan_id}
    try:
        for key, value in values.items():
            client.create_score(
                trace_id=trace_id, name=f"cg.{key}", value=float(value), metadata=meta
            )
    except Exception:
        logger.debug("점수 기록 실패", exc_info=True)
    # 비대화 실행은 끝나자마자 서버가 내려가 배치에 남은 점수를 잃는다 (M6 확인).
    # 그래서 비우되 FLUSH_WAIT_S만 기다린다. 넘으면 SDK 배치와 종료 flush에 맡긴다
    flusher = threading.Thread(
        target=client.flush, name="cg-langfuse-flush", daemon=True
    )
    flusher.start()
    flusher.join(FLUSH_WAIT_S)
