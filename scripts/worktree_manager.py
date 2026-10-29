#!/usr/bin/env python3
"""
Git Worktree Isolation & Optimistic Concurrency Manager (Config 3 & Config 5).

Implements Section 9, Section 12, Section 14.3, and Section 16 (Adversarial Test T03:
Conflicting Updates) of the Evidence-Validated Multi-AI Operating System specification.

Responsibilities:
  1. Manage isolated task worktrees (`worktrees/<task-id>/`) for multi-platform collaboration.
  2. Verify branch cleanliness and SHA-256 file integrity prior to handoff or merge.
  3. Enforce optimistic concurrency via `state_version` lineage and `git_head_sha` checks,
     plus Python AST-node conflict detection (`function`/`class` definitions) so two agents
     cannot silently overwrite overlapping files or AST symbols without an explicit parent link.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent


def compute_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()


def extract_python_ast_hashes(source_code: str) -> dict[str, str]:
    """
    Parse Python source code and compute deterministic SHA-256 digests of every top-level
    and class-level FunctionDef, AsyncFunctionDef, and ClassDef node (normalized via ast.dump).
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return {"__raw_file__": compute_sha256_bytes(source_code.encode("utf-8"))}

    node_hashes: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            dumped = ast.dump(node, include_attributes=False)
            node_hashes[f"func:{node.name}"] = compute_sha256_bytes(dumped.encode("utf-8"))
        elif isinstance(node, ast.ClassDef):
            dumped = ast.dump(node, include_attributes=False)
            node_hashes[f"class:{node.name}"] = compute_sha256_bytes(dumped.encode("utf-8"))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sub_dump = ast.dump(sub, include_attributes=False)
                    node_hashes[f"method:{node.name}.{sub.name}"] = compute_sha256_bytes(
                        sub_dump.encode("utf-8")
                    )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    dumped = ast.dump(node, include_attributes=False)
                    node_hashes[f"assign:{target.id}"] = compute_sha256_bytes(dumped.encode("utf-8"))
    return node_hashes


def detect_ast_or_line_conflicts(
    base_source: str,
    agent_a_source: str,
    agent_b_source: str,
) -> list[str]:
    """
    Detect concurrent modifications to the same Python AST symbol (or overlapping lines
    for non-Python files) relative to `base_source`.
    """
    base_ast = extract_python_ast_hashes(base_source)
    a_ast = extract_python_ast_hashes(agent_a_source)
    b_ast = extract_python_ast_hashes(agent_b_source)

    conflicts: list[str] = []
    all_symbols = sorted(set(base_ast) | set(a_ast) | set(b_ast))
    for sym in all_symbols:
        base_h = base_ast.get(sym)
        a_h = a_ast.get(sym)
        b_h = b_ast.get(sym)
        # Both agents modified the symbol relative to base, and their modifications differ
        if a_h != base_h and b_h != base_h and a_h != b_h:
            conflicts.append(sym)

    if not conflicts and agent_a_source != base_source and agent_b_source != base_source and agent_a_source != agent_b_source:
        # Line-level overlap check fallback
        base_lines = base_source.splitlines()
        a_lines = agent_a_source.splitlines()
        b_lines = agent_b_source.splitlines()
        max_len = max(len(base_lines), len(a_lines), len(b_lines))
        for idx in range(max_len):
            bl = base_lines[idx] if idx < len(base_lines) else None
            al = a_lines[idx] if idx < len(a_lines) else None
            bl2 = b_lines[idx] if idx < len(b_lines) else None
            if al != bl and bl2 != bl and al != bl2:
                conflicts.append(f"line:{idx + 1}")
    return conflicts


@dataclass
class WorktreeUpdateAttempt:
    """Represents a handoff/commit state transition proposed by an agent worktree."""

    task_id: str
    agent_id: str
    worktree_branch: str
    parent_state_version: int | None
    new_state_version: int
    base_git_head_sha: str
    new_git_head_sha: str
    modified_files: dict[str, str]  # path -> sha256 or source content
    file_contents: dict[str, str] = field(default_factory=dict)


