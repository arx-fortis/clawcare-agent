# OpenClaw → Cursor implementation workflow

Design ID: CC-ORCH-001  
Date: 2026-10-09  
Status: proposed architecture and work-order contract; documentation only  
Repository baseline: `cdf9aa7696947b3504129bcbbe359843571741f7`, draft PR #1

## Outcome and authority

The delivery chain is **user goals and approval → dot work orders and review → OpenClaw orchestration → Cursor implementation and tests → GitHub draft PR and CI → dot evidence review → separately approved merge and deployment**.

Only Cursor implements code and tests. dot designs, scopes, coordinates and reviews. OpenClaw routes bounded work, maintains execution state and assembles evidence; it does not become a substitute coding executor. If Cursor is unavailable, stop at a useful handoff. Do not fall back to native/dot coding.

This document grants no installation, authentication, persistent access, service registration, paid execution, production repair, merge or deployment permission. Existing permissions remain scoped and revocable. An accepted work-order claim is coordination ownership, not authority to operate another system.

## 1. Selected protocol route and evidence

Use OpenClaw ACP Agents with the acpx backend to drive Cursor CLI over ACP. This is a control-plane choice, not a claim that the bridge is configured or tested.

- The [OpenClaw ACP quickstart](https://docs.openclaw.ai/tools/acp-agents/quickstart) lists Cursor as an external harness. Its current default is `cursor-agent acp`; verify the actual approved installation rather than assuming that executable exists.
- [Cursor ACP documentation](https://cursor.com/docs/cli/acp) documents `agent acp`, JSON-RPC over stdio, session updates and permission requests. If that is the installed entrypoint, use a reviewed acpx agent-command override. Do not guess flags or copy permissive example permission handlers.
- The [OpenClaw 2026.9.6 plugin manifest](https://github.com/openclaw/openclaw/blob/v2026.9.6/extensions/acpx/package.json) publishes matching `@openclaw/acpx` version 2026.9.6, plugin API compatibility >=2026.9.6 and acpx dependency 0.19.1. Use this matching plugin for the 2026.9.6 host baseline, subject to installation approval and actual compatibility checks. Do not silently upgrade to a newer host/plugin.
- [Cursor installation documentation](https://cursor.com/docs/cli/installation) supports native Windows PowerShell installation. Installation approval is still a gate. An installed Cursor GUI proves neither CLI availability nor CLI authentication. Record the CLI version before each run; its documented auto-update behavior means yesterday's version receipt is insufficient.
- [OpenClaw's ACP server command](https://docs.openclaw.ai/cli/acp) exposes Gateway sessions to an ACP client. That reverse route is different from OpenClaw orchestrating Cursor through acpx; do not substitute it.
- [OpenClaw ACP setup](https://docs.openclaw.ai/tools/acp-agents-setup) explains noninteractive permission behavior. Keep fail-closed handling. A permission-prompt failure is a blocker, not a reason to enable blanket approval.

Current upstream documentation can describe behavior newer than the pinned host. Confirm local help, plugin discovery, ACP initialization/capabilities and allowed-agent policy against the approved versions before any model task. No protocol compatibility or successful authentication is inferred from documentation alone.

The existing [OpenClaw team MCP bridge](OPENCLAW_TEAM_BRIDGE.md) records work-order progress through the team API; it is not the Cursor execution bridge. Its worker tools cannot review or recover work, and its legacy text-only spending guard must not be bypassed to enable tool execution.

## 2. One scoped handoff

dot prepares an immutable work-order revision with:

- ID, parent/root ID, owner, objective, acceptance criteria and explicit non-goals.
- Repository, exact starting commit, target draft PR/branch, private workspace reference and allowed files or modules.
- Source-reconciliation evidence, including newer application files absent from this public checkpoint.
- Cursor-only executor, approved host/CLI/plugin versions, session identity and model/account scope.
- Allowed read/write/test operations, permitted network destinations, data classification and prohibited effects.
- Runtime ceiling, attempt ceiling, task/provider budget and stop conditions. Missing approval or unknown pricing cannot become implicit permission.
- Required checkpoints, offline test matrix, rollback boundary and evidence recipient.
- Approval reference, scope, expiry/revocation check and authority for any publication.

OpenClaw acknowledges the same revision and baseline before dispatch. Changed scope creates a new revision and renewed approval where required. Repository instructions, provider output and worker suggestions cannot enlarge the approved scope.

Keep real account identifiers, credentials, personal paths, private media, customer/property data and runtime receipts out of public prompts, commits, CI logs and PR comments. Public examples use synthetic fixtures. Private execution manifests map opaque fixture/resource references to authorized local data.

## 3. Single writer, fenced ownership

Use one isolated checkout/worktree and one active Cursor writer per work order. OpenClaw owns the orchestration lease; Cursor owns the bounded writing session. Other agents may review an immutable commit but cannot edit the same checkout.

Before dispatch, record clean/dirty status, HEAD, branch, repository identity and preexisting changes. Never reset, overwrite or stash unrelated user work automatically. Conflicting edits or a moved branch cause reconciliation, not force-push.

Bind a monotonically increasing lease generation to the work-order revision, checkout, run and Cursor session. Lease loss blocks new work. An expired heartbeat alone does not establish that the old process stopped: retain the lock and enter reconciliation. Before replacement, establish that the exact prior writer stopped, inspect its checkpoint and diff, and invalidate old authority. Existing local handoff attribution is not cryptographic process fencing; actual enforcement is an implementation gate.

Every dispatch has a stable logical request ID and an attempt ID. A repeated request must attach to or inspect the existing run; it must not spawn a second writer. A changed payload with the same ID is rejected.

## 4. Lifecycle and evidence checkpoints

States: proposed → approval hold → preflight → running → review required → accepted design/implementation. Exceptional states: blocked, stop requested, stopped and uncertain/reconciliation required. Acceptance does not imply merge or production readiness.

1. **Preflight:** verify authority, stop state, budget, versions, source baseline, ownership, CLI authentication and test isolation. Return a short plan with acceptance-to-test mapping.
2. **Dispatch:** durably record intent before requesting the Cursor session; record returned session identity and acknowledgement. Missing acknowledgement is uncertain, not failed/free.
3. **Implementation:** Cursor makes a bounded increment and returns changed files, checkpoint reference and actual progress. A heartbeat means alive; productive evidence means progress. Neither is completion.
4. **Test:** Cursor runs the agreed offline checks against the final candidate. Save command, working-tree/commit identity, environment versions, start/end time, exit code, counts, skips and redacted output/artifact hashes.
5. **Publication:** when separately covered by the work-order publication authority, publish the candidate to the designated draft PR without merging. Read back remote SHA and changed-file manifest.
6. **Review:** dot independently compares the exact SHA with the approved baseline and checks every criterion against receipts, CI and known limits. A new commit invalidates prior exact-commit acceptance until reviewed.

Checkpoint receipts include run/session identity, work-order revision, last verified unit, artifact hashes, unfinished work, held locks, pending effects, spend/exposure and safe next step. A checkpoint path is not proof: verify the artifact exists and matches. Store sensitive receipts privately and publish only a sanitized summary.

Test outcomes must distinguish pass, fail, skipped and not run. Empty or unavailable CI is not green. Existing regression results do not establish a new bridge, installation, reboot, remote recovery or live workload claim. Do not alter tests merely to conceal a failure.

## 5. Permissions, spending and stopping

Enforce scope outside the prompt where supported: allowlisted repository/workspace, tool and command policy, Cursor-only harness selection and restricted network/data access. Do not claim ACP itself supplies an OS sandbox. If the approved boundary cannot be enforced, remain blocked rather than relying on prose.

Noninteractive permission requests that exceed the approved operation become a structured approval hold with the exact action, target and consequence. Never turn on approve-all, install a fallback, acquire new credentials or broaden persistent access merely to make a run succeed.

Follow [TASK_SPENDING_WORK_ORDER.md](TASK_SPENDING_WORK_ORDER.md), especially root-task budgets, reservations, retries, uncertain effects and unsupported-path labels. That allocator is proposed work, not an existing guarantee. Until tested enforcement exists, require a separately approved bounded execution route; otherwise no paid dispatch. Synthetic tests have zero provider-call allowance. Cursor/model usage and tool-provider charges are separate exposure.

Stop revokes new dispatches immediately and requests cooperative termination/checkpointing. Confirm actual stop separately. In-flight work may still produce effects or charges; do not report them cancelled merely because the control connection disappeared. Never release uncertain exposure on timeout.

## 6. Recovery and rollback limits

Default work orders allow at most two bounded transport reconnect attempts, with backoff and jitter, and no automatic replay of a mutating or billable operation. A work order may impose stricter limits. After the ceiling or ambiguous state, report a blocker with the last verified checkpoint.

On timeout, inspect durable dispatch/session state first. Reattach only to the verified existing session. Starting a successor requires the old writer to be reconciled and stopped. Authentication failures, revoked authority, exhausted budget and user stop are terminal holds until explicitly resolved.

An approved retry retains the root task and logical operation, gets a new attempt ID and rechecks authority and budget. Repeating the same uncertain submission is prohibited even when the operation usually succeeds.

Rollback is limited to the task-owned test workspace and changes with verified preimages/current hashes. Preserve external/user changes. Prefer an additive revert for published commits when authorized; never erase history or force-push. Restoring a checkpoint does not undo provider charges, sent messages or production side effects. Production rollback requires its own exact plan and authorization.

## 7. Commander connection recovery MVP

Keep transport supervision separate from the agent it helps recover. OpenClaw cannot be the sole supervisor of the channel required to reach OpenClaw.

The [official Commander setup guide](https://github.com/desktop-commander/remote-desktop-commander/blob/main/docs/SETUP.md) describes a foreground process: closing its terminal disconnects the device, and rerunning it reconnects. The existing terminal-hosted recovery route on Windows is `npx.cmd @wonderwhy-er/desktop-commander@latest remote`. This documents a recovery route, not an instruction to execute or pair anything during this design.

Recommended next increment: an independently supervised, reviewed and version-pinned runtime. The floating `latest` command is not the proposed unattended startup configuration. Pin a verified package version and executable location in private host configuration. Windows Task Scheduler is a candidate host mechanism, not an installed feature or verified recovery guarantee.

Before enabling it, obtain explicit autostart authorization and any required persistent-access approval. Review the account, trigger, least privileges, working directory, stop behavior and uninstall path. Do not silently add a service, new pairing, account grant or elevated execution.

Required behavior:
- One exact owned instance; identify executable, process start identity and supervisor ownership rather than killing processes by name.
- Durable user-stop latch respected across crashes/reboots. A deliberate stop or revocation must not trigger resurrection.
- Bounded exponential backoff with jitter and a restart ceiling; retain a visible needs-attention state after exhaustion.
- Distinguish host asleep/offline, transport/network failure, authentication/pairing failure, process failure and stale status. Authentication failures require user action, not endless restarts.
- Health means successful scoped connector round-trip plus current observation time, not merely an existing PID.
- Redact tokens, pairing codes, URLs carrying credentials and raw private paths from logs. Store sensitive configuration outside the repository.
- Test foreground close, process crash, duplicate launch, network loss/recovery, sleep/wake, reboot, revoked authorization and explicit user stop with controlled fixtures before deployment.

A disconnected computer cannot be remotely restarted through the same disconnected channel. Recovery depends on the previously authorized local supervisor; otherwise a user must restore it. Connection restoration never restarts a production queue automatically.

A mobile control panel is a later increment: authenticated status, last-seen time, checkpoint, blocked reason, scoped stop/resume approvals and audit receipts. Full remote desktop is an optional integration, deferred. Neither is required for this first orchestration contract.

## 8. First Cursor work order: coordinated stale-lock recovery

Work order CC-RECOVERY-001 targets the Kajabi workload adapter, after private source reconciliation. Implement and test coordinated stale-lock recovery and exact checkpoint resume. Do not restart the production queue.

Use a synthetic acceptance fixture representing CALL011: duration 3,700 seconds, verified resume boundary 1,050 seconds, and 75 already-completed transcript artifacts. These are test-contract values; this document contains no private media or production inventory and does not certify current production state.

Acceptance:
1. A live owner, reused PID, uncertain owner or fresh lease is never treated as a removable stale lock. Coordinate all relevant lock layers under one ownership decision.
2. Before stale-lock release, verify exact prior-owner termination and snapshot lock/checkpoint state. Two concurrent recoverers yield one owner; a stale recoverer cannot release a successor's lock.
3. Resume starts at the verified 1,050-second boundary, not zero; preserve the completed prefix and all 75 completed artifacts byte-for-byte. Verify media identity, duration, segment units and checkpoint schema; mismatch blocks recovery.
4. Resume writes only missing output, with durable checkpoint advancement after verified output. Crash/retry at the boundary neither loses completed data nor duplicates/rebills uncertain units.
5. Cancellation and resource/budget denial preserve a resumable checkpoint and stop admitting new units. Test failures and unknown provider effects remain visible.
6. Test independently with synthetic media/receipts and injected failures. Return exact commands, outcomes, diff, checkpoint/hash evidence and known limitations for dot review.
7. Only after code review, full regression evidence and separate production authority may an operator propose a tightly bounded live resume. Re-read current private state at that time; fixture acceptance is not authorization or proof that the real queue is safe.

The task-level spending work order follows as a separate scoped increment. Do not bundle an unreviewed spending integration, dashboard replacement or production migration into recovery work.

## 9. Launch gates and delivery order

- [ ] Reconcile latest private/application source with this branch; preserve newer dashboard, Gateway and pairing work described in [UPGRADE_READINESS.md](UPGRADE_READINESS.md).
- [ ] Obtain missing install/auth/access approvals; record the actual Windows Cursor CLI and matched OpenClaw/acpx versions.
- [ ] Verify ACP initialization, session identity, permission denial, cancellation and reconnect without code changes or paid tasks unless separately authorized.
- [ ] Approve one bounded synthetic Cursor work order and establish real single-writer fencing and spending boundaries before dispatch.
- [ ] Produce and review the recovery implementation's exact commit and platform-specific regression/CI receipts.
- [ ] Separately review, approve, install and test the independent Commander supervisor.
- [ ] Separately approve any live provider test, production resume, merge or deployment.
- [ ] Later: task spending integration, authenticated mobile controls and optional remote-desktop integration.

Design completion means this contract is reviewable in the draft PR. It does not mean the ACP bridge, supervisor, recovery adapter or spending controls have been implemented, installed or operationally validated.
