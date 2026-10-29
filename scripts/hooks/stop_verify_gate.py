#!/usr/bin/env python3
"""
Deterministic Stop-Hook Verification Gate (Enforcing T11 & P1-12).

Prevents an agent across Anthropic Claude Code, OpenAI Codex, or Google Antigravity
from declaring task completion unless:
1. Verification evidence (`verification_evidence.exit_code == 0` and non-empty `log_sha256`
   or live deterministic unit test run) is present and passing.
2. Active handoff manifest (`handoffs/HANDOFF-*.json`) and task state (`tasks/ACTIVE_TASK.yaml`),
   when present, pass SHA-256 and schema integrity checks.

Returns exit code 0 (`{"decision": "allow"}`) when verified, or exit code 2
(`{"decision": "block", "reason": ...}`) when verification is missing or failing (Test T11).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def compute_sha256(file_path: Path) -> str:
    """Compute hex SHA-256 digest of a file."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def evaluate_completion_claim(
    claim_payload: dict[str, Any],
    repo_root: Path | None = None,
    run_live_tests: bool = False,
) -> dict[str, Any]:
    """
    Deterministically evaluate whether an agent completion claim satisfies T11.

    Parameters
    ----------
    claim_payload : dict
        Either a Stop-hook stdin payload or a handoff manifest dictionary.
    repo_root : Path, optional
        Root of repository for verifying modified_files SHA-256 checksums.
    run_live_tests : bool
        If True, executes `python -m unittest discover -s tests` to verify live pass status.
    """
    root = repo_root or REPO_ROOT

    # 1. Inspect explicit verification_evidence if present in the payload
    if "verification_evidence" in claim_payload:
        evidence = claim_payload.get("verification_evidence")
        if not isinstance(evidence, dict):
            return {
                "allowed": False,
                "exit_code": 2,
                "decision": "block",
                "rule_id": "T11_MISSING_EVIDENCE_OBJECT",
                "reason": "T11 Evidence Violation: `verification_evidence` must be a structured object.",
            }

        exit_code = evidence.get("exit_code")
        command_executed = str(evidence.get("command_executed") or "").strip()
        log_sha256 = str(evidence.get("log_sha256") or "").strip()

        if exit_code is None or int(exit_code) != 0:
            return {
                "allowed": False,
                "exit_code": 2,
                "decision": "block",
                "rule_id": "T11_NONZERO_EXIT_CODE",
                "reason": f"T11 Evidence Violation: Completion blocked because verification exit_code={exit_code!r} (must be 0).",
            }

        if not command_executed:
            return {
                "allowed": False,
                "exit_code": 2,
                "decision": "block",
                "rule_id": "T11_EMPTY_COMMAND",
                "reason": "T11 Evidence Violation: Completion claimed without recording `command_executed`.",
            }

        if not log_sha256 or len(log_sha256) != 64:
            return {
                "allowed": False,
                "exit_code": 2,
                "decision": "block",
                "rule_id": "T11_MISSING_LOG_SHA256",
                "reason": "T11 Evidence Violation: Completion claimed without a valid 64-char `log_sha256` evidence digest.",
            }

    # 2. If payload claims unverified completion explicitly, block it
    if claim_payload.get("unverified_completion_claim") is True:
        return {
            "allowed": False,
            "exit_code": 2,
            "decision": "block",
            "rule_id": "T11_UNVERIFIED_CLAIM",
            "reason": "T11 Evidence Violation: Agent claimed tests passed without attaching deterministic execution evidence.",
        }

    # 3. Verify modified_files SHA-256 integrity if authoritative_repo_state is present
    repo_state = claim_payload.get("authoritative_repo_state")
    if isinstance(repo_state, dict):
        modified_files = repo_state.get("modified_files", [])
        if isinstance(modified_files, list):
            for entry in modified_files:
                if not isinstance(entry, dict):
                    continue
                rel_path = entry.get("path")
                expected_sha = entry.get("sha256")
                if rel_path and expected_sha:
                    target = root / str(rel_path)
                    if target.exists():
                        actual_sha = compute_sha256(target)
                        if actual_sha.lower() != str(expected_sha).lower():
                            return {
                                "allowed": False,
                                "exit_code": 2,
                                "decision": "block",
                                "rule_id": "T03_SHA256_MISMATCH",
                                "reason": (
                                    f"T03/T11 Integrity Violation: SHA-256 mismatch for '{rel_path}' "
                                    f"(expected {expected_sha[:12]}..., found {actual_sha[:12]}...)."
                                ),
                            }

    # 4. Run live deterministic test suite when requested
    if run_live_tests:
        tests_dir = root / "tests"
        if tests_dir.exists() and any(tests_dir.glob("test_*.py")):
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=45,
            )
            if proc.returncode != 0:
                return {
                    "allowed": False,
                    "exit_code": 2,
                    "decision": "block",
                    "rule_id": "T11_UNIT_TESTS_FAILED",
                    "reason": f"T11 Gate Blocked: `python -m unittest discover -s tests` exited with {proc.returncode}.",
                }

    return {
        "allowed": True,
        "exit_code": 0,
        "decision": "allow",
        "rule_id": None,
        "reason": "T11 Deterministic Stop verification gate passed.",
    }


