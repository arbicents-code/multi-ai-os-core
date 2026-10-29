@AGENTS.md

# Compact instructions
When running /compact or auto-compaction, you MUST preserve verbatim in the compaction summary:
1. Active Task Contract ID (`tasks/ACTIVE_TASK.yaml` or `tasks/TASK-*.yaml`) and current `state_version`.
2. Exact SHA-256 checksums and file paths of all modified files in the active worktree.
3. Most recent deterministic test and linter exit codes and failing traceback lines (`pytest`, `dotnet run`, `mypy`).
4. Active bitemporal `cutoff_ts` (UTC `TIMESTAMPTZ`) and `pit_as_of(cutoff_ts)` state invariants for Workload A.
5. Primary-source URLs, `verified_date`, and `claim_id` references from `research/CLAIMS_REGISTER.yaml`.
6. Material architectural decisions and unresolved blockers required for stateless session recovery (T02).

# Claude Code Runtime Overrides
- Size-Gated Context Rule (PB-06): Use `@path/to/file` for known target files <5,000 tokens; use bare paths for files >=5,000 tokens.
- Prompt Cache Preservation (PB-02/PB-04): Keep single-model `claude-sonnet-5-5` across Plan Mode and execution on <4-turn tasks; never export global `ANTHROPIC_API_KEY`.
- Agent Teams Disabled (PB-09): Keep `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=0`; use `--worktree` isolation for parallel tasks.