---
paths:
  - "src/bitemporal/**"
  - "data/**"
  - "scripts/**"
---

# Bitemporal Point-in-Time (PIT) State & Data Rules (Claude Code Path-Scoped)

1. **Strict Bitemporal Filtering (T05):** Every query or filter against `pit_observations` or `data/pit_store/` MUST enforce `valid_from_utc <= cutoff_ts AND ingested_at_utc <= cutoff_ts` via `pit_as_of(cutoff_ts)`. Filtering on `valid_from_utc` or `event_time_utc` alone is a critical look-ahead defect.
2. **Zero LLM Arithmetic:** Never compute numerical aggregations, statistical metrics, latency/throughput calculations, or deterministic state transitions in prose. Write deterministic Python 3.12+ code (`src/bitemporal/`) and verify with `python -m unittest tests/test_pit_loader.py -v`.
3. **Append-Only Immutability & Lineage (P1-10):** Never mutate raw fixtures in `data/raw/` or overwrite historical rows in `pit_observations`. Revisions must append a new record with `revision_num = revision_num + 1`, `raw_payload_sha256`, and `transform_git_sha`.
4. **Timezone & Entity Identifier Discipline:** Reject naive `datetime` objects (`tzinfo is None`). Always key entities by permanent `entity_id` alongside `label_at_time` to preserve historical cohort completeness across renames or deprecations.
