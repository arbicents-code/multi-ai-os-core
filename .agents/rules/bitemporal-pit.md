---
trigger: glob
globs: ["src/bitemporal/**", "data/**"]
description: Enforces bitemporal Point-in-Time (PIT) state integrity, 8-timestamp schema rules, and zero LLM arithmetic for analytical data pipelines.
---

# Bitemporal Point-in-Time (PIT) State & Data Rules (Google Antigravity)

1. **Mandatory Bitemporal Predicate (T05):** Any historical query at cutoff `cutoff_ts` against `pit_observations` or `data/pit_store/` MUST enforce `valid_from_utc <= cutoff_ts AND ingested_at_utc <= cutoff_ts AND tombstone_status IN ('ACTIVE', 'CORRECTED')` ordered by `ingested_at_utc DESC, revision_num DESC`.
2. **Zero LLM Arithmetic:** All numerical aggregations, statistical metrics, latency/throughput calculations, and deterministic state transitions must be computed by deterministic Python scripts and verified via `python -m unittest tests/test_pit_loader.py -v`.
3. **Cohort Completeness & Timezone Safety:** Group and join entities by permanent `entity_id` alongside `label_at_time` to preserve historical cohort completeness across renames or deprecations. Require timezone-aware UTC timestamps (`TIMESTAMPTZ`) on all inputs.
4. **Append-Only Store & Tombstone Lineage (P1-10):** Never modify or delete existing rows in `pit_observations` or files in `data/raw/`. Append revisions with `revision_num + 1` and preserve `raw_payload_sha256` on tombstoned records (`REDACTED_PII`, `LICENSE_EXPIRED`).
