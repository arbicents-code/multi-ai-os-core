# Phase 03: Bitemporal State Evaluator, Runtime Concurrency Guard & Domain Logic Implementation

**Phase Classification:** `DOMAIN_LOGIC_IMPLEMENTATION`  
**Target Configuration:** Config 3 (Software Engineering) & Config 5 (High-Integrity Data & Analytics)  
**Authoritative Spec Reference:** `Multi-AI Operating System Programme.md` Sections 4.1, 11, 13, 14.2

---

## 1. Objective

Implement the deterministic state evaluation and runtime concurrency modules (`src/bitemporal/state_evaluator.py`, `src/bitemporal/pit_loader.py`, `src/runtime/`) on top of the Phase 02 bitemporal store, adhering strictly to the **Zero LLM Arithmetic** hard constraint and 100% provenance traceability.

## 2. Hard Engineering Rules

1. **Zero LLM Arithmetic (Workload A Constraint 2):**
   - All numerical aggregations, statistical metrics, latency/throughput calculations, and deterministic state transitions must be computed in deterministic Python/SQL/C# code and verified against held-out unit test oracles.
2. **Historical Cohort Completeness:**
   - Cohort construction at historical cutoff `cutoff_ts` must include entities (`entity_id` + `label_at_time`) that were active at `cutoff_ts` even if subsequently renamed or deprecated prior to the current wall-clock date.
3. **100% Provenance Traceability (Workload A Constraint 3):**
   - Every analytical evaluation batch or runtime verification report must emit a deterministic provenance manifest containing `bitemporal_cutoff_utc`, `dataset_sha256`, `transform_git_sha`, and `execution_timestamp_utc`.
4. **Untrusted Input Quarantine (T06):**
   - External research notes, HTML documents, or MCP payloads ingested during technical synthesis must pass through deterministic prompt-injection sanitization before entering model context.

## 3. Acceptance Gate

- `python -m unittest discover -s tests -v` passes 100% of unit tests in `tests/test_pit_loader.py`.
- Zero unverified edits outside the assigned task worktree branch.
