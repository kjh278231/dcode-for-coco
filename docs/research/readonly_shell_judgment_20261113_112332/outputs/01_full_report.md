# 코딩 에이전트의 읽기 전용 셸 판정과 dcode 권고 (전체 보고서, 압축판)

조사일 2026-11-13 · 대상 독자: dcode 개발자 · 세션 폴더는 이 문서의 상위 폴더

## 1. 질문과 방법

질문: 2025년부터 2026년까지 코딩 에이전트는 셸 명령을 승인 없이 돌려도 되는지, 곧 읽기 전용 여부를 어떻게 판단하는가. 축은 (1) 정적 판정, (2) OS 샌드박스, (3) 승인 모드와 plan 모드, (4) 읽기 전용 단계의 `python -c`, (5) 같은 기간의 우회와 CVE다. 대상 도구 14개의 목록은 7장 표에 있다.

방법: 5개 리서치 에이전트가 1차 출처(공식 문서, 소스 코드, 릴리스 노트, GHSA/NVD)를 원문 인용과 함께 모았고 (`artifacts/agent_results/`), 오케스트레이터가 반증·확장 검색 17회와 WebFetch 확인 3회를 돌렸다 (`artifacts/expansion_log.md`). dcode 권고에 쓰이는 동작은 이 WSL2 머신에서 직접 실행해 확인했다 (`artifacts/exec/`). 주장 64건 중 29건이 게이트를 통과했다. 원문 스냅샷 엔진(insane-search)이 설치돼 있지 않아 날짜·버전·CVE가 들어간 고위험 주장은 전부 미확정으로 남았다. 이 장 이후 본문은 통과한 주장만 단정하고, 도구별 세부는 7장 미확정 부록에 둔다.

## 2. 업계 현황: 정적 목록에서 OS 샌드박스로

**정적 허용 목록은 반복해서 뚫렸다.** 독립 연구자들은 허용된 바이너리의 실행 플래그를 이용해 안전 명령 목록을 우회했다. 예는 rg --pre, sort --compress-program, git 옵션 축약, go test -exec다 (clm_030; src_e01, src_a08, src_b14). Trail of Bits는 샌드박스 없는 안전 명령 허용 목록은 근본적으로 결함이 있다고 보고 샌드박스를 1차 통제로 권한다 (clm_031; src_e01, src_e02).

**벤더도 정적 규칙을 보안 경계로 보지 않는다.** Microsoft, Cursor, Anthropic 문서는 자동 승인 규칙이나 분류기가 보안 경계가 아니라고 명시한다 (clm_061; src_c12, src_c07, src_a01). 정적 분석이 남은 곳에서는 해석·분류할 수 없는 명령을 자동 승인하지 않고 묻거나 막는 쪽으로 수렴했다. Claude Code, Gemini CLI, VS Code, Cursor가 그렇다 (clm_062; src_a01, src_c01, src_c13, src_c11). Claude Code 2.1.x의 Bash 권한 검사는 tree-sitter 파서를 쓴다 (clm_016; src_a06, src_a11).

**실행 경로는 OS 샌드박스로 옮겨 갔다.** Codex와 Cursor는 정적 안전 명령 판정 대신 샌드박스 안 실행을 기본 경로로 삼는다 (clm_063; src_b01, src_b06, src_c07, src_e08). Codex의 Linux 샌드박스는 bubblewrap(`--ro-bind / /`)과 seccomp를 주 경로로 쓴다 (clm_022; src_b04, src_b15). Claude Code의 OS 샌드박스는 macOS는 Seatbelt, Linux와 WSL2는 bubblewrap을 쓰지만 기본값은 꺼짐이다 (clm_010; src_a03, src_a04, src_a12).

**git은 읽기 명령도 코드를 실행할 수 있다.** 저장소 로컬 git 설정(core.fsmonitor, core.hooksPath 등)은 git status 같은 읽기 명령에서도 임의 프로그램을 실행시킬 수 있고, 여러 벤더가 이를 취약점으로 다뤘다 (clm_060; src_b02, src_c17, src_c08, src_b16, src_b19, src_x01). 우리 정책의 `git -C <루트>` 허용도 같은 위험 위에 서 있다.

