# Work order: task spending, resources and protection

Work order ID: CC-SPEND-001  
Date: 2026-10-08; expanded 2026-10-09  
Status: proposed implementation handoff; documentation only, not implemented or deployed  
Original review baseline: `2deed2ceced61cc63df43e02268d74df0e8d739d`; expansion baseline: `588b23997997c1285ec0ef3b01cb1ce1945859e7`, draft PR #1

## Outcome and ownership

ClawCare must answer: **which task used which provider credits, why, through which agent, and what did it cost?** Show confirmed charges, estimates, outstanding exposure and unexplained usage separately.

This requirement covers **ClawCare's own operating cost and every supervised task**, across model providers, tools, infrastructure, containers, memory and storage. ClawCare must show what it used, who or what used it, what remains available, and whether the next bounded unit is affordable and safe. Coding and transcription are examples, not the scope limit. Where ClawCare supervises PolyMind work, preserve [PolyMind's unified all-model application](POLYMIND_PLATFORM_DESIGN.md), shared context and complementary capabilities; this accounting does not reduce that vision to a coding or transcript workflow. ClawCare remains independently usable.

This expansion preserves the existing request ledger, reconciliation, privacy, stop controls and offline acceptance below. All added collectors, dashboard features and enforcement requirements are **proposed**, not implemented or validated by this documentation change.

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
6. Unified inventory of operating costs and resource capacity: model tokens, provider credits, monetary charges, Codespaces compute/storage, host and container usage, RAM/commit/swap, disk and other metered services.
7. ClawCare self-overhead and supervised-task allocation with no duplicate host/container billing, plus a conservative pilot proposal requiring explicit approval before any paid work.

The MVP must not attempt currency trading/conversion, invoice payment, account-wide network interception, arbitrary process killing, automatic top-ups, speculative task attribution, or retroactive recovery of unavailable historical request detail. Live provider rollout is a separate reviewed gate.

## Usage and cost coverage

Maintain an extensible inventory for every service and execution environment ClawCare itself uses or supervises. Each entry identifies the billing owner privately, product/SKU, machine or resource identity, adapter, unit, price provenance, measurement freshness, approval scope, enforceability and known gaps. Unseen activity remains unknown or unattributed, never zero.

- **Model usage:** provider, model/version and account; input/output and separately reported cached-input, reasoning, audio/image or other token categories; requests and tool charges. Preserve the provider's category definitions and whether a category is already included in a total, so nested counters are not added twice. Subscription charges, included entitlements, consumed usage and incremental cash charges are separate views.
- **Tools and credits:** provider/product/operation quantities, credit grants/purchases/expiry and reported charges. Firecrawl remains under **STOP**: import only already-saved, authorized, sanitized receipts or synthetic fixtures. No Firecrawl calls, polling, retries, balance fetches, new crawl/search jobs or re-enablement are authorized by this work order. Missing historical receipts stay unknown; do not make a new call to fill a gap.
- **Codespaces and other compute:** record active wall-clock intervals, machine tier, configured cores/RAM, elapsed hours and core-hours as distinct units, restart/stop observations and billing owner. Include setup/build, idle, supervision and shutdown intervals; billable provisioned time is not the same as useful CPU seconds. Price each machine segment separately if the tier changes. A disconnected editor is not evidence of a stopped machine.
- **Storage:** keep physical capacity/free space separate from billed stored quantity over time. Cover codespace files, custom images where billed, persistent volumes, logs, checkpoints, artifacts, caches, backups and prebuilds. Record byte/GB/GiB unit semantics and byte-hours or provider storage units; price only with the matching billing basis. Track prebuild generation, CI/Actions, network/egress, hosted tools, databases, subscriptions and other charges as distinct categories whenever actually used and billable. Unverified rate or payer remains unknown.
- **Docker:** record container, image/workload, host/VM and volume identities and sampled CPU time, memory and storage. Docker container telemetry is an allocation view of its underlying host bill; it is not a second compute invoice. On Codespaces, allocate the same Codespaces charge to containers/tasks instead of adding a fictional Docker hourly fee. Record genuinely separate Docker subscriptions, registry/build services or third-party host charges only with their own price/receipt evidence. For a local host, show resource consumption and any declared cost model separately from cash charges; never invent an electricity, hardware or license cost.

