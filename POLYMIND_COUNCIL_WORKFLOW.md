# PolyMind: full-model planning and review council

Design ID: PM-COUNCIL-001  
Date: 2026-10-09  
Status: proposed design only; no integration provisioned or live model calls performed  
Read baseline: `01a68a5125002182c4338c06c1b86f4b5654638f`, draft PR #1

## Intent and relationship to ClawCare

The optional delivery chain is:

**dot work order → ExecuBot → n8n-coordinated council visible in Discord → approved plan → OpenClaw → Cursor implementation → GitHub draft PR → full-model review council → Cursor revisions → exact-commit acceptance → separately authorized merge/deployment.**

The initial council includes **OpenAI/ChatGPT, Claude, Gemini, Perplexity and Manus**. Every participating model receives the independent planning and review passes. Additional approved models are extensible through the same contract. This design must not be reduced to two reviewers: breadth of participation is part of the requested outcome. Product names identify intended participants, not verified APIs, account entitlements or working integrations.

ClawCare remains an independent, standalone reliability/work-order product. PolyMind is an optional coordination integration, not a launch dependency, mandatory AI account, replacement control plane or background worker dependency. An unavailable council must not interrupt standalone monitoring or previously authorized ClawCare behavior. It blocks only a work order that explicitly requires council acceptance.

This extends the planning and review portions of [OpenClaw → Cursor](OPENCLAW_CURSOR_WORKFLOW.md), preserving its single-writer, scoped authority, recovery and publication gates. In standalone mode that existing workflow remains unchanged. Spending follows [task-level budgets and attribution](TASK_SPENDING_WORK_ORDER.md); the proposed allocator is not an implemented guarantee. Current [source reconciliation and launch gates](UPGRADE_READINESS.md) remain open.

## Roles and boundaries

- **User:** owns goals, consequential decisions and approvals. Can pause, revoke or change scope.
- **dot:** translates the goal into a scoped work-order revision, checks the synthesis and evidence, and escalates decisions. Does not implement code.
- **ExecuBot:** the logical council coordinator. Validates the work order, prepares packets, routes bounded requests through n8n, collects responses, produces the synthesis and dispatches only an authorized accepted plan. No special execution authority is implied by this role name.
- **n8n:** orchestration runtime for a durable structured state store and queue. Its explicit workflow state is the source of truth, not a Discord transcript, model memory or a successful-looking node log. Actual durable storage, transactional admission and fencing remain implementation choices to verify.
- **Discord:** human-readable progress, discussion and authenticated control surface. Models can debate here through approved adapters, while structured responses and decisions are retained in authoritative state.
- **All council participants:** independently plan, challenge and review; submit evidence, findings, advisory votes and dissent. They do not edit the implementation checkout, grant permissions, invoke arbitrary tools or approve their own authority.
- **OpenClaw:** receives one accepted immutable plan and orchestrates one bounded Cursor session under the existing execution contract.
- **Cursor:** the sole implementation writer; changes code/tests and returns exact-commit evidence.
- **GitHub:** versioned draft PR and CI evidence. Council output is not a substitute for branch protections or required repository approvals.

There is one logical coordinator and one active implementation writer per work order. If n8n workers are replicated, a durable lease/fencing generation must still produce one coordinator decision and one dispatch. Giving each model its own coding agent or write access is out of scope.

## Work-order and participant contract

Create an immutable revision before fan-out. It records:

- Work-order/root IDs, revision, authorized owner, objective, acceptance criteria and non-goals.
- Repository, starting SHA, target branch/draft PR, allowed paths and source-reconciliation status.
- Participant roster with stable IDs, provider/product/model version where exposed, adapter version, account scope reference and capability limits. Multiple models may be listed per provider; freeze the exact roster before dispatch.
- Approved packet/artifact references, hashes, classification and per-provider disclosure permissions.
- Allowed operations and destinations, prohibited effects, publication authority, approval reference, expiry and revocation policy.
- Phase deadlines, maximum rounds, per-participant response/usage limits, aggregate root budget, retry ceiling and unresolved-issue escalation rule.
- Coordinator identity/lease generation, state revision, logical request IDs, attempt IDs and idempotency keys.

Participants return schema-validated records bound to work-order revision, phase, packet hash and, for review, immutable candidate SHA:

1. Proposed plan or review verdict; assumptions and confidence/uncertainty.
2. Numbered findings with severity, claim, evidence reference and reproducible test/check where possible.
3. Alternatives and tradeoffs, acceptance-to-test mapping, risks and missing information.
4. Advisory vote: support, support with conditions, oppose or abstain.
5. Dissent and remaining conditions; explicit unavailable evidence.
6. Actual provider receipt/usage where available, latency and response status.

Malformed, truncated or mismatched responses are not votes or approvals. Preserve a sanitized failure record and apply only an authorized bounded retry. Exact provider capabilities and endpoint availability must be verified before selecting an adapter; do not assume a consumer subscription supplies API access.

