# E: Cross-tool allowlist bypasses (2025-2026) + Linux primitives for read-only command execution (WSL2 / Ubuntu 24.04)

Researcher: agent E. Date of research: 2026-11-13. Every claim lists URL, organization, date, source type, and a verbatim quote. Advisory quotes and blog quotes marked [grep-verified] were checked by `curl -sL <url> | grep -F "<quote>"` against the live page (HTML tags stripped). Others came through WebFetch (model-relayed) and are marked [relayed]. HIGH-RISK means the claim carries a date, CVE id, version, or number.

---

## PART 1: Static "safe command" allowlist bypasses

### 1.1 Core thesis (3 independent organizations agree)

| # | Claim | Source (org, date, type) | Verbatim quote |
|---|---|---|---|
| P1 | Trail of Bits: safe-command allowlists without a sandbox are "fundamentally flawed"; sandboxing is the primary control. [grep-verified] | https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/ (Trail of Bits, 2025-10-22, blog) | "Maintaining allowlists of “safe” commands without a sandbox is fundamentally flawed" / "Implement sandboxing as the primary security control" |
| P2 | ToB `go test -exec` ran with no approval because `go test` was on the safe list. [grep-verified] | same | "Because go test is considered a safe command" |
| P3 | ToB recommends `--` before user input (facade pattern). [grep-verified] | same | "Place -- before user input" |
| P4 | Correction to the task premise: ToB did NOT bypass via `find -exec`. That flag was filtered, and the bypass went through `fd -x=python3`, `rg --pre bash`, and `git show --format/--output`. ToB also does not name the 3 vendors (disclosure was ongoing). [grep-verified] | same | "commonly known execution flags (such as find -exec) were filtered" |
| P5 | Flatt Security (RyotaK): Anthropic fixed by moving from a blocklist to an allowlist. CVE-2025-66032, v1.0.93. HIGH-RISK [grep-verified] | https://flatt.tech/research/posts/pwning-claude-code-in-8-different-ways (GMO Flatt Security, 2026-01-12, blog) | "Anthropic was very responsive and addressed these issues by introducing an allowlist approach instead of the previous blocklist approach. These vulnerabilities were assigned CVE-2025-66032 and fixed in Claude Code v1.0.93." |
| P6 | Academic: 69.0-98.6% of 1,709 real-world agent command denylists are fragile (ShellSieve). HIGH-RISK [grep-verified] | https://arxiv.org/abs/2606.15549 (Chen & Lin, arXiv, 2026-06-14 v1, paper/blog) | "we applied ShellSieve to 1,709 real-world command denylists (containing 13,332 denylist rules) collected from GitHub. The evaluation shows several key findings, including that 69.0--98.6% of the" |

### 1.2 Bypass classes, with concrete instances