For each category, expose observed versus estimated versus provider-confirmed measurements, reconciliation age and coverage. A zero marginal cash charge supported by included usage does not mean zero resource consumption.

### Shared costs and ClawCare self-overhead

Give ClawCare's monitor, coordinator, ledger, dashboard, polling, recovery, checkpointing and idle service their own overhead category. Meter their provider calls and resource use using the same admission path as supervised work. Monitoring cannot recursively launch unbounded monitoring or silently bypass the budget.

Keep three compatible views: the authoritative bill, direct task usage, and an explicitly labeled allocation of shared overhead. Use direct attribution where evidence exists; otherwise use a documented, versioned allocation basis such as active task time or measured CPU share. Record interval, denominator, rounding and unallocated residual. A task's allocated share is an estimate, not a provider-confirmed task invoice.

For a host billing interval: task allocations + ClawCare overhead + other/unallocated usage must equal the reconciled host total within declared rounding, with an explicit residual when incomplete. Do not show the full host bill plus its allocated shares as additive spend. Overlapping containers, parent/child tasks, shared image layers and shared volumes require one underlying billing identity; do not sum duplicated byte gauges or cumulative CPU counters as separate charges. Historical allocation revisions append auditable corrections.

## Data and attribution contract

Use immutable opaque identifiers. The trusted service derives account/tenant authorization; clients cannot select an arbitrary scope.

- Identity: event ID, schema version, tenant/account scope, work-order ID and revision, root task ID, executing task ID, parent task ID, run ID, agent/worker ID, provider/product, operation and adapter version.
- Execution: logical request ID, attempt ID, retry-of attempt, idempotency key reference, existing lookup/action ID where applicable, provider request/job ID when available, and stable provider receipt/line-item identity.
- Explanation: bounded purpose code plus sanitized human-readable purpose; opaque resource/artifact reference or approved sanitized origin. Do not persist request bodies, prompt contents, full URLs, query strings, signed links, customer/property details, credentials or raw errors.
- Time: occurrence, recording and provider observation timestamps; provider billing period, timezone, source scope and snapshot freshness.
- Measurement: quantity, explicit unit namespace and product (credits, tokens, pages, seconds, etc.), measurement source, estimate/confirmed/unknown status and confidence where useful.
- Money: nullable decimal amount, ISO currency, valuation basis (provider-billed versus locally calculated), price-card/version reference, effective date and relevant tier/discount assumptions. A calculated amount remains an estimate even when its underlying credit quantity is provider-confirmed.
- Audit: actor, event kind, causal/correlation reference, receipt revision and append-only correction/refund linkage. Mutable task display names do not change historical attribution.
- Infrastructure: opaque host/codespace/container/volume identity, billing SKU, machine tier, effective interval and owner scope; link samples and bill line items to task/run/agent when known.
- Resources: platform and namespace, physical/virtual/container scope, timestamp, units, measurement method, instantaneous gauge versus cumulative counter versus interval delta, reset epoch and supported/unknown status. Preserve actual worker identity; a sample of the observer's own container is insufficient for another worker.
- Allocation: direct or shared/self-overhead classification, allocation policy/version, source bill/sample references, denominator and residual. Attribution and allocation confidence are separate from billing certainty.

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

## Resource capacity and admission

Resource observations complement spending controls; RAM and disk pressure cannot be inferred from a credit balance. Extend the existing [workload policy](WORKLOAD_PROTECTION.md) and [read-only observer](WORKLOAD_OBSERVER.md) through reviewed adapters without misrepresenting their present implementation.