## 3. plan 단계와 `python -c`

plan 단계에서 셸을 안전하게 만드는 방식은 세 갈래다 (clm_078; src_d02, src_d06, src_c02, src_d03, src_d10, src_b06).

| 방식 | 사례 | `python -c` 결과 |
|---|---|---|
| 셸 제거 | OpenHands planning 프리셋, Roo Architect/Ask, Gemini plan 기본값 | 실행 불가 |
| 항상 묻기 | Aider, Continue의 `-c` 규칙 | 사람이 승인 |
| OS 샌드박스 | OpenHands Docker, Codex read-only | 쓰기를 커널이 막음. 승인 없이 돌리는지는 도구마다 다르다(7장) |

Continue의 터미널 보안 평가기는 인터프리터 `-c`를 항상 권한 요청 대상으로 둔다 (clm_076; src_d10, src_d11). 그리고 Claude Code plan 모드의 셸 명령은 bypass 권한을 쓸 수 있는 대화형 세션이면 검사 없이 돌고, auto 모드를 쓸 수 있으면(기본) 분류기가 판단하며, 둘 다 아니면 내장 읽기 전용 명령만 프롬프트 없이 돌고 나머지는 사용자에게 묻는다 (clm_012; src_a01, src_a02, src_a16). Codex Plan Mode는 프롬프트 지시(변경 금지)일 뿐이고, 샌드박스나 승인 정책을 바꾼다는 근거는 찾지 못했다 (clm_025; src_b13, src_b18). 정리하면, 검증된 범위 안에서는 인터프리터 `-c` 명령을 묻지 않고 돌리는 안전한 경로는 커널 수준 격리뿐이었다.

## 4. 이 머신에서 한 실험 (커널 6.6.87.2-microsoft-standard-WSL2, /bin/sh는 dash)

| # | 실험 | 결과 | 주장 |
|---|---|---|---|
| 1 | 커널 기능 | 비특권 사용자 네임스페이스와 Landlock ABI 3 동작, bubblewrap 미설치. Microsoft WSL2 커널 설정도 Landlock과 사용자 네임스페이스를 켜 둔다 | clm_001, clm_034 |
| 2 | Landlock 래퍼(ctypes 약 70줄) | `git status -sb`, `python -c 'import textual'`, `python -c print`은 성공 | clm_002 |
| 3 | 같은 래퍼, 쓰기 시도 | 리다이렉트, touch/rm/mkdir, 함수 정의 우회, `$(...)` 안 쓰기, `git log/diff --output`, `find -exec rm`, `sed -i`, python 쓰기가 모두 거부됨. /mnt/c와 /dev/shm도 막힘 | clm_003, clm_004 |
| 4 | Landlock의 빈틈 | chmod·mtime 변경, 경로 유닉스 소켓 connect, 미리 열린 fd로 쓰기, 네트워크는 통과. 커널 문서도 chmod/chown/utime 제한 불가와 열린 fd 미적용을 적는다 | clm_005, clm_032 |
| 5 | 읽기 전용 bind mount | chmod·touch는 EROFS로 막지만 유닉스 소켓 connect는 통과. 최상위만 remount하면 /dev/shm 같은 하위 마운트는 rw로 남음 | clm_006, clm_008 |
| 6 | WSL interop | Landlock 아래에서도 `cmd.exe`가 호스트에서 돌아 C:에 파일을 씀. `WSL_INTEROP`만 지워서는 안 막히고 /run/WSL을 tmpfs로 가리면 막힘 | clm_007 |
| 7 | `mount_setattr` 재귀 읽기 전용 | 네임스페이스 안에서 / 전체를 읽기 전용으로 만들면 내용 쓰기, chmod, touch가 /dev/shm과 /mnt/c까지 막히고, git status·import·`/dev/null`은 동작, 네트워크 차단 | clm_080 |
| 8 | 소켓 탈출 | 읽기 전용 마운트 아래에서 `systemd-run --user`가 사용자 버스로 밖에 파일을 만듦. /run을 가려도 `/mnt/wslg/run/user/UID`와 홈의 소켓 38개가 남아 같은 탈출이 됨 | clm_081, clm_083 |
| 9 | 최종 프로토타입 | 7에 /run tmpfs, /tmp 쓰기용 tmpfs, seccomp(AF_UNIX socket·io_uring 거부, x32 번호 차단), setsid를 더하면 읽기는 동작하고(`git status -sb` 출력이 안팎에서 같음) 쓰기, systemd-run, interop, 네트워크, herdr 소켓이 모두 막힘. 호출당 약 14ms | clm_082, clm_009 |

