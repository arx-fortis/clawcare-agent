# ClawCare 0.3.0 — standalone team control-plane prerelease

ClawCare coordinates work ownership, progress, review, recovery and handoff so
the next operator can continue from recorded evidence rather than reconstructing
the previous session. An OpenClaw skill is included; the control plane can run
independently of the agent it supports.

Implemented in this prerelease:
- Durable work orders, scoped resource claims and session expiry/reconciliation.
- Player/agent attribution, validated handoff reports and hash-linked events.
- Loopback API with operator-issued credentials, workspace roles and projects.
- Independent worker supervision and bounded JSON-file repair/rollback adapter.

Validation: 37 local tests passed across the API and regression runs. A synthetic
100-client HTTP test verified 100 distinct claims, 100 correctly attributed
progress records, and one winner among 100 conflicting claims. See
TEAM_TEST_RESULTS.md for measurements and limitations. These are synthetic tests,
not user installations or token usage. New Windows/Linux CI results are pending
at preparation time.

Public use: MIT licensed. Start with HANDOFFS.md for local collaboration and
TEAM_API.md for a private loopback test. Do not expose the prototype HTTP server
to the Internet. No public signup, invitations, hosted application, customer
connectors, or deployed OpenClaw multiplayer integration is claimed.

The earlier 70-second v0.2.0 demo demonstrates the monitoring fixture and labeled
repair simulation only. It does not demonstrate these new team features.

## Contest status

Official rules checked 2026-09-29: https://luma.com/zhkhsnpa
Submission deadline: September 29, 11:59 PM Pacific.
Real OpenClaw multiplayer operation, Agent Index registration, scoped real usage
reporting, a current operational demo and organizer verification remain gates.
Source publication alone is not a contest submission or proof of eligibility.
