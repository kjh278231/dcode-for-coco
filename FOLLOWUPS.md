# M8 이후 작업

`dcode-a`(M7 `4235bca` 릴리스본)를 실제 작업에 써 보다가 나온 문제다. M8을 끝낸 뒤, M9 전후에 처리한다. 처리하면 PROGRESS.md에 결과를 적고 여기서 지운다. F1, F3과 F2의 조사·문서화는 끝났다(PROGRESS.md "F1–F3" 절, DECISIONS O17, O18). F5(계획 전 셸 판정 2차)도 끝났다(PROGRESS.md "F5" 절, O19, O20). F7(계획 전 execute 읽기 전용 샌드박스)도 끝났다(PROGRESS.md "F7" 절, O26~O32). F9(실사용 thread 01a1d30a 검토 반영)도 끝났다(PROGRESS.md "F9. 실사용 검토 반영" 절, O34~O38). 남은 일은 아래 F7, F9 절.

## F2. auto 모드 분류기가 시간 초과로 호출을 거부한다 (남은 일)

- 끝난 것: 원인 조사(기본 20초 로컬 마감, 분류기 = 주 모델), auto와 게이트의 순서, 설정 방법을 SPEC 14장에 적었다. 코드는 바꾸지 않았다(O18).
- 남은 것:
  1. 20초 초과를 재현하지 못했다. 남은 분류기 요청을 같은 모델로 다시 보내면 0.7~4.9초, 시간 초과 난 호출을 재구성한 요청은 3.5~7.9초였다(실제 요청은 남지 않아 재구성). 다시 보이면 그때의 Langfuse/LangSmith `auto_classifier_review` 구간 시간과 공급자 오류(429, 재시도)를 본다. 자주 나면 `[models].auto_classifier_timeout`을 올리거나 `[models].auto_classifier`로 별도 모델을 지정한다(사용자 `~/.deepagents/config.toml`. 이 작업에서는 고치지 않았다).
  2. 게이트가 확실히 거부할 호출(승인 전, 읽기 전용이 아닌 `execute`)도 auto 분류기를 거친다. 비용과 지연이 들고, 분류기가 거부하면 게이트의 안내 문장(F1) 대신 `Auto denied [...]`가 모델에 간다. 고치려면 업스트림 `auto_mode.py` `awrap_model_call`에서 그런 호출을 분류기 없이 게이트로 넘겨야 한다(SPEC 13장 절차, baseline). 게이트 허용을 분류기 허용으로 넘기는 것은 하지 않는다(분류기 우회로가 된다).

## F4. 업스트림 읽기 전용 판정에 남은 우회 (F1 리뷰에서 발견)

- [F7] 계획 전 `execute`는 이제 샌드박스에서 돈다. 아래 우회는 샌드박스를 못 쓰는 환경(탐침 실패, `DEEPAGENTS_CODE_PLAN_SANDBOX=0`, 원격 샌드박스), 승인 뒤 J4 없이 통과하는 `read_only_shell`, auto 모드 결정적 허용에만 남는다.

- 본 것: 업스트림 `config.is_shell_command_allowed`는 `cat () ( touch x ) && cat`(허용 이름의 함수 정의)을 허용하고, `auto_mode._fixed_repo_command_allowed`는 `git diff *`를 허용한다(glob이 `--output=x` 파일 이름을 옵션으로 펼쳐 쓴다). [F5] 같은 함수가 `git log {--output=f,HEAD}`(중괄호 펼침), `git log $@--output=f`(`$@`, `$1`은 업스트림 `contains_dangerous_patterns`가 안 막음)도 허용한다(임시 저장소에서 파일이 써짐). 계획 게이트(`policy.is_read_only_shell`)에서는 막았지만 업스트림의 비대화형 `--shell-allow-list recommended` 자동 승인과 auto 모드의 결정적 허용은 그대로다. `hostname <이름>`도 허용 목록에 있어 root로 돌면 호스트 이름을 바꾼다(게이트에도 남음, 쓰기 파일은 아님).
- 할 일: 업스트림에 고치려면 SPEC 13장 절차와 baseline. 게이트 쪽 `hostname` 인자 거부는 필요해지면 `_read_only_chain`과 2)에 같이 넣는다.

