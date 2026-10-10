# Bootstrap work order: build PolyMind with the participating models

Work order ID: PM-BOOTSTRAP-001  
Date: 2026-10-09  
Status: proposed engineering handoff; documentation only  
Product authority: [PolyMind platform design](POLYMIND_PLATFORM_DESIGN.md)

## First objective

**The participating models' first engineering task is to collaboratively build PolyMind itself.** This is not a generic demonstration or benchmark project. Begin with available, authorized orchestration and model access; a finished PolyMind app must not be a prerequisite for building PolyMind.

The intended participant inventory includes OpenAI/ChatGPT, Claude, Gemini, Grok, Perplexity, DeepSeek, Kimi, Manus and extensible additions. Every available, authorized participant contributes to the bootstrap plan; missing or unsupported providers remain visible. A partial bootstrap roster must never be presented as universal model access.

ClawCare continues independently and in parallel. This document lives alongside ClawCare's architecture notes for coordination only; it does not make PolyMind a ClawCare module or authorize placing its application code in this repository. The actual PolyMind repository, starting revision and deployment target must be resolved before any implementation dispatch.

No code, account connections, bot installations, credentials, persistent grants, paid provider tests, merge or deployment are authorized by publishing this work order.

## Temporary bootstrap route

Use the actual existing, authorized Discord/n8n setup or available approved connectors as a temporary coordination path. Verify that each exists and can perform the needed operation; do not assume a channel, workflow, bot, provider API or account is connected.

Keep one coordinator with a durable structured task record and one canonical context packet. If n8n is already authorized and available, it can drive the queue/state workflow. Discord can expose progress and authenticated controls. If another approved connector supplies a needed route, document its capabilities and limitations. None of these temporary components needs to be PolyMind's eventual application backend.

If no suitable route is available, produce the inventory and architecture handoff and stop at the exact setup/authorization gate. Do not install or provision a replacement automatically, bypass an access denial, or claim models have participated when they have not.

The bootstrap task record, participant responses and accepted plan must be exportable/importable into the future PolyMind workspace with stable IDs and provenance. Migration itself is a later scoped action, not permission to copy private data into a new service.

## Inputs to resolve before live work

- PolyMind application repository and exact baseline, allowed branch/files, owner and source-reconciliation status.
- Primary app surface and first usable slice: one shared chat/task workspace with visible participants, capability inventory, bounded coordination and evidence.
- Existing authorized orchestrator/connectors, provider accounts/routes and actual read/execute permissions.
- Intended versus currently usable model roster and explicit user-approved exceptions for missing required participants.
- Per-provider permitted task context, private-source sharing scope and peer-output redistribution permissions.
- Numeric task/root/provider budgets, runtime deadlines, concurrency and bounded planning/revision rounds.
- Cursor-only implementation environment, OpenClaw execution route, tool scope and separate publication permission.
- Acceptance criteria, evidence store, artifact audience and user stop/approval route.
- The required private governance-source manifest and participant receipts, requirement traceability and resolved conflicts described below.

Unknown values remain named blockers. Do not fill them with invented account IDs, guessed endpoints, unlimited budgets or implicit approval.

## Mandatory existing-governance gate before planning and implementation

Every participant must ground its contribution in the user's designated existing governance sources, including the specified coursework and prior-conversation records in connected private document/spreadsheet systems, plus the existing organizational and project governance/risk designs. Generic governance principles are insufficient substitutes. The exact source names, account locations and private links belong only in the authorized private manifest, not in this public document.

First locate and read the user's existing source-pack hub in the connected private knowledge workspace, following its linked sheets and other sources as needed. Preserve its organization and content; do not assemble a replacement hub or edit the sources. Maintain a private reference manifest of that existing material with stable source IDs, exact accessible links, document/tab/range or section scope, revision/version or snapshot hash, retrieval time, owner/authority and applicable requirements. Record what was actually read and what was unavailable; titles, search snippets and remembered summaries alone do not establish inspection of required content.

