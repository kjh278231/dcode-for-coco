# M8 이후 작업

`dcode-a`(M7 `4235bca` 릴리스본)를 실제 작업에 써 보다가 나온 문제다. M8을 끝낸 뒤, M9 전후에 처리한다. 처리하면 PROGRESS.md에 결과를 적고 여기서 지운다. F1, F3과 F2의 조사·문서화는 끝났다(PROGRESS.md "F1–F3" 절, DECISIONS O17, O18). F5(계획 전 셸 판정 2차)도 끝났다(PROGRESS.md "F5" 절, O19, O20).

## F2. auto 모드 분류기가 시간 초과로 호출을 거부한다 (남은 일)

- 끝난 것: 원인 조사(기본 20초 로컬 마감, 분류기 = 주 모델), auto와 게이트의 순서, 설정 방법을 SPEC 14장에 적었다. 코드는 바꾸지 않았다(O18).
- 남은 것:
  1. 20초 초과를 재현하지 못했다. 남은 분류기 요청을 같은 모델로 다시 보내면 0.7~4.9초, 시간 초과 난 호출을 재구성한 요청은 3.5~7.9초였다(실제 요청은 남지 않아 재구성). 다시 보이면 그때의 Langfuse/LangSmith `auto_classifier_review` 구간 시간과 공급자 오류(429, 재시도)를 본다. 자주 나면 `[models].auto_classifier_timeout`을 올리거나 `[models].auto_classifier`로 별도 모델을 지정한다(사용자 `~/.deepagents/config.toml`. 이 작업에서는 고치지 않았다).
  2. 게이트가 확실히 거부할 호출(승인 전, 읽기 전용이 아닌 `execute`)도 auto 분류기를 거친다. 비용과 지연이 들고, 분류기가 거부하면 게이트의 안내 문장(F1) 대신 `Auto denied [...]`가 모델에 간다. 고치려면 업스트림 `auto_mode.py` `awrap_model_call`에서 그런 호출을 분류기 없이 게이트로 넘겨야 한다(SPEC 13장 절차, baseline). 게이트 허용을 분류기 허용으로 넘기는 것은 하지 않는다(분류기 우회로가 된다).

## F4. 업스트림 읽기 전용 판정에 남은 우회 (F1 리뷰에서 발견)

- 본 것: 업스트림 `config.is_shell_command_allowed`는 `cat () ( touch x ) && cat`(허용 이름의 함수 정의)을 허용하고, `auto_mode._fixed_repo_command_allowed`는 `git diff *`를 허용한다(glob이 `--output=x` 파일 이름을 옵션으로 펼쳐 쓴다). [F5] 같은 함수가 `git log {--output=f,HEAD}`(중괄호 펼침), `git log $@--output=f`(`$@`, `$1`은 업스트림 `contains_dangerous_patterns`가 안 막음)도 허용한다(임시 저장소에서 파일이 써짐). 계획 게이트(`policy.is_read_only_shell`)에서는 막았지만 업스트림의 비대화형 `--shell-allow-list recommended` 자동 승인과 auto 모드의 결정적 허용은 그대로다. `hostname <이름>`도 허용 목록에 있어 root로 돌면 호스트 이름을 바꾼다(게이트에도 남음, 쓰기 파일은 아님).
- 할 일: 업스트림에 고치려면 SPEC 13장 절차와 baseline. 게이트 쪽 `hostname` 인자 거부는 필요해지면 `_read_only_chain`과 2)에 같이 넣는다.

## F6. 계획 전 git 판정 확장의 남은 일

- 실제 모델(glm-5.3-flash)이 하위 명령 이름이 든 새 거부 문장을 보고 git 형태를 바꿔 재시도하는 일을 멈추는지 실사용에서 본다.
- auto 모드 결정적 허용(업스트림 `_GIT_READ_OPTIONS`)에는 묶음과 추가 하위 명령이 없어 분류기로 간다. 넓히려면 SPEC 13장 절차와 baseline.
- rev-list `-8`은 업스트림 `_git_option_allowed`가 log에서만 받아 거부된다(`-n 8`은 받음). 실사용에서 나오면 우리 루프에서 따로 받는다.
- `git log -1 … | cat`이 실사용에서 거부된 원인을 체크포인트 원문으로 확인한다(문자열 자체는 F5부터 허용).
- branch `--format=%(signature)`, blame textconv, 업스트림 `log --format=%G?`는 저장소·사용자 설정의 `gpg.program`, textconv를 돌린다. 루트 설정을 믿는 전제(O17)가 바뀌면 같이 다시 본다.
