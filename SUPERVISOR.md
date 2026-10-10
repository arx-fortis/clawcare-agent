# Independent supervisor — version 5 development increment

The supervisor runs as a separate process from the monitored Gateway. It starts
only the packaged ClawCare HTTP monitoring worker; it never executes a repair.
The local CLI works without any chat or execution-framework dependency.

```sh
python supervisor.py --db /private/path/clawcare.sqlite3 run
python supervisor.py --db /private/path/clawcare.sqlite3 status
python supervisor.py --db /private/path/clawcare.sqlite3 stop
```

`stop` persists a stop request, pauses the control plane and revokes its grants.
Check `status` for STOPPED; the request itself is not a stop acknowledgement.
`run` respects an existing stop request and an exhausted restart budget.
`start` explicitly clears the stop request/restart budget and runs in the
foreground. It does **not** unpause repairs or restore old approvals. Use
`control.py resume` separately after review, then issue new scoped approvals.

Two OS locks prevent duplicate supervisors and duplicate workers for the same
ledger, including a worker started directly through `clawcare.py worker`.
These are trusted-local-owner controls, not hostile-user authorization.
The managed worker holds a pipe from its supervisor; EOF ends the worker if its
supervisor is killed abruptly. No stale PID is used to kill an unrelated process.
Status PIDs are evidence from the last heartbeat, not proof of current liveness.

Worker failures, including failed process starts, consume a durable restart
budget. Default: five failures, backoff 1/2/4/8/16 seconds, capped at 30 seconds.
After 60 seconds continuously running, the failure count resets. Exhaustion
records EXHAUSTED and exits without erasing the budget. Relaunching `run` cannot
silently defeat this limit. Heartbeats do not create audit events every tick.

## Windows sign-in startup

Run `install-startup.ps1 -PythonExe C:\path\to\python.exe` using Windows PowerShell.
It creates a new owner-only runtime directory, copies the four required modules,
initializes a paused control plane with no monitoring targets, and registers the
least-privileged current-user task `ClawCare-Standalone-Supervisor`. Existing tasks
are never overwritten. It uses `pythonw.exe` and opens no terminal window.

The task starts at **user sign-in after reboot**, not before login, and does not
need an account password. Task Scheduler retries a failed supervisor up to three
times, one minute apart; the worker's separate persisted budget still applies.
Do not claim a real reboot test unless one was performed. Sleep/shutdown suspends
monitoring; this is not an always-available cloud service.

The installer prints the exact runtime and database paths and stores a private
`installation.json`. Add authorized health targets using the installed
`clawcare.py` with `CLAWCARE_DB` set to that database. No targets are guessed or
imported from private projects. With zero targets, a running worker is idle.
Use that runtime's `supervisor.py stop` for a persistent stop. To resume in the
background, first wait for STOPPED, then run `supervisor.py --db DATABASE enable`
and start the scheduled task. Alternatively run the documented `start` command
in a controlled session; `run` alone will
not undo a stop. Do not delete a database or reset approvals to force restart.

## Planned macOS and platform adapter supervision

Apple Silicon Mac mini support is a proposed extension; no Mac startup installer or unattended-host validation is supplied here. Keep one platform-neutral stop/checkpoint/recovery contract and separate OS startup adapters. A reviewed macOS launchd agent/service is a candidate to evaluate against the actual user-session needs; the Windows Task Scheduler setup above must not be applied to a Mac.

Before any activation, obtain the specific install/autostart/access authority and verify the exact binary/runtime, owner, permissions, working directory, stop latch and removal path. Test login/unlock boundaries, process/host restart, sleep/wake, denied access and safe revocation. Intentional stop or disconnect must survive supervisor restart; it must not trigger automatic reconnection. Do not change sleep/security settings to imply always-online operation.

A live supervisor is only process evidence. Phone-away availability additionally needs a working authorized transport and the actual operation's browser/app control and authenticated session. See [capability distinctions](SYSTEMS_RELIABILITY.md#phone-away-control-and-capability-evidence) and [platform acceptance](UPGRADE_READINESS.md#platform-readiness-and-mac-mini-acceptance). This documentation installs or enables nothing.

## Evidence and remaining limits

Tests kill isolated workers/supervisors, confirm restart and orphan exit, preserve
one incident across restart, preserve pause/revoked approvals, exercise a durable
restart ceiling and exclude competing workers. The HTTP fixture and files are
synthetic. No customer system or live Gateway is damaged for these tests.

The supervisor currently monitors process exit, not an unresponsive live process.
No hung-worker watchdog, kernel sandbox, authenticated remote control, general
session handoff coordinator or production admission enforcement is claimed.
The control-plane pause gates real repairs; read-only monitoring can continue
while repairs are paused. Existing simulation approval records belong to the
legacy monitor namespace and cannot authorize `control.py execute`.
