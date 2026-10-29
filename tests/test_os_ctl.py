#!/usr/bin/env python3
"""
Unit & Integration Tests for `scripts/os_ctl.py` (`TestOsCtlCli`).

Verifies all 5 subcommands of the Multi-AI OS Control Plane & Project Bootstrapper:
  1. `status`: CLI probes, OD-2=2C billing isolation, CD-3 skills junction, AGENTS.md budget, and T10 claims check.
  2. `new-task`: T12 minimum-complexity routing (`Config_1` single-file vs `Config_3` / `Config_5` / `Config_2` multi-file).
  3. `handoff`: Live SHA-256 file & log hashing and T11 `stop_verify_gate` completion gate enforcement.
  4. `verify`: T02 stateless session recovery, SHA-256 tamper detection, and T09/T11 hook self-tests.
  5. `init-project`: Full Three-Tier Policy & Security Adapter bootstrap into an isolated project directory.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.os_ctl import (
    cmd_handoff,
    cmd_init_project,
    cmd_new_task,
    cmd_status,
    cmd_verify,
)


class TestOsCtlCli(unittest.TestCase):
    """End-to-end deterministic tests for the `scripts/os_ctl.py` control plane."""

    def test_01_status_healthy_on_canonical_repo(self) -> None:
        """Verify `cmd_status` reports healthy state, policy budgets, and non-expired T10 claims."""
        status = cmd_status(workspace_root=REPO_ROOT)
        self.assertTrue(status["healthy"], f"Expected healthy status, got: {status}")
        self.assertEqual(status["status"], "HEALTHY")
        self.assertTrue(status["od2_billing_isolation"]["clean"])
        self.assertTrue(status["cd3_skills_junction"]["valid"])
        self.assertTrue(status["policy_budget_p1_07"]["agents_md_within_budget"])
        self.assertLess(status["policy_budget_p1_07"]["agents_md_lines"], 120)
        self.assertLess(status["policy_budget_p1_07"]["agents_md_bytes"], 6144)
        self.assertEqual(status["policy_budget_p1_07"]["claude_md_line_1"], "@AGENTS.md")
        self.assertTrue(status["t10_claims_register"]["valid"])
        self.assertEqual(len(status["t10_claims_register"]["expired_claims"]), 0)

    def test_02_init_project_bootstraps_three_tier_adapter(self) -> None:
        """Verify `cmd_init_project` bootstraps a new directory with full policy, hooks, and skills junction."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="multi_ai_os_bootstrap_"))
        try:
            res = cmd_init_project(
                target_dir=tmp_dir,
                project_name="Domain-Agnostic Analytics Node",
                source_root=REPO_ROOT,
            )
            self.assertTrue(res["bootstrapped"], f"Bootstrap failed: {res}")
            self.assertTrue((tmp_dir / "AGENTS.md").exists())
            self.assertTrue((tmp_dir / "CLAUDE.md").exists())
            self.assertTrue((tmp_dir / ".claude" / "settings.json").exists())
            self.assertTrue((tmp_dir / ".codex" / "config.toml").exists())
            self.assertTrue((tmp_dir / ".codex" / "hooks.json").exists())
            self.assertTrue((tmp_dir / ".agents" / "hooks.json").exists())
            self.assertTrue((tmp_dir / "scripts" / "hooks" / "pre_tool_guard.py").exists())
            self.assertTrue((tmp_dir / "scripts" / "hooks" / "stop_verify_gate.py").exists())
            self.assertTrue((tmp_dir / "research" / "CLAIMS_REGISTER.yaml").exists())
            self.assertGreaterEqual(len(res["cd3_skills_junction"]["discovered_skills"]), 3)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_03_new_task_routes_config_1_vs_config_3_and_config_5(self) -> None:
        """Verify `cmd_new_task` enforces T12 minimum-complexity routing across workloads."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="multi_ai_os_routing_"))
        try:
            cmd_init_project(target_dir=tmp_dir, project_name="RoutingTest", source_root=REPO_ROOT)

            # 1. Single-file low complexity -> Config_1
            low_res = cmd_new_task(
                task_id="TASK-TEST-LOW-01",
                title="Single-file formatting check",
                workload="B_SOFTWARE_ENGINEERING",
                complexity="LOW_SINGLE_FILE",
                target_files=["README.md"],
                create_worktree=False,
                workspace_root=tmp_dir,
            )
            self.assertEqual(low_res["status"], "CREATED")
            self.assertEqual(low_res["tcvso_routing"]["selected_config"], "Config_1")
            self.assertFalse(low_res["tcvso_routing"]["multi_platform_justified"])

            # 2. Multi-file engineering -> Config_3 (£4.60 vs £6.67)
            eng_res = cmd_new_task(
                task_id="TASK-TEST-ENG-02",
                title="Multi-file software engineering module",
                workload="B_SOFTWARE_ENGINEERING",
                complexity="MODERATE_MULTI_FILE",
                target_files=["scripts/os_ctl.py", "scripts/validate_handoff.py"],
                create_worktree=True,
                workspace_root=tmp_dir,
            )
            self.assertEqual(eng_res["status"], "CREATED")
            self.assertEqual(eng_res["tcvso_routing"]["selected_config"], "Config_3")
            self.assertTrue(eng_res["tcvso_routing"]["multi_platform_justified"])
            self.assertAlmostEqual(eng_res["tcvso_routing"]["modeled_tcvso_gbp"], 4.60, places=2)
            self.assertIsNotNone(eng_res["worktree"])
            self.assertTrue(eng_res["worktree"]["skills_junction_valid"])

            # 3. High-integrity data & analytics -> Config_5 (£5.76 vs £7.20)
            data_res = cmd_new_task(
                task_id="TASK-TEST-DATA-03",
                title="Bitemporal PIT analytical pipeline",
                workload="A_DATA_AND_ANALYTICS",
                complexity="HIGH_ARCHITECTURAL",
                target_files=["scripts/validate_handoff.py", "scripts/tcvso_calculator.py"],
                create_worktree=False,
                workspace_root=tmp_dir,
            )
            self.assertEqual(data_res["status"], "CREATED")
            self.assertEqual(data_res["tcvso_routing"]["selected_config"], "Config_5")
            self.assertTrue(data_res["tcvso_routing"]["multi_platform_justified"])
            self.assertAlmostEqual(data_res["tcvso_routing"]["modeled_tcvso_gbp"], 5.76, places=2)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_04_handoff_and_verify_t02_t11_roundtrip(self) -> None:
        """Verify `cmd_handoff` writes SHA-256-stamped JSON and `cmd_verify` recovers T02 state & detects tampering."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="multi_ai_os_handoff_"))
        try:
            cmd_init_project(target_dir=tmp_dir, project_name="HandoffDrill", source_root=REPO_ROOT)

            cmd_new_task(
                task_id="TASK-DRILL-01",
                title="Cross-Platform Control Plane Drill",
                workload="B_SOFTWARE_ENGINEERING",
                complexity="MODERATE_MULTI_FILE",
                target_files=["AGENTS.md", "CLAUDE.md"],
                create_worktree=True,
                workspace_root=tmp_dir,
            )

            ho_res = cmd_handoff(
                task_id="TASK-DRILL-01",
                handoff_id="HANDOFF-DRILL-01",
                from_agent="claude-sonnet-5-5",
                to_agent="gpt-6.1-sol",
                state_version=1,
                summary="Verified Three-Tier policy and deterministic hooks.",
                modified_files=["AGENTS.md", "CLAUDE.md"],
                run_tests=False,
                workspace_root=tmp_dir,
            )
            self.assertTrue(ho_res["handoff_written"], f"Handoff failed: {ho_res}")
            self.assertEqual(ho_res["status"], "HANDOFF_WRITTEN")
            self.assertEqual(ho_res["t11_gate"]["decision"], "allow")

            # Verify valid T02 session recovery + T09/T11 hooks
            ver_res = cmd_verify(
                task_id="TASK-DRILL-01",
                handoff_id="HANDOFF-DRILL-01",
                workspace_root=tmp_dir,
            )
            self.assertTrue(ver_res["valid"], f"Verify failed: {ver_res}")
            self.assertTrue(ver_res["t02_session_recovery"]["recovered"])
            self.assertTrue(ver_res["t09_pre_tool_guard_self_test_passed"])
            self.assertTrue(ver_res["t11_stop_verify_gate_self_test_passed"])

            # Tamper with a tracked file and confirm `cmd_verify` deterministically rejects the mismatch
            (tmp_dir / "README.md").write_text("tampered\n", encoding="utf-8")
            (tmp_dir / "CLAUDE.md").write_text("@AGENTS.md\n# tampered line\n", encoding="utf-8")
            tampered_ver = cmd_verify(
                task_id="TASK-DRILL-01",
                handoff_id="HANDOFF-DRILL-01",
                workspace_root=tmp_dir,
            )
            self.assertFalse(tampered_ver["valid"])
            self.assertFalse(tampered_ver["t02_session_recovery"]["recovered"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
