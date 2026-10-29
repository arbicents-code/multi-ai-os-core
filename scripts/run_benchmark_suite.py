#!/usr/bin/env python3
"""Full Gate 0-4 Verification & Risk-Weighted TCVSO Benchmark Runner.

Executes the locked Gate 0 operator configuration:
- OD-1 = 1B: Risk-weighted tri-workload lock (Workload A = 45%, Workload B = 35%, Workload C = 20%)
- OD-2 = 2C: Subscription-first + zero global API keys + useG1Credits=false
- OD-3 = 3B: Native Windows 11 NTFS + PowerShell + Python-backed deterministic hooks
- OD-4 = 4B: £0.00 overage subscription-quota baseline
- OD-5 = 5C: OS-enforced workspace-write sandbox + hard deny rules + human external gate
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ensure_links import check_subscription_billing_isolation, ensure_skills_junction
from scripts.hooks.pre_tool_guard import _run_self_test as run_pre_tool_self_test
from scripts.hooks.stop_verify_gate import _run_self_test as run_stop_hook_self_test
from scripts.tcvso_calculator import MODELED_BENCHMARK_BASELINES
from scripts.validate_handoff import reconstruct_session_state
from tests.adversarial.test_t01_to_t12 import TestAdversarialSuiteT01ToT12
from tests.oracle.run_oracles import run_all_benchmark_oracles as run_all_oracles
from tests.test_os_ctl import TestOsCtlCli
from tests.test_pit_loader import TestBitemporalPITLoaderAndStateEvaluator


WORKLOAD_WEIGHTS_OD1_1B: Dict[str, float] = {
    "A_DATA_AND_ANALYTICS": 0.45,
    "B_SOFTWARE_ENGINEERING": 0.35,
    "C_DEEP_RESEARCH": 0.20,
}


def compute_weighted_portfolio_tcvso() -> Dict[str, Any]:
    """Compute OD-1=1B (45% A / 35% B / 20% C) weighted portfolio TCVSO."""
    baselines = MODELED_BENCHMARK_BASELINES

    c1_a = float(baselines["A_DATA_AND_ANALYTICS"]["Config_1"]["modeled_tcvso_gbp"])
    c1_b = float(baselines["B_SOFTWARE_ENGINEERING"]["Config_1"]["modeled_tcvso_gbp"])
    c1_c = float(baselines["C_DEEP_RESEARCH"]["Config_1"]["modeled_tcvso_gbp"])

    target_a = float(baselines["A_DATA_AND_ANALYTICS"]["Config_5"]["modeled_tcvso_gbp"])
    target_b = float(baselines["B_SOFTWARE_ENGINEERING"]["Config_3"]["modeled_tcvso_gbp"])
    target_c = float(baselines["C_DEEP_RESEARCH"]["Config_2"]["modeled_tcvso_gbp"])

    weighted_c1 = round(
        WORKLOAD_WEIGHTS_OD1_1B["A_DATA_AND_ANALYTICS"] * c1_a
        + WORKLOAD_WEIGHTS_OD1_1B["B_SOFTWARE_ENGINEERING"] * c1_b
        + WORKLOAD_WEIGHTS_OD1_1B["C_DEEP_RESEARCH"] * c1_c,
        2,
    )
    weighted_target = round(
        WORKLOAD_WEIGHTS_OD1_1B["A_DATA_AND_ANALYTICS"] * target_a
        + WORKLOAD_WEIGHTS_OD1_1B["B_SOFTWARE_ENGINEERING"] * target_b
        + WORKLOAD_WEIGHTS_OD1_1B["C_DEEP_RESEARCH"] * target_c,
        2,
    )
    reduction_pct = round(((weighted_c1 - weighted_target) / weighted_c1) * 100.0, 2)

    return {
        "weights": WORKLOAD_WEIGHTS_OD1_1B,
        "single_agent_config_1_weighted_tcvso_gbp": weighted_c1,
        "target_arch_f_weighted_tcvso_gbp": weighted_target,
        "weighted_tcvso_reduction_pct": reduction_pct,
        "per_workload_summary": {
            "A_DATA_AND_ANALYTICS": {
                "weight": 0.45,
                "target_ceiling_gbp": 6.00,
                "config_1_tcvso_gbp": c1_a,
                "selected_config": "Config_5",
                "selected_tcvso_gbp": target_a,
                "within_target": target_a <= 6.00,
            },
            "B_SOFTWARE_ENGINEERING": {
                "weight": 0.35,
                "target_ceiling_gbp": 5.00,
                "config_1_tcvso_gbp": c1_b,
                "selected_config": "Config_3",
                "selected_tcvso_gbp": target_b,
                "within_target": target_b <= 5.00,
            },
            "C_DEEP_RESEARCH": {
                "weight": 0.20,
                "target_ceiling_gbp": 9.00,
                "config_1_tcvso_gbp": c1_c,
                "selected_config": "Config_2",
                "selected_tcvso_gbp": target_c,
                "within_target": target_c <= 9.00,
            },
        },
    }


def run_unittest_suite() -> Dict[str, Any]:
    """Execute all canonical unit and adversarial tests (`T01-T12` + `test_pit_loader` + `test_os_ctl`)."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestBitemporalPITLoaderAndStateEvaluator))
    suite.addTests(loader.loadTestsFromTestCase(TestAdversarialSuiteT01ToT12))
    suite.addTests(loader.loadTestsFromTestCase(TestOsCtlCli))
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    return {
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "passed": result.wasSuccessful(),
    }


