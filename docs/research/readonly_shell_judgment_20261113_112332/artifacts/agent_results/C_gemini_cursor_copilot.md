# C: Gemini CLI, Cursor, and GitHub Copilot (VS Code, Copilot CLI, cloud agent): read-only shell judgment, 2025-2026

Agent C. Gathered on 2026-11-13. Every claim has a source URL, the organization, a date, a source type, and a verbatim quote. Claims marked **[HR]** contain a date, CVE ID, version, or number. None of these claims was tested by running anything. Gemini CLI sources are pinned to commit `b9776560ea5710bc673891499aaec68c737d160a` (main on 2026-11-13). VS Code source files are from `main` as fetched on 2026-11-13, with last-commit dates taken from the GitHub atom feed.

## Summary

| | Gemini CLI | Cursor | VS Code agent (Copilot) | Copilot CLI | Copilot cloud agent |
|---|---|---|---|---|---|
| Static judgment | tree-sitter-bash splits the command and checks each part recursively. Redirection and `$()` downgrade ALLOW to ASK. A built-in "known safe" list (ported from Codex style) has per-tool checks for find/git/sed/rg/base64 and auto-allows. | Allowlist with prefix matching. Parsing is server-side and closed source. Commands it cannot classify go to approval (since 2.3). | tree-sitter-bash/pwsh extracts subcommands. Each one must match a `true` rule and none may match `false`. Default rules ship as regexes (git/find/sed/rg/npm...). Unanalyzable syntax disables auto-approve. | A safety layer sorts commands into read-only and write-capable. Read-only commands run automatically. Closed source. | No per-command gate. The agent runs freely in an ephemeral VM or Actions runner behind a firewall. |
| OS sandbox | Off by default. Legacy whole-process options: Seatbelt profiles, docker/podman/gVisor/LXC. Newer `security.toolSandboxing` (default false) uses bwrap on Linux and has a read-only workspace in plan mode. | Seatbelt on macOS. Landlock+seccomp on Linux, with a bubblewrap fallback. WSL2 on Windows. Network blocked by default. | Off by default. Seatbelt on macOS. bubblewrap on Linux/WSL2. Network allowed by default. | Off by default. MXC: Seatbelt on macOS, bubblewrap on Linux. | GitHub-hosted ephemeral environment with a firewall. |
| Plan/ask mode | Plan mode denies every tool by default, including `run_shell_command`. Users can add `commandPrefix` allow rules for plan mode. | Ask mode: shell is disabled when no OS sandbox is available. Otherwise it relies on a read-only sandbox (forum, unofficial). Plan mode: no evidence found. | Plan agent "default read-only project access". Terminal handling in Plan: no evidence found. | Plan mode blocks commands that would change workspace files. Commands "whose effect can't be clearly determined" pass through. | n/a |
| `python -c` | Not on the known-safe list, so ASK in default mode. Denied in plan mode unless a user rule allows it (inference). | Auto-review: runs in the sandbox without a prompt (inference). The CLI's ask+sandbox mode was reported to block `python3`. | Not in the default rules, so it needs approval. With the sandbox on, the runtime may approve sandboxed commands (inference). | Not read-only, so manual approval, or an LLM in "assisted" mode (inference). | Runs freely. |

---

## (a) Google Gemini CLI

### Axis 1: Static judgment (chains, redirects, substitution, git, find, sed)

**C1. A bash command is parsed with tree-sitter (web-tree-sitter + tree-sitter-bash). A parse failure falls back to the default decision (ASK, or DENY when non-interactive).**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/utils/shell-utils.ts (Google, last commit 2026-11-09, repository)
- Quote: `import { Language, Parser, Query, type Node, type Tree } from 'web-tree-sitter';`
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/policy/policy-engine.ts (Google, last commit 2026-11-05, repository)
- Quote: `// Parsing logic failed, we can't trust it. Use default decision ASK_USER (or DENY in non-interactive).`

**C2. A compound command is split into subcommands. Each one is re-checked recursively. Any DENY wins, and any ASK makes the whole command ASK. `bash -c` wrappers are stripped and their contents re-checked.**
- Source: policy-engine.ts (as C1)
- Quote: `if (subResult.decision === PolicyDecision.DENY) return subResult;`
- Quote: `// Recursive check for shell wrappers (bash -c, etc.)`

**C3 [doc/code discrepancy]. The user docs (shell.md, last commit 2026-05-01) say a disallowed part blocks the whole chain. The November engine code aggregates a non-allowed part to ASK_USER instead (C2).**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/docs/tools/shell.md (Google, 2026-05-01, official_docs)
- Quote: "The tool automatically splits commands chained with `&&`, `||`, or `;` and validates each part separately. If any part of the chain is disallowed, the entire command is blocked."

