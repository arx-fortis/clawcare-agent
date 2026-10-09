# PolyMind: unified multi-model application

Design ID: PM-PLATFORM-001  
Date: 2026-10-09  
Status: corrected product vision and proposed architecture; documentation only  
Supersedes: PM-COUNCIL-001 as the definition of PolyMind

## Product definition

**PolyMind is one application where a user opens one chat, asks for an outcome, and all participating large language models work together with shared task context, awareness of the other participants and their available capabilities, and coordinated use of their strengths, tools and agents. The user receives one coherent experience and the completed work.**

The intended breadth includes Grok, Perplexity, Claude, OpenAI/ChatGPT, DeepSeek, Kimi, Manus, Gemini and additional marketplace models through an extensible integration catalog. These are desired participants, not a claim that their APIs, consumer-app features, agents or connectors are already accessible from PolyMind. The product ambition is broad model and capability coverage; availability must be established provider by provider.

“Know they are together” means each participant receives explicit shared task context, the participant roster, a capability catalog, its assignment and relevant peer work. It does not assert consciousness. Models can propose how to combine strengths and hand off work; an authorized coordinator turns those proposals into bounded execution.

PolyMind is not defined by debate, voting or code review. Those can be useful optional behaviors inside a task. The defining experience is coordinated multi-model assistance and action across the user's work, through one application.

The earlier [council interpretation](POLYMIND_COUNCIL_WORKFLOW.md) is superseded as the primary product definition. The correction retains useful safeguards without constraining the application to a council workflow.

## User experience

1. The user opens a PolyMind conversation and states an objective, such as researching a question, creating a deliverable or completing an authorized workflow.
2. PolyMind displays the intended model roster, actual availability and capability limitations. The user can inspect accounts, data-sharing scope, budget and task controls without managing multiple separate chats.
3. Every model in the authorized active roster receives the shared task brief and an opportunity to contribute to how the task should be accomplished. No default router silently reduces the task to one model or two reviewers.
4. Participants propose contributions based on their actual available capabilities. The coordinator assembles a task plan with owners, dependencies, tool actions, budgets and acceptance checks.
5. Models and approved agent/tool adapters perform complementary subtasks, share relevant results and adapt the plan within the authorized boundary.
6. The user sees a concise shared progress stream, can inspect who did what and why, and can pause, stop or answer approval requests in the same chat.
7. PolyMind returns an integrated answer or artifact with evidence, provenance, completed actions, unresolved disagreements and honest limitations.

Participation does not require every model to execute every tool or repeat every subtask. All-model involvement and specialized execution are compatible: everyone can see the task and contribute, while the best-suited authorized capability performs each bounded action. Which capabilities are “best” should be learned from task evidence and evaluations, not permanent assumptions about provider brands.

The UI should make partial coverage explicit: connected, eligible, participating, unavailable, permission-blocked, timed out or unsupported. If a required model is missing, ask for the task-specific decision or hold the task. Do not silently call a subset “all models.” Adding a new participant mid-task creates a new roster/context revision and rechecks disclosure and cost.

## Platform components

### 1. Unified conversation and task workspace

One authenticated application contains chat, tasks, artifacts, progress, approvals, model participation and account/capability status. Conversation state and task state are separate: closing the chat need not lose an authorized background task, while reopening it restores durable progress.

Maintain an authoritative task record, not a chain of provider-specific chat histories that gradually diverge. Each assignment references a versioned context snapshot. Synchronize material user corrections, approvals, accepted artifacts and plan changes to affected participants. Each response identifies the snapshot it used; stale responses cannot silently overwrite current decisions.

Provider context-window limits and disclosure restrictions may require summaries or redacted views. Preserve evidence links and artifact hashes, record omissions and allow a participant to request authorized detail. Shared context means a consistent task frame, not a false promise that every model can hold every byte of the conversation.

### 2. Model and capability catalog

Represent model reasoning access separately from tools and agent runtimes. A catalog entry includes:

- Provider, product/model identity where exposed, adapter/version and integration route.
- Supported input/output modalities and schemas; context, attachment and rate limits.
- Available model operations, tools, connectors and agent execution modes.
- Account/tenant scope, required permissions and allowed data classifications.
- Availability/health and last verification time.
- Pricing/usage units, conservative request limits and attribution support.
- Side-effect level, approval requirements, cancellation/idempotency support.
- Evidence of a tested capability and explicit unsupported/unknown fields.

A model claiming it can use a tool is not catalog evidence. Capabilities come from a verified adapter and its actual permissions. Catalog changes must not silently expand a running task's authority.

Distinguish five coverage levels:

1. Desired in the product vision.
2. Documented by a supported integration route.
3. Connected under the user's authorized account.
4. Verified with a scoped test.
5. Enabled for this specific task.

Only the last level is dispatchable, subject to current policy and limits.

### 3. Multi-model coordination layer