Required observations, where supported by the target platform:

- Physical RAM total, available/usable, resident/working-set usage and reclaimable/cache context. Raw free RAM alone is insufficient.
- Commit/virtual-memory usage and limit, swap/pagefile total/used/available, paging activity and sustained memory-pressure signals. Virtual address size, committed memory, resident RAM and swap are distinct measures and must not be added as though independent physical capacity. Missing or noncomparable platform fields are explicit.
- Worker/container current usage, configured limits, reservations, ancestor limits, throttling/pressure and OOM/failure events. Host capacity does not override a tighter container or ancestor limit. Unlimited must be explicitly observed; missing is not unlimited.
- Disk/filesystem total, available bytes, quotas and inode availability where applicable; container writable layers and persistent volumes; expected output/temp/checkpoint growth, I/O pressure and storage retention. Memory-based filesystems also consume RAM. Logical/shared storage attribution must not duplicate physical usage.
- CPU consumption and configured quota, concurrency, throttling and execution duration where relevant to task performance or billed compute. Attribute sample overhead to ClawCare.

Before a new task, child task, provider dispatch or bounded work unit, check current authorization, stop state, conservative cost reservation and resource fit together. Estimate the next unit's additional peak working set, commit/swap needs, disk/output growth and checkpoint reserve; include other admitted work and operating-system/ClawCare overhead. Bind estimates and observations to the actual execution environment, with freshness and uncertainty. Capacity reservations are policy bookkeeping, not guaranteed OS allocations; distinguish already-observed consumption from future demand to avoid double-counting it.

**Do not block or stop work solely because free RAM is below an arbitrary fixed threshold.** Evaluate workload-specific peak demand, effective host/container limits, pressure trend, commit/swap condition, competing work and checkpoint capacity. Conversely, a high host-RAM reading cannot approve a task that exceeds a container limit or disk quota. A conservative bounded workload may fit even with low raw free RAM; demonstrated pressure, insufficient effective capacity or unknown safety-critical evidence requires a hold with a precise reason. Do not treat swap as equivalent-speed extra physical RAM or disable existing safety holds without the reviewed replacement.

Use stable-sample recovery, hysteresis and cooldown appropriate to the workload. Prefer lower concurrency, smaller bounded units and cooperative pause/checkpoint before admitting more work; changing those settings must stay within approved authority. Unsupported collectors provide an observe-only or unknown result rather than a fabricated safe decision.

### Safe pause and checkpoint

Budget or capacity denial stops admission of new units. The owned cooperative adapter must save and independently verify a durable checkpoint and output inventory at its next supported safe boundary, preserving drafts and incomplete work. Record stop requested, checkpoint verified, quiescence confirmed and actual host/provider stop as separate facts.

Never kill arbitrary processes, stop a host/container with unsaved work, erase outputs, prune Docker data or delete a codespace to satisfy a budget automatically. If a safe stop cannot be verified, keep the unresolved state and any continuing charge exposure visible and request a decision. Allow only the already-authorized bounded checkpoint/reconciliation work, with a reserved shutdown margin; no fresh paid retry or unrelated work. Resume needs explicit current authority, safe resources, available budget and reconciliation of uncertain prior effects.

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
- Budget scope includes direct provider spend, provisioned infrastructure, retained storage and ClawCare overhead. Track gross list-price estimates, verified allowance offsets and expected payable cash separately. Never assume an account has an unused free quota or that a subscription includes API/tool use.
- Forecast burn rate, time to budget exhaustion and continuing storage/in-flight liability. Reserve conservative exposure through the next safe stopping boundary, including shutdown/checkpoint work and billing-report delays. Currency and allowance changes require revaluation under a versioned policy.
- A ClawCare admission stop is not a guaranteed provider invoice cap. Verify provider-side budget behavior separately; an alert-only budget, delayed billing or retained storage may continue accruing costs. No automatic top-up, machine upgrade, new provider or transfer between budget categories is permitted without authority.

