# Experimental workload protection increment

The next additive demonstrator, [COOPERATIVE_WORKER.md](COOPERATIVE_WORKER.md),
now governs its own bounded actual file workload. The fixture policy boundaries
and real-collector limitations below still apply; it is not arbitrary-process protection.

This is an additive, dependency-free review candidate. It extends the offline
fixture service through `FixtureService.workload_protection()` and the read-only
`clawcare_workload_status` MCP tool. It does **not** start, kill, pause, or replay a
worker, modify the gateway repair adapter, deploy a service, or establish live
production protection. Every policy decision remains labeled synthetic and every
claim returns `execute: false`.

`workload_observer.py` separately supplies actual read-only Linux observations and
a tiny verified-artifact demonstration. See [WORKLOAD_OBSERVER.md](WORKLOAD_OBSERVER.md)
for its scope, commands and limitations. Real observations do not make a fixture
policy engine or its caller-reported verification a production enforcement layer.

## Policy behavior

- Admission is `allow`, `pause`, or `unknown`, with a reason. A fresh available-RAM
  observation must cover the caller's peak additional estimate, a reserve, and
  outstanding reservations for other tasks. Defaults: 30-second freshness,
  256 MiB reserve, and another 128 MiB recovery margin. These are configurable
  fixture thresholds, not recommended sizing for all real workloads.
- Missing, invalid, future, stale or conflicting same-time observations fail
  closed. Older observations cannot overwrite newer evidence. Even invalid
  payloads advance the ordering watermark when their time is plausible.
- Every accepted memory observation updates registered task recovery state.
  Pressure cannot disappear between explicit assessments. Recovery needs two
  distinct good samples and ten seconds of observed cooldown by default.
- A live heartbeat is separate from productive progress. Only a strictly
  increasing durable-work sequence refreshes progress. A fresh heartbeat with
  no progress for 60 seconds is `STALLED`; absent heartbeat is `UNKNOWN`, never
  proof that a worker stopped. Progress counters must come from a trusted adapter
  that verifies real durable units, not a heartbeat timer.
- Checkpoint references and SHA-256 identities are immutable. Already verified
  output digests, saved-but-unverified output references, and draft references
  survive restart. Claims cannot reprocess any of those protected item IDs.
  The module stores references/inventories, not the original output bytes.
- Checkpoint verification is an explicit fresh adapter report about reference
  integrity and the verified inventory. Preserved drafts/unverified items are
  not promoted by that report; they remain blocked for separate review. A failed
  or conflicting report invalidates earlier success. New faults invalidate prior
  verification and require post-fault evidence.
- A transaction reserves each action ID once, before any possible external
  adapter effect. The same ID returns `EXISTING_ACTION`; a new ID cannot bypass
  an unresolved action. `CLAIMED` and `UNKNOWN` actions keep memory reservations. Terminal actions
  also retain reservations until a newer memory sample; unresolved disconnect
  uncertainty retains them until explicit reconciliation.
  Restart never retries them automatically. These reservations are ledger
  accounting, not OS memory reservations; they intentionally can double-count
  memory already consumed by a real process.
- A task has at most three lifetime claims, including successful claims. This is
  an intentionally small finite fixture policy, not an unlimited batch scheduler.
  Known no-effect failures need positive quiescence evidence and exponential
  retry cooldown. Unknown effects require reconciliation and cannot be replayed.
- Recovery claims need recent explicit worker-quiescence evidence. Heartbeats
  invalidate that evidence. Stale no-effect reports cannot override subsequent
  activity or progress. A disconnect requires explicit no-untracked-effects
  reconciliation as well as individual resolution of any outstanding claim.
- A successful-looking return cannot mark recovery. Fresh independent output
  verification, original-symptom health, independent health, post-action and
  current-fault-epoch progress, and valid resources must all agree. Even a newly
  verified output does not automatically clear disconnect uncertainty.
- Host, gateway and task observations are stored separately with
  `causal_link: unknown`. Temporal order is not a causal conclusion. Local alert
  rows deduplicate by task and code; counts/timestamps record repetition. There
  is no email, network notification, or remote alert transport.

All mutations reuse the candidate's SQLite `BEGIN IMMEDIATE` transactions and
`FULL` synchronous setting. Configuration and budgets persist across restarts;
implicit limit changes and backwards/nonfinite clocks fail closed. This is a
trusted-local-owner ledger, not tamper-proof storage or a secure clock. It has
no retention/migration policy for production, and intentionally does not expire
an uncertain action into permission to retry.

## API and verification contract

```python
engine = service.workload_protection()
engine.register('job-1', required_bytes=512 * 1024 * 1024,
                checkpoint_ref='checkpoint-v1', checkpoint_sha256='a' * 64)
engine.observe_memory(observed_at, available_bytes, total_bytes)
assessment = engine.assess('job-1')
```

