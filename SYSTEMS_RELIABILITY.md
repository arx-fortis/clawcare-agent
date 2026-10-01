# ClawCare — Systems Reliability Principles

ClawCare is a standalone OpenClaw reliability and recovery product. These principles shape how ClawCare observes, diagnoses, repairs, verifies, rolls back, and learns from runtime behavior. They do **not** make ARX, Fortis, PolyMind, ExecuBot, n8n, blockchain, or any future governance stack dependencies.

## Core control loop

**desired healthy state → observe actual state → detect discrepancy → diagnose → bounded intervention → verify → record → observe again**

Persistent discrepancy should trigger structural diagnosis rather than unlimited repeated correction.

## Principles

1. **Relationships matter more than parts alone.** Track connectors, dependencies, routes, credentials, tools, gateways, plugins, and upstream/downstream effects—not just isolated agents.
2. **Diagnose structure before reacting to events.** A crash, timeout, or failed task is evidence. Repeated patterns and system structure explain why it keeps happening.
3. **Model nonlinearity.** Small changes can have no visible effect until a threshold is crossed; large interventions can have surprisingly little effect.
4. **Model delays explicitly.** Separate decision time, execution time, effect time, observation time, reporting time, and evaluation time.
5. **Distinguish finite and replenishing resources.** Track current stock, inflow, outflow, replenishment, depletion thresholds, reset windows, and recovery delays for CPU, memory, API quotas, storage, retry budgets, and other constrained resources.
6. **Expect adaptation.** A repair or new rule changes the system. Observe how agents, plugins, workflows, and users adapt after intervention.
7. **Detect drift to low performance.** Preserve reference standards instead of silently lowering the definition of healthy because degraded performance became normal.
8. **Separate actual, observed, inferred, and desired state.** Logs and health checks are partial observations, not reality itself.
9. **Observe across time, boundaries, and hierarchy.** A local failure may be caused by an upstream dependency or larger-system constraint.
10. **Regulate discrepancy; diagnose persistent discrepancy.** Small safe corrections can restore equilibrium. Repeated correction is evidence of a deeper structural fault.
11. **Repeated intervention is evidence.** If ClawCare keeps applying the same repair, escalate from regulation mode to diagnosis mode instead of declaring repeated success.

## Runtime health model

Each monitored target should expose or infer:

- desired state
- observed state
- inferred state
- pending/unresolved state
- health signals
- dependency state
- resource state
- last stable checkpoint
- active discrepancy
- expected effect window

## Event and timing model

Record:

- decision time
- approval time
- execution time
- expected effect window
- first observed effect
- verification time
- delayed side effects
- retry count
- prior identical interventions

## Regulation mode

Use for bounded, reversible corrections when the likely cause is known and the discrepancy is within a safe operating range.

## Diagnosis mode

Trigger when:

- the same repair is repeated;
- the discrepancy persists;
- the effect window has passed without expected recovery;
- multiple subsystems drift together;
- measurements conflict;
- the monitored system cannot reach its target despite correction.

## Verification rule

A command succeeding is not proof of recovery. Verification must test the original symptom and at least one independent harmless health signal.

## Implementation implications

- Extend incident/work-order records with expected-effect windows and repeat-intervention counts.
- Add a persistent-discrepancy detector.
- Add a regulation-to-diagnosis escalation rule.
- Preserve absolute health/reference standards separately from current measured performance.
- Add dependency/connector inventory to diagnostics.
- Track resource classes and retry/replenishment budgets.
- Flag stale or delayed observations separately from confirmed failures.
- Record pre-action and post-action state with timing.
- Add acceptance tests for delay, repeated repair, false health signals, drift, and upstream dependency failure.

## Public positioning

Describe ClawCare simply as a **self-regulating reliability and recovery agent for OpenClaw**:

**observe → diagnose → checkpoint → bounded repair → verify → rollback/escalate → audit**

Keep ARX/Fortis/Proof-of-Risk language outside public ClawCare positioning. ClawCare may be used privately as a research testbed, but no such system is required for ClawCare to operate.
