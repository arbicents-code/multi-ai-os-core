# Cross-Module Interface Contracts (`harness/context/INTERFACE_CONTRACTS.md`)

**Status:** Authoritative Interface Specification (Materiality-Filtered Context Record)  
**Schema Version:** `1.0.0`  
**Last Verified:** `2026-10-29T01:50:00Z`

---

## 1. Bitemporal PIT Storage Contract (`src/bitemporal/pit_loader.py`)

### `BitemporalPITStore`
- **Constructor:** `BitemporalPITStore(db_path: str | Path | None = None)`
- **Core Methods:**
  - `ingest_observation(obs: dict[str, Any]) -> str`: Validates all 8 bitemporal UTC timestamps (rejecting naive timestamps or missing UTC designators with `ValueError`), verifies SHA-256 provenance fields (`raw_payload_sha256`, `transform_git_sha`), and appends an immutable revision row. Never mutates existing rows in place.
  - `query_pit_as_of(cutoff_utc: str | datetime, entity_id: str | None = None, metric_name: str | None = None) -> list[dict[str, Any]]`: Reconstructs exact historical knowledge satisfying `valid_from_utc <= cutoff_utc` AND `ingested_at_utc <= cutoff_utc` AND `tombstone_status IN ('ACTIVE', 'CORRECTED')`, selecting the latest revision (`ORDER BY ingested_at_utc DESC, revision_num DESC`) per `(entity_id, metric_name, event_time_utc)`.
  - `apply_tombstone(entity_id: str, event_time_utc: str, metric_name: str, status: str, reason: str = "") -> int`: Enforces P1-10 lawful erasure (`REDACTED_PII` or `LICENSE_EXPIRED`) by redacting `metric_value = None` in a new tombstone state while preserving cryptographic `raw_payload_sha256` lineage.

---

## 2. Deterministic State Evaluator Contract (`src/bitemporal/state_evaluator.py` & `src/bitemporal/pit_loader.py`)

- **Core Functions / Classes:**
  - `evaluate_entities_as_of(store: BitemporalPITStore, cutoff_utc: str, min_value: float | None = None) -> dict[str, Any]`
  - Returns deterministic ranked results alongside a provenance dictionary containing:
    - `bitemporal_cutoff_utc`
    - `dataset_sha256`
    - `record_count`
    - `results` (sorted deterministically)

---

## 3. Handoff, Worktree & TCVSO Contracts (`scripts/`)

### 3.1 `scripts/validate_handoff.py`
- Validates both Section 14.2 (`tasks/*.yaml`) and Section 14.3 (`handoffs/*.json`) schemas, supporting both canonical Section 14 field names and flat alias fields for cross-agent compatibility.
- Computes live `hashlib.sha256` digests for every path in `modified_files` and supports `--sync-hashes` to deterministically stamp current file hashes into a handoff manifest.
- Enforces the 4-Tier Evidence Hierarchy Oracle (`adjudicate_dispute()`): Level 1 (Deterministic Test/PIT Oracle) > Level 2 (Primary Source) > Level 3 (Cross-Family Adversarial Falsification) > Level 4 (Human Arbitration).

### 3.2 `scripts/worktree_manager.py`
- Manages worktree metadata (`worktrees/<task-id>/`), validates working-tree cleanliness, and enforces optimistic concurrency control (`verify_concurrent_update()`):
  - Rejects any concurrent agent write where `incoming_state_version <= current_state_version` or `base_git_head_sha != current_git_head_sha` when overlapping files or AST nodes are modified (**T03**).

### 3.3 `scripts/tcvso_calculator.py`
- Computes exact Section 4.2 TCVSO:
  $$\text{TCVSO} = \frac{\sum_{i=1}^{N_{\text{total}}} (C_{\text{platform},i} + C_{\text{waste},i} + C_{\text{human},i}) + C_{\text{setup\_amortised}}}{N_{\text{verified}}}$$
- Returns `None` (`"Undefined"`) when $N_{\text{verified}} == 0$.
- Enforces **T01** (Single-Agent Challenge), **T08** (Cost Escalation Circuit Breaker: `max_session_spend_gbp`, `max_consecutive_failed_tests`, `max_context_resends`), and **T12** (Minimum-Complexity Routing Challenge: multi-platform requires >= 15% TCVSO reduction or critical defect prevention).
