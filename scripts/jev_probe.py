"""실제 Jev에 질문 하나를 보내 원본 응답 형태와 Verdict를 출력한다 (M2 검사).

사용법:
    libs/code/.venv/bin/python scripts/jev_probe.py

키는 dcode와 같은 방식으로 셸 환경, 현재 폴더에서 위로 찾은 프로젝트 `.env`,
`~/.deepagents/.env` 순서로 찾는다. TYPESAFE_API_KEY가 없으면 OPENROUTER_API_KEY를 쓴다.
키 값은 출력하지 않는다. 응답 본문은 키를 담지 않으므로 그대로 보여준다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from deepagents_code.assistant.decider import JevDecider, Noul

# dcode의 .env 규칙을 그대로 쓰려고 비공개 함수를 가져온다
from deepagents_code.config import _dotenv_environment  # noqa: PLC2701

QUESTION = Noul(
    name="J1",
    instructions="계획의 완료 조건을 명령 실행이나 테스트로 확인할 수 있는가?",
    true="실행해서 확인할 방법이 있다.",
    false="확인할 방법이 없다.",
)
STATE = "## 완료 조건\n`pytest tests/test_login.py`가 통과한다."


def main() -> None:
    """JevDecider로 한 번 판정하고 그 호출의 원본 응답을 보여준다."""
    environ = _dotenv_environment(start_path=Path.cwd(), environ=os.environ)
    decider = JevDecider.from_environment(environ)
    print("엔드포인트:", decider.url, "모델:", decider.model)
    raw: list[httpx.Response] = []
    client = httpx.Client(event_hooks={"response": [raw.append]})
    decider._client = client  # 원본 응답을 엿보려고 갈아 끼운다
    [verdict] = decider.judge(STATE, [QUESTION])
    if not raw:  # 연결 자체가 실패했다
        print("응답 없음. Verdict:", verdict)
        return
    response = raw[0]
    response.read()
    print("HTTP", response.status_code)
    try:
        data = response.json()
    except ValueError:
        print("JSON 아님:", response.text[:500])
    else:
        print("최상위 키:", sorted(data) if isinstance(data, dict) else type(data))
        answers = data.get("answers") if isinstance(data, dict) else None
        answer = answers.get("J1") if isinstance(answers, dict) else None
        print("answers.J1:", json.dumps(answer, ensure_ascii=False))
        if isinstance(answer, dict):
            print("noul 형:", type(answer.get("noul")).__name__)
        print("usage:", json.dumps(data.get("usage"), ensure_ascii=False))
    print("Verdict:", verdict)


if __name__ == "__main__":
    main()
