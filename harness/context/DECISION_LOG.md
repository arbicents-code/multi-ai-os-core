# Material Decision Log (`harness/context/DECISION_LOG.md`)

**Governance Rule:** Only decisions passing the **Materiality Test** (affecting cross-module interfaces, security boundaries, bitemporal correctness, or platform cost routing) are persisted here. Conversational scratchpads are excluded.

---

## DEC-2026-1028-01: Three-Tier Unified Repository Policy Adapter (Resolves P1-07)
- **Context:** Claude Code ignores `AGENTS.md` if `CLAUDE.md` is present unless imported; OpenAI Codex walks top-down (`32 KiB` cap); Google Antigravity walks bottom-up (`24 KB`/file cap, `20k` token budget, flat `.agents/rules/*.md` scan requiring `snake_case` trigger).
- **Decision:** Keep canonical policy in root `./AGENTS.md` (`< 120` lines), import `@AGENTS.md` on line 1 of root `./CLAUDE.md`, store canonical skills in `.agents/skills/<name>/SKILL.md`, and link `.claude/skills` -> `../.agents/skills`.
- **Status:** `ACCEPTED_VERIFIED`

## DEC-2026-1028-02: Reject 3-Platform Swarms; Retain Config 1 Baseline & Config 3/5 Worktree Handoffs (Resolves P0-05, P1-06, P1-11)
- **Context:** Three-platform central orchestrators and experimental Agent Teams multiply token burn up to 7x in plan mode, invalidate prompt caches on model switches, and violate consumer subscription ToS.
- **Decision:** Default to **Config 1** (Single Platform + Deterministic Oracles) for routine tasks (<= 3 files). Escalate to **Config 3** or **Config 5** (Two-Platform Shared Git Worktree + Cross-Family Adversarial Review) only when modeled/measured TCVSO improves by >= 15% or prevents high-severity look-ahead/production defects.
- **Status:** `ACCEPTED_VERIFIED`

## DEC-2026-1028-03: Eight-Timestamp Append-Only Bitemporal Store with Tombstone Redaction (Resolves T05, P1-10)
- **Context:** Standard historical state queries filtering only on `valid_from <= cutoff` leak backdated state revisions into historical evaluations. Pure immutability conflicts with GDPR/privacy erasure and license expiration.
- **Decision:** Enforce dual-predicate `valid_from_utc <= cutoff_ts AND ingested_at_utc <= cutoff_ts` over append-only revisions (`revision_num + 1`). Reconcile legal erasure via `tombstone_status IN ('REDACTED_PII', 'LICENSE_EXPIRED')` which clears `metric_value` while retaining `raw_payload_sha256` audit lineage.
- **Status:** `ACCEPTED_VERIFIED`

## DEC-2026-1028-04: Level 1 Deterministic Oracle Overrules Unanimous Model Consensus (Resolves P1-12, T04)
- **Context:** Frontier LLMs share training-corpus biases and can unanimously agree on off-by-one or look-ahead bugs.
- **Decision:** Cross-model agreement is never treated as proof. In the 4-Tier Evidence Hierarchy, Level 1 deterministic execution (unit tests, static typechecks, bitemporal SQL invariants, SHA-256 checksums) unconditionally overrides Level 3 model consensus.
- **Status:** `ACCEPTED_VERIFIED`

## DEC-2026-1028-05: Zero-Dependency Python 3.15 Standard Library Fallback
- **Context:** Host environments (including Windows Python 3.15 workstation images) may run without third-party C-extensions (`duckdb`, `pyyaml`, `pytest`) installed in the global interpreter.
- **Decision:** All core storage, handoff validation, TCVSO calculation, hook enforcement, and test suites (`unittest`) include deterministic Python standard-library implementations (`sqlite3`, `json`, custom YAML parser, `hashlib`, `ast`, `unittest`) so verification succeeds with zero external dependency failures.
- **Status:** `ACCEPTED_VERIFIED`