Other bounded APIs: `heartbeat(task_id, progress_seq)`, `observe_cause(...)`,
`verify_checkpoint(...)`, `claim(task_id, item_id, action_id)`, `outcome(...)`,
and `reconcile_disconnect(...)`. The automated examples are authoritative for
exact argument shapes. These calls accept trusted test assertions; they do not
authenticate a worker, open or verify arbitrary checkpoint files, or grant an
external action permission. A future execution adapter must independently enforce
identity, approval, current state and the claim/effect boundary.

`ReadView.workload_status()` and `clawcare_workload_status` show at most 100 task
summaries, actions, observations and alerts per category. Task summaries expose
counts rather than full checkpoint inventories to keep MCP output bounded. This
is last-recorded evidence and is not proof that the service is presently running.
Older candidate ledgers without workload tables return an empty uninitialized
view. No automatic migration of any production database is supplied.

## Tests and evidence

```sh
python -m unittest discover -s tests -v
python -m compileall -q .
python workload_observer.py --demo --items 3
```

The deterministic generic media-ingestion regression deliberately uses invented
IDs and dummy hashes: 82 saved audio references, 80 independently verified,
20 draft transcript references. Two task OOM observations precede a host
connection loss; gateway health remains a separate unknown. Existing checkpoints
and all saved/draft IDs remain protected. An ambiguous claim is never replayed;
only a new item can be planned after quiescence, reconciliation, resource
stability and checkpoint verification. Only independently verified subsequent
progress can receive a synthetic recovery label. No media, course content,
private URL, provider request, or real desktop incident is included.

Coverage also includes stale/missing/conflicting memory, recovery hysteresis,
intermediate pressure, live-but-stalled workers, fresh quiescence, concurrent
claims, cross-task headroom, restart persistence, bounded retry, checkpoint
ordering, fault epochs, false recovery rejection, deduplicated alerts, and
bounded read-only projection. The collector has separate deterministic parser
and actual Linux tiny-workload tests. These do not prove real gateway repair,
transcription resumption, crash-power-loss durability or Windows operation.

## Expanded resource and cost requirements

The proposed [task spending, resources and protection work order](TASK_SPENDING_WORK_ORDER.md#resource-capacity-and-admission) extends future admission to physical RAM, commit/swap, effective container/ancestor limits, pressure, CPU/concurrency, disk quotas/inodes and checkpoint capacity, together with spending reservations. The fixture thresholds above continue to describe existing code only. Do not treat a fixed raw-free-RAM threshold as the production policy or remove current holds without a reviewed replacement.

Future adapters must estimate the next bounded unit, account for competing work and ClawCare overhead, preserve unknown/stale evidence, and checkpoint safely before a supported pause. Capacity samples are observations, not guaranteed allocations. Budget denial must not kill unsaved work, prune storage or restart uncertain paid work. These additions and their acceptance scenarios are not implemented or proven by this documentation update.

### Platform adapter scope

The future platform-neutral admission contract must support a macOS / Apple Silicon Mac mini adapter and a Windows adapter alongside existing Linux work. Bind measurements to the exact host/VM/container and retain platform-specific meanings. Mac memory pressure, compressed memory and swap must not be substituted with a Linux-only free-RAM calculation; Windows commit/working-set metrics need their own verified mapping. [Apple's memory overview](https://support.apple.com/en-au/guide/activity-monitor/actmntr1004/mac) describes pressure using multiple signals, including swap and cached/wired memory.

No Mac collector or pressure-governed workload is established by this document. Use the [platform acceptance scenarios](UPGRADE_READINESS.md#platform-readiness-and-mac-mini-acceptance), including owner-away operation, restart/resume, pressure, sign-in holds, denied permissions and revocation. Keep existing safe unknown/hold behavior until reviewed adapter evidence supports a replacement.

## Release-readiness checklist

Complete these gates before claiming a production release of workload protection:

- Reconcile the current application/desktop source and schemas; this candidate
  does not replace or claim parity with an uninspected newer implementation.
- Implement an installed-target adapter with exact owned-worker identity,
  independently checked output/checkpoint semantics, bounded peak-resource
  estimation, cooperative pause/cancel, and authorization checked at the effect.
- Bind collection to the actual worker's namespace/cgroup. Support required
  Linux variants and Windows collectors, including unknown/stale behavior.
- Exercise real representative workloads under safe controlled pressure, stalls,
  crash/restart, host disconnect, cancellation and checkpoint reconciliation.
- Establish secure authenticated current policy, remote revocation limits,
  multi-host idempotency, migration, retention and permission boundaries.
- Verify startup/reboot/shutdown behavior, supported platforms, final integrated
  test suites and real independent gateway health checks.
- Review operational alert delivery and user controls separately; no network
  alert or security-setting change is part of this increment.

No percentage or guarantee of reliability is implied by these fixture passes.
The smallest next integration is an authorized cooperative local test worker
which checks a current claim at each unit boundary, writes durable checkpoints,
and supplies independent verification receipts. The existing tiny observer demo
is deliberately not such a governor and does not claim to prevent OOM.