| Class | Concrete instance (tool) | Source / id |
|---|---|---|
| **Argument injection into an allowlisted binary (exec-capable flags)** | `go test -exec`, `fd -x=python3`, `rg --pre bash` (unnamed agents, ToB); `man --html="touch /tmp/pwned" man`; `sort -S 1b --compress-program "sh"`; `rg ... --pre=sh` (Claude Code, Flatt) | ToB P2; Flatt [grep-verified: "man --html=", "--compress-program"] |
| **Option abbreviation (GNU getopt_long / git prefix match)** | `git ls-remote --upload-pa="touch /tmp/pwned" test`, which git expands to `--upload-pack`. It beat a blocklist on `--upload-pack`. | Flatt [grep-verified: "--upload-pa="] |
| **File-write flag on a "read" command → config/hook RCE** | `git show --format=... --output=./.git/config` plants an external diff tool, which runs on the next `git diff` (Codex CLI) | Pillar, see 1.3 |
| **Interpreter-in-a-tool (sed `e`, `w`)** | `echo test \| sed 's/test/touch \/tmp\/pwned/e'` (Claude Code); sed parsing → file write (CVE-2025-64755); piped `echo \| sed` → write into `.claude` (CVE-2026-25723) | Flatt; GHSA-7mv8-j34q-vp7q; GHSA-mhg7-666j-cqg4 |
| **Parser desync on flags taking or not taking a value** | `xargs -t touch echo`: the validator thought `touch` was `-t`'s value and checked `echo` as the command | Flatt [grep-verified: "xargs -t touch echo"] |
| **`$IFS` word splitting hides arguments from the validator** | `rg -v -e pattern$IFS.$IFS$HOME/.claude/projects$IFS--pre=sh` | Flatt; GHSA-xq4m-mc3c-vvg3 ("$IFS and short CLI flags") |
| **Parameter-expansion / prompt-expansion code exec** | `echo ${one="$"}${two="$one(touch /tmp/pwned)"}${two@P}` | Flatt [grep-verified: "${two@P}"] |
| **Quote breakout / command substitution inside an allowlisted command** | `echo "\"; <COMMAND>; echo \""` (Claude Code CVE-2025-54795); backtick or `$(cmd)` (Cursor CVE-2025-54131) | Cymulate; GHSA-x56v-x2h6-7j34; CVE record |
| **Persistence via shell rc / history** | `history -s "touch /tmp/pwned"; history -a ~/.bashrc` | Flatt [grep-verified] |
| **`cd` + relative write into protected dir** | `cd .claude` then write (Claude Code CVE-2026-25722) | GHSA-66q4-vfjg-2qhh |
| **Shell-dialect syntax unknown to the parser** | zsh clobber `>!` / `>\|` writes outside cwd (CVE-2026-24053) | GHSA-q728-gf8j-w49r |
| **`find` parsing** | CVE-2026-24887, `find` command injection | GHSA-qgqw-h4xq-7w8w |
| **Over-broad allowlist (network exfil)** | `ping`/`nslookup`/`host`/`dig` were allowlisted → DNS exfiltration (CVE-2025-55284) | Embrace The Red; GHSA-x5gv-jw7f-j6xj |
| **Agent edits its own allowlist/config** | Amp: writes `amp.commands.allowlist` in VS Code settings. Copilot: `"chat.tools.autoApprove": true` in `.vscode/settings.json` (CVE-2025-53773) | Embrace The Red (Aug 2025) |
| **Sandbox config gaps (post-sandbox era)** | bwrap did not protect a missing `.claude/settings.json`, so a SessionStart hook was planted (CVE-2026-25725). macOS seatbelt escape via git worktree named `.git` + fsmonitor (CVE-2026-55607). Codex trusted a model-generated `cwd` as a writable root (CVE-2025-59532). | GHSA-ff64-7w26-62rf; GHSA-7835-87q9-rgvv; GHSA-w5fx-fh39-j5rw |
| Shell function definitions, glob expansion into options (`-*` files), newline / `\` continuation, `PAGER` / `GIT_*` env abuse, here-docs | **No source found** in this pass for a 2025-2026 agent advisory of these specific classes. See EXPAND. | — |

### 1.3 Advisory table (Claude Code, Codex, Cursor, Copilot, Amp, Gemini)

All Anthropic GHSA quotes below were [grep-verified] against github.com/anthropics/claude-code/security/advisories/<id>.

| Tool | ID | Published | Fixed in | Verbatim quote | Reporter |
|---|---|---|---|---|---|
| Claude Code | GHSA-x5gv-jw7f-j6xj / **CVE-2025-55284** | 2025-08-15 | v1.0.4 | "Due to an overly broad allowlist of safe commands" | wunderwuzzi23 (Rehberger) |
| Claude Code | GHSA-x56v-x2h6-7j34 / **CVE-2025-54795** | 2025-08-01 | v1.0.20 | "Due to an error in command parsing, it was possible to bypass the Claude Code confirmation prompt" | Elad Beber (Cymulate) |
| Claude Code | GHSA-qxfv-fcpc-w36x / **CVE-2025-58764** (rg) | 2025-09-09 | 1.0.105 [relayed] | "NVIDIA AI Red Team" | NVIDIA AI Red Team |
| Claude Code | GHSA-7mv8-j34q-vp7q / **CVE-2025-64755** (sed) | 2025-11-20 | v2.0.31 [relayed] | "Due to an error in sed command parsing, it was possible to bypass the Claude Code read-only validation and write to arbitrary files on the host system" | Adam Chester (SpecterOps) |
| Claude Code | GHSA-xq4m-mc3c-vvg3 / **CVE-2025-66032** | 2025-12-03 | v1.0.93 | "Due to errors in parsing shell commands related to $IFS and short CLI flags, it was possible to bypass the Claude Code read-only validation and trigger arbitrary code execution" | RyotaK (GMO Flatt) |
| Claude Code | GHSA-qgqw-h4xq-7w8w / **CVE-2026-24887** (find; NOT awk, as one search snippet claimed) | 2026-02-03 | v2.0.72 [relayed] | "to trigger execution of untrusted commands through the find command" | alexbernier |
| Claude Code | GHSA-q728-gf8j-w49r / **CVE-2026-24053** (zsh clobber) | 2026-02-03 | v2.0.74 [relayed] | "Due to a Bash command validation flaw in parsing ZSH clobber syntax" | alexbernier |
| Claude Code | GHSA-66q4-vfjg-2qhh / **CVE-2026-25722** (cd) | 2026-02-06 | v2.0.57 [relayed] | "command to navigate into sensitive directories like" | nil221 |
| Claude Code | GHSA-mhg7-666j-cqg4 / **CVE-2026-25723** (piped sed) | 2026-02-06 | v2.0.55 [relayed] | "failed to properly validate commands using piped sed operations with the echo command" | nil221 |
| Claude Code (bwrap sandbox) | GHSA-ff64-7w26-62rf / **CVE-2026-25725** | 2026-02-06 | v2.1.2 [relayed] | "settings.json was not protected if it was missing" | edbr |
| Claude Code (macOS seatbelt; not bwrap) | GHSA-7835-87q9-rgvv / **CVE-2026-55607** | 2026-06-25 | 2.1.163 [relayed] | "leading to code execution outside of seatbelt sandbox restrictions" | metnew |
| Codex CLI | GHSA-w5fx-fh39-j5rw / **CVE-2025-59532** (cwd sandbox config) | 2025-09-19 | 0.39.0 [relayed] | "Codex CLI could treat a model-generated" | Tzanko Matev |
| Codex CLI | `git show --output` → `.git/config` (Pillar "GitPwned") | reported 2026-01-07, fixed 2026-02-04, disclosed 2026-07-20 | v0.95.0 | "OpenAI's Codex CLI trusts git show as a safe command, but git show --output can write arbitrary content to arbitrary files—including .git/config." [grep-verified] / "patched in Codex CLI version v0.95.0 on February 4, 2026" [grep-verified]. **No CVE/GHSA id found.** GHSA-w5fx is the earlier cwd bug, not this one. | Pillar Security (Ariel Fogel) |
| Cursor | GHSA-534m-3w6r-8pqr / **CVE-2025-54131** | 2025-08-01 | 1.3 | "In versions below 1.3, an attacker can bypass the allow list in auto-run mode with a backtick (`) or $(cmd)." [relayed via cve.circl.lu; NVD fetch failed] | — |
| Copilot (VS Code) | **CVE-2025-53773** | post 2025-08-12 | Aug 2025 Patch Tuesday | "chat.tools.autoApprove" / "August Patch Tuesday" [grep-verified] | Rehberger |
| Amp | (no CVE) config self-edit | post 2025-08-05 | "within a few days" [relayed] | "amp.commands.allowlist" [grep-verified] | Rehberger |

