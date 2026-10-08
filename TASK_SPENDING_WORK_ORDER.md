# Work order: task-level provider credits and spending

Work order ID: CC-SPEND-001  
Date: 2026-10-08  
Status: proposed implementation handoff; documentation only, not implemented or deployed  
Review baseline: `2deed2ceced61cc63df43e02268d74df0e8d739d`, draft PR #1

## Outcome and ownership

ClawCare must answer: **which task used which provider credits, why, through which agent, and what did it cost?** Show confirmed charges, estimates, outstanding exposure and unexplained usage separately.

Delivery sequence: **dot defines the work order and reviews evidence → OpenClaw orchestrates the bounded implementation work → Cursor writes and tests the code → dot reviews the resulting draft PR.** This document does not authorize paid calls, purchase of credits, account changes, merge, deployment or production-data import. Do not start coding through a different executor as a side effect of this handoff.

Before implementation, OpenClaw must reconcile the current application source and dashboard revision with this branch. The newer dashboard, Gateway and pairing/relay source remains outside this checkpoint. Do not replace it with a speculative implementation.

## Existing foundation and boundaries

Read [LOOKUP_LEDGER.md](LOOKUP_LEDGER.md), [UPGRADE_READINESS.md](UPGRADE_READINESS.md), and `clawcare_ledger/` first. Reuse or deliberately migrate the existing scoped claims, provider-specific credit totals, local-reuse distinction, unknown charges and receipt-based reconciliation; do not introduce a second source of truth that counts the same execution twice.

The existing library is a same-host SQLite lookup ledger, not an integrated provider connector, authenticated dashboard or distributed budget service. Its execution lease is not a spending reservation. Its current tests do not establish this work order's acceptance.

An app ledger observes only instrumented paths. Provider/account statements may expose broader totals, but cannot necessarily identify external tasks. Unsupported SDKs, personal accounts, third-party clients and direct provider calls remain outside ClawCare's enforcement unless separately routed through an enforced boundary. Label this coverage explicitly. Never claim account-wide prevention from app-only controls.

## MVP scope

1. Durable append-only usage events and materialized read models linked to existing work orders, tasks and lookup actions.
2. A shared admission/reservation interface for instrumented provider adapters, including delegated workers and asynchronous jobs. Prove it first with a synthetic adapter; select the first real adapter only after source reconciliation.
3. Task/provider/agent spending views, request-level drilldown, filtered CSV/JSON exports and explicit unknown/unattributed buckets.
4. Scoped provider-balance snapshots and reconciliation reports, including periods, grants, expiration and unexplained differences.
5. Atomic budgets and stop controls, with honest labels for enforced, observe-only and unsupported paths.

The MVP must not attempt currency trading/conversion, invoice payment, account-wide network interception, arbitrary process killing, automatic top-ups, speculative task attribution, or retroactive recovery of unavailable historical request detail. Live provider rollout is a separate reviewed gate.

## Data and attribution contract

Use immutable opaque identifiers. The trusted service derives account/tenant authorization; clients cannot select an arbitrary scope.

- Identity: event ID, schema version, tenant/account scope, work-order ID and revision, root task ID, executing task ID, parent task ID, run ID, agent/worker ID, provider/product, operation and adapter version.
- Execution: logical request ID, attempt ID, retry-of attempt, idempotency key reference, existing lookup/action ID where applicable, provider request/job ID when available, and stable provider receipt/line-item identity.
- Explanation: bounded purpose code plus sanitized human-readable purpose; opaque resource/artifact reference or approved sanitized origin. Do not persist request bodies, prompt contents, full URLs, query strings, signed links, customer/property details, credentials or raw errors.
- Time: occurrence, recording and provider observation timestamps; provider billing period, timezone, source scope and snapshot freshness.
- Measurement: quantity, explicit unit namespace and product (credits, tokens, pages, seconds, etc.), measurement source, estimate/confirmed/unknown status and confidence where useful.
- Money: nullable decimal amount, ISO currency, valuation basis (provider-billed versus locally calculated), price-card/version reference, effective date and relevant tier/discount assumptions. A calculated amount remains an estimate even when its underlying credit quantity is provider-confirmed.
- Audit: actor, event kind, causal/correlation reference, receipt revision and append-only correction/refund linkage. Mutable task display names do not change historical attribution.

Never add heterogeneous credits, tokens or currencies into one unlabeled total. No price implies unknown monetary cost, not zero. Use fixed precision decimals or integer minor units with declared scale, never floating-point financial accumulation. Retain immutable identity; attribution corrections are new linked events with reviewer and reason, not silent rewriting. Historical data lacking an ID stays explicitly unattributed.

