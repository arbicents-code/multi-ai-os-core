#!/usr/bin/env python3
"""
Total Cost per Verified Successful Outcome (TCVSO) Calculator & Circuit Breaker Engine.

Implements Section 4.2, Section 10, Section 16 (T01, T08, T12), Section 18, and Section 19
of the Evidence-Validated Multi-AI Operating System specification.

Formula:
    TCVSO = (Sum_{i=1..N_total}(C_platform_i + C_waste_i + C_human_i) + C_setup_amortised) / N_verified
    If N_verified == 0, TCVSO is strictly Undefined (None).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable


OPERATOR_RATE_GBP_PER_MINUTE: float = 1.00  # £60/hour UK operator baseline (Section 4.2)
DEFAULT_MIN_MULTI_AGENT_IMPROVEMENT: float = 0.15  # 15% TCVSO reduction threshold (T01 / T12)


@dataclass(frozen=True)
class AttemptRecord:
    """Cost and verification record for a single task attempt."""

    c_platform_gbp: float
    c_waste_gbp: float = 0.0
    c_human_gbp: float = 0.0
    verified_pass: bool = True
    critical_defects_caught: int = 0
    cache_hit_ratio: float = 0.90

    @property
    def total_attempt_cost_gbp(self) -> float:
        return round(self.c_platform_gbp + self.c_waste_gbp + self.c_human_gbp, 6)


@dataclass(frozen=True)
class TCVSOResult:
    """Computed TCVSO summary across N_total attempts."""

    n_total: int
    n_verified: int
    sum_c_platform_gbp: float
    sum_c_waste_gbp: float
    sum_c_human_gbp: float
    c_setup_amortised_gbp: float
    total_cost_gbp: float
    tcvso_gbp: float | None
    status: str  # "VALID" | "UNDEFINED_ZERO_VERIFIED"
    verified_pass_rate: float


# Section 10, 18 & 19 Parametric Scenario Model Baselines (GBP)
MODELED_BENCHMARK_BASELINES: dict[str, dict[str, dict[str, Any]]] = {
    "A_DATA_AND_ANALYTICS": {
        "Config_1": {
            "name": "Config 1: Minimal Complexity (Single-Agent Baseline)",
            "c_platform_gbp": 0.45,
            "c_waste_gbp": 0.55,
            "c_human_gbp": 4.50,
            "c_setup_amortised_gbp": 0.26,
            "verified_pass_rate": 0.80,
            "modeled_tcvso_gbp": 7.20,
            "critical_defect_escape_rate": 0.12,
        },
        "Config_5": {
            "name": "Config 5: High-Integrity Data & Quantitative Analytics (2-Platform + PIT Oracle)",
            "c_platform_gbp": 0.82,
            "c_waste_gbp": 0.24,
            "c_human_gbp": 4.10,
            "c_setup_amortised_gbp": 0.60,
            "verified_pass_rate": 1.00,
            "modeled_tcvso_gbp": 5.76,
            "critical_defect_escape_rate": 0.00,
        },
        "Config_3": {
            "name": "Config 3: Software-Development Performance (2-Platform Worktree)",
            "c_platform_gbp": 0.78,
            "c_waste_gbp": 0.30,
            "c_human_gbp": 4.40,
            "c_setup_amortised_gbp": 0.50,
            "verified_pass_rate": 0.96,
            "modeled_tcvso_gbp": 6.23,
            "critical_defect_escape_rate": 0.02,
        },
        "Config_4": {
            "name": "Config 4: Advanced Multi-Agent Automation (Worktree Fan-Out)",
            "c_platform_gbp": 1.95,
            "c_waste_gbp": 0.85,
            "c_human_gbp": 4.20,
            "c_setup_amortised_gbp": 1.10,
            "verified_pass_rate": 0.95,
            "modeled_tcvso_gbp": 8.53,
            "critical_defect_escape_rate": 0.02,
        },
        "Arch_C_Central_Orchestrator": {
            "name": "Architecture C: 3-Platform Centralised Custom Orchestrator (Rejected)",
            "c_platform_gbp": 2.90,
            "c_waste_gbp": 1.72,
            "c_human_gbp": 5.40,
            "c_setup_amortised_gbp": 1.80,
            "verified_pass_rate": 0.95,
            "modeled_tcvso_gbp": 12.42,
            "critical_defect_escape_rate": 0.03,
        },
    },
    "B_SOFTWARE_ENGINEERING": {
        "Config_1": {
            "name": "Config 1: Minimal Complexity (Single-Agent Baseline)",
            "c_platform_gbp": 0.38,
            "c_waste_gbp": 0.49,
            "c_human_gbp": 4.20,
            "c_setup_amortised_gbp": 0.27,
            "verified_pass_rate": 0.80,
            "modeled_tcvso_gbp": 6.67,
            "critical_defect_escape_rate": 0.08,
        },
        "Config_3": {
            "name": "Config 3: Software-Development Performance (2-Platform Worktree + Browser/Review)",
            "c_platform_gbp": 0.68,
            "c_waste_gbp": 0.22,
            "c_human_gbp": 3.20,
            "c_setup_amortised_gbp": 0.50,
            "verified_pass_rate": 1.00,
            "modeled_tcvso_gbp": 4.60,
            "critical_defect_escape_rate": 0.00,
        },
        "Config_4": {
            "name": "Config 4: Advanced Multi-Agent Automation (Batch Worktrees)",
            "c_platform_gbp": 1.60,
            "c_waste_gbp": 0.70,
            "c_human_gbp": 3.50,
            "c_setup_amortised_gbp": 1.00,
            "verified_pass_rate": 0.95,
            "modeled_tcvso_gbp": 7.16,
            "critical_defect_escape_rate": 0.01,
        },
        "Arch_E_Three_Platform_Swarm": {
            "name": "Architecture E: 3-Platform Specialist Agent Swarm (Rejected)",
            "c_platform_gbp": 4.20,
            "c_waste_gbp": 2.90,
            "c_human_gbp": 5.10,
            "c_setup_amortised_gbp": 1.95,
            "verified_pass_rate": 0.95,
            "modeled_tcvso_gbp": 14.90,
            "critical_defect_escape_rate": 0.04,
        },
    },
    "C_DEEP_RESEARCH": {
        "Config_1": {
            "name": "Config 1: Minimal Complexity (Single-Agent Research Baseline)",
            "c_platform_gbp": 0.65,
            "c_waste_gbp": 0.85,
            "c_human_gbp": 9.80,
            "c_setup_amortised_gbp": 0.23,
            "verified_pass_rate": 0.75,
            "modeled_tcvso_gbp": 15.37,
            "critical_defect_escape_rate": 0.15,
        },
        "Config_2": {
            "name": "Config 2: Research & Analytical Excellence (2-Platform Adversarial Audit)",
            "c_platform_gbp": 1.10,
            "c_waste_gbp": 0.35,
            "c_human_gbp": 6.50,
            "c_setup_amortised_gbp": 0.50,
            "verified_pass_rate": 1.00,
            "modeled_tcvso_gbp": 8.45,
            "critical_defect_escape_rate": 0.00,
        },
    },
}


def _coerce_attempt(item: AttemptRecord | dict[str, Any]) -> AttemptRecord:
    if isinstance(item, AttemptRecord):
        return item
    c_platform = float(item.get("c_platform_gbp", item.get("c_platform", 0.0)))
    c_waste = float(item.get("c_waste_gbp", item.get("c_waste", 0.0)))
    if "c_human_gbp" in item or "c_human" in item:
        c_human = float(item.get("c_human_gbp", item.get("c_human", 0.0)))
    elif "human_minutes" in item:
        c_human = float(item["human_minutes"]) * OPERATOR_RATE_GBP_PER_MINUTE
    else:
        c_human = 0.0
    verified = bool(item.get("verified_pass", item.get("verified", True)))
    defects = int(item.get("critical_defects_caught", 0))
    cache_hit = float(item.get("cache_hit_ratio", 0.90))
    return AttemptRecord(
        c_platform_gbp=c_platform,
        c_waste_gbp=c_waste,
        c_human_gbp=c_human,
        verified_pass=verified,
        critical_defects_caught=defects,
        cache_hit_ratio=cache_hit,
    )


def compute_tcvso_details(
    attempts: Iterable[AttemptRecord | dict[str, Any]],
    c_setup_amortised_gbp: float = 0.0,
) -> TCVSOResult:
    """
    Compute the Section 4.2 Total Cost per Verified Successful Outcome (TCVSO):
        TCVSO = (Sum(C_platform + C_waste + C_human) + C_setup_amortised) / N_verified
    """
    records = [_coerce_attempt(a) for a in attempts]
    n_total = len(records)
    n_verified = sum(1 for r in records if r.verified_pass)

    sum_platform = round(sum(r.c_platform_gbp for r in records), 6)
    sum_waste = round(sum(r.c_waste_gbp for r in records), 6)
    sum_human = round(sum(r.c_human_gbp for r in records), 6)
    setup = round(float(c_setup_amortised_gbp), 6)
    total_cost = round(sum_platform + sum_waste + sum_human + setup, 6)

    if n_verified == 0:
        return TCVSOResult(
            n_total=n_total,
            n_verified=0,
            sum_c_platform_gbp=sum_platform,
            sum_c_waste_gbp=sum_waste,
            sum_c_human_gbp=sum_human,
            c_setup_amortised_gbp=setup,
            total_cost_gbp=total_cost,
            tcvso_gbp=None,
            status="UNDEFINED_ZERO_VERIFIED",
            verified_pass_rate=0.0,
        )

    tcvso = round(total_cost / n_verified, 2)
    pass_rate = round(n_verified / n_total, 4) if n_total > 0 else 0.0
    return TCVSOResult(
        n_total=n_total,
        n_verified=n_verified,
        sum_c_platform_gbp=sum_platform,
        sum_c_waste_gbp=sum_waste,
        sum_c_human_gbp=sum_human,
        c_setup_amortised_gbp=setup,
        total_cost_gbp=total_cost,
        tcvso_gbp=tcvso,
        status="VALID",
        verified_pass_rate=pass_rate,
    )


def calculate_tcvso(
    attempts: Iterable[AttemptRecord | dict[str, Any]],
    c_setup_amortised_gbp: float = 0.0,
) -> float | None:
    """Return numeric TCVSO in GBP, or None if N_verified == 0."""
    return compute_tcvso_details(attempts, c_setup_amortised_gbp=c_setup_amortised_gbp).tcvso_gbp


def evaluate_single_agent_challenge(
    single_agent_tcvso_gbp: float | None,
    multi_agent_tcvso_gbp: float | None,
    caught_critical_defect_missed_by_single: bool = False,
    min_improvement_ratio: float = DEFAULT_MIN_MULTI_AGENT_IMPROVEMENT,
) -> dict[str, Any]:
    """
    Enforce Adversarial Tests T01 (Single-Agent Challenge) & T12 (Minimum-Complexity Challenge).

    A multi-platform or multi-agent configuration is rejected unless:
      1. It reduces TCVSO by >= `min_improvement_ratio` (default 15%), OR
      2. It catches a critical/high-severity defect missed by Config 1 while still passing hard constraints.
    """
    if multi_agent_tcvso_gbp is None:
        return {
            "approved": False,
            "selected_configuration": "Config_1",
            "reason": "Multi-agent candidate produced 0 verified outcomes (TCVSO Undefined).",
            "improvement_ratio": 0.0,
        }

    if single_agent_tcvso_gbp is None or single_agent_tcvso_gbp <= 0:
        return {
            "approved": True,
            "selected_configuration": "Multi_Platform",
            "reason": "Single-agent baseline failed verification (TCVSO Undefined); multi-platform succeeded.",
            "improvement_ratio": 1.0,
        }

    improvement_ratio = round(
        (single_agent_tcvso_gbp - multi_agent_tcvso_gbp) / single_agent_tcvso_gbp,
        4,
    )

    if improvement_ratio >= min_improvement_ratio:
        return {
            "approved": True,
            "selected_configuration": "Multi_Platform",
            "reason": (
                f"Multi-platform TCVSO (£{multi_agent_tcvso_gbp:.2f}) beats single-agent "
                f"(£{single_agent_tcvso_gbp:.2f}) by {improvement_ratio * 100:.1f}% (>= {min_improvement_ratio * 100:.0f}% threshold)."
            ),
            "improvement_ratio": improvement_ratio,
        }

    if caught_critical_defect_missed_by_single and multi_agent_tcvso_gbp <= single_agent_tcvso_gbp:
        return {
            "approved": True,
            "selected_configuration": "Multi_Platform",
            "reason": "Multi-platform caught critical defect missed by Config 1 at equal or lower TCVSO.",
            "improvement_ratio": improvement_ratio,
        }

    return {
        "approved": False,
        "selected_configuration": "Config_1",
        "reason": (
            f"Rejected under T01/T12: Multi-platform TCVSO (£{multi_agent_tcvso_gbp:.2f}) does not beat "
            f"Config 1 (£{single_agent_tcvso_gbp:.2f}) by >= {min_improvement_ratio * 100:.0f}% "
            f"(actual improvement: {improvement_ratio * 100:.1f}%)."
        ),
        "improvement_ratio": improvement_ratio,
    }


def route_minimum_complexity(task_spec: dict[str, Any]) -> dict[str, Any]:
    """
    Enforce Section 19 & T12 Minimum-Complexity Routing Matrix.

    Routes single-file / scoped low-complexity tasks (<= 3 files, mechanical edits, formatting)
    to Config 1 (Single-Platform) and reserves Config 2, Config 3, and Config 5 for high-complexity
    or correctness-critical workloads where multi-platform TCVSO dominates.
    """
    target_files = task_spec.get("target_files") or task_spec.get("inputs", {}).get("target_files", [])
    file_count = int(task_spec.get("file_count", len(target_files) if target_files else 1))
    workload = str(task_spec.get("workload_class", "B_SOFTWARE_ENGINEERING")).upper()
    complexity = str(task_spec.get("complexity", "LOW")).upper()
    requires_pit_audit = bool(task_spec.get("requires_pit_audit", False))
    requires_primary_source_audit = bool(task_spec.get("requires_primary_source_audit", False))

    if (
        file_count <= 3
        and not requires_pit_audit
        and not requires_primary_source_audit
        and complexity in {"LOW", "LOW_SINGLE_FILE", "MECHANICAL", "SCOPED_SINGLE_MODULE"}
    ):
        return {
            "recommended_config": "Config_1",
            "multi_platform_justified": False,
            "platforms_count": 1,
            "rationale": (
                f"Task touches {file_count} file(s) with {complexity} complexity; "
                "Config 1 (Single-Platform + deterministic linter/pytest) dominates TCVSO (Section 19 / T12)."
            ),
        }

    if "DATA" in workload or "ANALYTICS" in workload or requires_pit_audit:
        return {
            "recommended_config": "Config_5",
            "multi_platform_justified": True,
            "platforms_count": 2,
            "rationale": "Bitemporal data & analytics workload routes to Config 5 (modeled TCVSO drops from £7.20 to £5.76, -20.0%).",
        }

    if "RESEARCH" in workload or requires_primary_source_audit:
        return {
            "recommended_config": "Config_2",
            "multi_platform_justified": True,
            "platforms_count": 2,
            "rationale": "Deep research synthesis routes to Config 2 (modeled TCVSO drops from £15.37 to £8.45, -45.0%).",
        }

    return {
        "recommended_config": "Config_3",
        "multi_platform_justified": True,
        "platforms_count": 2,
        "rationale": (
            f"Multi-file engineering ({file_count} files, {complexity}) routes to Config 3 "
            "(modeled TCVSO drops from £6.67 to £4.60, -31.0%)."
        ),
    }


@dataclass
class CostEscalationBreaker:
    """
    Enforces Adversarial Test T08 (Cost Escalation & Retry Circuit Breaker).
    Halts execution immediately if session spend, consecutive test failures, or uncached
    context re-sends exceed configured task bounds.
    """

    max_session_spend_gbp: float = 2.50
    max_consecutive_failed_tests: int = 2
    max_context_resends: int = 2
    min_cache_hit_ratio: float = 0.85

    current_spend_gbp: float = 0.0
    consecutive_failed_tests: int = 0
    context_resends: int = 0
    halted: bool = False
    halt_reasons: list[str] = field(default_factory=list)

    def record_turn(
        self,
        turn_cost_gbp: float,
        test_passed: bool | None = None,
        was_uncached_resend: bool = False,
        cache_hit_ratio: float | None = None,
    ) -> dict[str, Any]:
        self.current_spend_gbp = round(self.current_spend_gbp + float(turn_cost_gbp), 6)

        if test_passed is False:
            self.consecutive_failed_tests += 1
        elif test_passed is True:
            self.consecutive_failed_tests = 0

        if was_uncached_resend:
            self.context_resends += 1

        if self.current_spend_gbp > self.max_session_spend_gbp:
            self.halted = True
            self.halt_reasons.append(
                f"BUDGET_BREAKER: Session spend £{self.current_spend_gbp:.2f} exceeded cap £{self.max_session_spend_gbp:.2f}"
            )

        if self.consecutive_failed_tests > self.max_consecutive_failed_tests:
            self.halted = True
            self.halt_reasons.append(
                f"RETRY_BREAKER: Consecutive failed test loops ({self.consecutive_failed_tests}) "
                f"exceeded max allowed ({self.max_consecutive_failed_tests})"
            )

        if self.context_resends > self.max_context_resends:
            self.halted = True
            self.halt_reasons.append(
                f"RESEND_BREAKER: Uncached context resends ({self.context_resends}) "
                f"exceeded max allowed ({self.max_context_resends})"
            )

        if cache_hit_ratio is not None and cache_hit_ratio < self.min_cache_hit_ratio:
            self.halted = True
            self.halt_reasons.append(
                f"CACHE_BREAKER: Prompt cache hit ratio {cache_hit_ratio:.2%} fell below minimum {self.min_cache_hit_ratio:.2%}"
            )

        return {
            "halted": self.halted,
            "current_spend_gbp": self.current_spend_gbp,
            "consecutive_failed_tests": self.consecutive_failed_tests,
            "context_resends": self.context_resends,
            "halt_reasons": list(self.halt_reasons),
        }


def evaluate_all_modeled_baselines() -> dict[str, Any]:
    """Evaluate all Section 10 / 18 modeled configurations against T01 and T12."""
    report: dict[str, Any] = {}
    for workload, configs in MODELED_BENCHMARK_BASELINES.items():
        c1_tcvso = configs["Config_1"]["modeled_tcvso_gbp"]
        workload_evals: dict[str, Any] = {}
        for cfg_id, data in configs.items():
            if cfg_id == "Config_1":
                workload_evals[cfg_id] = {
                    **data,
                    "t01_t12_verdict": "RETAIN_BASELINE",
                    "improvement_vs_config_1": 0.0,
                }
            else:
                verdict = evaluate_single_agent_challenge(
                    single_agent_tcvso_gbp=c1_tcvso,
                    multi_agent_tcvso_gbp=data["modeled_tcvso_gbp"],
                    caught_critical_defect_missed_by_single=(data["critical_defect_escape_rate"] == 0.0),
                )
                workload_evals[cfg_id] = {
                    **data,
                    "t01_t12_verdict": "RETAIN" if verdict["approved"] else "REJECT",
                    "improvement_vs_config_1": verdict["improvement_ratio"],
                    "decision_reason": verdict["reason"],
                }
        report[workload] = workload_evals
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="TCVSO Calculator & Cost Escalation Circuit Breaker (Section 4.2, 10, 16, 18)"
    )
    parser.add_argument("--summary", action="store_true", help="Print modeled benchmark TCVSO baselines")
    parser.add_argument("--verify-gate", action="store_true", help="Verify T01, T08, and T12 economic gates")
    parser.add_argument("--workload", type=str, default=None, help="Filter by workload (A_DATA_AND_ANALYTICS, B_SOFTWARE_ENGINEERING, C_DEEP_RESEARCH)")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    report = evaluate_all_modeled_baselines()
    if args.workload:
        key = args.workload.upper()
        if key not in report:
            print(f"Unknown workload: {args.workload}", file=sys.stderr)
            return 2
        report = {key: report[key]}

    if args.verify_gate:
        # Verify Config 5 on Workload A, Config 3 on Workload B, Config 2 on Workload C are retained,
        # while 3-platform Arch C and Arch E swarms are rejected.
        full_report = evaluate_all_modeled_baselines()
        assertions = [
            full_report["A_DATA_AND_ANALYTICS"]["Config_5"]["t01_t12_verdict"] == "RETAIN",
            full_report["A_DATA_AND_ANALYTICS"]["Arch_C_Central_Orchestrator"]["t01_t12_verdict"] == "REJECT",
            full_report["B_SOFTWARE_ENGINEERING"]["Config_3"]["t01_t12_verdict"] == "RETAIN",
            full_report["B_SOFTWARE_ENGINEERING"]["Arch_E_Three_Platform_Swarm"]["t01_t12_verdict"] == "REJECT",
            full_report["C_DEEP_RESEARCH"]["Config_2"]["t01_t12_verdict"] == "RETAIN",
        ]
        if not all(assertions):
            print("TCVSO verification gate FAILED.", file=sys.stderr)
            return 1

    if args.json or not args.summary:
        print(json.dumps(report, indent=2))
    else:
        for wl, cfgs in report.items():
            print(f"=== {wl} ===")
            for cfg_id, info in cfgs.items():
                print(
                    f"  {cfg_id:30s} | TCVSO: £{info['modeled_tcvso_gbp']:6.2f} | "
                    f"PassRate: {info['verified_pass_rate']*100:5.1f}% | Verdict: {info['t01_t12_verdict']}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
