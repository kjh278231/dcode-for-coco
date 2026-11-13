"""계획 게이트 미들웨어: 승인 전 코드 변경을 막고 승인 뒤 범위를 검사한다."""

from __future__ import annotations

import asyncio
import dataclasses
import threading
from typing import TYPE_CHECKING, Annotated, Any, NotRequired

from deepagents.backends import LocalShellBackend
from deepagents.middleware._utils import (  # noqa: PLC2701  # SPEC 3.7이 지정한 도우미
    append_to_system_message,
)
from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    PrivateStateAttr,
    TracePolicy,
    omit_payload,
)
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

from deepagents_code.assistant import prompts, sandbox, tracing
from deepagents_code.assistant.decider import question_j4, question_j5
from deepagents_code.assistant.options import (
    APPROVE_WORDS,
    APPROVED_HUMAN_ID_KEY,
    ASYNC_SUBAGENT_TOOLS,
    COUNTERS_KEY,
    EXPLORED_KEY,
    EXPLORER_SUBAGENT_NAME,
    LAST_ERROR_KEY,
    LAST_HUMAN_ID_KEY,
    NEEDS_CHANGE_KEY,
    OTHER_MUTATING_TOOLS,
    PHASE_KEY,
    PLAN_GATE_MIDDLEWARE_NAME,
    PLAN_ID_KEY,
    REJECT_WORDS,
    REQUEST_TEXT_KEY,
    REVIEW_ROUND_KEY,
    SHELL_TOOLS,
    SUBAGENT_ALLOWED_TOOLS,
    WRITE_PATH_TOOLS,
)
from deepagents_code.assistant.plan import (
    Plan,
    PlanFormatError,
    PlanStore,
    record_answers,
)
from deepagents_code.assistant.policy import (
    GIT_READ_SUBCOMMANDS,
    classify_call,
    is_read_only_shell,
    normalize_tool_path,
    relative_target,
    summarize_call,
    tool_name_of,
)
from deepagents_code.assistant.tools import build_plan_tools

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from pathlib import Path

    from deepagents.backends.protocol import BackendProtocol
    from langchain.agents.middleware.types import (
        ModelRequest,
        ModelResponse,
        ToolCallRequest,
    )
    from langgraph.runtime import Runtime

    from deepagents_code.assistant.options import PlanGateOptions

REQUEST_TEXT_MAX = 4000

_DENY_TEXT = {
    # [F1] 다음 행동을 알려 줘서 셸 명령만 바꿔 가며 다시 시도하지 않게 한다
    # [F6] git 하위 명령은 판정 표에서 만든다. branch는 목록만 받는다
    # [F7] execute가 이 문장을 받는 것은 샌드박스를 못 쓸 때뿐이다
    "no_approved_plan": "승인된 계획이 없다. 샌드박스를 못 쓰는 환경이라 읽기 전용 명령"
    f"(ls, cat, head, grep, echo, 정해진 옵션의 git {', '.join(GIT_READ_SUBCOMMANDS)}."
    " branch는 목록만)과 그 조합만 통과하고 프로그램 실행과 쓰기는 통과하지 않으니 "
    "셸 명령을 바꿔 다시 시도하지 마라. 읽기는 read_file, "
    'glob, grep이나 task(subagent_type="explorer")로 하라. 코드를 바꾸려면 먼저 '
    "탐색하고 submit_plan으로 계획을 내서 승인을 받아라.",
    "protected_path": ".deepagents/ 아래 계획, Memory, 개선안 폴더는 "
    "직접 고칠 수 없다.",
    "bad_path": "경로를 해석할 수 없다.",
    "out_of_scope": "승인된 계획의 범위 밖이다. 필요하면 submit_plan으로 계획을 고쳐 "
    "재검토를 받아라.",
    "async_subagent": "원격 서브에이전트는 쓰기를 막을 수 없어 계획 게이트가 "
    "켜져 있으면 시작하거나 지시를 바꿀 수 없다.",
    "subagent_read_only": "서브에이전트는 읽기 전용이다. 파일 변경과 쓰기 명령은 "
    "주 에이전트만 한다. 필요한 변경은 결과에 적어 돌려줘라.",
}
# [F9] J4 실패나 보호 폴더 언급으로 샌드박스에 보낸 execute 결과에 붙인다.
# 모델이 쓰기 실패를 이해하게. 계획 전 보통 명령(사유 sandbox)에는 붙이지 않는다
_SANDBOX_NOTE = {
    "sandbox_scope": "\n\n[게이트] 승인된 계획의 범위 밖으로 판정돼 읽기 전용 "
    "샌드박스에서 돌렸다. 쓰기가 필요하면 submit_plan으로 계획을 고쳐라.",
    "sandbox_protected": "\n\n[게이트] .deepagents/ 보호 폴더를 언급해 읽기 전용 "
    "샌드박스에서 돌렸다. 계획, Memory, 개선안 폴더는 직접 고칠 수 없다.",
}
_J5_YES = "\n\n[판정] 코드 변경이 필요하다. submit_plan으로 계획을 제출하라."
_J5_NO = "\n\n[판정] 이 요청은 코드 변경이 필요 없어 보인다. 탐색 결과로 답하라."


