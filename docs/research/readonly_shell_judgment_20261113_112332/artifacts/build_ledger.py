#!/usr/bin/env python3
"""Builds sources/sources.jsonl and artifacts/claim_ledger.jsonl for this session.

Data comes from artifacts/agent_results/*.md (agent findings with verbatim quotes),
orchestrator counter-searches (artifacts/expansion_log.md), and local experiments (artifacts/exec/).
Grades are fixed per domain (one grade per domain, gate rule). Risk is assigned by the
skill definition (dates/versions/CVE ids/numbers/causal = high) before running the gate.
"""
import json
import os

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBS = "2026-11-13T02:30:00Z"
GRADE = {  # one grade per domain
    "local": "B", "code.claude.com": "B", "www.anthropic.com": "B", "github.com": "B",
    "raw.githubusercontent.com": "B", "learn.chatgpt.com": "B", "nvd.nist.gov": "A",
    "man7.org": "B", "docs.kernel.org": "B", "cursor.com": "B", "geminicli.com": "B",
    "docs.github.com": "B", "code.visualstudio.com": "B", "docs.cline.bot": "B", "docs.roocode.com": "B",
    "ampcode.com": "B", "docs.all-hands.dev": "B", "aider.chat": "B", "opencode.ai": "B",
    "blog.trailofbits.com": "C", "flatt.tech": "D", "specterops.io": "D", "cymulate.com": "D",
    "embracethered.com": "D", "finisky.github.io": "D", "arrangeactassert.com": "D",
    "blakecrosley.com": "D", "codex.danielvaughan.com": "D", "www.pillar.security": "D",
    "arxiv.org": "D", "research.checkpoint.com": "D", "claudeissues.com": "E",
    "alexcloudstar.com": "D", "www.qualys.com": "C", "ubuntu.com": "B", "tracebit.com": "D",
    "www.backslash.security": "D", "hiddenlayer.com": "D", "osv.dev": "B",
    "tangled.org": "E", "nhimg.org": "D", "docs.curiosity.ai": "D", "openai.com": "B", "bugs.launchpad.net": "C", "securitybrief.asia": "D", "docs.openhands.dev": "B", "adversa.ai": "D", "goose-docs.ai": "B", "zed.dev": "B", "api.github.com": "B", "labs.cloudsecurityalliance.org": "D", "pillar.security": "D", "forum.cursor.com": "E",
}

SOURCES = []


def src(sid, url, title, org, typ, date, snippet, domain=None):
    dom = domain or url.split("://", 1)[-1].split("/", 1)[0]
    SOURCES.append({
        "id": sid, "url": url, "title": title, "org": org, "domain": dom, "type": typ,
        "quality_rating": GRADE[dom], "date": date, "valid_at": date, "observed_at": OBS,
        "snippet": snippet, "access": {"layer": "webfetch" if dom != "local" else "local-run"},
    })