Distinguish execution ownership from reuse: a locally cached result may be consumed by another task with zero new provider execution; reference the original charged task and record the reuse relationship. Do not charge the original provider cost again or invent cash savings.

## Event accounting and state machine

Keep execution state, billing state and reservation state separate.

Suggested event kinds: request_planned, reservation_held, dispatch_intent, provider_accepted, usage_reported, billing_corrected, refund_confirmed, reservation_adjusted, reservation_released, local_reuse, admission_denied and reconciliation_recorded.

1. Persist attribution and atomically hold a conservative reservation before dispatch. Commit a durable dispatch intent and fenced permit. A reservation is exposure, not spent credits.
2. Record provider acceptance and request/job identity. For timeouts or crashes, preserve the possible execution and reserved exposure as uncertain until reconciled. Never infer free usage from failure, missing response, expired lease or missing heartbeat.
3. Record provider-reported actual usage only with provenance. Provider cache hits can still charge. Local cache hits have no new provider charge. Retries receive distinct attempt IDs and reservations; link them to the logical request.
4. Normalize whether provider receipts express deltas or cumulative totals. Deduplicate by scoped provider/product/receipt identity and revision. Replayed receipts, polls, completion callbacks and restarts must not double-charge. Conflicting payloads at the same identity/revision become reconciliation errors.
5. Settle a reservation against confirmed actuals transactionally, releasing only the unused portion supported by evidence. Adjustments and refunds append linked events and cannot resurrect failed results. A pending refund is not available credit.
6. Actual charges may exceed estimates or configured limits. Record the full actual amount, expose the overrun, then block further admission under policy; never cap the recorded charge to make a budget appear satisfied.
7. Late or out-of-order receipts must converge to the same final totals. Preserve both original billing period and received-at time. Corrections must not silently restate previously exported snapshots.

Asynchronous jobs hold reservations until terminal billing evidence or a reviewed reconciliation decision establishes the remaining exposure. Job completion alone may precede final billing. Use bounded polling/backoff and separate poll charges when billable. Stale jobs enter needs-reconciliation, not automatically refunded/free. Cancellation is requested and then confirmed separately; cancelled jobs may still incur charges. An uncertain submission is never blindly resubmitted. Use provider idempotency when supported and disclose its limits.

## Budget and stop-control contract

Define independent task, provider/account and global budget policies. Limits are typed by unit/currency and time window. A global monetary budget is enforceable only where every admitted request has a compatible conservative monetary bound; otherwise block unknown-priced work under that budget or require a separately approved bounded policy. Do not invent cross-currency conversion or add incompatible credits.

- Admission must atomically check all applicable policies and reserve against each, using confirmed net spend plus outstanding exposure without double-counting settled reservations.
- Parallel workers share one authoritative allocator. Same-host transactions are sufficient only for that scope; multiple devices require a central authenticated allocation boundary, not copied SQLite files.
- Use versioned/fenced permits bound to task, agent, provider, operation, amount and policy revision. Recheck permit and stop state at the instrumented dispatch boundary. Workers cannot evade limits through child tasks, retries, restarts or a new run ID; delegated tasks inherit the root policy.
- Stop controls exist at task/root, provider/account and global scope. A committed stop denies subsequent admissions and not-yet-dispatched permits through that boundary. Serialize stop versus dispatch authorization and document that linearization point.
- Already dispatched/in-flight work may finish and be charged. Request provider cancellation only where supported and authorized; do not promise instantaneous interruption or retroactive cancellation.
- Ledger/control-plane unavailability, stale authorization, unknown required prices or missing attribution fails closed for enforced paid dispatch. Read-only history remains available if safe.
- Restart preserves reservations, stops, policy revisions and uncertain dispatch. No automatic reset or free retry.
- Threshold notifications should be deduplicated; warning thresholds must not substitute for hard admission checks. Policy edits, stop/resume and reconciliation overrides require authenticated authorization and an audit event.

Expose each adapter's coverage and enforcement capability in the UI. A direct SDK call that bypasses the boundary is not stopped by this feature. Stronger account-wide enforcement would require a separately designed credential/proxy/provider limit architecture and security review.

## Dashboard and exports

Provide a Spending view with an explicit period/timezone and data-freshness indicator.

- Summary: confirmed credits by provider/product/unit, provider-billed money by currency, locally valued estimates, open reservations, pending/unknown charges, refunds and unexplained account-balance differences.
- Breakdown: task/work order, root/delegated task, agent, provider, operation and date; show top spenders without mixing units.
- Task detail: purpose, sanitized resource, request/attempt timeline, actual versus estimated usage, monetary valuation source, cache reuse, retries/failures, async status, outstanding exposure and budget denials.
- Coverage: enforced versus observe-only versus unsupported, last successful reconciliation, missing statement scopes and unattributed usage. Do not hide unknown records from totals or filters.
- Controls: authorized budget edits and stop/resume with visible scope and in-flight warning. Read-only users cannot mutate policy.
- CSV/JSON: same authorized scope and filters as the screen; include schema version, generation time, snapshot/revision, units/currency, valuation status and coverage. Protect CSV against spreadsheet formula injection. No public export links or unsanitized metadata.

