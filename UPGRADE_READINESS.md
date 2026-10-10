# Upgrade source coverage and launch readiness

Status: experimental review checkpoint, 2026-10-08. **Not launch-ready.**

## Included source

- Preserved public standalone baseline `c40650a052671ca06b57f02c4ea4ebd14b52f9df`, MIT license, demo, and history. Baseline monitoring, bounded Boolean control, supervisor, team handoffs and user-owned connections remain intact.
- `fixture_service.py`, `fixture_service_supervisor.py`, `fixture_service_mcp.py`: bounded trusted-local-owner synthetic service with independent fixture verification, conditional exact-byte rollback, persistent receipts and a four-tool read-only MCP view. See [service boundary](START_HERE_SERVICE_CANDIDATE.md).
- `packaging/`: Linux and Windows review templates only; no installation or reboot proof.
- `clawcare_ledger/`: optional same-host scoped lookup/reuse library with evidence freshness, claim deduplication and billing reconciliation. It is not a provider connector, authenticated service, dashboard or distributed database. See [execution contract](LOOKUP_LEDGER.md).
- `workload_protection.py`: synthetic admission, productive-progress/stall, checkpoint inventory and bounded recovery-decision policy with no process-control effects. `workload_observer.py`: actual bounded read-only Linux host/cgroup observations and a tiny verified-artifact demonstration. Neither supplies an OS memory governor or production recovery adapter. See [policy boundaries](WORKLOAD_PROTECTION.md) and [observer limits](WORKLOAD_OBSERVER.md).

- `cooperative_worker.py` and `cooperative_demo.py`: bounded actual tiny-file work with admission, pause/cancel, checkpoints and independent output reconciliation. Pressure/interruption demonstrations are simulated; real file effects are confined to the new owned workload. This does not adopt or protect arbitrary jobs. See [cooperative worker](COOPERATIVE_WORKER.md).

Source inclusion is additive. The new modules do not silently migrate or share existing runtime databases, policies or credentials. Use fresh, private synthetic directories/databases for evaluation.

## Pending source reconciliation

The newer thermostat, exact-instance Gateway lifecycle, responsive work-order dashboard and pairing/relay integration source has not been transferred into this checkout. Reported historical checks from that source are not checks of this branch. Do not overwrite that work or call this checkpoint “all upgrades integrated.”

Before merging those sources: verify the source revision and file manifest, compare work-order revisions, health schemas, policies and idempotency, then design storage migrations and run one consolidated full suite.

## Launch gates still open

- [ ] Reconcile the newer application bundle and execute consolidated current-source tests.
- [ ] Deliver the central authenticated phone fleet experience: enroll/pair authorized hosts and OpenClaw agents, enforce tenant/role/target isolation, revoke safely, and verify away-from-host-network status and supported secure access.
- [ ] Verify supported bounded real Gateway diagnostics and repair against the exact owned instance with current authorization and independent health evidence.
- [ ] Validate productive-progress telemetry, actual checkpoint/output recovery and cancellation for real workload adapters.
- [ ] Exercise permissions, expiry, revocation and uncertain effects through offline/disconnected paths; never replay uncertain paid or side-effectful actions automatically.
- [ ] Validate each claimed Linux, Windows and planned macOS / Apple Silicon Mac mini target separately for installation, startup, stop, crash recovery, reboot, sleep and resource exhaustion. Windows ACLs and Mac permission/session boundaries require platform-specific evidence.
- [ ] Test production identity/transport, scoped artifacts, backup/retention, migrations and operational alert delivery.
- [ ] Record platform-specific results for the exact reviewed commit, with skips and unrun stages explicit.

## Spending and resource requirements

[TASK_SPENDING_WORK_ORDER.md](TASK_SPENDING_WORK_ORDER.md) now specifies ClawCare self-overhead and all supervised-task usage: provider tokens/credits/currency, Codespaces/host compute and storage, Docker allocation without duplicate bills, RAM/commit/swap/container limits, disk capacity, joint admission and safe checkpoint/stop behavior. These are documentation requirements, not implemented collectors, an integrated spending dashboard or validated budget enforcement. Preserve existing relevant source and reconcile it before Cursor implementation.

The proposed one-time USD $5 pilot still needs numerical approval; no paid execution or Firecrawl re-enablement follows from this update. Required offline tests include saved-receipt import under STOP, unknown costs, delayed settlement, shared-cost allocation, pressure-aware admission and retained storage after compute stops.

A later optional credential/asset-protection phase requires separate vault/security review, explicit access authority and isolated restore evidence. It must not silently block the current bounded ClawCare setup, nor imply credential access, backup activation, legal IP protection or security certification.

## Platform readiness and Mac mini acceptance

