#!/usr/bin/env python3
"""Windows 11 Non-Admin Skills Junction & Subscription Billing Guard (`CD-3` & `OD-2=2C`).

1. Ensures `.claude/skills` is linked to `.agents/skills` via a Windows NTFS Directory Junction
   (`mklink /J`) on Windows (or symlink on POSIX) without requiring Administrator elevation.
2. Verifies that global API keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
   `GOOGLE_API_KEY`) are unset in the environment (`OD-2=2C` / `PB-10` / `QW-01`) so interactive
   sessions authenticate via included subscription quotas rather than pay-as-you-go API billing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

API_ENV_VARS_TO_GUARD: List[str] = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
]


def ensure_skills_junction(workspace_root: Path) -> Dict[str, Any]:
    """Ensure `.claude/skills` points to `.agents/skills` in `workspace_root`."""
    agents_skills = (workspace_root / ".agents" / "skills").resolve()
    claude_dir = workspace_root / ".claude"
    claude_skills = claude_dir / "skills"

    if not agents_skills.exists():
        raise FileNotFoundError(f"Canonical skills directory missing: {agents_skills}")

    claude_dir.mkdir(parents=True, exist_ok=True)
    created = False

    if not claude_skills.exists():
        if os.name == "nt":
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(claude_skills), str(agents_skills)],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            claude_skills.symlink_to(agents_skills, target_is_directory=True)
        created = True

    discovered_skills = sorted(
        p.parent.name for p in claude_skills.glob("*/SKILL.md") if p.is_file()
    )
    return {
        "workspace_root": str(workspace_root),
        "claude_skills_path": str(claude_skills),
        "target_agents_skills_path": str(agents_skills),
        "junction_created": created,
        "discovered_skills": discovered_skills,
        "valid": len(discovered_skills) >= 3,
    }


def check_subscription_billing_isolation() -> Dict[str, Any]:
    """Verify OD-2=2C (QW-01 / PB-10): no stray API keys set in environment."""
    present_keys = [k for k in API_ENV_VARS_TO_GUARD if os.environ.get(k)]
    return {
        "od2_mode": "2C_SUBSCRIPTION_FIRST_ZERO_GLOBAL_API_KEYS",
        "checked_variables": API_ENV_VARS_TO_GUARD,
        "leaked_variables": present_keys,
        "clean": len(present_keys) == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure .claude/skills junction and OD-2=2C billing isolation.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Target workspace or Git worktree root.",
    )
    args = parser.parse_args()

    junction_status = ensure_skills_junction(args.workspace.resolve())
    billing_status = check_subscription_billing_isolation()

    report = {
        "status": "PASS" if (junction_status["valid"] and billing_status["clean"]) else "FAIL",
        "cd3_skills_junction": junction_status,
        "od2_billing_isolation": billing_status,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
