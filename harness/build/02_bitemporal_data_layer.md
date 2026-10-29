# Phase 02: Eight-Timestamp Bitemporal PIT Data Layer & Immutability Reconciliation

**Phase Classification:** `DATA_ARCHITECTURE_IMPLEMENTATION`  
**Target Configuration:** Config 5 (High-Integrity Data Engineering & Bitemporal State)  
**Authoritative Spec Reference:** `Multi-AI Operating System Programme.md` Sections 12, 13, 16 (T05, P1-10)

---

## 1. Objective

Implement the local content-addressed bitemporal Point-in-Time (PIT) storage engine (`src/bitemporal/pit_loader.py`, `scripts/ingest_pit.py`, and `data/pit_store/`) enforcing the 8-timestamp schema and `pit_as_of(cutoff_ts)` query semantics with zero look-ahead or cohort-omission leakage.

## 2. Mandatory Schema Contract (`pit_observations`)

Every system state observation must record:
- **Identity & Cohort Completeness Protection:** `observation_id` (UUID), `entity_id` (permanent identifier, e.g., `SYS-0001`, never mutable label alone), `label_at_time` (identifier label active on `event_time_utc`, e.g., `NODE-ALPHA`), `metric_name`, `metric_value` (nullable only when tombstoned), `unit`.
- **Eight Bitemporal Timestamps (Strict UTC ISO-8601 / `TIMESTAMPTZ`):**
  1. `event_time_utc`: Sampling interval end timestamp in UTC.
  2. `exchange_tz`: IANA timezone string of originating node (e.g., `Europe/London`, `America/New_York`).
  3. `published_at_utc`: Official upstream emission timestamp.
  4. `first_avail_utc`: Collector ingestion arrival timestamp.
  5. `valid_from_utc`: Start of business validity window.
  6. `valid_to_utc`: End of validity window (`None`/`NULL` if currently active).
  7. `ingested_at_utc`: Immutable system transaction timestamp when written to `pit_store`.
  8. `superseded_at_utc`: System transaction timestamp when a revision arrived.
- **Provenance & P1-10 Reconciliation Fields:** `revision_num` (int >= 1), `source_vendor`, `raw_payload_sha256` (64-hex SHA-256), `transform_git_sha` (40-hex commit SHA), `tombstone_status` (`ACTIVE`, `CORRECTED`, `REDACTED_PII`, `LICENSE_EXPIRED`).

## 3. Deterministic `pit_as_of(cutoff_ts)` Invariant

```sql
SELECT * EXCLUDE (rn)
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY entity_id, metric_name, event_time_utc
               ORDER BY ingested_at_utc DESC, revision_num DESC
           ) AS rn
    FROM pit_observations
    WHERE valid_from_utc <= cutoff_ts
      AND ingested_at_utc <= cutoff_ts
      AND tombstone_status IN ('ACTIVE', 'CORRECTED')
)
WHERE rn = 1;
```

## 4. Acceptance Gate (Gate 1B — Data Layer)

- Naive datetime inputs (missing UTC timezone info) must raise `ValueError`.
- In-place `UPDATE` or `DELETE` on historical observations is forbidden; revisions append `revision_num + 1`.
- GDPR/license erasure (`REDACTED_PII` / `LICENSE_EXPIRED`) purges raw value/payload while preserving cryptographic `raw_payload_sha256` audit lineage.
- Adversarial Test **T05** (revision leak check on `SYS-0001` / `NODE-ALPHA` and `SYS-0002` / `SERVICE-BRAVO`) must pass with 100% numeric accuracy.
