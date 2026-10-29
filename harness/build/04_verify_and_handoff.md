# Phase 04: Deterministic Verification Gate, Cross-Platform Handoff & Adversarial Audit

**Phase Classification:** `VERIFICATION_AND_HANDOFF`  
**Target Configuration:** Config 3 & Config 5 (Cross-Family Adversarial Verification)  
**Authoritative Spec Reference:** `Multi-AI Operating System Programme.md` Sections 11, 14.2, 14.3, 16 (T01–T12)

---

## 1. Objective

Execute the 4-Tier Evidence Hierarchy Oracle, validate task and handoff manifests (`tasks/*.yaml`, `handoffs/*.json`), synchronize live cryptographic SHA-256 digests across modified artifacts, and run the complete T01–T12 adversarial test suite before permitting branch merge.

## 2. Verification & Handoff Protocol

1. **Deterministic Stop Gate (`scripts/hooks/stop_verify_gate.py` — T11):**
   - Runs `acceptance_oracle.deterministic_commands` (or `verification_commands`) defined in `tasks/TASK-<ID>.yaml`.
   - Blocks task completion (`{"decision": "block"}`) if any test fails or if `verification_evidence.exit_code != 0`.
2. **Handoff Schema & Cryptographic Digest Verification (`scripts/validate_handoff.py` — T02, T03):**
   - Validates `tasks/TASK-2026-1028-01.yaml` and `handoffs/HANDOFF-2026-1028-01.json` against Section 14 schemas.
   - Verifies that every file in `modified_files` exists on disk and its live SHA-256 digest matches the handoff manifest.
   - Enforces monotonic `state_version` progression and parent commit lineage via `scripts/worktree_manager.py` (preventing T03 silent concurrent overwrites).
3. **Cross-Family Adversarial Audit (Level 3 Oracle — T04):**
   - Receiving auditor agent (e.g., OpenAI Codex `gpt-6.1-sol` or Google Antigravity `/browser`) verifies disk hashes first, generates an explicit **Rival Explanation / Falsification Hypothesis**, and executes held-out oracle checks (`tests/oracle/run_oracles.py`).
   - Remember: **Level 1 deterministic execution oracles always overrule unanimous LLM consensus (T04).**

## 3. Final Gate 3/4 Sign-Off Criteria

- `python scripts/validate_handoff.py --task tasks/TASK-2026-1028-01.yaml --handoff handoffs/HANDOFF-2026-1028-01.json` exits `0`.
- `python -m unittest discover -s tests -v` executes all unit and T01–T12 adversarial tests with `0` failures and `0` errors.
- `python scripts/tcvso_calculator.py --verify-gate` confirms multi-platform orchestration is retained only where TCVSO beats the single-agent baseline by >= 15% or eliminates critical defect escape (T01, T12).