**C4. Redirection and command substitution downgrade an ALLOW to ASK unless the rule sets `allowRedirection` or `allowCommandSubstitution`. Substitution includes `$()`, backticks, `<()` and `>()`.**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/docs/reference/policy-engine.md (Google, 2026-11-05, official_docs)
- Quote: "(Optional) If true, lets shell commands use command substitution # ($(), backticks, <(), >(), or PowerShell @()). By default, the policy # engine asks for confirmation when substitution syntax is detected"
- Quote: "In chained commands (e.g., cmd1 > file && cmd2), each # individual command rule must permit redirection if it's used."
- Note: in the raw file, each of those lines starts with `# ` inside a TOML code block. The quotes keep those `# ` markers.

**C5. A built-in "known safe" heuristic upgrades ASK to ALLOW. It applies when the matched rule has no `commandPrefix` or `argsPattern`, or when no rule matched at all. It downgrades "dangerous" commands to ASK, and git in an untrusted folder to ASK.**
- Source: policy-engine.ts
- Quote: `[PolicyEngine.check] Command evaluated as known safe, overriding ASK_USER to ALLOW: ${command}`
- Quote: `if (containsGitCommand(parsedArgs) && !this.isTrustedFolder()) {`

**C6. The known-safe list and its per-tool checks.** Plain safe commands: cat, cd, cut, echo, expr, grep, head, ls, nl, pwd, stat, tail, tr, uniq, wc, which, and others. `find` is rejected if it has any of -exec, -execdir, -ok, -okdir, -delete, -fls, -fprint, -fprint0 or -fprintf. git allows only status/log/diff/show/branch, rejects `-c`/`--config-env`, and rejects `--output`, `--ext-diff`, `--textconv`, `--exec` and `--paginate`. sed allows only `sed -n {N|M,N}p`. Path arguments must stay inside the workspace, symlinks included. Inside `bash -c`, `()<>` are rejected.
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/sandbox/utils/commandSafety.ts (Google, last commit 2026-09-04, repository)
- Quote: "It performs deep validation * for specific tools like `base64`, `find`, `rg`, `git`, and `sed` to ensure * unsafe flags (like `--output`, `-exec`, or mutating options) are not used, * and ensures all path arguments remain strictly within the workspace."
- Quote: `// Special-case sed -n {N|M,N}p`
- Quote: `// We allow &&, ||, |, ; but explicitly block subshells () and redirection >, >>, <`
- Quote (git): `const unsafeFlags = new Set([ '--output', '--ext-diff', '--textconv', '--exec', '--paginate', ]);` (whitespace between tokens collapsed from the source lines)

**C7. Rules match by `commandPrefix` (string prefix) or `commandRegex`. In the legacy `tools.core` setting, `run_shell_command(git)` is a prefix allow, and `tools.exclude` is deprecated.**
- Source: policy-engine.md
- Quote: "`commandPrefix`: Matches if the `command` argument starts with the given   string."
- Note: the raw file wraps this line. The source text is "starts with the given" + newline + "  string.", so the quote contains a line break and two spaces.
- Source: shell.md
- Quote: "`tools.exclude` [DEPRECATED]: To block specific commands, use the"

### Axis 2: OS sandbox and default modes

**C8 [HR]. The legacy whole-process sandbox is off by default (`tools.sandbox` default `undefined`). Options are `GEMINI_SANDBOX=true|docker|podman|sandbox-exec|runsc|lxc`. The macOS Seatbelt default profile is `permissive-open`.**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/docs/cli/sandbox.md (Google, undated, official_docs)
- Quote: "**Default profile**: `permissive-open` - denies operations by default; confines writes to the project directory while allowing broad file reads and network access."
- Quote: "`permissive-open` (default): Write restrictions, network allowed"
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/docs/reference/configuration.md
- Quote: "**`security.toolSandboxing`** (boolean):"
- Quote: "Tool-level sandboxing. Isolates individual tools instead of     the entire CLI process."
- Note: the raw file wraps this sentence. The source text is "Isolates individual tools instead of" + newline + "    the entire CLI process.", so the quote contains a line break and four spaces.
- Default: the configuration.md entry for `security.toolSandboxing` lists `**Default:** \`false\``.

**C9. The newer per-tool sandbox has a per-mode policy. In plan mode it is read-only with no network and no approved tools. On Linux it is bwrap-based: the workspace is mounted `--ro-bind-try` unless the mode allows writes, the command is in `approvedTools`, or YOLO is on.**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/policy/policies/sandbox-default.toml (Google, last commit 2026-06-11, repository)
- Quote: `[modes.plan] network = false readonly = true approvedTools = []` (whitespace collapsed)
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/sandbox/linux/LinuxSandboxManager.ts
- Quote: `const workspaceWrite = !isReadonlyMode || isApproved || isYolo;`
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/sandbox/linux/bwrapArgsBuilder.ts (2026-04-16)
- Quote: `const bindFlag: MountType = workspaceWrite ? '--bind-try' : '--ro-bind-try';`
- Caveat: tool sandboxing is off by default (C8). So by default a shell command in plan mode is not run in a read-only sandbox. Instead it is denied by policy (C10).