EXEC = "file:///home/sds/workspace/dcode-assistant/docs/research/readonly_shell_judgment_20261113_112332/artifacts/exec/"
# --- local experiments
src("src_l01", EXEC + "run_tests.out", "Landlock read-only probe run (run_tests.sh)", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")
src("src_l02", EXEC + "metadata_socket_probe.out", "Landlock gaps probe (chmod/utime/unix socket)", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")
src("src_l03", EXEC + "ro_mount_socket_probe.out", "Read-only bind mount probe", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")
src("src_l04", EXEC + "wsl_interop_probe.out", "WSL interop probe under Landlock", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")
src("src_l05", EXEC + "userns_ro_bind.out", "userns rbind + ro remount probe", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")
src("src_l06", EXEC + "drvfs_probe.out", "Landlock on drvfs /mnt/c and /dev/shm", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")

src("src_l07", EXEC + "mount_setattr_probe.out", "Recursive read-only mount launcher probe", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")
src("src_l09", EXEC + "ro_launcher_probe.out", "Final prototype launcher probe (ro_launcher.py)", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")
src("src_l08", EXEC + "bus_escape_probe.out", "systemd user bus escape probe", "local-experiment", "primary", "2026-11-13", "probe outputs", "local")

# --- Claude Code
src("src_a01", "https://code.claude.com/docs/en/permissions.md", "Claude Code docs: Permissions", "anthropic", "official_docs", "undated", "The recognized command separators are `&&`, `||`, `;`, `|`, `|&`, `&`, and newlines. Every subcommand must be allowed for a compound command to run without a prompt")
src("src_a02", "https://code.claude.com/docs/en/permission-modes.md", "Claude Code docs: Permission modes", "anthropic", "official_docs", "undated", "Auto mode not available, or `useAutoModeDuringPlan` off: commands outside the built-in read-only set prompt for approval")
src("src_a03", "https://code.claude.com/docs/en/sandboxing.md", "Claude Code docs: Sandboxing", "anthropic", "official_docs", "undated", "The sandbox runs on macOS, Linux, and WSL2. ... The sandbox is off by default.")
src("src_a04", "https://github.com/anthropic-experimental/sandbox-runtime", "sandbox-runtime README", "anthropic", "repository", "undated", "`srt` uses native OS sandboxing primitives (`sandbox-exec` on macOS, `bubblewrap` on Linux) and proxy-based network filtering.")
src("src_a05", "https://www.anthropic.com/engineering/claude-code-sandboxing", "Beyond permission prompts: Claude Code sandboxing", "anthropic", "official_blog", "2025-10-20", "In our internal usage, we've found that sandboxing safely reduces permission prompts by 84%.")
src("src_a06", "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md", "Claude Code CHANGELOG", "anthropic", "official_release", "2026-11", "Fixed sandbox auto-allow asking for approval on every run of many inline scripts (`python3 -c`, `node -e`) just because they contain `=`")
src("src_a07", "https://specterops.io/blog/2025/11/21/an-evening-with-claude-code/", "An Evening with Claude Code", "specterops", "blog", "2025-11-21", "a request out to Anthropic's Haiku model with the prompt: <policy_spec> # Claude Code Code Bash command prefix detection")
src("src_a08", "https://flatt.tech/research/posts/pwning-claude-code-in-8-different-ways", "Pwning Claude Code in 8 different ways", "gmo-flatt-security", "blog", "2026-01-12", "Anthropic was very responsive and addressed these issues by introducing an allowlist approach instead of the previous blocklist approach.")
src("src_a09", "https://cymulate.com/blog/cve-2025-547954-54795-claude-inverseprompt/", "InversePrompt: CVE-2025-54795", "cymulate", "blog", "undated", "A template for this injection could be: echo ...")
src("src_a10", "https://embracethered.com/blog/posts/2025/claude-code-exfiltration-via-dns-requests/", "Claude Code exfiltration via DNS requests", "embrace-the-red", "blog", "2025-08-11", "ping , nslookup , host and dig can be used to leak data!")
src("src_a11", "https://finisky.github.io/en/claude-code-bash-security", "Claude Code bash security (leaked-source analysis)", "finisky", "blog", "2026-04-05", "It parses commands into an AST with Tree-Sitter, then walks the tree against an explicit allowlist")
src("src_a12", "https://arrangeactassert.com/posts/claude-code-sandbox-close-the-gaps-before-you-auto-allow/", "Claude Code sandbox: close the gaps before you auto-allow", "arrange-act-assert", "blog", "2026-06-30", "On macOS it uses Apple's Seatbelt framework. On Linux and WSL2 it uses bubblewrap for filesystem isolation and a proxy for network control.")
src("src_a13", "https://nvd.nist.gov/vuln/detail/CVE-2025-66032", "NVD CVE-2025-66032", "nist", "government", "2025-12-03", "Prior to 1.0.93, due to errors in parsing shell commands related to $IFS and short CLI flags")
src("src_a14", "https://nvd.nist.gov/vuln/detail/CVE-2025-64755", "NVD CVE-2025-64755", "nist", "government", "2025-11-21", "Prior to version 2.0.31, due to an error in sed command parsing")
src("src_a15", "https://github.com/anthropics/claude-code/security/advisories/GHSA-xq4m-mc3c-vvg3", "GHSA-xq4m-mc3c-vvg3", "anthropic", "advisory", "2025-12-03", "Due to errors in parsing shell commands related to $IFS and short CLI flags")
src("src_a16", "https://alexcloudstar.com/md/blog/claude-code-plan-mode-2026/", "Claude Code Plan Mode (2026 guide)", "alexcloudstar", "blog", "2026", "you will see Claude run read-only commands freely and ask before anything that could change state (WebFetch-confirmed)")
src("src_a17", "https://claudeissues.com/issue/45072-bug-recent-seccomp-change-for-sandbox-broke-executing-windows-tools-from-wsl", "Claude Code issue #45072 mirror: seccomp change broke Windows tools from WSL", "claudeissues", "forum", "2026", "the sandbox's seccomp filter blocked connect() on Unix sockets, which stopped all .exe launches from WSL2 (search-result summary)")
src("src_a18", "https://osv.dev/vulnerability/CVE-2025-66032", "OSV CVE-2025-66032", "osv", "advisory", "2025-12-03", "counter-search result: no dispute of the 1.0.93 fix found")

# --- Codex
src("src_b01", "https://github.com/openai/codex/commit/942af8447b1d1addc81fb3c3135293497d479a06", "Codex PR #39630: retire untrusted / remove known-safe allowlist", "openai", "repository", "2026-08-20", "Remove the known-safe command allowlist. Projects marked untrusted now request approval for every command unless an explicit exec policy rule allows it.")
src("src_b02", "https://github.com/openai/codex/commit/3b45c29062ff0e76e71c91b6753290400e7fa8da", "Codex PR #39524: remove Git from safe list", "openai", "repository", "2026-08-19", "Repository configuration can cause even read-only Git commands to execute helpers, so Git command arguments alone are not enough to establish trust.")
src("src_b03", "https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/shell-command/src/bash.rs", "Codex bash.rs (tree-sitter plain-command parser)", "openai", "repository", "2026-11-13", "Any other punctuation like parentheses, braces, redirects, backticks, etc are rejected.")
src("src_b04", "https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/linux-sandbox/README.md", "Codex linux-sandbox README", "openai", "repository", "2026-11-13", "The helper uses bubblewrap for filesystem and namespace isolation, and seccomp for syscall filtering. ... The legacy Landlock option is rejected for these policies because it cannot isolate app-server Unix sockets.")
src("src_b05", "https://learn.chatgpt.com/docs/sandboxing", "Codex docs: Sandboxing", "openai", "official_docs", "undated", "read-only : The agent can inspect files, but it can't edit files or run commands without approval.")
src("src_b06", "https://learn.chatgpt.com/docs/agent-approvals-security", "Codex docs: Agent approvals & security", "openai", "official_docs", "undated", "With on-request , commands allowed by the sandbox can run without approval, read accessible files, and use network access if enabled.")
src("src_b07", "https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/core/src/exec_policy.rs", "Codex exec_policy.rs", "openai", "repository", "2026-11-13", "In restricted sandboxes, do not prompt for non-escalated, non-dangerous commands; let the sandbox enforce restrictions without a user prompt.")
src("src_b08", "https://blakecrosley.com/blog/codex-untrusted-approval-policy-retired", "Codex untrusted approval policy retired", "blakecrosley", "blog", "2026-08-25", "Codex CLI v0.149.0 (stable, August 20, 2026) retired the untrusted approval policy in PR #39630")
src("src_b09", "https://codex.danielvaughan.com/2026/08/31/codex-cli-sandbox-permission-hardening-full-auto-removed-untrusted-retired-fail-closed/", "Codex CLI sandbox permission hardening", "danielvaughan", "blog", "2026-08-31", "PR #39630 ... merged in v0.149.0 (20 August 2026), removes untrusted from the CLI")
src("src_b10", "https://github.com/openai/codex/security/advisories/GHSA-w5fx-fh39-j5rw", "GHSA-w5fx-fh39-j5rw", "openai", "advisory", "2025-09-19", "Codex CLI could treat a model-generated `cwd` as the sandbox's writable root")
src("src_b11", "https://nvd.nist.gov/vuln/detail/CVE-2025-59532", "NVD CVE-2025-59532", "nist", "government", "2025-09-22", "this did not impact the network-disabled sandbox restriction")
src("src_b12", "https://nvd.nist.gov/vuln/detail/CVE-2026-19591", "NVD CVE-2026-19591", "nist", "government", "2026-09-01", "misclassified certain PowerShell commands as safe because their command-safety parser interpreted PowerShell's stop-parsing token (--%) differently")
src("src_b13", "https://raw.githubusercontent.com/openai/codex/553c764e8b99fa519e9c6eb9b657875ef0f5e1c1/codex-rs/collaboration-mode-templates/templates/plan.md", "Codex Plan Mode template", "openai", "repository", "2026-11-13", "You may explore and execute **non-mutating** actions that improve the plan. You must not perform **mutating** actions.")
src("src_b14", "https://www.pillar.security/blog/gitpwned-allowlist-to-rce", "GitPwned: allowlist to RCE", "pillar-security", "blog", "2026-07-20", "OpenAI's Codex CLI trusts git show as a safe command, but git show --output can write arbitrary content to arbitrary files—including .git/config.")
src("src_b15", "https://codex.danielvaughan.com/2026/05/03/codex-cli-sandbox-internals-seatbelt-bubblewrap-landlock-windows-dacl/", "Codex CLI sandbox internals", "danielvaughan", "blog", "2026-05-03", "Bubblewrap is the primary containment tool. ... On older kernels (pre-5.13) or systems where Bubblewrap is unavailable, the driver falls back to Landlock LSM. (WebFetch-confirmed)")
src("src_b16", "https://nvd.nist.gov/vuln/detail/CVE-2026-19592", "NVD CVE-2026-19592", "nist", "government", "2026-09-01", "automatically collected Git repository metadata without disabling the repository-local core.fsmonitor setting")

src("src_b17", "https://codex.danielvaughan.com/2026/05/21/codex-cli-execution-policy-rules-starlark-command-governance-enterprise-allowlists/", "Codex CLI execution policy rules (May 2026)", "danielvaughan", "blog", "2026-05-21", "counter-search result: pre-removal description of known-safe auto-approval (search-result summary)")

src("src_b18", "https://codex.danielvaughan.com/2026/03/27/planning-mode-in-practice/", "Planning Mode in Practice (Codex)", "danielvaughan", "blog", "2026-03-27", "this constraint is enforced at the prompt level only ... there is no runtime sandbox that physically blocks mutations (WebFetch-confirmed)")

src("src_b19", "https://openai.com/security/advisories/cve-2026-19592/", "OpenAI advisory CVE-2026-19592", "openai", "advisory", "2026-09", "Git ran the program as a filesystem monitor (search-result summary)")
src("src_x01", "https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-git-config-rce-20260904-cs/", "CSA: GitSpawn malicious git configs hijack AI coding agents", "cloud-security-alliance", "blog", "2026-09-04", "same root cause affects other agents (search-result summary)")
src("src_x02", "https://bugs.launchpad.net/bugs/2046477", "Launchpad bug 2046477: enable unprivileged userns restrictions by default", "canonical-launchpad", "forum", "2024", "Enable unprivileged user namespace restrictions by default")
src("src_x03", "https://securitybrief.asia/story/tracebit-finds-major-vulnerability-in-google-gemini-cli-tool", "SecurityBrief: Tracebit finds Gemini CLI vulnerability", "securitybrief", "news", "2025-07", "25 July - Gemini CLI v0.1.14 released with fix (search-result summary)")
src("src_x04", "https://nvd.nist.gov/vuln/detail/CVE-2025-54131", "NVD CVE-2025-54131", "nist", "government", "2025-08-01", "The allow list can be bypassed in auto-run mode with a backtick or $(cmd) in versions below 1.3")
src("src_x05", "https://nvd.nist.gov/vuln/detail/CVE-2026-29783", "NVD CVE-2026-29783", "nist", "government", "2026-03-06", "fails to account for several bash parameter expansion features (search-result summary)")
src("src_x06", "https://labs.cloudsecurityalliance.org/research/csa-research-note-guardfall-ai-coding-agent-shell-injection/", "CSA: GuardFall research note", "cloud-security-alliance", "blog", "2026-07", "opencode leaked 16 of 16 test cases, Goose leaked 22 of 23 (search-result summary)")

src("src_x07", "https://tangled.org/oppi.li/claude-code/blob/main/utils/shell/prefix.ts", "Unofficial Claude Code source dump: prefix.ts", "unofficial-mirror", "forum", "undated", "command_injection_detected treated as no prefix (search-result summary; leaked source)")
src("src_x08", "https://nhimg.org/articles/codex-cli-sandbox-escapes-show-why-model-behaviour-is-not-control/", "NHIMG: Codex CLI sandbox escapes", "nhimg", "blog", "2026", "coverage of Pillar GitPwned (search-result summary)")
src("src_x09", "https://docs.curiosity.ai/landlock-sharp/core-concepts/abi-versions", "Landlock-Sharp: ABI versions", "curiosity", "blog", "undated", "Network sandboxing on 6.7+ (search-result summary)")

# --- cross-cutting / Linux
src("src_e01", "https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/", "Prompt injection to RCE in AI agents", "trail-of-bits", "blog", "2025-10-22", "Maintaining allowlists of \u201csafe\u201d commands without a sandbox is fundamentally flawed")
src("src_e02", "https://arxiv.org/abs/2606.15549", "ShellSieve (agent command denylists)", "arxiv-chen-lin", "blog", "2026-06-14", "we applied ShellSieve to 1,709 real-world command denylists")
src("src_e03", "https://man7.org/linux/man-pages/man7/landlock.7.html", "landlock(7)", "man-pages", "official_docs", "2026-07-18", "Files or directories opened before the sandboxing are not subject to these restrictions.")
src("src_e04", "https://docs.kernel.org/userspace-api/landlock.html", "Landlock: unprivileged access control (kernel docs)", "kernel.org", "official_docs", "2026-10-20", "this policy will be enforced on all its subsequently created children as well.")
src("src_e05", "https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/arch/x86/configs/config-wsl", "WSL2 kernel config-wsl", "microsoft", "repository", "2025-11-17", "CONFIG_SECURITY_LANDLOCK=y / CONFIG_USER_NS=y")
src("src_e06", "https://github.com/containers/bubblewrap", "bubblewrap README", "containers", "repository", "2026-09-16", "the level of protection between the sandboxed processes and the host system is entirely determined by the arguments passed to bubblewrap.")
src("src_e07", "https://www.qualys.com/2025/three-bypasses-of-Ubuntu-unprivileged-user-namespace-restrictions.txt", "Three bypasses of Ubuntu unprivileged userns restrictions", "qualys", "advisory", "2025-03", "Ubuntu 24.04 enabled them by default.")
src("src_e08", "https://cursor.com/blog/agent-sandboxing", "Cursor: agent sandboxing", "cursor", "official_blog", "2026-02-18", "The kernel exposes the required primitives via Landlock and seccomp ... On Windows, we run our Linux sandbox inside WSL2.")

# --- Gemini CLI / Cursor / Copilot (agent C; Gemini pinned at commit b9776560)
G = "https://raw.githubusercontent.com/google-gemini/gemini-cli/b9776560ea5710bc673891499aaec68c737d160a/"
src("src_c01", G + "packages/core/src/utils/shell-utils.ts", "Gemini CLI shell-utils.ts", "google", "repository", "2026-11", "tree-sitter-bash parse; compound commands split and each part checked")
src("src_c02", G + "packages/core/src/policy/policies/plan.toml", "Gemini CLI plan-mode policy", "google", "repository", "2026-11", "plan mode denies all tools by default including run_shell_command")
src("src_c03", G + "packages/core/src/sandbox/utils/commandSafety.ts", "Gemini CLI commandSafety.ts", "google", "repository", "2026-11", "known-safe list: find without -exec/-delete, git status/log/diff/show/branch without -c/--output, sed -n Np")
src("src_c04", G + "docs/cli/sandbox.md", "Gemini CLI sandbox docs", "google", "repository", "2026-11", "sandbox off by default; seatbelt, docker, podman; per-tool bwrap sandbox on Linux")
src("src_c05", "https://tracebit.com/blog/code-exec-deception-gemini-ai-cli-hijack", "Tracebit: Gemini CLI code execution via allowlist", "tracebit", "blog", "2025-07", "grep ...; <exfil> matched as grep; fixed in v0.1.14")
src("src_c06", "https://cursor.com/docs/reference/sandbox.md", "Cursor docs: Sandbox", "cursor", "official_docs", "undated", "Cursor uses Landlock and seccomp. Landlock applies filesystem restrictions. Seccomp blocks unsafe syscalls.")
src("src_c07", "https://cursor.com/docs/agent/security/run-modes.md", "Cursor docs: Run modes", "cursor", "official_docs", "undated", "Auto-review default; non-allowlisted commands run sandboxed; classifier is not a security boundary")
src("src_c08", "https://github.com/cursor/cursor/security/advisories/GHSA-82wg-qcm4-fp2w", "Cursor GHSA-82wg-qcm4-fp2w (CVE-2026-26268)", "cursor", "advisory", "2026-01-14", "Sandbox escape via writing .git configuration was possible in versions prior to 2.5.")
src("src_c09", "https://www.backslash.security/blog/cursor-ai-security-flaw-autorun-denylist", "Backslash: Cursor auto-run denylist bypasses", "backslash", "blog", "2025-07", "four ways to bypass Cursor's denylist")
src("src_c10", "https://github.com/cursor/cursor/security/advisories/GHSA-534m-3w6r-8pqr", "Cursor GHSA-534m-3w6r-8pqr (CVE-2025-54131)", "cursor", "advisory", "2025-08-01", "bypass the allow list in auto-run mode with a backtick or $(cmd)")
src("src_c11", "https://pillar.security/blog/the-agent-security-paradox-when-trusted-commands-in-cursor-become-attack-vectors", "Pillar: trusted commands in Cursor (CVE-2026-22708)", "pillar-security", "blog", "2026", "shell built-ins export/typeset/declare ran without allowlist; fixed by requiring approval for unclassifiable commands")
src("src_c12", "https://code.visualstudio.com/docs/agents/run/approvals.md", "VS Code docs: approvals", "microsoft", "official_docs", "undated", "Terminal auto-approval is a best-effort convenience, not a security boundary.")
src("src_c13", "https://raw.githubusercontent.com/microsoft/vscode/main/src/vs/platform/terminal/common/autoApprove/defaultAutoApproveRules.ts", "VS Code defaultAutoApproveRules.ts", "microsoft", "repository", "2026-11", "default auto-approve rules: find -exec denied, sed -e/-f denied, git status/log/show/diff allowed with --output denied")
src("src_c14", "https://code.visualstudio.com/docs/agents/run/agent-sandboxing.md", "VS Code docs: agent sandboxing", "microsoft", "official_docs", "undated", "chat.agent.sandbox.enabled default off; Seatbelt on macOS, bubblewrap on Linux/WSL2")
src("src_c15", "https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference", "Copilot CLI command reference", "github", "official_docs", "undated", "Some things are intentionally allowed through so research isn't overly restricted: for example, shell commands whose effect can't be clearly determined in advance")
src("src_c16", "https://github.com/github/copilot-cli/security/advisories/GHSA-g8r9-g2v8-jv6f", "Copilot CLI GHSA-g8r9-g2v8-jv6f (CVE-2026-29783)", "github", "advisory", "2026-03-06", "Commands with dangerous expansion patterns are unconditionally blocked at the tool execution layer")
src("src_c17", "https://nvd.nist.gov/vuln/detail/CVE-2026-45033", "NVD CVE-2026-45033 (Copilot CLI nested bare repo)", "nist", "government", "2026-05-13", "git's core.fsmonitor config key (and 15+ similar keys such as core.hookspath, diff.external, merge.tool, etc.) can specify arbitrary shell commands that git will execute as part of normal operations like status, diff, or rev-parse.")
src("src_c18", "https://docs.github.com/en/copilot/concepts/customizations/allowing-safe-commands", "Copilot docs: assisted permissions", "github", "official_docs", "undated", "It uses a large language model to review permission requests and automatically approve actions it judges to be safe")

# --- OpenHands / Aider / Cline / Roo / Amp / opencode / Goose / Continue (agent D)
RAW = "https://raw.githubusercontent.com/"
src("src_d01", "https://docs.openhands.dev/openhands/usage/runtimes/overview.md", "OpenHands runtimes overview", "openhands", "official_docs", "undated", "Docker sandbox runtime is the default; process runtime is opt-out")
src("src_d02", RAW + "OpenHands/software-agent-sdk/main/openhands-tools/openhands/tools/preset/planning.py", "OpenHands planning preset", "openhands", "repository", "2026-11", "planning agent tools: Glob, Grep, PlanningFileEditor (no terminal)")
src("src_d03", RAW + "Aider-AI/aider/main/aider/io.py", "Aider io.py", "aider", "repository", "2026-11", "explicit_yes_required: with --yes-always the answer to suggested shell commands is forced to n")
src("src_d04", RAW + "cline/cline/main/sdk/packages/core/src/extensions/tools/command-guard.ts", "Cline SDK command-guard.ts", "cline", "repository", "2026-11", " * This is a simple blacklist, not a shell interpreter.")
src("src_d05", RAW + "cline/cline/main/docs/core-workflows/plan-and-act.mdx", "Cline docs: plan and act", "cline", "repository", "2026-11", "docs say plan mode cannot run commands (conflicts with SDK presets)")
src("src_d06", RAW + "RooCodeInc/Roo-Code/main/packages/types/src/mode.ts", "Roo Code mode.ts", "roocode", "repository", "2026", "Architect groups: read, edit (.md only), mcp - no command group")
src("src_d07", RAW + "RooCodeInc/Roo-Code/main/src/shared/parse-command.ts", "Roo Code parse-command.ts", "roocode", "repository", "2026", "shell-quote split with regex placeholders for substitutions")
src("src_d08", "https://opencode.ai/v1/docs/agents.md", "opencode docs: agents", "opencode", "official_docs", "undated", "plan agent does not restrict bash")
src("src_d09", "https://goose-docs.ai/docs/guides/managing-tools/goose-permissions", "Goose permissions", "goose", "official_docs", "undated", "Smart Approve: LLM classifies each tool call as read-only or not")
src("src_d10", RAW + "continuedev/continue/main/packages/terminal-security/src/evaluateTerminalCommandSecurity.ts", "Continue evaluateTerminalCommandSecurity.ts", "continue", "repository", "2026-11", "// For now, require permission for any -c usage")
src("src_d11", "https://adversa.ai/blog/opensource-ai-coding-agents-shell-injection-vulnerability/", "Adversa GuardFall", "adversa", "blog", "2026-06-30", "16/16 leaked (opencode)")
src("src_d12", "https://ampcode.com/manual.md", "Amp manual", "amp", "official_docs", "undated", "no approval gate for shell by default today; legacy amp.permissions glob rules")
src("src_d13", "https://zed.dev/docs/ai/tool-permissions", "Zed tool permissions", "zed", "official_docs", "undated", "always_allow / always_deny / always_confirm regex per parsed sub-command; default confirm")

# ---------------- claims
CLAIMS = []


def cs(query, urls, summary):
    return {"query": query, "urls": urls, "summary": summary}


def claim(cid, text, risk, ctype, sids, counter=None, conflicting=False, valid_at="2026-11-13", proof=None, evidence=None):
    c = {"claim_id": cid, "text": text, "risk": risk, "claim_type": ctype, "source_ids": sids,
         "counter_refuted": False, "conflicting": conflicting, "valid_at": valid_at}
    if counter:
        c["counter_search"] = counter
    if proof:
        c["execution_proof"] = proof
    if evidence:
        c["evidence"] = evidence
    CLAIMS.append(c)


ENV = "Linux 6.6.87.2-microsoft-standard-WSL2, Ubuntu 24.04.5, Python 3.12.3, /bin/sh=dash, Landlock ABI 3"
ROOT = "artifacts/exec/"
# ---- executable (local runs)
claim("clm_001", "이 WSL2 머신에서 비특권 사용자 네임스페이스와 Landlock(ABI 3)이 동작하고 bubblewrap은 설치되어 있지 않다", "normal", "executable", ["src_l01", "src_l05", "src_e05"],
      proof={"script": "landlock_create_ruleset(NULL,0,VERSION) syscall via ctypes; unshare --user --map-root-user --mount; which bwrap; " + ROOT + "userns_ro_bind.out", "output": "landlock abi 3; uid=0(root) inside userns; bwrap: not found (apt candidate 0.9.0-1ubuntu0.3)", "env": ENV, "verdict": "confirmed"})
claim("clm_002", "약 70줄 ctypes Landlock 래퍼로 sh -c를 감싸면 git status -sb, python -c 'import textual', python -c print 같은 읽기 명령은 그대로 성공한다", "normal", "executable", ["src_l01"],
      proof={"script": ROOT + "landlock_ro.py + run_tests.sh", "output": "git status -sb exit=0; .venv/bin/python -c 'import textual' -> 8.2.8 exit=0; python3 -c print -> 45 exit=0; ls >/dev/null && echo devnull-ok", "env": ENV, "verdict": "confirmed"})
claim("clm_003", "같은 Landlock 래퍼 아래에서 리다이렉트, touch/rm/mkdir, 셸 함수 정의 우회, $(...) 안의 쓰기, git log/diff --output, find -exec rm, sed -i, python open(w) 쓰기가 모두 커널에서 거부된다", "normal", "executable", ["src_l01"],
      proof={"script": ROOT + "run_tests.sh", "output": "cannot create out.txt: Permission denied; cat() { echo pwned > fn.txt; } -> Permission denied; git log --output -> fatal: could not open ... Permission denied; find -exec rm -> Permission denied; sed -i -> couldn't open temporary file; scratch dir unchanged afterwards", "env": ENV, "verdict": "confirmed"})
claim("clm_004", "Landlock 래퍼는 WSL drvfs(/mnt/c)와 /dev/shm 쓰기도 막는다", "normal", "executable", ["src_l06"],
      proof={"script": ROOT + "drvfs_probe.out", "output": "touch /mnt/c/Users/Public/.../x: Permission denied; /dev/shm write: Permission denied", "env": ENV, "verdict": "confirmed"})
claim("clm_005", "Landlock ABI 3 래퍼는 chmod와 mtime 변경, 경로 유닉스 소켓 connect, 샌드박스 전에 열린 fd로의 쓰기, 네트워크 접속을 막지 못한다", "normal", "executable", ["src_l01", "src_l02"],
      proof={"script": ROOT + "metadata_socket_probe.sh, run_tests.sh (fd 3 and network probes)", "output": "mode 644->600 and mtime changed; unix socket server wrote 'via-unix-socket'; inherited fd 3 wrote 'via-fd'; connect 1.1.1.1:53 succeeded", "env": ENV, "verdict": "confirmed"})
claim("clm_006", "unshare 사용자+마운트 네임스페이스의 읽기 전용 bind mount는 chmod와 touch를 EROFS로 막지만 유닉스 소켓 connect는 막지 못한다", "normal", "executable", ["src_l03"],
      proof={"script": ROOT + "ro_mount_socket_probe.sh", "output": "chmod: Read-only file system; touch: Read-only file system; server file: via-unix-socket", "env": ENV, "verdict": "confirmed"})
claim("clm_007", "WSL2에서는 Landlock 아래에서도 Windows 실행 파일(cmd.exe)이 interop으로 호스트에서 실행되어 C: 드라이브에 파일을 쓸 수 있고, WSL_INTEROP만 지워서는 막히지 않으며 /run/WSL을 tmpfs로 가리면 막힌다", "normal", "executable", ["src_l04", "src_a17"],
      proof={"script": ROOT + "wsl_interop_probe.out", "output": "interop-ran exit=0 and C:\\Users\\Public\\ll_interop_probe.txt created; env -u WSL_INTEROP: interop-ran; unshare -rm + mount tmpfs /run/WSL: WSL ERROR ... exit=1", "env": ENV, "verdict": "confirmed"})
claim("clm_008", "rbind 뒤 최상위만 remount,ro 하면 /dev/shm 같은 하위 마운트는 rw로 남는다", "normal", "executable", ["src_l05"],
      proof={"script": ROOT + "userns_ro_bind.out (findmnt -R)", "output": "top: ro; m/dev, m/dev/shm, m/dev/pts: rw", "env": ENV, "verdict": "confirmed"})
claim("clm_009", "Landlock 래퍼의 호출당 추가 시간은 이 머신에서 약 14ms다 (python3 기동 포함)", "normal", "executable", ["src_l01"],
      proof={"script": "time 10x python3 landlock_ro.py true vs 10x sh -c true", "output": "0.148s vs 0.006s for 10 runs", "env": ENV, "verdict": "confirmed"})

claim("clm_080", "비특권 사용자+마운트+네트워크 네임스페이스에서 mount_setattr(AT_RECURSIVE, MOUNT_ATTR_RDONLY)로 /를 재귀 읽기 전용으로 만들면 내용 쓰기, chmod, touch가 /dev/shm과 /mnt/c를 포함해 모두 EROFS로 막히고, git status와 python import, /dev/null 리다이렉트는 동작하며, 네트워크는 끊기고 /run/WSL을 가리면 interop도 막힌다", "normal", "executable", ["src_l07"],
      proof={"script": ROOT + "mount_setattr_probe.py (os.unshare USER|NS|NET, identity uid map, MS_PRIVATE, tmpfs /run/WSL, mount_setattr RDONLY recursive, tmpfs scratch)", "output": "out.txt/chmod/touch/dev/shm//mnt/c: Read-only file system; scratch tmpfs write ok; git status -sb ok; textual 8.2.8; Network is unreachable; interop_exit=1; devnull-ok; 10 runs 0.15s", "env": ENV, "verdict": "confirmed"})
claim("clm_081", "읽기 전용 마운트만으로는 경로 유닉스 소켓 connect가 막히지 않아, 샌드박스 안에서 systemd-run --user가 /run/user/UID/bus를 통해 샌드박스 밖에 파일을 만들 수 있고, /run을 tmpfs로 가리면 막힌다", "normal", "executable", ["src_l07", "src_l08"],
      proof={"script": ROOT + "bus_escape_probe.out, mount_setattr_probe.out (unix socket server)", "output": "systemd_run_exit=0 and file created outside sandbox; with tmpfs over /run: Failed to connect to bus, no file; pathname socket server received 'via-unix-socket'", "env": ENV, "verdict": "confirmed"})

claim("clm_082", "최종 프로토타입(사용자·마운트·네트워크 네임스페이스, /run tmpfs, 재귀 읽기 전용, /tmp 쓰기용 tmpfs, seccomp로 AF_UNIX socket과 io_uring 거부)에서 git status -sb, python -c 'import textual', ls/grep/find는 동작하고, 함수 정의·--output·touch·chmod 쓰기, systemd-run 탈출, WSL interop, 네트워크, herdr 소켓 접속은 모두 막혔으며 호출당 약 14ms가 더 든다", "normal", "executable", ["src_l09"],
      proof={"script": ROOT + "ro_launcher.py + probes in ro_launcher_probe.out", "output": "git status -sb output identical inside and outside; setsid drops controlling tty (/dev/tty ENXIO); x32 syscall numbers killed; host legacy_tiocsti=0; textual 8.2.8; fn_probe/gitout/probe_file: Read-only file system; chmod AGENTS.md: Read-only file system; systemd-run via /mnt/wslg bus: Operation not permitted; herdr.sock connect: Operation not permitted; Network is unreachable; /tmp scratch ok; 10 runs 0.14s", "env": ENV, "verdict": "confirmed"})
claim("clm_083", "seccomp 없이 /run만 가린 상태에서는 /mnt/wslg/run/user/UID 아래 같은 사용자 런타임 디렉터리와 홈의 소켓(herdr, VS Code IPC 등 38개)이 그대로 보여, systemd 사용자 버스를 통해 샌드박스 밖에 파일을 만들 수 있었다", "normal", "executable", ["src_l09"],
      proof={"script": ROOT + "ro_launcher_probe.out (before seccomp section)", "output": "find -type s: 35 under /mnt/wslg, 3 under /home/sds; DBUS_SESSION_BUS_ADDRESS=unix:path=/mnt/wslg/run/user/1000/bus systemd-run -> systemd_run_exit=0, host file created", "env": ENV, "verdict": "confirmed"})

# ---- Claude Code
claim("clm_010", "Claude Code의 OS 샌드박스는 기본으로 꺼져 있고, macOS는 Seatbelt, Linux와 WSL2는 bubblewrap을 쓴다", "normal", "descriptive", ["src_a03", "src_a04", "src_a12"],
      counter=cs("WSL2 sandbox escape interop Windows binary bubblewrap Claude Code /mnt/c 2026", ["https://claudeissues.com/issue/45072-bug-recent-seccomp-change-for-sandbox-broke-executing-windows-tools-from-wsl"], "No contradiction; issue reports show bwrap+seccomp in use on WSL2."))
claim("clm_011", "Claude Code는 복합 명령을 &&, ||, ;, |, &, 줄바꿈으로 나누고 모든 하위 명령이 허용돼야 프롬프트 없이 실행하며, 해석할 수 없는 명령은 읽기 전용으로 보지 않고 묻는다", "normal", "descriptive", ["src_a01"])
claim("clm_012", "Claude Code plan 모드의 셸 명령은 bypass 권한을 쓸 수 있는 대화형 세션이면 검사 없이 돌고, auto 모드를 쓸 수 있으면(기본) 분류기가 판단하며, 둘 다 아니면 내장 읽기 전용 명령만 프롬프트 없이 돌고 나머지는 사용자에게 묻는다", "normal", "descriptive", ["src_a01", "src_a02", "src_a16"],
      counter=cs("Claude Code plan mode which bash commands run without approval python -c 2026", ["https://alexcloudstar.com/md/blog/claude-code-plan-mode-2026/"], "Third-party guide agrees read-only commands run freely and others ask; GitHub issue mirrors report version-specific regressions (v2.1.212 asked for every command, fixed). No source says python -c is in the read-only set."))
claim("clm_013", "Claude Code에서 python -c는 내장 읽기 전용 목록에 없어서 plan 모드에서는 묻거나 분류기로 가고, 샌드박스 자동 허용은 plan 모드 밖에서만 python3 -c를 프롬프트 없이 실행한다", "normal", "descriptive", ["src_a02", "src_a03", "src_a06"])
claim("clm_014", "Claude Code는 CVE-2025-66032 이후 v1.0.93에서 읽기 전용 명령 검증을 블록리스트에서 허용 목록 방식으로 바꿨다", "high", "causal", ["src_a08", "src_a13", "src_a15"], valid_at="2025-12-03",
      counter=cs("Claude Code CVE-2025-66032 not fixed bypass allowlist v1.0.93 dispute", ["https://osv.dev/vulnerability/CVE-2025-66032"], "No dispute found; aggregators agree fixed in 1.0.93 (one stale aggregator says no fix)."),
      evidence=[{"source_id": "src_a08", "quote": "Anthropic was very responsive and addressed these issues by introducing an allowlist approach instead of the previous blocklist approach."}])
claim("clm_015", "2025년 Claude Code는 Bash 명령마다 Haiku 모델에 접두사 추출을 요청했고 주입이 의심되면 command_injection_detected를 받아 프롬프트를 띄웠다", "high", "descriptive", ["src_a07", "src_a06"], valid_at="2025-11-21",
      counter=cs("Claude Code Haiku command prefix detection command_injection_detected removed 2026", ["https://tangled.org/oppi.li/claude-code/blob/main/utils/shell/prefix.ts"], "Only unofficial source-dump mirrors (one labelled v2.1.20) still show the step; no official source says it was removed or kept."),
      evidence=[{"source_id": "src_a07", "quote": "Claude Code Code Bash command prefix detection"}])
claim("clm_016", "Claude Code 2.1.x의 Bash 권한 검사는 tree-sitter 파서를 쓴다(changelog의 parser 재설정·simple_expansion 항목과 유출 소스 분석이 일치)", "normal", "descriptive", ["src_a11", "src_a06"])
claim("clm_019", "Claude Code는 모르는 AST 노드나 파서 시간 초과를 too-complex로 보고 사용자에게 묻는 fail-closed 구조다", "normal", "descriptive", ["src_a11"])
claim("clm_017", "Anthropic은 사내 사용에서 샌드박스가 권한 프롬프트를 84% 줄였다고 밝혔다", "high", "numeric", ["src_a05"], valid_at="2025-10-20",
      counter=cs("Claude Code sandboxing 84% fewer permission prompts independent measurement", ["https://www.anthropic.com/engineering/claude-code-sandboxing"], "Every source traces the 84% figure to Anthropic internal usage; no independent replication."),
      evidence=[{"source_id": "src_a05", "quote": "In our internal usage, we've found that sandboxing safely reduces permission prompts by 84%."}])
claim("clm_018", "Claude Code의 2025-2026 읽기 전용 검증 우회 CVE는 echo(CVE-2025-54795), DNS 유출 허용 목록(CVE-2025-55284), $IFS·짧은 플래그(CVE-2025-66032), sed(CVE-2025-64755), find(CVE-2026-24887), zsh clobber(CVE-2026-24053) 등 10건 이상이다", "high", "descriptive", ["src_a13", "src_a14", "src_a15", "src_a08", "src_a10"], valid_at="2026-11-13",
      counter=cs("Claude Code CVE-2025-66032 not fixed bypass allowlist v1.0.93 dispute", ["https://osv.dev/vulnerability/CVE-2025-66032"], "Trackers agree on ids and fix versions."),
      evidence=[{"source_id": "src_a14", "quote": "Prior to version 2.0.31, due to an error in sed command parsing"}])

# ---- Codex
claim("clm_020", "Codex CLI는 v0.149.0(2026-08-20, PR #39630)에서 known-safe 명령 허용 목록을 지우고 untrusted 승인 정책을 폐지했다", "high", "descriptive", ["src_b01", "src_b08", "src_b09"], valid_at="2026-08-20",
      counter=cs("Codex CLI known safe command allowlist still auto-approves read-only commands 2026", ["https://blakecrosley.com/blog/codex-untrusted-approval-policy-retired", "https://codex.danielvaughan.com/2026/05/21/codex-cli-execution-policy-rules-starlark-command-governance-enterprise-allowlists/"], "Pre-August 2026 blogs describe the allowlist as active; later sources report the removal. Consistent with a change in v0.149.0."),
      evidence=[{"source_id": "src_b01", "quote": "Remove the known-safe command allowlist. Projects marked untrusted now request approval for every command unless an explicit exec policy rule allows it."}])
claim("clm_021", "Codex는 저장소 설정이 읽기 전용 git 명령에서도 헬퍼를 실행시킬 수 있다는 이유로 2026-08-19 git을 안전 목록에서 뺐다", "high", "causal", ["src_b02", "src_b16"], valid_at="2026-08-19",
      counter=cs("CVE-2026-19592 Codex core.fsmonitor git metadata", ["https://openai.com/security/advisories/cve-2026-19592/", "https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-git-config-rce-20260904-cs/"], "OpenAI advisory and CSA note agree: repo-local core.fsmonitor ran during metadata collection, outside the sandbox; same root cause hit other agents. No contradiction."),
      evidence=[{"source_id": "src_b02", "quote": "Repository configuration can cause even read-only Git commands to execute helpers, so Git command arguments alone are not enough to establish trust."}])
claim("clm_028", "Codex의 예전 Landlock 경로는 앱 서버 유닉스 소켓을 격리하지 못해 파일시스템 제한 정책에서 거부된다", "normal", "descriptive", ["src_b04"])
claim("clm_022", "Codex의 Linux 샌드박스는 bubblewrap(--ro-bind / /)과 seccomp를 주 경로로 쓴다", "normal", "descriptive", ["src_b04", "src_b15"],
      counter=cs("Codex CLI Linux sandbox bubblewrap seccomp ro-bind replaced Landlock 2026", ["https://codex.danielvaughan.com/2026/05/03/codex-cli-sandbox-internals-seatbelt-bubblewrap-landlock-windows-dacl/"], "Some April-July 2026 blogs still describe Landlock as primary; repository README at main says bubblewrap with Landlock legacy."))
claim("clm_023", "Codex에서 read-only 샌드박스와 on-request 승인 정책을 함께 쓰면 위험 목록에 걸리지 않은 명령(python 포함)은 승인 없이 샌드박스 안에서 실행된다", "normal", "descriptive", ["src_b06", "src_b07", "src_b05", "src_b08"], conflicting=True,
      counter=cs("Codex CLI known safe command allowlist still auto-approves read-only commands 2026", ["https://blakecrosley.com/blog/codex-untrusted-approval-policy-retired"], "Codex sandboxing docs page and Crosley say read-only asks before commands; approvals page and exec_policy.rs code say commands run sandboxed without approval. Unresolved conflict."))
claim("clm_024", "Codex의 tree-sitter 파서는 단어만 있는 명령을 &&, ||, ;, |로 이은 경우만 받아들이고 리다이렉트, 서브셸, 치환, 글롭, $, 중괄호, 백슬래시가 있으면 거부하며, 지금은 이를 exec-policy 규칙 매칭에만 쓴다", "normal", "descriptive", ["src_b03", "src_b07"])
claim("clm_025", "Codex Plan Mode는 프롬프트 지시(변경 금지)일 뿐이고 샌드박스나 승인 정책을 바꾼다는 근거는 찾지 못했다", "normal", "descriptive", ["src_b13", "src_b18"],
      counter=cs("Codex CLI plan mode collaboration mode sandbox read-only permission 2026", ["https://codex.danielvaughan.com/2026/03/27/planning-mode-in-practice/"], "Third-party blog agrees plan mode is prompt-level; official docs point to read-only sandbox via /permissions for planning without changes."))
claim("clm_026", "Codex CLI의 git show --output 허용 목록 우회는 Pillar가 보고했고 2026-02-04 v0.95.0에서 고쳐졌다", "high", "descriptive", ["src_b14"], valid_at="2026-02-04",
      counter=cs("Pillar Security GitPwned Codex git show --output v0.95.0", ["https://www.pillar.security/blog/gitpwned-allowlist-to-rce", "https://nhimg.org/articles/codex-cli-sandbox-escapes-show-why-model-behaviour-is-not-control/"], "Secondary coverage and Mend WS-2026-0013 repeat Pillar's dates (reported 2026-01-07, fixed v0.95.0 2026-02-04); no contradiction, no CVE id."),
      evidence=[{"source_id": "src_b14", "quote": "OpenAI's Codex CLI trusts git show as a safe command, but git show --output can write arbitrary content to arbitrary files"}])
claim("clm_027", "Codex의 CVE-2026-19591은 PowerShell --% 토큰을 다르게 해석한 안전 명령 파서 때문에 파일을 쓰는 git 명령이 승인 없이 돌던 문제다", "high", "descriptive", ["src_b12"], valid_at="2026-09-01",
      counter=cs("CVE-2026-19592 Codex core.fsmonitor git metadata", ["https://openai.com/security/advisories/cve-2026-19592/"], "Search covered the 19590-19593 batch; nothing contradicts 19591, but no second org describes it."),
      evidence=[{"source_id": "src_b12", "quote": "misclassified certain PowerShell commands as safe"}])

# ---- cross-cutting
claim("clm_030", "독립 보안 연구자들은 코딩 에이전트의 안전 명령 허용 목록을 허용된 바이너리의 실행 플래그(rg --pre, sort --compress-program, git 옵션 축약, go test -exec 등)로 반복해서 우회했다", "normal", "descriptive", ["src_e01", "src_a08", "src_b14"])
claim("clm_031", "Trail of Bits는 샌드박스 없는 안전 명령 허용 목록은 근본적으로 결함이 있다고 보고 샌드박스를 1차 통제로 권한다", "normal", "descriptive", ["src_e01", "src_e02"])
claim("clm_032", "Landlock은 chmod, chown, setxattr, utime 같은 메타데이터 변경을 제한하지 못하고, 샌드박스 전에 열린 fd에는 적용되지 않으며, 제한은 자식 프로세스에 상속되고 풀 수 없다", "normal", "descriptive", ["src_e03", "src_e04", "src_l02"])
claim("clm_033", "Landlock 네트워크 제한은 ABI 4(커널 6.7)부터라 ABI 3 커널에서는 네트워크를 막을 수 없다", "high", "numeric", ["src_e03", "src_e04"], valid_at="2026-07-18",
      counter=cs("Landlock ABI 4 network TCP restriction kernel 6.7 version table", ["https://docs.curiosity.ai/landlock-sharp/core-concepts/abi-versions"], "Third-party doc and kernel docs agree network rules start at ABI 4 / 6.7; no contradiction."),
      evidence=[{"source_id": "src_e03", "quote": "LANDLOCK_ACCESS_NET_BIND_TCP"}])
claim("clm_034", "Microsoft WSL2 커널 설정은 Landlock과 사용자 네임스페이스를 켜 두었다", "normal", "descriptive", ["src_e05", "src_l01"])
claim("clm_035", "bubblewrap은 setuid 모드를 없애고 비특권 사용자 네임스페이스에 의존하며, 보호 수준은 전적으로 넘긴 인자에 달려 있다", "normal", "descriptive", ["src_e06", "src_b04"])
claim("clm_036", "Ubuntu 24.04는 AppArmor로 비특권 사용자 네임스페이스 제한을 기본으로 켜서 bwrap에 프로필이 필요할 수 있지만, 이 WSL2 커널에는 그 sysctl이 없다", "high", "descriptive", ["src_e07", "src_x02", "src_a03", "src_l01"], valid_at="2025-03",
      counter=cs("Ubuntu 24.04 apparmor_restrict_unprivileged_userns bubblewrap default WSL2", ["https://bugs.launchpad.net/bugs/2046477", "https://www.qualys.com/2025/three-bypasses-of-Ubuntu-unprivileged-user-namespace-restrictions.txt"], "Launchpad and Qualys agree the restriction is default on 24.04; nothing found about WSL2 specifically."),
      evidence=[{"source_id": "src_e07", "quote": "Ubuntu 24.04 enabled them by default."}])
claim("clm_037", "Cursor는 Linux에서 Landlock과 seccomp로 에이전트 명령 샌드박스를 만들고 Windows에서는 그 Linux 샌드박스를 WSL2 안에서 돌린다", "normal", "descriptive", ["src_e08"])

# ---- Gemini / Cursor / Copilot
claim("clm_040", "Gemini CLI는 tree-sitter-bash로 명령을 나눠 부분마다 정책을 검사하고, 리다이렉트나 명령 치환이 있으면 allow를 ask로 낮추며, 파싱에 실패하면 ask(비대화형이면 deny)로 처리한다", "normal", "descriptive", ["src_c01"])
claim("clm_041", "Gemini CLI plan 모드는 run_shell_command를 포함한 모든 도구를 기본으로 거부하고 사용자가 명령 접두사 허용 규칙을 추가해야 셸을 쓸 수 있다", "normal", "descriptive", ["src_c02"])
claim("clm_042", "Gemini CLI의 known-safe 목록은 find(-exec 등 제외), git status/log/diff/show/branch(-c, --output 등 제외), sed -n Np만 허용하며 python 같은 인터프리터는 없다", "normal", "descriptive", ["src_c03"])
claim("clm_043", "Gemini CLI의 OS 샌드박스는 기본으로 꺼져 있고 macOS Seatbelt, docker/podman, Linux 도구 단위 bubblewrap을 고를 수 있다", "normal", "descriptive", ["src_c04"])
claim("clm_044", "Tracebit은 2025년 7월 Gemini CLI가 grep ...; <명령>을 grep으로 판단해 허용하는 우회를 보고했고 v0.1.14에서 고쳐졌다", "high", "descriptive", ["src_c05", "src_x03"], valid_at="2025-07-25",
      counter=cs("Tracebit Gemini CLI allowlist bypass v0.1.14 fix 2025", ["https://tracebit.com/blog/code-exec-deception-gemini-ai-cli-hijack", "https://securitybrief.asia/story/tracebit-finds-major-vulnerability-in-google-gemini-cli-tool"], "News coverage repeats Tracebit's timeline (fix in v0.1.14, 2025-07-25); no contradiction."),
      evidence=[{"source_id": "src_c05", "quote": "v0.1.14"}])
claim("clm_045", "Cursor는 Linux에서 Landlock과 seccomp(구형 커널은 bubblewrap 또는 승인 요청)로, macOS에서 Seatbelt로 명령을 샌드박스하고 Windows는 WSL2 안에서 같은 Linux 샌드박스를 쓴다", "normal", "descriptive", ["src_c06", "src_e08"])
claim("clm_046", "Cursor 기본 Auto-review 모드는 허용 목록 밖 명령을 프롬프트 없이 샌드박스에서 돌리고, 샌드박스할 수 없는 명령만 LLM 분류기에 보내며 이 분류기는 보안 경계가 아니라고 문서에 적혀 있다", "normal", "descriptive", ["src_c07"])
claim("clm_047", "Cursor는 Backslash의 denylist 우회 보고 뒤 auto-run denylist를 폐기했고, backtick과 $() 허용 목록 우회(CVE-2025-54131)를 1.3에서 고쳤다", "high", "descriptive", ["src_c09", "src_c10", "src_x04"], valid_at="2025-08-01",
      counter=cs("Cursor CVE-2025-54131 backtick allowlist bypass denylist deprecated 1.3", ["https://nvd.nist.gov/vuln/detail/CVE-2025-54131"], "NVD confirms backtick/$(cmd) bypass fixed in 1.3; search found nothing about denylist deprecation (Backslash only)."),
      evidence=[{"source_id": "src_c10", "quote": "an attacker can bypass the allow list in auto-run mode with a backtick"}])
claim("clm_048", "VS Code Copilot 에이전트의 터미널 자동 승인은 tree-sitter로 모든 하위 명령을 검사하고 기본 규칙에 python 규칙이 없으며, 샌드박스(chat.agent.sandbox.enabled)는 기본으로 꺼져 있다", "normal", "descriptive", ["src_c12", "src_c13", "src_c14"])
claim("clm_049", "Copilot CLI plan 모드는 작업 공간 파일을 바꾸는 명령을 강제로 막지만 효과를 미리 판단할 수 없는 명령은 통과시키고, assisted permissions는 LLM이 요청을 검토한다", "normal", "descriptive", ["src_c15", "src_c18"])
claim("clm_050", "Copilot CLI의 CVE-2026-29783은 ${var@P}, ${var=value}, ${!var} 같은 확장이 읽기 전용 분류기를 통과한 문제로, 이후 이런 패턴은 --yolo에서도 무조건 막힌다", "high", "descriptive", ["src_c16", "src_x05"], valid_at="2026-03-06",
      counter=cs("Copilot CLI CVE-2026-29783 ${var@P} dangerous expansion read-only classifier", ["https://nvd.nist.gov/vuln/detail/CVE-2026-29783"], "Trackers agree: affected <=0.0.422, fixed 0.0.423 (2026-03-06); no contradiction."),
      evidence=[{"source_id": "src_c16", "quote": "Commands with dangerous expansion patterns are unconditionally blocked at the tool execution layer"}])

# ---- cross-vendor
claim("clm_060", "저장소 로컬 git 설정(core.fsmonitor, core.hooksPath 등)은 git status 같은 읽기 명령에서도 임의 프로그램을 실행시킬 수 있어서 여러 벤더가 이를 취약점으로 다뤘다", "normal", "descriptive", ["src_b02", "src_c17", "src_c08", "src_b16", "src_b19", "src_x01"])
claim("clm_061", "Microsoft, Cursor, Anthropic 문서는 명령 자동 승인 규칙이나 분류기가 보안 경계가 아니라고 명시한다", "normal", "descriptive", ["src_c12", "src_c07", "src_a01"])
claim("clm_062", "Claude Code, Gemini CLI, VS Code, Cursor는 해석하거나 분류할 수 없는 명령을 자동 승인하지 않고 묻거나 막는 쪽으로 수렴했다", "normal", "descriptive", ["src_a01", "src_c01", "src_c13", "src_c11"])
claim("clm_063", "Codex와 Cursor는 정적 안전 명령 판정 대신 OS 샌드박스 안 실행을 기본 경로로 삼는다", "normal", "descriptive", ["src_b01", "src_b06", "src_c07", "src_e08"])

# ---- others (agent D)
claim("clm_070", "OpenHands는 기본으로 Docker 샌드박스에서 명령을 돌리고, planning 에이전트 프리셋에는 터미널 도구가 아예 없다", "normal", "descriptive", ["src_d01", "src_d02"])
claim("clm_071", "Aider는 샌드박스와 정적 판정이 없고, LLM이 제안한 셸 명령은 항상 사용자에게 묻고 --yes-always에서도 거부한다", "normal", "descriptive", ["src_d03"])
claim("clm_072", "Cline SDK plan 모드는 셸 도구를 남겨 두고 단순 블랙리스트 가드만 적용해 python -c 쓰기를 잡지 못한다고 코드 주석에 적혀 있으며, 문서는 plan 모드에서 명령을 못 돌린다고 말해 서로 어긋난다", "normal", "descriptive", ["src_d04", "src_d05"], conflicting=True)
claim("clm_073", "Roo Code의 Architect와 Ask 모드에는 명령 실행 도구 그룹이 없고, Code 모드는 parseCommand로 나눈 하위 명령마다 접두사 허용/거부 목록을 적용한다", "normal", "descriptive", ["src_d06", "src_d07"])
claim("clm_074", "opencode의 plan 에이전트는 bash를 제한하지 않아 기본 설정에서는 python -c도 프롬프트 없이 돈다", "normal", "descriptive", ["src_d08"])
claim("clm_075", "Goose의 Smart Approve는 LLM이 각 도구 호출을 읽기 전용인지 판단하고, 정적 규칙은 기본으로 꺼진 정규식 검사뿐이다", "normal", "descriptive", ["src_d09"])
claim("clm_076", "Continue의 터미널 보안 평가기는 인터프리터 -c 사용을 항상 권한 요청 대상으로 둔다", "normal", "descriptive", ["src_d10", "src_d11"])
claim("clm_077", "Adversa GuardFall(2026-06-30)은 원문 텍스트 매칭 가드가 opencode 16/16, Goose 22/23 사례에서 뚫렸다고 보고했다", "high", "numeric", ["src_d11", "src_x06"], valid_at="2026-06-30",
      counter=cs("Adversa GuardFall AI coding agents shell guard bypass opencode goose 2026", ["https://labs.cloudsecurityalliance.org/research/csa-research-note-guardfall-ai-coding-agent-shell-injection/"], "CSA and news coverage repeat Adversa's numbers (16/16, 22/23); all trace to Adversa, no independent re-test."),
      evidence=[{"source_id": "src_d11", "quote": "16/16 leaked"}])
claim("clm_078", "plan 단계에서 셸을 안전하게 만드는 방식은 도구마다 셸 제거(OpenHands planning, Roo Architect/Ask, Gemini plan 기본값), 항상 묻기(Aider, Continue의 -c 규칙), OS 샌드박스(OpenHands Docker, Codex read-only)로 갈린다", "normal", "descriptive", ["src_d02", "src_d06", "src_c02", "src_d03", "src_d10", "src_b06"])

# ---- WRITE
def _write(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


_ids = [s["id"] for s in SOURCES]
assert len(_ids) == len(set(_ids)), "duplicate source id"
_cids = [c["claim_id"] for c in CLAIMS]
assert len(_cids) == len(set(_cids)), "duplicate claim id"
_urls = {s["url"].lower().rstrip("/") for s in SOURCES}
for c in CLAIMS:
    for u in (c.get("counter_search") or {}).get("urls", []):
        assert u.lower().rstrip("/") in _urls, (c["claim_id"], u)
_write(os.path.join(S, "sources", "sources.jsonl"), SOURCES)
_write(os.path.join(S, "artifacts", "claim_ledger.jsonl"), CLAIMS)
print(f"sources={len(SOURCES)} claims={len(CLAIMS)}")