Read models and exports must use consistent snapshots, deterministic aggregation and bounded pagination. Parent-task rollups count descendants once; displaying a child separately must not increase account totals.

## Account reconciliation

Store scoped provider balance snapshots with source, observed-at, period, timezone and freshness. Reconcile only comparable units and account/product scopes:

Expected closing balance = opening balance + purchases/top-ups + grants + confirmed credit refunds + explicit adjustments - confirmed consumption - expired grants.

Represent subscription renewals, grant buckets and expiry rules explicitly; use provider ordering/allocation evidence where available. Do not assume all balance changes are consumption or that credit balances are cash. Account cash charges and credit purchases/consumption are different measures and must not be double-counted.

Report expected versus observed closing balance, attributable usage, provider-confirmed but unattributed usage, residual discrepancy and explanatory events. Imports are idempotent. Scope/time gaps, delayed posting, shared accounts and unavailable request-level detail remain visible. Never distribute a residual across tasks just to force reconciliation to zero. Unknown balance means unknown coverage, not a successful match. Keep account reconciliation separate from per-request billing truth.

## Synthetic verification and acceptance criteria

All development tests use synthetic accounts, tasks, receipts and prices, isolated temporary storage and a fake clock. No billable integration tests, real keys, production ledgers, customer data or provider calls.

MVP acceptance requires evidence for the exact reviewed commit:

1. Two root tasks with delegated workers and multiple providers produce correct task/agent/provider drilldowns; every dispatched attempt has immutable attribution and a sanitized purpose/resource.
2. Mixed credit systems and currencies remain separate. Missing price/usage appears unknown. Price-version changes leave prior valuation reproducible.
3. Local reuse adds no charge; provider cache hits can charge; failed and retried requests retain every charge exactly once.
4. Duplicate and out-of-order cumulative/delta receipts, conflicting receipts, refunds, corrections and post-restart replay produce deterministic correct totals or an explicit conflict.
5. Crashes before dispatch, after acceptance and before settlement retain safe exposure. Async polling/cancellation and terminal-but-unbilled jobs cannot release exposure prematurely or resubmit uncertain work.
6. Concurrent reservations cannot exceed the applicable task/provider/global admission limits. Settlement and release do not create capacity twice; actual overruns remain fully recorded and block new work.
7. Task/provider/global stop races, delegated workers, policy revision changes and restart cannot bypass the tested boundary. In-flight charges and unsupported SDK paths are truthfully labeled.
8. Reconciliation fixtures include grants, expiry, period boundaries, late charges, refunds, scope gaps, external unattributed activity and unknown balances. No fabricated task allocation or false balanced state.
9. Dashboard totals equal exported snapshot totals; pagination and root/child aggregation do not duplicate usage. Access isolation, malicious metadata, redaction and CSV-injection fixtures pass.
10. Existing lookup-ledger behavior and repository regression suites pass. Document migration/rollback and compatibility tests before any existing database is changed. Report passed, failed, skipped and unrun checks separately.

Suggested proof fixture: Task A reserves 12 provider-A credits, confirms 7 and releases 5; duplicate confirmation changes nothing; a retry costs 2; a confirmed refund returns 1. Net actual is 8, and reservation is 0. Task B's local reuse adds 0. A separate async job reserves 4 and stays uncertain: show 8 confirmed plus 4 exposure, not 12 spent. A different provider's 3 tokens remain a separate unit. This is synthetic arithmetic, not a real usage report.

## Implementation handoff and review gates

OpenClaw should return a short source-reconciliation plan identifying the current dashboard/service files, existing ledger integration, first adapter, exact enforcement boundary and migration needs. Then break Cursor work into:

1. Typed schema/events/read models plus migration and privacy tests.
2. Atomic allocator and fake adapter with crash/concurrency/stop tests.
3. Task dashboard, filters, exports and access-control tests.
4. Provider receipt/balance reconciliation using recorded synthetic fixtures.
5. Documentation, coverage matrix and one consolidated offline regression report.

Cursor returns a draft PR with the changed-file list, schema/API examples containing only synthetic values, exact test commands/results, migrations/rollback, known limits and evidence for each acceptance criterion. dot reviews before any live rollout proposal. Any paid verification, new credential access, merge or deployment needs separate authorization. Completion of this work order means the defined offline MVP is implemented and reviewed; it does not by itself mean production readiness.
