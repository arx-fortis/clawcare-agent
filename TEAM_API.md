# Authenticated multiplayer API prototype

Development increment, 2026-09-29. This is a loopback test service, not an
internet-facing production server. The installed supervisor is unchanged.

## Boundary

The service authenticates possession of an operator-issued random 256-bit bearer
credential. Its registry binds that credential to a workspace, stable player ID,
agent ID, role and expiry. Only SHA-256 digests are stored in the registry.
Identity fields cannot be supplied in a work-order request. This authenticates
a provisioned credential, not a verified real-world person or an agent binary.
Secure credential delivery and binding people to accounts are not implemented.

Each workspace has its own SQLite ledger selected by the server, never by a
client path. Named projects have separate ledgers within that workspace. Viewers
can inspect; workers can create, claim, renew and report; reviewers can additionally
review handoffs and reconcile abandoned sessions. Administrators can create
projects and manage ordinary members; owners can also manage administrators and
owners. Removing or demoting the last active owner is denied atomically.
Reviewers may review their own work; mandatory two-person review is not included.
All operations remain coordination only: no GHL, shell, repair or other external
execution endpoint is exposed.

Revocation denies subsequently authenticated requests; an already authenticated
in-flight command can finish. Token renewal for the same player/agent/workspace
preserves session identity. Do not share credentials between participants.

## Local setup

Choose a private directory outside any repository, protected by owner-only OS
permissions. This prototype relies on those permissions; it does not configure
Windows ACLs for you. The plaintext credential file must also be private.

```text
python team_api.py --root PRIVATE_DIRECTORY issue --workspace demo --player player-a --agent assistant-a --role worker --token-file PRIVATE_TOKEN_FILE
python team_api.py --root PRIVATE_DIRECTORY serve --port 8765
python team_api.py --root PRIVATE_DIRECTORY revoke --workspace demo --player player-a
```

Issue writes a new file exclusively and never prints its token. Default expiry
is one hour, maximum 24 hours. Credential issuance is offline administration;
role changes use the authenticated `member_update` operation below.
Existing credential roles are migrated to memberships; conflicting
legacy roles are reduced to viewer pending review. Provisioning cannot silently
change an existing membership's role or reactivate it.

## Workspace and project management

Bootstrap an owner with the offline `issue` command using `--role owner`. All
credential roles are looked up from the current membership on every new request.
Disabling a member also revokes their existing credentials; re-enabling membership
does not revive those credentials. Requests already authenticated may finish.

Supported command bodies:

```json
{"operation":"workspace_info"}
```
```json
{"operation":"project_create","project_id":"demo-project","name":"Demo project"}
```
```json
{"operation":"member_update","player_id":"player-b","role":"viewer","active":true}
```

All workspace members can see the workspace roster and project list. Members
currently inherit their workspace role across ALL its projects; project-specific
membership is not implemented. Administrators cannot promote anyone to admin or
owner, or alter an existing admin/owner. Membership changes and project creation
append actor-attributed administration events in the identity registry; these
administration events are not yet hash-linked or externally anchored.

Work commands optionally accept `project_id`; omitting it selects the legacy
`default` project and preserves its original ledger and session identity. A
different project cannot resolve another project's work-order ID. Resource claims
are project-scoped: do not connect the same mutable external resource to multiple
projects until global connector/resource ownership is implemented.

Adding a member does not invite them, send a message, create a verified account,
or deliver credentials. Human account signup, OIDC login, invitations and a UI
remain separate work. This increment changes local source code only.

POST JSON to `http://127.0.0.1:8765/v1/workspaces/demo/commands` with
`Authorization: Bearer <credential>`. Keep credentials out of chat, source code,
command histories and logs. Example body:

```json
{"operation":"create","resource":"fixture","objective":"Inspect fixture","acceptance":"Readback matches"}
```

Operations use the handoff engine fields documented in HANDOFFS.md. Claim and
renew require an explicit integer `ttl`; the server sets owner/reviewer from the
credential identity. Inspect requires `id`. Review requires `id`, `revision`,
`accept` and `evidence`. Unknown fields and duplicate JSON keys are rejected.
Requests are limited to 64 KiB, connections time out, and browser Origins are
denied. The server binds only IPv4 loopback, with a loopback Host check and no
CORS support. Do not expose it through a tunnel or public reverse proxy.

Codes: 200 success; 400 malformed; 401 invalid/expired credential; 403 permission
denied; 409 state/ownership/integrity conflict; 413 oversized; 503 storage busy.
Report request IDs support deduplicated retries. Create is NOT idempotent;
inspect existing state before retrying a create after an ambiguous failure.
Over 128 active connections are dropped rather than creating unlimited threads.

## Automated evidence and capacity limits

`python -m unittest discover -s tests -p test_team_api.py -v` starts an ephemeral
HTTP server and provisions synthetic identities in temporary directories. It
tests workspace isolation, role checks, expiry/revocation, forged identity,
cross-player session use, persistent identities, and attributed handoffs.

The concurrency test launches 100 synchronized HTTP clients for distinct claims,
then 100 progress submissions, then 100 claims on one contested work order.
Expected results: all distinct claims and reports succeed, all report authors
match their credentials, and the contested claim has exactly one winner.

This bounded local workload does not establish unlimited capacity, sustained
throughput, Internet security, multi-host consistency or a production SLA.
SQLite serializes writes within a workspace; the handoff engine currently scans
history. Large-history performance, PostgreSQL transactions, authenticated user
sign-in/OIDC, quotas, secure transport, operational telemetry, independent audit
anchors, credential delivery, disaster recovery and a production HTTP stack
remain required before a hosted release. Sheets/GitHub/Discord are future API
adapters, not alternate authorities.
