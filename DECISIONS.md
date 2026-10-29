# DECISIONS.md — Architectural Decision Record (ADR) Log

Every architectural decision in this repository is governed by primary vendor documentation verified as of 28 October 2026, parametric TCVSO modeling, and deterministic red-team verification (`P0-01` through `P2-14`, `T01` through `T12`).

---

## ADR-001: Three-Tier Authoritative Policy & Skill Adapter Architecture
- **Date:** 2026-10-28
- **Status:** Accepted (Desk-Verified & Implemented in Chunk 1)
- **Red-Team Findings Addressed:** `P0-05` (Cross-platform runtime state isolation), `P1-07` (Conflicting instruction discovery and precedence traps).
- **Context:**
  1. Claude Code ignores `AGENTS.md` whenever `CLAUDE.md` exists in the repository root unless `CLAUDE.md` explicitly imports `@AGENTS.md`.
  2. OpenAI Codex walks directories **top-down** (`~/.codex/` -> Git root -> `$CWD`), picking one file per directory (`AGENTS.override.md > AGENTS.md`) up to `project_doc_max_bytes` (32 KiB default).
  3. Google Antigravity walks directories **bottom-up** (`$FILE_DIR` -> workspace root), cumulatively combining `AGENTS.md`, `GEMINI.md`, and flat `.agents/rules/*.md` files (requiring snake_case `trigger:` frontmatter, 24 KB per-file cap, 20,000-token aggregate budget).
  4. Both Codex and Antigravity natively discover `.agents/skills/<name>/SKILL.md`, whereas Claude Code discovers `.claude/skills/<name>/SKILL.md`.
- **Decision:**
  1. Maintain a single authoritative root `./AGENTS.md` strictly `< 120 lines` and `< 6 KB`.
  2. Place a 15-line `./CLAUDE.md` adapter at the repository root whose first line is `@AGENTS.md`, followed by deterministic `# Compact instructions` and Claude-specific cache rules.
  3. Store all canonical skills in `.agents/skills/<name>/SKILL.md` and link `.claude/skills` -> `.agents/skills` via a directory junction / symlink.
  4. Keep runtime-specific rules scoped in `.claude/rules/*.md` (`paths:` frontmatter) and flat `.agents/rules/*.md` (`trigger: glob` or `trigger: model_decision` snake_case frontmatter).
- **Rejected Alternatives:** Maintaining separate, manually synchronised copies of repository rules across `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` (guaranteed instruction drift and silent truncation).

---