def main() -> int:
    junction_check = ensure_skills_junction(REPO_ROOT)
    billing_check = check_subscription_billing_isolation()
    pre_tool_rc = run_pre_tool_self_test()
    stop_hook_rc = run_stop_hook_self_test()
    handoff_recovery = reconstruct_session_state(
        REPO_ROOT / "tasks" / "TASK-2026-1028-01.yaml",
        REPO_ROOT / "handoffs" / "HANDOFF-2026-1028-01.json",
        REPO_ROOT,
    )
    oracle_report = run_all_oracles()
    portfolio_tcvso = compute_weighted_portfolio_tcvso()
    unittest_summary = run_unittest_suite()

    all_passed = (
        junction_check["valid"]
        and billing_check["clean"]
        and pre_tool_rc == 0
        and stop_hook_rc == 0
        and handoff_recovery["recovered"]
        and oracle_report["all_passed"]
        and unittest_summary["passed"]
    )

    report: Dict[str, Any] = {
        "report_id": "BENCHMARK-REPORT-2026-10-29",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "overall_status": "VERIFIED_PASS" if all_passed else "FAIL",
        "locked_gate_0_decisions": {
            "OD-1": "1B (Risk-Weighted Lock: Workload A=45%, Workload B=35%, Workload C=20%)",
            "OD-2": "2C (Subscription-First + Zero Global API Keys + useG1Credits=false)",
            "OD-3": "3B (Native Windows 11 NTFS + PowerShell + Python-Backed Hooks)",
            "OD-4": "4B (£0.00 Overage Subscription-Quota Baseline)",
            "OD-5": "5C (workspace-write / acceptEdits / proceed-in-sandbox + hard deny rules + human external gate)",
        },
        "api_overage_spend_gbp": 0.00,
        "cd3_skills_junction": junction_check,
        "od2_billing_isolation": billing_check,
        "hooks_verification": {
            "pre_tool_guard_t09_passed": pre_tool_rc == 0,
            "stop_verify_gate_t11_passed": stop_hook_rc == 0,
        },
        "t02_handoff_recovery": {
            "recovered": handoff_recovery["recovered"],
            "task_id": handoff_recovery["task_id"],
            "handoff_id": handoff_recovery["handoff_id"],
            "verified_files_count": len(handoff_recovery["verified_files"]),
        },
        "benchmark_oracles_bm_a1_to_c4": {
            "total_tasks": oracle_report["total_tasks"],
            "passed_tasks": oracle_report["passed_tasks"],
            "all_passed": oracle_report["all_passed"],
        },
        "unittest_and_adversarial_suite": unittest_summary,
        "portfolio_tcvso_evaluation": portfolio_tcvso,
    }

    report_path = REPO_ROOT / "benchmarks" / "BENCHMARK_REPORT_2026-10-29.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