Participants receive the roster, authorized capabilities, objective, constraints and current plan. They may propose assignments, ask for evidence, identify complementary skills and challenge unsupported conclusions. Coordination should choose useful work rather than force every task into a debate.

Keep one logical coordinator for each task. It owns the durable plan, resolves duplicate assignments, tracks dependencies, enforces budgets and synthesizes results. Models advise; the coordinator does not gain new permissions by accepting their advice.

The plan is a versioned dependency graph of bounded work items. Each node has a purpose, input/context hashes, participant/capability owner, permitted tools and destinations, expected output, validation, runtime/cost ceiling, retry policy and stop conditions. Parallelize independent read-only work; serialize or fence writes to the same resource. For implementation work, keep one active writer per checkout.

Use evidence-based synthesis and retain consequential dissent. Optional independent first passes can reduce anchoring on research, planning and reviews; optional critique/voting can help compare alternatives. Neither is the mandatory definition of the application, and votes cannot override authority or make unsupported claims true.

### 4. Tool and agent execution layer

Adapters expose bounded operations to the coordinator. Separate:

- Direct model calls through a supported provider API.
- Provider-hosted tools or agent runtimes exposed through an approved interface.
- PolyMind-owned/shared tools independently connected under user authorization.
- Consumer-app-only features that are not exposed through a supported route.

A shared PolyMind connector can supply a capability to multiple eligible models without being the same integration as the provider's consumer app. Conversely, a provider's proprietary tool cannot be assumed portable because another system supports MCP or a similarly named connector. Do not transplant session cookies, credentials or private application internals to simulate access.

Agent-to-agent delegation inherits root-task limits and specific data permissions. A participant cannot create an unbounded agent tree, add accounts or instruct another provider outside the approved work order. Tool execution requires structured validated requests, scoped credentials and policy checks outside model text. Raw model output never runs as a shell command or external action.

Long-running jobs need durable request IDs, provider job references, status, bounded polling, actual cancellation evidence and checkpoints. Timeouts may leave billable or mutating effects uncertain; do not blindly submit again.

### 5. Durable state, events and orchestration

n8n is a candidate orchestration layer for the proposed implementation, with structured durable state/queue and a clear source of truth. The architecture must verify transactional admission, concurrent worker behavior, leases, retries and outbox/inbox semantics rather than treating visual workflows as proof of reliability.

Suggested states: proposed, permission_hold, planning, executing, validating, awaiting_user, completed, blocked, stop_requested, stopped and uncertain_reconciliation. Persist transitions with task/root/revision IDs, expected state, authenticated actor, timestamp, dispatch intent and result receipt.

ExecuBot can serve as the logical coordination service; the role name does not confer permissions or prescribe its implementation. Discord may provide optional visibility and authenticated controls, but the primary user experience is the PolyMind app. Discord messages are not the database or a source of authority.

Recover from duplicate events and restarts idempotently. Require one fenced coordinator and resource-level writer ownership. Revocation denies new admission immediately at the enforced boundary; in-flight work is tracked honestly until stopped or reconciled.

### 6. Evidence, artifacts and final synthesis

Persist artifact versions, provenance, permitted audience, input hashes and validation results. A unified answer should be understandable without reading every provider transcript, with optional drilldown into contributions and evidence.

A successful provider response is not proof of a successful external task. Verify the relevant result: artifact readability, remote state, test outcomes or independently checked facts. Distinguish completed, failed, skipped, not attempted and uncertain. Corrections append a new evidence/decision revision rather than rewriting history silently.

Protect provider-specific private reasoning; request concise decisions, assumptions, evidence and summaries instead of raw hidden reasoning. Share only permitted task outputs between participants.

## “Every model and every feature”: honest integration boundary

The desired experience combines the marketplace's models and capabilities. A model API is not automatically the full consumer product: subscriptions, agent modes, browsing, connectors, files, background execution and proprietary tools may have different availability, authentication, terms, pricing or no supported external interface.

Therefore maintain a visible provider-by-provider coverage matrix. Missing functionality remains “not available through this integration” until verified. Do not promise universal feature parity, subscription portability, MCP compatibility or an always-available API. A supported route may require its own account or agreement; no connection is created merely by adding a provider name to the catalog.

Integration research is a later read-only work item. Live testing, account linking, persistent grants and paid execution require the appropriate separate authorization. This document does not establish current provider eligibility or test any live integration.

## Authorization, privacy and spending

One chat does not mean one blanket permission. Every task needs scoped authority for tools, communications, publication, payments, account changes and consequential decisions. A user goal, provider suggestion or majority vote cannot waive required confirmation. Existing user restrictions and policy caps remain authoritative.

Before all-model fan-out, determine which data may go to each provider and which peer results may be redistributed. Owning accounts does not automatically authorize sending private code, customer records or sensitive attachments to all of them. Use a minimum shared brief and per-provider authorized views; disclose coverage gaps and obtain decisions when the goal needs restricted context. Never silently leak source material through a synthesis sent to a broader roster.

