# Evidence-Validated Multi-AI Operating System (`multi-ai-os-core`)

An evidence-validated, domain-agnostic Multi-AI Operating System orchestrating **Anthropic Claude Code**, **OpenAI Codex**, and **Google Antigravity** to minimize **Total Cost per Verified Successful Outcome (TCVSO)** under strict chronological-integrity, deterministic verification, and security constraints.

---

## 1. Core Architectural Pillars & Priority Workloads

| Workload Class | Scope & Stack | Target TCVSO | Primary Modules |
| :--- | :--- | :--- | :--- |
| **Workload A (`A_DATA_AND_ANALYTICS`)** | Data Engineering, Analytical Pipelines & Bitemporal Point-in-Time (PIT) State Integrity (`valid_from_utc <= cutoff_ts AND ingested_at_utc <= cutoff_ts`) | `<= £6.00` | `src/bitemporal/`, `data/pit_store/`, `tests/test_pit_loader.py` |
| **Workload B (`B_SOFTWARE_ENGINEERING`)** | Multi-File Systems, .NET 8 C# Deterministic Concurrency & CAS State Guards, Python Control Plane CLI, and Isolated Git Worktrees | `<= £5.00` | `src/runtime/`, `scripts/os_ctl.py`, `tests/test_os_ctl.py` |
| **Workload C (`C_DEEP_RESEARCH`)** | Primary-Source Claim Auditing, Untrusted Content Quarantine (`T06`), and Stateless Cross-Session Recovery (`T02`) | `<= £9.00` | `research/CLAIMS_REGISTER.yaml`, `tasks/`, `handoffs/`, `scripts/validate_handoff.py` |

### Non-Negotiable Operational Invariants
1. **Bitemporal PIT Integrity (`T05`):** Historical queries at cutoff `t_c` enforce both validity and system knowledge predicates (`valid_from_utc <= cutoff_ts AND ingested_at_utc <= cutoff_ts`) via `pit_as_of(cutoff_ts)`. Rows are never mutated in place; revisions append with `revision_num + 1`.
2. **Zero LLM Arithmetic:** All numerical aggregations, statistical metrics, latency/throughput calculations, and deterministic state transitions execute in deterministic Python or C# code—never via LLM token generation.
3. **Verification Before Completion (`T04` / `T11`):** Model agreement is never proof. **Level 1 Deterministic Oracles** (test exit codes, static typechecks, PIT SQL checks, SHA-256 hashes) override unanimous model consensus 100% of the time.
4. **Untrusted Content Quarantine (`T06`):** External payloads, PDFs, issues, and web pages are untrusted data and never acquire instruction authority.
5. **Stateless Disk Continuity (`T02`):** Git-tracked contracts (`tasks/*.yaml`, `handoffs/*.json`), `data/pit_store/`, and `research/CLAIMS_REGISTER.yaml` are the sole authoritative state across vendor boundaries.

---

## 2. Repository Directory Map

```text
multi-ai-os-core/
├── AGENTS.md                        # Canonical Tier-1 operational policy (<120 lines, <6 KB)
├── CLAUDE.md                        # Claude Code entry point (@AGENTS.md import + quick commands)
├── GOALS.md / PLANS.md / DECISIONS.md # Programme governance, roadmap, and architectural decisions
├── .agents/                         # Cross-platform skills (SKILL.md) and scoped rules
├── .claude/                         # Claude Code settings, hooks, and symlinked skills
├── .codex/                          # OpenAI Codex sandbox & approval configuration (config.toml)
├── docs/                            # System architecture (ARCHITECTURE.md) & work records
├── data/pit_store/                  # Append-only 8-timestamp bitemporal store & fixtures
├── src/
│   ├── bitemporal/                  # Python 3.12+ / DuckDB / SQLite bitemporal PIT engine & TCVSO router
│   └── runtime/                     # .NET 8 C# deterministic CAS state guard & concurrency verifier
├── scripts/
│   ├── os_ctl.py                    # Unified OS Control Plane CLI (status, new-task, handoff, verify, init-project)
│   ├── validate_handoff.py          # Zero-dependency YAML/JSON schema & SHA-256 handoff oracle
│   ├── run_benchmark_suite.py       # Workload A/B/C TCVSO empirical benchmark runner
│   └── hooks/                       # PreToolUse hard-deny guard & Stop verification gate
├── tasks/ & handoffs/               # Portable task contracts (YAML) & cryptographic handoffs (JSON)
├── research/                        # Audited claims register (YAML) & immutable source log (JSONL)
└── tests/                           # Unit, PIT, control-plane & T01–T12 adversarial red-team suite
```

---

## 3. Quick-Start & Deterministic Verification Commands

Run the full verification suite from the repository root before completing any task or cross-platform handoff:

```powershell
# 1. Full Python Unit, PIT, Control Plane & Adversarial Suite
python -m unittest discover -s tests -v

# 2. Unified OS Control Plane Status & Contract Verification
python scripts/os_ctl.py status
python scripts/os_ctl.py verify --task-id TASK-2026-1028-01 --handoff-id HANDOFF-2026-1028-01

# 3. Bitemporal PIT Revision Leak Check (Test T05)
python -m unittest tests/test_pit_loader.py -v

# 4. Task & Handoff Cryptographic Schema Gate (Tests T02 / T03 / T11)
python scripts/validate_handoff.py

# 5. Deterministic Hook Self-Verification (Test T09)
python scripts/hooks/pre_tool_guard.py --self-test
python scripts/hooks/stop_verify_gate.py --self-test

# 6. .NET 8 C# Runtime Concurrency & CAS Guard (Workload B)
dotnet run --project src/runtime/
```

---

## 4. Security Boundaries & Human-Gated Operations

- **Protected Paths (`scripts/hooks/pre_tool_guard.py`):** Reading or writing `.env*`, `~/.ssh/**`, `~/.aws/**`, `**/credentials*`, `secrets/**`, or mutating `data/raw/**` and `.git/config` is deterministically blocked (`exit code 2`).
- **Destructive & External Commands:** `rm -rf`, `git push --force`, `git reset --hard`, and autonomous remote pushes are blocked by policy (`OD-5 = 5C`). Remote synchronization (`git push`) is strictly human-executed.
