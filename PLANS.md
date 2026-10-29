# PLANS.md — Staged Multi-Agent Execution Plan & Backlog

## 1. Execution Governance (Staged Build Pattern)
In accordance with the Codex Staged Build Pattern and Requirement 57 of the Master Specification, execution is divided into isolated, gate-verified chunks and phases. Every implementation unit must satisfy deterministic verification (`python -m unittest discover -s tests -v` and `python scripts/validate_handoff.py`) before completion.

## 2. Parallel Implementation Chunks (Current Repository Build)

| Chunk ID | Architectural Scope | Key Deliverables | Verification Gate |
| :--- | :--- | :--- | :--- |
| **Chunk 1** | **Policy Adapter, Governance & Security Hardening** | `AGENTS.md` (<120 lines, <6 KB), `CLAUDE.md` (15-line `@AGENTS.md` adapter), `GOALS.md`, `PLANS.md`, `DECISIONS.md`, `docs/ARCHITECTURE.md`, `docs/WORK_RECORD_2026-10-28.yaml`, `.agents/skills/*` (+ `.claude/skills` junction), `.claude/rules/*`, `.agents/rules/*`, `.claude/settings.json`, `.codex/config.toml`, `.codex/hooks.json`, `.agents/hooks.json`, `scripts/hooks/pre_tool_guard.py`, `scripts/hooks/stop_verify_gate.py`. | `AGENTS.md` budget check; `.claude/skills` junction check; `pre_tool_guard.py` (T09) and `stop_verify_gate.py` (T11) deterministic self-tests. |
| **Chunk 2** | **Bitemporal PIT Data Architecture & Runtime Concurrency Engine (Workload A & B)** | Eight-timestamp bitemporal store (`src/bitemporal/pit_schema.sql`, `src/bitemporal/pit_loader.py`, `src/bitemporal/state_evaluator.py`), `data/pit_store/` fixtures (`node_alpha_revision_fixture.json`, `manifest.json`), `scripts/ingest_pit.py`, .NET 8 C# runtime concurrency guard (`src/runtime/`), and `tests/test_pit_loader.py` (T05). | `python -m unittest tests/test_pit_loader.py -v` proving `pit_as_of('2026-06-01T12:00:00Z')` returns `0.12` (Revision 1) for `SYS-0001` (`NODE-ALPHA`) and never leaks `0.08` (2026-08-10 Revision 2). |
| **Chunk 3** | **Cross-Platform Handoffs, Evidence Hierarchy & Adversarial Suite (T01–T12)** | `src/verification/handoff_validator.py`, `src/verification/evidence_oracle.py`, `src/verification/tcvso_calculator.py`, `scripts/validate_handoff.py`, `tasks/ACTIVE_TASK.yaml`, `tasks/TASK-2026-1028-01.yaml`, `handoffs/HANDOFF-2026-1028-01.json`, `research/CLAIMS_REGISTER.yaml`, `benchmarks/BENCHMARK_MANIFEST.yaml`, `tests/test_adversarial_suite.py`. | Full unit and adversarial test suite (`T01`–`T12`) passing with exit code `0`. |

## 3. Six-Phase Operational Rollout Roadmap

### Phase 1: Foundation & Security Hardening (Day 1 — 60 mins)
- **Prerequisites:** Gate 0 operator confirmation of workload priorities, subscriptions, host OS, spend cap, and sandbox boundaries.
- **Concrete Actions:**
  1. Initialise Git repository structure (`tasks/`, `handoffs/`, `harness/`, `data/pit_store/`, `.agents/skills/`).
  2. Deploy Tier 1 root `./AGENTS.md` (<120 lines) and Tier 2 `./CLAUDE.md` (`@AGENTS.md` adapter).
  3. Configure `.claude/settings.json`, `.codex/config.toml` (removing retired `approval_policy = "untrusted"`), and `.agents/hooks.json` (`proceed-in-sandbox`, `useG1Credits: false`).
  4. Apply Quick Wins **QW-01** through **QW-05** (unset global `ANTHROPIC_API_KEY`, disable classifier auto-model-switching, migrate legacy workflows).
- **Acceptance Gate (Gate 1A):** Execute Adversarial Test **T09** (`pre_tool_guard.py` blocking `.env*`, `~/.ssh`, `rm -rf`, `git push --force`) and verify 100% deterministic denial (exit code `2`).
- **Rollback Procedure:** `git checkout -- .` and restore backed-up shell/settings profiles.

### Phase 2: Mandatory Standalone Pilot & PIT Store (Days 2–3 — 2 hours)
- **Prerequisites:** Phase 1 (Gate 1A) Pass.
- **Concrete Actions:**
  1. Deploy the 8-timestamp bitemporal schema (`pit_observations`) and `pit_as_of(cutoff_ts)` query logic (`FN-03`).
  2. Enable `PreToolUse` test-output filtering and `Stop` deterministic verification hook (`FN-02`).
  3. Execute the **Mandatory Working Pilot (`TASK-2026-1028-01`)**: implement the bitemporal PIT loader, simulate a mid-task session kill (**T02**), reconstruct state from `tasks/TASK-2026-1028-01.yaml` and `handoffs/HANDOFF-2026-1028-01.json`, and run the **T05** revision leak oracle.
