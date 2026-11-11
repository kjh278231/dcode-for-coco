"""Jev 판정기와 판정 질문 J1~J5."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol

import httpx

from deepagents_code._env_vars import PLAN_GATE_JEV_THRESHOLD
from deepagents_code.assistant.options import JEV_THRESHOLD_DEFAULT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from deepagents_code.assistant.plan import Plan

KEY_ENV: str = "TYPESAFE_API_KEY"
OPENROUTER_KEY_ENV: str = "OPENROUTER_API_KEY"
STATE_MAX_CHARS: int = 4000

VerdictReason = Literal[
    "ok", "below_threshold", "refused", "invalid", "transport_error"
]


@dataclass(frozen=True, slots=True)
class Noul:
    """예 또는 아니오 질문 하나."""

    name: str
    instructions: str
    true: str
    false: str


@dataclass(frozen=True, slots=True)
class Verdict:
    """질문 하나의 판정 결과."""

    name: str
    probability: float | None
    passed: bool
    reason: VerdictReason


class DeciderError(RuntimeError):
    """Jev 호출 실패. 메시지에 키나 요청 본문을 넣지 않는다."""


class Decider(Protocol):
    """판정기. 테스트에서는 FakeDecider를 주입한다."""

    def judge(self, state: str, questions: Sequence[Noul]) -> list[Verdict]:
        """state를 근거로 questions 각각을 판정한다. 예외를 던지지 않는다."""
        ...


def _verdict(name: str, probability: float, threshold: float) -> Verdict:
    passed = probability >= threshold
    return Verdict(name, probability, passed, "ok" if passed else "below_threshold")


def _failed(name: str, reason: VerdictReason) -> Verdict:
    return Verdict(name, None, passed=False, reason=reason)


def _read_answer(answer: object, name: str, threshold: float) -> Verdict:
    if answer is None:
        return _failed(name, "refused")
    if not isinstance(answer, dict):
        return _failed(name, "invalid")
    value = answer.get("noul")
    if value is None:
        return _failed(name, "refused")
    # bool은 int의 하위형이라 따로 막는다. JSON true가 1.0으로 통과하면 안 된다
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _failed(name, "invalid")
    probability = float(value)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        return _failed(name, "invalid")
    return _verdict(name, probability, threshold)


class JevDecider:
    """TypeSafe Jev를 부르는 판정기. TypeSafe 직접 또는 OpenRouter 경유."""

    URL: ClassVar[str] = "https://api.typesafe.ai/v1/systemone"
    MODEL: ClassVar[str] = "jev-latest"
    # OpenRouter는 같은 본문 형식을 받는다. jev-latest는 HTTP 400이라 버전을 고정한다
    OPENROUTER_URL: ClassVar[str] = "https://openrouter.ai/api/alpha/decisions"
    OPENROUTER_MODEL: ClassVar[str] = "typesafe/jev-1.13"
    TIMEOUT_S: ClassVar[float] = 15.0
    MAX_QUESTIONS_PER_CALL: ClassVar[int] = 32

    def __init__(
        self,
        api_key: str,
        *,
        threshold: float = JEV_THRESHOLD_DEFAULT,
        client: httpx.Client | None = None,
        url: str = URL,
        model: str = MODEL,
    ) -> None:
        """판정기를 만든다.

        Args:
            api_key: TypeSafe 또는 OpenRouter API 키.
            threshold: 통과로 보는 확률의 최솟값.
            client: 테스트에서 주입하는 HTTP 클라이언트.
            url: 판정 엔드포인트.
            model: 요청 본문의 모델 이름.

        Raises:
            ValueError: api_key가 비었을 때.
        """
        if not api_key or not api_key.strip():
            msg = f"{KEY_ENV}가 비었다"
            raise ValueError(msg)
        self._api_key = api_key.strip()
        self.threshold = threshold
        self.url = url
        self.model = model
        self._client = client or httpx.Client()

    def judge(self, state: str, questions: Sequence[Noul]) -> list[Verdict]:
        """state를 근거로 questions 각각을 판정한다.

        Args:
            state: 판정 근거 본문.
            questions: 판정할 질문들.

        Returns:
            questions와 같은 순서의 판정. 실패는 passed=False로 담는다.
        """
        verdicts: list[Verdict] = []
        step = self.MAX_QUESTIONS_PER_CALL
        for start in range(0, len(questions), step):
            verdicts.extend(self._judge_chunk(state, questions[start : start + step]))
        return verdicts

    def _judge_chunk(self, state: str, questions: Sequence[Noul]) -> list[Verdict]:
        body = {
            "model": self.model,
            "state": state,
            "questions": {
                q.name: {
                    "type": "noul",
                    "instructions": q.instructions,
                    "criteria": {"true": q.true, "false": q.false},
                }
                for q in questions
            },
        }
        try:
            response = self._client.post(
                self.url,
                json=body,
                headers={"Authorization": "Bearer " + self._api_key},
                timeout=self.TIMEOUT_S,
            )
            response.raise_for_status()
            answers = response.json().get("answers")
        except httpx.HTTPError, ValueError, AttributeError:
            return [_failed(q.name, "transport_error") for q in questions]
        if not isinstance(answers, dict):
            return [_failed(q.name, "transport_error") for q in questions]
        return [
            _read_answer(answers.get(q.name), q.name, self.threshold) for q in questions
        ]

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> JevDecider:
        """환경에서 키와 임계값을 읽어 만든다.

        TYPESAFE_API_KEY가 있으면 TypeSafe를, 없고 OPENROUTER_API_KEY가 있으면
        OpenRouter를 쓴다.

        Args:
            environ: 환경변수 사전.

        Returns:
            판정기.

        Raises:
            DeciderError: 키가 없거나 임계값이 (0, 1] 밖일 때.
                메시지는 변수 이름만 말한다.
        """
        endpoint: dict[str, str] = {}
        key = environ.get(KEY_ENV, "").strip()
        if not key:
            key = environ.get(OPENROUTER_KEY_ENV, "").strip()
            endpoint = {"url": cls.OPENROUTER_URL, "model": cls.OPENROUTER_MODEL}
        if not key:
            msg = f"{KEY_ENV} 또는 {OPENROUTER_KEY_ENV}가 설정되지 않았다"
            raise DeciderError(msg)
        raw = environ.get(PLAN_GATE_JEV_THRESHOLD, "").strip()
        threshold = JEV_THRESHOLD_DEFAULT
        if raw:
            try:
                threshold = float(raw)
            except ValueError:
                threshold = math.nan
            if not 0.0 < threshold <= 1.0:  # NaN도 여기서 걸린다
                msg = f"{PLAN_GATE_JEV_THRESHOLD}는 0보다 크고 1 이하인 수여야 한다"
                raise DeciderError(msg)
        return cls(key, threshold=threshold, **endpoint)


@dataclass
class FakeDecider:
    """대본으로 답하는 판정기. 테스트와 가짜 모델 실행에 쓴다.

    script는 질문 이름 또는 접두사에서 확률로. "J6"는 "J6:..." 전부에 맞는다.
    값이 None이면 그 질문은 transport_error다.
    """

    script: Mapping[str, float | None] | None = None
    default: float = 1.0
    threshold: float = JEV_THRESHOLD_DEFAULT
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def _probability(self, name: str) -> float | None:
        script = self.script or {}
        if name in script:
            return script[name]
        return script.get(name.split(":", 1)[0], self.default)

    def judge(self, state: str, questions: Sequence[Noul]) -> list[Verdict]:
        """대본의 확률로 판정한다.

        Args:
            state: 판정 근거 본문. calls에 기록만 한다.
            questions: 판정할 질문들.

        Returns:
            questions와 같은 순서의 판정.
        """
        self.calls.append((state, tuple(q.name for q in questions)))
        verdicts = []
        for q in questions:
            probability = self._probability(q.name)
            if probability is None:
                verdicts.append(_failed(q.name, "transport_error"))
            else:
                verdicts.append(_verdict(q.name, probability, self.threshold))
        return verdicts


def _state(*parts: str) -> str:
    kept = [p for p in parts if p]
    text = "\n\n".join(kept)
    if len(text) <= STATE_MAX_CHARS:
        return text
    # 긴 절 하나가 나머지를 밀어내지 않게 각 부분을 같은 몫으로 자른다
    share = (STATE_MAX_CHARS - 2 * (len(kept) - 1)) // len(kept)
    return "\n\n".join(p[:share] for p in kept)


def _section(plan: Plan, title: str) -> str:
    return f"## {title}\n{plan.sections.get(title, '').strip()}"


def _targets(plan: Plan) -> str:
    return "## 수정 대상(targets)\n" + "\n".join(f"- {t}" for t in plan.targets)


def question_j1(plan: Plan) -> tuple[str, Noul]:
    """완료 조건이 실행해서 확인할 수 있는가.

    Args:
        plan: 판정할 계획.

    Returns:
        (state, 질문).
    """
    state = _state(
        _section(plan, "완료 조건"),
        f"## 테스트 명령\n{plan.test_command}",
        _section(plan, "요구사항"),
    )
    return state, Noul(
        name="J1",
        instructions="계획의 완료 조건을 명령 실행이나 테스트로 확인할 수 있는가?",
        true="완료 조건마다 실행해서 참 거짓을 가릴 방법"
        "(테스트, 명령, 관찰할 출력)이 있다.",
        false="완료 조건이 '잘 동작한다'처럼 모호하거나, 실행으로 확인할 방법이 없다.",
    )


def question_j2(plan: Plan) -> tuple[str, Noul]:
    """작업 범위가 요구사항 안에 있는가.

    Args:
        plan: 판정할 계획.

    Returns:
        (state, 질문).
    """
    state = _state(
        _section(plan, "작업 범위"),
        _targets(plan),
        _section(plan, "요구사항"),
    )
    return state, Noul(
        name="J2",
        instructions="계획의 작업 범위와 수정 대상이 "
        "요구사항이 필요로 하는 것 안에 있는가?",
        true="모든 작업과 수정 대상이 요구사항을 이루는 데 필요하다.",
        false="요구사항에 없는 기능, 리팩터링, 파일 수정이 범위에 들어 있다.",
    )


def question_j3(plan: Plan) -> tuple[str, Noul]:
    """작업 순서와 테스트 방법이 수정 대상에 대응하는가.

    Args:
        plan: 판정할 계획.

    Returns:
        (state, 질문).
    """
    state = _state(
        _section(plan, "작업 순서"),
        _targets(plan),
        f"## 테스트 명령\n{plan.test_command}",
        _section(plan, "완료 조건"),
    )
    return state, Noul(
        name="J3",
        instructions="작업 순서와 테스트 방법이 수정 대상(targets)에 대응하는가?",
        true="수정 대상마다 그것을 고치는 단계가 있고, "
        "테스트 명령이 그 변경을 검사한다.",
        false="단계가 없는 수정 대상이 있거나, "
        "수정 대상 밖의 파일을 고치는 단계가 있거나, "
        "테스트 명령이 변경과 무관하다.",
    )


def question_j4(plan: Plan, tool_name: str, summary: str) -> tuple[str, Noul]:
    """이 호출이 승인된 계획 범위 안인가.

    Args:
        plan: 승인된 계획.
        tool_name: 호출할 도구 이름.
        summary: 경로와 명령만 담은 호출 요약.

    Returns:
        (state, 질문).
    """
    state = _state(
        f"## 도구 호출\n{tool_name}: {summary}",
        _targets(plan),
        _section(plan, "작업 범위"),
        _section(plan, "요구사항"),
        _section(plan, "작업 순서"),
    )
    return state, Noul(
        name="J4",
        instructions="이 도구 호출이 승인된 계획의 범위 안에 있는가?",
        true="호출이 계획의 작업 범위와 작업 순서를 수행하는 데 필요하다.",
        false="호출이 계획에 없는 파일을 바꾸거나, 계획과 무관하거나, "
        "되돌리기 어려운 일을 한다.",
    )


def question_j5(request: str, exploration: str) -> tuple[str, Noul]:
    """이 요청이 코드 변경을 필요로 하는가.

    Args:
        request: 사용자의 요청문.
        exploration: 탐색 서브에이전트의 요약.

    Returns:
        (state, 질문).
    """
    state = _state(f"## 요청\n{request}", f"## 탐색 결과\n{exploration}")
    return state, Noul(
        name="J5",
        instructions="이 요청을 처리하려면 저장소의 파일을 바꿔야 하는가?",
        true="요청이 코드, 설정, 문서 파일의 생성, 수정, 삭제를 요구한다.",
        false="요청이 질문, 설명, 조사처럼 파일을 바꾸지 않고 답할 수 있는 것이다.",
    )