Before substantive planning/build contributions, each participant returns a source-reference receipt tied to the manifest revision and its authorized view. The receipt identifies inspected source IDs/versions, relevant requirements, applicability and unresolved conflicts. A coordinator's assertion that everyone has the packet is not a substitute for each participant's receipt. A provider unable to read an authorized source representation is blocked at this gate; do not fabricate a receipt.

Map governance requirements to architecture choices, task constraints, acceptance tests and review evidence. Resolve contradictions according to source authority and the user's current direction; escalate consequential or ambiguous conflicts to the user and record the decision before proceeding. External source content is evidence of requirements, not permission to widen tools, data sharing or execution authority.

Required inaccessible, incomplete or conflicting sources block the affected planning and all PolyMind implementation until resolved. The private gate record must establish manifest completeness, actual inspection by every required participant, requirement traceability and resolved decisions. A roster change or material source revision invalidates affected receipts and requires renewed review.

Do not publish source contents, private links, personal coursework details or sensitive governance requirements in this repository, prompts to unapproved providers, public PRs or CI logs. Any cross-provider disclosure needs its own applicable authorization. Public evidence may report only a sanitized gate status and opaque references that reveal no private content.

Read-only source discovery and separately authorized installation prerequisites may continue while this gate is pending. Neither satisfies the gate or permits PolyMind implementation to start.

## Phase 1: inventory actual capabilities

Build a versioned inventory using read-only checks where available. For every intended provider/model, distinguish desired, documented, connected, verified and enabled-for-this-task.

Record the supported integration route; model access; tools/agents exposed through that route; consumer-app-only features; account scope; required permissions; input/context limits; usage/pricing visibility; idempotency/cancellation; and last evidence timestamp.

Do not make billable calls merely to check availability. A necessary live probe requires its own bounded authorization. Reading documentation establishes documented support, not a working connection.

Deliver:
1. A full roster with available, blocked, unsupported and unverified entries.
2. A provider/tool capability catalog grounded in actual evidence.
3. The concrete missing permissions or setup steps that prevent intended participation.
4. A proposed usable bootstrap route and its failure/stop boundaries.

The vision includes broad participation. Where not every intended provider is connected, the user decides whether the bootstrap proceeds with the explicit available roster or waits. That exception applies to this task, not a permanent reduction of PolyMind's ambition.

## Phase 2: shared context and independent contributions

Prepare one versioned bootstrap packet containing the corrected product definition, this work order, repository baseline when resolved, verified capability catalog, roster, constraints, acceptance criteria and open decisions.

Only after the mandatory existing-governance gate is satisfied, every available authorized model receives the same core task frame and is told that it is collaborating with the other named participants. Respect provider-specific disclosure limits and record any differing context views. A participant must know which capabilities are available to the team and which it may actually request.

Ask each for an independent initial contribution before sharing peer answers:
- Proposed application architecture and minimum useful product slice.
- Research questions, supported integration routes and evidence gaps.
- Shared context/state model and participant/capability contracts.
- Task breakdown, dependencies and recommended capability ownership.
- Security/privacy/spending boundaries and acceptance tests.
- Risks, alternatives, assumptions and unresolved decisions.

Do not fabricate contributions or substitute the coordinator's opinion for a missing model response. Responses include work-order/context revision, provider/model identity where exposed, evidence and limitations.

## Phase 3: one coordinated build plan

Share relevant authorized peer contributions. Have participants identify useful combinations of strengths, reconcile contradictions and refine the task graph. Debate is a technique here, not the product definition.

The coordinator produces one implementation plan with:
- Chosen app architecture and reasons tied to evidence.
- Concrete tasks, dependencies, owners and expected artifacts.
- Model/agent/tool capability assignments, scoped authority and budgets.
- Shared context/versioning, participant awareness and synchronization design.
- Minimal usable interface and durable task/approval/progress behavior.
- Test matrix, schema/API contracts, rollout sequence and known feature gaps.
- Material dissent and the exact decisions still requiring the user.