## ADR-002: Selection of Architecture F (Pragmatic Hybrid) & Configurations 1, 2, 3, and 5
- **Date:** 2026-10-28
- **Status:** Accepted (Baseline Config 1 & Two-Platform Configs 2, 3, 5 Retained; Config 4 Conditional; Arch C & E Rejected)
- **Red-Team Findings Addressed:** `P0-02` (TCVSO objective), `P0-05` (ToS & harness boundaries), `P1-06` (Single-agent sufficiency), `P1-11` (Full lifecycle cost accounting).
- **Context:** Parametric TCVSO modeling across Workloads A, B, and C demonstrates that single-agent execution paired with deterministic test/SQL oracles (**Config 1**) is Pareto-optimal for routine tasks ($\le 3$ files, mechanical edits, standard unit tests). For correctness-critical multi-file software engineering (**Workload B**) and bitemporal state analytical pipelines (**Workload A**), adding a **second model family** via isolated Git worktrees and structured handoffs (**Architecture B / Architecture F — Configs 3 & 5**) reduces modeled TCVSO from **£6.67 to £4.60** (Workload B) and from **£7.20 to £5.76** (Workload A) by catching silent defects before human review. Conversely, building a central 3-platform orchestrator (**Architecture C**) or enabling multi-agent swarms (**Architecture E** / `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) multiplies plan-mode token usage by $\sim 7\times$, busts prompt caches, violates consumer subscription ToS boundaries, and inflates TCVSO to **£12.42–£14.90**.
- **Decision:**
  - **Retain Architecture A & F (Configs 1, 2, 3, 5):** Default to single-agent + deterministic oracle (**Config 1**) for routine work; escalate to two-platform shared-repo worktree handoffs (**Config 3** for multi-file systems & .NET 8 C# runtime modules, **Config 5** for bitemporal state & analytical pipelines, **Config 2** for primary-source research) only when cross-family verification reduces TCVSO.
  - **Restrict Config 4 (Architecture D/E):** Conditional on embarrassingly parallel, read-only audits or worktree-isolated `/batch` migrations.
  - **Reject Architecture C & Unbounded Swarms (`RJ-01`):** Do not build a custom 3-platform central orchestrator or enable `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` for sequential or write-heavy engineering.

---

## ADR-003: Eight-Timestamp Bitemporal PIT Schema & Payload Separation
- **Date:** 2026-10-28
- **Status:** Accepted (Verified in Deterministic Code via Test T05)
- **Red-Team Findings Addressed:** `T05` (Historical revision look-ahead leak), `P1-10` (Append-only immutability vs vendor correction, licensing expiry, and GDPR redaction).
- **Context:** Analytical pipelines and deterministic state evaluators fail silently if historical queries read backdated state revisions or omit deprecated/renamed entities that were active at the historical cutoff $t_c$. However, strict append-only storage must also accommodate upstream error corrections and legal/licensing erasure requests without corrupting audit lineage.
- **Decision:**
  1. Store all observations in `pit_observations` (DuckDB/SQLite + Zstandard Parquet in `data/pit_store/`) using **8 UTC timestamps**: `event_time_utc`, `published_at_utc`, `first_avail_utc`, `valid_from_utc`, `valid_to_utc`, `ingested_at_utc`, `superseded_at_utc`, plus IANA `source_tz` / `exchange_tz`.
  2. Enforce the deterministic `pit_as_of(cutoff_ts)` query macro requiring `valid_from_utc <= cutoff_ts AND ingested_at_utc <= cutoff_ts AND tombstone_status IN ('ACTIVE', 'CORRECTED')`, windowed by `(entity_id, metric_name, event_time_utc)` ordered by `ingested_at_utc DESC, revision_num DESC`.
  3. Reconcile immutability with erasure (`P1-10`) by storing raw upstream blobs in partitioned payload files (`data/payloads/vendor=<v>/`) while keeping cryptographic `raw_payload_sha256` and `tombstone_status` (`REDACTED_PII` or `LICENSE_EXPIRED`) in `pit_observations`.

---

## ADR-004: Four-Tier Evidence Hierarchy Oracle & Deterministic Lifecycle Hooks
- **Date:** 2026-10-28
- **Status:** Accepted (Enforced via `scripts/hooks/` and `src/verification/`)
- **Red-Team Findings Addressed:** `P1-08` (Upfront security constraints), `P1-12` / `T04` (Model agreement falsely treated as proof), `T09` (Permission challenge), `T11` (Completion without verification evidence).
- **Context:** Instruction files (`AGENTS.md`, `CLAUDE.md`) are model-discretionary and can be ignored under context pressure or prompt injection. Furthermore, multiple LLMs frequently share correlated training biases and can unanimously approve a flawed state calculation or off-by-one formula (**T04**).
- **Decision:**
  1. Enforce security boundaries deterministically via `scripts/hooks/pre_tool_guard.py` wired into `.claude/settings.json`, `.codex/hooks.json`, and `.agents/hooks.json` (`PreToolUse`), returning exit code `2` on any attempt to access `.env*`, `~/.ssh`, `~/.aws`, `secrets/**`, `data/raw/**` writes, or destructive shell commands (`rm -rf`, `git push --force`, `git reset --hard`) or live production mutation endpoints.
  2. Enforce completion verification deterministically via `scripts/hooks/stop_verify_gate.py` (`Stop` hook), blocking task completion unless unit tests pass (`exit_code == 0`) and active handoff manifests validate cleanly.
  3. Adjudicate all cross-agent disagreements via the **4-Tier Evidence Hierarchy Oracle**: **Level 1** (Deterministic test/SQL/SHA-256 execution) > **Level 2** (Primary vendor/system source with URL and date) > **Level 3** (Cross-family adversarial competing hypothesis) > **Level 4** (Human arbitration gate in `tasks/ACTIVE_TASK.yaml`).

---

## ADR-005: Gate 0 Operator Sign-Off (`OD-1..OD-5`) & Host Conditional Calibration (`CD-1..CD-6`)
- **Date:** 2026-10-29
- **Status:** Locked & Active (`GATE_0_APPROVED`)
- **Decisions Locked by Operator:**
  1. **`OD-1 = 1B` (Risk-Weighted Tri-Workload Lock):** Lock **Workload A (`A_DATA_AND_ANALYTICS` — Data Engineering, Analytical Pipelines & Bitemporal State Integrity = 45% weight, target TCVSO <= £6.00)**, **Workload B (`B_SOFTWARE_ENGINEERING` — Software Engineering, Multi-File Systems & Runtime Concurrency = 35% weight, target TCVSO <= £5.00)**, and **Workload C (`C_DEEP_RESEARCH` — Deep Technical Research & Stateless Continuity = 20% weight, target TCVSO <= £9.00)**, led by the Phase 2 Workload A Bitemporal Pilot (`TASK-2026-1028-01`).
  2. **`OD-2 = 2C` (Subscription-First + Zero Global API Key Override):** Keep `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` strictly unset across Windows `Process`, `User`, and `Machine` scopes so interactive sessions use subscription sign-in (`claude /login`, `codex login`, `agy login`) and preserve the 1-hour subscription prompt cache TTL (`PB-10` / `QW-01`). Enforce `"useG1Credits": false` in Google Antigravity and inject API keys only inside ephemeral process-scoped wrappers when explicitly running headless Batch API / SDK jobs.
  3. **`OD-3 = 3B` (Native Windows 11 NTFS + Native CLI Sandboxes + Python-Backed Hooks):** Execute natively on Windows 11 NTFS (`NT 10.0.26200.0`) with PowerShell and native Windows binaries (`claude 2.1.311`, `codex 0.164.0`, `agy 1.4.8`, `Python 3.15.2`, `.NET 8.0.100`), avoiding WSL2 `/mnt/c/` 9P filesystem degradation and using Python-backed hooks (`scripts/hooks/pre_tool_guard.py`, `scripts/hooks/stop_verify_gate.py`).
  4. **`OD-4 = 4B` (£0 Overage / Subscription-Quota-Only Validation Baseline):** Execute all Phase 1–4 validation and deterministic oracle benchmarks within included subscription quotas at **£0.00 out-of-pocket API overage** (`max_session_spend_gbp: 2.50` circuit breaker), gating any paid external API invoice trials behind a separate explicit approval.
  5. **`OD-5 = 5C` (OS-Enforced `workspace-write` Sandbox + Hard `deny` Rules + Human External Gate):** Enforce `acceptEdits` (Claude Code), `sandbox_mode = "workspace-write"` + `approval_policy = "on-request"` + `web_search = "cached"` (Codex), and `proceed-in-sandbox` + `enableTerminalSandbox: true` (Antigravity) inside isolated worktrees, paired with hard `deny` rules on secrets/raw data and mandatory human approval for `git push`, `main` merges, and external network writes.
  6. **`CD-1` through `CD-6` (Playbook & Host Calibrations):**
     - `CD-1 (PB-04)`: Default to single-model `claude-sonnet-5-5` (`high`/`xhigh` effort) in `Shift+Tab` Plan Mode; reserve `/model opusplan` for tasks with $\ge 4$ execution turns and $>15,000$ output tokens.
     - `CD-2 (PB-06)`: Enforce the 5,000-token (~180-line) size gate (`@file` when known and $<5,000$ tokens; bare path when $\ge 5,000$ tokens).
     - `CD-3 (P1-07)`: Use Windows NTFS Directory Junctions (`mklink /J`) for `.claude\skills -> .agents\skills` via `scripts/ensure_links.py`.
     - `CD-4 (FN-03)`: Use the Dual-Engine Bitemporal Store (`SQLite 3.53.4` built-in stdlib + `DuckDB 2.0` SQL parity) in `src/bitemporal/pit_loader.py`.
     - `CD-5 (§10/§18)`: Reject Arch C & E for routine work (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0`); restrict Arch D to read-only audits and Config 4 to $\ge 10$-file independent fan-out.
     - `CD-6 (T10)`: Pin current-generation models (`claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-opus-5-5`, `gpt-6.1-sol`, `gpt-6-luna`, `gemini-3.8-flash`, `gemini-4-argon`) and enforce sunset checks via `T10`.
