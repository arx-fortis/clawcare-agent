# ClawCare 0.3.1 — user-owned runtime connections

ClawCare can now be initialized without supplying any model API key. Users connect
their existing OpenClaw agent, preserving its own model/provider configuration,
or use the coordination system in manual mode without any model connection.

- Private local setup with separate human-owner and agent-worker credentials.
- Generated MCP connector settings contain no provider key or model override.
- Six scoped work-order tools, including progress and handoff with server-derived
  actor identity. Agent tools cannot approve, recover or administer memberships.
- Operator CLI for inspecting and reviewing handoffs independently of the agent.
- No founder credentials, shared provider account or automatic model fallback.
- Windows crash-test synchronization waits for the actual fixture process to exit.

Start with [GETTING_STARTED.md](GETTING_STARTED.md). Python 3.11+ is required.
The suite tests private setup, credential separation, model-free handoff/review,
MCP transport, authentication, concurrency, monitoring and bounded recovery fixtures.

This is a local prerelease. It has no hosted signup, remote multiplayer deployment,
standalone provider-chat client or credential vault. The API must run on the same
machine as its connectors. Human and agent IDs are operator-provisioned principals,
not verified online accounts. A real multi-user OpenClaw run, operational video,
contest usage reporting and organizer verification remain separate validation gates.
Automated clients and synthetic fixtures are not real contest installs or usage.