Product and compatibility expansion, 2026-10-10: the central experience is one phone app for many authorized machines/OpenClaw agents, including Apple Silicon Mac minis and Windows PCs, through [one core with platform adapters](SYSTEMS_RELIABILITY.md#platform-neutral-core-and-host-adapters). Verify the exact OS, architecture, runtime, tool version and session, rather than claiming generic platform parity.

| Target | Evidence currently represented by this branch | Outstanding gate |
| --- | --- | --- |
| macOS / Apple Silicon Mac mini | Product requirements only; no Mac run or adapter validation | Native runtime/dependencies, collectors, permissions, background supervision and owner-away acceptance |
| Windows | Existing synthetic/isolated tests and sign-in startup implementation | Actual authorized-host install/reboot, session/control access, ACLs and representative recovery |
| Linux / containers | Existing bounded read-only observations and isolated cooperative fixtures | Target-specific collection/control coverage and representative workload/host recovery |
| Central phone fleet experience | Product requirement and proposed authenticated registry/control contract | Host/agent pairing, tenant isolation, chosen secure tool, exact host/session, permissions, away-from-network behavior and safe revocation |

No current CI result should be labeled a Mac pass: this branch's configured matrix remains Ubuntu and Windows. A generic Python test pass also cannot establish native UI control, background access or an authenticated provider session.

Required future adapter acceptance, first with synthetic faults and then only on an explicitly authorized test host:

1. **Owner away and fleet selection:** from the approved phone app, select an authorized host and exact OpenClaw agent, inspect fresh health, work-order/checkpoint state and costs, request the supported remote view or secure user-authentication handoff, approve a bounded recovery, and independently verify the resulting checkpoint/output before reporting success. Unsupported native/browser actions produce an accurate blocker. Do not equate process liveness, browser discovery, control capability or session authentication.
2. **Restart and login boundary:** verify one exact supervisor/worker, durable stop/restart ceilings and preserved state after controlled process and host restart. Login/unlock requirements remain visible; no promise of pre-login operation or silent security bypass.
3. **Checkpoint resume:** after an authorized disconnect/reconnect or restart, verify the last durable checkpoint and output inventory, preserve completed/draft work, reconcile pending effects and resume only permitted missing units. Duplicate delivery cannot spawn competing workers or rebill an uncertain unit.
4. **Resource pressure:** workload-specific Mac memory/pressure/swap and disk evidence, and Windows-equivalent supported metrics, drive bounded admission. Missing/stale measurements remain unknown; low raw free RAM alone is not a stop criterion. Preserve sufficient checkpoint capacity and pause safely.
5. **Sign-in prompt:** an expired browser/provider session becomes an authentication hold with a supported secure user handoff. No credential copying from another session, repeated blind login or claim that a listed browser is authenticated.
6. **Denied permissions:** deny required screen, accessibility, filesystem or tool permissions in a controlled fixture; the exact affected capability remains blocked and no alternate route bypasses denial. Unaffected read-only status may remain available only within its permissions.
7. **Safe revocation:** revoke task or connector authority; deny new dispatch, preserve checkpoints and show unresolved in-flight effects. Stale phone controls, worker retries and background startup cannot resurrect revoked or intentionally stopped work.
8. **Intentional sleep and disconnect:** deliberate stop, sleep/shutdown and removed connectivity remain respected across wake/restart. No unauthorized wake policy, keep-awake setting or autostart is introduced. Recovery status must distinguish reconnect from authorized task resume.
9. **Audit and privacy:** phone, host and adapter events correlate to one task/run without publishing secrets, private source paths or credentials. Unavailable collectors/control routes and skipped platform tests remain visible.
10. **Scoped workflow prerequisites:** a user-specific ingestion-before-reply dependency blocks only that user's affected workflow; it cannot prevent unrelated users from setting up or using ClawCare.
11. **Multiple hosts and tenant isolation:** two authorized machines/agents remain distinct in the same phone app; selecting one never sends a command or approval to another. Unpaired devices, other tenants, removed roles, stale host selections and replayed approvals are rejected. Pairing/revocation cannot be inferred from discovery or connectivity.
12. **Gateway, credential and handoff scope:** gateway management targets the exact authorized instance; credential metadata does not expose API keys or grant vault access; recovery and handoff receipts preserve task ownership, authority and independent verification across the phone/host boundary.

Return evidence for the exact commit and hardware/OS/tool combination, including passes, failures, skips and unrun stages. These are acceptance requirements only. No Mac access, installation, service registration, permission grant, paid test, merge or deployment is authorized by this update; Cursor remains the sole implementation writer.

## Verification

Run `python -m unittest discover -s tests -v` from the repository root. All added module tests are placed in `tests/` so this command and root CI discover them. CI targets Ubuntu and Windows with Python 3.14 and also compiles Python source. Local execution uses isolated temporary fixtures and loopback-only baseline HTTP servers; it does not contact providers, install services, register accounts or deploy anything.

`SOURCE_COVERAGE.json` records selected source hashes, boundaries and final local evidence. GitHub Actions results for the exact PR head are separate evidence. A Linux skip is not a Windows pass, and green synthetic tests are not live launch acceptance.

No credentials, private datasets, real research audit counts, customer records, runtime databases, logs, checkpoint contents or machine-specific configuration are included in this checkpoint.