Sources for the non-GHSA rows: Embrace The Red CVE-2025-55284 post https://embracethered.com/blog/posts/2025/claude-code-exfiltration-via-dns-requests/ (2025-08-11): "ping, nslookup, host and dig" and "The fix is in the product starting with v1.0.4. The vulnerability was assigned CVE-2025-55284." [grep-verified]. Cymulate https://cymulate.com/blog/cve-2025-547954-54795-claude-inverseprompt/ (undated; page says last updated 2026-04-06): "Command injection (CVE-2025-54795)Affected: versions < v1.0.20Fixed: v1.0.20" [grep-verified]. Pillar https://www.pillar.security/blog/gitpwned-allowlist-to-rce (2026-07-20).

Independent second-org confirmations of the key claims:
- CVE-2025-66032: Anthropic GHSA + Flatt (2 orgs).
- CVE-2025-55284: Anthropic GHSA + Embrace The Red (2 orgs).
- CVE-2025-54795: Anthropic GHSA + Cymulate (2 orgs).
- "allowlists are insufficient": Trail of Bits + Flatt + Pillar + arXiv (4 orgs).
- Codex git-show: Pillar only (single source; secondary press not fetched).

### 1.4 Vendor responses: sandbox vs. patched lists

| Vendor | Response | Evidence |
|---|---|---|
| Anthropic (Claude Code) | Both. It patches the parser and lists every time (≥10 parsing GHSAs, 2025-08 → 2026-02), switched blocklist→allowlist (P5), and in Oct 2025 added an opt-in OS sandbox (bubblewrap/seatbelt). The sandbox is off by default. | https://www.anthropic.com/engineering/claude-code-sandboxing (Anthropic, 2025-10-20, official_blog) [grep-verified]: "We’ve built this on top of OS level primitives such as Linux bubblewrap and MacOS seatbelt to enforce these restrictions at the OS level." / "we've found that sandboxing safely reduces permission prompts by 84%" (HIGH-RISK, vendor figure). Docs https://code.claude.com/docs/en/sandboxing (Anthropic, undated, official_docs) [relayed]: "The sandbox is off by default." |
| OpenAI (Codex CLI) | Sandbox-first. Commands run inside bwrap+seccomp (Linux) by default, and the safe-list was patched for `git show`. Legacy Landlock is now rejected for filesystem-restricted policies. | codex-rs/linux-sandbox/README.md (OpenAI, commit 2026-11-12, repository) [curl]: "The helper uses bubblewrap for filesystem and namespace isolation, and seccomp" / "The legacy Landlock option is rejected for these policies because it cannot isolate app-server Unix sockets." |
| Cursor | Moved to a sandbox. Linux uses Landlock+seccomp directly; Windows runs the Linux sandbox in WSL2. | https://cursor.com/blog/agent-sandboxing (Cursor, 2026-02-18, official_blog) [grep-verified]: "The kernel exposes the required primitives via Landlock and seccomp, but userspace is responsible for composing them into a usable sandbox." / "On Windows, we run our Linux sandbox inside WSL2." / "40% less often" (HIGH-RISK). |
| Google (Gemini CLI), Backslash's Cursor denylist findings, HiddenLayer CVE-2025-62354 ("allowlist is best-effort") | Search-summary only, not fetched. Listed as LEADs. | — |

