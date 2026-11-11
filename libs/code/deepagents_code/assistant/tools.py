"""계획 도구: submit_plan, request_plan_approval, complete_plan, propose_rule."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any

from langchain.tools import InjectedToolCallId, ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command, interrupt

from deepagents_code.assistant import tracing
from deepagents_code.assistant.decider import question_j1, question_j2, question_j3
from deepagents_code.assistant.memory import (
    MemoryFormatError,
    MemoryStore,
    rule_name,
)
from deepagents_code.assistant.options import (
    APPROVE_WORDS,
    APPROVED_HUMAN_ID_KEY,
    COUNTERS_KEY,
    EXPLORED_KEY,
    EXPLORER_SUBAGENT_NAME,
    LAST_HUMAN_ID_KEY,
    MAX_REVIEW_ROUNDS,
    NEEDS_CHANGE_KEY,
    PHASE_KEY,
    PLAN_ID_KEY,
    REJECT_WORDS,
    REVIEW_ROUND_KEY,
)
from deepagents_code.assistant.plan import (
    EMPTY_MARK,
    Plan,
    PlanFormatError,
    PlanStore,
    new_plan_id,
    record_answers,
    validate_plan,
)

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol
    from langchain_core.tools import BaseTool

    from deepagents_code.assistant.decider import Verdict
    from deepagents_code.assistant.options import PlanGateOptions
    from deepagents_code.assistant.reviewer import ReviewResult

TEST_TIMEOUT_S = 600
OUTPUT_TAIL_CHARS = 4000


def _reply(
    text: str, tool_call_id: str, name: str, *, error: bool = False, **updates: Any
) -> Command[Any]:
    message = ToolMessage(
        content=text,
        tool_call_id=tool_call_id,
        name=name,
        status="error" if error else "success",
    )
    return Command(update={**updates, "messages": [message]})


def _bullets(items: tuple[str, ...] | list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) or EMPTY_MARK


def _dedupe(*groups: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for group in groups:
        for item in group:
            if item.strip():
                seen.setdefault(item.strip(), None)
    return tuple(seen)


def _review_entry(
    round_no: int,
    verdicts: list[Verdict],
    issues: list[str],
    review: ReviewResult,
) -> str:
    judged = [
        f"- {v.name}: {'통과' if v.passed else '통과 못 함'} ({v.reason})"
        for v in verdicts
    ]
    parts = [
        f"### {round_no}회차",
        "판정:\n" + ("\n".join(judged) or "부르지 않음 (형식 문제)"),
        "형식 문제:\n" + _bullets(issues),
        "의견:\n" + _bullets(list(review.comments)),
    ]
    if review.error:
        parts.append(f"리뷰 실패: {review.error}")
    return "\n\n".join(parts)


def _load(store: PlanStore, plan_id: str | None) -> Plan | None:
    if not plan_id:
        return None
    try:
        return store.load(plan_id)
    except FileNotFoundError, PlanFormatError, ValueError:
        return None


def build_plan_tools(
    options: PlanGateOptions, backend: BackendProtocol
) -> list[BaseTool]:
    """계획 도구를 만든다. PlanGateMiddleware.tools가 이 목록을 쓴다.

    `propose_improvement`(M7)는 아직 없다.

    Args:
        options: 게이트 옵션.
        backend: `complete_plan`이 테스트 명령을 실행할 백엔드.

    Returns:
        submit_plan, request_plan_approval, complete_plan, propose_rule.
    """
    store = PlanStore(options.project_root)
    memory = MemoryStore(options.project_root)

    async def submit_plan(  # 계획의 절마다 인자 하나
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
        """계획을 제출한다. 형식 검사, 판정, 리뷰를 거쳐 계획 파일을 쓴다.

        Args:
            requirements: 요구사항.
            scope: 작업 범위.
            done_criteria: 실행해서 확인할 수 있는 완료 조건.
            steps: 작업 순서.
            targets: 고칠 파일. 프로젝트 루트 기준 상대 경로.
            test_command: 완료를 확인하는 테스트 명령.
            memory_refs: 참고한 Memory. 없으면 "없음".
            open_questions: 사람에게 물을 질문. 없으면 빈 목록.
            tool_call_id: 주입되는 호출 id.
            runtime: 주입되는 도구 실행 환경.

        Returns:
            상태 갱신과 결과 메시지.
        """
        state = runtime.state
        phase = state.get(PHASE_KEY, "idle")
        if phase == "awaiting_approval":
            return _reply(
                "사람의 답을 기다리는 중이다. 계획을 다시 낼 수 없다.",
                tool_call_id,
                "submit_plan",
                error=True,
            )
        if not state.get(EXPLORED_KEY):
            return _reply(
                f"먼저 task(subagent_type='{EXPLORER_SUBAGENT_NAME}')로 탐색하라.",
                tool_call_id,
                "submit_plan",
                error=True,
            )
        if state.get(NEEDS_CHANGE_KEY) is False:  # J5는 변경이 필요 없다고 봤다
            tracing.record(
                "cg.judge.mismatch",
                output={"j5_needs_change": False, "tool": "submit_plan"},
            )
        # idle에서는 끝났거나 거부된 계획을 덮어쓰지 않도록 새 id를 만든다
        plan_id = state.get(PLAN_ID_KEY) if phase != "idle" else None
        previous = await asyncio.to_thread(_load, store, plan_id)
        # 새 계획(idle)과 승인 뒤 재검토(executing)는 리뷰 회차를 처음부터 센다
        review_round = (
            0 if phase in {"idle", "executing"} else state.get(REVIEW_ROUND_KEY, 0)
        )
        now = datetime.now(UTC)
        plan_id = plan_id or new_plan_id(now, requirements)
        kept = previous.sections if previous else {}
        plan = Plan(
            id=plan_id,
            status="draft",
            targets=tuple(targets),
            test_command=test_command,
            review_round=review_round,
            trace_ids=previous.trace_ids if previous else (),
            created_at=previous.created_at if previous else now.isoformat(),
            sections={
                "요구사항": requirements,
                "작업 범위": scope,
                "완료 조건": done_criteria,
                "작업 순서": steps,
                "참고한 Memory": memory_refs,
                "미결 질문": _bullets(
                    _dedupe(
                        previous.open_questions() if previous else (), open_questions
                    )
                ),
                "결정 사항": kept.get("결정 사항", EMPTY_MARK),
                "리뷰 기록": kept.get("리뷰 기록", ""),
            },
        )
        issues = validate_plan(plan)
        verdicts: list[Verdict] = []
        if not issues:

            def judge() -> list[Verdict]:
                out: list[Verdict] = []
                for build in (question_j1, question_j2, question_j3):
                    text, question = build(plan)
                    out.extend(options.decider.judge(text, [question]))
                return out

            verdicts = await asyncio.to_thread(judge)
        review = await options.reviewer.areview(plan, verdicts, issues)
        review_round += 1
        log = plan.sections["리뷰 기록"].strip()
        entry = _review_entry(review_round, verdicts, issues, review)
        questions = _dedupe(plan.open_questions(), review.questions)
        sections = dict(plan.sections)
        sections["리뷰 기록"] = f"{log}\n\n{entry}" if log else entry
        sections["미결 질문"] = _bullets(questions)

        if issues:
            status, text = "draft", "형식 문제가 있다. 고쳐서 다시 제출하라.\n"
            text += _bullets(issues)
        elif review.comments and review_round < MAX_REVIEW_ROUNDS:
            status, text = "draft", "리뷰 의견이 있다. 반영해서 다시 제출하라.\n"
            text += _bullets(list(review.comments))
        else:
            status = "reviewed"
            text = "검토가 끝났다. request_plan_approval을 불러 사람의 승인을 받아라."
        plan = plan.with_updates(
            status=status, review_round=review_round, sections=sections
        )
        await asyncio.to_thread(store.save, plan)
        tracing.record(
            "cg.plan.submit",
            output={
                "plan_id": plan_id,
                "round": review_round,
                "format_issues": len(issues),
                "status": status,
            },
        )
        return _reply(
            f"계획 {plan_id}\n{text}",
            tool_call_id,
            "submit_plan",
            # 리뷰 의견으로 다시 내는 것은 정상 흐름이라 오류로 세지 않는다
            error=bool(issues),
            **{
                PHASE_KEY: "planning",
                PLAN_ID_KEY: plan_id,
                REVIEW_ROUND_KEY: review_round,
            },
        )

    def _ask(
        tool_call_id: str, state: dict[str, Any]
    ) -> tuple[Plan | None, list[dict[str, Any]], Command[Any] | None]:
        # 멈추기 전 단계. (계획, 질문, 바로 돌려줄 결과)
        name = "request_plan_approval"
        plan = _load(store, state.get(PLAN_ID_KEY))
        if plan is None or plan.status != "reviewed":
            return (
                None,
                [],
                _reply(
                    "검토가 끝난 계획이 없다. 먼저 submit_plan으로 계획을 내라.",
                    tool_call_id,
                    name,
                    error=True,
                ),
            )
        questions = plan.open_questions()
        markdown = plan.to_markdown()
        if not options.interactive:
            tracing.record("cg.human.question", output={"asked": len(questions)})
            ask = (
                "\n\n다음 질문에 답해 주세요.\n" + _bullets(list(questions))
                if questions
                else "\n\n승인하려면 '승인', 거부하려면 '거부'를 보내 주세요."
            )
            return (
                None,
                [],
                _reply(
                    "아래 내용을 그대로 최종 답변으로 출력하고 턴을 끝내라.\n\n"
                    + markdown
                    + ask,
                    tool_call_id,
                    name,
                    **{PHASE_KEY: "awaiting_approval"},
                ),
            )
        if questions:
            asked: list[dict[str, Any]] = [
                {"question": q, "type": "text"} for q in questions
            ]
            asked[0]["question"] = f"{markdown}\n\n{questions[0]}"
        else:
            asked = [
                {
                    "question": f"{markdown}\n\n이 계획을 승인하시겠습니까?",
                    "type": "multiple_choice",
                    "choices": [{"value": "승인"}, {"value": "거부"}],
                }
            ]
        return plan, asked, None

    def _answer(  # 재개 값 해석 표의 행마다 하나
        plan: Plan,
        asked: list[dict[str, Any]],
        response: object,
        tool_call_id: str,
        state: dict[str, Any],
    ) -> Command[Any]:
        # 재개 값을 해석해 계획과 상태를 갱신한다
        name = "request_plan_approval"
        answered = (
            isinstance(response, dict)
            and response.get("status", "answered") == "answered"
        )
        answers = response.get("answers") if answered else None  # type: ignore[union-attr]
        if not (
            isinstance(answers, list)
            and len(answers) == len(asked)
            and all(isinstance(a, str) for a in answers)
        ):
            return _reply(
                "답을 받지 못했다. 다시 request_plan_approval을 불러라.",
                tool_call_id,
                name,
                error=True,
                **{PHASE_KEY: "planning"},
            )
        questions = plan.open_questions()
        if questions:
            tracing.record("cg.human.question", output={"answered": len(questions)})
            pairs = list(zip(questions, answers, strict=True))
            store.save(record_answers(plan, pairs).with_updates(status="draft"))
            qa = "\n".join(f"- 질문: {q}\n  답: {a}" for q, a in pairs)
            return _reply(
                "사람이 질문에 답했다. 결정 사항에 적었다. "
                "답을 계획 본문에 반영해서 다시 제출하라.\n" + qa,
                tool_call_id,
                name,
                **{PHASE_KEY: "planning"},
            )
        answer = answers[0].strip()
        result = (
            "approved"
            if answer.lower() in APPROVE_WORDS
            else "rejected"
            if answer.lower() in REJECT_WORDS
            else "revise"
        )
        tracing.record("cg.plan.approval", output={"result": result})
        if result == "approved":
            store.save(plan.with_updates(status="approved"))
            return _reply(
                "승인됐다. 계획대로 진행하고 끝나면 complete_plan을 불러라.",
                tool_call_id,
                name,
                **{
                    PHASE_KEY: "executing",
                    APPROVED_HUMAN_ID_KEY: state.get(LAST_HUMAN_ID_KEY),
                },
            )
        if result == "rejected":
            store.save(plan.with_updates(status="rejected"))
            return _reply(
                "거부됐다. 코드 변경을 하지 말고 사용자에게 다음 지시를 물어라.",
                tool_call_id,
                name,
                **{PHASE_KEY: "idle"},
            )
        store.save(plan.with_updates(status="draft", review_round=0))
        return _reply(
            "사람이 수정을 요청했다. 반영해서 다시 제출하라.\n수정 요청: " + answer,
            tool_call_id,
            name,
            **{PHASE_KEY: "planning", REVIEW_ROUND_KEY: 0},
        )

    def _payload(tool_call_id: str, asked: list[dict[str, Any]]) -> dict[str, Any]:
        return {"type": "ask_user", "tool_call_id": tool_call_id, "questions": asked}

    def request_plan_approval(
        tool_call_id: Annotated[str, InjectedToolCallId],
        runtime: ToolRuntime[Any, Any],
    ) -> Command[Any]:
        """검토가 끝난 계획을 사람에게 보여주고 승인이나 답을 받는다.

        Args:
            tool_call_id: 주입되는 호출 id.
            runtime: 주입되는 도구 실행 환경.

        Returns:
            상태 갱신과 결과 메시지.
        """
        plan, asked, early = _ask(tool_call_id, runtime.state)
        if early is not None or plan is None:
            return early  # type: ignore[return-value]
        # 재개되면 도구 본문이 처음부터 다시 돈다. 멈추기 전에는 비용이 드는 일이 없다
        response = interrupt(_payload(tool_call_id, asked))
        return _answer(plan, asked, response, tool_call_id, runtime.state)

    async def arequest_plan_approval(
        tool_call_id: Annotated[str, InjectedToolCallId],
        runtime: ToolRuntime[Any, Any],
    ) -> Command[Any]:
        """검토가 끝난 계획을 사람에게 보여주고 승인이나 답을 받는다.

        Args:
            tool_call_id: 주입되는 호출 id.
            runtime: 주입되는 도구 실행 환경.

        Returns:
            상태 갱신과 결과 메시지.
        """
        state = runtime.state
        plan, asked, early = await asyncio.to_thread(_ask, tool_call_id, state)
        if early is not None or plan is None:
            return early  # type: ignore[return-value]
        # interrupt()는 실행 문맥에서 불러야 해서 스레드로 넘기지 않는다
        response = interrupt(_payload(tool_call_id, asked))
        return await asyncio.to_thread(
            _answer, plan, asked, response, tool_call_id, state
        )

    async def complete_plan(
        summary: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        runtime: ToolRuntime[Any, Any],
        abandon: bool = False,  # 모델이 채우는 도구 인자
    ) -> Command[Any]:
        """작업을 끝낸다. 게이트가 계획의 test_command를 직접 실행해 결과를 기록한다.

        Args:
            summary: 한 일의 요약.
            tool_call_id: 주입되는 호출 id.
            runtime: 주입되는 도구 실행 환경.
            abandon: 계획을 포기하면 True. 테스트를 돌리지 않는다.

        Returns:
            상태 갱신과 결과 메시지.
        """
        name = "complete_plan"
        state = runtime.state
        plan = await asyncio.to_thread(_load, store, state.get(PLAN_ID_KEY))
        if state.get(PHASE_KEY) != "executing" or plan is None:
            return _reply("승인된 계획이 없다.", tool_call_id, name, error=True)
        if abandon:
            await asyncio.to_thread(store.save, plan.with_updates(status="failed"))
            tracing.record("cg.result", output={"status": "failed", "summary": summary})
            return _reply("계획을 포기했다.", tool_call_id, name, **{PHASE_KEY: "idle"})
        with tracing.span("cg.test.run", input={"command": plan.test_command}) as run:
            try:
                result = await backend.aexecute(  # ty: ignore[unresolved-attribute]
                    plan.test_command, timeout=TEST_TIMEOUT_S
                )
                exit_code, output = result.exit_code, result.output
            except NotImplementedError:
                exit_code, output = None, "이 세션의 백엔드는 셸 명령을 실행할 수 없다."
            run.update(
                output={"exit_code": exit_code, "tail": output[-OUTPUT_TAIL_CHARS:]},
                level=None if exit_code == 0 else "ERROR",
            )
        if exit_code == 0:
            done = plan.with_updates(status="done")
            await asyncio.to_thread(store.save, done)
            text = f"테스트 통과: {plan.test_command}. 계획을 마쳤다."
            try:
                record = await asyncio.to_thread(
                    memory.save_work_record, done, summary, now=datetime.now(UTC)
                )
                text += f" 작업 기록 {record.name}을 저장했다."
            except (OSError, ValueError) as exc:
                text += f" 작업 기록은 저장하지 못했다: {exc}"
            tracing.record("cg.result", output={"status": "done", "summary": summary})
            return _reply(
                text,
                tool_call_id,
                name,
                **{PHASE_KEY: "idle"},
            )
        return _reply(
            f"테스트 실패 (종료 코드 {exit_code}): {plan.test_command}\n"
            f"고친 뒤 다시 complete_plan을 불러라.\n\n{output[-OUTPUT_TAIL_CHARS:]}",
            tool_call_id,
            name,
            error=True,
            **{COUNTERS_KEY: {"test_failures": 1}},
        )

    def _rule_question(description: str, body: str) -> dict[str, Any]:
        ask = "프로젝트 규칙으로 저장할까요?"
        name = rule_name(description.strip())
        if memory.exists(name):
            ask = f"같은 설명의 기존 규칙 {name}을 이 내용으로 바꿀까요?"
        return {
            "question": f"{ask}\n\n{description}\n\n{body}",
            "type": "multiple_choice",
            "choices": [{"value": "저장"}, {"value": "버림"}],
        }

    def _rule_result(
        description: str, body: str, response: object, tool_call_id: str
    ) -> Command[Any]:
        name = "propose_rule"
        answers = response.get("answers") if isinstance(response, dict) else None
        if not (
            isinstance(answers, list) and answers and str(answers[0]).strip() == "저장"
        ):
            return _reply("사람이 규칙을 저장하지 않기로 했다.", tool_call_id, name)
        try:
            record = memory.save_rule(
                description, body, source="agent-approved", now=datetime.now(UTC)
            )
        except (MemoryFormatError, OSError) as exc:
            text = f"규칙을 저장하지 못했다: {exc}"
            return _reply(text, tool_call_id, name, error=True)
        return _reply(f"규칙 {record.name}을 저장했다.", tool_call_id, name)

    def _rule_headless(tool_call_id: str) -> Command[Any] | None:
        if options.interactive:
            return None
        return _reply(
            "비대화 실행에서는 규칙을 저장할 수 없다.",
            tool_call_id,
            "propose_rule",
            error=True,
        )

    def propose_rule(
        description: str,
        body: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        runtime: ToolRuntime[Any, Any],
    ) -> Command[Any]:
        """프로젝트 규칙 후보를 사람에게 보여주고, 승인되면 저장한다.

        Args:
            description: 규칙의 한 줄 설명 (200자 이하).
            body: 규칙 본문. 왜 그런지 한 줄을 함께 적는다.
            tool_call_id: 주입되는 호출 id.
            runtime: 주입되는 도구 실행 환경.

        Returns:
            결과 메시지.
        """
        del runtime
        if (early := _rule_headless(tool_call_id)) is not None:
            return early
        response = interrupt(
            _payload(tool_call_id, [_rule_question(description, body)])
        )
        return _rule_result(description, body, response, tool_call_id)

    async def apropose_rule(
        description: str,
        body: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
        runtime: ToolRuntime[Any, Any],
    ) -> Command[Any]:
        """프로젝트 규칙 후보를 사람에게 보여주고, 승인되면 저장한다.

        Args:
            description: 규칙의 한 줄 설명 (200자 이하).
            body: 규칙 본문. 왜 그런지 한 줄을 함께 적는다.
            tool_call_id: 주입되는 호출 id.
            runtime: 주입되는 도구 실행 환경.

        Returns:
            결과 메시지.
        """
        del runtime
        if (early := _rule_headless(tool_call_id)) is not None:
            return early
        # 멈추기 전에는 비용이 드는 일을 하지 않는다. 저장은 재개 뒤에 한 번
        response = interrupt(
            _payload(tool_call_id, [_rule_question(description, body)])
        )
        return await asyncio.to_thread(
            _rule_result, description, body, response, tool_call_id
        )

    return [
        StructuredTool.from_function(coroutine=submit_plan, name="submit_plan"),
        StructuredTool.from_function(
            func=request_plan_approval,
            coroutine=arequest_plan_approval,
            name="request_plan_approval",
        ),
        StructuredTool.from_function(coroutine=complete_plan, name="complete_plan"),
        StructuredTool.from_function(
            func=propose_rule, coroutine=apropose_rule, name="propose_rule"
        ),
    ]
