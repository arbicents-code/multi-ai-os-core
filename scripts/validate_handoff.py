#!/usr/bin/env python3
"""
Cross-Platform Task & Handoff Validator and 4-Tier Evidence Hierarchy Oracle.

Implements Section 11, Section 14.2, Section 14.3, and Section 16 (T02, T03, T04, T11)
of the Evidence-Validated Multi-AI Operating System specification.

Features:
  1. Zero-dependency YAML + JSON parser compatible with Python 3.15 standard library.
  2. Schema validation for `tasks/*.yaml` and `handoffs/*.json` supporting both Section 14
     nested contracts (`authoritative_repo_state`, `acceptance_oracle`, `constraints.budget_bounds`)
     and flat operational contracts (`bitemporal_cutoff_utc`, `acceptance_criteria`,
     `verification_commands`, `budget_breaker`, `git_head_sha`, `modified_files`,
     `open_risks`, `next_actions`).
  3. Live cryptographic SHA-256 file digest verification and `--sync-hashes` auto-stamping.
  4. Deterministic 4-Tier Evidence Hierarchy Oracle (`adjudicate_evidence_hierarchy`) that
     enforces Level 1 deterministic execution supremacy over unanimous LLM agreement (T04).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def _parse_scalar(val: str) -> Any:
    val = val.strip()
    if not val:
        return ""
    # Strip inline comments outside quotes
    if not (val.startswith('"') or val.startswith("'")):
        hash_idx = val.find(" #")
        if hash_idx != -1:
            val = val[:hash_idx].strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    low = val.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none", "~"):
        return None
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        parts = [p.strip() for p in inner.split(",")]
        return [_parse_scalar(p) for p in parts]
    if val.startswith("{") and val.endswith("}"):
        try:
            return json.loads(val)
        except ValueError:
            pass
    try:
        if "." in val or "e" in low:
            return float(val)
        return int(val)
    except ValueError:
        return val


def parse_yaml_text(text: str) -> dict[str, Any]:
    """
    Lightweight, deterministic zero-dependency YAML parser for `tasks/*.yaml`,
    `benchmarks/REGISTRY.yaml`, `research/CLAIMS_REGISTER.yaml`, and `docs/WORK_RECORD_*.yaml`.
    """
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            return loaded
    except ImportError:
        pass

    stripped = text.strip()
    if stripped.startswith("{"):
        return dict(json.loads(stripped))

    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))

    def _parse_block(idx: int, min_indent: int) -> tuple[Any, int]:
        if idx >= len(lines):
            return {}, idx
        first_indent, first_content = lines[idx]
        if first_indent < min_indent:
            return {}, idx

        if first_content.startswith("- ") or first_content == "-":
            items: list[Any] = []
            while idx < len(lines):
                ind, content = lines[idx]
                if ind < first_indent:
                    break
                if ind != first_indent or not (content.startswith("- ") or content == "-"):
                    break
                after_dash = content[1:].strip()
                idx += 1
                if not after_dash:
                    sub_val, idx = _parse_block(idx, first_indent + 1)
                    items.append(sub_val)
                elif ":" in after_dash and not (after_dash.startswith('"') or after_dash.startswith("'")):
                    # Inline dict item start: `- key: val`
                    k, _, v_part = after_dash.partition(":")
                    k = k.strip().strip('"').strip("'")
                    v_part = v_part.strip()
                    item_dict: dict[str, Any] = {}
                    if v_part:
                        item_dict[k] = _parse_scalar(v_part)
                    else:
                        sub_val, idx = _parse_block(idx, first_indent + 2)
                        item_dict[k] = sub_val
                    # Read additional keys indented inside this list item
                    while idx < len(lines):
                        sub_ind, sub_c = lines[idx]
                        if sub_ind <= first_indent:
                            break
                        if sub_c.startswith("- "):
                            break
                        sk, _, sv = sub_c.partition(":")
                        sk = sk.strip().strip('"').strip("'")
                        sv = sv.strip()
                        idx += 1
                        if sv:
                            item_dict[sk] = _parse_scalar(sv)
                        else:
                            nested_val, idx = _parse_block(idx, sub_ind + 1)
                            item_dict[sk] = nested_val
                    items.append(item_dict)
                else:
                    items.append(_parse_scalar(after_dash))
            return items, idx

        mapping: dict[str, Any] = {}
        while idx < len(lines):
            ind, content = lines[idx]
            if ind < first_indent:
                break
            if content.startswith("- ") or content == "-":
                break
            if ":" not in content:
                idx += 1
                continue
            key, _, rest = content.partition(":")
            key = key.strip().strip('"').strip("'")
            rest = rest.strip()
            idx += 1
            if rest:
                mapping[key] = _parse_scalar(rest)
            else:
                sub_val, idx = _parse_block(idx, ind + 1)
                mapping[key] = sub_val
        return mapping, idx

    parsed, _ = _parse_block(0, 0)
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def load_yaml_file(path: str | Path) -> dict[str, Any]:
    return parse_yaml_text(Path(path).read_text(encoding="utf-8"))


def compute_file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_task_contract(
    task_data: dict[str, Any],
    repo_root: str | Path = REPO_ROOT,
    verify_spec_hashes: bool = False,
) -> dict[str, Any]:
    """
    Validate a task manifest (`tasks/*.yaml`) against Section 14.2 & operational contracts.
    Checks required fields:
      - `task_id`
      - `workload_class`
      - `bitemporal_cutoff_utc` (top-level or in `inputs`/`constraints`, required for Workload A or if present)
      - `acceptance_criteria` or `inputs`/`title`
      - `verification_commands` or `acceptance_oracle.deterministic_commands`
      - `budget_breaker` or `constraints.budget_bounds`
    """
    root = Path(repo_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    task_id = task_data.get("task_id")
    if not task_id or not isinstance(task_id, str):
        errors.append("Missing or invalid required field: 'task_id'")

    workload_class = task_data.get("workload_class")
    if not workload_class or not isinstance(workload_class, str):
        errors.append("Missing or invalid required field: 'workload_class'")

    # Check bitemporal_cutoff_utc
    cutoff = (
        task_data.get("bitemporal_cutoff_utc")
        or (task_data.get("inputs") or {}).get("bitemporal_cutoff_utc")
        or (task_data.get("constraints") or {}).get("bitemporal_cutoff_utc")
    )
    if str(workload_class or "").startswith("A") and not cutoff:
        # Check if task_data explicitly omitted bitemporal_cutoff_utc in strict mode
        if "bitemporal_cutoff_utc" not in task_data and "inputs" not in task_data:
            errors.append("Missing required field for Workload A task: 'bitemporal_cutoff_utc'")

    # Check acceptance_criteria
    has_acceptance_criteria = bool(
        task_data.get("acceptance_criteria")
        or task_data.get("acceptance_oracle")
        or (task_data.get("inputs") or {}).get("authoritative_specs")
    )
    if not has_acceptance_criteria:
        errors.append("Missing required field: 'acceptance_criteria' (or 'acceptance_oracle')")

    # Check verification_commands
    ver_cmds = task_data.get("verification_commands") or (
        (task_data.get("acceptance_oracle") or {}).get("deterministic_commands")
    )
    if not ver_cmds or not isinstance(ver_cmds, list) or len(ver_cmds) == 0:
        errors.append(
            "Missing or empty required field: 'verification_commands' (or 'acceptance_oracle.deterministic_commands')"
        )

    # Check budget_breaker / budget_bounds
    budget = task_data.get("budget_breaker") or (
        (task_data.get("constraints") or {}).get("budget_bounds")
    )
    if not budget or not isinstance(budget, dict):
        errors.append("Missing required field: 'budget_breaker' (or 'constraints.budget_bounds')")

    if verify_spec_hashes:
        specs = (task_data.get("inputs") or {}).get("authoritative_specs") or []
        for spec in specs:
            if isinstance(spec, dict) and "path" in spec and "sha256" in spec:
                fpath = root / str(spec["path"])
                if not fpath.exists():
                    errors.append(f"Authoritative spec file not found: {spec['path']}")
                else:
                    live_sha = compute_file_sha256(fpath)
                    if live_sha != spec["sha256"]:
                        warnings.append(
                            f"Authoritative spec SHA-256 mismatch on {spec['path']}: "
                            f"expected {spec['sha256'][:12]}..., got {live_sha[:12]}..."
                        )

    return {
        "valid": len(errors) == 0,
        "task_id": task_id,
        "workload_class": workload_class,
        "errors": errors,
        "warnings": warnings,
    }


def _extract_modified_files_list(handoff_data: dict[str, Any]) -> list[dict[str, Any]]:
    repo_state = handoff_data.get("authoritative_repo_state")
    if isinstance(repo_state, dict) and isinstance(repo_state.get("modified_files"), list):
        return repo_state["modified_files"]
    if isinstance(handoff_data.get("modified_files"), list):
        return handoff_data["modified_files"]
    return []


def sync_handoff_hashes(
    handoff_path: str | Path,
    task_path: str | Path | None = None,
    repo_root: str | Path = REPO_ROOT,
) -> dict[str, Any]:
    """
    Compute live SHA-256 digests of every modified file in `handoff_path` (and spec files in
    `task_path` if provided) and write updated hashes to disk.
    """
    root = Path(repo_root).resolve()
    hpath = Path(handoff_path).resolve()
    handoff_data = json.loads(hpath.read_text(encoding="utf-8"))

    updated_files: dict[str, str] = {}

    def _update_entry_list(entries: list[Any]) -> None:
        for entry in entries:
            if isinstance(entry, dict) and "path" in entry:
                rel = str(entry["path"])
                full = root / rel
                if full.exists() and full.is_file():
                    digest = compute_file_sha256(full)
                    entry["sha256"] = digest
                    updated_files[rel] = digest

    if isinstance(handoff_data.get("modified_files"), list):
        _update_entry_list(handoff_data["modified_files"])

    repo_state = handoff_data.get("authoritative_repo_state")
    if isinstance(repo_state, dict) and isinstance(repo_state.get("modified_files"), list):
        _update_entry_list(repo_state["modified_files"])

    ver_ev = handoff_data.get("verification_evidence")
    if isinstance(ver_ev, dict) and ver_ev.get("log_artifact_path"):
        log_full = root / str(ver_ev["log_artifact_path"])
        if log_full.exists() and log_full.is_file():
            ver_ev["log_sha256"] = compute_file_sha256(log_full)

    hpath.write_text(json.dumps(handoff_data, indent=2) + "\n", encoding="utf-8")

    # Optionally update authoritative_specs sha256 in task YAML if present
    for candidate_tpath in filter(None, [task_path, root / "tasks" / "ACTIVE_TASK.yaml"]):
        tpath = Path(candidate_tpath).resolve()
        if not tpath.exists():
            continue
        raw_yaml = tpath.read_text(encoding="utf-8")
        for spec_rel in ("GOALS.md", "data/pit_store/schema.sql"):
            spec_full = root / spec_rel
            if spec_full.exists() and spec_rel in raw_yaml:
                spec_sha = compute_file_sha256(spec_full)
                escaped_rel = re.escape(spec_rel)
                raw_yaml = re.sub(
                    rf'(path:\s*"{escaped_rel}"\s*\r?\n\s*sha256:\s*")[0-9a-fA-F]{{64}}(")',
                    rf"\g<1>{spec_sha}\2",
                    raw_yaml,
                )
        tpath.write_text(raw_yaml, encoding="utf-8")

    return {
        "synced": True,
        "handoff_path": str(hpath),
        "updated_file_hashes": updated_files,
    }


def validate_handoff_contract(
    handoff_data: dict[str, Any],
    repo_root: str | Path = REPO_ROOT,
    verify_file_hashes: bool = True,
    expected_min_state_version: int | None = None,
) -> dict[str, Any]:
    """
    Validate `handoffs/*.json` against Section 14.3 schema and cryptographic SHA-256 digests.
    Verifies required fields:
      - `handoff_id`
      - `task_id`
      - `state_version` (integer >= 1)
      - `from_agent`
      - `to_agent`
      - `git_head_sha` (top-level or in `authoritative_repo_state.git_head_sha`)
      - `modified_files` (top-level or in `authoritative_repo_state.modified_files`)
      - `verification_evidence` (with `exit_code == 0`)
      - `open_risks` or `unresolved_blockers`
      - `next_actions` or `next_required_action`
    """
    root = Path(repo_root).resolve()
    errors: list[str] = []
    hash_mismatches: list[dict[str, str]] = []
    verified_files: list[str] = []

    handoff_id = handoff_data.get("handoff_id")
    if not handoff_id or not isinstance(handoff_id, str):
        errors.append("Missing required field: 'handoff_id'")

    task_id = handoff_data.get("task_id")
    if not task_id or not isinstance(task_id, str):
        errors.append("Missing required field: 'task_id'")

    state_version = handoff_data.get("state_version")
    if not isinstance(state_version, int) or isinstance(state_version, bool) or state_version < 1:
        errors.append("Missing or invalid integer field: 'state_version' (must be >= 1)")
    elif expected_min_state_version is not None and state_version < expected_min_state_version:
        errors.append(
            f"Stale state_version={state_version}; expected >= {expected_min_state_version} (T03 violation)"
        )

    if not isinstance(handoff_data.get("from_agent"), dict):
        errors.append("Missing required object field: 'from_agent'")
    if not isinstance(handoff_data.get("to_agent"), dict):
        errors.append("Missing required object field: 'to_agent'")

    repo_state = handoff_data.get("authoritative_repo_state") or {}
    git_head_sha = handoff_data.get("git_head_sha") or repo_state.get("git_head_sha")
    if not git_head_sha or not isinstance(git_head_sha, str) or len(git_head_sha.strip()) < 7:
        errors.append("Missing or invalid required field: 'git_head_sha'")

    modified_files = _extract_modified_files_list(handoff_data)
    if not modified_files:
        errors.append("Missing or empty required field: 'modified_files'")

    ver_ev = handoff_data.get("verification_evidence")
    if not isinstance(ver_ev, dict):
        errors.append("Missing required object field: 'verification_evidence'")
    else:
        exit_code = ver_ev.get("exit_code")
        if exit_code != 0:
            errors.append(
                f"Verification evidence exit_code must be 0 before handoff, got {exit_code!r} (T11 violation)"
            )
        cmd_exec = ver_ev.get("command_executed") or ver_ev.get("commands_executed")
        if not cmd_exec:
            errors.append("Missing 'command_executed' in 'verification_evidence' (T11 violation)")

    has_open_risks = "open_risks" in handoff_data or "unresolved_blockers" in handoff_data
    if not has_open_risks:
        errors.append("Missing required field: 'open_risks' (or 'unresolved_blockers')")

    has_next_actions = bool(
        handoff_data.get("next_actions") or handoff_data.get("next_required_action")
    )
    if not has_next_actions:
        errors.append("Missing required field: 'next_actions' (or 'next_required_action')")

    if verify_file_hashes and modified_files:
        for item in modified_files:
            if not isinstance(item, dict) or "path" not in item or "sha256" not in item:
                errors.append(f"Invalid modified_files entry (requires 'path' and 'sha256'): {item!r}")
                continue
            rel_path = str(item["path"])
            expected_sha = str(item["sha256"]).lower().strip()
            file_path = root / rel_path
            if not file_path.exists():
                errors.append(f"Modified file does not exist on disk: {rel_path}")
                hash_mismatches.append(
                    {"path": rel_path, "expected": expected_sha, "actual": "MISSING_FILE"}
                )
            else:
                actual_sha = compute_file_sha256(file_path)
                if actual_sha != expected_sha:
                    errors.append(
                        f"SHA-256 mismatch for {rel_path}: expected {expected_sha[:12]}..., got {actual_sha[:12]}..."
                    )
                    hash_mismatches.append(
                        {"path": rel_path, "expected": expected_sha, "actual": actual_sha}
                    )
                else:
                    verified_files.append(rel_path)

    return {
        "valid": len(errors) == 0,
        "handoff_id": handoff_id,
        "task_id": task_id,
        "state_version": state_version,
        "git_head_sha": git_head_sha,
        "verified_files": verified_files,
        "hash_mismatches": hash_mismatches,
        "errors": errors,
    }


def reconstruct_session_state(
    task_path: str | Path,
    handoff_path: str | Path,
    repo_root: str | Path = REPO_ROOT,
) -> dict[str, Any]:
    """
    Reconstruct complete session state solely from `tasks/*.yaml` and `handoffs/*.json`
    after process termination or `/clear` (Adversarial Test T02: Context Continuity Recovery).
    """
    task_data = load_yaml_file(task_path)
    handoff_data = json.loads(Path(handoff_path).read_text(encoding="utf-8"))

    task_val = validate_task_contract(task_data, repo_root=repo_root)
    handoff_val = validate_handoff_contract(handoff_data, repo_root=repo_root, verify_file_hashes=True)

    decisions = (
        handoff_data.get("material_decisions_and_assumptions")
        or handoff_data.get("material_decisions")
        or []
    )
    next_actions = (
        handoff_data.get("next_actions")
        or (
            [handoff_data["next_required_action"]]
            if handoff_data.get("next_required_action")
            else []
        )
    )
    open_risks = handoff_data.get("open_risks", handoff_data.get("unresolved_blockers", []))

    return {
        "recovered": task_val["valid"] and handoff_val["valid"],
        "task_id": task_data.get("task_id"),
        "handoff_id": handoff_data.get("handoff_id"),
        "state_version": handoff_data.get("state_version"),
        "git_head_sha": handoff_val["git_head_sha"],
        "verified_files": handoff_val["verified_files"],
        "material_decisions": decisions,
        "open_risks": open_risks,
        "next_actions": next_actions,
        "task_validation": task_val,
        "handoff_validation": handoff_val,
    }


def adjudicate_evidence_hierarchy(
    *,
    llm_votes: list[dict[str, Any]],
    level_1_deterministic_oracle: dict[str, Any] | None = None,
    level_2_primary_source: dict[str, Any] | None = None,
    level_3_rival_hypothesis: str | None = None,
) -> dict[str, Any]:
    """
    Enforce the Section 11 Four-Tier Evidence Hierarchy Oracle (and Adversarial Test T04:
    False Consensus Trap).

    Hierarchy:
      - Level 1 (Highest Authority): Deterministic execution oracle (pytest/unittest exit code,
        DuckDB/SQLite PIT invariance check, SHA-256 checksum). Overrides unanimous LLM consensus 100% of the time.
      - Level 2: Primary vendor/technical documentation with verified URL and timestamp.
      - Level 3: Cross-family adversarial review with an explicit rival/falsification hypothesis.
      - Level 4: Human Arbitration Gate when Level 2/3 remain unresolved.
    """
    unanimous_llm_approve = len(llm_votes) > 0 and all(
        bool(v.get("approves_claim", False)) for v in llm_votes
    )
    llm_families = sorted({str(v.get("vendor_family", v.get("model", "unknown"))) for v in llm_votes})

    # Level 1 check
    if level_1_deterministic_oracle is not None:
        l1_passed = bool(level_1_deterministic_oracle.get("passed", False))
        l1_metric = level_1_deterministic_oracle.get("oracle_value")
        if not l1_passed:
            return {
                "final_decision": "REJECTED_BY_LEVEL_1_ORACLE",
                "winning_tier": "LEVEL_1_DETERMINISTIC_EXECUTION",
                "llm_unanimous_approval_overruled": unanimous_llm_approve,
                "llm_families_evaluated": llm_families,
                "oracle_value": l1_metric,
                "reason": (
                    "Level 1 deterministic oracle failed and automatically overruled "
                    f"{len(llm_votes)} concurring LLM vote(s) (P1-12 / T04 protection)."
                ),
            }
        return {
            "final_decision": "VERIFIED_BY_LEVEL_1_ORACLE",
            "winning_tier": "LEVEL_1_DETERMINISTIC_EXECUTION",
            "llm_unanimous_approval_overruled": False,
            "llm_families_evaluated": llm_families,
            "oracle_value": l1_metric,
            "reason": "Level 1 deterministic execution oracle passed.",
        }

    # Level 2 check
    if level_2_primary_source is not None:
        has_url = bool(level_2_primary_source.get("primary_url"))
        has_date = bool(level_2_primary_source.get("verified_date"))
        supports = bool(level_2_primary_source.get("supports_claim", False))
        if has_url and has_date:
            return {
                "final_decision": "VERIFIED_BY_LEVEL_2_PRIMARY_SOURCE"
                if supports
                else "REJECTED_BY_LEVEL_2_PRIMARY_SOURCE",
                "winning_tier": "LEVEL_2_PRIMARY_SOURCE",
                "llm_unanimous_approval_overruled": (unanimous_llm_approve and not supports),
                "llm_families_evaluated": llm_families,
                "reason": f"Adjudicated via primary source {level_2_primary_source['primary_url']}.",
            }

    # Level 3 check: requires >= 2 distinct vendor families AND explicit rival hypothesis
    if len(llm_families) >= 2 and level_3_rival_hypothesis and level_3_rival_hypothesis.strip():
        return {
            "final_decision": "PROVISIONAL_LEVEL_3_ADVERSARIAL_CONSENSUS"
            if unanimous_llm_approve
            else "ESCALATE_TO_LEVEL_4_HUMAN_ARBITRATION",
            "winning_tier": "LEVEL_3_CROSS_FAMILY_ADVERSARIAL"
            if unanimous_llm_approve
            else "LEVEL_4_HUMAN_ARBITRATION_GATE",
            "llm_unanimous_approval_overruled": False,
            "llm_families_evaluated": llm_families,
            "reason": "Cross-family adversarial review evaluated with explicit rival hypothesis.",
        }

    # Level 4 fallback
    return {
        "final_decision": "BLOCKED_PENDING_LEVEL_4_HUMAN_ARBITRATION",
        "winning_tier": "LEVEL_4_HUMAN_ARBITRATION_GATE",
        "llm_unanimous_approval_overruled": unanimous_llm_approve,
        "llm_families_evaluated": llm_families,
        "reason": "No Level 1/2 oracle or cross-family rival hypothesis provided; escalated to human operator.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Multi-AI OS Task YAML & Handoff JSON contracts (Section 14)"
    )
    parser.add_argument(
        "--task",
        type=str,
        default="tasks/TASK-2026-1028-01.yaml",
        help="Path to task YAML manifest",
    )
    parser.add_argument(
        "--handoff",
        type=str,
        default="handoffs/HANDOFF-2026-1028-01.json",
        help="Path to handoff JSON manifest",
    )
    parser.add_argument(
        "--sync-hashes",
        action="store_true",
        help="Compute live SHA-256 digests for modified_files and write them into the handoff JSON",
    )
    args = parser.parse_args(argv)

    task_path = REPO_ROOT / args.task
    handoff_path = REPO_ROOT / args.handoff

    if args.sync_hashes and handoff_path.exists():
        sync_res = sync_handoff_hashes(
            handoff_path=handoff_path,
            task_path=task_path if task_path.exists() else None,
            repo_root=REPO_ROOT,
        )
        print(json.dumps(sync_res, indent=2))

    if not task_path.exists():
        print(json.dumps({"valid": False, "error": f"Task file not found: {task_path}"}))
        return 1
    if not handoff_path.exists():
        print(json.dumps({"valid": False, "error": f"Handoff file not found: {handoff_path}"}))
        return 1

    state = reconstruct_session_state(task_path, handoff_path, repo_root=REPO_ROOT)
    print(json.dumps(state, indent=2))
    return 0 if state["recovered"] else 1


if __name__ == "__main__":
    sys.exit(main())