def _last_value(left: str | None, right: str | None) -> str | None:
    """병렬 도구 호출이 한 단계에 같이 써도 되게 하는 리듀서. 나중 값이 이긴다.

    Returns:
        right.
    """
    del left
    return right


def _merge_counters(
    left: dict[str, int] | None, right: dict[str, int] | None
) -> dict[str, int]:
    """키별로 더한다. `__reset__`이 있으면 빈 사전에서 다시 센다.

    Returns:
        합친 카운터.
    """
    right = dict(right or {})
    merged = {} if right.pop("__reset__", 0) else dict(left or {})
    for key, value in right.items():
        merged[key] = merged.get(key, 0) + value
    return merged


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
    _cg_counters: NotRequired[
        Annotated[dict[str, int], PrivateStateAttr, _merge_counters]
    ]
    _cg_last_error: NotRequired[Annotated[str | None, PrivateStateAttr, _last_value]]


def precheck_denies(state: object, tool_call: object) -> bool:
    """Dcode 승인 화면을 띄우기 전에 게이트가 반드시 거부할 호출인가.

    프로젝트 루트 없이 확정되는 경우만 True다. 승인 전의 경로 쓰기 도구와
    그 밖의 쓰기 도구는 경로와 관계없이 거부된다. `execute`, MCP, 승인 뒤의
    보호 경로는 승인 화면을 거친 뒤 게이트가 판단한다.

    Args:
        state: 그래프 상태.
        tool_call: 대기 중인 도구 호출.

    Returns:
        게이트가 켜져 있고 이 호출을 거부할 것이 확실하면 True.
    """
    if not isinstance(state, dict) or not isinstance(tool_call, dict):
        return False
    phase = state.get(PHASE_KEY)
    if phase is None:
        return False
    name = tool_call.get("name")
    if name in ASYNC_SUBAGENT_TOOLS:
        return True  # 단계와 관계없이 거부된다
    return phase != "executing" and name in WRITE_PATH_TOOLS | OTHER_MUTATING_TOOLS


def _last_human(messages: list[Any]) -> HumanMessage | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message
    return None


def _text_of(message: Any) -> str:  # noqa: ANN401  # ToolMessage 또는 사람 메시지
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        part.get("text", "") if isinstance(part, dict) else str(part)
        for part in content
    )


def _message_of(result: object) -> ToolMessage | None:
    # 도구 결과가 Command면 update["messages"]의 마지막 ToolMessage
    if isinstance(result, ToolMessage):
        return result
    if isinstance(result, Command) and isinstance(result.update, dict):
        messages = result.update.get("messages") or []
        return next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
    return None


def _append_text(
    result: ToolMessage | Command[Any], text: str
) -> ToolMessage | Command[Any]:
    # 도구 결과의 ToolMessage 본문 끝에 글을 붙인다
    message = _message_of(result)
    if message is None:
        return result
    new = message.model_copy(update={"content": _text_of(message) + text})
    if isinstance(result, ToolMessage):
        return new
    update = dict(result.update)  # ty: ignore[no-matching-overload]
    update["messages"] = [new if m is message else m for m in update["messages"]]
    return dataclasses.replace(result, update=update)


def _with_sandbox_note(result: Any, reason: str) -> Any:  # noqa: ANN401
    # 성공한 명령에는 안 붙인다. 쓰기 실패를 설명하려는 문구라 성공엔 컨텍스트만 늘린다
    note = _SANDBOX_NOTE.get(reason)
    message = _message_of(result)
    if note is None or (message and "[Command succeeded" in _text_of(message)):
        return result
    return _append_text(result, note)


def _with_updates(
    result: ToolMessage | Command[Any], updates: dict[str, Any]
) -> ToolMessage | Command[Any]:
    # 카운터 증가분을 도구 결과에 실어 상태에 남긴다 (SPEC 3.7)
    if isinstance(result, ToolMessage):
        return Command(update={"messages": [result], **updates})
    if result.graph is not None or not isinstance(result.update, dict):
        return result  # 부모 그래프로 가는 Command는 건드리지 않는다
    update = dict(result.update)
    if COUNTERS_KEY in update:  # 도구가 직접 센 값 (complete_plan의 test_failures)
        updates = {
            **updates,
            COUNTERS_KEY: _merge_counters(update[COUNTERS_KEY], updates[COUNTERS_KEY]),
        }
    return dataclasses.replace(result, update={**update, **updates})


def _sandboxed(request: ToolCallRequest) -> ToolCallRequest:
    # [F7] 실행할 명령만 런처로 감싼다. 모델과 승인 화면은 원래 명령을 본다
    args = request.tool_call.get("args") or {}
    command = sandbox.wrap_command(args["command"])
    return request.override(
        tool_call={**request.tool_call, "args": {**args, "command": command}}
    )


def _sandboxable(args: Mapping[str, Any]) -> bool:
    command = args.get("command")
    return isinstance(command, str) and bool(command.strip()) and sandbox.available()


def _deny(request: ToolCallRequest, reason: str) -> ToolMessage:
    return ToolMessage(
        content=_DENY_TEXT.get(reason, reason),
        name=request.tool_call["name"],
        tool_call_id=request.tool_call["id"],
        status="error",
    )


