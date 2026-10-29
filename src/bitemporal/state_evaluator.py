"""Deterministic Point-in-Time State Evaluator & Cross-Sectional Ranking Engine.

Enforces Workload A (Config 5) Governance:
- Zero LLM Arithmetic: all metric aggregations, cross-sectional rankings, and status classifications are
  computed deterministically in Python from `BitemporalPITStore.query_pit_as_of(cutoff_ts)`.
- Historical Cohort Completeness (Survivorship-Bias Prevention): keys cross-sections by permanent
  `entity_id`, preserving deprecated/decommissioned system entities (`LEGACY-NODE-DEPRECATED`) that were
  active as of `cutoff_ts`.
- Cryptographic Provenance: emits a SHA-256 lineage manifest (`EvaluationSignalManifest`) binding
  every generated ranking to the exact `observation_id` and `raw_payload_sha256` inputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from src.bitemporal.pit_loader import BitemporalPITStore, PITObservation, canonical_utc_iso


@dataclass(frozen=True)
class EvaluationRankingRow:
    """Single entity's point-in-time metrics and cross-sectional rank as of `cutoff_ts`."""

    rank: int
    entity_id: str
    label_at_time: str
    unit: str
    event_time_utc: str
    primary_metric: float
    secondary_metric: float | None
    primary_revision_num: int
    composite_score: float
    action_classification: str
    source_observation_ids: tuple[str, ...]
    source_payload_sha256s: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize ranking row to a JSON-compatible dictionary."""
        data = asdict(self)
        data["source_observation_ids"] = list(self.source_observation_ids)
        data["source_payload_sha256s"] = list(self.source_payload_sha256s)
        return data


@dataclass(frozen=True)
class EvaluationSignalManifest:
    """Deterministic PIT cross-sectional state evaluator output and SHA-256 provenance manifest."""

    cutoff_ts_utc: str
    cohort_count: int
    includes_deprecated_entities: bool
    rankings: tuple[EvaluationRankingRow, ...]
    provenance_sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize full state evaluation manifest to a JSON-compatible dictionary."""
        return {
            "cutoff_ts_utc": self.cutoff_ts_utc,
            "cohort_count": self.cohort_count,
            "includes_deprecated_entities": self.includes_deprecated_entities,
            "rankings": [row.to_dict() for row in self.rankings],
            "provenance_sha256": self.provenance_sha256,
        }