Expose each adapter's coverage and enforcement capability in the UI. A direct SDK call that bypasses the boundary is not stopped by this feature. Stronger account-wide enforcement would require a separately designed credential/proxy/provider limit architecture and security review.

## Dashboard and exports

Provide a Spending view with an explicit period/timezone and data-freshness indicator.

- Summary: confirmed credits by provider/product/unit, provider-billed money by currency, locally valued estimates, open reservations, pending/unknown charges, refunds and unexplained account-balance differences.
- Breakdown: task/work order, root/delegated task, agent, provider, operation and date; show top spenders without mixing units.
- Task detail: purpose, sanitized resource, request/attempt timeline, actual versus estimated usage, monetary valuation source, cache reuse, retries/failures, async status, outstanding exposure and budget denials.
- Coverage: enforced versus observe-only versus unsupported, last successful reconciliation, missing statement scopes and unattributed usage. Do not hide unknown records from totals or filters.
- Resources: host and container RAM, commit/swap, effective limits, disk/volume capacity, CPU/concurrency and pressure with freshness, peaks/trends, next-unit estimate, reservations and the precise admission reason. Missing values stay visible.
- Operating cost: Codespaces/host compute and retained storage, other service categories, direct task cost, allocated ClawCare overhead and unallocated residual; clearly identify views of the same charge.
- Alerts: forecast/threshold budget risk, unknown prices or billing gaps, sustained pressure, storage/checkpoint risk and stalled productive progress. Include task/resource scope, source age, consequence and safe next step; use deduplication and cooldown. Alert delivery and acknowledgement need verification, not merely a local alert row.
- Controls: authorized budget edits and stop/resume with visible scope and in-flight warning. Read-only users cannot mutate policy.
- CSV/JSON: same authorized scope and filters as the screen; include schema version, generation time, snapshot/revision, units/currency, valuation status and coverage. Protect CSV against spreadsheet formula injection. No public export links or unsanitized metadata.

Read models and exports must use consistent snapshots, deterministic aggregation and bounded pagination. Parent-task rollups count descendants once; displaying a child separately must not increase account totals.

## Account reconciliation

Store scoped provider balance snapshots with source, observed-at, period, timezone and freshness. Reconcile only comparable units and account/product scopes:

Expected closing balance = opening balance + purchases/top-ups + grants + confirmed credit refunds + explicit adjustments - confirmed consumption - expired grants.

Represent subscription renewals, grant buckets and expiry rules explicitly; use provider ordering/allocation evidence where available. Do not assume all balance changes are consumption or that credit balances are cash. Account cash charges and credit purchases/consumption are different measures and must not be double-counted.

Report expected versus observed closing balance, attributable usage, provider-confirmed but unattributed usage, residual discrepancy and explanatory events. Imports are idempotent. Scope/time gaps, delayed posting, shared accounts and unavailable request-level detail remain visible. Never distribute a residual across tasks just to force reconciliation to zero. Unknown balance means unknown coverage, not a successful match. Keep account reconciliation separate from per-request billing truth.

## Phased credential and intellectual-property protection

Proposed extension: make ClawCare a place to inventory and protect the credentials and project assets used by its own services and supervised tasks. The assets include code, designs, documents and configuration. This complements the standalone observe/checkpoint/recover core; advanced vault and asset protection are a later reviewed phase and do not silently become prerequisites for the current bounded setup. Any external governance or attestation integration is optional and supplies no new authority.

### Credential inventory and established vault adapters

The proposed portal spans authorized providers such as OpenAI, Gemini and other API-key services without assuming universal adapter support. Its UI shows metadata, access/cost links and lifecycle status; secret entry or display belongs only to the separately approved secure-vault flow, never an ordinary chat or document.

