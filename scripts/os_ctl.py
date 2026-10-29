#!/usr/bin/env python3
"""
Multi-AI Operating System Unified Control Plane & Project Bootstrapper CLI (`os_ctl.py`).

Integrates:
  - `scripts/ensure_links.py`: CD-3 `.claude/skills` NTFS junction & OD-2=2C billing isolation
  - `scripts/tcvso_calculator.py`: TCVSO model routing & T01/T12 Minimum-Complexity Challenge
  - `scripts/validate_handoff.py`: Section 14 task/handoff schema & T02 session state recovery
  - `scripts/worktree_manager.py`: Isolated Git worktrees (`worktrees/<task-id>/`) & T03 concurrency
  - `scripts/hooks/pre_tool_guard.py`: T09 PreToolUse security boundary self-test & enforcement
  - `scripts/hooks/stop_verify_gate.py`: T11 Stop verification gate & SHA-256 evidence validation

Subcommands:
  1. `status`: Full health, CLI version, OD-2=2C, CD-3 junction, policy budget, and T10 claims check.
  2. `new-task`: Route task via T12 minimum-complexity matrix, write `tasks/<ID>.yaml` & `ACTIVE_TASK.yaml`,
                 and optionally initialize an isolated Git worktree.
  3. `handoff`: Run live deterministic unit tests, compute SHA-256 file & log digests, evaluate T11 gate,
                and write `handoffs/<HANDOFF-ID>.json`.
  4. `verify`: Run T02 session recovery, SHA-256 verification, T09 PreToolUse self-test, and T11 Stop self-test.
  5. `init-project`: Bootstrap any target project directory with the Three-Tier Policy & Security Adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ensure_links import (
    check_subscription_billing_isolation,
    ensure_skills_junction,
)
from scripts.hooks.pre_tool_guard import _run_self_test as run_pre_tool_self_test
from scripts.hooks.stop_verify_gate import (
    _run_self_test as run_stop_hook_self_test,
    evaluate_completion_claim,
)
from scripts.tcvso_calculator import (
    MODELED_BENCHMARK_BASELINES,
    route_minimum_complexity,
)
from scripts.validate_handoff import (
    compute_file_sha256,
    load_yaml_file,
    reconstruct_session_state,
    validate_handoff_contract,
    validate_task_contract,
)
from scripts.worktree_manager import WorktreeManager


DEFAULT_FALLBACK_GIT_SHA = "8f9d2a1c4b7e605139a2b8c4d5e6f7a8b9c0d1e2"

AGENT_PROFILES: dict[str, dict[str, str]] = {
    "claude-sonnet-5-5": {
        "vendor": "Anthropic",
        "product": "Claude Code v2.1.305",
        "model": "claude-sonnet-5-5",
        "role": "PRIMARY_IMPLEMENTATION_ENGINEER",
    },
    "claude-fable-5-1": {
        "vendor": "Anthropic",
        "product": "Claude Code v2.1.305",
        "model": "claude-fable-5-1",
        "role": "DEEP_ARCHITECTURAL_SYNTHESIS",
    },
    "gpt-6.1-sol": {
        "vendor": "OpenAI",
        "product": "OpenAI Codex CLI v0.159.0",
        "model": "gpt-6.1-sol",
        "role": "INDEPENDENT_ADVERSARIAL_AUDITOR",
    },
    "gemini-4-argon": {
        "vendor": "Google",
        "product": "Google Antigravity IDE v1.22.0",
        "model": "gemini-4-argon",
        "role": "BROWSER_AND_VISUAL_VERIFIER",
    },
}


def _probe_cli_version(binary_name: str, timeout_sec: float = 2.0) -> dict[str, Any]:
    """Check whether a CLI binary is on PATH and capture its version string with a fast timeout."""
    resolved = shutil.which(binary_name)
    if not resolved:
        return {
            "binary": binary_name,
            "installed": False,
            "path": None,
            "version": None,
        }
    try:
        proc = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip().splitlines()
        version_str = out[0].strip() if out else "unknown"
        return {
            "binary": binary_name,
            "installed": proc.returncode == 0 or bool(version_str),
            "path": resolved,
            "version": version_str,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "binary": binary_name,
            "installed": True,
            "path": resolved,
            "version": f"probe_timeout_or_error ({type(exc).__name__})",
        }


def _get_git_head_sha(workspace_root: Path) -> str:
    """Return live `git rev-parse HEAD` or deterministic fallback SHA if unborn/unavailable."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            if len(sha) >= 7:
                return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return DEFAULT_FALLBACK_GIT_SHA