## F6. 계획 전 git 판정 확장의 남은 일

- [F7] 계획 전 git은 이제 샌드박스에서 돌아 아래 판정 표는 샌드박스를 못 쓸 때와 승인 뒤에만 쓰인다. 첫 항목(거부 문장으로 재시도가 멈추는가)은 그 경우에만 의미가 있다.

- 실제 모델(glm-5.3-flash)이 하위 명령 이름이 든 새 거부 문장을 보고 git 형태를 바꿔 재시도하는 일을 멈추는지 실사용에서 본다.
- auto 모드 결정적 허용(업스트림 `_GIT_READ_OPTIONS`)에는 묶음과 추가 하위 명령이 없어 분류기로 간다. 넓히려면 SPEC 13장 절차와 baseline.
- rev-list `-8`은 업스트림 `_git_option_allowed`가 log에서만 받아 거부된다(`-n 8`은 받음). 실사용에서 나오면 우리 루프에서 따로 받는다.
- `git log -1 … | cat`이 실사용에서 거부된 원인을 체크포인트 원문으로 확인한다(문자열 자체는 F5부터 허용).
- branch `--format=%(signature)`, blame textconv, 업스트림 `log --format=%G?`는 저장소·사용자 설정의 `gpg.program`, textconv를 돌린다. 루트 설정을 믿는 전제(O17)가 바뀌면 같이 다시 본다.

## F7. 계획 전 execute 읽기 전용 샌드박스의 남은 일

- 일반 Ubuntu 23.10+(AppArmor `apparmor_restrict_unprivileged_userns=1`)에서 탐침이 실패해 정적 판정으로 넘어가는지 확인한다. 넘어가면 동작은 F6 그대로다. 샌드박스를 쓰려면 AppArmor 프로필이 필요하다.
- 실사용에서 모델이 "Read-only file system"을 보고 같은 쓰기를 반복하는지 본다. 샌드박스 안 실패는 `gate_denies`로 세지 않는다(O28).
- 비밀 읽기: 계획 전에도 `~/.ssh`, `.env`를 읽을 수 있다. 막으려면 런처에서 그 경로에 tmpfs를 올린다. (같은 uid 프로세스의 `/proc/<pid>/environ`은 리뷰 뒤 PID 네임스페이스로 가렸다.)
- 프로젝트 `.env`가 `DEEPAGENTS_CODE_PLAN_SANDBOX=0`(정적 판정으로 내려감)이나 `DEEPAGENTS_CODE_PLAN_GATE=0`(게이트 꺼짐, F7 전부터)을 넣을 수 있다. `read_project_dotenv` 기본값이 켜짐이고 `config._DOTENV_DENIED_ENV_KEYS`에 둘 다 없다. 넣으면 전역 `~/.deepagents/.env`에서도 못 쓰게 되니 프로젝트 파일만 막을지 정한다(업스트림 수정, baseline 필요).
- 장치 파일: 읽기 전용 마운트는 장치 쓰기를 막지 않는다. `/dev/dxg`(WSL GPU)가 샌드박스 안에서 열린다. 지속되는 부작용은 찾지 못했다.
- 명령이 `-`로 시작하면 `sh -c -x`처럼 셸 옵션으로 읽혀 실패한다(업스트림 `shell=True`와 같다. 탈출은 아님).
- aarch64: seccomp 번호와 arch 값을 더하면 쓸 수 있다. 지금은 탐침 전에 정적 판정으로 넘어간다.
- PreToolUse 훅은 감싼 명령을 본다(O27). 훅 사용자가 생기면 원래 명령을 따로 넘길지 본다.

## F9. 실사용 검토 반영의 남은 일