- **Acceptance Gate (Gate 1B):** Pilot test suite exits `0`; **T05** confirms `0.12` state metric for `SYS-0001` (`NODE-ALPHA`) at `2026-06-01T12:00:00Z` cutoff; **T02** recovery loses 0 material decisions.
- **Rollback Procedure:** Remove pilot worktree (`git worktree remove --force`) and reset PIT store partition.

### Phase 3: Two-Platform Shared-Repo Integration (Days 4–5 — 1.5 hours)
- **Prerequisites:** Phase 2 (Gate 1B) Pass.
- **Concrete Actions:**
  1. Verify `.claude/skills` directory junction pointing to `.agents/skills` (`FN-01`).
  2. Execute two-platform worktree handoff (`AO-01` / Config 3 & Config 5): primary builder implements in isolated worktree, writes `handoffs/HANDOFF-*.json`, and independent model family (OpenAI Codex `gpt-6.1-sol` `/review` or Google Antigravity `/browser`) performs adversarial verification.
- **Acceptance Gate (Gate 2):** Cross-platform handoff completes with zero rule conflicts and passes **T01** (Single-Agent Challenge), **T03** (Concurrent Edit Detection), **T04** (False Consensus Override), and **T12** (Minimum-Complexity Challenge).
- **Rollback Procedure:** Revert to single-platform **Config 1** baseline.

### Phase 4: Controlled Benchmark Execution (Week 2 — 3 hours)
- **Prerequisites:** Gate 2 Pass + explicit operator approval of the £40 ($50 USD) benchmark spend cap.
- **Concrete Actions:** Execute the preregistered 12-task benchmark manifest (`BM-A1` through `BM-C4`, 3 counterbalanced repeats per task) across Configs 1, 2, 3, and 5 with held-out deterministic test oracles and zero AI self-scoring.
- **Acceptance Gate (Gate 3A):** Empirical TCVSO computed per workload; prune any multi-platform workflow that fails to beat single-agent TCVSO by the required margin.
- **Rollback Procedure:** Halt benchmark execution immediately if cumulative spend reaches £40.00.

### Phase 5: Selective Automation & Batching (Week 3 — Optional)
- **Prerequisites:** Gate 3A empirical proof of incremental value.
- **Concrete Actions:** Enable 50%-discounted Batch API runs for overnight PIT state evaluation backfills and read-only scheduled audits (Config 4).
- **Acceptance Gate (Gate 3B):** Scheduled/batch tasks remain strictly read-only or worktree-isolated within budget caps.
- **Rollback Procedure:** Disable scheduled jobs and sidecars.

### Phase 6: Adversarial Hardening & Version-Drift Cadence (Ongoing)
- **Prerequisites:** Operational deployment.
- **Concrete Actions:** Run the full **T01–T12** adversarial suite monthly and before model transitions (29 Oct 2026 Haiku 4.5 retirement; 2 Nov 2026 Antigravity Claude 4.6 / GPT-OSS-120b sunset; 1 Dec 2026 Gemini 4 Argon pricing step).
- **Acceptance Gate (Gate 4):** Zero high-severity residual risks; 100% of active claims in `research/CLAIMS_REGISTER.yaml` within valid `recheck_date` windows (**T10**).

## 4. Prioritised Quick Wins & Foundations Checklist
- [x] **QW-01:** Keep `ANTHROPIC_API_KEY` unset in global shell profiles to protect Pro/Max subscription routing.
- [x] **QW-02:** Disable silent classifier model-switching in Claude settings to protect the 1-hour prompt cache.
- [x] **QW-03:** Remove retired `approval_policy = "untrusted"` in `.codex/config.toml`; enforce `web_search = "cached"`.
- [x] **QW-04:** Use open-standard `.agents/skills/<name>/SKILL.md` (replacing deprecated `.agents/workflows/*.md`) and avoid sunset models.
- [x] **QW-05:** Prefer single-model `claude-sonnet-5-5` in Plan Mode on short (<4-turn) tasks over `/model opusplan`.
- [x] **FN-01:** Deploy Three-Tier Policy Adapter (`AGENTS.md` + `CLAUDE.md` `@AGENTS.md` + `.claude/skills` junction).
- [x] **FN-02:** Wire deterministic `pre_tool_guard.py` and `stop_verify_gate.py` across `.claude/`, `.codex/`, and `.agents/`.
- [x] **FN-03:** Deploy 8-timestamp bitemporal PIT schema (`pit_observations` + `pit_as_of` macro) and T05 revision leak oracle.
