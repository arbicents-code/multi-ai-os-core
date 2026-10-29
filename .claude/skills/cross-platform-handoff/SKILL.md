---
name: cross-platform-handoff
description: Generates, updates, and cryptographically verifies portable task contracts (tasks/TASK-*.yaml) and cross-platform handoff manifests (handoffs/HANDOFF-*.json) across Anthropic Claude Code, OpenAI Codex, and Google Antigravity for stateless session recovery (Test T02) and concurrent edit protection (Test T03).
---

# Cross-Platform Handoff & Stateless Recovery Skill

Use this skill before running `/clear`, ending a worktree session, recovering from an interrupted session (**T02**), or handing an implementation across model families (e.g., Claude Code -> OpenAI Codex `gpt-6.1-sol` `/review` or Google Antigravity `/browser`).

## 1. Handoff Generation Protocol (Outgoing Agent)

1. **Run Deterministic Acceptance Oracle First (T11):**
   - Execute the required unit/integration tests defined in `tasks/ACTIVE_TASK.yaml` (`acceptance_oracle.deterministic_commands`).
   - Capture the exit code and log output. Do NOT generate a `READY_FOR_REVIEW` or `VERIFIED_COMPLETE` handoff if `exit_code != 0`.

2. **Compute Authoritative Repository State (T03):**
   - Record current branch and `git_head_sha` (`git rev-parse HEAD`).
   - Compute exact `sha256` checksums for every modified file listed in `authoritative_repo_state.modified_files`.
   - Increment `state_version` monotonically (`state_version = previous + 1`).

3. **Write Handoff Manifest (`handoffs/HANDOFF-<ID>.json`):**
   - Populate `schema_version` (`"1.0.0"`), `handoff_id`, `task_id`, `state_version`, `created_at_utc`, `from_agent`, `to_agent`, `authoritative_repo_state`, `verification_evidence`, `material_decisions_and_assumptions`, `unresolved_blockers`, and `next_required_action`.
   - Update `tasks/ACTIVE_TASK.yaml` to point to the latest `handoff_id` and `state_version`.

4. **Validate Handoff Deterministically:**
   ```powershell
   python scripts/validate_handoff.py
   ```

## 2. Stateless Session Recovery & Audit Protocol (Incoming Agent — T02 / T03)

1. **Never Trust Narrative Summaries Alone:**
   - Before reading conversational notes or `material_decisions_and_assumptions`, run `python scripts/validate_handoff.py` to verify that every file in `modified_files` exists on disk and matches its declared `sha256` digest.
2. **Detect Concurrent Edit Collisions (T03):**
   - Compare the handoff's `state_version` and `git_head_sha` against the target branch. If a concurrent agent modified overlapping files or advanced `state_version`, halt automatic merge and trigger a 3-way worktree diff + full test re-run.
3. **Reconstruct Context in <= 2.0 Minutes (T02):**
   - Load `tasks/ACTIVE_TASK.yaml` and the latest `handoffs/HANDOFF-<ID>.json`, verify `verification_evidence.exit_code == 0`, and proceed with `next_required_action`.