### 1.5 Axis 4 (`python -c`) per tool, as far as this scope found
- Claude Code: inside the opt-in sandbox, any command (including `python -c`) runs under bwrap with writes limited to cwd/TMPDIR ("Default write behavior: read and write access to the current working directory ..." [relayed, code.claude.com/docs/en/sandboxing]). Without the sandbox, plan-mode/approval handling of `python -c` was **not examined in this scope** (other agents cover it).
- Codex: bubblewrap does `--ro-bind / /` by default, so `python -c` runs physically read-only in read-only mode ("When bubblewrap is active, the filesystem is read-only by default via `--ro-bind / /`." [curl, Codex README]).
- Cursor: sandboxed commands run under Landlock (blog). Specific `python -c` handling: **no evidence found**.
- Amp, Copilot, Gemini CLI: **no evidence found** in this scope.

---

## PART 2: Linux primitives to make a command physically unable to write (unprivileged Python, Ubuntu 24.04, WSL2 6.6.x)

### 2.0 Local observation on the target machine (raw probe output, not a claim of tested sandbox behaviour)
```
uname -r                                  -> 6.6.87.2-microsoft-standard-WSL2
zcat /proc/config.gz | grep ...           -> CONFIG_USER_NS=y, CONFIG_SECCOMP_FILTER=y, CONFIG_OVERLAY_FS=y,
                                             CONFIG_SECURITY_LANDLOCK=y, CONFIG_SECURITY_APPARMOR=y,
                                             CONFIG_LSM="landlock,lockdown,yama,loadpin,safesetid,integrity,selinux,apparmor,tomoyo"
syscall(444 landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION) -> 3
/sys/module/apparmor/parameters/enabled  -> N
sysctl kernel.apparmor_restrict_unprivileged_userns -> "cannot stat ... No such file or directory"
/usr/lib/sysctl.d/10-apparmor.conf        -> "kernel.apparmor_restrict_unprivileged_userns = 1"  (Ubuntu package ships it; the WSL kernel has no such knob)
user.max_user_namespaces                  -> 79955
unshare -r -m -n sh -c id                 -> uid=0(root) ... ok
which bwrap firejail nsjail landrun       -> only /usr/bin/unshare present (bwrap NOT installed)
/etc/apparmor.d/                          -> contains lxc-usernsexec, unprivileged_userns; no bwrap-userns-restrict
```
What this means for the deployment: on this WSL2 kernel, Landlock is **ABI 3** (fs + REFER + TRUNCATE, with no TCP, ioctl or scope controls). Unprivileged user namespaces work, and Ubuntu's AppArmor userns restriction is **not in effect** (the knob is absent). bwrap would need `apt install bubblewrap`. I do not assert why AppArmor is inactive.

