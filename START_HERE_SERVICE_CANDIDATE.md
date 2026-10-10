# ClawCare offline service candidate

See [workload protection](WORKLOAD_PROTECTION.md) and [read-only Linux observations](WORKLOAD_OBSERVER.md) for the additive workload increment.

## What this checkpoint is

Start here. The historical `SUPERVISOR.md`, release files, and legacy startup installer describe the preserved public base. They are not installation instructions or deployment evidence for this service candidate.

An experimental synthetic-fixture service layered on the public standalone baseline. It imports the unchanged `Control`, `process_lock`, and `Supervisor` modules. The original demo and Git history are preserved.

This module is included with the optional lookup library and workload policy module in a single testable source checkpoint. Inclusion does not connect their runtime databases, policies, or adapters. The newer thermostat, Gateway lifecycle, dashboard, and pairing/relay source remains pending reconciliation. See `UPGRADE_READINESS.md` for current scope and launch gates; historical release files describe earlier versions.

## Implemented behavior

1. **Observe and diagnose:** deterministic local fixture signals distinguish a disabled synthetic gateway from an external/provider dependency and an unexplained enabled-but-unhealthy condition
2. **Checkpoint and authorize:** the existing bounded Boolean repair creates exact before/after bytes and a scoped order; only an explicit, current, finite cached fixture policy allows action
3. **Repair:** only `gateway.json`, field `enabled`, value `true`, inside a newly created, explicitly marked synthetic directory
4. **Verify independently:** the original simulated response symptom and a separate simulated heartbeat signal must both pass; a successful write is insufficient
5. **Rollback conditionally:** the authorization bundles exact-byte restoration if verification fails; rollback rechecks policy, expiry, pause, revision, and drift at the effect boundary
6. **Record:** durable SQLite receipts retain before/after/actual hashes, the authorizing policy and revision, current revision, verification evidence, restored-state observation, result, and timestamps
7. **Reconcile on restart:** a durable checkpoint without effect is aborted; a completed effect can be passively verified; any uncertain effect remains `NEEDS_RECONCILIATION` and is never automatically replayed
8. **Schedule and supervise:** a durable next-due time, exponential failure backoff, finite per-policy action budget, same-host exclusion locks, and the base supervisor's persisted restart budget prevent uncontrolled repeated actions

All fixture observations, receipts, and MCP outputs are labeled synthetic. An online/provider failure records `ONLINE_REQUIRED`, makes no provider call, and grants no spend. Unknown failure classes become `DIAGNOSIS_REQUIRED`.

## Safety and policy boundary

Initialization creates a **new directory only**, starts paused, and issues no policy. No arbitrary shell command, plugin execution, path, provider, credential, network call, or real Gateway adapter exists in the new service engine.

`authorize-fixture` is an explicit local test authorization. It grants exactly the repair/conditional-rollback pair for one fixture, defaults to one action, permits at most three actions, and expires in at most 900 seconds. Repeated healthy/broken cycles cannot exceed that grant. Policies are checked at detection, approval, claim, and immediately before the file effect. The legacy grant's absolute deadline is capped to the cached policy deadline. A clock moving backward fails closed. Stop/revoke increments the permission revision, so merely restarting or resuming cannot revive an old grant.

These are **trusted-local-owner fixture controls**, not authenticated customer authorization. The cached policy is not signed, the clock is not a secure clock, the local owner can edit files, and the ledger is not a tamper-proof audit system. On Linux the fixture root must exclude group/other access and newly created state is private. Windows ACL enforcement must be configured and reviewed separately; the candidate does not claim to validate Windows ACLs. The unchanged base CLI remains available in the source bundle but is not a production service permission boundary.

Offline operation cannot learn a remote revocation before receiving it. A production offline policy needs a verified signer, bounded offline validity, local revocation/revision handling, exact target and runbook restrictions, and a documented online freshness requirement. This candidate demonstrates the bounded local logic only.

## Run the deterministic acceptance example

Use a supported Python in an isolated review environment. No package installation is needed.

