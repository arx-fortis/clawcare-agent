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

## Operating costs and project protection

ClawCare must account for its own operating overhead and all supervised tasks, including provider tokens/credits, infrastructure compute, container allocation, memory pressure and retained storage. Decisions combine current authority, conservative cost exposure and workload-specific resource fit; a fixed free-RAM threshold alone is insufficient. Budget holds preserve work through verified cooperative checkpoints rather than arbitrary process termination.

The expanded [task spending, resources and protection work order](TASK_SPENDING_WORK_ORDER.md) is the proposed implementation contract. It preserves the existing ledger, reconciliation and source-review gates; its USD $5 pilot is unapproved. Firecrawl remains stopped, with saved-receipt or synthetic accounting only.

A later optional phase adds non-secret credential inventory, established encrypted vault adapters and versioned protection/restore checks for code, designs, documents and configuration. No secret import, persistent access or backup rollout is authorized here. Security and provenance evidence must state their limits; neither metadata nor encryption is a legal IP guarantee. These future capabilities do not make external platforms dependencies of standalone ClawCare.

## Phone-first fleet monitoring and secure access

ClawCare's central product purpose is **one phone-accessible application for many authorized computers and OpenClaw agent instances**, especially Apple Silicon Mac minis and also Windows hosts. The owner should be able to select the exact host and agent, inspect health, gateway/connector status, current work order, productive progress, last verified checkpoint, spend/exposure and resource pressure, then use the supported remote-view, secure handoff, approval and bounded recovery controls. Mobile fleet access is central; full native desktop control depends on the chosen tool and permissions.

Maintain an authenticated host/agent registry with opaque stable identities, tenant/owner, authorized roles, host-to-agent relationships, platform/version, approved transport/pairing reference, capabilities, observation freshness and revocation state. Distinguish discovered, paired, authorized, reachable and operation-ready. A discovered host, existing account or shared network does not authorize access. Pairing and persistent-access grants require explicit approval; no registry or pairing is created by this design.

Reuse established secure transport and remote/browser tools through verified adapters. Do not invent a new remote-control protocol or expose the current loopback API through an unreviewed tunnel. Enforce tenant, host, agent, artifact and operation scope at both the control plane and target boundary. The phone session must not become a universal credential for every device, agent or provider. Bind each command/approval to the selected host, exact agent instance, work-order revision and current authorization; recheck when switching devices or reconnecting.

The shared fleet view needs honest offline/stale/permission-blocked states and independent host, gateway and task health. Remote-view availability is tested on its own; a successful view does not authorize repair. Secret entry uses a supported secure handoff, and the credential portal exposes non-secret inventory/status through approved vault integration. Audit who requested, approved and executed a bounded action, its target/revision, checkpoint, result and verification, without recording secret values or unnecessary screen contents.

Keep the durable inspect → diagnose → checkpoint → approve → execute → verify → audit → handoff loop beneath the app. A coordinating component may be reused behind the ClawCare interface to avoid duplicate coordinators, but its role and ownership remain an open architecture proposal; no product merger or new dependency is decided here. Standalone local operation remains available independently of the phone surface or optional orchestration products.

## Platform-neutral core and host adapters

Product target, 2026-10-10: make ClawCare useful for Apple Silicon Mac mini owners alongside Windows users, while retaining the existing standalone core and Linux/container work. This is a proposed compatibility architecture, not a claim that a Mac adapter, installer or native UI has been implemented or tested.

The shared core owns work-order identity, authority and stop state, checkpoint inventories, bounded recovery, cost/exposure accounting, resource admission, non-secret credential metadata, audit evidence and readiness. OS-specific collection, process ownership, filesystem permissions, startup supervision, browser/desktop access and secure-store integration belong to versioned adapters. Each adapter reports capability, platform/architecture/version, exact target, permission scope, last successful test and supported/blocked/unknown status. Do not force non-equivalent OS metrics into one misleading value.

- **macOS / Apple Silicon Mac mini:** verify native runtime and dependency compatibility for the actual macOS and arm64 environment; define host memory/pressure/swap, storage, process identity and safe checkpoint behavior. A container/VM observation is not a measurement of the entire Mac. Background supervision requires a reviewed platform-appropriate design, such as a scoped launchd agent/service, with user-session requirements explicit; Windows Task Scheduler instructions do not apply. [Apple's launchd guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html) is an architectural reference, not a current ClawCare installer or proof of compatibility.
- **Windows:** preserve existing supervision and sign-in startup documentation, then validate the Windows collector/control adapter, ACLs, session boundaries and platform-specific recovery. An existing scheduled task or passed fixture is insufficient evidence of unattended production readiness.
- **Linux / containers:** preserve the bounded current collectors and source boundaries. Expose host, VM and container scope separately; do not silently reuse Linux-only collectors as macOS or Windows implementations.

### Phone-away control and capability evidence

Prefer an existing authorized connector, browser or remote-control tool that supports the requested operation. ClawCare should integrate its status, controls and receipts through supported interfaces; it need not build a new remote-desktop system to provide value. Native app/UI control is available only when the selected tool and current OS permissions actually support it.

Record these independently: process alive; transport reachable; browser listed/discovered; exact browser/tab or app controllable; application session authenticated; and requested operation authorized. A browser name in a list, a running PID or an authenticated phone session does not establish the other states. Verify with a harmless scoped round-trip on the exact target; retain freshness and a precise next step when blocked. The phone should show the last verified checkpoint, current or stale status, costs/exposure and what actually needs the owner's attention.

Protected sign-in, credential entry and OS permission prompts require the supported user handoff. Explain the exact permission and reason; keep denial/revocation intact and avoid repeated prompts or alternative routes around it. macOS [Accessibility](https://support.apple.com/guide/mac-help/allow-accessibility-apps-to-access-your-mac-mh43185/mac) and [screen-recording permissions](https://support.apple.com/en-gb/guide/mac-help/mchld6aa7d23/mac) are separate capabilities, not implied by connector installation. No key or password belongs in the phone transcript, logs or public docs.

Respect intentional disconnect, stop, sleep and shutdown. Do not silently change power/security settings, relaunch a deliberately stopped connector, or promise reachability before login/unlock. A host that is asleep, offline or awaiting its owner remains explicitly unavailable for affected operations. After an authorized reconnect, reconcile checkpoint, session identity, pending effects, budget and current authority before resuming; never replay uncertain work because connectivity returned.

A user's requirement to finish a particular source ingestion before enabling a reply workflow belongs in that user's private workflow template and task dependencies. It is not a universal installation or readiness gate for Mac mini users, Windows users or standalone ClawCare. Preserve such scoped prerequisites without publishing private source material.

## Public positioning

Describe the proposed ClawCare product as a **phone-first fleet monitor and secure access/recovery hub for OpenClaw agents on authorized computers**. Its existing local reliability core follows:

**observe → diagnose → checkpoint → bounded repair → verify → rollback/escalate → audit**

Keep ARX/Fortis/Proof-of-Risk language outside public ClawCare positioning. ClawCare may be used privately as a research testbed, but no such system is required for ClawCare to operate.