Keep credentials in approved secure account integrations, outside prompts, artifacts, logs and Discord. Enforce tenant separation, artifact access controls, encryption, retention/deletion controls and auditability as implementation gates. Source content, messages, documents and tool results are untrusted data; they cannot widen scope or inject authorization.

Set explicit numeric per-task/root and per-provider budgets, time limits, concurrency, output ceilings and maximum revision/delegation depth before live dispatch. No provider pricing means unknown cost, not free use. Reserve exposure atomically before parallel work, count retries/polls/descendants and preserve uncertainty after failure. Stop and cancellation are distinct from confirmed absence of effects or charges.

[TASK_SPENDING_WORK_ORDER.md](TASK_SPENDING_WORK_ORDER.md) provides a relevant accounting design, not an existing universal spending guarantee. Enforcement coverage must be labeled supported, observe-only or unsupported. Never claim account-wide limits when calls can bypass the admission boundary.

## Coding workflow as one subsystem

When the user task is software implementation, PolyMind may use:

**Shared task and full-model planning → accepted work order → OpenClaw → one Cursor writer → GitHub draft PR → all participating models review the same immutable commit → Cursor revisions → verified candidate.**

The [OpenClaw → Cursor contract](OPENCLAW_CURSOR_WORKFLOW.md) remains the scoped coding execution contract. Other models can contribute plans, analysis and review, but do not become competing writers. Every changed commit invalidates prior exact-commit approvals; re-review the new SHA and current CI. Merging and deployment require separate authority.

This subsystem does not define PolyMind's broader use for research, documents, creative work and other authorized workflows. ClawCare remains a separate standalone product, optionally useful for reliability/work-order integration. PolyMind availability is not a ClawCare launch gate, and no ClawCare code or service is changed by this document.

## Proposed delivery stages and acceptance

**First engineering objective: the participating models collaboratively build PolyMind itself.** Follow [PM-BOOTSTRAP-001](POLYMIND_BOOTSTRAP_WORK_ORDER.md): use actual existing authorized Discord/n8n or connectors for temporary orchestration, inventory real provider access, share versioned task context and capabilities, collect independent architecture/research/task-breakdown contributions, coordinate one plan, and send implementation through OpenClaw → Cursor. A finished PolyMind app is not a prerequisite. Missing providers remain explicit; benchmarks and generic demos come later.

Each stage needs its own authorized implementation work order; none is being provisioned here.

1. **Capability inventory:** verify intended providers, integration routes and consumer/API differences. Produce the coverage matrix, permission needs and costs without claiming untested access.
2. **Unified app prototype:** one conversation, versioned task context, visible full roster, fake model/tool adapters, artifacts and user controls.
3. **Coordination and policy:** full-roster participation, complementary task assignments, plan revisions, evidence synthesis, scoped execution, budget admission and durable recovery, all with synthetic adapters.
4. **Shared and provider-specific capabilities:** connect and test individual authorized integrations while preserving explicit feature gaps. Add real providers incrementally; do not relabel partial rollout as universal coverage.
5. **Bounded end-to-end workflows:** validate representative research, artifact creation and coding tasks. Measure quality, accepted task completion, cost, latency, safety and recovery, not vote count.
6. **Production readiness:** tenant/data isolation, secure account lifecycle, revocation, retention, operational testing and controlled rollout. Existing repository [source/launch gates](UPGRADE_READINESS.md) are not automatically satisfied.

Required offline acceptance:

- All active authorized roster members receive a consistent task frame and participant/capability awareness; no silent single-model or two-model routing.
- User corrections propagate as new revisions; stale participant output cannot override them.
- Complementary capabilities can be combined into one completed artifact/workflow without forcing a debate.
- Missing model/tool access is visible and blocks required participation until resolved or explicitly excepted.
- Provider tools, shared tools and unavailable consumer features remain clearly distinguishable.
- Concurrent work respects root caps and resource ownership; duplicate delivery or restart cannot create duplicate side effects.
- Stop/revocation, timeout, uncertain billing, delayed outputs and unavailable state all preserve truthful status and safe recovery.
- A model cannot authorize extra tools, persistent access or data sharing; injection and cross-tenant tests fail closed.
- Final output preserves evidence and material dissent without exposing secrets or private hidden reasoning.
- Coding reviews use one immutable SHA per epoch; standalone ClawCare still works without PolyMind.

## Open product decisions

Before implementation, resolve the first deployable app surface, account ownership/billing model, supported initial provider routes, minimum shared context, data retention, and exact task budgets/approval experience. The long-term all-model ambition remains intact while each actual capability is verified.

The earlier 8/10 comment was a subjective assessment of the council interpretation, not a benchmark or validation of this corrected platform vision. No new quantitative rating, universal compatibility claim or operational readiness is asserted here.