참고로 bubblewrap은 setuid 모드를 없애고 비특권 사용자 네임스페이스에 의존하며, 보호 수준은 넘긴 인자에 전적으로 달려 있다 (clm_035; src_e06, src_b04). 실험 5와 8이 그 예다. 읽기 전용 마운트만으로는 경로 유닉스 소켓 connect가 막히지 않는다 (clm_006, clm_081). 같은 이유로 bubblewrap을 쓰더라도 인자에 /run 가리기와 소켓 차단을 따로 넣어야 한다.

## 5. dcode 권고

### 5.1 결정

계획 승인 전 `execute`는 **정적 허용 목록 판정을 거치지 않고, 쓰기가 물리적으로 불가능한 샌드박스 안에서 그대로 실행**한다. 정적 판정(`is_read_only_shell`)은 런처를 띄울 수 없을 때의 대체 경로로 내린다. 근거는 2장(업계 수렴), 4장 실험 9(이 머신에서 동작 확인)이다. 이렇게 하면 지금 막히는 `git status -sb`와 `python -c "import textual"`이 그대로 돌고, 셸 함수 정의, git `--output=` 글롭, 재구성 인자 뒤 줄바꿈 같은 우회 부류는 판정 대상이 아니게 된다. 쓰기는 문자열이 아니라 커널이 막는다 (clm_003, clm_082).

### 5.2 최소 구현 (MVP)

1. `artifacts/exec/ro_launcher.py`를 dcode 확장 패키지 아래 모듈로 옮긴다. 의존성 없이 stdlib(`os.unshare`, ctypes)만 쓴다.
2. 계획 전 `execute`의 `subprocess.run(cmd, shell=True)`를 `subprocess.run([sys.executable, "-I", LAUNCHER, cmd], close_fds=True, timeout=...)`로 바꾼다. `preexec_fn`은 스레드가 있는 프로세스에서 안전하지 않으니 별도 프로세스로 띄운다. 런처가 `/bin/sh -c`로 실행하므로 dash 의미론은 그대로다.
3. 런처 설정 순서 (실험 9 그대로):
   - `unshare(CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWNET)`, uid/gid를 자기 자신으로 매핑 (root로 매핑하지 않아 git의 소유자 검사가 그대로 동작)
   - `/`를 `MS_REC|MS_PRIVATE`로 바꿔 호스트로 마운트가 새지 않게 함
   - `/run`에 tmpfs (systemd·dbus·컨테이너 데몬·WSL interop 소켓 가림)
   - `mount_setattr("/", AT_RECURSIVE, MOUNT_ATTR_RDONLY)` (하위 마운트까지 읽기 전용, 실험 5의 함정 회피)
   - `/tmp`에 크기 제한 tmpfs를 올리고 `TMPDIR=/tmp` (버리는 쓰기 공간)
   - seccomp: `socket(AF_UNIX)`와 `io_uring_setup`을 EPERM으로, x32 ABI 번호는 프로세스 종료로 (경로 소켓 탈출 차단, 실험 8)
   - `setsid()`로 제어 터미널을 떼어 dcode TUI에 키 입력을 밀어 넣는 TIOCSTI를 막음 (이 커널은 legacy_tiocsti=0이라 이미 막혀 있지만 방어선을 하나 더 둠)
   - 설정 중 하나라도 실패하면 명령을 돌리지 않고 종료 코드 125
