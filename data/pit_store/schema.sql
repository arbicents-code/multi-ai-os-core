-- =============================================================================
-- Multi-AI Operating System — Workload A: High-Integrity Data & Quantitative Analytics
-- Section 13.1: The Eight-Timestamp Bitemporal Schema (DuckDB + Parquet / SQLite)
-- Resolves Red-Team Findings T05 (Historical Integrity / PIT Restatement Leak)
-- and P1-10 (Immutability vs. Compliance / Retention Payload Erasure).
-- =============================================================================

CREATE TABLE IF NOT EXISTS pit_observations (
    observation_id      UUID PRIMARY KEY,
    entity_id           VARCHAR NOT NULL,          -- Permanent system entity_id (never mutable label alone, preventing cohort survivorship bias)
    label_at_time       VARCHAR NOT NULL,          -- Human-readable label active on event_time (e.g., 'NODE-ALPHA', 'SERVICE-BRAVO')
    metric_name         VARCHAR NOT NULL,          -- e.g., 'throughput_score', 'capacity_units', 'reliability_index'
    metric_value        DOUBLE,                    -- Nullable if redacted/tombstoned under P1-10
    unit                VARCHAR(16),               -- Measurement unit or category (e.g., 'SCORE', 'OPS_SEC', 'RATIO')
    -- Chronological & Bitemporal Timestamps (All stored in strict UTC TIMESTAMPTZ / ISO-8601 UTC)
    event_time_utc      TIMESTAMPTZ NOT NULL,      -- Observation window end (e.g., 2026-03-31T23:59:59Z)
    source_tz           VARCHAR(32) NOT NULL,      -- IANA timezone (e.g., 'America/New_York', 'Europe/London') for DST-safe local reconstruction
    published_at_utc    TIMESTAMPTZ NOT NULL,      -- Official upstream telemetry publication timestamp
    first_avail_utc     TIMESTAMPTZ NOT NULL,      -- Collector arrival timestamp
    valid_from_utc      TIMESTAMPTZ NOT NULL,      -- Start of domain validity window
    valid_to_utc        TIMESTAMPTZ,               -- NULL if currently valid; set when superseded
    ingested_at_utc     TIMESTAMPTZ NOT NULL,      -- Immutable system transaction timestamp when written to pit_store
    superseded_at_utc   TIMESTAMPTZ,               -- System transaction timestamp when a revision/recalibration arrived
    revision_num        INTEGER NOT NULL DEFAULT 1,
    -- Provenance & P1-10 Immutability-Retention Reconciliation Fields
    source_vendor       VARCHAR NOT NULL,
    raw_payload_sha256  CHAR(64) NOT NULL,         -- SHA-256 of decoupled raw source payload in data/payloads/vendor=<v>/<sha256>.json
    transform_git_sha   CHAR(40) NOT NULL,         -- Git commit SHA of ingestion pipeline
    tombstone_status    VARCHAR(24) DEFAULT 'ACTIVE' -- 'ACTIVE', 'CORRECTED', 'REDACTED_PII', 'RETENTION_EXPIRED', 'TOMBSTONED_RECORD'
);

-- Deterministic Point-in-Time (PIT) As-Of Query Macro (DuckDB syntax):
-- Reconstructs the exact state known at any historical cutoff timestamp `cutoff_ts`
-- while enforcing the full bitemporal window and excluding tombstoned records.
CREATE OR REPLACE MACRO pit_as_of(cutoff_ts) AS TABLE
SELECT * EXCLUDE (rn)
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY entity_id, metric_name, event_time_utc
               ORDER BY ingested_at_utc DESC, revision_num DESC
           ) AS rn
    FROM pit_observations
    WHERE valid_from_utc <= cutoff_ts
      AND (valid_to_utc IS NULL OR valid_to_utc > cutoff_ts)
      AND ingested_at_utc <= cutoff_ts
      AND (superseded_at_utc IS NULL OR superseded_at_utc > cutoff_ts)
      AND tombstone_status = 'ACTIVE'
)
WHERE rn = 1;

-- =============================================================================
-- P1-10 Decoupled Payload Erasure & Zstandard Parquet Export Reference:
-- 1. Raw source payloads are stored outside pit_observations at:
--    data/payloads/vendor=<source_vendor>/<raw_payload_sha256>.json
-- 2. Upon GDPR right-to-erasure or data retention expiration:
--    - Delete the decoupled payload file in data/payloads/vendor=<v>/
--    - Update pit_observations SET metric_value = NULL,
--      tombstone_status = 'RETENTION_EXPIRED' (or 'REDACTED_PII')
--    This satisfies legal erasure while preserving cryptographic lineage counts.
-- 3. DuckDB Zstandard Parquet archival command:
--    COPY pit_observations TO 'data/pit_store/pit_observations.parquet'
--    (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 9);
-- =============================================================================
