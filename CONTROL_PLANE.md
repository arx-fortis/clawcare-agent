# Version 5 scope: standalone control-plane increment

Implemented 2026-09-29 against the universal standalone scope. No model, phone
line, Discord, OpenClaw, Plow or other framework is required. `control.py` adds
explicit work orders and a bounded repair adapter to the existing SQLite ledger.
The original monitor and its simulation-only `repair` command remain unchanged.

## Supported repair

Change one existing top-level Boolean field in a managed JSON configuration,
maximum 64 KiB. The JSON is reserialized; other semantic values are preserved.
The original exact bytes are checkpointed in SQLite before approval. Approval
binds the target, field, desired value, optional health probe and before/after
hashes, expires within 15 minutes, and is consumed before the filesystem effect.
An HTTP probe, when supplied, must also succeed before VERIFIED is recorded.
Without a probe, VERIFIED means configuration bytes match, not service health.
Rollback needs a new approval and verifies restoration of the checkpoint bytes;
it does not imply restoration of service health.

## Local workflow

Use a private ledger outside the managed directory. Only the trusted local owner
should have access to both. Checkpoints contain original file contents, which may
contain secrets; do not publish the database or checkpoints.

```sh
python control.py --db private.sqlite3 init /path/to/managed-configs
python control.py --db private.sqlite3 propose service.json enabled true --probe http://127.0.0.1:8080/health
# Review the target, exact change and returned scope before approving.
python control.py --db private.sqlite3 approve WO-ID --scope RETURNED-SCOPE --ttl 300
python control.py --db private.sqlite3 execute WO-ID
python control.py --db private.sqlite3 handoff WO-ID
# If rollback is needed, review rollback_scope from the handoff:
python control.py --db private.sqlite3 approve WO-ID --action rollback --scope ROLLBACK-SCOPE
python control.py --db private.sqlite3 execute WO-ID --action rollback
```

`pause` persistently blocks mutations and revokes outstanding approvals. `resume`
does not restore them. `abort WO-ID` prevents further execution, but does not undo
effects that already happened. Each operation is bounded; pause waits for any
active local transaction/health request to finish (HTTP timeout is five seconds).
It is not a process kill switch.

After a crash, an EXECUTING order never replays automatically. `reconcile WO-ID`
records whether current bytes match the before/after checkpoint or have drifted,
and marks RECOVERY_REQUIRED. Inspect the result before separately approving any
rollback. Do not infer success from the file write alone.

Handoff JSON includes durable order ID, status, hashes, attempts and ordered audit
events. It excludes configuration bytes, target paths and health URLs. It is
replayable evidence for the next operator, not an executable authorization token.

## Evidence and limits

Tests exercise actual local file effects, a real HTTP service reading the setting,
byte-exact rollback, changed-target refusal, missing/wrong/expired approvals,
pause/revocation/abort, single approval consumption across competing processes,
corrupt checkpoint refusal, and subprocess crash after a file effect. Existing
worker restart/recovery tests remain intact. Fixtures are isolated and synthetic;
no customer, GHL, production service or OpenClaw configuration was changed.

This is a local trusted-owner prototype, not production admission enforcement.
It rejects links/reparse points and checks hashes, but cannot protect against a
hostile process with the same filesystem/OS privileges (including path-swap races
or direct ledger tampering). The local username is attribution, not separate
multi-user authentication. Audit is append-only by convention, not tamper-proof.
Raw checkpoint storage is not encrypted by this program. JSON byte replacement
does not preserve all filesystem metadata such as ACLs/xattrs; use this adapter
only for dedicated managed configuration fixtures until an application-specific
adapter defines and preserves the required metadata.

Still pending: independent OS supervisor deployment, admission/quarantine and
capability inventory, generic task/session ownership and cross-user handoff,
authenticated roles, full recovery for arbitrary execution workers, and Discord.
These tests do not prove the entire version 5 acceptance gate or contest eligibility.
