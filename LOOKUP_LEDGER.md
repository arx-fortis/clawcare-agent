# Optional lookup ledger

Status: optional dependency-free library included in the experimental source checkpoint. It is not wired to a provider, authenticated server, dashboard, or multi-device transport. Use a fresh database; no migration is supplied. No provider calls or spending are needed for these tests.

## Run

From the repository root:

    python -m unittest discover -s tests -v
    python -m compileall -q clawcare_ledger tests

## Execution contract

1. The trusted server authenticates the request and derives `Scope(tenant, account, access_context, permission_revision)` from current authorization. Never accept an arbitrary scope supplied by a dashboard/browser or worker. Rotate permission_revision when grants change. Artifact access must also be rechecked at dereference time.
2. Build `Lookup(provider, operation, adapter_version, parameters)` with the **complete effective provider request**: target/query, output formats, extraction query/schema/prompt, locale, freshness/cache settings, model, defaults, and every result-affecting option. Object-key order is canonicalized; strings, array order, case, and numeric representations are preserved conservatively. Do not drop meaningful options to improve the apparent hit rate. Provider defaults should be materialized by the adapter; bump adapter_version on semantic changes.
3. Pass opaque non-secret agent/device/work-order IDs in `Actor`. Call `claim` before any provider invocation. Only a response containing `execution_token` permits this caller to invoke the provider. A pending response without a token is a join/wait, never execution permission. `cached_fresh` means local reuse with no provider invocation. `cached_stale` is inspectable; claim acquires a refresh. `refresh=True` bypasses a fresh cache but still joins an existing execution. Failed attempts require `retry_failed=True`.
4. Store sanitized result bodies in an **access-controlled artifact store**, then `complete` using an opaque result reference plus evidence provenance. The ledger stores no page body. Result kinds distinguish `full_page`, `derived_answer`, `structured`, and `search_results`; `derived_from` records upstream opaque artifact references. Metadata is not proof those artifacts exist: the integration must verify existence and current access before accepting or using the reference. An unavailable artifact must not be presented as a usable hit. There is no automatic cross-format derivation: a full page may support an adapter-verified local extraction later, but a query-specific answer is not a full page.
5. Freshness expires at the **oldest evidence observation time plus TTL**, not time of recording. Use actual provider observation time. Evidence with future times is rejected. Historical records with unknown times or missing bodies are audit-only and must not be inserted as successful reusable results. `ttl_seconds=0` is immediately stale.
6. `fail` records a bounded non-secret outcome code, not raw provider errors. Credits remain null/unknown unless actually reported, including failures. A failed refresh stays visibly failed with an optional older result; it is never silently promoted to successful cached data.
7. Persist provider-reported credits independently of any provider cache flag. A provider-side cache hit may still charge credits. Local reuse has no new execution action. Totals are grouped by provider, not summed across incompatible credit systems. Provider IDs must distinguish products with different credit units. Unknown charge counts are visible; no dollar cost or savings is fabricated.
8. Use `reconcile_billing` for later authoritative per-action **total** credits, with a stable opaque receipt ID and compare-and-set billing revision. Retries of the same receipt are idempotent. This preserves the failed/abandoned state and cannot resurrect a result.

## Crash and concurrency behavior

SQLite `BEGIN IMMEDIATE` and a partial unique index serialize claims across processes on the **same host/database**. Claim timestamps are taken after acquiring the write lock. Read views use a consistent transaction snapshot. Execution ownership is fenced by an action-specific token; only its hash is persisted. Identical completion replay does not create a second result or bill twice. Conflicting replay is rejected.

A process restart preserves entries and pending leases. **An expired lease does not mean the provider did nothing or charged nothing.** It is not automatically stolen. Reconcile the provider execution first, then explicitly call `abandon_expired` if necessary. A later `retry_failed=True` creates a new attempt; the old worker is fenced from completion. Provider calls themselves are not exactly-once: use provider idempotency where supported and disclose duplicate-spend risk before retrying uncertain executions. `renew` can extend a pending worker's lease.

Use a central authenticated service for multiple devices; do not copy SQLite files to devices or put the database on a network filesystem. There is no HTTP service, cross-device transport, production migration, or distributed DB implementation in this increment.

## Privacy and deployment requirements

On POSIX, new DB files are created mode 0600. Windows mode bits do not establish owner-only ACLs; configure and verify the containing directory and database ACLs separately before use. This module does not enforce Windows ACLs. Use a private parent directory with normal application backup/retention policy; existing DB permissions are not changed. Host administrators and code with DB access are trusted. This is a logical scoped ledger, not row-level security or a tamper-proof forensic audit system.

Never provide credentials in lookup parameters, IDs, provenance, or errors. The adapter must allowlist non-secret result-affecting parameters and redact upstream content before persistence. Parameters are hashed, not stored, but SHA-256 pseudonyms are **not encryption** and low-entropy values can be guessed. Credentials belong in the existing secret store outside the ledger. Evidence persists only an HTTPS origin and a hash of the source URL; paths, userinfo, query strings, and fragments are omitted. Only opaque artifact references are accepted, so signed/secret URLs cannot enter result references. Origin hostnames and non-secret IDs still reveal metadata and need normal access controls.

The module is intended for read-only research lookups. Do not deduplicate arbitrary side-effectful tools (purchases, writes, messages) using this cache contract. Generic activity logging for other tools remains an integration task.

## Dashboard contract (implemented serializer, no integrated UI)

`dashboard(scope)` returns schema_version, lookups, actions, events, and billing.

- `lookups[].state`: `cached_fresh`, `cached_stale`, `pending`, `failed`, or `missing`
- Pending: show action ID, lease deadline and `lease_expired`; label expired pending as “needs reconciliation,” not completed/failed/free automatically
- Failed refresh: show failed status and old evidence separately with its actual `fresh` flag
- Result: ID, source action, opaque artifact reference, kind, derived-from references, evidence hashes/origin/observation time, created/expiry timestamps
- Action: provider/operation/adapter, agent/device/work order, start/finish/lease time, outcome, credits, billing status/revision
- Events: ordered append-only sequence through this API, attribution, timestamp, event kind, bounded details; cache reuse and in-flight joins are included
- Billing: per-provider reported-credit totals; unknown action count; currency_cost and estimated_savings are null
- Execution tokens are never returned by dashboard or inspect

Integration acceptance: current-source adapter tests, authenticated scope derivation, permission-change tests, artifact-existence/revocation checks, provider idempotency mapping, full app test suite, UI state rendering, and multi-device service testing are still required. No claims of an integrated dashboard or full app test pass are made.

### Final review notes

Independent review found and verified fixes for write-lock and read-lock freshness races, inconsistent dashboard snapshots, malformed IPv6 origins, and missing billing reconciliation. The final suite includes regression coverage for both lock timing races. This prototype requires a **fresh database**; it supplies no migration from earlier experimental schemas even if they also used schema version 1. Keep existing production storage unchanged until a current-source migration is designed and tested. Security boundaries depend on the integrating service and artifact store; this candidate is not a production security certification.