class PlanGateMiddleware(AgentMiddleware):
    """계획 승인 전의 코드 변경을 막고, 승인 뒤에는 범위를 검사한다."""

    state_schema = PlanGateState
    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(self, options: PlanGateOptions, backend: BackendProtocol) -> None:
        """게이트를 만든다.

        Args:
            options: 게이트 옵션.
            backend: 메인 에이전트의 백엔드. `complete_plan`이 테스트를 돌린다.
        """
        super().__init__()
        self._options = options
        self._store = PlanStore(options.project_root)
        self._targets_lock = threading.Lock()
        self.tools = build_plan_tools(options, backend)
        # [F7] 원격 샌드박스 백엔드에서는 명령이 이 머신에서 돌지 않는다
        default = getattr(backend, "default", backend)
        self._local_shell = isinstance(default, LocalShellBackend)

    @property
    def name(self) -> str:
        """미들웨어 이름."""
        return PLAN_GATE_MIDDLEWARE_NAME

    def _load(self, plan_id: object) -> Plan | None:
        if not isinstance(plan_id, str) or not plan_id:
            return None
        try:
            return self._store.load(plan_id)
        except FileNotFoundError, PlanFormatError, ValueError:
            return None

    # ----- 요청의 시작 -----

    def _start_request(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        human = _last_human(state.get("messages", []))
        if human is None or human.id == state.get(LAST_HUMAN_ID_KEY):
            return None  # 사람 메시지가 없거나 멈춤 뒤 재개된 실행이다
        text = _text_of(human)
        breakdown = state.get("_session_cost_breakdown") or {}
        updates: dict[str, Any] = {
            LAST_HUMAN_ID_KEY: human.id,
            REQUEST_TEXT_KEY: text[:REQUEST_TEXT_MAX],
            # LLM 호출 수는 대화 누적이라 요청 시작 값을 적어 두고 차이를 쓴다
            COUNTERS_KEY: {
                "__reset__": 1,
                "llm_base": int(breakdown.get("request_count", 0)),
            },
            LAST_ERROR_KEY: None,
        }
        phase = state.get(PHASE_KEY, "idle")
        if phase == "awaiting_approval":
            if self._options.interactive:
                phase = "planning"
            else:
                phase = self._answer_headless(state, text, human.id, updates)
        if phase == "idle":
            updates[EXPLORED_KEY] = False
            updates[NEEDS_CHANGE_KEY] = None
        updates[PHASE_KEY] = phase
        return updates

    def _answer_headless(
        self,
        state: Mapping[str, Any],
        text: str,
        human_id: str | None,
        updates: dict[str, Any],
    ) -> str:
        plan = self._load(state.get(PLAN_ID_KEY))
        if plan is None:
            return "planning"
        word = text.strip().lower()
        questions = plan.open_questions()
        if word in APPROVE_WORDS and not questions:
            self._store.save(plan.with_updates(status="approved"))
            tracing.record("cg.plan.approval", output={"result": "approved"})
            updates[APPROVED_HUMAN_ID_KEY] = human_id
            return "executing"
        if word in REJECT_WORDS:
            self._store.save(plan.with_updates(status="rejected"))
            tracing.record("cg.plan.approval", output={"result": "rejected"})
            return "idle"
        if questions:
            # 메시지 하나가 질문 전부에 대한 답이다
            plan = record_answers(plan, [("; ".join(questions), text.strip())])
            tracing.record("cg.human.question", output={"answered": len(questions)})
        else:
            tracing.record("cg.plan.approval", output={"result": "revise"})
        self._store.save(plan.with_updates(status="draft", review_round=0))
        updates[REVIEW_ROUND_KEY] = 0
        return "planning"

    def before_agent(
        self, state: PlanGateState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """새 사람 메시지를 알아보고 요청 단위 값을 정한다.

        Returns:
            상태 갱신. 재개된 실행이면 None.
        """
        del runtime
        return self._start_request(state)

    async def abefore_agent(
        self, state: PlanGateState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """새 사람 메시지를 알아보고 요청 단위 값을 정한다.

        Returns:
            상태 갱신. 재개된 실행이면 None.
        """
        del runtime
        return await asyncio.to_thread(self._start_request, state)

    # ----- 모델 호출 -----

    def _model_overrides(self, state: Mapping[str, Any]) -> tuple[str, str | None]:
        phase = state.get(PHASE_KEY, "idle")
        plan = self._load(state.get(PLAN_ID_KEY))
        summary = (
            f"id: {plan.id}\nstatus: {plan.status}\ntargets: {', '.join(plan.targets)}"
            if plan
            else None
        )
        return phase, summary

    def _override(
        self, request: ModelRequest, phase: str, summary: str | None
    ) -> ModelRequest:
        tools = request.tools
        if phase != "executing":
            blocked = (
                WRITE_PATH_TOOLS
                | OTHER_MUTATING_TOOLS
                | self._options.mcp_mutating_tool_names
            )
            tools = [t for t in tools if tool_name_of(t) not in blocked]
        system = append_to_system_message(
            request.system_message, prompts.gate_prompt(phase, summary)
        )
        return request.override(tools=tools, system_message=system)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """승인 전에는 쓰기 도구를 숨기고 단계 지침을 덧붙인다.

        Returns:
            모델 응답.
        """
        phase, summary = self._model_overrides(request.state)
        return handler(self._override(request, phase, summary))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """승인 전에는 쓰기 도구를 숨기고 단계 지침을 덧붙인다.

        Returns:
            모델 응답.
        """
        phase, summary = await asyncio.to_thread(self._model_overrides, request.state)
        return await handler(self._override(request, phase, summary))

    # ----- 도구 호출 -----

    def _decide(self, request: ToolCallRequest) -> tuple[str, str, str | None]:
        # (결정, 사유, J4가 통과시킨 새 대상). 결정은 allow, deny, explore, sandbox
        state = request.state
        name = request.tool_call["name"]
        args = request.tool_call.get("args") or {}
        phase = state.get(PHASE_KEY, "idle")
        if name == "task":
            if args.get("subagent_type") == EXPLORER_SUBAGENT_NAME:
                return "explore", "explorer", None
            # 승인 뒤에도 서브에이전트는 SubagentWriteBlockMiddleware로 읽기 전용이다
            if phase == "executing":
                return "allow", "task", None
            return "deny", "no_approved_plan", None
        plan = self._load(state.get(PLAN_ID_KEY)) if phase == "executing" else None
        last = state.get(LAST_HUMAN_ID_KEY)
        fresh = last is not None and state.get(APPROVED_HUMAN_ID_KEY) == last
        decision, reason = classify_call(
            phase=phase,
            tool_name=name,
            args=args,
            targets=plan.targets if plan else (),
            project_root=self._options.project_root,
            mcp_mutating=self._options.mcp_mutating_tool_names,
            fresh_approval=fresh,
        )
        pre_plan = phase != "executing" and reason in {
            "read_only_shell",
            "no_approved_plan",
        }
        if (
            name in SHELL_TOOLS
            and (pre_plan or reason == "protected_path")
            and self._local_shell
            and _sandboxable(args)
        ):
            # [F7] 승인 전 execute는 정적 판정 대신 읽기 전용 샌드박스에서 돈다.
            # [F9] 보호 폴더를 언급한 명령은 단계와 관계없이 샌드박스에서 돈다.
            # 읽기는 되고 쓰기는 EROFS다. J4에 보내지 않는다(통과하면 쓸 수 있다)
            return "sandbox", "sandbox" if pre_plan else "sandbox_protected", None
        if decision != "needs_scope_check":
            return decision, reason, None
        if plan is None:
            return "deny", "no_approved_plan", None
        text, question = question_j4(
            plan,
            name,
            summarize_call(name, args),
            "" if fresh else state.get(REQUEST_TEXT_KEY, ""),
        )
        verdict = self._options.decider.judge(text, [question])[0]
        if not verdict.passed:
            if name in SHELL_TOOLS and self._local_shell and _sandboxable(args):
                # [F9] 거부 대신 읽기 전용 샌드박스. 쓰기는 거부처럼 실패하고
                # 읽기 탐침은 돈다. 거부가 아니라 세지 않는다(O28)
                tracing.record("cg.gate.sandbox", input={"tool": name})
                return "sandbox", "sandbox_scope", None
            return "deny", "out_of_scope", None
        target = None
        if name in WRITE_PATH_TOOLS:
            path = normalize_tool_path(args.get("file_path"))
            target = relative_target(path, self._options.project_root) if path else None
        return "allow", "scope_ok", target

    def _extend_targets(
        self, plan_id: object, target: str | None, result: object
    ) -> None:
        # 쓰기가 성공한 뒤에만 대상을 더한다. 병렬 쓰기가 서로 덮지 않게 다시 읽는다
        if target is None or (
            isinstance(result, ToolMessage) and result.status == "error"
        ):
            return
        with self._targets_lock:
            plan = self._load(plan_id)
            if plan is not None and target not in plan.targets:
                self._store.save(plan.with_updates(targets=(*plan.targets, target)))
                tracing.record("cg.scope.extend", output={"added": target})

    def _explored(
        self, request: ToolCallRequest, result: ToolMessage | Command[Any]
    ) -> ToolMessage | Command[Any]:
        # 탐색 결과에 J5 판정을 붙이고 탐색 완료를 상태에 적는다
        message = _message_of(result)
        if message is None or message.status == "error":
            return result
        summary = _text_of(message)
        text, question = question_j5(request.state.get(REQUEST_TEXT_KEY, ""), summary)
        passed = self._options.decider.judge(text, [question])[0].passed
        tracing.record(
            "cg.explore",
            output={"summary_chars": len(summary), "needs_change": passed},
        )
        judged = _append_text(result, _J5_YES if passed else _J5_NO)
        flags = {EXPLORED_KEY: True, NEEDS_CHANGE_KEY: passed}
        if isinstance(judged, Command):
            update = judged.update  # ty: ignore[no-matching-overload]
            return dataclasses.replace(judged, update={**update, **flags})
        return Command(update={"messages": [judged], **flags})

    @staticmethod
    def _counted(
        request: ToolCallRequest,
        result: ToolMessage | Command[Any],
        denied: str | None = None,
    ) -> ToolMessage | Command[Any]:
        # 카운터 증가분을 정하고 거부를 기록한다 (SPEC 3.7 6~8단계)
        name = request.tool_call["name"]
        if name == "ask_user":
            # AskUserMiddleware가 ToolMessage로 거절 경고를 남긴다. 감싸지 않는다
            return result
        signature = summarize_call(name, request.tool_call.get("args") or {})
        message = _message_of(result)
        failed = message is not None and message.status == "error"
        delta = {"tool_calls": 1}
        if failed:
            delta["tool_errors"] = 1
            if request.state.get(LAST_ERROR_KEY) == signature:
                delta["repeat_failures"] = 1
        if denied is not None:
            delta["gate_denies"] = 1
            if denied == "out_of_scope":
                delta["jev_denies"] = 1
            tracing.record(
                "cg.gate.deny",
                input={"tool": name, "reason": denied},
                level="WARNING",
                status_message=denied,
            )
        updates = {COUNTERS_KEY: delta, LAST_ERROR_KEY: signature if failed else None}
        return _with_updates(result, updates)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """승인 전 쓰기를 거부하고, 승인 뒤에는 범위 밖 쓰기를 J4로 거른다.

        Returns:
            도구 결과 또는 거부 메시지.
        """
        decision, reason, target = self._decide(request)
        if decision == "deny":
            return self._counted(request, _deny(request, reason), reason)
        if decision == "explore":
            return self._counted(request, self._explored(request, handler(request)))
        result = handler(_sandboxed(request) if decision == "sandbox" else request)
        result = _with_sandbox_note(result, reason)
        self._extend_targets(request.state.get(PLAN_ID_KEY), target, result)
        return self._counted(request, result)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """승인 전 쓰기를 거부하고, 승인 뒤에는 범위 밖 쓰기를 J4로 거른다.

        Returns:
            도구 결과 또는 거부 메시지.
        """
        decision, reason, target = await asyncio.to_thread(self._decide, request)
        if decision == "deny":
            denied = _deny(request, reason)
            return await asyncio.to_thread(self._counted, request, denied, reason)
        run = _sandboxed(request) if decision == "sandbox" else request
        result = await handler(run)
        result = _with_sandbox_note(result, reason)
        if decision == "explore":
            result = await asyncio.to_thread(self._explored, request, result)
        else:
            await asyncio.to_thread(
                self._extend_targets, request.state.get(PLAN_ID_KEY), target, result
            )
        return await asyncio.to_thread(self._counted, request, result)

    # ----- 요청의 끝 -----

    def _end_request(self, state: Mapping[str, Any]) -> None:
        counters = state.get(COUNTERS_KEY) or {}
        breakdown = state.get("_session_cost_breakdown") or {}
        llm_calls = int(breakdown.get("request_count", 0)) - counters.get("llm_base", 0)
        plan = self._load(state.get(PLAN_ID_KEY))
        tracing.end_request(
            counters=counters,
            llm_calls=max(llm_calls, 0),
            review_rounds=plan.review_round if plan else 0,
            phase=state.get(PHASE_KEY, "idle"),
            plan_id=plan.id if plan else None,
        )

    def after_agent(
        self, state: PlanGateState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """요청의 지표를 trace에 점수로 붙인다.

        Returns:
            None. 상태를 바꾸지 않는다.
        """
        del runtime
        self._end_request(state)
        return None

    async def aafter_agent(
        self, state: PlanGateState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        """요청의 지표를 trace에 점수로 붙인다.

        Returns:
            None. 상태를 바꾸지 않는다.
        """
        del runtime
        await asyncio.to_thread(self._end_request, state)
        return None


class SubagentWriteBlockMiddleware(AgentMiddleware):
    """서브에이전트에 허용 목록의 도구만 열어 둔다.

    서브에이전트는 비공개 상태를 받지 못해 단계와 `targets`를 모른다. 범위 검사를
    할 수 없으므로 승인 뒤에도 읽기 도구만 쓴다 (SPEC 12장 P3). 목록에 없는 도구
    (쓰기, 계획 도구, `task`, 확장 도구, 읽기 전용이 아닌 MCP)는 거부한다.
    """

    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(
        self,
        project_root: Path,
        read_only_tool_names: frozenset[str] = frozenset(),
        *,
        shell_sandbox: bool = False,
    ) -> None:
        """차단기를 만든다.

        Args:
            project_root: 프로젝트 루트. 읽기 전용 셸 판정에 쓴다.
            read_only_tool_names: 더 허용할 읽기 전용 도구 이름 (MCP).
            shell_sandbox: `execute`가 이 머신의 셸에서 도는가. 그러면 [F7]
                샌드박스를 쓸 수 있을 때 정적 판정 대신 샌드박스에서 돌린다.
        """
        super().__init__()
        self._project_root = project_root
        self._allowed = SUBAGENT_ALLOWED_TOOLS | read_only_tool_names
        self._shell_sandbox = shell_sandbox

    @property
    def name(self) -> str:
        """미들웨어 이름. fork가 물려받는 PlanGateMiddleware를 이 이름으로 바꾼다."""
        return PLAN_GATE_MIDDLEWARE_NAME

    def _hide(self, request: ModelRequest) -> ModelRequest:
        tools = [t for t in request.tools if tool_name_of(t) in self._allowed]
        return request.override(tools=tools)

    def _route(self, request: ToolCallRequest) -> ToolCallRequest | None:
        # 실행할 요청. 거부면 None
        name = request.tool_call["name"]
        if name in SHELL_TOOLS:
            args = request.tool_call.get("args") or {}
            if self._shell_sandbox and _sandboxable(args):
                return _sandboxed(request)
            if is_read_only_shell(args.get("command"), self._project_root):
                return request
            return None
        return request if name in self._allowed else None

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """허용 목록 밖의 도구를 모델에게 보이지 않는다.

        Returns:
            모델 응답.
        """
        return handler(self._hide(request))

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """허용 목록 밖의 도구를 모델에게 보이지 않는다.

        Returns:
            모델 응답.
        """
        return await handler(self._hide(request))

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """허용 목록 밖의 호출을 거부한다. `execute`는 읽기 전용 명령만 통과시킨다.

        Returns:
            도구 결과 또는 거부 메시지.
        """
        run = self._route(request)
        if run is None:
            return _deny(request, "subagent_read_only")
        return handler(run)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """허용 목록 밖의 호출을 거부한다. `execute`는 읽기 전용 명령만 통과시킨다.

        Returns:
            도구 결과 또는 거부 메시지.
        """
        run = await asyncio.to_thread(self._route, request)
        if run is None:
            return _deny(request, "subagent_read_only")
        return await handler(run)