- 끝난 것: 리뷰어가 게이트 절을 요구하던 문제, 상한에서 남은 의견이 승인 화면에 안 보이던 문제, 계획 자기완결과 사용자 결정 기록 규칙, explorer 먼저 안내, 승인 전 시안 실행·테스트 재실행 줄이기 안내, 승인 뒤 J4가 흔들리던 읽기 탐침(샌드박스로), 샌드박스 안 pytest 캐시 EROFS 경고, 보호 폴더를 읽기만 하는 셸 명령 거부.
- 남은 것:
  1. 프롬프트 규칙의 효과는 실제 모델(glm-5.3-flash)로 다시 돌려 봐야 안다. 볼 지표: 첫 `task(explorer)`까지의 호출 수, 승인 전 python 실행 수, 변경 없이 다시 돈 pytest 수, `complete_plan` 직전 같은 명령, 리뷰 상한 도달 횟수.
  2. 대화에서 받은 사용자 결정은 요구사항 본문의 `(사용자 결정: ...)`일 뿐이라 작업 기록의 "사용자 결정"(Memory)에는 안 들어간다(O35). 필요하면 작업 기록이 요구사항에서 이 표시를 뽑아 따로 적게 한다.
  3. 비대화 "승인"은 미해결 리뷰 의견이 남아도 그대로 승인한다(O37). 막을지는 실사용을 보고 정한다.
  4. 승인 뒤 샌드박스로 돈 execute는 거부로 세지 않아 7.2 임계값(`cg.jev_denies`)에 안 잡힌다. `cg.gate.sandbox` 기록 수를 보고 신호로 쓸지 정한다.

## M9. 보정과 README의 남은 일

- 자기 개선(T8)의 실제 모델 경로: 함정 과제 두 번 → `/improve` → `evalsuite run --improvement`(에이전트 실행 18회) → `/improve apply`를 한 번도 끝까지 돌리지 않았다. M8에서 함정 과제가 7.2 임계값을 넘는 신호를 만들지 못했다. 사용자 결정(O39)으로 다음 자기 개선 작업(`docs/design/self_improvement_v2.md`)에서 과제·임계값·검증과 함께 다시 본다.
- T2(질문에 계획 없이 답), T6(모호한 요청에 질문 화면)은 실제 모델로 돌리지 않았다(O39). 가짜 모델 테스트만 있다. 실제 모델이 모호한 요청에서 `open_questions`를 내는지는 모른다.
- 리뷰어 의견 반영 왕복은 T7에서 한 번 봤다(1회차 의견 → 재제출 → 2회차 의견 없음). T3에서는 리뷰어가 의견을 내지 않았다.
- Jev 보정 사례는 분명한 편이라 holdout 95/96이 실제 계획의 정확도를 뜻하지 않는다. 실사용 계획(`.deepagents/plans/`)에서 사례를 뽑아 라벨을 붙이면 더 어려운 묶음을 만들 수 있다. Sonnet급 생성 모델로 다시 만드는 것도 남았다(O40).
- 계획 frontmatter의 `trace_ids`를 채우는 코드가 없다(T3, T7 계획 모두 `[]`). 계획에서 trace로 가는 길은 `/runs`·`/trace`(세션 id)뿐이다. 채우려면 `submit_plan`/`complete_plan`이 실행의 `cg_trace_id`를 더해야 한다.
- 계획 요구사항의 `(사용자 결정: ...)` 표시를 모델이 요청문 속 지시(테스트 명령)에도 붙였다(T3). F9 프롬프트 규칙의 효과는 더 봐야 한다.
- 평가 과제와 보정 사례 파일은 wheel의 포함 목록(`.py`, `.md`)에 없다. `release.sh`(wheel 설치)의 `dcode-a`에서는 보정·평가 명령이 파일을 못 찾는다. 필요하면 `pyproject.toml`의 include에 `*.jsonl`, `*.toml`, `*.patch`를 더한다(업스트림 파일, baseline 필요).
