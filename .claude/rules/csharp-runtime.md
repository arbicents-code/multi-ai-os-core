---
paths:
  - "src/runtime/**"
  - "**/*.cs"
---

# .NET 8 C# Runtime State & Concurrency Guard Rules (Claude Code Path-Scoped)

1. **Deterministic Discrete-Step Execution:** Execute state evaluations and discrete transitions strictly on completed interval boundaries (`OnIntervalCompleted()`) using explicit UTC timestamps rather than mid-interval estimations to prevent intra-interval look-ahead leakage.
2. **Async Dispatch Race Prevention (BM-A2):** Never assume synchronous state mutation after asynchronous dispatch calls. Guard state transitions and concurrency quotas with deterministic state locks and verify completion callbacks before submitting dependent operations.
3. **Zero Autonomous Production Mutation:** All C# runtime code in this repository is restricted to deterministic simulation, verification, and concurrency guard validation. Enforce mandatory dry-run / simulation-only runtime guards blocking live production mutation mode.
4. **UTC Chronological Alignment:** Convert all timestamps to `DateTimeKind.Utc` before joining with external bitemporal state exports.
