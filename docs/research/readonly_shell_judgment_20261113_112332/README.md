# readonly_shell_judgment_20261113_112332

Research session (insane-research, Phases 2–7): how coding agents decide a shell command is read-only / safe without approval (2025–2026), and a recommendation for dcode's pre-plan `execute`.

- `outputs/00_executive_summary.md` — Korean summary and recommendation
- `outputs/01_full_report.md` — compact full report; section 7 is the unresolved annex with the per-tool comparison table
- `outputs/{verified,unresolved,refuted}_claims.json`, `outputs/eval_report.json` — gate outputs
- `artifacts/agent_results/` — 5 research agents' raw findings with verbatim quotes
- `artifacts/exec/` — local probes on this WSL2 machine; `ro_launcher.py` is the recommended prototype
- `artifacts/claim_ledger.jsonl`, `artifacts/build_ledger.py`, `artifacts/expansion_log.md`
- `sources/sources.jsonl`, `sources/bibliography.md`

Gates: `validate_ledger.py` pass (29 verified / 35 unresolved / 0 refuted, 55% unresolved warning), `verify_report.py` pass, `eval_report.py` PASS. `snapshot_sources.py` exited 2 (insane-search engine not installed), so every high-risk claim stayed unresolved; this is recorded in `state.json` limitations, not bypassed.
