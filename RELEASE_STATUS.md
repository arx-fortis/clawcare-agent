# Release 0.2.0 evidence — 2026-09-28

Implemented: independent Python polling, SQLite durable cases and work orders, one open case per target, real HTTP verification, external recovery closure, per-target scheduling, single-use simulation approval and consistent ledger snapshot.

Tested on Windows / Python 3.14.7: all five unittest cases passed (4.171 seconds). Test fixture used an actual loopback HTTP server and separate worker process. Worker was terminated and restarted; incident identity survived and returned health closed the case. No credentials or production endpoint used.

First test run revealed an unclosed snapshot handle in the test harness. Fixed with contextlib.closing; repeat suite passed. Originals from the downloaded MVP are preserved separately.

Not tested/implemented: actual OpenClaw repair, Gateway state restore, cross-host failover, authenticated multi-user approvals, multiplayer channel, unattended Windows service, live Compose deployment, Agent Index registration/reporting or public user installs. The ledger checkpoint must not be advertised as Gateway recovery.

## Contest gates

Official event page checked 2026-09-28: https://luma.com/zhkhsnpa
Submission deadline extended to September 29, 11:59 PM Pacific; leaderboard snapshot September 30, 11:59 PM Pacific.

- Public MIT repository: https://github.com/arx-fortis/clawcare-agent. Clean standalone distribution; private runtime history/configuration was not published.
- Cross-platform verification: all five tests passed on both GitHub-hosted Windows and Linux, run https://github.com/arx-fortis/clawcare-agent/actions/runs/36519014301.
- Demonstration: demo/clawcare-mvp-demo.mp4 is a 70-second evidence presentation generated from a real isolated HTTP failure/recovery and worker-restart test. It is not a screen recording or multiplayer deployment. Repair execution is explicitly simulated.
- OpenClaw 2.0 multiplayer: requires actual configured shared interaction and evidence; not satisfied by the CLI worker.
- Agent Index: official client https://github.com/plow-pbc/agent-index-client; requires authorized registration identity. Reporting must reflect real usage, never fabricated activity or unrelated agents.
- Video: at least 60 seconds showing real product operation; tests/simulated actions must be labeled.
- Submit/register and host verification: pending, not accomplished by this release package.

Publishing instructions: https://aiworthusing.com/agent-index/publish
The publishing page and client README differ about credential bootstrapping; resolve using the current client/host workflow before sending credentials. Do not put any token in source, chat, video or ZIP.

Next work order: configure and demonstrate a scoped multiplayer OpenClaw instance consuming ClawCare cases, then register/report using the owner's Plow identity.