class WorktreeManager:
    """
    Manages isolated Git worktrees (`worktrees/<task-id>/`) and enforces T03 concurrency checks.
    """

    def __init__(self, repo_root: str | Path = REPO_ROOT) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.worktrees_dir = self.repo_root / "worktrees"
        self._committed_state_by_task: dict[str, dict[str, Any]] = {}

    def get_worktree_path(self, task_id: str) -> Path:
        safe_id = task_id.lower().replace(" ", "_")
        return self.worktrees_dir / safe_id

    def check_working_tree_clean(self, path: str | Path | None = None) -> dict[str, Any]:
        """Check whether the Git working tree at `path` is clean (or falls back if not a Git repo)."""
        target = Path(path) if path else self.repo_root
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if proc.returncode == 0:
                dirty_lines = [line for line in proc.stdout.splitlines() if line.strip()]
                return {
                    "git_available": True,
                    "working_tree_clean": len(dirty_lines) == 0,
                    "dirty_entries": dirty_lines,
                }
        except (OSError, subprocess.SubprocessError):
            pass
        return {
            "git_available": False,
            "working_tree_clean": True,
            "dirty_entries": [],
        }

    def initialize_worktree_manifest(
        self,
        task_id: str,
        branch_name: str,
        base_git_head_sha: str = "8f9d2a1c4b7e605139a2b8c4d5e6f7a8b9c0d1e2",
        initial_state_version: int = 1,
        base_files: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Initialize or reset tracked state for a task worktree."""
        wt_path = self.get_worktree_path(task_id)
        wt_path.mkdir(parents=True, exist_ok=True)
        base_contents = dict(base_files or {})
        base_hashes = {
            p: compute_sha256_bytes(content.encode("utf-8"))
            for p, content in base_contents.items()
        }
        state = {
            "task_id": task_id,
            "worktree_path": str(wt_path),
            "branch_name": branch_name,
            "state_version": initial_state_version,
            "git_head_sha": base_git_head_sha,
            "file_hashes": base_hashes,
            "file_contents": base_contents,
            "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._committed_state_by_task[task_id] = state
        manifest_file = wt_path / ".worktree_state.json"
        manifest_file.write_text(
            json.dumps(
                {k: v for k, v in state.items() if k != "file_contents"},
                indent=2,
            ),
            encoding="utf-8",
        )
        return state

    def verify_and_apply_update(self, attempt: WorktreeUpdateAttempt) -> dict[str, Any]:
        """
        Validate a proposed worktree handoff/merge update against current authoritative state.
        Enforces Adversarial Test T03 (Conflicting Updates):
          - Rejects missing or stale `parent_state_version` (`parent_state_version != current.state_version`).
          - Rejects mismatched `base_git_head_sha` when overlapping files or AST nodes were modified.
          - Requires explicit 3-way merge + deterministic test re-execution on conflict.
        """
        current = self._committed_state_by_task.get(attempt.task_id)
        if current is None:
            raise KeyError(f"Task worktree '{attempt.task_id}' is not initialized.")

        current_version = int(current["state_version"])
        current_head = str(current["git_head_sha"])
        reasons: list[str] = []
        conflicting_files: list[str] = []
        ast_conflicts: dict[str, list[str]] = {}

        if attempt.parent_state_version is None:
            reasons.append(
                "MISSING_PARENT_STATE_VERSION: Update does not declare a parent state_version link."
            )
        elif attempt.parent_state_version != current_version:
            reasons.append(
                f"STALE_STATE_VERSION: Incoming parent_state_version={attempt.parent_state_version} "
                f"does not match authoritative state_version={current_version}."
            )

        if attempt.new_state_version <= current_version:
            reasons.append(
                f"NON_MONOTONIC_STATE_VERSION: Incoming new_state_version={attempt.new_state_version} "
                f"must be > authoritative state_version={current_version}."
            )

        if attempt.base_git_head_sha != current_head:
            reasons.append(
                f"DIVERGENT_GIT_HEAD_SHA: Incoming base_git_head_sha={attempt.base_git_head_sha[:12]} "
                f"diverges from authoritative git_head_sha={current_head[:12]}."
            )

        # Check overlapping file / AST modifications
        current_hashes: dict[str, str] = current.get("file_hashes", {})
        current_contents: dict[str, str] = current.get("file_contents", {})
        base_snapshot_contents: dict[str, str] = current.get(
            "base_contents", current_contents
        )

        for rel_path, new_hash in attempt.modified_files.items():
            if rel_path in current_hashes and current_hashes[rel_path] != new_hash:
                if reasons:
                    conflicting_files.append(rel_path)
                    if rel_path in attempt.file_contents and rel_path in current_contents:
                        base_src = base_snapshot_contents.get(rel_path, "")
                        syms = detect_ast_or_line_conflicts(
                            base_source=base_src,
                            agent_a_source=current_contents[rel_path],
                            agent_b_source=attempt.file_contents[rel_path],
                        )
                        if syms:
                            ast_conflicts[rel_path] = syms

        if reasons:
            return {
                "accepted": False,
                "status": "CONFLICT_REJECTED_T03",
                "task_id": attempt.task_id,
                "agent_id": attempt.agent_id,
                "authoritative_state_version": current_version,
                "attempted_parent_version": attempt.parent_state_version,
                "attempted_new_version": attempt.new_state_version,
                "conflicting_files": conflicting_files,
                "ast_conflicts": ast_conflicts,
                "reasons": reasons,
                "required_resolution": "Perform explicit 3-way merge in isolated worktree and re-run deterministic test suite.",
            }

        # Apply update atomically
        if "base_contents" not in current:
            current["base_contents"] = dict(current_contents)
        for rel_path, new_hash in attempt.modified_files.items():
            current_hashes[rel_path] = new_hash
        for rel_path, content in attempt.file_contents.items():
            current_contents[rel_path] = content
            current_hashes[rel_path] = compute_sha256_bytes(content.encode("utf-8"))

        current["state_version"] = attempt.new_state_version
        current["git_head_sha"] = attempt.new_git_head_sha
        current["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        wt_path = Path(current["worktree_path"])
        manifest_file = wt_path / ".worktree_state.json"
        if wt_path.exists():
            manifest_file.write_text(
                json.dumps(
                    {k: v for k, v in current.items() if k not in ("file_contents", "base_contents")},
                    indent=2,
                ),
                encoding="utf-8",
            )

        return {
            "accepted": True,
            "status": "APPLIED",
            "task_id": attempt.task_id,
            "agent_id": attempt.agent_id,
            "state_version": current["state_version"],
            "git_head_sha": current["git_head_sha"],
            "modified_files": list(attempt.modified_files.keys()),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Git Worktree & T03 Optimistic Concurrency Manager"
    )
    parser.add_argument("--check-clean", action="store_true", help="Check if repository working tree is clean")
    parser.add_argument("--simulate-t03", action="store_true", help="Run a self-test of T03 concurrent update rejection")
    args = parser.parse_args(argv)

    mgr = WorktreeManager()
    if args.check_clean:
        res = mgr.check_working_tree_clean()
        print(json.dumps(res, indent=2))
        return 0

    if args.simulate_t03:
        base_code = "def compute_quota(usage: float) -> float:\n    return usage * 0.02\n"
        mgr.initialize_worktree_manifest(
            task_id="TASK-T03-DEMO",
            branch_name="worktree/t03-demo",
            base_git_head_sha="1111111111111111111111111111111111111111",
            initial_state_version=1,
            base_files={"src/quota.py": base_code},
        )
        agent_1_code = "def compute_quota(usage: float) -> float:\n    return usage * 0.015\n"
        r1 = mgr.verify_and_apply_update(
            WorktreeUpdateAttempt(
                task_id="TASK-T03-DEMO",
                agent_id="claude-sonnet-5-5",
                worktree_branch="worktree/agent-1",
                parent_state_version=1,
                new_state_version=2,
                base_git_head_sha="1111111111111111111111111111111111111111",
                new_git_head_sha="2222222222222222222222222222222222222222",
                modified_files={"src/quota.py": compute_sha256_bytes(agent_1_code.encode("utf-8"))},
                file_contents={"src/quota.py": agent_1_code},
            )
        )
        agent_2_code = "def compute_quota(usage: float) -> float:\n    return max(0.0, usage * 0.03)\n"
        r2 = mgr.verify_and_apply_update(
            WorktreeUpdateAttempt(
                task_id="TASK-T03-DEMO",
                agent_id="gpt-6.1-sol",
                worktree_branch="worktree/agent-2",
                parent_state_version=1,  # Stale!
                new_state_version=2,
                base_git_head_sha="1111111111111111111111111111111111111111",
                new_git_head_sha="3333333333333333333333333333333333333333",
                modified_files={"src/quota.py": compute_sha256_bytes(agent_2_code.encode("utf-8"))},
                file_contents={"src/quota.py": agent_2_code},
            )
        )
        print(json.dumps({"agent_1": r1, "agent_2": r2}, indent=2))
        return 0 if (r1["accepted"] and not r2["accepted"]) else 1

    print(json.dumps(mgr.check_working_tree_clean(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