class DeterministicStateEvaluator:
    """Deterministic Point-in-Time Cross-Sectional State Evaluator for Workload A."""

    def __init__(self, store: BitemporalPITStore) -> None:
        self.store = store

    def evaluate_cross_section(
        self,
        cutoff_ts: str,
        unit_filter: str | None = "SCORE",
        event_time_utc: str | None = None,
        primary_metric_name: str = "throughput_score",
        secondary_metric_name: str = "capacity_units",
    ) -> EvaluationSignalManifest:
        """Compute a deterministic cross-sectional system state ranking as of `cutoff_ts`.

        1. Queries `BitemporalPITStore.query_pit_as_of(cutoff_ts)` and verifies zero look-ahead leak.
        2. Selects each entity's latest available `primary_metric_name` (`throughput_score`) and
           `secondary_metric_name` (`capacity_units`) observation known at `cutoff_ts`.
        3. Computes a deterministic composite score:
           `composite_score = round(primary_metric * 10.0 + (secondary_metric or 0.0) / 10000.0, 6)`
        4. Ranks entities cross-sectionally and assigns deterministic operational classifications
           (`PRIORITY_SCALE_UP`, `STANDARD_ALLOCATION`, `QUARANTINE_DEGRADED`).
        5. Generates a cryptographic `provenance_sha256` over all input `raw_payload_sha256` hashes and scores.
        """
        cutoff_iso = canonical_utc_iso(cutoff_ts)
        observations = self.store.query_pit_as_of(cutoff_iso, event_time_utc=event_time_utc)

        latest_by_entity_metric: dict[tuple[str, str], PITObservation] = {}
        for obs in observations:
            if unit_filter is not None and obs.unit != unit_filter:
                continue
            key = (obs.entity_id, obs.metric_name)
            existing = latest_by_entity_metric.get(key)
            if existing is None or (obs.event_time_utc, obs.ingested_at_utc) > (
                existing.event_time_utc,
                existing.ingested_at_utc,
            ):
                latest_by_entity_metric[key] = obs

        entity_ids = sorted({entity_id for (entity_id, _) in latest_by_entity_metric})
        unranked_rows: list[dict[str, Any]] = []

        for entity_id in entity_ids:
            primary_obs = latest_by_entity_metric.get((entity_id, primary_metric_name))
            if primary_obs is None or primary_obs.metric_value is None:
                continue
            secondary_obs = latest_by_entity_metric.get((entity_id, secondary_metric_name))
            secondary_val = (
                secondary_obs.metric_value
                if (secondary_obs is not None and secondary_obs.metric_value is not None)
                else None
            )

            primary_val = float(primary_obs.metric_value)
            composite = round((primary_val * 10.0) + ((secondary_val or 0.0) / 10000.0), 6)

            if primary_val < 0.0:
                classification = "QUARANTINE_DEGRADED"
            elif composite >= 20.0:
                classification = "PRIORITY_SCALE_UP"
            else:
                classification = "STANDARD_ALLOCATION"

            obs_ids: list[str] = [primary_obs.observation_id]
            payload_hashes: list[str] = [primary_obs.raw_payload_sha256]
            if secondary_obs is not None:
                obs_ids.append(secondary_obs.observation_id)
                payload_hashes.append(secondary_obs.raw_payload_sha256)

            unranked_rows.append(
                {
                    "entity_id": entity_id,
                    "label_at_time": primary_obs.label_at_time,
                    "unit": primary_obs.unit or "SCORE",
                    "event_time_utc": primary_obs.event_time_utc,
                    "primary_metric": primary_val,
                    "secondary_metric": secondary_val,
                    "primary_revision_num": primary_obs.revision_num,
                    "composite_score": composite,
                    "action_classification": classification,
                    "source_observation_ids": tuple(obs_ids),
                    "source_payload_sha256s": tuple(payload_hashes),
                }
            )

        # Sort descending by composite_score, then ascending by entity_id for 100% deterministic tie-breaking
        unranked_rows.sort(key=lambda r: (-float(r["composite_score"]), str(r["entity_id"])))

        ranked_rows: list[EvaluationRankingRow] = []
        for idx, item in enumerate(unranked_rows, start=1):
            ranked_rows.append(
                EvaluationRankingRow(
                    rank=idx,
                    entity_id=str(item["entity_id"]),
                    label_at_time=str(item["label_at_time"]),
                    unit=str(item["unit"]),
                    event_time_utc=str(item["event_time_utc"]),
                    primary_metric=float(item["primary_metric"]),
                    secondary_metric=float(item["secondary_metric"])
                    if item["secondary_metric"] is not None
                    else None,
                    primary_revision_num=int(item["primary_revision_num"]),
                    composite_score=float(item["composite_score"]),
                    action_classification=str(item["action_classification"]),
                    source_observation_ids=tuple(item["source_observation_ids"]),
                    source_payload_sha256s=tuple(item["source_payload_sha256s"]),
                )
            )

        includes_deprecated = any("DEPRECATED" in row.label_at_time for row in ranked_rows)
        canonical_manifest_payload = json.dumps(
            {
                "cutoff_ts_utc": cutoff_iso,
                "rankings": [r.to_dict() for r in ranked_rows],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        provenance_sha256 = hashlib.sha256(canonical_manifest_payload.encode("utf-8")).hexdigest()

        return EvaluationSignalManifest(
            cutoff_ts_utc=cutoff_iso,
            cohort_count=len(ranked_rows),
            includes_deprecated_entities=includes_deprecated,
            rankings=tuple(ranked_rows),
            provenance_sha256=provenance_sha256,
        )

    @staticmethod
    def compare_revision_impact(
        early_manifest: EvaluationSignalManifest,
        late_manifest: EvaluationSignalManifest,
        label: str = "NODE-ALPHA",
    ) -> dict[str, Any]:
        """Compare an entity's PIT metric and rank between two cutoffs to audit T05 revision progression."""
        early_row = next((r for r in early_manifest.rankings if r.label_at_time == label), None)
        late_row = next((r for r in late_manifest.rankings if r.label_at_time == label), None)
        if early_row is None or late_row is None:
            raise KeyError(f"Label {label!r} not found in both manifests.")

        return {
            "label": label,
            "entity_id": early_row.entity_id,
            "early_cutoff_utc": early_manifest.cutoff_ts_utc,
            "early_primary_metric": early_row.primary_metric,
            "early_revision_num": early_row.primary_revision_num,
            "early_rank": early_row.rank,
            "late_cutoff_utc": late_manifest.cutoff_ts_utc,
            "late_primary_metric": late_row.primary_metric,
            "late_revision_num": late_row.primary_revision_num,
            "late_rank": late_row.rank,
            "metric_delta": round(late_row.primary_metric - early_row.primary_metric, 6),
        }