Maintain a **non-secret** inventory: opaque credential record ID, authorized owner/team, provider/product, intended purpose, allowed scopes, environment, established vault reference, creation/expiry metadata where known, last verified rotation/revocation state, permitted consumers and links to attributed usage/cost. Unknown or stale lifecycle state must be visible. Use provider-issued non-secret credential identifiers or opaque aliases where available; never infer which key was used without a trustworthy mapping.

The inventory must not contain raw API keys, access/refresh tokens, passwords, recovery codes or private encryption keys. Keep secret values in an established encrypted secret manager through separately reviewed and authorized adapters, rather than building custom cryptography or a plaintext database. Runtime access must use minimum necessary scopes and duration, enforce tenant/project boundaries, and avoid putting secrets in model context, saved receipts, logs, exports, Git, documents or backups of ordinary application data. Audit secret access events using non-secret identifiers and outcomes; never log returned values.

Metadata inventory does not create persistent access. Connecting a vault, collecting/importing credentials, granting a workload secret access, generating/rotating/revoking keys or enabling unattended retrieval each requires the applicable explicit authorization. This design authorizes none of those operations. Approval references, adapter capability and actual provisioning state must remain distinct. If a credential appears compromised, hold affected new dispatches within the enforced boundary and present the scoped response plan; do not claim revocation from an unverified request or rotate unrelated credentials.

### Project asset inventory, backup and recovery

Inventory authorized code repositories, design assets, documents, configuration and work-order/checkpoint artifacts by opaque identity, owner, source, sensitivity/access policy, version/hash, lineage, approved storage location and retention policy. Avoid public manifests of private paths or customer/project content. Record who may view, edit, export or restore each asset; access to the dashboard must not imply access to every asset.

Use approved encryption in transit and at rest, established key-management facilities, least-privilege access and auditable versioned backups. Separate backup access from everyday runtime access where supported. Specify retention/deletion, key ownership/recovery, access revocation and export policy before activation. Back up only authorized sources to authorized destinations; credential material remains under the secret manager's separately approved backup/recovery model. Detect embedded secrets in configuration/assets before ordinary backup or export and route them through the approved secret policy; retain safe references and verify restore usability without leaking values.

A backup is not proven protection until a bounded isolated restore verifies version/hash and, where relevant, that the restored artifact is usable. Preserve originals and user edits, record verification time and gaps, and require separate authorization before overwriting a live asset. Hashes establish byte identity, not authorship, ownership or permission. Provide provenance and access evidence without promising legal IP ownership, patent/copyright enforcement, guaranteed confidentiality or a security certification.

Before rollout, document the threat model and trust boundaries: compromised host/admin or provider, stolen session/credential, malicious plugin/model input, cross-tenant disclosure, accidental publication, backup loss, key loss and malicious/deceptive restore. Review encryption/key-management choices, authenticated access and audit integrity independently. Define what ClawCare can observe, block, recover and cannot protect; an encrypted store cannot guarantee safety on an already-compromised authorized endpoint.

## Proposed pilot budget requiring approval

**Proposal only, 2026-10-09: USD $5 maximum gross pilot envelope. No numerical budget has been approved.** This is a one-time, seven-day evaluation proposal, not a subscription or authority to create/start a codespace, run paid work, enable a provider or change account settings. Start with synthetic adapters and already-saved receipts. Implementation and tests still follow OpenClaw → Cursor.

Proposed limits:

| Category | Proposed bound | Conditions |
| --- | ---: | --- |
| Codespaces compute | USD $3 | One 2-core / 8 GB machine; at most 10 total active elapsed hours across the pilot, including setup, idle and shutdown; no parallel extra machines or tier upgrade |
| Retained storage | USD $1 | Forecast and reserve storage through the approved retention window; verify actual stored size and billing units before starting |
| Contingency | USD $1 | Reserve for applicable tax/rounding and delayed final settlement; not authority for extra runtime, a new service or provider calls |
| New model/tool/Firecrawl spend | USD $0 | No new provider calls, credit purchases or paid agent runs; Firecrawl STOP remains in force |