### Axis 3: Approval and permission rule design, and plan mode

**C10. Plan mode denies every tool by default (priority 40). Only listed read-only tools are allowed, and `run_shell_command` is not among them. Writes are allowed only for `.md` files in the plans directory.**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/policy/policies/plan.toml (Google, last commit 2026-07-13, repository)
- Quote: `denyMessage = "You are in Plan Mode with access to read-only tools. Execution of scripts (including those from skills) is blocked."`

**C11. Users can allow shell prefixes in plan mode through TOML rules. The docs give `git status` and `git diff` as the example. An approval granted in plan mode applies to all modes.**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/docs/cli/plan-mode.md (Google, undated, official_docs)
- Quote: `commandPrefix = ["git status", "git diff"]`
- Source: policy-engine.md
- Quote: "**Approvals in `plan` mode**: These represent an intentional choice to trust a   tool globally."
- Note: the raw file wraps this line. The source text is "to trust a" + newline + "  tool globally.", so the quote contains a line break and two spaces.

**C12. Rule priority tiers are Admin > User > Workspace > Extension > Default. YOLO mode allows everything, including redirection and substitution.**
- Source: https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/packages/core/src/policy/policies/yolo.toml
- Quote: `allowRedirection = true allowCommandSubstitution = true` (whitespace collapsed)

### Axis 4: `python -c`

**C13 (inference from C6/C10).** `python` is not on the known-safe list (C6). In default mode, `python -c "print(1)"` therefore falls to ASK_USER. In plan mode, `run_shell_command` hits the catch-all deny (C10). A user-added plan-mode rule such as `commandPrefix="python"` would let it through. If `security.toolSandboxing` is on, it would then run with the workspace mounted read-only (C9). No interpreter-specific rule was found. **No evidence found** of any special handling for `python -c`.

### Axis 5: Bypasses, CVEs, and vendor responses

**C14 [HR]. Tracebit, June-July 2025.** Allowlist matching was cursory: `grep ...; <exfil>` was treated as "grep". The bug was reported 2025-06-27 and fixed in v0.1.14 on 2025-07-25. Google triaged it at P2/S4 and later reclassified it as P1/S1.
- Source: https://tracebit.com/blog/code-exec-deception-gemini-ai-cli-hijack (Tracebit, 2025-07-28, blog)
- Quote: "For the purposes of comparison to the whitelist, Gemini would consider this to be a ‘grep’ command, and execute it without asking the user again."
- Quote: "This discovery was ultimately classified by Google VDP as a P1 / S1 issue and fixed in v0.1.14 released July 25 with agreed disclosure date July 28."
- Second org: press coverage (scworld.com, itpro.com) returned 403 or was not fetched. Tracebit is the only verified source.

**C15 [HR]. GHSA-wpqr-6v78-jr5g / CVE-2026-12537 (critical, 2026-04-24).** Under `--yolo`, a fine-grained tool allowlist such as `run_shell_command(echo)` was ignored. Fixed in 0.39.1, which also changed headless folder trust.
- Source: https://api.github.com/advisories/GHSA-wpqr-6v78-jr5g (GitHub Advisory DB / Google, 2026-04-24, advisory)
- Quote: "it would ignore any fine grained tool allowlist in `~/.gemini/settings.json` (e.g. `run_shell_command(echo)` would allow any command)."
- Quote: "In version `0.39.1`, the Gemini CLI policy engine now evaluates tool allowlisting under `--yolo` mode"
- Second org: https://labs.cloudsecurityalliance.org/research/csa-research-note-gemini-cli-supply-chain-cvss10-20260506-cs/ (Cloud Security Alliance, 2026-05-06, blog)
- Quote: "Google corrected this in version 0.39.1 by reworking the policy enforcement path for --yolo mode"

---

## (b) Cursor (IDE and cursor-agent CLI)

### Axis 1: Static judgment

**K1. The allowlist (`terminalAllowlist` in permissions.json) uses case-sensitive prefix semantics, and `cmd:argsglob` is supported. The CLI uses `Shell(commandBase)`, where commandBase is the first token.**
- Source: https://cursor.com/docs/reference/permissions.md (Cursor, undated, official_docs)
- Quote: "Matching is case-sensitive and uses prefix semantics: `git` matches `git status` but not `gitk`."
- Source: https://cursor.com/docs/cli/reference/permissions.md (Cursor, undated, official_docs)
- Quote: "The `commandBase` is the first token in the command line. Supports glob patterns and an optional `command:args` syntax for finer control."

