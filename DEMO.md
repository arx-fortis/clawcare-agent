# 70-second demo outline

Only show evidence from a run. This is an HTTP health-monitor fixture demonstration, not a Gateway repair claim.

0–10s: ClawCare is a background reliability worker with durable support cases. Show worker process running.
10–25s: Fixture returns 503. Show one incident and its work order/audit; repeated polls keep one case.
25–35s: Stop/restart worker. Show same incident ID survives in SQLite.
35–45s: Attempt repair without approval; show rejection. Record approval, run clearly labeled simulation. Endpoint remains unhealthy and case stays RECOVERY_REQUIRED.
45–60s: Restore fixture health externally. Worker observes recovery and closes the case; audit attributes recovery externally.
60–70s: Show ledger snapshot and handoff. State: real monitoring, persistent audit; real Gateway repair and multiplayer integration are not yet demonstrated.

Do not claim simulation fixed the endpoint. Do not show credentials or personal workspaces. A multiplayer contest demo must additionally show real shared agent interaction after it is configured.