### 2.1 WSL2 kernel config (primary)
- Claim: Microsoft's WSL2 6.6 kernel config enables Landlock, user namespaces and seccomp filter, and has landlock first in CONFIG_LSM. HIGH-RISK. Source: https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/arch/x86/configs/config-wsl (Microsoft, last commit 2025-11-17, repository). Quotes: `CONFIG_SECURITY_LANDLOCK=y` / `CONFIG_USER_NS=y` / `CONFIG_LSM="landlock,lockdown,yama,loadpin,safesetid,integrity,selinux,apparmor,tomoyo"` / `CONFIG_DEFAULT_SECURITY_SELINUX=y`.
- Second org: Codex README (OpenAI) "WSL2 follows the normal Linux bubblewrap path. WSL1 is not supported for bubblewrap sandboxing because it cannot create the required user namespaces". Claude Code docs (Anthropic) [relayed]: "The sandbox runs on macOS, Linux, and WSL2."

### 2.2 bubblewrap
| Claim | Source | Quote |
|---|---|---|
| Unprivileged; needs user namespaces; setuid mode removed | https://github.com/containers/bubblewrap README (containers org, commit 2026-09-16, repository) | "Historically, bubblewrap also supported a setuid mode for systems where unprivileged user namespaces were not supported. However, this has been removed." |
| Security depends entirely on the arguments | same | "the level of protection between the sandboxed processes and the host system is entirely determined by the arguments passed to bubblewrap." |
| Uses NO_NEW_PRIVS | same | "bubblewrap uses `PR_SET_NO_NEW_PRIVS` to turn off setuid binaries" |
| Real-world read-only recipe (Codex): `--ro-bind / /`, writable roots via `--bind`, `.git` re-applied ro, `--unshare-user`, `--unshare-pid`, `--unshare-net`, `--proc /proc`, plus seccomp blocking `io_uring` | Codex linux-sandbox README (OpenAI, 2026-11-12, repository) | "When bubblewrap is active, the filesystem is read-only by default via `--ro-bind / /`." / "protected subpaths under writable roots (for example `.git`, resolved `gitdir:`, and `.codex`) are re-applied as read-only via `--ro-bind`." / "All filter modes block `io_uring` to prevent bypassing socket-family restrictions." |
| `--new-session` needed against TIOCSTI unless seccomp filters it | bwrap README | "If you are not filtering out `TIOCSTI` commands using seccomp filters," (followed by "argument `--new-session` is needed") |

Suggested minimal argv for the "plan phase", derived (not quoted): `bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --unshare-all --die-with-parent --new-session -- <cmd>`. Only `/tmp` (tmpfs, discarded) is writable. `--unshare-all` also drops the network.

