# Standalone handoffs — development increment, 2026-09-29

Status: local trusted-owner prototype. No hosted service, authenticated team
identity, Sheets synchronization, GitHub App, or Discord integration is deployed.
Existing client sheets and production systems are unchanged.

## Player and agent attribution

Every new handoff-engine event (schema version 2) includes `actor.player_id`,
`actor.agent_id`, identity source, and authentication status in the hashed payload.
Create, claim, progress, renew, handoff, review, and recovery are attributed to
the caller. Automatic expiry is attributed to the system, not whoever observed
it. UTC receipt time, event ID, work-order ID, and session reference when
applicable remain separate. Review does not change the original report author.

Pass global `--player-id player-a --agent-id assistant-a` before the command.
Reuse these stable IDs across calls. Defaults identify the local OS username
and `local-cli`; owner/reviewer display labels remain separate from player IDs.
A claimed session binds both player and agent; differing identities cannot
write, renew, or replay that session through this API. This is consistency
checking, NOT authentication: the trusted local operator can choose these labels.
No roles, remote identity provider, or approval authority is added here.

Inspection includes full attributed `audit_events` and report actors. Older
events remain unchanged; legacy reports show `legacy_unattributed` rather than
inventing an author. Legacy active sessions must expire and be reconciled before
being claimed anew. This attribution applies to the handoff engine; the separate
repair controller has not yet been migrated to this actor schema.

## Reusable workflow

Create work order → claim resource → inspect external state → record progress →
submit handoff → review evidence → complete and issue one successor, or return
the same order to the queue. A claim grants coordination ownership only; it
never grants repair or external execution authority.

The reusable concepts are work orders, sessions, change evidence, checkpoints,
exact stopping points, approval holds, and a verified next step. Client names,
customer data, business rules, and historical client rows are not included.

## Local use

Run `python handoffs.py --help`. Use `--db PATH` for a private local ledger.

```text
python handoffs.py --db demo.sqlite3 create demo-resource "Inspect fixture" "Readback matches expected state"
python handoffs.py --db demo.sqlite3 claim BUILD-ID --owner operator-a --revision 0
python handoffs.py --db demo.sqlite3 inspect BUILD-ID
```

Use the returned session and revision for progress/handoff writes. Submit a JSON
file via `--report`, with a stable `--request-id` for safe retries. Progress
requires exactly these list fields:

```json
{
  "completed": ["Synthetic fixture inspected"],
  "remaining": [],
  "blockers": [],
  "verification": ["Fixture read back and matched expected state"],
  "checkpoint_refs": ["fixture-snapshot-001"],
  "recovery_notes": ["Read-only inspection; no restoration required"]
}
```

A handoff additionally requires `next_work_order`: null, or an object with
`objective` and `acceptance`. Verification and recovery lists must be nonempty.
Checkpoint references are references, not proof that a snapshot exists.
Review is explicitly a local operator attestation, not automated GHL validation.
Unfinished or blocked work cannot be accepted as completed.

## Guarantees within the local trust boundary

- SQLite transactions serialize claims for the same normalized resource.
- Revisions reject stale writes; session leases can be renewed explicitly.
- Expiry moves an order to REVIEW_REQUIRED and retains its resource lock.
- Recovery requires attestation that the prior session stopped and state was
  inspected. ClawCare does not stop another person's ChatGPT session.
- Identical request retries are deduplicated; changed content with the same
  request ID is denied. Review creates at most one successor.
- Events use UTC timestamps, generated IDs and versioned canonical JSON.
  SHA-256 covers previous hash, newline, and canonical event payload. Reports
  are anchored by their content hashes. Detected corruption blocks continuation.

## Limits and next engineering steps

This is not an immutable or independently anchored audit system. A local owner
can rewrite the database, its materialized state, and the entire hash chain, or
truncate its tail. Hashes do not authenticate an operator. All current history
is scanned for validation; this is intentionally not a scalable storage design.
Expiry maintenance runs on interaction or explicit Python `Handoffs.sweep()`;
it is not yet wired into the installed background supervisor.

Before hosted team use: authenticated principals, tenant isolation, transactional
PostgreSQL storage, separately protected signed checkpoints, resumable event
delivery, tested backup restoration, quotas, and adversarial security testing.
Adapters must submit typed commands to this engine instead of directly editing
its tables. A shared sheet can remain a view and controlled input channel.

Historical spreadsheet import must preserve raw rows separately, identify schema
versions, quarantine shifted columns and inconsistent IDs, and label pre-hash
history honestly. Never fabricate old hashes, timestamps, or verification.
No importer or migration of existing client data is included in this increment.
