#!/usr/bin/env python3
"""Deterministic Bitemporal PIT Store Ingestion & Pilot Verification Script.

Initializes `data/pit_store/pit_store.db`, `data/pit_store/manifest.json`, and
`data/payloads/vendor=<vendor>/<sha256>.json` from `data/samples/pit_fixtures.json`,
executes the Phase 2 Mandatory Working Pilot queries (`TASK-2026-1028-01`), and
asserts all T05 (Historical Integrity / Restatement Leak) and P1-10 (Tombstone Erasure)
invariants.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.bitemporal.pit_loader import BitemporalPITStore
from src.bitemporal.state_evaluator import DeterministicStateEvaluator


def run_pilot_ingestion_and_verification(
    fixtures_path: Path = REPO_ROOT / "data" / "samples" / "pit_fixtures.json",
    db_path: Path = REPO_ROOT / "data" / "pit_store" / "pit_store.db",
    payload_root: Path = REPO_ROOT / "data" / "payloads",
    schema_sql_path: Path = REPO_ROOT / "data" / "pit_store" / "schema.sql",
) -> dict[str, object]:
    """Ingest `pit_fixtures.json` and run deterministic T05 and P1-10 verification checks."""
    raw_fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    observations_data = raw_fixtures["observations"]

    store = BitemporalPITStore(
        db_path=db_path,
        payload_root=payload_root,
        schema_sql_path=schema_sql_path,
    )
    store.reset_store()
    store.ingest_observations(observations_data)
    counts = store.count_all_observations()

    # 1. Pilot Query 1: Cutoff = 2026-05-15T00:00:00Z (Pre-Recalibration & Pre-Q2 Cutoff)
    cutoff_may = "2026-05-15T00:00:00Z"
    alpha_may = store.query_pit_as_of(
        cutoff_ts=cutoff_may,
        label="NODE-ALPHA",
        metric_name="throughput_score",
    )
    if len(alpha_may) != 1:
        raise AssertionError(f"Expected exactly 1 NODE-ALPHA throughput_score row at {cutoff_may}, got {len(alpha_may)}")
    if alpha_may[0].metric_value != 1.00 or alpha_may[0].revision_num != 1:
        raise AssertionError(
            f"T05 Failure at {cutoff_may}: expected NODE-ALPHA throughput_score=1.00 (rev 1), "
            f"got {alpha_may[0].metric_value} (rev {alpha_may[0].revision_num})"
        )

    # Contrast with naive valid_from query at 2026-05-15T00:00:00Z (demonstrating retroactive revision leak)
    alpha_naive_may = store.query_naive_valid_from(
        cutoff_ts=cutoff_may,
        label="NODE-ALPHA",
        metric_name="throughput_score",
    )
    naive_q1_alpha = [r for r in alpha_naive_may if r.event_time_utc == "2026-03-31T23:59:59Z"]
    if not naive_q1_alpha or naive_q1_alpha[0].metric_value != 1.50:
        raise AssertionError("Expected naive valid_from query to demonstrate the 1.50 retroactive revision leak.")

    # 2. Section 16 T05 Reference Check on SERVICE-BRAVO at 2026-06-01T12:00:00Z
    cutoff_june = "2026-06-01T12:00:00Z"
    bravo_june = store.query_pit_as_of(
        cutoff_ts=cutoff_june,
        label="SERVICE-BRAVO",
        metric_name="reliability_index",
    )
    if len(bravo_june) != 1 or bravo_june[0].metric_value != 0.12 or bravo_june[0].revision_num != 1:
        raise AssertionError(
            f"T05 SERVICE-BRAVO Failure at {cutoff_june}: expected 0.12 (rev 1), got {bravo_june}"
        )

    # 3. Pilot Query 2: Cutoff = 2026-09-01T00:00:00Z (Post-Recalibration & Post-Q2 Cutoff)
    cutoff_sep = "2026-09-01T00:00:00Z"
    alpha_sep_q1 = store.query_pit_as_of(
        cutoff_ts=cutoff_sep,
        label="NODE-ALPHA",
        metric_name="throughput_score",
        event_time_utc="2026-03-31T23:59:59Z",
    )
    if len(alpha_sep_q1) != 1 or alpha_sep_q1[0].metric_value != 1.50 or alpha_sep_q1[0].revision_num != 2:
        raise AssertionError(
            f"T05 Failure at {cutoff_sep}: expected NODE-ALPHA Q1 throughput_score=1.50 (rev 2), got {alpha_sep_q1}"
        )

    alpha_sep_all = store.query_pit_as_of(
        cutoff_ts=cutoff_sep,
        label="NODE-ALPHA",
        metric_name="throughput_score",
    )
    if len(alpha_sep_all) != 2:
        raise AssertionError(
            f"Expected 2 NODE-ALPHA throughput_score periods (Q1 revised + Q2 initial) at {cutoff_sep}, got {len(alpha_sep_all)}"
        )

    # 4. Verify Historical Cohort Completeness (Survivorship Bias Prevention) & P1-10 Tombstone Exclusion
    all_may = store.query_pit_as_of(cutoff_ts=cutoff_may)
    may_labels = sorted({obs.label_at_time for obs in all_may})
    if "LEGACY-NODE-DEPRECATED" not in may_labels:
        raise AssertionError(
            "Cohort completeness check failed: LEGACY-NODE-DEPRECATED missing from May 2026 PIT cross-section."
        )
    if "TOMBSTONED_RECORD" in may_labels:
        raise AssertionError("P1-10 check failed: TOMBSTONED_RECORD leaked into active PIT query.")

    # 5. Run Deterministic State Evaluator (Q1 2026 period comparison across May vs Sep cutoffs)
    evaluator = DeterministicStateEvaluator(store)
    eval_may = evaluator.evaluate_cross_section(
        cutoff_may,
        unit_filter="SCORE",
        event_time_utc="2026-03-31T23:59:59Z",
    )
    eval_sep = evaluator.evaluate_cross_section(
        cutoff_sep,
        unit_filter="SCORE",
        event_time_utc="2026-03-31T23:59:59Z",
    )
    revision_impact = evaluator.compare_revision_impact(eval_may, eval_sep, label="NODE-ALPHA")

    summary = {
        "status": "VERIFIED_PASS",
        "engine": store.engine_name,
        "db_path": db_path.relative_to(REPO_ROOT).as_posix(),
        "counts": counts,
        "t05_node_alpha_verification": {
            "cutoff_2026_05_15": {
                "pit_as_of_throughput_score": alpha_may[0].metric_value,
                "pit_as_of_revision_num": alpha_may[0].revision_num,
                "naive_valid_from_leaked_score": naive_q1_alpha[0].metric_value,
                "q2_future_observation_blocked": len(alpha_may) == 1,
            },
            "cutoff_2026_09_01": {
                "pit_as_of_q1_throughput_score": alpha_sep_q1[0].metric_value,
                "pit_as_of_q1_revision_num": alpha_sep_q1[0].revision_num,
                "pit_as_of_q2_throughput_score": alpha_sep_all[1].metric_value,
            },
        },
        "t05_service_bravo_verification": {
            "cutoff_2026_06_01_reliability_index": bravo_june[0].metric_value,
            "cutoff_2026_06_01_revision_num": bravo_june[0].revision_num,
        },
        "p1_10_tombstone_verification": {
            "total_audit_rows": counts["total_observations"],
            "active_rows": counts["active_observations"],
            "tombstoned_rows": counts["tombstoned_observations"],
            "tombstoned_excluded_from_pit_as_of": "TOMBSTONED_RECORD" not in may_labels,
        },
        "state_evaluator_pilot": {
            "may_2026_provenance_sha256": eval_may.provenance_sha256,
            "sep_2026_provenance_sha256": eval_sep.provenance_sha256,
            "node_alpha_progression": revision_impact,
        },
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest PIT system telemetry fixtures and verify Bitemporal As-Of invariants."
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=REPO_ROOT / "data" / "samples" / "pit_fixtures.json",
        help="Path to input JSON fixtures file.",
    )
    args = parser.parse_args()

    summary = run_pilot_ingestion_and_verification(fixtures_path=args.fixtures)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
