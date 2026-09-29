# Start with your own runtime

ClawCare is a local work-order and recovery control plane. Its ledger, API,
background health worker, approvals and handoffs do not require a model API key.
Connect an existing OpenClaw agent when you want model-assisted work. That agent
uses its existing provider and billing account; ClawCare does not supply a key,
proxy requests to a founder account, or fall back to one.

## 1. Create a private workspace

Install Python 3.11+ and download this repository. From the package directory:

```sh
python connect.py init --data-dir ../clawcare-private --workspace my-team --player your-name
```

Choose a new private directory outside the package and outside any shared or
synced folder. Initialization refuses an existing directory rather than replacing
its contents. It sets owner-only permissions before writing credentials (Windows
requires PowerShell; Linux/macOS use mode 0700). If initialization fails, no
existing directory is replaced; a partially created new directory may remain.

The generated files include:

| File | Purpose |
|---|---|
| `agent.token`, `agent.json` | Worker credential for your local agent |
| `operator.token`, `operator.json` | Human owner credential; keep out of agent configuration |
| `openclaw-mcp.json` | Connector entry; no model or provider settings |
| `connection.json` | Selected mode and the two provisioned principal IDs |

The human principal is `your-name`; the agent principal is `your-name:agent`.
These are operator-provisioned identities, not verified online accounts or two
different people. Each real team member needs separately provisioned credentials.
The service checks authority; the credential holder's display name is not proof
of a real-world identity. Agent credentials cannot approve handoffs or manage users.

Credentials expire after 24 hours. Renew them with the offline `team_api.py issue`
command described in [TEAM_API.md](TEAM_API.md), using a new private token file and
the same identity and role. Point the relevant profile/connector at that file.
Expired or unavailable credentials cause failure; there is no shared fallback.

## 2. Start the coordination API

```sh
python team_api.py --root ../clawcare-private serve --port 8765
```

Keep this process running. It binds only to `127.0.0.1`; all connectors must run
on the same machine. Closing this terminal stops the API, but preserves the ledger.
Hosted remote access and automatic API supervision are not included. Do not expose
this prototype with a public tunnel. The independent health monitor has its own
[supervision guide](SUPERVISOR.md).

## 3. Connect your OpenClaw

Merge only the generated `mcp.servers.clawcare_team` entry from `openclaw-mcp.json`
into your agent's existing OpenClaw configuration. Preserve the existing model,
provider credentials, channels and other settings. Grant the six tools documented
in [OPENCLAW_TEAM_BRIDGE.md](OPENCLAW_TEAM_BRIDGE.md) through your agent's tool policy.

No OpenClaw gateway bearer token or Claude API key is requested by this connector.
The local MCP process talks to ClawCare's API with its worker credential. OpenClaw
handles model authentication separately. If your runtime has no working model,
configure your own supported provider there; this package does not yet include
a standalone provider-chat client or hosted credential vault.

Ask your agent:

> Create a work order for this task. Inspect and claim it, record only observed
> evidence, then hand off the stopping point for human review. Do not approve
> your own work or claim that a checkpoint or external change exists without proof.

## 4. Review as the operator

Save a JSON command to a file such as `inspect.json`:

```json
{"operation":"inspect","id":"RETURNED_WORK_ORDER_ID"}
```

```sh
python connect.py command --profile ../clawcare-private/operator.json --request inspect.json
```

After independently checking the handoff evidence, save a review command using
the latest revision from inspection:

```json
{"operation":"review","id":"RETURNED_WORK_ORDER_ID","revision":2,"accept":true,"evidence":"Describe what you actually checked"}
```

Run the same operator command with that file. Do not reuse the sample revision
without checking it. A stale revision is rejected. Do not give the operator
profile or token to an agent, or expose this CLI as an unrestricted agent tool.

## Use without AI

Add `--mode manual` to initialization to omit the OpenClaw connector. The same
operator CLI supports the typed commands in [HANDOFFS.md](HANDOFFS.md) and
[TEAM_API.md](TEAM_API.md), including create, claim, progress, handoff and review.
No model request is made by this path. There is no conversational assistant in
manual mode, and verification remains evidence supplied by the operator.

## What this release does not claim

Local initialization is not hosted signup. It does not give remote teammates
access, import your ChatGPT/Claude conversations, configure Discord, report
contest usage or automatically execute repairs. Coordination state persists,
but the API must be running for new requests. Keep private ledgers and credentials
out of Git, videos and shared chat. AI costs belong to the user's runtime/provider;
control-plane operations themselves do not consume model tokens.