Use bounded rounds and a final deadline. No majority vote expands permissions, hides a provider gap or resolves an unsupported technical claim. Freeze the accepted plan revision before implementation.

## Phase 4: OpenClaw → Cursor builds the app

The mandatory existing-governance gate must be satisfied before any implementation dispatch. The approved implementation route is **OpenClaw orchestration → Cursor as the sole code/test writer**. The other models continue contributing architecture, research, task decomposition, analysis and review. They do not edit the same codebase independently or start competing implementation agents.

Before dispatch, identify the actual PolyMind repository and baseline, reconcile newer source, verify a single isolated writer, and apply the [OpenClaw → Cursor contract](OPENCLAW_CURSOR_WORKFLOW.md). That contract's unrelated application-recovery example is not the first PolyMind task.

Proposed first application increment:
1. Versioned conversation/task context and participant roster schemas.
2. Capability catalog with explicit supported/blocked/unknown states.
3. A shared chat/task workspace showing who is involved, current assignments and progress.
4. A bounded coordination/task graph with one authoritative state record.
5. Adapter interfaces and synthetic model/tool implementations for offline tests.
6. Permission/budget/stop boundaries, artifact provenance and evidence views.
7. A documented bridge for importing or referencing bootstrap context without copying secrets.

Synthetic adapters support safe engineering verification; they are not a substitute for the participating models' real authorized collaboration, nor are they evidence of live provider integration. Any later real adapter activation requires its own permission and verification.

Cursor returns changed files, exact commit, test commands/results, schema/migration notes, known gaps and criterion-by-criterion evidence. If Cursor or its authorized route is unavailable, return a useful blocked handoff; do not switch code writers.

## Phase 5: all-participant validation and revision

Publish a draft PR only where the implementation work order authorizes publication. Freeze an immutable candidate SHA and one review packet containing baseline/diff, accepted plan, shared-context contracts, tests/CI and known limitations.

Every available authorized participant in the accepted bootstrap roster reviews that same SHA independently. Then synthesize findings into one prioritized Cursor revision request. Keep finding provenance and consequential dissent.

Cursor alone revises. Each new commit invalidates all previous exact-commit approvals and triggers review of the new SHA by the roster. Verify current CI and acceptance evidence; missing checks are not passing. Bound the revision cycles and escalate unresolved material concerns rather than looping indefinitely.

Acceptance means a verified first PolyMind application increment and a truthful integration inventory. It does not mean every marketplace provider, proprietary agent or consumer plugin has been integrated.

## Bootstrap acceptance and handoff

The first increment must demonstrate, with explicit offline/live labels:

- Every required participant inspected the designated existing governance sources and returned a version-bound source-reference receipt; requirements are traceable and conflicts resolved without publishing private materials.
- The actual authorized models collaborated on building PolyMind, with attributable contributions and a visible record of missing participants.
- No finished PolyMind instance was required to coordinate the work.
- The shared-context scaffold represents the same goal, roster, capability awareness, revisions and task dependencies across participants.
- The app exposes one coherent conversation/task experience, with transparent partial integration coverage.
- The coordinator can assign complementary capabilities without silently reducing the requested roster.
- Tool permissions, data disclosure, cost caps, stop/revocation and untrusted external content are enforced at the designed boundary.
- Duplicate events, stale context, unavailable providers and uncertain effects preserve correct state.
- One Cursor writer produced the implementation; the latest reviewed commit has criterion-specific evidence and truthful test/CI results.
- ClawCare's independent source, worker behavior and launch path were not made dependent on PolyMind.

Deliver the app increment, draft PR/evidence, remaining integration gates and the next scoped work order. Benchmarks and generic demonstration tasks come later to evaluate and harden the app; they are not the initial build objective. Merge, production launch and new live integrations require separate authority.