4. 종료 코드 125면 지금의 정적 판정으로 넘어가되, 통과 못 하면 사용자 승인으로 보낸다. 실패해도 쓰기는 일어나지 않는다.
5. 테스트: 4장의 탐침 명령을 단위 테스트로 옮긴다. 읽기 성공 3종(`git status -sb`, `python -c 'import textual'`, `rg`/`find`)과 쓰기 실패 8종(리다이렉트, 함수 정의, `--output`, `find -exec`, `sed -i`, chmod, systemd-run, 유닉스 소켓)이다.

### 5.3 남길 정적 검사

- **계획 승인 뒤 경로의 판정과 승인 흐름**은 그대로 둔다. 샌드박스는 계획 전 단계에만 쓴다.
- **런처를 못 쓸 때의 대체 판정**으로 지금의 `is_read_only_shell`을 유지한다. 다만 저장소 로컬 git 설정은 git status 같은 읽기 명령에서도 임의 프로그램을 실행시킬 수 있으니 (clm_060) 대체 경로에서는 git을 빼거나 `-c core.fsmonitor= -c core.hooksPath=/dev/null`과 `safe.bareRepository=explicit`을 강제하는 쪽이 낫다.
- **보호 경로 언급 검사 같은 읽기 차단**은 비밀 유출이 걱정되면 남긴다. 샌드박스는 읽기를 막지 않는다.
- 해석하거나 분류할 수 없는 명령을 통과시키는 새 정적 규칙은 더 만들지 않는다. 업계가 그 방향을 버렸다 (clm_062, clm_063).

### 5.4 주요 위험

| 위험 | 내용 | 대응 |
|---|---|---|
| 남은 IPC | seccomp가 AF_UNIX만 막는다. SysV IPC와 다른 소켓 계열은 실험하지 않았다 | `CLONE_NEWIPC` 추가는 한 줄. 필요하면 소켓 계열 허용 목록으로 바꾼다 |
| PID 네임스페이스 없음 | 같은 사용자 프로세스에 시그널을 보낼 수 있다 (`kill`). Yama ptrace_scope=1이라 ptrace는 자손으로 제한된다 | `CLONE_NEWPID` + fork + 새 /proc. 구현 비용이 조금 더 든다 |
| 비밀 읽기 | 계획 전 단계도 `~/.ssh` 등을 읽을 수 있다. 네트워크가 끊겨 바로 유출되진 않지만 모델 컨텍스트로 들어간다 | 기존 보호 경로 검사 유지, 필요하면 해당 디렉터리에 tmpfs |
| 환경 의존 | 비특권 사용자 네임스페이스가 꺼졌거나 보안 모듈이 막는 환경(일부 컨테이너, WSL이 아닌 일부 배포판)에서는 설정이 실패한다 | 125 → 정적 판정 → 승인 |
| 프로젝트가 /tmp 아래 | /tmp에 tmpfs를 올리면 cwd가 가려진다 | 프로젝트 루트가 /tmp 아래면 쓰기용 tmpfs를 다른 경로에 올린다 |
| 아키텍처 | seccomp 필터는 x86_64만 처리하고 다른 아키텍처는 프로세스를 죽인다 | aarch64 지원 시 syscall 번호 추가 |
| 자원 남용 | 포크 폭탄, 긴 실행 | 기존 timeout 유지, 필요하면 `RLIMIT_NPROC` |

## 6. 결론

정적 판정으로 우회를 하나씩 막는 길은 앞선 도구들이 이미 걸어 본 길이고, 그 끝은 "해석 못 하면 묻기"와 OS 샌드박스였다 (clm_062, clm_063). dcode의 지원 대상은 리눅스와 WSL2뿐이라 이 머신에서 검증한 네임스페이스 런처 하나로 계획 전 쓰기 금지를 커널에 맡길 수 있다. 정적 판정은 대체 경로로만 남긴다.

## Confidence

