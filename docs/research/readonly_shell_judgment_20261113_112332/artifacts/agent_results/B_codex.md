# B — OpenAI Codex CLI: read-only shell judgment, sandbox, approvals (as of 2026-11-13)

Scope: github.com/openai/codex (Rust `codex-rs`). Source code was read at main commit `553c764e8b99fa519e9c6eb9b657875ef0f5e1c1` (2026-11-13T02:11Z) unless another SHA is named. Raw files: `https://raw.githubusercontent.com/openai/codex/<sha>/<path>`.

## TL;DR (most important for dcode-assistant)

1. **Codex removed its static "known-safe command" allowlist on 2026-08-20** (PR #39630, released in v0.149.0) and removed Git from it the day before (PR #39524). `is_safe_command.rs` / `windows_safe_commands.rs` are gone from main. Codex no longer statically decides that a command is read-only. What remains: (a) a tree-sitter-bash "plain words only" parser that splits `bash -lc` scripts into segments for **exec-policy rule matching**, (b) a small **dangerous-command** detector (`rm -f*` plus `sudo`, `env`, `trap` wrappers, plus Windows-specific rules), (c) the **OS sandbox**, which is the real read-only guarantee.
2. **Read-only mode = OS sandbox, not command classification.** With `sandbox_mode=read-only` plus `approval_policy=on-request`, any command that is not flagged dangerous and does not request escalation runs **without approval inside the read-only sandbox**. This includes `python3` scripts. A rule-free unit test (empty policy, read_only, on-request) expects `Skip` with the message "On non-Windows, rely on the read-only sandbox to prevent harm." So `python -c ...` is allowed in read-only mode, and the sandbox blocks the writes.
3. The Git change was driven by "repo config can make read-only git run helpers". The 2026-09-01 CVE batch (CVE-2026-19590/19592/19593: `core.hooksPath`, `core.fsmonitor`, `attr.tree`/filters) and CVE-2026-19591 (PowerShell `--%` safe-command misclassification leading to a file-writing Git command) are the same class of problem.

---

## Axis 1 — Static judgment (is_known_safe_command, bash parsing, dangerous list, execpolicy)

### 1.1 History and current status of `is_known_safe_command`

| # | Claim | Source | Org | Date | Type | Verbatim quote |
|---|---|---|---|---|---|---|
| 1a | **HIGH-RISK.** The known-safe allowlist was removed and `untrusted` retired in PR #39630 | https://github.com/openai/codex/commit/942af8447b1d1addc81fb3c3135293497d479a06 | OpenAI | 2026-08-20 | repository | "Remove the known-safe command allowlist. Projects marked untrusted now request approval for every command unless an explicit exec policy rule allows it." |
| 1a' | Same commit deletes `is_safe_command.rs` (536 lines) and `windows_safe_commands.rs` (503 lines). DERIVED from the GitHub API file list, not a verbatim source quote | same commit | OpenAI | 2026-08-20 | repository | (derived; no quote) |
| 1a'' | Before removal, known-safe commands were auto-allowed only under `untrusted` (or a Windows sandbox missing its backend). Old `exec_policy.rs` @9ca99b51 | https://raw.githubusercontent.com/openai/codex/9ca99b51713066681cce211184c0ff9035496979/codex-rs/core/src/exec_policy.rs | OpenAI | 2026-08 (parent of #39630) | repository | `if is_known_safe` / `&& (approval_policy == AskForApproval::UnlessTrusted` / `|| windows_managed_fs_restrictions_without_sandbox_backend)` / `return Decision::Allow;` |
| 1a (2nd org) | Independent confirmation, with version | https://blakecrosley.com/blog/codex-untrusted-approval-policy-retired | Blake Crosley (independent blog) | 2026-08-25 | blog | "Codex CLI v0.149.0 (stable, August 20, 2026) retired the untrusted approval policy in PR #39630, “Retire the untrusted approval policy.”" |
| 1a (3rd org) | Independent timeline | https://codex.danielvaughan.com/2026/08/31/codex-cli-sandbox-permission-hardening-full-auto-removed-untrusted-retired-fail-closed/ | Daniel Vaughan (independent blog) | 2026-08-31 (upd. 2026-11-12) | blog | "PR #39630 (“Retire the untrusted approval policy”), merged in v0.149.0 (20 August 2026), removes untrusted from the CLI, the config.toml schema, and the MCP tool interface." |
| 1b | **HIGH-RISK.** Git was removed from the safe list one day earlier because repo config can make read-only git run helpers (PR #39524) | https://github.com/openai/codex/commit/3b45c29062ff0e76e71c91b6753290400e7fa8da | OpenAI | 2026-08-19 | repository | "Repository configuration can cause even read-only Git commands to execute helpers, so Git command arguments alone are not enough to establish trust." |
| 1b' | Same commit | same | OpenAI | 2026-08-19 | repository | "Under the `unless-trusted` approval policy, require approval for commands such as `git status` unless an explicit execution policy rule allows them." |
| 1c | Current `lib.rs` exports only the dangerous-command check (no safe-command export) | https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/shell-command/src/lib.rs | OpenAI | 2026-11-13 | repository | `pub use command_safety::is_dangerous_command;` |

### 1.2 What the allowlist looked like before removal (useful as prior art)

Source: `codex-rs/shell-command/src/command_safety/is_safe_command.rs` at `1b450c79126cc56df29b833110a8c702f82de882` (parent of #39524, mid-Aug 2026). Org OpenAI, type repository.

- Entry point and `bash -lc` composition rule:
  - Comment lines (verbatim): `// more "plain" commands (only bare words / quoted strings) combined with` / `// a conservative allow‑list of shell operators that themselves do not` / `// introduce side effects ( "&&", "||", ";", and "|" ). If every`
  - Code: `.all(|cmd| is_safe_to_call_with_exec(cmd))`. Every segment had to be safe.
- Unconditionally safe programs (verbatim list): `"cat" | "cd" | "cut" | "echo" | "expr" | "false" | "grep" | "head" | "id" | "ls" | "nl" | "paste" | "pwd" | "rev" | "seq" | "stat" | "tail" | "tr" | "true" | "uname" | "uniq" | "wc" | "which" | "whoami"`, plus Linux-only `matches!(cmd, "numfmt" | "tac")`.
- `find`: `"-exec", "-execdir", "-ok", "-okdir",` … `"-delete",` … `"-fls", "-fprint", "-fprint0", "-fprintf",` are rejected.
- `rg`: `"--pre",` … `"--hostname-bin",` and `"--search-zip",` / `"-z",` are rejected.
- `base64`: `const UNSAFE_BASE64_OPTIONS: &[&str] = &["-o", "--output"];`
- `sed`: only `sed -n {N|M,N}p`: `command.len() <= 4` and `command.get(1).map(String::as_str) == Some("-n")`, with the arg matching `/^(\d+,)?\d+p$/`. So `sed -i` and every other sed form were not safe.
- Git (before 2026-08-19): `find_git_subcommand(command, &["status", "log", "diff", "show", "branch"])`. Rejected global options: `-C`, `-c`, `-p`, `--config-env`, `--exec-path`, `--git-dir`, `--namespace`, `--paginate`, `--super-prefix`, `--work-tree`. Rejected subcommand options: `GitOptionPattern::Exact("--output"),` … `GitOptionPattern::Exact("--ext-diff"),` … `GitOptionPattern::Exact("--textconv"),` … `GitOptionPattern::Exact("--exec"),`. `git branch` was safe only with no args or with `"--list" | "-l" | "--show-current" | "-a" | "--all" | "-r" | "--remotes" | "-v"`, `"-vv" | "--verbose"` or `--format=`.
- Earlier Git hardening, **HIGH-RISK** (fix for issue #10160): https://github.com/openai/codex/commit/f50c8b2f81d69e49d1f6eafaeebf0f6ba2bbba52 (2026-02-02): "Hardens Git command safety to prevent approval bypasses for destructive or write-capable invocations (branch delete, risky push forms, output/config-override flags), so these commands no longer auto-run as “safe.”" It also mentions "risky Git config override flags (-c, --config-env) that can trigger external execution".
- Older path: `codex-rs/core/src/command_safety/is_safe_command.rs` was moved into a new crate on 2026-02-10 (commit d8f9bb65e2, "Split command parsing/safety out of `codex-core` into new `codex-command` (#11361)"; commit-list output).

### 1.3 tree-sitter-bash parsing (still present, now used for rule matching)

Source: https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/shell-command/src/bash.rs (OpenAI, 2026-11-13, repository).

- Accepted constructs: "Returns `Some(Vec<command_words>)` if every command is a plain word‑only" … "command and the parse tree does not contain disallowed constructs" … "(parentheses, redirections, substitutions, control flow, etc.). Otherwise" … "returns `None`."
- Node allowlist: `"program", "list", "pipeline", "command", "command_name", "word", "string", "string_content", "raw_string", "number", "concatenation"`. Operator allowlist: `const ALLOWED_PUNCT_TOKENS: &[&str] = &["&&", "||", ";", "|", "\"", "'"];`
- Redirects, subshells, braces and backticks are rejected: "Any other punctuation like parentheses, braces, redirects, backticks, etc are rejected."
- Words that the shell could expand are rejected: `&& !word.contains(['{', '}', '*', '?', '[', ']', '\\', '~', '^', '#', '$', '`'])` with the comment "A tree-sitter word can still undergo shell expansion or escape removal. Do not use its source spelling as proof of runtime argv." It also rejects `!word.starts_with('=')` (zsh equals expansion).
- Double quotes are accepted only if their contents are already literal: "Double quotes suppress globbing and brace expansion, but not escape" … "removal. Only accept contents whose source spelling is already literal."
- A second, permissive parser is used **only to find dangerous commands**: "This is suitable" … "for identifying dangerous literal commands, but must not be used to prove" … "that a command is safe."
- Only `-lc`/`-c` with bash/zsh/sh: `if !matches!(flag.as_str(), "-lc" | "-c")`.
- Current use (`codex-rs/core/src/exec_policy.rs`): `if let Some(commands) = parse_shell_lc_plain_commands(command)` splits the script into segments for exec-policy matching. If parsing fails, the whole argv is one opaque command: `commands: vec![command.to_vec()],`.
- Model-facing prompt (`codex-rs/prompts/templates/permissions/approval_policy/on_request.md`): "Commands that use more advanced shell features like redirection (>, >>, <), substitutions ($(...), ...), environment variables (FOO=bar), or wildcard patterns (*, ?) will not be evaluated against rules, to limit the scope of what an approved rule allows."

### 1.4 Dangerous-command list (current)

Source: `codex-rs/shell-command/src/command_safety/is_dangerous_command.rs` @553c764 (OpenAI, repository).

- POSIX list is tiny: `Some("rm") if rm_args_include_force_option(&command[1..]) => {` … `Some("sudo") =>` (recurse) … `Some("env") =>` … `Some("trap") =>`.
- Recursion through shell wrappers is capped: `const MAX_DANGEROUS_COMMAND_WRAPPER_DEPTH: usize = 8;`. Above the cap the command is treated as dangerous (`return Some(DangerousCommandMatch::Other);`).
- #39524 also removed 73 lines of Git logic from this file (commit file list: `modified codex-rs/shell-command/src/command_safety/is_dangerous_command.rs 0 73`).
- Effect (exec_policy.rs): "If the command is flagged as dangerous or we have no sandbox protection," … "we should never allow it to run without approval." With `never` it is `AskForApproval::Never => Decision::Forbidden,`.
- `sed -i`: #39630 says "Keep command parsing conservative by treating in-place `sed` forms as mutating". Inferred, not read: per that commit's file list the change is in `parse_command.rs`, which I believe is the UI/memory-summary classifier, not an approval gate. After #39630 no approval gate special-cases `sed -i`; under on-request it runs in the sandbox like anything else.

### 1.5 execpolicy `.rules` (Starlark prefix rules)

Source: https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/execpolicy/README.md (OpenAI, repository).

- "Policy engine and CLI built around `prefix_rule(pattern=[...], decision?, justification?, match?, not_match?)` plus `host_executable(name=..., paths=[...])`."
- "`decision` defaults to `allow`; valid values: `allow`, `prompt`, `forbidden`."
- "The effective `decision` is the strictest severity across all matches (`forbidden` > `prompt` > `allow`)."
- `match`/`not_match` are "validated at load time (think of them as unit tests)".
- An allow rule bypasses the sandbox only when **every** segment is explicitly allowed (exec_policy.rs): "Bypass sandbox only when every parsed command segment is" … "explicitly allowed by execpolicy."
- A heredoc does not reduce to its prefix. Test `heredoc_script_stays_in_sandbox_despite_inner_allow_rule`: with `prefix_rule(pattern=["python3"], decision="allow")` the script `"python3 <<'PY'\nprint('hello')\nPY"` gets `bypass_sandbox: false` (`codex-rs/core/src/exec_policy_tests.rs`).
- Note: the docs page `learn.chatgpt.com/docs/exec-policy` returned "Page not found" (2026-11-13).

## Axis 2 — OS sandbox and default modes

| Claim | Source | Org | Date | Type | Verbatim quote |
|---|---|---|---|---|---|
| Three sandbox modes | https://learn.chatgpt.com/docs/sandboxing.md (developers.openai.com/codex/* now redirects to learn.chatgpt.com/docs/*) | OpenAI | undated | official_docs | "`workspace-write`: The agent can read files, edit within the workspace, and run" (next line) "routine local commands inside that boundary. This is the default low-friction" |
| read-only wording (see conflict note under Axis 3) | same | OpenAI | undated | official_docs | "`read-only`: The agent can inspect files, but it can't edit files or run" (next line) "commands without approval." |
| danger-full-access | same | OpenAI | undated | official_docs | "`danger-full-access`: The agent runs without sandbox restrictions. This removes" |
| Network off by default | https://learn.chatgpt.com/docs/agent-approvals-security.md | OpenAI | undated | official_docs | "By default, the agent runs with network access turned off." |
| Platform mechanisms | https://learn.chatgpt.com/docs/sandboxing.md | OpenAI | undated | official_docs | "On **macOS**, sandboxing works out of the box using the built-in Seatbelt" / "On **Linux and WSL2**, install `bubblewrap` with your package manager first:" |
| **HIGH-RISK.** Linux uses bubblewrap + seccomp now; Landlock is legacy | https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/linux-sandbox/README.md | OpenAI | 2026-11-13 | repository | "The helper uses bubblewrap for filesystem and namespace isolation, and seccomp for syscall filtering. `src/seccomp.rs` installs `PR_SET_NO_NEW_PRIVS` and the seccomp filters; it also retains the legacy Landlock filesystem implementation." |
| Landlock is rejected for FS-restricted policies | same | OpenAI | 2026-11-13 | repository | "Filesystem-restricted execution requires bubblewrap. The legacy Landlock option is rejected for these policies because it cannot isolate app-server Unix sockets." |
| Read-only by default with `--ro-bind` | same | OpenAI | 2026-11-13 | repository | "When bubblewrap is active, the filesystem is read-only by default via `--ro-bind / /`." |
| Network namespace | same | OpenAI | 2026-11-13 | repository | "When bubblewrap is active and network is restricted without proxy routing, the helper also isolates the network namespace via `--unshare-net`." |
| seccomp also blocks io_uring | same | OpenAI | 2026-11-13 | repository | "All filter modes block `io_uring` to prevent bypassing socket-family restrictions." |
| WSL | same | OpenAI | 2026-11-13 | repository | "WSL2 follows the normal Linux bubblewrap path. WSL1 is not supported for bubblewrap sandboxing because it cannot create the required user namespaces" |
| Protected paths inside writable roots | https://learn.chatgpt.com/docs/agent-approvals-security.md | OpenAI | undated | official_docs | "`<writable_root>/.git` is protected as read-only whether it appears as a directory or file." / "`<writable_root>/.codex` is protected as read-only when it exists as a directory." |
| macOS Seatbelt is deny-by-default | https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/sandboxing/src/seatbelt_base_policy.sbpl | OpenAI | 2026-11-13 | repository | "; start with closed-by-default" / "(deny default)" |
| Windows sandbox variants | https://learn.chatgpt.com/docs/windows/windows-sandbox.md | OpenAI | undated | official_docs | "`mxc`: The recommended sandbox on compatible Windows devices. Uses native process isolation without administrator-approved setup, additional Windows accounts, or local firewall rules." |
| Windows unelevated | same | OpenAI | undated | official_docs | "It runs commands with a restricted Windows token derived from your current user, applies ACL-based filesystem boundaries, and uses environment-level offline controls instead of the dedicated offline-user firewall rule." |
| (2nd org, **HIGH-RISK**) v0.150.0 made Linux/Windows sandboxes fail-closed | danielvaughan.com (URL above) | Daniel Vaughan | 2026-08-31 | blog | "v0.150.0 changed the evaluation so that denied or unreadable paths are treated as blocked rather than silently allowed. macOS (Seatbelt) was already fail-closed; this brings Linux and Windows to parity." |

Bubblewrap as default: a web search surfaced mirrored commit "refactor: make bubblewrap the default Linux sandbox (#13996)" dated 2026-03-11. This is **not verified** against github.com (API rate-limited). **No independent second-org source verified for bubblewrap.** Daniel Vaughan's 2026-05-03 post "Codex CLI Sandbox Internals: How Seatbelt, Bubblewrap, Landlock and Windows DACL…" exists, but per the search summary it may describe Landlock as primary (not opened). Single-org (OpenAI docs + repo) for this claim. See EXPAND.

## Axis 3 — Approval policies, presets, plan mode

| Claim | Source | Org | Date | Type | Verbatim quote |
|---|---|---|---|---|---|
| **HIGH-RISK.** CLI accepts only on-request / never | https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/utils/cli/src/approval_mode_cli_arg.rs | OpenAI | 2026-11-13 | repository | "/// The model decides when to ask the user for approval." / "OnRequest," / "/// Never ask for user approval" / "Never," |
| `on-failure` is now just an alias of on-request; `untrusted` is internal only (project trust) | `codex-rs/protocol/src/protocol.rs` @553c764 | OpenAI | 2026-11-13 | repository | `/// Internal policy for projects marked untrusted. Commands require` … `#[serde(alias = "on-failure")]` |
| Granular policy | same | OpenAI | 2026-11-13 | repository | `/// Fine-grained controls for individual approval flows.` |
| Retired-policy migration (official) | https://learn.chatgpt.com/docs/agent-approvals-security.md | OpenAI | undated | official_docs | "Codex and ChatGPT Work no longer support `approval_policy = "untrusted"`." |
| Official read-only recipe | same | OpenAI | undated | official_docs | "Or run `codex --sandbox read-only --ask-for-approval on-request`." / "With `on-request`, commands allowed by the sandbox can run without approval," |
| Strict prompting now uses project trust | same | OpenAI | undated | official_docs | `trust_level = "untrusted"` / "Commands then require approval unless an execution-policy rule allows them." |
| "Plan" in docs means read-only mode | same | OpenAI | undated | official_docs | "If you want to chat or plan without making changes, switch to `read-only` mode with the `/permissions` command." |
| Official preset table: read-only + on-request still runs commands | same | OpenAI | undated | official_docs | "Codex can read files and run commands within the read-only sandbox. Actions outside the sandbox can require approval." (row "Safe read-only browsing", `--sandbox read-only --ask-for-approval on-request`) |
| Decision table for unmatched commands (core logic) | `codex-rs/core/src/exec_policy.rs` @553c764 | OpenAI | 2026-11-13 | repository | "In restricted sandboxes, do not prompt for non-escalated," / "non-dangerous commands; let the sandbox enforce" / "restrictions without a user prompt." |
| `never` relies on the sandbox | same | OpenAI | 2026-11-13 | repository | "We allow the command to run, relying on the sandbox for" / "protection." |
| Plan Mode (collaboration mode) is prompt-level | https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/collaboration-mode-templates/templates/plan.md | OpenAI | 2026-11-13 | repository | "You may explore and execute **non-mutating** actions that improve the plan. You must not perform **mutating** actions." |
| Plan Mode allows tests and builds | same | OpenAI | 2026-11-13 | repository | "Tests, builds, or checks that may write to caches or build artifacts (for example, `target/`, `.cache/`, or snapshots) so long as they do not edit repo-tracked files" |

Under the retired `untrusted` policy (before 2026-08-20), commands matching `is_known_safe_command` auto-ran and everything else prompted. Today `UnlessTrusted` returns `Decision::Prompt` for every unmatched command ("Projects marked untrusted require approval for every command" / "that is not explicitly allowed by an exec policy rule.").

**Docs conflict.**
- Against auto-run: the sandboxing page says read-only "can't edit files or run" / "commands without approval", and Crosley's blog (independent) says "read-only plus on-request prompts for edits as well as commands".
- For auto-run: the agent-approvals-security page ("Codex can read files and run commands within the read-only sandbox"), the exec_policy code, and a rule-free unit test (Axis 4).
- Majority view: commands run sandboxed without a prompt. The sandboxing-page sentence is probably loose wording for "anything outside the sandbox needs approval".
- Older 2025 docs described a "Read Only" preset that asked before running commands. That was under the then-existing policy set, which I did not re-verify.

## Axis 4 — `python -c` in read-only / plan

**Answer: allowed without approval, contained by the OS sandbox.** No static classification is involved.

- Code path: `render_decision_for_unmatched_command_for_platform`. If the command is not dangerous, under `AskForApproval::OnRequest` with `FileSystemSandboxKind::Restricted`, `requests_sandbox_override()` false leads to `Decision::Allow` ("In restricted sandboxes, do not prompt for non-escalated," … "non-dangerous commands; let the sandbox enforce" … "restrictions without a user prompt."). Source: `codex-rs/core/src/exec_policy.rs` @553c764, OpenAI, repository.
- Direct test evidence: `codex-rs/core/src/exec_policy_tests.rs` @553c764, `heredoc_script_stays_in_sandbox_despite_inner_allow_rule`: command `"python3 <<'PY'\nprint('hello')\nPY"` with `permission_profile: PermissionProfile::read_only(),` and `approval_policy: AskForApproval::OnRequest,` yields `ExecApprovalRequirement::Skip {` / `bypass_sandbox: false,`, which means it runs without a prompt inside the sandbox. (This test also has a `python3` allow rule. The point is that it still stays sandboxed. The generic unmatched-command path above gives Skip even without the rule.)
- **Rule-free test** (`verify_approval_requirement_for_unsafe_powershell_command`, same file): `ExecPolicyManager::new(Arc::new(Policy::empty()))`, `SandboxPermissions::UseDefault`, `approval_policy: AskForApproval::OnRequest,`, `permission_profile: PermissionProfile::read_only(),`. On non-Windows it expects `ExecApprovalRequirement::Skip {` with the message `"On non-Windows, rely on the read-only sandbox to prevent harm."`. On Windows (no backend) it expects NeedsApproval: `On Windows, SandboxPolicy::ReadOnly should be assumed to mean` / `that no sandbox is present, so anything that is not "provably` / `safe" should require approval.`
- Gate check: the shell tool (`unified_exec/preparation.rs`) computes its requirement through `.create_exec_approval_requirement_for_shell(` in exec_policy. The stricter `default_exec_approval_requirement` in `tools/sandboxing.rs` (doc: `/// - OnRequest: ask unless filesystem access is unrestricted`) is only the fallback in `orchestrator.rs` for tools that return no requirement: `tool.exec_approval_requirement(req).unwrap_or_else(|| {`. Not every tool was audited (e.g. apply_patch has its own).
- Same for `git status` under on-request (test `git_status_obeys_approval_policy_and_explicit_rules`): `AskForApproval::OnRequest,` / `None,` leads to `ExecApprovalRequirement::Skip {` / `bypass_sandbox: false,` (workspace-write profile).
- Official docs: "With `on-request`, commands allowed by the sandbox can run without approval," and, in the preset table, "Codex can read files and run commands within the read-only sandbox. Actions outside the sandbox can require approval." (learn.chatgpt.com/docs/agent-approvals-security.md, OpenAI, undated, official_docs).
- Escalation leaves the sandbox only through an explicit request: on_request.md tells the model "Provide the `sandbox_permissions` parameter with the value `"require_escalated"`". The test `unmatched_on_request_uses_permission_profile_file_system_policy_for_escalation_prompts` shows `madeup-cmd` + read_only + `SandboxPermissions::RequireEscalated` leads to `Decision::Prompt`.
- Plan Mode: prompt-only rule ("must not perform **mutating** actions"). I found no evidence that Plan Mode changes the sandbox or approval policy itself (not verified).
- Residual risk: the read-only sandbox still allows reading everything readable ("Read anywhere, no writes" — danielvaughan table) and `/dev/null` writes. Network is blocked by default.

## Axis 5 — CVEs / GHSA 2025-2026 and vendor response

| CVE / GHSA | Summary (verbatim) | Fix | Source(s) |
|---|---|---|---|
| **CVE-2025-59532 / GHSA-w5fx-fh39-j5rw** (HIGH-RISK) | "Codex CLI could treat a model-generated `cwd` as the sandbox’s writable root, including paths outside of the folder where the user started their session." | "We released a patch in Codex CLI **0.39.0** that canonicalizes and validates that the boundary used for sandbox policy is based on where the user started the session"; IDE ext 0.4.12; affected `0.2.0 <= 0.38.0` | GHSA (OpenAI, 2025-09-19, advisory) https://github.com/openai/codex/security/advisories/GHSA-w5fx-fh39-j5rw ; NVD (NIST, published 2025-09-22, government) https://nvd.nist.gov/vuln/detail/CVE-2025-59532 : "this did not impact the network-disabled sandbox restriction"; fix commit 8595237505a1e0faabc2af3db805b66ce3ae182d |
| **CVE-2025-61260** (HIGH-RISK) | Check Point: "Codex CLI will automatically load and execute MCP server entries from a project-local configuration whenever codex is run inside that repository." | "OpenAI issued a fix on August 20, 2025, in Codex CLI version 0.23.0." | Check Point Research (2025-12-01, blog) https://research.checkpoint.com/2025/openai-codex-cli-command-injection-vulnerability/ ; NVD (published 2026-04-14): "Codex automatically loads project-local .env and .codex/config.toml files without requiring user confirmation" |
| **CVE-2026-19591** (HIGH-RISK) — safe-command bypass | "misclassified certain PowerShell commands as safe because their command-safety parser interpreted PowerShell's stop-parsing token (--%) differently than PowerShell itself." … "Codex can run a file-writing Git command without requesting user approval." | Ref PR https://github.com/openai/codex/pull/22643 ; "The approval bypass does not disable filesystem sandboxing; the default filesystem sandbox on macOS and Linux can prevent writes outside permitted locations." | NVD (published 2026-09-01; CNA id 8f4f43ab-ba69-4d92-aa1d-d772184d6fb7, not resolved to an org) |
| **CVE-2026-19592** (HIGH-RISK) | "automatically collected Git repository metadata without disabling the repository-local core.fsmonitor setting." … "The helper runs outside Codex's command sandbox and without a user-approval prompt" | PR https://github.com/openai/codex/pull/22652 | NVD 2026-09-01 |
| **CVE-2026-19590** (Desktop) | "automated Git operations trusted the repository's local core.hooksPath setting." | PR https://github.com/openai/codex/pull/22843 | NVD 2026-09-01 |
| **CVE-2026-19593** (Desktop) | "the attr.tree setting and a configured clean or process filter can cause Git to run an attacker-controlled program." | — | NVD 2026-09-01; ZDI-26-651 (Trend Micro ZDI, independent) |
| CVE-2026-14898 (Desktop, macOS) | "rendered remote images from Markdown in model responses" (exfil via prompt injection) | — | NVD 2026-07-06 (keyword search result; not opened in detail) |
| Issue #10160 (no CVE) | Git safe-list bypasses: "`git show|diff|log --output` ... style file-write flags", "risky Git config override flags (-c, --config-env) that can trigger external execution" | commit f50c8b2f81 (2026-02-02) | repository |

**Vendor response pattern.** OpenAI hardened the safe-list repeatedly (Feb 2026 Git flags; PowerShell `--%`). In Aug 2026 it then **gave up on static safe-command classification entirely**: Git first (#39524, rationale "Repository configuration can cause even read-only Git commands to execute helpers"), then the whole list (#39630). It relies on the OS sandbox plus explicit exec-policy rules, and it disables repo-local Git helpers during internal metadata collection (CVE-2026-19590/92/93).

## Implications for dcode-assistant (brief, not a recommendation)

- Codex's final design: no static "read-only" proof for shell. Read-only = OS sandbox; static parsing is only used to (a) split segments for user rules and (b) catch `rm -f`-class danger.
- Git with arbitrary repo config is unsafe even for `git status` (fsmonitor, hooksPath, attr filters, textconv/ext-diff). This applies directly to any `git` allowlist entry and to `git -C <root>`.
- The tree-sitter "plain word" rules (no redirects, no `$`, `{}`, globs, `~`, backslash escapes; only `&& || ; |`) are a well-tested reference for a conservative parser.

## Not checked / risks

- Not checked: Plan Mode's effect on the sandbox; the exact release versions that fixed CVE-2026-19590..93; the bubblewrap-default commit on github.com; the body of `parse_command.rs`; a second independent source for CVE-2026-19591 (SentinelOne returned 429; ZDI covers only 19593).
- Risk: the docs contradict each other on read-only + on-request. My conclusion (commands auto-run inside the sandbox) rests on code and tests at main 553c764 plus one docs page.

## EXPAND

- LEAD: Commit "make bubblewrap the default Linux sandbox (#13996)" dated 2026-03-11 (seen only on mirrors) — WHY: dates the Landlock to bubblewrap switch — ANGLE: `https://github.com/openai/codex/pull/13996` or `commits?path=codex-rs/linux-sandbox/README.md` once the API rate limit clears.
- LEAD: PR #22643 (fix for CVE-2026-19591 PowerShell `--%`) and the fixed versions for CVE-2026-19590..93 — WHY: concrete parser-differential bypass of a safe-command classifier, directly relevant to our gate — ANGLE: fetch PR page / Codex releases around v0.13x–0.14x; GHSA list on github.com/openai/codex/security (API returned only 1 public advisory).
- LEAD: v0.150.0 "sandbox fail-closed on Linux and Windows" — WHY: earlier denied-path fall-through means the sandbox was weaker than documented before then — ANGLE: Codex release notes rust-v0.150.0.
- LEAD: Whether Plan Mode (collaboration mode) switches the sandbox to read-only automatically — WHY: decides if Codex's "plan" phase allows `python -c` writes in workspace-write — ANGLE: grep `collaboration_mode` + `sandbox`/`permission_profile` in codex-rs/core.
- LEAD: `parse_command.rs` (UI classifier: read/search/list/unknown) — WHY: still classifies commands as "read" for display/memory; could be mistaken for a gate — ANGLE: read codex-rs/shell-command/src/parse_command.rs.
- DEAD END: learn.chatgpt.com/docs/exec-policy returned "Page not found"; developers.openai.com/codex/security now redirects to the Codex Security (scanner) product page.
- DEAD END: SentinelOne CVE pages returned HTTP 429; GitHub REST API rate-limited after ~10 calls (no `gh`).