```sh
python fixture_service.py --root /tmp/clawcare-new-fixture init-fixture
python fixture_service.py --root /tmp/clawcare-new-fixture authorize-fixture --ttl 300 --max-actions 1
python fixture_service.py --root /tmp/clawcare-new-fixture once
python fixture_service.py --root /tmp/clawcare-new-fixture status
```

The first command refuses an existing directory. `once` prints a synthetic receipt. Reconstructing the service against the same directory preserves the receipt and schedule. For rollback coverage, use the automated tests; they intentionally make the independent fixture signal fail and verify exact-byte restoration.

Run all available tests:

```sh
python -m unittest discover -s tests -v
python -m compileall -q .
```

Tests create temporary files, bounded subprocesses, and the original source's isolated loopback HTTP fixtures. They do not exercise a real Gateway, contact a provider, or install an OS service.

## Optional foreground supervision, after review

```sh
python fixture_service_supervisor.py --root /tmp/clawcare-new-fixture run
```

This opt-in command runs until stopped; it does not install startup. The cached policy still expires without renewal. From another process:

```sh
python fixture_service_supervisor.py --root /tmp/clawcare-new-fixture status
python fixture_service_supervisor.py --root /tmp/clawcare-new-fixture stop
```

A service-lifetime worker lock prevents two continuous workers. A separate per-tick effect lock permits explicit policy renewal between ticks. Revoke serializes through the SQLite effect transaction, so it remains available while the worker runs. Stop requests must be observed as `STOPPED`; the request itself is not evidence of termination. An interrupted managed worker exits on its supervisor pipe closing.

`packaging/` contains review templates only. The Linux user-service template and Windows task description use explicit placeholders and a 900-second demo runtime ceiling. No installer was run, no startup registration was made, and no reboot/Windows installation test was performed. Before an actual installation, approve the specific source, runtime directory, OS account, startup behavior, file permissions, and repair scope; test graceful stop, crash, restart, sleep, disk-full, and host reboot in the selected environment.

## Read-only MCP, separate from the engine

```sh
python fixture_service_mcp.py --root /tmp/clawcare-new-fixture
```

This uses the base project's stdio JSON-RPC convention and advertises only:

- `clawcare_health` with no arguments
- `clawcare_work_order_status` with `order_id`
- `clawcare_failure_records` with no arguments
- `clawcare_workload_status` with no arguments (bounded experimental workload summaries)

It opens SQLite read-only and cannot authorize, repair, roll back, start, stop, or submit work. The four read-only tools are tested directly and through a stdio smoke test. No MCP client registration, authentication grant, remote listener, or live ExecuBot connection was created. Readouts are last-recorded evidence, not proof of current process liveness. An unfinished order's base `Control` byte status cannot be presented as verified service recovery.

## Optional online sync, future integration only

A future explicit adapter may export sanitized immutable receipts and bounded failure summaries. It must enforce audience/project authorization, least disclosure, identity-bound idempotency, local retention, and conflict handling. Receiving a work order or synced claim must never itself grant repair authority. Sync must not refresh a cached repair policy or increase its budget implicitly. Keep provider operations, credentials, spending approval, and uncertain-charge reconciliation outside the offline engine. No sync transport or provider execution has been implemented here.

## Remaining integration gates

- Transfer and inspect the actual Surface source, then map its interfaces instead of overwriting it
- Reconcile this candidate with current app storage, dashboard, work orders, identities, and the separate lookup ledger; no migration is provided for any existing production or experimental database
- Implement and review real diagnostic and repair adapters, exact reversible runbooks, external approvals, authenticated current policy, and independent Gateway health checks
- Establish real rollback/checkpoint integrity, filesystem durability, permission boundaries, bounded execution time, hung-worker detection, and cross-process cancellation for real adapters
- Add authenticated transport and per-project access if evidence leaves the local owner boundary
- Verify Linux and Windows deployment, restart/reboot behavior, multi-host architecture, prolonged offline behavior, secure time assumptions, current full-application tests, and operational monitoring

Until those gates are completed, the result is a tested fixture candidate, not a deployed monitoring service or a repaired Gateway.