게이트 결과: 검증 29건, 미확정 35건, 반증 0건 (미확정 비율 55%로 경고). 검증된 29건 중 13건은 이 머신에서 직접 실행한 증적이고, 나머지 16건은 서로 다른 조직의 출처 두 곳 이상으로 받쳐진다. 권고(5장)는 실행 증적과 다중 출처 주장에만 기대고 있다. 도구별 날짜·버전·CVE 같은 세부는 원문 스냅샷이 없어 미확정이다.

## Refuted

반증된 주장은 없다. 다만 에이전트 E의 조사는 질문 전제 두 가지를 바로잡았다. Trail of Bits가 `find -exec`로 우회한 것은 아니며(그 플래그는 막혀 있었다), Codex의 `git show --output` 우회는 CVE-2025-59532와 다른 건이다.

## 7. 미확정 주장 포함 도구별 비교 (Unresolved annex)

이 부록의 내용은 1차 출처 인용이 있지만 게이트를 통과하지 못했다. 이유는 대부분 독립 조직 출처가 하나뿐이거나(벤더 문서와 벤더 저장소는 한 조직), 고위험 주장인데 원문 스냅샷이 없어서다. 칸 끝의 `[미확정 주장 ID]` 표기는 그 칸이 기대는 미확정 주장이다. 단정하지 말고 원문(`artifacts/agent_results/`)을 확인한 뒤 써야 한다.

### 7.1 도구별 비교표

| 도구 | 정적 판정 | OS 샌드박스 | plan / 읽기 전용 모드 | `python -c` |
|---|---|---|---|---|
| Claude Code | 복합 명령을 나눠 모든 하위 명령이 허용돼야 통과, 해석 불가는 질문 [미확정 clm_011]. 모르는 AST 노드는 too-complex로 질문 [미확정 clm_019]. 2025년엔 Haiku 접두사 추출 [미확정 clm_015] | bwrap/Seatbelt, 기본 꺼짐 (검증 clm_010) | bypass 가능 세션은 무검사, 기본은 분류기, 그 외엔 내장 읽기 전용 목록만 무프롬프트 (검증 clm_012) | 목록에 없음. plan에서는 질문 또는 분류기, 샌드박스 자동 허용은 plan 밖에서만 [미확정 clm_013] |
| Codex | 안전 명령 목록을 2026-08 제거 [미확정 clm_020]. Landlock 경로는 유닉스 소켓 때문에 거부 [미확정 clm_028]. tree-sitter는 규칙 매칭용 [미확정 clm_024]. git 제외 이유는 저장소 설정 [미확정 clm_021] | bwrap `--ro-bind / /` + seccomp (검증 clm_022) | Plan Mode는 프롬프트 지시뿐 (검증 clm_025) | read-only + on-request면 샌드박스 안에서 무승인 실행. 공식 문서끼리 충돌 [미확정 clm_023] |
| Gemini CLI | tree-sitter로 나눠 검사, 리다이렉트·치환은 ask [미확정 clm_040]. known-safe 목록에 인터프리터 없음 [미확정 clm_042] | 기본 꺼짐, Seatbelt·docker·bwrap 선택 [미확정 clm_043] | plan에서 셸 기본 거부 [미확정 clm_041] | 추론상 plan에서 거부 |
| Cursor | 서버 측 파서(비공개) | Linux Landlock+seccomp, Windows는 WSL2 [미확정 clm_045, clm_037] | Auto-review가 목록 밖 명령을 샌드박스에서 실행 [미확정 clm_046] | 추론상 샌드박스 안 무프롬프트 |
| Copilot (VS Code) | tree-sitter로 모든 하위 명령 검사, python 규칙 없음 [미확정 clm_048] | 기본 꺼짐 [미확정 clm_048] | Plan 에이전트의 터미널 처리 근거 없음 | 승인 필요(추론) |
| Copilot CLI | 비공개 읽기 전용 분류기 | MXC 기본 꺼짐 | plan에서 파일 변경 명령은 강제 차단, 판단 불가 명령은 통과 [미확정 clm_049] | 승인 또는 LLM 검토(추론) |
| OpenHands | 선택적 정규식·LLM 위험 표시 | Docker 기본 [미확정 clm_070] | planning 프리셋에 터미널 없음 [미확정 clm_070] | planning에선 불가 |
| Aider | 없음 | 없음 | 제안 명령은 항상 질문, `--yes-always`도 거부 [미확정 clm_071] | 항상 질문 |
| Cline | plan에서 블랙리스트 가드 | 없음 | 코드와 문서가 충돌 [미확정 clm_072] | 가드가 못 잡는다고 코드 주석에 적힘 [미확정 clm_072] |
| Roo Code | parseCommand 분할 + 접두사 목록 [미확정 clm_073] | 없음 | Architect/Ask에 명령 도구 없음 [미확정 clm_073] | Architect/Ask에선 불가 |
| opencode | tree-sitter 분할 + 와일드카드 규칙 | 없음 | plan 에이전트가 bash 제한 안 함 [미확정 clm_074] | 기본 설정에서 무프롬프트 [미확정 clm_074] |
| Goose | 기본 꺼진 정규식 | 없음 | Smart Approve는 LLM 판정 [미확정 clm_075] | LLM 판정 |
| Continue | shell-quote 토큰화 + 재귀 평가 | 근거 없음 | — | 항상 질문 (검증 clm_076) |
| Amp | 현재 기본 승인 없음, 2025년엔 `amp.permissions` 글롭 | 로컬 없음 | 셸 게이트 근거 없음 | 기본 게이트 없음 |

