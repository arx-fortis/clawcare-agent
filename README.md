# ClawCare — background reliability work orders

ClawCare watches HTTP health endpoints independently of the monitored OpenClaw Gateway. When a check fails it opens one durable support case, records inspection evidence and a work order, and tracks the case through approval, verification and handoff. Closing chat does not close the worker's cases.

**Release 0.2.0: working monitoring and ledger; repair is simulation-only.** No API key, model call or third-party Python dependency is required for this worker. The accompanying OpenClaw skill supplies the support-engineer operating contract. Multiplayer, Agent Index reporting and actual Gateway repair are not configured by this package.

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

Five tests cover deduplication/persistence, approval/retry, snapshot integrity, input validation, and a real loopback HTTP fixture with worker termination/restart and observed recovery. Fixtures are not evidence of production OpenClaw repair. See `RELEASE_STATUS.md` and `DEMO.md` for evidence and submission limits.

## Privacy and scope

No telemetry is sent by this worker. Targets and case evidence stay in SQLite. Protect that directory with operating-system permissions. No secrets should be placed in target URLs or actor labels. No shell repair, destructive reset, chat delivery or cloud account access is implemented.

MIT licensed; see LICENSE. Based on the founder's reusable inspect → diagnose → checkpoint → approve → execute → verify → audit → handoff pattern. No private CRM data or credentials are included.
