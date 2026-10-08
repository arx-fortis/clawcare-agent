# ClawCare — background reliability work orders

## Experimental upgrade checkpoint

The original standalone monitoring/control plane remains below. This branch adds a bounded synthetic offline service, optional lookup ledger, workload protection policies, and a [bounded cooperative tiny-file worker](COOPERATIVE_WORKER.md). Start with [upgrade scope and launch gates](UPGRADE_READINESS.md), [fixture service](START_HERE_SERVICE_CANDIDATE.md), and [lookup ledger](LOOKUP_LEDGER.md). These additions are source-level candidates, not a launch or deployment claim. The newer thermostat, Gateway lifecycle, dashboard, and pairing/relay bundle is still pending source reconciliation. Historical release notes and demo remain available.


ClawCare watches HTTP health endpoints independently of the monitored OpenClaw Gateway. When a check fails it opens one durable support case, records inspection evidence and a work order, and tracks the case through approval, verification and handoff. Closing chat does not close the worker's cases.

**Start here: [User-owned setup](GETTING_STARTED.md).** Connect your existing OpenClaw agent and its own model account, or use the work-order system without AI. No founder API key, shared model account or automatic billing fallback is supplied. The core and connector require no third-party Python dependencies.

Version 0.3.1 adds authenticated local team handoffs, a six-tool MCP adapter and user-owned setup. See [release notes](RELEASE_0.3.1.md). Hosted signup, remote multiplayer deployment, contest usage reporting and real Gateway repair remain unverified or unimplemented. Automated fixtures are not real installs or contest activity.

## Standalone control plane — development increment, 2026-09-29

Version 5 makes the standalone core the first priority. Discord, OpenClaw and
other coordination systems are optional adapters. The `control.py`
increment performs one real, bounded JSON Boolean repair with checkpointed bytes,
expiring scoped approval, drift checks, verification, separately approved rollback,
pause/revocation, crash reconciliation and sanitized handoff export. See
[CONTROL_PLANE.md](CONTROL_PLANE.md) for commands, evidence and limits.

Tests use isolated fixtures, not production admission or Gateway-recovery evidence.
The old 0.2.0 demo describes the monitoring/simulation baseline.
`clawcare.py repair` remains simulated; `control.py execute` has real
filesystem effects and requires a dedicated managed directory.

## Supervised background worker — development increment

`supervisor.py` provides single-worker protection, bounded restart/backoff,
persistent stop requests, and orphan cleanup when its supervisor exits. The
suite includes real isolated worker/supervisor crashes. See [SUPERVISOR.md](SUPERVISOR.md)
for operation, Windows sign-in startup, and limits. Use current source or 0.3.0
for supervision rather than the historical 0.2.0 ZIP.

## Run locally

Install Python 3.11 or newer. Extract this package into a writable directory. From that directory:

```sh
python clawcare.py add http://127.0.0.1:18789/health --interval 30
python clawcare.py worker
```

Use `py -3.14` instead of `python` on Windows if needed. Set `CLAWCARE_DB` to an absolute persistent SQLite path before starting; otherwise the database is created in the current directory. The default worker scheduling tick is one second; targets are checked at their configured interval. HTTP requests time out after five seconds. Use only endpoints you own or are authorized to monitor, without credentials or query strings.

In another terminal:

```sh
python clawcare.py list
python clawcare.py audit CC-YOUR-CASE-ID
python clawcare.py checkpoint
python clawcare.py approve CC-YOUR-CASE-ID --actor your-name
python clawcare.py repair CC-YOUR-CASE-ID
```

`repair` records a **simulation with no external effect**, then checks health. A failed verification leaves `RECOVERY_REQUIRED`. Returning health closes the case with an external-recovery handoff, never a claim that the simulation repaired it. A simulation approval is single-use. To deliberately retry, run `retry CASE-ID`, then approve again. A healthy check can also close an unused approved case.

`checkpoint` uses SQLite's backup API to create a consistent ledger snapshot under `checkpoints/`. This protects case records only: it is **not** a Gateway configuration/session checkpoint or a tested automatic restore. Retain snapshots privately. Event records are append-only through normal commands, not tamper-proof against a database administrator. Actor names are local operator labels, not authenticated identities. Run one worker per database; multi-worker leases are future work.

## Independent background supervision (Docker)

The supplied Compose configuration keeps the worker separate from OpenClaw and retains data across worker recreation. Docker must already be running. Container-local `127.0.0.1` refers to the container, not your host; choose an endpoint reachable from the worker's network. On Docker Desktop, a host service may be reachable through `host.docker.internal`, depending on its binding/firewall.

```sh
docker compose build
docker compose run --rm clawcare add http://host.docker.internal:18789/health --interval 30
docker compose up -d
docker compose exec clawcare list
docker compose logs --tail 50
docker compose stop
```

Restart policy: `unless-stopped`; CPU/memory/log bounds are configured. There are no published ports or Docker socket mounts. Closing your terminal leaves Docker running. A host shutdown still stops monitoring until Docker starts again. Compose packaging requires validation on the deployment host; it was not exercised on the release author's machine.

## OpenClaw integration

Place this folder at `skills/clawcare` inside your OpenClaw agent workspace. The root `SKILL.md` defines the case workflow. Python monitoring remains separately supervised; do not launch it as an agent turn that dies with the Gateway. In a properly scoped agent environment, allow the agent to inspect `list` and `audit` output. Keep repair approvals with the authorized operator. This package does not change OpenClaw permissions or install messaging channels automatically.

## Tests and demo

```sh
python -m unittest discover -s tests -v
```

The suite covers monitoring, checkpointed fixture repairs, supervision, authenticated team handoffs, MCP transport and user-owned setup. Fixtures are not evidence of production OpenClaw repair. See the repository Actions tab for current CI results; `RELEASE_STATUS.md` and `DEMO.md` retain historical release evidence.

## Privacy and scope

No telemetry is sent by this worker. Targets and case evidence stay in SQLite. Protect that directory with operating-system permissions. No secrets should be placed in target URLs or actor labels. No shell repair, destructive reset, chat delivery or cloud account access is implemented.

MIT licensed; see LICENSE. Based on the founder's reusable inspect → diagnose → checkpoint → approve → execute → verify → audit → handoff pattern. No private CRM data or credentials are included.

## Standalone team foundation

The package includes the attributed handoff engine
([HANDOFFS.md](HANDOFFS.md)) and loopback credential-authenticated team API
([TEAM_API.md](TEAM_API.md)). They provide work-order claims, handoff review,
workspace roles and separate project ledgers. These are local prototypes; installed
background workers and production accounts are not automatically updated. The MCP
connector is available on main. Human signup/login, invitations, hosted UI and
external business-tool connectors are not yet implemented.