Amp, Zed, Kiro 행은 에이전트 D의 단일 조직 출처뿐이라 원장에 올리지 않았다 (`artifacts/agent_results/D_others.md`).

### 7.2 미확정 우회·CVE (2025–2026)

- Claude Code는 CVE-2025-66032 이후 v1.0.93에서 블록리스트를 허용 목록으로 바꿨다 [미확정 clm_014]. echo, DNS 유출, $IFS, sed, find, zsh clobber 등 10건 이상 [미확정 clm_018]. 사내 수치로 샌드박스가 프롬프트를 84% 줄였다 [미확정 clm_017].
- Codex의 `git show --output` 우회(Pillar, v0.95.0) [미확정 clm_026]와 PowerShell `--%` 오분류 CVE-2026-19591 [미확정 clm_027].
- Gemini CLI의 `grep ...; <명령>` 우회(Tracebit, v0.1.14) [미확정 clm_044].
- Cursor의 backtick·`$()` 우회 CVE-2025-54131과 denylist 폐기 [미확정 clm_047].
- Copilot CLI의 `${var@P}` 등 확장 우회 CVE-2026-29783 [미확정 clm_050].
- Adversa GuardFall의 원문 텍스트 매칭 가드 누출 수치 [미확정 clm_077].

### 7.3 미확정 리눅스 사실

- Landlock 네트워크 제한은 ABI 4(커널 6.7)부터다 [미확정 clm_033]. 이 머신(ABI 3)에서 네트워크가 열려 있음은 실험으로 확인했다 (검증 clm_005).
- Ubuntu 24.04의 AppArmor 사용자 네임스페이스 제한은 기본으로 켜져 있지만 이 WSL2 커널에는 그 sysctl이 없다 [미확정 clm_036]. 그래서 native Ubuntu에서 런처가 동작하는지는 확인하지 못했다.

### 7.4 한계

- insane-search 엔진이 없어 `snapshot_sources.py`가 exit 2로 끝났다. 고위험 주장은 모두 원문 대조를 못 해 미확정이다. 게이트를 우회하지 않았다.
- `gh`가 없고 GitHub API가 속도 제한에 걸려 일부 advisory와 PR은 raw 파일이나 미러로 읽었다.
- 확장 조사는 깊이 1에서 멈췄다. 남은 리드는 `artifacts/expansion_log.md`에 있다.
- 에이전트 인용 일부는 WebFetch 요약을 거쳐 바이트 단위로 확인하지 않았다.
