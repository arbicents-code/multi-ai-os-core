#!/usr/bin/env python3
"""
Unit Test Suite for BitemporalPITStore and DeterministicStateEvaluator (`tests/test_pit_loader.py`).

Tests Section 13.1 & Section 16 (T05, P1-10) invariants:
  1. Point-in-time (PIT) historical cutoff filtering (`valid_from_utc <= cutoff_ts` AND `ingested_at_utc <= cutoff_ts`).
  2. Restatement/revision isolation (NODE-ALPHA 2026-05-15 -> 1.00 vs 2026-08-15 -> 1.50; SERVICE-BRAVO 2026-06-01 -> 0.12 vs 2026-08-10 -> 0.08).
  3. Look-ahead bias rejection (future Q2 2026 release at 2026-08-20 excluded at 2026-05-15 cutoff; naive datetime raises ValueError).
  4. Historical cohort completeness (`LEGACY-NODE-DEPRECATED` keyed by permanent `SYS-9999` retained in May 2026 cross-section).
  5. P1-10 GDPR / compliance retention tombstone erasure (`tombstone_entity_or_payload` removes raw payload file and nulls `metric_value` while preserving audit row count and SHA-256 lineage).
  6. Cryptographic SHA-256 payload provenance (`compute_payload_sha256` and `EvaluationSignalManifest.provenance_sha256`).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
import warnings

warnings.filterwarnings("ignore", category=ResourceWarning)

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.bitemporal.pit_loader import (
    BitemporalPITStore,
    PIT_COLUMNS,
    canonical_utc_iso,
    compute_payload_sha256,
)
from src.bitemporal.state_evaluator import DeterministicStateEvaluator


class TestBitemporalPITLoaderAndStateEvaluator(unittest.TestCase):
    """Comprehensive deterministic unit tests for BitemporalPITStore and DeterministicStateEvaluator."""

    def setUp(self) -> None:
        warnings.simplefilter("ignore", ResourceWarning)
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_path = Path(self.temp_dir.name)
        self.db_path = self.tmp_path / "pit_store" / "pit_store.db"
        self.payload_root = self.tmp_path / "payloads"
        self.store = BitemporalPITStore(
            db_path=self.db_path,
            payload_root=self.payload_root,
        )
        fixtures_file = REPO_ROOT / "data" / "samples" / "pit_fixtures.json"
        raw_fixtures = json.loads(fixtures_file.read_text(encoding="utf-8"))
        self.ingested = self.store.ingest_observations(raw_fixtures["observations"])

    def tearDown(self) -> None:
        import gc
        gc.collect()
        self.temp_dir.cleanup()

    def test_schema_columns_and_fixture_ingestion_counts(self) -> None:
        """Verify 19-column schema and exact fixture counts (13 total, 12 active, 1 tombstoned)."""
        self.assertEqual(len(PIT_COLUMNS), 19)
        self.assertEqual(len(self.ingested), 13)
        counts = self.store.count_all_observations()
        self.assertEqual(counts["total_observations"], 13)
        self.assertEqual(counts["active_observations"], 12)
        self.assertEqual(counts["tombstoned_observations"], 1)

    def test_naive_datetime_rejected_with_value_error(self) -> None:
        """Section 14.3 Material Decision: Naive datetime or timestamp without UTC offset raises ValueError."""
        with self.assertRaises(ValueError):
            canonical_utc_iso("2026-05-15 12:00:00")
        with self.assertRaises(ValueError):
            canonical_utc_iso(datetime(2026, 5, 15, 12, 0, 0))
        self.assertEqual(
            canonical_utc_iso(datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)),
            "2026-05-15T00:00:00Z",
        )

    def test_pit_restatement_isolation_node_alpha_and_service_bravo(self) -> None:
        """Test T05: Retroactive revision arriving in August 2026 never leaks into May/June 2026 PIT queries."""
        # NODE-ALPHA as of 2026-05-15T00:00:00Z -> must return rev 1 (throughput_score = 1.00), NOT rev 2 (1.50)
        alpha_may = self.store.query_pit_as_of(
            "2026-05-15T00:00:00Z", label="NODE-ALPHA", metric_name="throughput_score"
        )
        self.assertEqual(len(alpha_may), 1)
        self.assertAlmostEqual(alpha_may[0].metric_value or 0.0, 1.00, places=6)
        self.assertEqual(alpha_may[0].revision_num, 1)

        # NODE-ALPHA as of 2026-08-16T00:00:00Z (after revision, before Q2 release on Aug 20) -> rev 2 (1.50)
        alpha_aug16 = self.store.query_pit_as_of(
            "2026-08-16T00:00:00Z", label="NODE-ALPHA", metric_name="throughput_score"
        )
        self.assertEqual(len(alpha_aug16), 1)
        self.assertAlmostEqual(alpha_aug16[0].metric_value or 0.0, 1.50, places=6)
        self.assertEqual(alpha_aug16[0].revision_num, 2)

        # SERVICE-BRAVO as of 2026-06-01T12:00:00Z -> must return rev 1 (reliability_index = 0.12), NOT rev 2 (0.08)
        bravo_june = self.store.query_pit_as_of(
            "2026-06-01T12:00:00Z", label="SERVICE-BRAVO", metric_name="reliability_index"
        )
        self.assertEqual(len(bravo_june), 1)
        self.assertAlmostEqual(bravo_june[0].metric_value or 0.0, 0.12, places=6)
        self.assertEqual(bravo_june[0].revision_num, 1)

        # Confirm naive valid_from query leaks the August revision at the June cutoff
        bravo_naive = self.store.query_naive_valid_from(
            "2026-06-01T12:00:00Z", label="SERVICE-BRAVO", metric_name="reliability_index"
        )
        self.assertEqual(len(bravo_naive), 1)
        self.assertAlmostEqual(bravo_naive[0].metric_value or 0.0, 0.08, places=6)
        with self.assertRaises(AssertionError):
            self.store.verify_no_lookahead_or_restatement_leak(bravo_naive, "2026-06-01T12:00:00Z")

    def test_lookahead_bias_rejection_future_q2_release(self) -> None:
        """Ensure Q2 2026 observation (event_time 2026-06-30, ingested 2026-08-20) is excluded prior to ingestion."""
        # At 2026-07-15, Q2 period has ended (valid_from 2026-06-30 <= 2026-07-15),
        # but the benchmark report was not published/ingested until 2026-08-20!
        alpha_july = self.store.query_pit_as_of(
            "2026-07-15T00:00:00Z", label="NODE-ALPHA", metric_name="throughput_score"
        )
        self.assertEqual(len(alpha_july), 1)
        self.assertEqual(alpha_july[0].event_time_utc, "2026-03-31T23:59:59Z")
        self.assertAlmostEqual(alpha_july[0].metric_value or 0.0, 1.00, places=6)

        # At 2026-09-01, both Q1 (revised to 1.50) and Q2 (1.85) are known
        alpha_sept = self.store.query_pit_as_of(
            "2026-09-01T00:00:00Z", label="NODE-ALPHA", metric_name="throughput_score"
        )
        self.assertEqual(len(alpha_sept), 2)
        values_by_period = {obs.event_time_utc: obs.metric_value for obs in alpha_sept}
        self.assertAlmostEqual(values_by_period["2026-03-31T23:59:59Z"] or 0.0, 1.50, places=6)
        self.assertAlmostEqual(values_by_period["2026-06-30T23:59:59Z"] or 0.0, 1.85, places=6)

    def test_cohort_completeness_deprecated_entity_retained_in_evaluator(self) -> None:
        """Verify decommissioned entity (`LEGACY-NODE-DEPRECATED` / `SYS-9999`) is retained in historical cross-sections."""
        evaluator = DeterministicStateEvaluator(self.store)
        manifest = evaluator.evaluate_cross_section("2026-05-15T00:00:00Z", unit_filter="SCORE")
        self.assertTrue(manifest.includes_deprecated_entities)
        labels = [r.label_at_time for r in manifest.rankings]
        self.assertEqual(labels, ["CLUSTER-CHARLIE", "ENGINE-DELTA", "NODE-ALPHA", "LEGACY-NODE-DEPRECATED"])
        legacy_row = next(r for r in manifest.rankings if r.label_at_time == "LEGACY-NODE-DEPRECATED")
        self.assertEqual(legacy_row.entity_id, "SYS-9999")
        self.assertEqual(legacy_row.action_classification, "QUARANTINE_DEGRADED")

    def test_p1_10_gdpr_and_retention_tombstone_erasure(self) -> None:
        """Verify P1-10 tombstone erasure deletes raw payload file and nulls metric_value while preserving audit lineage."""
        before_counts = self.store.count_all_observations()
        delta_obs = self.store.query_pit_as_of(
            "2026-05-15T00:00:00Z", label="ENGINE-DELTA", metric_name="throughput_score"
        )
        self.assertEqual(len(delta_obs), 1)
        payload_sha = delta_obs[0].raw_payload_sha256
        payload_file = self.payload_root / f"vendor={delta_obs[0].source_vendor}" / f"{payload_sha}.json"
        self.assertTrue(payload_file.exists())

        affected = self.store.tombstone_entity_or_payload(
            observation_id=delta_obs[0].observation_id,
            reason="REDACTED_PII",
        )
        self.assertEqual(affected, 1)
        self.assertFalse(payload_file.exists())

        after_counts = self.store.count_all_observations()
        # Total row count is unchanged (immutable audit log), active decremented by 1
        self.assertEqual(after_counts["total_observations"], before_counts["total_observations"])
        self.assertEqual(after_counts["active_observations"], before_counts["active_observations"] - 1)
        self.assertEqual(after_counts["tombstoned_observations"], before_counts["tombstoned_observations"] + 1)

        # Tombstoned record is excluded from active PIT queries
        delta_after = self.store.query_pit_as_of(
            "2026-05-15T00:00:00Z", label="ENGINE-DELTA", metric_name="throughput_score"
        )
        self.assertEqual(len(delta_after), 0)

    def test_sha256_payload_and_evaluator_manifest_provenance(self) -> None:
        """Verify deterministic SHA-256 payload digest and state evaluator manifest provenance."""
        sample_payload = {"system_name": "Compute Node Alpha", "throughput_score": 1.00}
        digest_a = compute_payload_sha256(sample_payload)
        digest_b = compute_payload_sha256({"throughput_score": 1.00, "system_name": "Compute Node Alpha"})
        self.assertEqual(len(digest_a), 64)
        self.assertEqual(digest_a, digest_b)

        evaluator = DeterministicStateEvaluator(self.store)
        m1 = evaluator.evaluate_cross_section("2026-05-15T00:00:00Z")
        m2 = evaluator.evaluate_cross_section("2026-05-15T00:00:00Z")
        self.assertEqual(m1.provenance_sha256, m2.provenance_sha256)
        self.assertEqual(len(m1.provenance_sha256), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
