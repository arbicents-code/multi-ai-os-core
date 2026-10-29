# Multi-AI Operating System — Operator Playbook & Daily Quickstart Guide

**Document Version:** 1.0.0  
**Host Platform:** Native Windows 11 NTFS (`NT 10.0.26200.0`) + PowerShell (`OD-3 = 3B`)  
**Installed CLI Toolchains:** `claude 2.1.311` | `codex 0.164.0` | `agy 1.4.8` | `Python 3.15.2` | `.NET 8.0.100`  
**Governance Lock:** `OD-1 = 1B` | `OD-2 = 2C` | `OD-3 = 3B` | `OD-4 = 4B` | `OD-5 = 5C` (`CD-1`..`CD-6`)

---

## 1. Quickstart & Daily Workflow (`scripts/os_ctl.py`)

The Multi-AI Operating System provides a unified, deterministic operator CLI (`scripts/os_ctl.py`) to inspect environment readiness, spawn routed task contracts, generate cryptographic cross-platform handoffs, execute Level 1 verification gates, and bootstrap new domain projects.

### 1.1 Check System Status & Host Calibration
Run the status command at the start of a work session to confirm that the Three-Tier Policy Adapter (`AGENTS.md` + `CLAUDE.md` + `.claude/skills` junction), subscription-first environment variables (`OD-2 = 2C`), bitemporal PIT store, and active task contracts are healthy:

```powershell
python scripts/os_ctl.py status
```

**What it verifies:**
- `AGENTS.md` is strictly `< 120` lines and `< 6 KB`, and `CLAUDE.md` starts with `@AGENTS.md`.
- `.claude\skills` is linked via a Windows NTFS Directory Junction (`mklink /J`) to `.agents\skills` (`CD-3`).
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` are unset in global scopes (`Process`, `User`, `Machine`) so interactive sessions route through subscription plans and preserve the 1-hour prompt cache TTL (`OD-2 = 2C`).
- Current `tasks/ACTIVE_TASK.yaml` state, active worktrees, and latest `handoffs/HANDOFF-*.json` manifest status.

### 1.2 Spawn a Routed Task (`new-task`)
When starting a new engineering, data pipeline, or research unit, create a schema-validated task contract (`tasks/TASK-<ID>.yaml`) and automatically route it to the lowest-TCVSO configuration (`Config 1`, `Config 2`, `Config 3`, or `Config 5`):

```powershell
# Example A: Bitemporal data pipeline task (routes to Config 5)
python scripts/os_ctl.py new-task `
  --task-id TASK-2026-1029-01 `
  --title "Add bitemporal retention window check to PIT state evaluator" `
  --workload A_DATA_AND_ANALYTICS `
  --files 4 `
  --activate

# Example B: Multi-file software / C# concurrency task (routes to Config 3)
python scripts/os_ctl.py new-task `
  --task-id TASK-2026-1029-02 `
  --title "Extend RuntimeStateGuard sequence lock diagnostics" `
  --workload B_SOFTWARE_ENGINEERING `
  --files 5 `
  --activate
```

### 1.3 Create a Cryptographic Cross-Platform Handoff (`handoff`)
Before switching model families (e.g., handing off from **Claude Code** implementation to **OpenAI Codex** `/review` or **Google Antigravity** `/browser`), before running `/clear`, or before ending a session (`T02`), generate a SHA-256-verified handoff manifest:

```powershell
python scripts/os_ctl.py handoff `
  --handoff-id HANDOFF-2026-1029-01 `
  --task-id TASK-2026-1029-01 `
  --from-agent claude-code:claude-sonnet-5-5 `
  --to-agent openai-codex:gpt-6.1-sol `
  --summary "Implemented bitemporal retention check and verified T05 PIT isolation" `
  --run-tests
