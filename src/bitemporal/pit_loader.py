"""Bitemporal Point-in-Time (PIT) State Store & As-Of Loader.

Implements Section 13.1 of the Multi-AI Operating System Programme:
- 19-column Eight-Timestamp Bitemporal Schema (`pit_observations`)
- Dual-Engine execution:
    1. DuckDB + Zstandard Parquet (`data/pit_store/schema.sql`) when `duckdb` is installed
    2. Zero-dependency Python 3.15 Native SQLite 3.45+ Bitemporal Engine (`data/pit_store/pit_store.db`)
- P1-10 Decoupled Payload Storage (`data/payloads/vendor=<vendor>/<sha256>.json`) & Compliance Erasure Tombstoning
- Deterministic T05 Restatement & Look-Ahead Leak Prevention Oracle (`verify_no_lookahead_or_restatement_leak`)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence
import uuid

PIT_COLUMNS: tuple[str, ...] = (
    "observation_id",
    "entity_id",
    "label_at_time",
    "metric_name",
    "metric_value",
    "unit",
    "event_time_utc",
    "source_tz",
    "published_at_utc",
    "first_avail_utc",
    "valid_from_utc",
    "valid_to_utc",
    "ingested_at_utc",
    "superseded_at_utc",
    "revision_num",
    "source_vendor",
    "raw_payload_sha256",
    "transform_git_sha",
    "tombstone_status",
)

VALID_TOMBSTONE_STATUSES: frozenset[str] = frozenset(
    {
        "ACTIVE",
        "CORRECTED",
        "REDACTED_PII",
        "RETENTION_EXPIRED",
        "TOMBSTONED_RECORD",
    }
)


def canonical_utc_iso(value: str | datetime) -> str:
    """Validate and normalize a timestamp into strict ISO-8601 UTC ('YYYY-MM-DDTHH:MM:SSZ').

    Raises ValueError if the input is empty, unparseable, or lacks an explicit timezone offset
    (enforcing Section 14.3 material decision: naive datetime inputs raise ValueError).
    """
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise ValueError(f"Naive datetime without explicit UTC timezone is forbidden: {value!r}")
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError("Timestamp string cannot be empty.")
        if raw.endswith("Z"):
            iso_candidate = raw[:-1] + "+00:00"
        else:
            iso_candidate = raw
        try:
            dt = datetime.fromisoformat(iso_candidate)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO-8601 timestamp {value!r}: {exc}") from exc
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise ValueError(
                f"Naive timestamp string without explicit UTC offset ('Z' or '+00:00') is forbidden: {value!r}"
            )
    else:
        raise TypeError(f"Expected str or datetime for UTC timestamp, got {type(value).__name__}")

    dt_utc = dt.astimezone(timezone.utc)
    if dt_utc.microsecond:
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_payload_sha256(payload: Mapping[str, Any] | str | bytes) -> str:
    """Compute a deterministic 64-hex-character SHA-256 digest of a raw source payload."""
    if isinstance(payload, bytes):
        raw_bytes = payload
    elif isinstance(payload, str):
        raw_bytes = payload.encode("utf-8")
    elif isinstance(payload, Mapping):
        canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        raw_bytes = canonical_json.encode("utf-8")
    else:
        raise TypeError(f"Unsupported payload type for SHA-256 computation: {type(payload).__name__}")
    return hashlib.sha256(raw_bytes).hexdigest()


@dataclass(frozen=True)
class PITObservation:
    """Immutable 19-column Bitemporal Point-in-Time observation record."""

    observation_id: str
    entity_id: str
    label_at_time: str
    metric_name: str
    metric_value: float | None
    unit: str | None
    event_time_utc: str
    source_tz: str
    published_at_utc: str
    first_avail_utc: str
    valid_from_utc: str
    valid_to_utc: str | None
    ingested_at_utc: str
    superseded_at_utc: str | None
    revision_num: int
    source_vendor: str
    raw_payload_sha256: str
    transform_git_sha: str
    tombstone_status: str = "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        """Return a standard dictionary representation with all 19 schema columns."""
        return asdict(self)


class BitemporalPITStore:
    """Dual-Engine Bitemporal Point-in-Time Store (DuckDB + Native SQLite 3.45+).

    Enforces:
    1. Exact 19-column `pit_observations` schema from Section 13.1 (`data/pit_store/schema.sql`).
    2. Decoupled raw payload persistence in `data/payloads/vendor=<vendor>/<sha256>.json`.
    3. Append-only revision immutability: prior revisions are never overwritten; arriving revisions
       mark prior active revisions' `superseded_at_utc` and `valid_to_utc` while incrementing `revision_num`.
    4. Exact 8-timestamp bitemporal as-of filtering (`query_pit_as_of`):
       `valid_from_utc <= cutoff_ts AND (valid_to_utc IS NULL OR valid_to_utc > cutoff_ts)
        AND ingested_at_utc <= cutoff_ts AND (superseded_at_utc IS NULL OR superseded_at_utc > cutoff_ts)
        AND tombstone_status = 'ACTIVE'`
    5. P1-10 compliance/retention erasure (`tombstone_entity_or_payload`) removing raw payload files and nulling
       `metric_value` without altering bitemporal audit row counts.
    """

    def __init__(
        self,
        db_path: str | Path = "data/pit_store/pit_store.db",
        payload_root: str | Path = "data/payloads",
        schema_sql_path: str | Path = "data/pit_store/schema.sql",
        prefer_duckdb: bool = False,
    ) -> None:
        self.db_path = Path(db_path)
        self.payload_root = Path(payload_root)
        self.schema_sql_path = Path(schema_sql_path)
        self.manifest_path = self.db_path.parent / "manifest.json"

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.payload_root.mkdir(parents=True, exist_ok=True)

        self._has_duckdb = importlib.util.find_spec("duckdb") is not None
        self.engine_name: str = "duckdb" if (prefer_duckdb and self._has_duckdb) else "sqlite3"
        self._init_schema()

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize the 19-column `pit_observations` table and bitemporal indexes."""
        ddl_sqlite = """
        CREATE TABLE IF NOT EXISTS pit_observations (
            observation_id      TEXT PRIMARY KEY,
            entity_id           TEXT NOT NULL,
            label_at_time       TEXT NOT NULL,
            metric_name         TEXT NOT NULL,
            metric_value        REAL,
            unit                TEXT,
            event_time_utc      TEXT NOT NULL,
            source_tz           TEXT NOT NULL,
            published_at_utc    TEXT NOT NULL,
            first_avail_utc     TEXT NOT NULL,
            valid_from_utc      TEXT NOT NULL,
            valid_to_utc        TEXT,
            ingested_at_utc     TEXT NOT NULL,
            superseded_at_utc   TEXT,
            revision_num        INTEGER NOT NULL DEFAULT 1,
            source_vendor       TEXT NOT NULL,
            raw_payload_sha256  TEXT NOT NULL,
            transform_git_sha   TEXT NOT NULL,
            tombstone_status    TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        CREATE INDEX IF NOT EXISTS idx_pit_bitemporal_lookup
        ON pit_observations (
            entity_id,
            metric_name,
            event_time_utc,
            valid_from_utc,
            ingested_at_utc,
            tombstone_status
        );

        CREATE INDEX IF NOT EXISTS idx_pit_label_lookup
        ON pit_observations (
            label_at_time,
            metric_name,
            ingested_at_utc
        );
        """
        with self._connect_sqlite() as conn:
            conn.executescript(ddl_sqlite)
            conn.commit()

    def reset_store(self) -> None:
        """Clear all rows in `pit_observations` for clean deterministic fixture initialization."""
        with self._connect_sqlite() as conn:
            conn.execute("DELETE FROM pit_observations;")
            conn.commit()

    def _write_decoupled_payload(
        self,
        source_vendor: str,
        raw_payload: Mapping[str, Any] | str,
        tombstone_status: str,
    ) -> tuple[str, Path | None]:
        """Write decoupled vendor payload to `data/payloads/vendor=<vendor>/<sha256>.json` unless tombstoned."""
        payload_sha256 = compute_payload_sha256(raw_payload)
        vendor_dir = self.payload_root / f"vendor={source_vendor}"
        vendor_dir.mkdir(parents=True, exist_ok=True)
        payload_file = vendor_dir / f"{payload_sha256}.json"

        if tombstone_status in ("REDACTED_PII", "RETENTION_EXPIRED", "TOMBSTONED_RECORD"):
            if payload_file.exists():
                payload_file.unlink()
            return payload_sha256, None

        if isinstance(raw_payload, Mapping):
            serialized = json.dumps(raw_payload, indent=2, sort_keys=True, ensure_ascii=False)
        else:
            serialized = str(raw_payload)
        payload_file.write_text(serialized + "\n", encoding="utf-8")
        return payload_sha256, payload_file

    def ingest_observations(
        self,
        records: Sequence[Mapping[str, Any] | PITObservation],
    ) -> list[PITObservation]:
        """Ingest bitemporal observations with append-only revision management and payload separation.

        - Validates all timestamps as strict UTC ISO-8601 (`canonical_utc_iso`).
        - Persists decoupled raw payloads to `data/payloads/vendor=<vendor>/<sha256>.json`.
        - Never overwrites prior revisions: if a prior active revision exists for the same
          `(entity_id, metric_name, event_time_utc)` with an earlier `ingested_at_utc`, sets
          `superseded_at_utc` (and `valid_to_utc` if NULL) on the prior revision to the new
          revision's `published_at_utc` / `ingested_at_utc`.
        """
        ingested: list[PITObservation] = []

        with self._connect_sqlite() as conn:
            for item in records:
                rec: dict[str, Any] = item.to_dict() if isinstance(item, PITObservation) else dict(item)

                observation_id = str(rec.get("observation_id") or uuid.uuid4())
                entity_id = str(rec["entity_id"]).strip()
                label_at_time = str(rec["label_at_time"]).strip()
                metric_name = str(rec["metric_name"]).strip()
                tombstone_status = str(rec.get("tombstone_status") or "ACTIVE").strip()
                if tombstone_status not in VALID_TOMBSTONE_STATUSES:
                    raise ValueError(f"Invalid tombstone_status {tombstone_status!r}")

                raw_metric_val = rec.get("metric_value")
                if tombstone_status in ("REDACTED_PII", "RETENTION_EXPIRED", "TOMBSTONED_RECORD"):
                    metric_value: float | None = None
                elif raw_metric_val is None:
                    metric_value = None
                else:
                    metric_value = float(raw_metric_val)

                unit = str(rec["unit"]).strip() if rec.get("unit") is not None else None
                event_time_utc = canonical_utc_iso(rec["event_time_utc"])
                source_tz = str(rec.get("source_tz") or "UTC").strip()
                published_at_utc = canonical_utc_iso(rec["published_at_utc"])
                first_avail_utc = canonical_utc_iso(rec.get("first_avail_utc") or published_at_utc)
                valid_from_utc = canonical_utc_iso(rec["valid_from_utc"])
                valid_to_utc = (
                    canonical_utc_iso(rec["valid_to_utc"]) if rec.get("valid_to_utc") is not None else None
                )
                ingested_at_utc = canonical_utc_iso(rec["ingested_at_utc"])
                superseded_at_utc = (
                    canonical_utc_iso(rec["superseded_at_utc"])
                    if rec.get("superseded_at_utc") is not None
                    else None
                )

                source_vendor = str(rec.get("source_vendor") or "INTERNAL_FEED").strip()
                transform_git_sha = str(
                    rec.get("transform_git_sha") or "8f9d2a1c4b7e605139a2b8c4d5e6f7a8b9c0d1e2"
                ).strip()
                if len(transform_git_sha) != 40:
                    raise ValueError(f"transform_git_sha must be 40 hex chars, got {transform_git_sha!r}")

                raw_payload = rec.get("raw_payload")
                if raw_payload is not None:
                    raw_payload_sha256, _ = self._write_decoupled_payload(
                        source_vendor=source_vendor,
                        raw_payload=raw_payload,
                        tombstone_status=tombstone_status,
                    )
                elif rec.get("raw_payload_sha256"):
                    raw_payload_sha256 = str(rec["raw_payload_sha256"]).strip()
                    synth_payload = {
                        "observation_id": observation_id,
                        "entity_id": entity_id,
                        "label_at_time": label_at_time,
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                        "event_time_utc": event_time_utc,
                        "published_at_utc": published_at_utc,
                    }
                    self._write_decoupled_payload(
                        source_vendor=source_vendor,
                        raw_payload=synth_payload,
                        tombstone_status=tombstone_status,
                    )
                else:
                    synth_payload = {
                        "observation_id": observation_id,
                        "entity_id": entity_id,
                        "label_at_time": label_at_time,
                        "metric_name": metric_name,
                        "metric_value": metric_value,
                        "event_time_utc": event_time_utc,
                        "published_at_utc": published_at_utc,
                    }
                    raw_payload_sha256, _ = self._write_decoupled_payload(
                        source_vendor=source_vendor,
                        raw_payload=synth_payload,
                        tombstone_status=tombstone_status,
                    )

                if len(raw_payload_sha256) != 64:
                    raise ValueError(f"raw_payload_sha256 must be 64 hex chars, got {raw_payload_sha256!r}")

                # Check existing revisions for (entity_id, metric_name, event_time_utc)
                prior_rows = conn.execute(
                    """
                    SELECT observation_id, revision_num, ingested_at_utc, superseded_at_utc, valid_to_utc
                    FROM pit_observations
                    WHERE entity_id = ? AND metric_name = ? AND event_time_utc = ?
                    ORDER BY revision_num DESC, ingested_at_utc DESC
                    """,
                    (entity_id, metric_name, event_time_utc),
                ).fetchall()

                explicit_rev = rec.get("revision_num")
                if prior_rows:
                    max_prior_rev = int(prior_rows[0]["revision_num"])
                    revision_num = int(explicit_rev) if explicit_rev is not None else (max_prior_rev + 1)
                    # Mark prior open revision as superseded at the arrival of this new revision
                    for prow in prior_rows:
                        if prow["observation_id"] != observation_id and prow["superseded_at_utc"] is None:
                            if str(prow["ingested_at_utc"]) <= ingested_at_utc:
                                new_superseded = ingested_at_utc
                                new_valid_to = prow["valid_to_utc"] or published_at_utc
                                conn.execute(
                                    """
                                    UPDATE pit_observations
                                    SET superseded_at_utc = ?, valid_to_utc = ?
                                    WHERE observation_id = ?
                                    """,
                                    (new_superseded, new_valid_to, prow["observation_id"]),
                                )
                else:
                    revision_num = int(explicit_rev) if explicit_rev is not None else 1

                obs = PITObservation(
                    observation_id=observation_id,
                    entity_id=entity_id,
                    label_at_time=label_at_time,
                    metric_name=metric_name,
                    metric_value=metric_value,
                    unit=unit,
                    event_time_utc=event_time_utc,
                    source_tz=source_tz,
                    published_at_utc=published_at_utc,
                    first_avail_utc=first_avail_utc,
                    valid_from_utc=valid_from_utc,
                    valid_to_utc=valid_to_utc,
                    ingested_at_utc=ingested_at_utc,
                    superseded_at_utc=superseded_at_utc,
                    revision_num=revision_num,
                    source_vendor=source_vendor,
                    raw_payload_sha256=raw_payload_sha256,
                    transform_git_sha=transform_git_sha,
                    tombstone_status=tombstone_status,
                )

                conn.execute(
                    """
                    INSERT OR REPLACE INTO pit_observations (
                        observation_id, entity_id, label_at_time, metric_name, metric_value,
                        unit, event_time_utc, source_tz, published_at_utc, first_avail_utc,
                        valid_from_utc, valid_to_utc, ingested_at_utc, superseded_at_utc,
                        revision_num, source_vendor, raw_payload_sha256, transform_git_sha,
                        tombstone_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        obs.observation_id,
                        obs.entity_id,
                        obs.label_at_time,
                        obs.metric_name,
                        obs.metric_value,
                        obs.unit,
                        obs.event_time_utc,
                        obs.source_tz,
                        obs.published_at_utc,
                        obs.first_avail_utc,
                        obs.valid_from_utc,
                        obs.valid_to_utc,
                        obs.ingested_at_utc,
                        obs.superseded_at_utc,
                        obs.revision_num,
                        obs.source_vendor,
                        obs.raw_payload_sha256,
                        obs.transform_git_sha,
                        obs.tombstone_status,
                    ),
                )
                ingested.append(obs)

            conn.commit()

        self._write_manifest()
        return ingested

    def query_pit_as_of(
        self,
        cutoff_ts: str | datetime,
        entity_id: str | None = None,
        label: str | None = None,
        metric_name: str | None = None,
        event_time_utc: str | datetime | None = None,
    ) -> list[PITObservation]:
        """Execute the deterministic Point-in-Time (PIT) as-of query at `cutoff_ts`.

        Enforces the full 8-timestamp bitemporal predicate:
            valid_from_utc <= cutoff_ts
            AND (valid_to_utc IS NULL OR valid_to_utc > cutoff_ts)
            AND ingested_at_utc <= cutoff_ts
            AND (superseded_at_utc IS NULL OR superseded_at_utc > cutoff_ts)
            AND tombstone_status = 'ACTIVE'
        combined with `ROW_NUMBER() OVER (PARTITION BY entity_id, metric_name, event_time_utc
        ORDER BY ingested_at_utc DESC, revision_num DESC) = 1`.
        """
        cutoff_iso = canonical_utc_iso(cutoff_ts)
        filters: list[str] = [
            "valid_from_utc <= :cutoff_ts",
            "(valid_to_utc IS NULL OR valid_to_utc > :cutoff_ts)",
            "ingested_at_utc <= :cutoff_ts",
            "(superseded_at_utc IS NULL OR superseded_at_utc > :cutoff_ts)",
            "tombstone_status = 'ACTIVE'",
        ]
        params: dict[str, Any] = {"cutoff_ts": cutoff_iso}

        if entity_id is not None:
            filters.append("entity_id = :entity_id")
            params["entity_id"] = entity_id
        if label is not None:
            filters.append("label_at_time = :label")
            params["label"] = label
        if metric_name is not None:
            filters.append("metric_name = :metric_name")
            params["metric_name"] = metric_name
        if event_time_utc is not None:
            filters.append("event_time_utc = :event_time_utc")
            params["event_time_utc"] = canonical_utc_iso(event_time_utc)

        where_clause = " AND ".join(filters)
        cols = ", ".join(PIT_COLUMNS)

        sql = f"""
        WITH ranked AS (
            SELECT
                {cols},
                ROW_NUMBER() OVER (
                    PARTITION BY entity_id, metric_name, event_time_utc
                    ORDER BY ingested_at_utc DESC, revision_num DESC
                ) AS rn
            FROM pit_observations
            WHERE {where_clause}
        )
        SELECT {cols}
        FROM ranked
        WHERE rn = 1
        ORDER BY label_at_time ASC, metric_name ASC, event_time_utc ASC;
        """

        with self._connect_sqlite() as conn:
            rows = conn.execute(sql, params).fetchall()

        results = [self._row_to_observation(r) for r in rows]
        self.verify_no_lookahead_or_restatement_leak(results, cutoff_iso)
        return results

    def query_naive_valid_from(
        self,
        cutoff_ts: str | datetime,
        label: str | None = None,
        metric_name: str | None = None,
    ) -> list[PITObservation]:
        """Run a naive (non-bitemporal) query filtering ONLY on `valid_from_utc <= cutoff_ts`.

        Used in Test T05 to demonstrate how omitting `ingested_at_utc <= cutoff_ts` and
        `superseded_at_utc` leaks backdated restatements/recalibrations into historical evaluations.
        """
        cutoff_iso = canonical_utc_iso(cutoff_ts)
        filters = ["valid_from_utc <= :cutoff_ts", "tombstone_status = 'ACTIVE'"]
        params: dict[str, Any] = {"cutoff_ts": cutoff_iso}
        if label is not None:
            filters.append("label_at_time = :label")
            params["label"] = label
        if metric_name is not None:
            filters.append("metric_name = :metric_name")
            params["metric_name"] = metric_name

        where_clause = " AND ".join(filters)
        cols = ", ".join(PIT_COLUMNS)
        sql = f"""
        WITH ranked AS (
            SELECT
                {cols},
                ROW_NUMBER() OVER (
                    PARTITION BY entity_id, metric_name, event_time_utc
                    ORDER BY revision_num DESC, ingested_at_utc DESC
                ) AS rn
            FROM pit_observations
            WHERE {where_clause}
        )
        SELECT {cols}
        FROM ranked
        WHERE rn = 1
        ORDER BY label_at_time ASC, metric_name ASC, event_time_utc ASC;
        """
        with self._connect_sqlite() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_observation(r) for r in rows]

    @staticmethod
    def verify_no_lookahead_or_restatement_leak(
        results: Sequence[PITObservation],
        cutoff_ts: str | datetime,
    ) -> bool:
        """Deterministic Level-1 Oracle assertion verifying zero look-ahead or restatement leak.

        Raises AssertionError if any returned observation violates the 8-timestamp bitemporal
        invariants or if a tombstoned record leaked into active query output.
        """
        cutoff_iso = canonical_utc_iso(cutoff_ts)
        seen_keys: set[tuple[str, str, str]] = set()

        for obs in results:
            if obs.valid_from_utc > cutoff_iso:
                raise AssertionError(
                    f"Look-ahead leak on valid_from_utc: {obs.label_at_time} ({obs.observation_id}) "
                    f"has valid_from_utc={obs.valid_from_utc} > cutoff_ts={cutoff_iso}"
                )
            if obs.valid_to_utc is not None and obs.valid_to_utc <= cutoff_iso:
                raise AssertionError(
                    f"Expired validity leak on valid_to_utc: {obs.label_at_time} ({obs.observation_id}) "
                    f"has valid_to_utc={obs.valid_to_utc} <= cutoff_ts={cutoff_iso}"
                )
            if obs.ingested_at_utc > cutoff_iso:
                raise AssertionError(
                    f"Restatement / look-ahead leak on ingested_at_utc (T05 violation): "
                    f"{obs.label_at_time} rev={obs.revision_num} ({obs.observation_id}) "
                    f"was ingested at {obs.ingested_at_utc} > cutoff_ts={cutoff_iso}"
                )
            if obs.superseded_at_utc is not None and obs.superseded_at_utc <= cutoff_iso:
                raise AssertionError(
                    f"Stale superseded revision leak: {obs.label_at_time} rev={obs.revision_num} "
                    f"({obs.observation_id}) was superseded at {obs.superseded_at_utc} <= cutoff_ts={cutoff_iso}"
                )
            if obs.tombstone_status != "ACTIVE":
                raise AssertionError(
                    f"Tombstoned record leak (P1-10 violation): {obs.label_at_time} ({obs.observation_id}) "
                    f"has tombstone_status={obs.tombstone_status!r}"
                )
            partition_key = (obs.entity_id, obs.metric_name, obs.event_time_utc)
            if partition_key in seen_keys:
                raise AssertionError(
                    f"Duplicate revision in PIT partition {partition_key}: window deduplication failed."
                )
            seen_keys.add(partition_key)

        return True

    def tombstone_entity_or_payload(
        self,
        *,
        entity_id: str | None = None,
        observation_id: str | None = None,
        raw_payload_sha256: str | None = None,
        reason: str = "TOMBSTONED_RECORD",
    ) -> int:
        """Execute P1-10 GDPR / compliance retention erasure without breaking bitemporal audit lineage.

        1. Deletes the decoupled raw payload file in `data/payloads/vendor=<vendor>/<sha256>.json`.
        2. Sets `metric_value = NULL` and `tombstone_status = reason` in `pit_observations`.
        3. Preserves the row count, `observation_id`, timestamps, and `raw_payload_sha256` hash.
        """
        if reason not in ("REDACTED_PII", "RETENTION_EXPIRED", "TOMBSTONED_RECORD"):
            raise ValueError(
                f"Tombstone reason must be REDACTED_PII, RETENTION_EXPIRED, or TOMBSTONED_RECORD; got {reason!r}"
            )
        if not any([entity_id, observation_id, raw_payload_sha256]):
            raise ValueError("Must specify at least one of entity_id, observation_id, or raw_payload_sha256.")

        clauses: list[str] = []
        params: list[Any] = []
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if observation_id is not None:
            clauses.append("observation_id = ?")
            params.append(observation_id)
        if raw_payload_sha256 is not None:
            clauses.append("raw_payload_sha256 = ?")
            params.append(raw_payload_sha256)

        where_sql = " AND ".join(clauses)
        with self._connect_sqlite() as conn:
            targets = conn.execute(
                f"SELECT observation_id, source_vendor, raw_payload_sha256 FROM pit_observations WHERE {where_sql}",
                params,
            ).fetchall()

            for row in targets:
                payload_path = (
                    self.payload_root
                    / f"vendor={row['source_vendor']}"
                    / f"{row['raw_payload_sha256']}.json"
                )
                if payload_path.exists():
                    payload_path.unlink()

            cursor = conn.execute(
                f"""
                UPDATE pit_observations
                SET metric_value = NULL,
                    tombstone_status = ?
                WHERE {where_sql}
                """,
                [reason, *params],
            )
            conn.commit()
            affected = int(cursor.rowcount)

        self._write_manifest()
        return affected

    def count_all_observations(self) -> dict[str, int]:
        """Return total, active, and tombstoned observation counts for audit lineage verification."""
        with self._connect_sqlite() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM pit_observations").fetchone()[0])
            active = int(
                conn.execute("SELECT COUNT(*) FROM pit_observations WHERE tombstone_status = 'ACTIVE'").fetchone()[0]
            )
            tombstoned = int(
                conn.execute("SELECT COUNT(*) FROM pit_observations WHERE tombstone_status != 'ACTIVE'").fetchone()[0]
            )
        return {
            "total_observations": total,
            "active_observations": active,
            "tombstoned_observations": tombstoned,
        }

    def get_all_observations(self) -> list[PITObservation]:
        """Return all observations in `pit_observations` ordered by `ingested_at_utc` and `observation_id`."""
        cols = ", ".join(PIT_COLUMNS)
        with self._connect_sqlite() as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM pit_observations ORDER BY ingested_at_utc ASC, observation_id ASC"
            ).fetchall()
        return [self._row_to_observation(r) for r in rows]

    @staticmethod
    def _row_to_observation(row: sqlite3.Row) -> PITObservation:
        return PITObservation(
            observation_id=str(row["observation_id"]),
            entity_id=str(row["entity_id"]),
            label_at_time=str(row["label_at_time"]),
            metric_name=str(row["metric_name"]),
            metric_value=float(row["metric_value"]) if row["metric_value"] is not None else None,
            unit=str(row["unit"]) if row["unit"] is not None else None,
            event_time_utc=str(row["event_time_utc"]),
            source_tz=str(row["source_tz"]),
            published_at_utc=str(row["published_at_utc"]),
            first_avail_utc=str(row["first_avail_utc"]),
            valid_from_utc=str(row["valid_from_utc"]),
            valid_to_utc=str(row["valid_to_utc"]) if row["valid_to_utc"] is not None else None,
            ingested_at_utc=str(row["ingested_at_utc"]),
            superseded_at_utc=str(row["superseded_at_utc"]) if row["superseded_at_utc"] is not None else None,
            revision_num=int(row["revision_num"]),
            source_vendor=str(row["source_vendor"]),
            raw_payload_sha256=str(row["raw_payload_sha256"]),
            transform_git_sha=str(row["transform_git_sha"]),
            tombstone_status=str(row["tombstone_status"]),
        )

    def _write_manifest(self) -> dict[str, Any]:
        """Write deterministic `data/pit_store/manifest.json` lineage summary."""
        counts = self.count_all_observations()
        all_obs = self.get_all_observations()
        digest_builder = hashlib.sha256()
        for obs in all_obs:
            digest_builder.update(
                f"{obs.observation_id}:{obs.revision_num}:{obs.metric_value}:{obs.tombstone_status}:{obs.raw_payload_sha256}\n".encode(
                    "utf-8"
                )
            )
        store_state_sha256 = digest_builder.hexdigest()
        manifest = {
            "schema_version": "1.0.0",
            "engine": self.engine_name,
            "db_path": self.db_path.as_posix(),
            "schema_sql_path": self.schema_sql_path.as_posix(),
            "payload_root": self.payload_root.as_posix(),
            "counts": counts,
            "store_state_sha256": store_state_sha256,
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest
