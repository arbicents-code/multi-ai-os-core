using System;
using System.Collections.Generic;

namespace MultiAiOs.Runtime
{
    public enum ExecutionEnvironment
    {
        Simulation,
        Staging,
        ProductionLive
    }

    public sealed record TimeWindowClosedEvent(
        string EntityId,
        DateTime WindowStartUtc,
        DateTime WindowEndUtc,
        decimal MetricSnapshotValue,
        bool IsWindowClosed
    );

    /// <summary>
    /// Deterministic Runtime State-Transition &amp; Chronological Guard (BM-A2).
    /// Enforces:
    /// 1. Simulation/Staging safety boundary (blocks autonomous live ProductionLive mutations).
    /// 2. Strict UTC and closed-window chronological evaluation.
    /// 3. Idempotent in-flight transition locking keyed by (WorkflowLabel, TransitionKey) to prevent duplicate async callbacks.
    /// </summary>
    public sealed class StateTransitionGuard
    {
        private readonly HashSet<string> _inFlightKeys = new(StringComparer.Ordinal);
        private readonly HashSet<string> _completedKeys = new(StringComparer.Ordinal);
        private DateTime _lastWindowEndUtc = DateTime.MinValue;

        public ExecutionEnvironment Environment { get; }
        public bool DryRunSimulation { get; }

        public StateTransitionGuard(ExecutionEnvironment environment, bool dryRunSimulation = false)
        {
            Environment = environment;
            DryRunSimulation = dryRunSimulation;
        }

        public void EnsureExecutionPermitted()
        {
            if (Environment == ExecutionEnvironment.ProductionLive && !DryRunSimulation)
            {
                throw new InvalidOperationException(
                    "SECURITY_BOUNDARY_VIOLATION: Autonomous live production state mutation (ExecutionEnvironment.ProductionLive) is prohibited by AGENTS.md Charter.");
            }
        }

        public void ValidateWindowClosedUtc(TimeWindowClosedEvent windowEvent, DateTime systemClockUtc)
        {
            if (windowEvent.WindowEndUtc.Kind != DateTimeKind.Utc || systemClockUtc.Kind != DateTimeKind.Utc)
            {
                throw new ArgumentException("Chronological violation: All runtime timestamps must be DateTimeKind.Utc.");
            }
            if (!windowEvent.IsWindowClosed || windowEvent.WindowEndUtc > systemClockUtc)
            {
                throw new InvalidOperationException("Look-ahead violation: State evaluated on an unclosed or future telemetry window.");
            }
            if (windowEvent.WindowEndUtc < _lastWindowEndUtc)
            {
                throw new InvalidOperationException("Out-of-order telemetry window progression detected.");
            }
            _lastWindowEndUtc = windowEvent.WindowEndUtc;
        }

        public bool TryBeginAsyncTransition(string workflowLabel, string transitionKey)
        {
            EnsureExecutionPermitted();
            string compositeKey = $"{workflowLabel}:{transitionKey}";
            if (_inFlightKeys.Contains(compositeKey) || _completedKeys.Contains(compositeKey))
            {
                return false; // Duplicate async race condition prevented (BM-A2)
            }
            _inFlightKeys.Add(compositeKey);
            return true;
        }

        public void CompleteAsyncTransition(string workflowLabel, string transitionKey, bool succeeded)
        {
            string compositeKey = $"{workflowLabel}:{transitionKey}";
            _inFlightKeys.Remove(compositeKey);
            if (succeeded)
            {
                _completedKeys.Add(compositeKey);
            }
        }
    }

    public static class Program
    {
        public static int Main()
        {
            // Self-verification oracle for Workload A/B runtime state guard module (BM-A2)
            var liveGuard = new StateTransitionGuard(ExecutionEnvironment.ProductionLive, dryRunSimulation: false);
            bool liveBlocked = false;
            try
            {
                liveGuard.TryBeginAsyncTransition("PIT_EVAL_WORKFLOW", "SYS-0001_2026Q1");
            }
            catch (InvalidOperationException)
            {
                liveBlocked = true;
            }
            if (!liveBlocked)
            {
                Console.Error.WriteLine("FAIL: ProductionLive execution was not blocked.");
                return 1;
            }

            var simGuard = new StateTransitionGuard(ExecutionEnvironment.Simulation);
            var window = new TimeWindowClosedEvent(
                "SYS-0001",
                new DateTime(2026, 5, 14, 20, 0, 0, DateTimeKind.Utc),
                new DateTime(2026, 5, 15, 20, 0, 0, DateTimeKind.Utc),
                1.00m,
                IsWindowClosed: true
            );
            simGuard.ValidateWindowClosedUtc(window, new DateTime(2026, 5, 15, 20, 0, 1, DateTimeKind.Utc));

            bool firstAttempt = simGuard.TryBeginAsyncTransition("PIT_EVAL_WORKFLOW", "SYS-0001_2026Q1");
            bool duplicateRaceAttempt = simGuard.TryBeginAsyncTransition("PIT_EVAL_WORKFLOW", "SYS-0001_2026Q1");
            simGuard.CompleteAsyncTransition("PIT_EVAL_WORKFLOW", "SYS-0001_2026Q1", succeeded: true);
            bool postCompleteDuplicate = simGuard.TryBeginAsyncTransition("PIT_EVAL_WORKFLOW", "SYS-0001_2026Q1");

            if (!firstAttempt || duplicateRaceAttempt || postCompleteDuplicate)
            {
                Console.Error.WriteLine("FAIL: Async state-transition guard failed idempotency check.");
                return 1;
            }

            Console.WriteLine("PASS: RuntimeStateGuard deterministic self-test succeeded (ProductionLive blocked, UTC WindowClosed verified, BM-A2 race prevented).");
            return 0;
        }
    }
}