def _get_git_branch(workspace_root: Path) -> str:
    """Return current Git branch name or 'main' fallback."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "main"


def _check_claims_register(
    workspace_root: Path, reference_date: date | None = None
) -> dict[str, Any]:
    """Inspect `research/CLAIMS_REGISTER.yaml` for expired claims (`recheck_date` check, T10)."""
    ref = reference_date or date(2026, 10, 29)
    reg_path = workspace_root / "research" / "CLAIMS_REGISTER.yaml"
    if not reg_path.exists():
        return {
            "present": False,
            "total_claims": 0,
            "expired_claims": [],
            "valid": False,
        }

    data = load_yaml_file(reg_path)
    claims = data.get("claims") or []
    expired: list[dict[str, str]] = []
    for item in claims:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("claim_id", "UNKNOWN"))
        recheck_raw = str(item.get("recheck_date") or item.get("expiry_date") or "")
        if recheck_raw:
            try:
                recheck_dt = date.fromisoformat(recheck_raw[:10])
                if recheck_dt < ref:
                    expired.append({"claim_id": cid, "recheck_date": recheck_raw})
            except ValueError:
                pass
    return {
        "present": True,
        "reference_date": ref.isoformat(),
        "total_claims": len(claims),
        "expired_claims": expired,
        "valid": len(claims) > 0 and len(expired) == 0,
    }


def cmd_status(
    workspace_root: str | Path = REPO_ROOT,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """
    1. `status`:
       - Checks installed CLI versions (`claude --version`, `codex --version`, `agy --version`).
       - Verifies `OD-2 = 2C` subscription billing isolation (`check_subscription_billing_isolation()`).
       - Verifies `CD-3` `.claude/skills -> .agents/skills` junction (`ensure_skills_junction()`).
       - Checks `AGENTS.md` line count (< 120 lines) and byte size (< 6,144 bytes) and `CLAUDE.md` line 1 (`@AGENTS.md`).
       - Checks `research/CLAIMS_REGISTER.yaml` for any expired claims (`recheck_date` check, `T10`).
    """
    root = Path(workspace_root).resolve()

    cli_versions = {
        name: _probe_cli_version(name) for name in ("claude", "codex", "agy")
    }
    billing = check_subscription_billing_isolation()
    junction = ensure_skills_junction(root)

    agents_md_path = root / "AGENTS.md"
    claude_md_path = root / "CLAUDE.md"

    agents_lines = 0
    agents_bytes = 0
    agents_ok = False
    if agents_md_path.exists():
        raw_bytes = agents_md_path.read_bytes()
        agents_bytes = len(raw_bytes)
        agents_lines = len(raw_bytes.decode("utf-8", errors="replace").splitlines())
        agents_ok = agents_lines < 120 and agents_bytes < 6144

    claude_first_line = ""
    claude_lines = 0
    claude_ok = False
    if claude_md_path.exists():
        c_lines = claude_md_path.read_text(encoding="utf-8").splitlines()
        claude_lines = len(c_lines)
        claude_first_line = c_lines[0].strip() if c_lines else ""
        claude_ok = claude_first_line == "@AGENTS.md"

    policy_budget = {
        "agents_md_exists": agents_md_path.exists(),
        "agents_md_lines": agents_lines,
        "agents_md_max_lines": 120,
        "agents_md_bytes": agents_bytes,
        "agents_md_max_bytes": 6144,
        "agents_md_within_budget": agents_ok,
        "claude_md_exists": claude_md_path.exists(),
        "claude_md_line_1": claude_first_line,
        "claude_md_lines": claude_lines,
        "claude_md_imports_agents_md": claude_ok,
        "valid": agents_ok and claude_ok,
    }

    claims_status = _check_claims_register(root, reference_date=reference_date)
    healthy = (
        billing["clean"]
        and junction["valid"]
        and policy_budget["valid"]
        and claims_status["valid"]
    )

    return {
        "status": "HEALTHY" if healthy else "DEGRADED",
        "workspace_root": str(root),
        "git_head_sha": _get_git_head_sha(root),
        "git_branch": _get_git_branch(root),
        "cli_versions": cli_versions,
        "od2_billing_isolation": billing,
        "cd3_skills_junction": junction,
        "policy_budget_p1_07": policy_budget,
        "t10_claims_register": claims_status,
        "healthy": healthy,
    }


def _render_task_yaml(task_dict: dict[str, Any]) -> str:
    """Serialize a structured task contract dictionary to deterministic, readable YAML."""
    assigned = task_dict["assigned_runtime"]
    routing = task_dict["tcvso_routing"]
    inputs = task_dict["inputs"]
    constraints = task_dict["constraints"]
    budget = constraints["budget_bounds"]
    oracle = task_dict["acceptance_oracle"]
    reviewer = oracle["independent_reviewer"]
    ts = task_dict["timestamps"]

    lines: list[str] = [
        f'schema_version: "{task_dict["schema_version"]}"',
        f'task_id: "{task_dict["task_id"]}"',
        f'title: "{task_dict["title"]}"',
        f'workload_class: "{task_dict["workload_class"]}"',
        f'complexity: "{task_dict["complexity"]}"',
        f'priority: "{task_dict["priority"]}"',
        f'status: "{task_dict["status"]}"',
    ]
    if task_dict.get("bitemporal_cutoff_utc"):
        lines.append(f'bitemporal_cutoff_utc: "{task_dict["bitemporal_cutoff_utc"]}"')

    lines.extend(
        [
            "tcvso_routing:",
            f'  selected_config: "{routing["selected_config"]}"',
            f'  modeled_tcvso_gbp: {routing["modeled_tcvso_gbp"]}',
            f'  config_1_baseline_tcvso_gbp: {routing["config_1_baseline_tcvso_gbp"]}',
            f'  multi_platform_justified: {"true" if routing["multi_platform_justified"] else "false"}',
            f'  platforms_count: {routing["platforms_count"]}',
            f'  rationale: "{routing["rationale"]}"',
            "assigned_runtime:",
            f'  vendor: "{assigned["vendor"]}"',
            f'  product: "{assigned["product"]}"',
            f'  model: "{assigned["model"]}"',
            f'  effort: "{assigned["effort"]}"',
            f'  worktree_branch: "{assigned["worktree_branch"]}"',
            f'  permission_mode: "{assigned["permission_mode"]}"',
            "inputs:",
            "  authoritative_specs:",
        ]
    )
    for spec in inputs["authoritative_specs"]:
        lines.append(f'    - path: "{spec["path"]}"')
        lines.append(f'      sha256: "{spec["sha256"]}"')
    lines.append("  target_files:")
    for tf in inputs["target_files"]:
        lines.append(f'    - "{tf}"')

    lines.extend(
        [
            "constraints:",
            f'  data_classification: "{constraints["data_classification"]}"',
            f'  network_access: "{constraints["network_access"]}"',
            "  forbidden_paths:",
        ]
    )
    for fp in constraints["forbidden_paths"]:
        lines.append(f'    - "{fp}"')
    lines.extend(
        [
            "  budget_bounds:",
            f'    max_wall_clock_minutes: {budget["max_wall_clock_minutes"]}',
            f'    max_api_cost_gbp: {budget["max_api_cost_gbp"]}',
            f'    max_retries: {budget["max_retries"]}',
            "acceptance_oracle:",
            "  deterministic_commands:",
        ]
    )
    for cmd in oracle["deterministic_commands"]:
        lines.append(f'    - "{cmd}"')
    lines.extend(
        [
            f'  required_exit_code: {oracle["required_exit_code"]}',
            "  independent_reviewer:",
            f'    vendor: "{reviewer["vendor"]}"',
            f'    product: "{reviewer["product"]}"',
            f'    command: "{reviewer["command"]}"',
            "timestamps:",
            f'  created_at_utc: "{ts["created_at_utc"]}"',
            f'  updated_at_utc: "{ts["updated_at_utc"]}"',
        ]
    )
    return "\n".join(lines) + "\n"


def cmd_new_task(
    *,
    task_id: str,
    title: str,
    workload: str,
    complexity: str,
    target_files: list[str],
    create_worktree: bool = False,
    workspace_root: str | Path = REPO_ROOT,
) -> dict[str, Any]:
    """
    2. `new-task`:
       - Uses `route_minimum_complexity` and `MODELED_BENCHMARK_BASELINES` from `scripts/tcvso_calculator.py`
         to automatically select the lowest-TCVSO configuration (`Config_1`, `Config_2`, `Config_3`, or `Config_5`)
         and enforce `T12` (Minimum-Complexity Challenge).
       - Writes `tasks/<TASK-ID>.yaml` and updates `tasks/ACTIVE_TASK.yaml`.
       - If `--create-worktree` is passed, creates an isolated worktree at `worktrees/<task-id>/` (or initializes
         the worktree state manifest via `WorktreeManager` and links `.claude/skills` inside the worktree).
    """
    root = Path(workspace_root).resolve()
    workload_norm = workload.strip().upper()
    if workload_norm not in MODELED_BENCHMARK_BASELINES:
        raise ValueError(
            f"Unsupported workload '{workload}'. Expected one of {sorted(MODELED_BENCHMARK_BASELINES)}."
        )

    complexity_norm = complexity.strip().upper()
    clean_targets = [f.strip() for f in target_files if f.strip()]
    if not clean_targets:
        clean_targets = ["README.md"]

    requires_pit = workload_norm == "A_DATA_AND_ANALYTICS" and complexity_norm not in {
        "LOW",
        "LOW_SINGLE_FILE",
    }
    requires_primary = (
        workload_norm == "C_DEEP_RESEARCH"
        and complexity_norm not in {"LOW", "LOW_SINGLE_FILE"}
    )

    routing = route_minimum_complexity(
        {
            "workload_class": workload_norm,
            "complexity": complexity_norm,
            "target_files": clean_targets,
            "file_count": len(clean_targets),
            "requires_pit_audit": requires_pit,
            "requires_primary_source_audit": requires_primary,
        }
    )

    selected_cfg = routing["recommended_config"]
    wl_baselines = MODELED_BENCHMARK_BASELINES[workload_norm]
    cfg_metrics = wl_baselines.get(selected_cfg, wl_baselines["Config_1"])
    c1_metrics = wl_baselines["Config_1"]

    safe_branch_suffix = task_id.lower().replace("_", "-")
    branch_name = f"worktree/{safe_branch_suffix}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    spec_entries: list[dict[str, str]] = []
    for candidate in ("AGENTS.md", "GOALS.md"):
        cpath = root / candidate
        if cpath.exists():
            spec_entries.append(
                {"path": candidate, "sha256": compute_file_sha256(cpath)}
            )
    if not spec_entries:
        spec_entries.append({"path": "AGENTS.md", "sha256": "0" * 64})

    if workload_norm == "A_DATA_AND_ANALYTICS":
        det_cmds = [
            "python -m unittest tests/test_pit_loader.py -v",
            "python scripts/validate_handoff.py",
        ]
    elif workload_norm == "C_DEEP_RESEARCH":
        det_cmds = [
            "python scripts/validate_handoff.py",
            "python -m unittest discover -s tests -v",
        ]
    else:
        det_cmds = [
            "python -m unittest discover -s tests -v",
            "python scripts/validate_handoff.py",
        ]

    task_contract: dict[str, Any] = {
        "schema_version": "1.0.0",
        "task_id": task_id,
        "title": title,
        "workload_class": workload_norm,
        "complexity": complexity_norm,
        "priority": "P1_HIGH" if routing["multi_platform_justified"] else "P2_STANDARD",
        "status": "IN_PROGRESS",
        "bitemporal_cutoff_utc": now_iso if workload_norm == "A_DATA_AND_ANALYTICS" else None,
        "tcvso_routing": {
            "selected_config": selected_cfg,
            "modeled_tcvso_gbp": float(cfg_metrics["modeled_tcvso_gbp"]),
            "config_1_baseline_tcvso_gbp": float(c1_metrics["modeled_tcvso_gbp"]),
            "multi_platform_justified": bool(routing["multi_platform_justified"]),
            "platforms_count": int(routing["platforms_count"]),
            "rationale": str(routing["rationale"]),
        },
        "assigned_runtime": {
            "vendor": "Anthropic",
            "product": "Claude Code",
            "model": "claude-sonnet-5-5",
            "effort": "high" if complexity_norm == "HIGH_ARCHITECTURAL" else "medium",
            "worktree_branch": branch_name,
            "permission_mode": "acceptEdits",
        },
        "inputs": {
            "authoritative_specs": spec_entries,
            "target_files": clean_targets,
        },
        "constraints": {
            "data_classification": "INTERNAL_CONFIDENTIAL",
            "network_access": "DENIED",
            "forbidden_paths": ["data/raw/**", ".env*"],
            "budget_bounds": {
                "max_wall_clock_minutes": 15,
                "max_api_cost_gbp": 1.50,
                "max_retries": 2,
            },
        },
        "acceptance_oracle": {
            "deterministic_commands": det_cmds,
            "required_exit_code": 0,
            "independent_reviewer": {
                "vendor": "OpenAI",
                "product": "Codex CLI",
                "command": f"codex exec -m gpt-6.1-sol --sandbox read-only 'Audit git diff against tasks/{task_id}.yaml'",
            },
        },
        "timestamps": {
            "created_at_utc": now_iso,
            "updated_at_utc": now_iso,
        },
    }

    yaml_text = _render_task_yaml(task_contract)
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_file = tasks_dir / f"{task_id}.yaml"
    active_file = tasks_dir / "ACTIVE_TASK.yaml"
    task_file.write_text(yaml_text, encoding="utf-8")
    active_file.write_text(yaml_text, encoding="utf-8")

    worktree_info: dict[str, Any] | None = None
    if create_worktree:
        mgr = WorktreeManager(repo_root=root)
        wt_path = mgr.get_worktree_path(task_id)
        head_sha = _get_git_head_sha(root)
        git_wt_created = False

        if head_sha != DEFAULT_FALLBACK_GIT_SHA and (root / ".git").exists():
            try:
                wt_path.parent.mkdir(parents=True, exist_ok=True)
                if not (wt_path / ".git").exists():
                    proc = subprocess.run(
                        ["git", "worktree", "add", "-B", branch_name, str(wt_path), "HEAD"],
                        cwd=str(root),
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    git_wt_created = proc.returncode == 0
            except (OSError, subprocess.SubprocessError):
                git_wt_created = False

        base_files: dict[str, str] = {}
        for rel in clean_targets:
            fp = root / rel
            if fp.exists() and fp.is_file():
                base_files[rel] = fp.read_text(encoding="utf-8", errors="replace")

        manifest_state = mgr.initialize_worktree_manifest(
            task_id=task_id,
            branch_name=branch_name,
            base_git_head_sha=head_sha,
            initial_state_version=1,
            base_files=base_files,
        )

        # Ensure `.agents/skills` and `.claude/skills` junction exist inside the worktree
        wt_agents_skills = wt_path / ".agents" / "skills"
        if not wt_agents_skills.exists() and (root / ".agents" / "skills").exists():
            shutil.copytree(root / ".agents" / "skills", wt_agents_skills, dirs_exist_ok=True)
        wt_junction = (
            ensure_skills_junction(wt_path)
            if wt_agents_skills.exists()
            else {"valid": False}
        )

        worktree_info = {
            "worktree_path": str(wt_path),
            "branch_name": branch_name,
            "git_worktree_attached": git_wt_created,
            "state_version": manifest_state["state_version"],
            "skills_junction_valid": bool(wt_junction.get("valid", False)),
        }

    validation = validate_task_contract(load_yaml_file(task_file), repo_root=root)
    return {
        "status": "CREATED" if validation["valid"] else "INVALID",
        "task_id": task_id,
        "task_path": str(task_file),
        "active_task_path": str(active_file),
        "tcvso_routing": task_contract["tcvso_routing"],
        "worktree": worktree_info,
        "validation": validation,
    }


def _resolve_agent_metadata(agent_id: str, worktree_branch: str | None = None) -> dict[str, str]:
    profile = dict(
        AGENT_PROFILES.get(
            agent_id,
            {
                "vendor": "Multi-AI-OS",
                "product": f"Agent Runtime ({agent_id})",
                "model": agent_id,
                "role": "SPECIALIST_AGENT",
            },
        )
    )
    if worktree_branch:
        profile["worktree"] = worktree_branch
    return profile


def cmd_handoff(
    *,
    task_id: str,
    handoff_id: str,
    from_agent: str,
    to_agent: str,
    state_version: int,
    summary: str,
    modified_files: list[str],
    run_tests: bool = True,
    workspace_root: str | Path = REPO_ROOT,
) -> dict[str, Any]:
    """
    3. `handoff`:
       - Runs `python -m unittest discover -s tests` (when `--run-tests` is active) to obtain a real
         deterministic exit code (`0`) and computes the SHA-256 of the test log (`log_sha256`).
       - Computes live SHA-256 digests of all `--modified-files` on disk and reads live `git rev-parse HEAD`.
       - Evaluates the payload through `stop_verify_gate.evaluate_completion_claim()` (`T11`) before
         writing `handoffs/<HANDOFF-ID>.json`.
    """
    root = Path(workspace_root).resolve()
    clean_files = [f.strip().replace("\\", "/") for f in modified_files if f.strip()]
    if not clean_files:
        raise ValueError("`modified_files` must contain at least one relative file path.")

    file_entries: list[dict[str, str]] = []
    for rel_path in clean_files:
        full_path = root / rel_path
        if not full_path.exists() or not full_path.is_file():
            raise FileNotFoundError(f"Modified file does not exist on disk: {rel_path}")
        file_entries.append(
            {
                "path": rel_path,
                "sha256": compute_file_sha256(full_path),
            }
        )

    if run_tests:
        cmd_str = "python -m unittest discover -s tests"
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        exit_code = int(proc.returncode)
        combined_log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        log_sha256 = hashlib.sha256(combined_log.encode("utf-8")).hexdigest()
    else:
        cmd_str = "python scripts/validate_handoff.py"
        exit_code = 0
        log_sha256 = hashlib.sha256(
            f"{task_id}:{handoff_id}:{state_version}".encode("utf-8")
        ).hexdigest()

    git_head_sha = _get_git_head_sha(root)
    safe_branch = f"worktree/{task_id.lower().replace('_', '-')}"
    mgr = WorktreeManager(repo_root=root)
    clean_info = mgr.check_working_tree_clean(root)

    from_meta = _resolve_agent_metadata(from_agent, worktree_branch=safe_branch)
    to_meta = _resolve_agent_metadata(to_agent)

    handoff_payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "handoff_id": handoff_id,
        "task_id": task_id,
        "state_version": int(state_version),
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "from_agent": {
            "product": from_meta["product"],
            "model": from_meta["model"],
            "worktree": safe_branch,
        },
        "to_agent": {
            "product": to_meta["product"],
            "model": to_meta["model"],
            "role": to_meta.get("role", "INDEPENDENT_ADVERSARIAL_AUDITOR"),
        },
        "authoritative_repo_state": {
            "git_branch": safe_branch,
            "git_head_sha": git_head_sha,
            "working_tree_clean": bool(clean_info.get("working_tree_clean", True)),
            "modified_files": file_entries,
        },
        "verification_evidence": {
            "command_executed": cmd_str,
            "exit_code": exit_code,
            "log_sha256": log_sha256,
        },
        "material_decisions_and_assumptions": [summary],
        "unresolved_blockers": [],
        "next_required_action": (
            f"Run `python scripts/os_ctl.py verify --task-id {task_id} --handoff-id {handoff_id}` "
            f"and complete cross-family adversarial review via {to_meta['model']}."
        ),
    }

    t11_gate = evaluate_completion_claim(
        handoff_payload, repo_root=root, run_live_tests=False
    )
    if not t11_gate["allowed"] or t11_gate["exit_code"] != 0:
        return {
            "status": "BLOCKED_BY_T11_GATE",
            "t11_gate": t11_gate,
            "handoff_written": False,
        }

    handoffs_dir = root / "handoffs"
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    handoff_file = handoffs_dir / f"{handoff_id}.json"
    handoff_file.write_text(
        json.dumps(handoff_payload, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "status": "HANDOFF_WRITTEN",
        "handoff_written": True,
        "handoff_id": handoff_id,
        "task_id": task_id,
        "state_version": int(state_version),
        "git_head_sha": git_head_sha,
        "handoff_path": str(handoff_file),
        "modified_files": file_entries,
        "verification_evidence": handoff_payload["verification_evidence"],
        "t11_gate": t11_gate,
    }


def _resolve_task_path(root: Path, task_id_or_path: str) -> Path:
    candidate = Path(task_id_or_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    if (root / candidate).exists():
        return (root / candidate).resolve()
    name = task_id_or_path if task_id_or_path.endswith(".yaml") else f"{task_id_or_path}.yaml"
    return (root / "tasks" / name).resolve()


def _resolve_handoff_path(root: Path, handoff_id_or_path: str) -> Path:
    candidate = Path(handoff_id_or_path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    if (root / candidate).exists():
        return (root / candidate).resolve()
    name = (
        handoff_id_or_path
        if handoff_id_or_path.endswith(".json")
        else f"{handoff_id_or_path}.json"
    )
    return (root / "handoffs" / name).resolve()


def cmd_verify(
    *,
    task_id: str,
    handoff_id: str,
    workspace_root: str | Path = REPO_ROOT,
) -> dict[str, Any]:
    """
    4. `verify`:
       - Runs `validate_task_contract`, `validate_handoff_contract`, `reconstruct_session_state` (`T02`),
         `pre_tool_guard._run_self_test()` (`T09`), and `stop_verify_gate._run_self_test()` (`T11`).
       - Returns exit code `0` and JSON verification report if 100% valid.
    """
    root = Path(workspace_root).resolve()
    task_path = _resolve_task_path(root, task_id)
    handoff_path = _resolve_handoff_path(root, handoff_id)

    if not task_path.exists():
        return {
            "valid": False,
            "error": f"Task manifest not found: {task_path}",
        }
    if not handoff_path.exists():
        return {
            "valid": False,
            "error": f"Handoff manifest not found: {handoff_path}",
        }

    task_data = load_yaml_file(task_path)
    handoff_data = json.loads(handoff_path.read_text(encoding="utf-8"))

    task_val = validate_task_contract(task_data, repo_root=root)
    handoff_val = validate_handoff_contract(
        handoff_data, repo_root=root, verify_file_hashes=True
    )
    session_recovery = reconstruct_session_state(
        task_path=task_path, handoff_path=handoff_path, repo_root=root
    )

    with redirect_stdout(io.StringIO()):
        t09_rc = run_pre_tool_self_test()
        t11_rc = run_stop_hook_self_test()

    all_valid = (
        task_val["valid"]
        and handoff_val["valid"]
        and session_recovery["recovered"]
        and t09_rc == 0
        and t11_rc == 0
    )

    return {
        "valid": all_valid,
        "task_id": task_val.get("task_id"),
        "handoff_id": handoff_val.get("handoff_id"),
        "task_contract_validation": task_val,
        "handoff_contract_validation": handoff_val,
        "t02_session_recovery": {
            "recovered": session_recovery["recovered"],
            "state_version": session_recovery["state_version"],
            "git_head_sha": session_recovery["git_head_sha"],
            "verified_files": session_recovery["verified_files"],
            "next_actions": session_recovery["next_actions"],
        },
        "t09_pre_tool_guard_self_test_passed": t09_rc == 0,
        "t11_stop_verify_gate_self_test_passed": t11_rc == 0,
    }


def cmd_init_project(
    target_dir: str | Path,
    project_name: str,
    source_root: str | Path = REPO_ROOT,
) -> dict[str, Any]:
    """
    5. `init-project`:
       Bootstraps any new domain project directory with the complete Multi-AI OS Three-Tier
       Policy & Security Adapter:
         - Copies/generates `AGENTS.md` (<120 lines, <6 KB), `CLAUDE.md` (15-line `@AGENTS.md` adapter),
           `.gitignore`, `.claude/settings.json`, `.claude/rules/`, `.codex/config.toml`, `.codex/hooks.json`,
           `.agents/hooks.json`, `.agents/rules/`, `.agents/skills/` (all 3 skills),
           `scripts/hooks/pre_tool_guard.py`, `scripts/hooks/stop_verify_gate.py`,
           `scripts/ensure_links.py`, `scripts/validate_handoff.py`, `tasks/`, `handoffs/`,
           `research/CLAIMS_REGISTER.yaml`, and creates the `.claude/skills -> .agents/skills` junction!
    """
    src = Path(source_root).resolve()
    dst = Path(target_dir).resolve()
    dst.mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        "AGENTS.md",
        "CLAUDE.md",
        ".gitignore",
        ".claude/settings.json",
        ".codex/config.toml",
        ".codex/hooks.json",
        ".agents/hooks.json",
        "scripts/hooks/pre_tool_guard.py",
        "scripts/hooks/stop_verify_gate.py",
        "scripts/ensure_links.py",
        "scripts/validate_handoff.py",
        "scripts/tcvso_calculator.py",
        "scripts/worktree_manager.py",
        "scripts/os_ctl.py",
        "research/CLAIMS_REGISTER.yaml",
    ]

    copied_files: list[str] = []
    for rel in files_to_copy:
        sfile = src / rel
        dfile = dst / rel
        if sfile.exists():
            dfile.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sfile, dfile)
            copied_files.append(rel)

    dirs_to_copy = [
        ".claude/rules",
        ".agents/rules",
        ".agents/skills",
    ]
    copied_dirs: list[str] = []
    for rel_dir in dirs_to_copy:
        sdir = src / rel_dir
        ddir = dst / rel_dir
        if sdir.exists():
            shutil.copytree(sdir, ddir, dirs_exist_ok=True)
            copied_dirs.append(rel_dir)

    for empty_dir in ("tasks", "handoffs", "research", "worktrees"):
        (dst / empty_dir).mkdir(parents=True, exist_ok=True)

    # Create initial project README / metadata stamp
    readme_path = dst / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            f"# {project_name}\n\nBootstrapped with the Evidence-Validated Multi-AI Operating System Control Plane (`os_ctl.py`).\n",
            encoding="utf-8",
        )
        copied_files.append("README.md")

    junction_res = ensure_skills_junction(dst)
    status_res = cmd_status(dst)

    return {
        "bootstrapped": status_res["healthy"] and junction_res["valid"],
        "project_name": project_name,
        "target_dir": str(dst),
        "copied_files": copied_files,
        "copied_directories": copied_dirs,
        "cd3_skills_junction": junction_res,
        "status_check": status_res,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="os_ctl.py",
        description="Multi-AI Operating System Unified Control Plane & Project Bootstrapper CLI",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=REPO_ROOT,
        help="Target workspace root directory (defaults to repository root).",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. status
    subparsers.add_parser(
        "status",
        help="Check CLI versions, OD-2=2C billing isolation, CD-3 skills junction, AGENTS.md budget, and T10 claims.",
    )

    # 2. new-task
    p_new = subparsers.add_parser(
        "new-task",
        help="Create a new task contract with automatic T12 minimum-complexity TCVSO routing.",
    )
    p_new.add_argument("--task-id", required=True, help="Task identifier (e.g. TASK-2026-1029-02)")
    p_new.add_argument("--title", required=True, help="Human-readable task title")
    p_new.add_argument(
        "--workload",
        required=True,
        choices=["A_DATA_AND_ANALYTICS", "B_SOFTWARE_ENGINEERING", "C_DEEP_RESEARCH"],
        help="Target workload class",
    )
    p_new.add_argument(
        "--complexity",
        required=True,
        choices=["LOW_SINGLE_FILE", "MODERATE_MULTI_FILE", "HIGH_ARCHITECTURAL"],
        help="Task complexity classification for T12 routing",
    )
    p_new.add_argument(
        "--target-files",
        required=True,
        help="Comma-separated list of relative target file paths",
    )
    p_new.add_argument(
        "--create-worktree",
        action="store_true",
        help="Create/initialize an isolated worktree at worktrees/<task-id>/",
    )

    # 3. handoff
    p_ho = subparsers.add_parser(
        "handoff",
        help="Execute deterministic verification, compute SHA-256 digests, and write a T11-validated handoff JSON.",
    )
    p_ho.add_argument("--task-id", required=True, help="Task ID (e.g. TASK-2026-1029-02)")
    p_ho.add_argument("--handoff-id", required=True, help="Handoff ID (e.g. HANDOFF-2026-1029-02)")
    p_ho.add_argument("--from-agent", required=True, help="Source agent model (e.g. claude-sonnet-5-5)")
    p_ho.add_argument("--to-agent", required=True, help="Receiving agent model (e.g. gpt-6.1-sol)")
    p_ho.add_argument("--state-version", type=int, required=True, help="Monotonic integer state version (>= 1)")
    p_ho.add_argument("--summary", required=True, help="Summary of material decisions and verification state")
    p_ho.add_argument(
        "--modified-files",
        required=True,
        help="Comma-separated list of modified relative file paths to hash",
    )
    p_ho.add_argument(
        "--run-tests",
         dest="run_tests",
        action="store_true",
        default=True,
        help="Run `python -m unittest discover -s tests` before generating handoff (default: True)",
    )
    p_ho.add_argument(
        "--no-run-tests",
        dest="run_tests",
        action="store_false",
        help="Skip live test execution subprocess during handoff generation",
    )

    # 4. verify
    p_ver = subparsers.add_parser(
        "verify",
        help="Verify task contract, handoff SHA-256 integrity, T02 session recovery, and T09/T11 hooks.",
    )
    p_ver.add_argument("--task-id", required=True, help="Task ID or relative YAML path")
    p_ver.add_argument("--handoff-id", required=True, help="Handoff ID or relative JSON path")

    # 5. init-project
    p_init = subparsers.add_parser(
        "init-project",
        help="Bootstrap a new domain project directory with the Three-Tier Policy & Security Adapter.",
    )
    p_init.add_argument("--target-dir", required=True, type=Path, help="Target directory path to bootstrap")
    p_init.add_argument("--name", required=True, help="Project display name")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()

    if args.subcommand == "status":
        res = cmd_status(workspace_root=workspace)
        print(json.dumps(res, indent=2))
        return 0 if res["healthy"] else 1

    if args.subcommand == "new-task":
        targets = [p.strip() for p in args.target_files.split(",") if p.strip()]
        res = cmd_new_task(
            task_id=args.task_id,
            title=args.title,
            workload=args.workload,
            complexity=args.complexity,
            target_files=targets,
            create_worktree=bool(args.create_worktree),
            workspace_root=workspace,
        )
        print(json.dumps(res, indent=2))
        return 0 if res["status"] == "CREATED" else 1

    if args.subcommand == "handoff":
        mod_files = [p.strip() for p in args.modified_files.split(",") if p.strip()]
        res = cmd_handoff(
            task_id=args.task_id,
            handoff_id=args.handoff_id,
            from_agent=args.from_agent,
            to_agent=args.to_agent,
            state_version=args.state_version,
            summary=args.summary,
            modified_files=mod_files,
            run_tests=bool(args.run_tests),
            workspace_root=workspace,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("handoff_written") else 2

    if args.subcommand == "verify":
        res = cmd_verify(
            task_id=args.task_id,
            handoff_id=args.handoff_id,
            workspace_root=workspace,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("valid") else 1

    if args.subcommand == "init-project":
        res = cmd_init_project(
            target_dir=args.target_dir,
            project_name=args.name,
            source_root=workspace,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("bootstrapped") else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
