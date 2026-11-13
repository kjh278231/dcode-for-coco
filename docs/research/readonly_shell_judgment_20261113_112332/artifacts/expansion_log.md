# Expansion log (Phase 3)

Batch 1 (5 agents, foreground-equivalent; all returned with EXPAND tails): A Claude Code, B Codex, C Gemini/Cursor/Copilot, D others, E CVEs + Linux primitives.

Orchestrator follow-ups run (counter-search / expansion, depth 1): 17 WebSearch calls and 3 WebFetch confirmations in total (src_a16, src_b15, src_b18). Listed queries:
- "Codex CLI known safe command allowlist still auto-approves read-only commands 2026" -> older blogs vs removal in v0.149.0 (clm_020)
- "Landlock does not restrict chmod chown utime limitation" -> man pages confirm; 2026-04 patch series not merged (clm_032, clm_033)
- "WSL2 sandbox escape interop Windows binary bubblewrap Claude Code /mnt/c 2026" -> Claude Code seccomp blocks unix connect, which breaks .exe interop (clm_007, clm_010)
- "Codex CLI Linux sandbox bubblewrap seccomp ro-bind replaced Landlock 2026" -> bwrap default since PR #13996 (mirror), some blogs stale (clm_022)
- "Claude Code CVE-2025-66032 not fixed bypass allowlist v1.0.93 dispute" -> no dispute (clm_014, clm_018)
- "Claude Code plan mode which bash commands run without approval python -c 2026" -> guide + issue mirrors (clm_012)
- "Codex CLI plan mode collaboration mode sandbox read-only permission 2026" -> prompt-level only (clm_025)
Local executable probes (artifacts/exec/): Landlock wrapper, ro bind mount, unix socket, inherited fd, network, drvfs, WSL interop, overhead.

## Leads (deduped across agents) and disposition
- Haiku prefix-detection call still running in Claude Code 2.1.3xx? — NOT PURSUED (no primary source reachable; leaked-source only). Unresolved clm_015.
- Exact Claude Code per-command flag allowlist — NOT PURSUED (only unofficial leaked-source mirrors).
- Codex PR #13996 bwrap default date — partly covered by counter-search (mirror only).
- Codex CVE-2026-19590..93 fix versions, PR #22643 — NOT PURSUED (GitHub API rate-limited, no gh).
- Codex Plan Mode vs sandbox — PURSUED (clm_025).
- Gemini shell-safety regression tests as fixtures — DEFERRED to implementation (useful test vectors for dcode).
- VS Code treeSitterCommandParser / hasUnanalyzableSyntax, blockDetectedFileWrites — DEFERRED (design detail, not decision-relevant).
- Cursor plan-mode shell policy — NOT PURSUED (forum only).
- Continue evaluateTerminalCommandSecurity.ts full read — DEFERRED to implementation.
- OpenHands _shell_ast.py / policy_rails.py — DEFERRED.
- Bypass classes with no 2025-2026 advisory found (shell function definitions, glob into option, newline continuation, PAGER/GIT_* env, heredoc) — DEAD END in search; covered instead by local Landlock probes (clm_003).
- bwrap-userns-restrict AppArmor profile on native 24.04 — NOT PURSUED (WSL2 kernel lacks the sysctl; matters only off-WSL).
- Claude Code WSL2 bwrap issues (#51126 E2BIG, /mnt/c binds) — partly covered (issue mirrors), not decision-critical.
- GuardFall (Adversa) taxonomy — single source, unresolved clm_077.

Convergence: stopped after depth 1 (orchestrator follow-ups). Remaining leads are implementation detail or blocked by rate limits; rule (c) would ask the user to extend, but the caller forbids questions, so the remaining leads are listed above as limitations.

Additional counter-searches (after advisor review):
- "CVE-2026-19592 Codex core.fsmonitor git metadata" (clm_021, clm_027, clm_060)
- "Claude Code sandboxing 84% fewer permission prompts independent measurement" (clm_017)
- "Ubuntu 24.04 apparmor_restrict_unprivileged_userns bubblewrap default WSL2" (clm_036)
- "Tracebit Gemini CLI allowlist bypass v0.1.14 fix 2025" (clm_044)
- "Cursor CVE-2025-54131 backtick allowlist bypass denylist deprecated 1.3" (clm_047)
- "Copilot CLI CVE-2026-29783 ${var@P} dangerous expansion read-only classifier" (clm_050)
- "Adversa GuardFall AI coding agents shell guard bypass opencode goose 2026" (clm_077)
- "Claude Code Haiku command prefix detection command_injection_detected removed 2026" (clm_015)
- "Pillar Security GitPwned Codex git show --output v0.95.0" (clm_026)
- "Landlock ABI 4 network TCP restriction kernel 6.7 version table" (clm_033)
- WebFetch confirmations: alexcloudstar plan-mode guide (three plan-mode cases), Vaughan sandbox internals (bwrap primary, Landlock fallback; does NOT state the unix-socket rejection, so that half was split into clm_028), Vaughan planning-mode (prompt-level only).
Local probes added: final launcher (ro_launcher.py) incl. git status identical inside/outside, setsid, x32 rule.
