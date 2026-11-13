# 요약: 코딩 에이전트는 셸 명령의 읽기 전용 여부를 어떻게 판단하나 (2025년부터 2026년까지)

조사일 2026-11-13. 대상 도구는 14개이고 목록과 도구별 세부는 `01_full_report.md` 7장에 있다.
본문은 검증 게이트(`validate_ledger.py`)를 통과한 주장만 단정한다. 도구별 세부 비교표는 1차 출처가 있어도 독립 출처 2곳이나 원문 스냅샷을 채우지 못한 칸이 많아 `01_full_report.md`의 미확정 부록에 따로 두었다.

## 핵심 결론

1. **정적 허용 목록만으로는 "읽기 전용"을 보장하지 못한다는 데 업계와 연구자가 수렴했다.** 독립 연구자들이 허용된 바이너리의 실행 플래그(rg --pre, sort --compress-program, git 옵션 축약, go test -exec)로 안전 명령 목록을 반복해서 뚫었고 (clm_030), Trail of Bits는 샌드박스를 1차 통제로 권한다 (clm_031). Microsoft, Cursor, Anthropic 문서도 자동 승인 규칙이나 분류기가 보안 경계가 아니라고 적는다 (clm_061).
2. **선두 도구는 OS 샌드박스로 옮겨 갔다.** Codex와 Cursor는 정적 판정 대신 샌드박스 안 실행을 기본 경로로 삼는다 (clm_063). Codex의 Linux 샌드박스는 bubblewrap `--ro-bind / /`와 seccomp를 주 경로로 쓴다 (clm_022). Claude Code의 OS 샌드박스는 macOS는 Seatbelt, Linux와 WSL2는 bubblewrap을 쓰며 기본값은 꺼짐이다 (clm_010).
3. **정적 분석은 남아 있지만 역할이 바뀌었다.** 해석하거나 분류할 수 없는 명령을 자동 승인하지 않고 묻거나 막는 쪽으로 수렴했다 (clm_062). Claude Code 2.1.x는 tree-sitter 파서를 쓴다 (clm_016).
4. **`git status`도 안전하지 않다.** 저장소 로컬 git 설정(core.fsmonitor, core.hooksPath 등)은 git status 같은 읽기 명령에서도 임의 프로그램을 실행시켜 여러 벤더가 취약점으로 다뤘다 (clm_060).
5. **plan 단계의 `python -c` 처리 방식은 세 갈래다.** 셸을 아예 빼거나, 항상 묻거나, OS 샌드박스로 쓰기를 막는다 (clm_078). Continue는 인터프리터 `-c`를 항상 권한 요청 대상으로 둔다 (clm_076). Claude Code plan 모드의 셸 명령은 bypass 권한을 쓸 수 있는 대화형 세션이면 검사 없이 돌고, auto 모드를 쓸 수 있으면(기본) 분류기가 판단하며, 둘 다 아니면 내장 읽기 전용 명령만 묻지 않는다 (clm_012). Codex Plan Mode는 프롬프트 지시(변경 금지)일 뿐이다 (clm_025).

## dcode에 대한 권고 (이 머신에서 실행 검증함)

계획 승인 전 `execute`를 **네임스페이스 기반 읽기 전용 런처**로 감싸고, 지금의 정적 허용 목록은 런처를 못 쓸 때의 대체 경로로 내린다.

- 최종 프로토타입(`artifacts/exec/ro_launcher.py`, 외부 의존성 없음, 약 100줄)은 사용자·마운트·네트워크 네임스페이스, /run tmpfs, `mount_setattr` 재귀 읽기 전용, /tmp 쓰기용 tmpfs, seccomp로 AF_UNIX와 io_uring 거부를 묶는다. 이 상태에서 `git status -sb`, `python -c 'import textual'`, ls/grep/find는 동작하고, 함수 정의·`--output`·touch·chmod 쓰기, systemd-run 탈출, WSL interop, 네트워크, herdr 소켓은 모두 막혔다. `git status -sb` 출력은 런처 안팎에서 같았다. 호출당 약 14ms가 더 든다 (clm_082).
- 읽기 전용 마운트나 Landlock만으로는 부족했다. 경로 유닉스 소켓 connect로 systemd 사용자 버스에 붙어 샌드박스 밖에 파일을 만들 수 있었고 (clm_081, clm_083), Landlock ABI 3 래퍼는 chmod와 mtime 변경, 경로 유닉스 소켓 connect, 샌드박스 전에 열린 fd로의 쓰기, 네트워크 접속을 막지 못했다 (clm_005). WSL interop으로 Windows 실행 파일이 C: 드라이브에 쓸 수도 있었다 (clm_007).

## 남은 위험

seccomp 필터는 x86_64 전용이다. PID 네임스페이스가 없어 같은 사용자의 다른 프로세스에 시그널을 보낼 수 있고, 비밀 파일은 여전히 읽힌다. WSL이 아닌 일반 리눅스에서 보안 모듈이 네임스페이스 안 권한을 막으면 런처 설정이 실패하므로, 그때는 정적 판정과 사용자 승인으로 넘겨 안전하게 실패하게 해야 한다. 미확정 주장 35건과 근거는 `01_full_report.md` 부록에 있다.
