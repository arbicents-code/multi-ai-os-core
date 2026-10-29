---
trigger: model_decision
description: Apply when writing, reviewing, or debugging C# .NET runtime concurrency guards, deterministic state machines, or verification modules in src/runtime/.
---

# .NET 8 C# Runtime State & Concurrency Guard Rules (Google Antigravity)

1. **Chronological & Interval-Boundary Integrity:** Evaluate historical state transitions strictly on completed interval boundaries using UTC timestamps (`DateTimeKind.Utc`). Never reference unclosed interval state in historical simulation logic.
2. **Async Dispatch & Race Condition Safety (BM-A2):** Guard asynchronous state operations against duplicate dispatches and race conditions using deterministic state tracking keyed by permanent entity ID and operation ID.
3. **Simulation-Only Safety Boundary:** Autonomous live production mutations are strictly prohibited by the Programme Charter. Enforce a mandatory runtime guard verifying that live production mutation mode is blocked unless dry-run simulation mode is active.
4. **Deterministic Verification:** Verify all C# changes with `dotnet run --project src/runtime/` or deterministic unit harness checks before generating a handoff manifest.