## Phase A: independent planning, bounded debate, synthesis

1. **Preflight:** verify authority, full roster, disclosure scope, enforceable budget, deadlines and packet consistency. Missing required access or pricing yields a hold, never a free-call assumption.
2. **Independent first pass:** send every participant the same authorized baseline packet without others' answers. Collect first-pass submissions before revealing peer outputs. Provider-specific redactions or omissions must be declared; do not describe differing packets as identical evidence.
3. **Challenge round:** distribute a structured comparison of all initial proposals, unresolved claims and evidence. Each participant challenges assumptions, proposes tests and responds to material objections. Minimize reputation effects by using neutral proposal IDs where practical, while preserving provenance privately.
4. **Synthesis:** ExecuBot assembles one proposed plan with an acceptance-to-evidence matrix, selected alternatives, reasons, dissent and unresolved blockers. Cite the underlying response/finding IDs. A majority is a signal, not proof of correctness.
5. **Ratification:** all participants may submit final advisory positions on the same plan revision. dot evaluates evidence and scope; the user resolves approval-required choices. Only an accepted, authorized plan goes to OpenClaw.

Full participation means each roster member is invited to the required pass and has a recorded terminal response or explicit failure; it does not mean the coordinator may silently label a timeout as consent. The default gate requires a valid response from every roster member before dispatch. If a model is unavailable, remain blocked or obtain an explicit work-order exception describing the missing participant and consequence. Do not silently replace the full council with whichever two models replied fastest.

Consensus is not required indefinitely. An unresolved material security, privacy, correctness or scope concern becomes a visible hold/escalation with evidence. Cosmetic disagreement can remain documented dissent under the approved acceptance rubric. No majority can override an authority cap, user stop, test failure or required approval.

## Phase B: implementation and full-council review

1. OpenClaw acknowledges the accepted plan revision and starting SHA, then dispatches the sole Cursor writer. Cursor follows the existing scoped execution, checkpoints, tests and recovery contract.
2. When publication is authorized, Cursor publishes a draft PR. Read back the actual remote candidate SHA and manifest; do not review a mutable branch name alone.
3. Freeze one review packet: candidate SHA, base SHA, full relevant diff, approved plan revision, acceptance criteria, exact-SHA test/CI receipts, known limitations and authorized source context.
4. Every council participant performs an independent first review of that same packet before reading peer reviews. Specialized emphasis is welcome, but no model is excused from its basic acceptance/safety review.
5. Run one bounded challenge/synthesis round for findings. Deduplicate equivalent findings without discarding attribution or dissent. ExecuBot produces one prioritized revision request with evidence and acceptance tests.
6. Cursor alone revises. Reconcile branch drift and preserve unrelated work; no force-push or parallel model edits. A new commit creates a new review epoch and invalidates all prior exact-commit approvals. Historical reviews remain audit evidence, not current approval.
7. Redistribute the new immutable SHA to the entire roster. Reviews must cover whether revisions introduced regressions as well as whether prior findings were addressed. No stale approval is carried forward automatically.
8. Accept only after the approved criteria, current required CI, unresolved-finding policy and full-roster review gate are satisfied for the exact final SHA. This yields a reviewed candidate, not merge/deployment authority.

Each finding has an ID, severity, affected SHA/path or criterion, evidence, status, owner and resolution evidence. “Fixed” requires verification; a Cursor assertion alone is insufficient. Tests distinguish passed, failed, skipped and not run. Model votes never make missing CI green.

## Bounded operation and failures

Proposed defaults below are configuration suggestions, not permission to incur charges:

- Planning: one independent round, one challenge round, one synthesis/ratification round.
- Review: one independent and one challenge round per candidate; at most two Cursor revision cycles before escalation.
- Each model call: explicit request deadline and output/usage ceiling. Each phase and root work order: an absolute deadline.
- Every live work order must supply actual numeric per-provider and aggregate limits before dispatch; missing values block paid execution. Set limits from verified pricing and the authorized roster rather than inventing a universal dollar budget.
- Transport reconnect: at most two bounded attempts. Never automatically replay a billable or mutating operation with uncertain acceptance.
- Late replies are retained with timestamps and marked late; they cannot silently change an accepted plan or revive expired authority.
- Deadline, budget or revision exhaustion produces a checkpoint with available results, dissent, missing evidence and the specific next decision. It does not manufacture consensus.

Reserve exposure atomically across all participants and descendants before fan-out. Record logical request, attempt and provider receipt separately; retries and polling may be billable. Preserve uncertain exposure after timeout. Parent/root caps cannot be escaped through a new run, extra model, new revision or child task. Stop prevents new admissions, requests cancellation where supported and reports in-flight/unknown effects honestly.

A reconnect attaches to verified existing work. Queue redelivery must be idempotent: the same request/payload returns or reconciles the existing result; the same ID with a different payload is rejected. An expired lease alone does not prove the old writer stopped. Reconcile the exact previous process/session before replacement.

