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
- [ ] Authenticate users and machines, pair/revoke safely, and verify phone access away from the host network.
- [ ] Verify supported bounded real Gateway diagnostics and repair against the exact owned instance with current authorization and independent health evidence.
- [ ] Validate productive-progress telemetry, actual checkpoint/output recovery and cancellation for real workload adapters.
- [ ] Exercise permissions, expiry, revocation and uncertain effects through offline/disconnected paths; never replay uncertain paid or side-effectful actions automatically.
- [ ] Validate Linux and Windows installation, startup, stop, crash recovery, reboot, sleep and resource exhaustion. Windows ACL enforcement requires separate work.
- [ ] Test production identity/transport, scoped artifacts, backup/retention, migrations and operational alert delivery.
- [ ] Record platform-specific results for the exact reviewed commit, with skips and unrun stages explicit.

## Verification

Run `python -m unittest discover -s tests -v` from the repository root. All added module tests are placed in `tests/` so this command and root CI discover them. CI targets Ubuntu and Windows with Python 3.14 and also compiles Python source. Local execution uses isolated temporary fixtures and loopback-only baseline HTTP servers; it does not contact providers, install services, register accounts or deploy anything.

`SOURCE_COVERAGE.json` records selected source hashes, boundaries and final local evidence. GitHub Actions results for the exact PR head are separate evidence. A Linux skip is not a Windows pass, and green synthetic tests are not live launch acceptance.

No credentials, private datasets, real research audit counts, customer records, runtime databases, logs, checkpoint contents or machine-specific configuration are included in this checkpoint.