**K2 [HR]. The parser is closed source and runs on the server. CVE-2025-54131 (backtick and `$()` bypass) was fixed in 1.3 by "a more robust parser". CVE-2026-22708 (shell built-ins such as `export`/`typeset`/`declare` were not on the allowlist but still ran) was fixed in 2.3: commands the server-side parser cannot classify now need approval.**
- Source: https://github.com/cursor/cursor/security/advisories/GHSA-534m-3w6r-8pqr (Cursor, 2025-08-01, advisory)
- Quote: "The allowlist logic has switched to a more robust parser."
- Source: NVD CVE-2025-54131 (NIST, 2025-08-01, government)
- Quote: "an attacker can bypass the allow list in auto-run mode with a backtick (`) or $(cmd)."
- Source: https://github.com/cursor/cursor/security/advisories/GHSA-82wg-qcm4-fp2w (Cursor, 2026-01-14, advisory)
- Quote: "Terminal command parsing around edge cases was improved."
- Source: https://pillar.security/blog/the-agent-security-paradox-when-trusted-commands-in-cursor-become-attack-vectors (Pillar Security, 2026-01-14, blog)
- Quote: "Cursor addressed the issue by requiring explicit user approval for any commands that the server-side parser is not able to classify."
- Quote: "It exploits shell built-in commands like export, typeset, and declare, which Cursor's server-side evaluator implicitly trusts and executes without user approval"

### Axis 2: OS sandbox and defaults