## Authoritative state and Discord controls

Suggested states:

`proposed → authorization_hold → planning_independent → planning_challenge → plan_review → implementation → review_independent → review_challenge → revision_required → reviewed_candidate`

Additional explicit states: `blocked`, `stop_requested`, `stopped`, `expired` and `uncertain_reconciliation`. Acceptance never directly transitions to deployed.

Persist state transitions and dispatch intents durably with expected revision checks, actor identity, timestamps, causation IDs and append-only decision records. A durable outbox/inbox pattern, acknowledgements and deduplication should be tested for queue/Discord/provider outages. Discord is a projection: replaying messages reconstructs visibility, not execution authority. If authoritative state is unavailable, new dispatch fails closed.

Discord controls must be authenticated structured actions bound to the authorized user/role, work-order revision, proposed operation and expiry, with replay protection and a visible receipt. Validate identity server-side; a display name, model-generated command, emoji in an unrelated thread, forwarded instruction or arbitrary “approved” text cannot grant authority. A control request enters the same policy check as any other action. Discord access itself does not grant repository, provider or deployment access.

Replies from models, repository files, web pages, attachments and Discord messages are untrusted content. They may supply evidence but cannot redefine instructions, recipients, budgets, tools or authorization. Only scoped tool calls from validated work orders may reach adapters. Keep secrets and credentials out of model packets and Discord; references are not bearer credentials.

## Data sharing and operational security

Before any live council run, establish what information may be disclosed to each specific provider, its model endpoint and the Discord audience. Private code, customer data, logs and sensitive test fixtures are not automatically approved for every participant merely because the user owns their accounts. Apply provider-specific data minimization/redaction, retention controls and approved contractual/account settings. If necessary context cannot be shared, surface the review limitation and obtain a decision; never claim a complete review of unseen code.

Do not paste credentials or configure persistent grants as part of this design. Account connections, tokens, API access, bot installations, server invitations and new persistent permissions require their own approval/setup flow. Do not broaden GitHub visibility or share a private repository to make review easier. Sanitized public documentation may describe the architecture without including real account IDs, personal machine paths or private execution receipts.

Voting is advisory. Policy and authorization are enforced outside model prose. If a provider adapter cannot enforce the scoped operation/data boundary, label it unsupported and block that route rather than trusting a prompt to supply security.

## Implementation sequence and verification gates

No code or integrations are implemented by publishing this document. A later authorized OpenClaw → Cursor work order should proceed in increments:

1. Reconcile current application source. Define versioned work-order, participant, finding and review-epoch schemas; test with all five synthetic adapters.
2. Implement durable state, queue, idempotency, coordinator fencing, root-budget admission and pause/revocation using fake providers and no external calls.
3. Add read-only Discord status projection and then separately authorized structured controls; test identity, stale actions and replay.
4. Implement independent fan-out, bounded debate, evidence synthesis, dissent and strict full-roster gates with synthetic responses.
5. Implement immutable-commit review packets, stale-approval invalidation and the single Cursor revision handoff using isolated fixtures.
6. Verify each intended live provider's supported integration route, account eligibility, data permissions, limits and billing separately. Obtain approval before any credentials, persistent grants, bot provisioning or paid smoke test.
7. Only after offline acceptance, approve one tightly bounded live end-to-end work order. Merge and deployment stay separate.

Required synthetic acceptance cases:

- Every initial participant receives both planning and review requests; roster extensions use the same contract.
- No participant sees peer answers before its independent first pass is closed.
- A missing participant, malformed result or unanimous unsupported assertion never becomes successful full-council acceptance.
- Conflicting evidence and minority dissent survive synthesis; critical unresolved findings block under the rubric.
- All review verdicts bind to the same SHA/packet; a new commit invalidates every prior approval.
- Duplicate deliveries, late replies, crashes around dispatch, lease expiry and uncertain provider acceptance cannot create a second writer, double-charge settled receipts or blindly replay execution.
- Concurrent fan-out, retries and revisions respect root caps; stop/revocation races deny new dispatch and preserve uncertain exposure.
- Discord impersonation, replay, arbitrary text and injected instructions cannot authorize tools or exceed scope.
- Provider-specific redaction, secrets filtering, artifact access and public-summary sanitization fail closed.
- ClawCare standalone works with the entire PolyMind integration absent or unavailable.

## Design assessment

The concept was rated **8/10 as a subjective architectural judgment**, not an objective benchmark or measured reliability claim. Its advantage is broad independent criticism before and after implementation. Its principal risks are correlated mistakes, persuasive consensus without evidence, cost/latency, divergent context, tool overreach and endless revisions.

The better execution pattern preserves the full council while separating independent answers from debate, anchoring decisions to evidence, retaining dissent, bounding rounds and spend, and keeping one coordinator and one writer. Measure real value later against accepted defects found, false positives, regressions, cycle time and total cost on comparable authorized tasks. More votes alone do not establish better software.