### 2.3 Ubuntu 24.04 AppArmor userns restriction
| Claim | Source | Quote |
|---|---|---|
| Introduced in 23.10, on by default in 24.04 (HIGH-RISK) | https://www.qualys.com/2025/three-bypasses-of-Ubuntu-unprivileged-user-namespace-restrictions.txt (Qualys, 2025-03, advisory) [curl] | "Ubuntu 23.10 introduced unprivileged user namespace restrictions (the sysctl kernel.apparmor_restrict_unprivileged_userns) and Ubuntu 24.04 enabled them by default." |
| 24.04 semantics: userns creation allowed, capabilities inside denied (quoting Ubuntu's Alex Murray) | same | "For Ubuntu 24.04 LTS, the use of unprivileged user namespaces is then allowed for all applications but access to any additional permissions within the namespace are denied." |
| Per-app opt-in via profile with `userns,` rule; disable via sysctl | https://ubuntu.com/blog/ubuntu-23-10-restricted-unprivileged-user-namespaces (Canonical, 2023-10-09, official_blog) [relayed] | "sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0" |
| Claude Code surfaces this exact failure and offers the fixes "add a bwrap profile" or the sysctl | code.claude.com/docs/en/sandboxing (Anthropic, official_docs) [relayed] | "Ubuntu's AppArmor restriction on user namespaces stops bubblewrap here" |
| Ubuntu package ships the sysctl default = 1 | local file /usr/lib/sysctl.d/10-apparmor.conf (Ubuntu apparmor 4.0.1really4.0.1-0ubuntu0.24.04.9) | "kernel.apparmor_restrict_unprivileged_userns = 1" |

On WSL2's Microsoft kernel the sysctl does not exist (2.0), so the restriction does not apply. On a native Ubuntu 24.04 kernel it does, and bwrap then needs a profile (the `bwrap-userns-restrict` profile from the AppArmor repo; shipping status on 24.04 is unresolved, see EXPAND) or the sysctl set to 0.

### 2.4 Landlock
| Claim | Source | Quote |
|---|---|---|
| ABI→kernel map: 1=5.13, 2=5.19 (REFER), 3=6.2 (TRUNCATE), 4=6.7 (NET TCP), 5=6.10 (IOCTL_DEV), 6=6.12 (scope abstract unix + signal), 7=6.15 (logging), 8=7.0 (TSYNC), 9=7.1 (RESOLVE_UNIX). HIGH-RISK | https://man7.org/linux/man-pages/man7/landlock.7.html (man-pages project, page dated 2026-07-18, official_docs) | "│  3  │  6.2   │ LANDLOCK_ACCESS_FS_TRUNCATE" / "│  4  │  6.7   │ LANDLOCK_ACCESS_NET_BIND_TCP" / "│  6  │  6.12  │ LANDLOCK_SCOPE_ABSTRACT_UNIX_SOCKET" |
| Kernel mainline docs now go to ABI v12 (UDP v10, capability/namespace rules v12). HIGH-RISK | https://docs.kernel.org/userspace-api/landlock.html (raw: torvalds/linux Documentation/userspace-api/landlock.rst, commit 2026-10-20, official_docs) | "Network rules (since ABI v4 for TCP and v10 for UDP)" / "Capability rules (since ABI v12)" |
| Inherited by children (and so across fork+execve); cannot be removed | landlock.rst | "this policy will be enforced on all its subsequently created children as well.  Once a thread is landlocked, there is no way to remove its security policy" |
| Already-open fds are not restricted | landlock(7) | "Files or directories opened before the sandboxing are not subject to these restrictions." |
| Truncate via fd rights is decided at open; fds passed between processes keep their properties | landlock.rst | "the availability of the ``LANDLOCK_ACCESS_FS_TRUNCATE`` and ``LANDLOCK_ACCESS_FS_IOCTL_DEV`` rights is associated with the newly created file descriptor" |
| **Not restrictable: chmod, chown, setxattr, utime, etc.** So Landlock alone is NOT fully "physically read-only" (metadata can still change). | include/uapi/linux/landlock.h (kernel, official source) | "It is currently not possible to restrict some file-related actions accessible through these syscall families: :manpage:`chdir(2)`, :manpage:`stat(2)`, :manpage:`flock(2)`, :manpage:`chmod(2)`, :manpage:`chown(2)`, :manpage:`setxattr(2)`, :manpage:`utime(2)`," |
| ABI<3 cannot deny truncation | landlock.rst | "File truncation could not be denied before the third Landlock ABI, so it is always allowed when using a kernel that only supports the first or second ABI." |
| /proc/<pid>/fd pipes/sockets and nsfs not restrictable; chroot not denied; mount denied | landlock.rst | "However, :manpage:`chroot(2)` calls are not denied." |
| OverlayFS layers vs merged dir are separate | landlock.rst | "A policy restricting an OverlayFS layer will not restrict the resulted merged hierarchy, and vice versa." |
| REFER denied by default even when not handled | landlock(7) | "This is the only access right which is denied by default by any ruleset, even if the right is not specified as handled at ruleset creation time." |

**Read-only rights set (derived from the rights list, not quoted).** Handle all write-ish fs rights the ABI supports: WRITE_FILE, REMOVE_DIR, REMOVE_FILE, MAKE_CHAR, MAKE_DIR, MAKE_REG, MAKE_SOCK, MAKE_FIFO, MAKE_BLOCK, MAKE_SYM, REFER (v2+), TRUNCATE (v3+), IOCTL_DEV (v5+). Also handle READ_FILE, READ_DIR and EXECUTE. Then add a single rule on `/` that grants only READ_FILE | READ_DIR | EXECUTE. For a scratch dir, add a rule on e.g. a private tmp that grants the write rights. On this WSL2 box (ABI 3) that covers file content/creation/deletion/rename/truncate. It does not cover chmod/chown/xattr/utime, network, or ioctl on devices.

Tools and bindings:
- landrun (Go CLI): https://github.com/Zouuup/landrun README (repository, undated main) [curl]: "Linux kernel 5.13 or later with Landlock enabled" / "`--ro <path>`: Allow read-only access to specified path" / "pass `--best-effort` so it gracefully degrades to the best ABI the running kernel supports". The ABI 3 box needs `--best-effort`.
- Python: PyPI `landlock` (Edward-Knight, pre-release 1.0.0.devN), `py-landlock` (0.1.1, Jan 2026; `allow_read`), `sandlock` (needs 6.7+/ABI 6, so unusable on this box). [search-summary only, not fetched]. ctypes with syscalls 444/445/446 is ~40 lines and needs no dependency (derived).
- How Codex uses it: legacy only. It is now rejected for filesystem-restricted policies in favour of bwrap (quote in 1.4). Cursor uses Landlock+seccomp directly (1.4).

### 2.5 seccomp, unshare, firejail, nsjail, systemd-run
| Primitive | Key fact | Source / quote |
|---|---|---|
| seccomp-bpf | Cannot see paths (no pointer deref), so it cannot express "read-only filesystem"; only usable to block syscalls wholesale (e.g. io_uring, `open` with O_WRONLY flags, but `openat2`/io_uring make that leaky). | Documentation/userspace-api/seccomp_filter.rst (kernel, official_docs): "BPF programs may not dereference pointers which constrains all filters to solely evaluating the system call arguments directly." / "System call filtering isn't a sandbox." Cursor blog (2nd org): "Linux doesn't provide easy access to the file path in a seccomp-bpf context." [grep-verified context] |
| `unshare -r -m -n` | Gives a userns-root + private mount ns + no network. You can then `mount --bind -o remount,ro` paths, but you must remount every mount point recursively, and fake root inside can still write files the real uid owns on any mount left rw. It is a building block, not a policy. | local probe shows it works on this box (2.0). No vendor source quoted. |
| firejail | setuid-root program, so larger attack surface | https://github.com/netblue30/firejail README: "it is an SUID sandbox program that reduces the risk of" |
| nsjail | namespaces + Kafel seccomp + `--bindmount_ro`; unprivileged with userns | https://github.com/google/nsjail README: "Linux process isolation tool using namespaces, resource limits, and seccomp-bpf syscall filters." / "-R, --bindmount_ro SRC    Read-only bind mount (SRC or SRC:DST)" |
| systemd-run --user -p ProtectSystem=strict | In user managers these options implicitly enable PrivateUsers= and need userns. Each call spawns a transient unit (latency, and needs a working `systemd --user`, which this box has: `running`). | https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html (systemd, official_docs): "This option is only available for system services, or for services running in per-user instances of the service manager in which case PrivateUsers= is implicitly enabled" / "If set to "strict" the entire file system hierarchy is mounted read-only, except for the API file system subtrees /dev/, /proc/ and /sys/" |
| Read-only overlay / container (docker/podman) | Heavier and needs a daemon or rootless podman. Not researched in depth. | — |

### 2.6 Trade-off summary (derived from the above)
| Option | Truly blocks writes? | Deps on this box | Gotchas |
|---|---|---|---|
| bwrap `--ro-bind / /` + `--tmpfs /tmp` + `--unshare-all` | Yes, including chmod/chown/xattr, since the mount is read-only | `apt install bubblewrap` | On native Ubuntu 24.04 the AppArmor userns restriction applies, but not on the WSL2 Microsoft kernel. Paths under `/mnt/c` and symlinks into `/mnt/c` break Claude Code's bwrap on WSL2 (forum mirrors, see EXPAND). |
| Landlock (ctypes / landrun) | File content, create, delete, rename, truncate (ABI 3). NOT chmod/chown/xattr/utime. Network is not restricted on ABI 3. | none (kernel ABI 3 present) | Inherits across exec. Pre-opened fds stay writable, so close or don't pass them. Overlay semantics. |
| seccomp alone | No (path-blind) | libseccomp or raw BPF | Only a complement (block io_uring, ptrace, mount). |
| unshare -r -m -n + manual ro remounts | Yes if done right | util-linux (present) | Easy to miss submounts, and fiddly. |
| firejail | Yes | install | setuid root |
| nsjail | Yes | build/install | Heavier config |
| systemd-run --user ProtectSystem=strict | Yes (except /dev, /proc, /sys) | systemd --user (running) | per-call unit startup, userns needed |

Skipped / not checked: the Codex safe-command source (GitHub API rate-limited; path unknown). NVD pages failed, so CVE-2025-54131 was relayed via circl.lu. No sandbox was actually run (bwrap not installed). Several "[relayed]" fix versions were not grep-verified.
Risk: Landlock on this WSL2 box (ABI 3) still allows chmod/chown/xattr and all network. Treat it as "no content writes", not "physically read-only". A host kernel update could change the ABI or AppArmor state.

## EXPAND
- LEAD: Gemini CLI allowlist bypass (Tracebit, fixed v0.1.14, July 2025) and GHSA-wpqr-6v78-jr5g (2026, --yolo allowlist) — WHY: a 3rd vendor's static-list bypass and response — ANGLE: fetch tracebit.com/blog/code-exec-deception-gemini-ai-cli-hijack and github.com/google-gemini/gemini-cli/security/advisories
- LEAD: Backslash Research's 4 Cursor denylist bypasses (July 2025) → Cursor deprecated the denylist in 1.3 — WHY: a vendor dropping a denylist is a direct precedent — ANGLE: backslash.security blog "cursor denylist"
- LEAD: HiddenLayer CVE-2025-62354 (Cursor "Follow Allowlist" bypass, v1.3.4–<2.0; vendor called the allowlist best-effort) — WHY: an explicit vendor statement that the allowlist is not a security boundary — ANGLE: hiddenlayer.com/sai_security_advisor/2025-11-cursor/
- LEAD: Pillar "Week of Sandbox Escapes" (Jul 2026), other days covering Cursor/Gemini/Antigravity (docker socket, git hooks) — WHY: post-sandbox bypass classes (config/hook persistence) — ANGLE: pillar.security blog series index
- LEAD: Codex safe-command list current source (git show/`--output` handling after v0.95.0) — WHY: shows exactly how the vendor patched argument injection — ANGLE: browse github.com/openai/codex codex-rs for `is_known_safe_command`
- LEAD: bypass classes with no source found (shell function definitions, glob expansion into options like a file named `-exec`, newline / `\` continuation, `PAGER`/`GIT_PAGER`/`GIT_EXTERNAL_DIFF`/`GIT_SSH_COMMAND` env, here-docs) — WHY: the task asked for these, and the dcode gate needs to cover them — ANGLE: search GHSA db for "claude-code newline" / "heredoc", plus Flatt's 2nd Claude Code post (poisoning-claude-code-one-github-issue)
- LEAD: `bwrap-userns-restrict` AppArmor profile, shipped and enabled on 24.04 or only in 25.04+ — WHY: decides whether native 24.04 needs a sysctl change — ANGLE: Launchpad bug 2046477, apparmor gitlab profiles/apparmor.d/bwrap-userns-restrict history
- LEAD: Claude Code WSL2 bwrap issues (GitHub #51126 E2BIG; mirror reports of `/mnt/c` binds and symlinked `~/.aws` failing, and network isolation unreliable on WSL2) — WHY: the deployment target is WSL2 — ANGLE: github.com/anthropics/claude-code/issues?q=WSL2+bwrap
- LEAD: Codex default switch to bubblewrap in 0.115.0 (search-summary only) — WHY: dates the vendor's Landlock→bwrap move — ANGLE: openai/codex releases notes 0.115.0
- DEAD END: NVD detail pages (WebFetch returned only "NVD - Home"); BleepingComputer (domain blocked); GitHub API (rate-limited, unauthenticated).