All sublimits and the USD $5 gross total apply together. The ten-hour compute target is intentionally below the USD $3 compute envelope to leave stopping/settlement headroom. Any provider-backed implementation session needs its own explicitly approved provider limit and would require revising this proposal; the table does not assume Cursor or another model is free. Baseline account activity outside the pilot remains separately reported, not silently charged to this allocation.

Published GitHub pricing checked 2026-10-09: [2-core compute is USD $0.18 per elapsed active hour and storage is USD $0.07 per GB-month](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces). The [documented smallest machine has 2 cores and 8 GB RAM](https://docs.github.com/en/codespaces/about-codespaces/what-are-codespaces). Availability must be checked for the actual account/repository.

**Illustrative arithmetic, not an account quote:** 10 active elapsed hours × USD $0.18 = USD $1.80 compute, excluding storage, providers and taxes. That is 20 core-hours of included-usage measurement, not 20 elapsed hours or a second compute charge. For storage, a constant 10 billable GB maintained for one full billing month at USD $0.07/GB-month illustrates USD $0.70; actual hourly metering, stored size and billing period determine the charge. See [included-usage and GB-hour measurement](https://docs.github.com/en/codespaces/troubleshooting/troubleshooting-included-usage). Account payer, plan, remaining allowances, other current usage, currency and tax treatment are unknown; budget conservatively without assuming allowance offsets.

Before approval, verify the billing owner, actual machine/rate, stored size, remaining allowances, projected storage through retention, provider spend disabled, safe-checkpoint route and relevant provider budget settings. The proposal is invalid if the conservative total cannot fit its bounds. Suggested warnings are 50% and 80% of any sublimit and an immediate hold when the next reservation plus current spend/exposure cannot fit; require a checkpoint/stop review by 8 of the 10 active hours. These are proposed settings, not installed controls.

At the end of every approved session, checkpoint and verify saved work before a separately authorized host stop; verify stopped state. [Closing the editor does not stop a codespace, and stopped codespaces still incur storage charges](https://docs.github.com/en/codespaces/developing-in-a-codespace/stopping-and-starting-a-codespace). Review storage at the seven-day boundary and obtain a decision on funded retention or verified export and authorized deletion. Do not auto-delete unsaved or unverified work. Keep storage exposure open after compute stops and after the evaluation ends until billing evidence establishes that accrual ended. No new compute is admitted while continuation would breach the approved storage/total envelope. A budget warning cannot guarantee an invoice hard cap or justify destroying work.

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
11. Model token categories, tool credits, subscriptions/allowances and cash charges remain distinct. Synthetic saved Firecrawl receipts import idempotently while STOP rejects every dispatch and polling route; missing receipts do not trigger retrieval.
12. Fake Codespaces sessions distinguish elapsed active hours, core-hours, CPU consumption and retained storage across idle, disconnect, stop/restart, tier change and billing-period boundaries. A stopped machine has no subsequent active-compute estimate but can accrue storage. Unknown allowances cannot produce a false zero cost.
13. A synthetic USD $1 host bill allocated as USD $0.60 to Task A, USD $0.25 to Task B and USD $0.15 to ClawCare remains USD $1 total, not USD $2 when host and allocation views appear together. Duplicate container samples, shared volumes, parent/child rollups and revised allocations do not multiply the bill; incomplete attribution retains a residual.
14. Low raw free RAM with adequate measured workload-specific headroom is not denied solely by a fixed threshold. High host availability with a tighter container/ancestor limit, exhausted commit/swap, sustained pressure, disk quota or insufficient checkpoint space correctly denies new units. Missing/stale/conflicting critical evidence is unknown and cannot become safe by substituting an unrelated host sample.
15. Resource fixtures cover Linux and Windows capability differences, RAM versus virtual/commit/swap distinctions, ancestor limits, cumulative counter resets, shared storage, inodes, concurrency and post-restart state. Estimates, live observations and policy reservations never masquerade as guaranteed capacity.
16. Budget and resource holds race safely with child dispatch and bounded-unit starts. A safe cooperative pause preserves saved/unsaved-in-progress state through a verified checkpoint where supported; inability to checkpoint remains an explicit blocker. No fallback kill, Docker prune, codespace deletion, unapproved resize or replay occurs.
17. Synthetic pilot approval is absent by default: USD $5 proposal text alone cannot admit paid work. Approved fixtures apply every sublimit plus the total, reserve final-settlement/storage exposure, warn before the safe stopping boundary, and leave retained-storage liability visible after compute stop or pilot expiry.
18. Dashboard/export snapshots include infrastructure, overhead, resource trends, unknowns and enforcement coverage consistently. Simulated alerts test threshold crossing, forecast risk, stale data, delivery failure, deduplication and acknowledgement without real notification or provider calls.

Suggested proof fixture: Task A reserves 12 provider-A credits, confirms 7 and releases 5; duplicate confirmation changes nothing; a retry costs 2; a confirmed refund returns 1. Net actual is 8, and reservation is 0. Task B's local reuse adds 0. A separate async job reserves 4 and stays uncertain: show 8 confirmed plus 4 exposure, not 12 spent. A different provider's 3 tokens remain a separate unit. This is synthetic arithmetic, not a real usage report.

### Later protection-phase acceptance

These criteria apply to the later authorized credential/asset phase, not to a claim that the current spending MVP includes a working vault:

- Synthetic credential records link owner/provider/environment/scope and opaque vault references to task usage without containing a secret. Unknown expiry, rotation or revocation remains unknown. A metadata record cannot authorize secret access.
- Seeded fake secrets in inputs are rejected or redacted from prompts, ledger events, logs, exports and repository output; scope/tenant denial and revocation races fail closed at the tested access boundary. Test with fake values only, never real keys.
- Approved mock vault adapters demonstrate least-privilege retrieval and auditable non-secret receipts; denied, expired, stale or unavailable access cannot fall back to plaintext storage or a broader account.
- Versioned synthetic code/design/document/config assets survive backup/restore tests with identity/hash and usability checks. Wrong version, corruption, unavailable keys, revoked access and destination mismatch block restore without overwriting live data.
- Threat-model review, encryption/key-management evidence, access/retention policy and explicit activation approval are required before any real vault/backup rollout. Report gaps and unrun security checks; passing fixtures provides no legal-IP guarantee or security certification.

## Implementation handoff and review gates

OpenClaw should return a short source-reconciliation plan identifying the current dashboard/service files, existing ledger integration, first adapter, exact enforcement boundary and migration needs. Then break Cursor work into:

1. Typed schema/events/read models plus migration and privacy tests.
2. Atomic allocator and fake adapter with crash/concurrency/stop tests.
3. Task dashboard, filters, exports and access-control tests.
4. Provider receipt/balance reconciliation using recorded synthetic fixtures.
5. Host/container/storage and platform-resource collector interfaces using synthetic fixtures first; direct/shared/self-overhead allocation and no-double-count tests.
6. Joint resource-and-spending admission, safe checkpoint/stop integration and pilot-policy fixtures; preserve current workload behavior until replacement evidence is reviewed.
7. Documentation, all-provider/infrastructure coverage matrix and one consolidated offline regression report.

Cursor returns a draft PR with the changed-file list, schema/API examples containing only synthetic values, exact test commands/results, migrations/rollback, known limits and evidence for each acceptance criterion. dot reviews before any live rollout proposal. Any paid verification, new credential access, merge or deployment needs separate authorization. Completion of this work order means the defined offline MVP is implemented and reviewed; it does not by itself mean production readiness.