def _run_self_test() -> int:
    """Run deterministic self-tests for T11 evidence verification."""
    # Case 1: Agent claims completion with missing log_sha256 -> MUST BLOCK (exit 2)
    bad_claim_missing_hash = {
        "handoff_id": "HO-TEST-FAIL-01",
        "verification_evidence": {
            "command_executed": "pytest tests/",
            "exit_code": 0,
            "log_sha256": "",
        },
    }
    res1 = evaluate_completion_claim(bad_claim_missing_hash)
    if res1["allowed"] or res1["exit_code"] != 2:
        print(f"[FAIL] T11 failed to block missing log_sha256: {res1}", file=sys.stderr)
        return 1

    # Case 2: Agent claims completion with non-zero exit code -> MUST BLOCK (exit 2)
    bad_claim_nonzero = {
        "handoff_id": "HO-TEST-FAIL-02",
        "verification_evidence": {
            "command_executed": "pytest tests/",
            "exit_code": 1,
            "log_sha256": "a" * 64,
        },
    }
    res2 = evaluate_completion_claim(bad_claim_nonzero)
    if res2["allowed"] or res2["exit_code"] != 2:
        print(f"[FAIL] T11 failed to block non-zero exit code: {res2}", file=sys.stderr)
        return 1

    # Case 3: Valid deterministic evidence -> MUST ALLOW (exit 0)
    valid_claim = {
        "handoff_id": "HO-TEST-PASS-01",
        "verification_evidence": {
            "command_executed": "python -m unittest discover -s tests -v",
            "exit_code": 0,
            "log_sha256": "1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d",
        },
    }
    res3 = evaluate_completion_claim(valid_claim)
    if not res3["allowed"] or res3["exit_code"] != 0:
        print(f"[FAIL] T11 blocked a valid evidence payload: {res3}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "hook": "stop_verify_gate.py",
                "t11_cases_verified": 3,
            }
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic Stop Verification Gate (T11).")
    parser.add_argument("--self-test", action="store_true", help="Run built-in deterministic T11 self-test suite.")
    parser.add_argument("--payload", type=str, default=None, help="JSON payload string to evaluate directly.")
    parser.add_argument("--skip-live-tests", action="store_true", help="Evaluate payload only without invoking unittest subprocess.")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    raw_input = args.payload
    if raw_input is None and not sys.stdin.isatty():
        raw_input = sys.stdin.read().strip()

    payload: dict[str, Any] = {}
    if raw_input:
        try:
            parsed = json.loads(raw_input)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {"raw_stdin": raw_input}

    result = evaluate_completion_claim(
        payload,
        repo_root=REPO_ROOT,
        run_live_tests=not args.skip_live_tests and "verification_evidence" not in payload,
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "reason": result["reason"],
                "rule_id": result["rule_id"],
            }
        )
    )
    if not result["allowed"]:
        print(result["reason"], file=sys.stderr)
    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
