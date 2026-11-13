# M8 이후 작업

`dcode-a`(M7 `4235bca` 릴리스본)를 실제 작업에 써 보다가 나온 문제다. M8을 끝낸 뒤, M9 전후에 처리한다. 처리하면 PROGRESS.md에 결과를 적고 여기서 지운다.

## F1. 계획 전 읽기 전용 셸 명령이 거부된다

- 본 것 (2026-11-13, `~/workspace/deepagents-coco`에서 coco 배너 요청): `echo probe`, `ls <경로> && head -60 <파일>`, `cd <루트> && git log --oneline -3 2>&1 | head -5`가 모두 `no_approved_plan`("승인된 계획이 없다…")으로 거부됐다. 모델은 탐색 서브에이전트나 `read_file`로 가지 않고 `execute`만 바꿔 가며 반복했다.
- 원인: `assistant/policy.py` `is_read_only_shell`이 업스트림 `RECOMMENDED_SAFE_SHELL_COMMANDS`(`config.py` `is_shell_command_allowed`)와 고정 저장소 명령만 허용한다. `echo`, `cd … &&` 조합, `2>&1` 같은 리다이렉트는 "확신 없음"으로 떨어진다. SPEC G3은 `ls` 하나만 단언한다.
- 할 일:
  1. 거부 메시지가 다음 행동을 알려 주게 한다. 예: "읽기는 read_file, glob, grep이나 탐색 서브에이전트로 하라".
  2. 허용 범위를 넓힐지 검토한다. 넓히면 게이트를 우회하는 새 경로가 생기는지(SPEC 13.3) 따져야 한다. 쓰기가 섞인 조합 명령(`cd x && rm y`, `>` 리다이렉트)은 계속 막혀야 한다.
  3. 같은 사유로 연속 거부되면 멈추는지, 반복 실패 신호(`cg.repeat_failures`)로 잡히는지 확인한다.
- 검사: 위 세 명령을 대본으로 한 가짜 모델 테스트, 쓰기 조합 명령은 여전히 거부되는지 확인하는 테스트.

## F2. auto 모드 분류기가 시간 초과로 호출을 거부한다

- 본 것: 같은 실행에서 `execute`(mascot 폴더의 `coco.sh`, `coco_motion.py` 미리 보기)가 `Auto denied [classifier unavailable]: classifier model z-ai/glm-5.3-flash-ultrafast did not respond within 20s`로 거부됐다. 상태줄은 `auto` 모드였다.
- 위치: 업스트림 `auto_mode.py`(시간 초과 문구 약 869줄, 묶음 거부 약 250줄). 분류기가 메인 모델과 같은 모델을 쓴다.
- 할 일: 시간 초과가 모델이 느려서인지, 설정 때문인지(시간 제한, 분류기 모델 지정) 확인한다. 계획 게이트와 auto 모드가 겹칠 때 어느 쪽이 먼저 판단하는지 정리한다. 업스트림 수정이 필요하면 SPEC 13장 절차를 따른다.

## F3. 릴리스본 `dcode-a`가 시작할 때 자동 업데이트를 시도한다

- 본 것: 시작할 때 "Updating dcode from v0.2.5 to v0.2.7" 다음 "Unsupported install method"로 실패하고 v0.2.5로 계속 갔다. 성공하면 고정한 릴리스본이 업스트림으로 덮어써질 수 있다.
- 할 일: `scripts/release.sh`가 만든 실행 환경에서 자동 업데이트를 끈다. 후보는 `DEEPAGENTS_CODE_AUTO_UPDATE`(`_env_vars.py` `AUTO_UPDATE`). 링크 대신 그 값을 넣는 감싸기 스크립트로 바꾸는 방법이 있다.