```

**What it records (`handoffs/HANDOFF-<ID>.json`):**
- Current `git_head_sha` and monotonic `state_version` (preventing concurrent lost updates under `T03`).
- Per-file SHA-256 checksums (`modified_files[].sha256`) for all touched files.
- Fresh Level 1 deterministic verification evidence (`exit_code: 0`, command, UTC timestamp).

### 1.4 Run the Full Verification Gate Before Merge (`verify`)
Never merge a worktree or mark a task `COMPLETED` without running the deterministic verification suite (`T04` / `T11`):

```powershell
python scripts/os_ctl.py verify
```

**What it executes:**
1. **Hook Self-Tests (`T09` & `T11`):** `python scripts/hooks/pre_tool_guard.py --self-test` and `python scripts/hooks/stop_verify_gate.py --self-test`
2. **Task & Handoff Schema Gate (`T02`/`T03`/`T04`):** `python scripts/validate_handoff.py`
3. **Python Unit, Bitemporal PIT (`T05`) & Adversarial Suite (`T01–T12`):** `python -m unittest discover -s tests -v`
4. **C# Runtime Concurrency Guard (`Workload B`):** `dotnet run --project src/runtime/`

### 1.5 Bootstrap a Brand-New Domain Project (`init-project`)
To scaffold a new domain-isolated project directory equipped with the Three-Tier Policy Adapter (`AGENTS.md` + `CLAUDE.md` `@AGENTS.md`), `.agents/skills` junction, lifecycle hooks, `tasks/`, and `handoffs/` directories:

```powershell
python scripts/os_ctl.py init-project --target-dir ./projects/my-app --name "My App"
```

---

## 2. Workload-to-Configuration Routing Matrix (`OD-1 = 1B`)

Under **ADR-002** and **ADR-005 (`OD-1 = 1B`)**, the operating system optimises **Total Cost per Verified Successful Outcome (TCVSO)** across three risk-weighted priority workloads (**45% Workload A**, **35% Workload B**, **20% Workload C**).

$$\text{TCVSO} = \frac{\sum_{i=1}^{N_{\text{total}}} \left( C_{\text{compute}, i} + C_{\text{retry}, i} + C_{\text{human}, i} + C_{\text{setup\_amortised}, i} \right)}{N_{\text{verified\_pass}}}$$

Human review and repair time ($C_{\text{human}}$) is valued at **£1.00/minute (£60.00/hour)**. Routing tasks to the minimum effective configuration reduces composite TCVSO from **£8.65** (unassisted single-agent baseline on complex tasks) to **£5.89** (**31.91% reduction**), while avoiding the **£12.42–£15.37** cost explosion of 3-platform swarms (`Architecture C` / `Architecture E`).

| Configuration | Target Workload & Trigger Condition | Primary Builder | Independent Verifier / Oracle | Modeled TCVSO (vs Config 1) |
| :--- | :--- | :--- | :--- | :--- |
| **Config 1: Single-Agent + Deterministic Oracle** | **Routine Tasks ($\le 3$ files):** Localised bug fixes, schema updates, documentation, or single-module unit tests across any workload (`P1-06` / `T12`). | **Claude Code** (`claude-sonnet-5-5`) *or* **Codex** (`gpt-6.1-sol`) | **Level 1 Deterministic Oracle** (`unittest`, `dotnet run`, `validate_handoff.py`) — zero second-LLM overhead. | **£3.20–£4.50** on routine tasks *(£8.65 composite average if misapplied to complex tasks)* |
| **Config 2: Research & Primary-Source Audit** | **Workload C (`C_DEEP_RESEARCH` — 20% weight):** Vendor capability audits, primary-source synthesis, `research/CLAIMS_REGISTER.yaml` updates, and untrusted content ingestion (`T06`, `T10`). Target $\le \text{£9.00}$. | **Claude Code** (`claude-sonnet-5-5` / `claude-opus-5-5`) *or* **Antigravity** (`gemini-4-argon` 1M context) | **Cross-Family Adversarial Auditor** (`gpt-6.1-sol`) + **Level 2 Primary-Source Oracle** (URL + `verified_date` + `recheck_date`). | **£8.45** *(beats £10.80 single-agent baseline by 21.8%)* |
| **Config 3: Two-Platform Shared-Repo Worktree + `/review` or `/browser`** | **Workload B (`B_SOFTWARE_ENGINEERING` — 35% weight):** Multi-file backend/frontend systems ($>3$ files), `.NET 8` C# concurrency guards (`src/runtime/`), and interactive UI tools (`docs/os_control_center.html`). Target $\le \text{£5.00}$. | **Claude Code** (`claude-sonnet-5-5` in `Shift+Tab` Plan Mode) in isolated Git worktree | **OpenAI Codex** (`gpt-6.1-sol` `/review` for AST/concurrency) *or* **Google Antigravity** (`gemini-3.8-flash` `/browser` for DOM/UI) + **Level 1 Test Suite**. | **£4.60** *(beats £7.50 single-agent baseline by 38.7%)* |
| **Config 4: Conditional Read-Only / Worktree Fan-Out** | **Conditional ($\ge 10$ independent files):** Embarrassingly parallel read-only repository audits or isolated `/batch` mechanical migrations (`CD-5`). Never used for coupled writes. | **Claude Code** (`/batch`) *or* **Codex** (`gpt-6-luna` subagents) | **Level 1 Deterministic Test Suite** + SHA-256 manifest verification across worktrees. | **£6.90** *(conditional; restricted by `CD-5`)* |
| **Config 5: Two-Platform + 8-Timestamp Bitemporal PIT Oracle** | **Workload A (`A_DATA_AND_ANALYTICS` — 45% weight):** DuckDB/SQLite/Parquet bitemporal pipelines (`src/bitemporal/`), deterministic state evaluators, and revision-isolated historical queries (`T05`). Target $\le \text{£6.00}$. | **Claude Code** (`claude-sonnet-5-5`) in isolated Git worktree | **OpenAI Codex** (`gpt-6.1-sol`) adversarial SQL/boundary review + **Level 1 `pit_as_of(cutoff_ts)` Oracle (`T05`)**. | **£5.76** *(beats £8.60 single-agent baseline by 33.0%)* |

### Decision Flowchart for Operators
1. **Does the task touch $\le 3$ files with complete deterministic unit test coverage and no cross-cutting schema/concurrency risk?**  
   $\rightarrow$ Use **Config 1** (Single Agent + Level 1 Oracle). Do not pay cross-platform handoff overhead (`T01` / `T12`).
2. **Does the task modify bitemporal tables, ingestion schemas, `pit_as_of(cutoff_ts)` logic, or deterministic state metrics (`Workload A`)?**  
   $\rightarrow$ Use **Config 5** (Builder in worktree + `test_pit_loader.py` `T05` oracle + cross-family Codex review).
3. **Does the task span $>3$ code files, `.NET 8` C# concurrency locks (`src/runtime/`), or HTML/JS UI artifacts (`Workload B`)?**  
   $\rightarrow$ Use **Config 3** (Builder in worktree + Codex `/review` for backend/concurrency or Antigravity `/browser` for UI verification).
4. **Does the task synthesize external documentation, vendor pricing/quotas, or technical claims (`Workload C`)?**  
   $\rightarrow$ Use **Config 2** (Primary researcher + `research/CLAIMS_REGISTER.yaml` + cross-family falsification check).

---

## 3. Platform-Specific Execution Rules (`CD-1`..`CD-6`)

### 3.1 Anthropic Claude Code (`v2.1.311`)
- **Subscription-First Authentication (`OD-2 = 2C` / `QW-01`):**
  - Always authenticate interactively via `claude /login` (Pro/Max/Team subscription).
  - Verify that `ANTHROPIC_API_KEY` is **unset** in Windows `Process`, `User`, and `Machine` environment scopes before starting interactive sessions. A stray `ANTHROPIC_API_KEY` silently diverts interactive sessions to metered Console API billing and forfeits subscription quota.
- **Single-Model Plan Mode vs. `/model opusplan` (`CD-1` / `PB-04`):**
  - **Default Rule:** Stay on single-model `claude-sonnet-5-5` when toggling `Shift+Tab` Plan Mode, adjusting effort (`high` or `xhigh`) via `/effort`. Changing effort on Claude 5.5 preserves the 1-hour prompt cache prefix (`CLM-02`), whereas switching models via `/model opusplan` invalidates the prompt cache and triggers a full cache re-write penalty (`1.25x` for 5m TTL, `2.0x` for 1h TTL).
  - **When `/model opusplan` is Justified:** Only switch to `/model opusplan` (or `claude-opus-5-5`) on deep architectural tasks projected to run **$\ge 4$ execution turns AND $> 15,000$ output tokens**, where Opus planning saves enough downstream retry turns to amortise the cache bust.
- **The 5,000-Token (`~180 Lines`) `@file` vs. Bare Path Rule (`CD-2` / `PB-06`):**
  - **Small, known files ($< 5,000$ tokens / $\le 180$ lines):** Reference directly with `@path/to/file` in your prompt to save a tool-discovery turn.
  - **Large files ($\ge 5,000$ tokens / $> 180$ lines) or exploratory searches:** Pass the **bare file path** (without `@`) so Claude Code reads targeted line ranges via tool calls instead of injecting the entire file into the permanent prompt prefix on every turn.
- **Experimental Swarms Disabled (`CD-5`):** Keep `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0` in `.claude/settings.json` to prevent $7\times$ plan-mode token inflation.

### 3.2 OpenAI Codex CLI (`v0.164.0`)
- **Model Selection (`CD-6`):**
  - **`gpt-6.1-sol` (Default Flagship — 500k context):** Use for cross-family `/review` audits, C#/.NET concurrency analysis, SQL bitemporal boundary verification, and multi-file implementation in Configs 1, 3, and 5.
  - **`gpt-6-luna` (High-Speed Subagent / Mechanical Worker):** Use for high-volume mechanical refactors, boilerplate test generation, and read-only explorer subagents.
  - **Retired Models (`T10`):** Never invoke retired `gpt-5.5` (retired 14 Oct 2026).
- **Sandbox & Configuration Posture (`OD-5 = 5C` / `QW-03`):**
  - Configured in `.codex/config.toml` with `sandbox_mode = "workspace-write"`, `approval_policy = "on-request"` (replacing the retired `"untrusted"` setting), and `web_search = "cached"`.
  - Top-down instruction discovery reads `./AGENTS.md` automatically at the repository root (capped at `32 KiB`).
- **Worktree-Isolated Reviews:** Run `python scripts/worktree_manager.py create --task-id <ID> --agent codex` to run Codex `/review` in an isolated worktree without contending with an active Claude Code working tree (`T03`).

### 3.3 Google Antigravity (`v1.4.8`)
- **Model Selection & 1 Dec 2026 Pricing Step (`CD-6` / `CLM-05`):**
  - **`gemini-3.8-flash`:** Default for rapid repository navigation, UI inspection, and `/browser` end-to-end DOM/visual verification (`BM-B3` on `docs/os_control_center.html`).
  - **`gemini-4-argon` (1M-Token Context + Implicit Caching):** Reserve for deep cross-repository synthesis, full-archive ingestion (`Workload C`), and massive log analysis. **Cost Alert (`CLM-05`):** `gemini-4-argon` introductory pricing (`$2.00 / $10.00` per MTok) doubles to **`$4.00 / $20.00` per MTok on 1 December 2026**—re-evaluate Workload C TCVSO routing before 1 Dec 2026.
  - **Sunset Models (`T10`):** Never configure `claude-sonnet-4-6`, `claude-opus-4-6`, or `gpt-oss-120b` inside Antigravity (all sunset on **2 November 2026**).
- **Credit & Sandbox Protection (`OD-2 = 2C` & `OD-5 = 5C`):**
  - `.agents/hooks.json` enforces `"toolPermission": "proceed-in-sandbox"`, `"enableTerminalSandbox": true`, and `"useG1Credits": false` so sessions never silently burn Google One credit balances.
- **Bottom-Up Rules & Skills (`ADR-001`):**
  - Antigravity walks directories bottom-up and scans `.agents/rules/*.md` (requiring snake_case `trigger:` frontmatter) and `.agents/skills/<name>/SKILL.md` (legacy `.agents/workflows/` is deprecated as of 19 Oct 2026).

---

## 4. Security, Recovery & Verification Reference

Every session across Claude Code, OpenAI Codex, and Google Antigravity is protected by four deterministic Python enforcement scripts and the 8-timestamp bitemporal PIT oracle.

| Enforcement Module | CLI Invocation | Red-Team Test IDs | Operational Guarantee |
| :--- | :--- | :--- | :--- |
| **`scripts/hooks/pre_tool_guard.py`** | `python scripts/hooks/pre_tool_guard.py --self-test` *(wired to `PreToolUse` in `.claude/`, `.codex/`, `.agents/`)* | **`T09`** (Permission Challenge)<br>**`T06`** (Untrusted Quarantine) | Deterministically blocks (exit code `2`) any read/write access to `.env*`, `~/.ssh/**`, `~/.aws/**`, `**/credentials*`, `secrets/**`, writes to `data/raw/**` or `.git/config`, and destructive or external mutation commands (`rm -rf`, `git push --force`, `git reset --hard`). |
| **`scripts/hooks/stop_verify_gate.py`** | `python scripts/hooks/stop_verify_gate.py --self-test` *(wired to `Stop` hook across all 3 platforms)* | **`T11`** (Stop Verification Gate)<br>**`T04`** (False Consensus Override) | Blocks agent completion (exit code `2`) if `tasks/ACTIVE_TASK.yaml` claims completion without fresh `exit_code == 0` test evidence or if the unit test suite fails. |
| **`scripts/validate_handoff.py`** *(backed by `src/verification/`)* | `python scripts/validate_handoff.py` | **`T02`** (Stateless Session Recovery)<br>**`T03`** (Concurrent Edit Detection)<br>**`T04`** (4-Tier Evidence Oracle)<br>**`T10`** (Claims Expiry Check) | Validates `tasks/*.yaml` and `handoffs/*.json` schemas, recalculates SHA-256 hashes of all listed `modified_files` to catch unrecorded concurrent edits (`T03`), verifies Level 1 oracle precedence over LLM agreement (`T04`), and audits `research/CLAIMS_REGISTER.yaml` for expired `recheck_date` entries (`T10`). |
| **`scripts/worktree_manager.py`** | `python scripts/worktree_manager.py list`<br>`python scripts/worktree_manager.py create --task-id <ID> --agent <name>` | **`T03`** (Worktree Isolation & Merge Safety) | Creates, lists, verifies, and prunes isolated Git worktrees under `.worktrees/` so two platforms never edit the same working tree simultaneously. |
| **`src/bitemporal/pit_loader.py`** & **`tests/test_pit_loader.py`** | `python -m unittest tests/test_pit_loader.py -v` | **`T05`** (Bitemporal PIT Revision Isolation) | Enforces `valid_from_utc <= cutoff_ts AND ingested_at_utc <= cutoff_ts AND tombstone_status IN ('ACTIVE', 'CORRECTED')` via `pit_as_of(cutoff_ts)`. Guarantees zero look-ahead leakage (`NODE-ALPHA` rev 1 vs rev 2; `SERVICE-BRAVO` rev 1 vs rev 2), retains `LEGACY-NODE-DEPRECATED` for historical cohort completeness, and excludes `TOMBSTONED_RECORD`. |

### Stateless Session Recovery Procedure (`T02`)
If an agent session crashes, hits a 5-hour rolling quota boundary (`CLM-01`), or is intentionally cleared via `/clear`:
1. Start a fresh session in any supported platform (`claude`, `codex`, or `agy`).
2. Run `python scripts/os_ctl.py status` and `python scripts/validate_handoff.py`.
3. Instruct the agent: *"Read `tasks/ACTIVE_TASK.yaml` and the referenced `handoffs/HANDOFF-*.json` manifest, verify all file SHA-256 hashes match disk state, and resume from the first pending acceptance criterion."*
4. Zero conversational memory is required; 100% of architectural decisions, file hashes, and verification gates are recovered deterministically from disk in under 2 minutes.
