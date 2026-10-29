---
name: pit-data-validator
description: Validates bitemporal Point-in-Time (PIT) state datasets, enforces the 8-timestamp schema and pit_as_of(cutoff_ts) query macro, audits revision isolation (Test T05), and prevents look-ahead or cohort-omission bias in Workload A analytical pipelines.
---

# Point-in-Time (PIT) Bitemporal State Validator Skill

Use this skill whenever creating, modifying, or auditing bitemporal analytical pipelines (`src/bitemporal/`), DuckDB/SQLite/Parquet queries (`data/pit_store/`), ingestion scripts (`scripts/ingest_pit.py`), or .NET 8 C# runtime state guards (`src/runtime/`).

## 1. Mandatory Eight-Timestamp Bitemporal Invariants

Every observation in `pit_observations` must carry:
1. `event_time_utc` (`TIMESTAMPTZ` — sampling interval end in UTC)
2. `exchange_tz` (`VARCHAR` — IANA timezone of the originating system, e.g., `'Europe/London'`)
3. `published_at_utc` (`TIMESTAMPTZ` — official upstream emission timestamp)
4. `first_avail_utc` (`TIMESTAMPTZ` — collector ingestion arrival timestamp)
5. `valid_from_utc` (`TIMESTAMPTZ` — start of business validity window)
6. `valid_to_utc` (`TIMESTAMPTZ` — nullable end of business validity window)
7. `ingested_at_utc` (`TIMESTAMPTZ` — immutable system transaction timestamp written to `pit_store`)
8. `superseded_at_utc` (`TIMESTAMPTZ` — nullable system transaction timestamp when superseded)

## 2. Step-by-Step Validation Procedure

1. **Check Dual-Predicate As-Of Filtering (`pit_as_of(cutoff_ts)`):**
   - Inspect every SQL query or Python filter touching `pit_observations`.
   - Reject any query that filters solely on `valid_from_utc <= cutoff_ts` or `event_time_utc <= cutoff_ts`.
   - Verify the query enforces BOTH:
     ```sql
     valid_from_utc <= cutoff_ts
     AND ingested_at_utc <= cutoff_ts
     AND tombstone_status IN ('ACTIVE', 'CORRECTED')
     ```
   - Verify deduplication partitions by `(entity_id, metric_name, event_time_utc)` ordered by `ingested_at_utc DESC, revision_num DESC` and selects `rn = 1`.

2. **Check Historical Cohort Completeness:**
   - Ensure joins and groupings key on permanent `entity_id` (e.g., `SYS-0001`), alongside `label_at_time` (e.g., `NODE-ALPHA`), never on mutable labels alone.

3. **Check Timezone Strictness:**
   - Confirm all cutoff timestamps passed into `pit_loader.py` or DuckDB/SQLite macros are timezone-aware UTC (`Z` or `+00:00`). Naive `datetime` objects must raise `ValueError`.

4. **Check Immutability & Erasure Reconciliation (P1-10):**
   - Confirm revisions append a new row with `revision_num + 1` rather than executing `UPDATE` or `DELETE`.
   - Confirm `REDACTED_PII` and `LICENSE_EXPIRED` rows retain `raw_payload_sha256` and `transform_git_sha` while setting `metric_value = NULL`.

5. **Execute Deterministic Test T05 Oracle:**
   - Run the deterministic revision leak test suite:
     ```powershell
     python -m unittest tests/test_pit_loader.py -v
     ```
   - Verify that querying `SYS-0001` (`NODE-ALPHA`) state metric for `2026-03-31` as of `2026-06-01T12:00:00Z` returns Revision 1 (`0.12`) and never leaks Revision 2 (`0.08`, ingested `2026-08-10T08:00:00Z`).