**K3 [HR]. Sandbox backends: Seatbelt (`sandbox-exec`) on macOS. Landlock+seccomp on Linux (kernel 6.2 or later), with a bubblewrap fallback. If the kernel is unsupported, Cursor falls back to asking for approval.**
- Source: https://cursor.com/docs/agent/security/run-modes.md (Cursor, changelog through 2026-10-01, official_docs)
- Quote: "Cursor uses Landlock and seccomp. Landlock applies filesystem restrictions. Seccomp blocks unsafe syscalls."
- Quote: "If your kernel does not meet these requirements, Cursor falls back to asking for approval before running commands."
- Second org: not found. The Cursor blog (https://cursor.com/blog/agent-sandboxing, 2026-02-18) is the same org. Quote: "Seccomp blocks unsafe syscalls, while Landlock enforces filesystem restrictions, letting us make ignored files completely inaccessible to the sandboxed process."

**K4. Sandbox defaults: read/write in the workspace. Protected paths include `.git/config`, `.git/hooks` and `.vscode`. Network is blocked by default and then opened per network mode, where "sandbox.json + Defaults" is the default. `/tmp` is writable.**
- Source: run-modes.md
- Quote: "Cursor protects paths like `.git/config`, `.git/hooks`, `.vscode`, `.cursorignore`, and sensitive Cursor config files."
- Quote: "Blocked by default, then opened by your network mode and [`sandbox.json`]"
- Note: in run-modes.md this quote is followed by the link target "(https://cursor.com/docs/reference/sandbox.md)" and ". |". The quote stops at the link text.

**K5 [HR]. Run modes (since 3.5/3.6, May 2026) are Auto-review (the default), Allowlist (sandbox optional), and Run Everything. "Ask Every Time" is deprecated. In Auto-review, unlisted shell commands run in the sandbox without a prompt. Commands that cannot be sandboxed, or that fail on a sandbox restriction, go to an LLM classifier on the server (Gemini 3.5 Flash Lite, falling back to Haiku).**
- Source: run-modes.md
- Quote: "Allowlisted calls run immediately. Other shell commands run in the sandbox when possible. Calls that do not use the sandbox go to the Auto-review classifier."
- Quote: "**Ask Every Time** was deprecated. New users cannot choose it. Use **Allowlist** with an empty allowlist for the same behavior."
- Quote: "The classifier can make mistakes. It can allow a call you would have blocked, or block a call you would have allowed."

**K6 [HR]. Cursor says sandboxed agents stop 40% less often.**
- Source: https://cursor.com/blog/agent-sandboxing (Cursor, 2026-02-18, official_blog)
- Quote: "Sandboxed agents stop 40% less often than unsandboxed ones, saving users hours of manual review and approval."

### Axis 3: Approval design, and plan and ask modes

**K7. Auto-review steering is a plain-English `allow_instructions`/`block_instructions` list, described as "steering, not enforcement". Allowlisted calls run outside the sandbox.**
- Source: https://cursor.com/docs/reference/permissions.md
- Quote: "Treat both as steering, not enforcement."

**K8 [forum, unofficial]. Ask mode removes edit and MCP tools. As of July 2026 the terminal was not hard-blocked at the tool level; write protection relied on a read-only sandbox. After August 2026, shell in Ask mode is fully disabled where no OS sandbox is available. The poster `deanrie` replies like support staff, but the forum JSON shows `staff: false`, so the affiliation is unverified.**
- Source: https://forum.cursor.com/t/164600 (forum.cursor.com, 2026-07-02 and 2026-08-25, forum)
- Quote: "Ask mode removes edit apply and MCP tools, but the terminal itself isn’t hard blocked at the tool level. Write protection relies on a read only sandbox, which isn’t always active yet."
- Quote: "on environments where the OS sandbox isn’t available (like Windows in your case), Shell in Ask mode is currently disabled entirely, with no allowlist-aware middle option."

**K9. Plan mode docs say nothing about shell restrictions.** The page describes research and plan files only. **No evidence found** of how Cursor Plan mode handles terminal commands.
- Source: https://cursor.com/docs/agent/plan-mode.md (Cursor, undated, official_docs)
- Quote: "Plan Mode creates detailed implementation plans before writing any code. Agent researches your codebase, asks clarifying questions, and generates a reviewable plan you can edit before building."

### Axis 4: `python -c`

**K10.**
- (Inference from K5) In Auto-review, `python -c` is not allowlisted, so it runs inside the sandbox without a prompt: workspace writes are possible, network is limited, and protected paths are blocked. If it fails on a sandbox restriction, the rerun goes to the classifier.
- (Forum report, unofficial) A user tested the CLI with `--mode ask --sandbox enabled` and reported shell, including `python3`, as "Blocked". Same thread, user dvdvdmt, 2026-09-06. Quote: "Shell (incl. pwd / echo / ls . / python3)"
- No interpreter-specific rule was found in the docs.

### Axis 5: CVEs and bypasses

**K11 [HR]. Backslash, 2025-07-21.** The denylist was bypassed with Base64, subshells, scripts, and quoting. Cursor deprecated the denylist in 1.3.
- Source: https://www.backslash.security/blog/cursor-ai-security-flaw-autorun-denylist (Backslash Security, 2025-07-21, blog)
- Quote: "The Cursor team acknowledged the issues we discovered and eventually informed us that they are “officially deprecating the denylist feature in release 1.3.”"
- Quote: "Commands can also be run without triggering the denylist if they are enclosed in a subshell"

**K12 [HR]. Other Cursor CVEs relevant to the shell gate and sandbox (NVD descriptions, government source):**
- CVE-2025-54135 (CurXecute, fixed in 1.3.9). Quote: "if sensitive MCP files, such as the .cursor/mcp.json file don't already exist in the workspace, an attacker can chain a indirect prompt injection vulnerability to hijack the context to write to the settings file and trigger RCE"
- CVE-2025-54136 (MCPoison, fixed in 1.3). Quote: "Once a collaborator accepts a harmless MCP, the attacker can silently swap it for a malicious command (e.g., calc.exe) without triggering any warning or re-prompt."
- CVE-2026-26268 (fixed in 2.5). Quote: "Sandbox escape via writing .git configuration was possible in versions prior to 2.5."
- CVE-2026-31854 (fixed in 2.0). Quote: "When combined with a bypass of the command whitelist mechanism, such indirect prompt injections could result in commands being executed automatically"
- CVE-2026-50548 (fixed in 3.0). Quote: "A malicious agent could set working_directory to a sensitive location and write arbitrary files outside the workspace under the user's privileges."
- CVE-2026-50549 (fixed in 3.0). Quote: "when canonicalization fails it falls back to the original path and writes without approval."
- CVE-2026-73217 (fixed in 3.1.2). Quote: "allows an agent running in Auto-Run Sandbox mode to replace a virtual environment's Python executable with a malicious wrapper that the Microsoft Python extension invokes outside the sandbox"
- CVE-2026-73218 (fixed in 3.0.0). Quote: "to launch a privileged container and mount Docker's virtiofs0, granting read and write access to the user's home directory"

---

## (c) GitHub Copilot

### Axis 1: Static judgment

**G1. VS Code checks each subcommand. A compound command is auto-approved only if every part matches a `true` rule and none matches a `false` rule. `false` takes precedence. Regex rules are written as `/.../`.**
- Source: https://code.visualstudio.com/docs/agents/run/approvals.md (Microsoft, undated, official_docs)
- Quote: "By default, rules match each subcommand. A compound command is auto-approved only when all its subcommands match a `true` rule and none match a `false` rule."
- Source: https://raw.githubusercontent.com/microsoft/vscode/main/src/vs/workbench/contrib/terminalContrib/chatAgentTools/common/terminalChatAgentToolsConfiguration.ts (Microsoft, last commit 2026-11-06, repository)
- Quote: "Inline commands such as {5} (process substitution) should also be detected."

**G2. The parser is tree-sitter (bash and PowerShell grammars). Syntax that cannot be analyzed, such as shell-state mutations, forces auto-approve off. Microsoft calls auto-approve "not a security boundary".**
- Source: https://raw.githubusercontent.com/microsoft/vscode/main/src/vs/workbench/contrib/terminalContrib/chatAgentTools/browser/tools/commandLineAnalyzer/commandLineAutoApproveAnalyzer.ts (Microsoft, 2026-10-30, repository)
- Quote: `// Shell-state mutations omitted from normal command extraction must never` / `// auto-approve, even when every extracted sub-command matches an allow rule.`
- Source: approvals.md
- Quote: "Terminal auto-approval is a best-effort convenience, not a security boundary."
- Quote: "The PowerShell and bash tree-sitter grammars might not identify every subcommand."

**G3. Default rules.**
- Rule entries:
  - `find: true` together with `/^find\b.*\s-(delete|exec|execdir|fprint|fprintf|fls|ok|okdir)\b/: false`
  - sed: `-e`, `-f`, and `e`/`w`/`r` script commands are set to false. `-i` is not listed; it is left to file-write detection.
  - git: status/log/show/diff/ls-files/grep/branch are true, with `--output`, `-O` and branch `-d/-D/-m/-M` set to false.
  - `rm`, `curl`, `wget`, `jq`, `xargs`, `eval` are false.
  - No python entry.
- Source: https://raw.githubusercontent.com/microsoft/vscode/main/src/vs/platform/terminal/common/autoApprove/defaultAutoApproveRules.ts (Microsoft, 2026-10-30, repository)
- Quote: `'/^find\\b.*\\s-(delete|exec|execdir|fprint|fprintf|fls|ok|okdir)\\b/': false,`
- Quote: `// - In-place editing (\`-i\`, \`-I\`, \`--in-place\`) is detected and blocked via file write` (in the source the backticks are not escaped: `` (`-i`, `-I`, `--in-place`) ``)
- Quote: `// Workspace trust and warnings of` / `// possible prompt injection are _the_ thing protecting the user in agent mode`
- Quote (git, from https://raw.githubusercontent.com/microsoft/vscode/main/src/vs/platform/terminal/common/autoApprove/gitAutoApproveRules.ts, 2026-09-22): `'/^git(\\s+(-(?-i:C)\\s+\\S+|--no-pager))*\\s+status\\b/': true,`

**G4. Copilot CLI: closed-source "shell safety assessment" sorts commands into read-only and write-capable. Read-only commands run automatically.**
- Source: https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/allowing-tools (GitHub, undated, official_docs)
- Quote: "Read-only operations like searching, reading files, and running read-only shell commands are generally allowed automatically, subject to applicable policy."
- Source: https://github.com/github/copilot-cli/security/advisories/GHSA-g8r9-g2v8-jv6f (GitHub, 2026-03-06, advisory)
- Quote: "The safety layer parses and classifies shell commands as either read-only (safe) or write-capable (requires user approval)."
- Pattern syntax (CLI reference, https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference). Quote: "For `shell` rules, the `:*` suffix matches the command stem followed by a space, preventing partial matches."
- **No evidence found** of how `--allow-tool` treats `&&` or pipes.

### Axis 2: OS sandbox and defaults

**G5. VS Code agent sandbox: setting `chat.agent.sandbox.enabled`, default `off`. Seatbelt on macOS 15 or later. bubblewrap 0.5 or later on Linux and WSL2. Network is allowed by default.**
- Source: https://code.visualstudio.com/docs/agents/run/agent-sandboxing.md (Microsoft, undated, official_docs)
- Quote: "The `setting(chat.agent.sandbox.enabled)` setting controls sandboxing on all supported platforms. It accepts `off` or `on` and defaults to `off`."
- Quote: "Turning on sandboxing does not block outbound network access by default."
- Setting name: the task mentions `chat.tools.terminal.sandbox`. The current source (`src/vs/platform/sandbox/common/settings.ts`) defines `AgentSandboxEnabled = 'chat.agent.sandbox.enabled'`. No migration entry from the old name was found in the fetched files (only `chat.agent.sandbox.allowNetwork` is migrated).

**G6. In Copilot harness sessions, the runtime can approve read-only or sandboxed commands before the terminal rules run, even when a `false` rule matches.**
- Source: approvals.md
- Quote: "In **Copilot** harness sessions, the runtime can approve read-only commands or sandboxed commands before terminal approval rules are evaluated. These calls do not prompt, even with a matching `false` rule"

**G7. Copilot CLI and app local sandbox: off by default. Uses MXC, which is Seatbelt on macOS and bubblewrap on Linux. Commands blocked by the sandbox prompt for an unsandboxed rerun, since `allowBypass` defaults to on.**
- Source: https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/about-cloud-and-local-sandboxes (GitHub, undated, official_docs)
- Quote: "Local sandboxing is turned off by default. Until you enable it, the shell commands that Copilot runs execute directly on your machine with the same access as your user account"
- Quote: "**Linux** uses the bubblewrap backend."

**G8. Copilot cloud agent: runs in a cloud sandbox or a GitHub Actions job behind a firewall. The firewall covers only processes started by the Bash tool. Branch and push are restricted, and workflows need approval.**
- Source: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/customize-the-agent-firewall (GitHub, undated, official_docs)
- Quote: "The firewall applies to processes started by the agent through its Bash tool."
- Source: https://docs.github.com/en/copilot/concepts/agents/cloud-agent/risks-and-mitigations
- Quote: "Copilot cloud agent can only perform simple push operations. It cannot directly run `git push` or other Git commands."

### Axis 3: Approval design and plan mode

**G9. In Copilot CLI plan mode, commands that would change workspace files are blocked by enforcement, not by prompt. Commands whose effect cannot be determined are allowed through ("safety net, not a guarantee").**
- Source: CLI command reference (GitHub, undated, official_docs)
- Quote: "Any attempt to edit, patch, or run a shell command that would change a file in your workspace is blocked automatically—this isn't just a suggestion to the model, it's enforced directly"
- Quote: "Some things are intentionally allowed through so research isn't overly restricted: for example, shell commands whose effect can't be clearly determined in advance, and calls to external/MCP tools you've connected."

**G10. "Assisted permissions" (CLI, VS Code, app): existing rules run first, then an LLM reviews eligible requests. In autopilot or non-interactive runs, anything still unresolved is denied.**
- Source: https://docs.github.com/en/copilot/concepts/customizations/allowing-safe-commands (GitHub, undated, official_docs)
- Quote: "It uses a large language model to review permission requests and automatically approve actions it judges to be safe in the context of your task."
- Quote: "In autopilot mode and non-interactive runs, requests that still require your approval are denied instead."

**G11. VS Code Plan agent: read-only by default. Its terminal handling is not documented.** **No evidence found** of whether the Plan agent can run terminal commands.
- Source: https://code.visualstudio.com/docs/agents/run/planning.md (Microsoft, undated, official_docs)
- Quote: "Additional tools can expand the agent's capabilities beyond its default read-only project access."

### Axis 4: `python -c`

**G12 (inference).**
- VS Code: python has no default rule (G3), so `python -c` needs manual approval unless the user adds a rule. In a Copilot harness session with the sandbox on, the runtime "can approve ... sandboxed commands" (G6), so it could run without a prompt inside the sandbox.
- Copilot CLI: `python -c` is not a read-only command (G4), so it needs manual approval, or LLM review in assisted mode (G10).
- No interpreter-specific rule was found for either.

### Axis 5: CVEs and bypasses

**G13 [HR]. CVE-2025-53773 (August 2025 Patch Tuesday).** The agent could write `"chat.tools.autoApprove": true` to `.vscode/settings.json` without approval, which turned on YOLO mode.
- Source: NVD CVE-2025-53773 (NIST, 2025-08-12, government)
- Quote: "Improper neutralization of special elements used in a command ('command injection') in GitHub Copilot and Visual Studio allows an unauthorized attacker to execute code locally."
- Second org: https://embracethered.com/blog/posts/2025/github-copilot-remote-code-execution-via-prompt-injection/ (Embrace The Red, 2025-08-12, blog)
- Quote: "\"chat.tools.autoApprove\": true This will put GitHub Copilot in YOLO mode."
- Quote: "With the August Patch Tuesday release this is now fixed."
- Note: the page text uses straight double quotes around chat.tools.autoApprove. The `\"` above is JSON-style escaping and is not part of the quote.

**G14 [HR]. CVE-2026-29783 / GHSA-g8r9-g2v8-jv6f (Copilot CLI ≤0.0.422, fixed in 0.0.423, 2026-03-06).** Parameter expansion slipped past the read-only classifier: `${var@P}`, `${var=value}`, `${!var}`, and `$()` nested inside `${}`. The fix downgrades these to write-capable and blocks them outright, even in `--yolo`.
- Source: GHSA-g8r9-g2v8-jv6f (GitHub, 2026-03-06, advisory)
- Quote: "Commands with dangerous expansion patterns are unconditionally blocked at the tool execution layer — regardless of permission mode (including --yolo / autopilot)."
- Second org: NVD (NIST, 2026-03-06, government)
- Quote: "The specific dangerous patterns are ${var@P}, ${var=value} / ${var:=value}, ${!var}, and nested $(cmd) or <(cmd) inside ${...} expansions."

**G15 [HR]. CVE-2026-45033 / GHSA-9ccr-r5hg-74gf (Copilot CLI, fixed in 1.0.43).** A nested bare repo runs `core.fsmonitor` during `git status/diff`. Fixed by setting `safe.bareRepository=explicit` through `GIT_CONFIG_*` environment variables.
- Source: NVD (NIST, 2026-05-13, government)
- Quote: "git's core.fsmonitor config key (and 15+ similar keys such as core.hookspath, diff.external, merge.tool, etc.) can specify arbitrary shell commands that git will execute as part of normal operations like status, diff, or rev-parse."
- Source: GHSA-9ccr-r5hg-74gf (GitHub, 2026-05-06, advisory)
- Quote: "The fix sets safe.bareRepository=explicit via git's GIT_CONFIG_COUNT / GIT_CONFIG_KEY_* / GIT_CONFIG_VALUE_* environment variable mechanism"

**G16 [HR]. Other 2026 Copilot and VS Code command-injection CVEs (NVD, descriptions only, no technical details):** CVE-2026-21256, -21257, -21516, -21518 (2026-02-10; -21518 is a "bypass a security feature" variant), CVE-2026-70335 (2026-08-11), CVE-2026-81380 (2026-09-08), CVE-2026-83953 (2026-11-10). Example quote for CVE-2026-21518: "Improper neutralization of special elements used in a command ('command injection') in GitHub Copilot and Visual Studio Code allows an unauthorized attacker to bypass a security feature over a network"

---

## Cross-cutting notes relevant to dcode

1. **Git config execution sits behind "read-only" git** in three tools: Gemini rejects `git -c`, Cursor protects `.git/config` and hooks (CVE-2026-26268), and Copilot CLI hit CVE-2026-45033 through nested bare repo fsmonitor. A static "git status is read-only" verdict is not enough without `safe.bareRepository=explicit` or protected config.
2. **The parse-failure policy converges on ASK.** Gemini (C1), VS Code (G2: unanalyzable syntax means no auto-approve), Cursor 2.3 (K2: unclassifiable commands need approval), and Copilot CLI 0.0.423 (G14: dangerous `${}` forms are blocked).
3. **Gemini's `commandSafety.ts` is the closest open-source match for a read-only judgment.** Its find/git/sed/rg/base64 flag lists can be copied as-is.

## Not covered

- Cursor's and Copilot CLI's parsers are closed source, so their compound-command behavior is known only from docs and advisories.
- MSRC pages for the 2026 VS Code CVEs were not fetched.
- The Tracebit claim has no independent second source.
- The press coverage at scworld and THN returned 403.

## EXPAND

- LEAD: Gemini CLI `shell-safety-regression.test.ts` and `shell-substitution.test.ts` in packages/core/src/policy — WHY: concrete bypass test vectors that dcode can reuse as fixtures — ANGLE: curl the raw files at commit b977656 and extract test command strings
- LEAD: VS Code `treeSitterCommandParser.ts` and the `extractAutoApprovalSubCommands` / `hasUnanalyzableSyntax` definition — WHY: shows exactly which bash node types count as "unanalyzable" (e.g. `export`, `cd`, assignments) — ANGLE: raw.githubusercontent.com microsoft/vscode main src/vs/workbench/contrib/terminalContrib/chatAgentTools/browser/treeSitterCommandParser.ts
- LEAD: VS Code `chat.tools.terminal.blockDetectedFileWrites` implementation, which detects `-i` and redirects — WHY: shows how VS Code handles `sed -i` and `>` without a regex — ANGLE: grep the vscode repo for blockDetectedFileWrites and commandLineFileWriteAnalyzer
- LEAD: CVE-2026-21518 / CVE-2026-70335 MSRC write-ups — WHY: possibly a VS Code terminal auto-approve bypass — ANGLE: msrc.microsoft.com update-guide, researcher blogs naming the CVE
- LEAD: Copilot CLI `copilot help permissions` output, or a GitHub issue on `&&` handling — WHY: compound-command semantics for `--allow-tool` are undocumented — ANGLE: github.com/github/copilot-cli issues search "allow-tool &&"
- LEAD: Cursor forum "Configurable read-only shell access in Ask Mode" feature request and any Plan-mode shell docs — WHY: Cursor's Plan-mode shell policy is unknown — ANGLE: forum.cursor.com search "plan mode terminal"
- LEAD: GuardFall (Adversa AI, disclosed 2026-06-30) — WHY: a taxonomy of quote-removal/IFS/base64 evasions against text-based guards; it did not test Gemini, Cursor or Copilot, but applies to dcode — ANGLE: adversa.ai blog opensource-ai-coding-agents-shell-injection
- DEAD END: scworld.com and thehackernews.com articles (HTTP 403)
- DEAD END: GitHub REST API listing of the cursor/cursor and gemini-cli repository advisories (rate-limited or empty). Used NVD keyword search instead.
