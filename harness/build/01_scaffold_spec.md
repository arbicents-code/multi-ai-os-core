# Phase 01: Repository Scaffold, Three-Tier Policy Adapter & Sandbox Specification

**Phase Classification:** `PLANNING_AND_SCAFFOLD_ONLY` (OpenAI Codex Staged Build Pattern — Section 7.2 & 14.1)  
**Target Configuration:** Config 1 (Solo Baseline) -> Config 3/5 (Two-Platform Shared Git Worktree)  
**Authoritative Spec Reference:** `Multi-AI Operating System Programme.md` Sections 8, 9, 12, 14, 15

---

## 1. Objective

Establish the foundational directory hierarchy, the Three-Tier Authoritative Policy & Adapter Architecture (`./AGENTS.md`, `./CLAUDE.md`, `.agents/skills/`, `.claude/skills/`), and the deterministic OS/harness security boundaries (`.claude/settings.json`, `.codex/config.toml`, `.codex/hooks.json`, `.agents/hooks.json`) before any application or analytical code is written.

## 2. Hard Invariants (Non-Negotiable)

1. **Instruction Exclusivity Resolution (P1-07):**
   - Root `./AGENTS.md` is the single authoritative repository policy (`< 120` lines, `< 6 KB`).
   - Root `./CLAUDE.md` is a thin 15-line adapter whose first line is `@AGENTS.md`, preventing Claude Code from ignoring `AGENTS.md` when `CLAUDE.md` is present.
   - All Antigravity rules in `.agents/rules/*.md` reside in a flat directory and begin with valid YAML frontmatter declaring a `snake_case` trigger (`always_on`, `model_decision`, `glob`, or `manual`).
2. **Upfront Security Posture (P1-08, T09):**
   - OS sandboxing defaults to `workspace-write` with network disabled.
   - `approval_policy = "untrusted"` is strictly forbidden in `.codex/config.toml` (retired setting; use project-scoped `trust_level = "untrusted"` where needed and `approval_policy = "on-request"`).
   - Deterministic `PreToolUse` hooks (`scripts/hooks/pre_tool_guard.py`) enforce hard exit-code `2` blocks on `.env*`, `~/.ssh/**`, `~/.aws/**`, `data/raw/**`, `git push --force`, `rm -rf`, and live production mutation endpoints.
3. **Authoritative State Ownership (P1-09):**
   - Conversation histories, platform memories, and vector indexes are non-authoritative caches.
   - All durable state lives in `tasks/*.yaml`, `handoffs/*.json`, `harness/context/*.md`, and `docs/WORK_RECORD_*.yaml`.

## 3. Deliverables & Acceptance Gate (Gate 1A)

- [x] Root `./AGENTS.md`, `./CLAUDE.md`, and `./GOALS.md` created and within byte/line budgets.
- [x] `.claude/settings.json`, `.codex/config.toml`, `.codex/hooks.json`, `.agents/hooks.json`, and `.agents/rules/*.md` configured.
- [x] `scripts/hooks/pre_tool_guard.py`, `scripts/hooks/pytest_trim_filter.py`, and `scripts/hooks/stop_verify_gate.py` executable and verified against Adversarial Test **T09** and **T11**.
