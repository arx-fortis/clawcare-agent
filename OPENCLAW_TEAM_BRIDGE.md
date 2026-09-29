# OpenClaw work-order connection

Status: stdio MCP adapter tested against the real local team API, 2026-09-29.
The test identities and fixture are synthetic. A live OpenClaw model-driven run,
real participant handoff, contest usage reporting and video remain unverified.

`team_mcp.py` connects an MCP-capable agent to one operator-selected workspace
and project. It exposes six tools: create, inspect, claim, renew, progress and
handoff. It cannot review, recover, change memberships, execute shell commands
or modify an external business system. The API supplies actor identity from the
credential registry; model arguments cannot override it or select another project.

## Operator setup

Follow [TEAM_API.md](TEAM_API.md) to create a private data directory, provision
a **worker** credential for this participant/agent and start the loopback API.
Keep the plaintext token file outside the repository with owner-only permissions.
Use a separate reviewer credential through an operator-controlled client.

Configure the following entry under `mcp.servers` in an isolated OpenClaw config.
Replace placeholders with absolute paths. The token-file argument is a path,
not the token. Do not put token contents in configuration, prompts or recordings.

```json
{
  "clawcare_team": {
    "command": "ABSOLUTE_PATH_TO_PYTHON",
    "args": [
      "ABSOLUTE_PATH_TO_CLAWCARE/team_mcp.py",
      "--port", "8765",
      "--workspace", "demo",
      "--project", "default",
      "--token-file", "ABSOLUTE_PRIVATE_TOKEN_FILE"
    ]
  }
}
```

Grant the configured MCP tools through the host's tool policy. In the isolated
OpenClaw lab, `tools.alsoAllow: ["bundle-mcp"]` enables MCP discovery; keep unrelated
MCP servers out of that profile. The API enforces roles independently of prompts.

The legacy local ClawCare spending guard accepts text-only requests and blocks
tool declarations/results. Connecting this adapter does **not** remove that
restriction. Do not bypass the guard: an explicitly scoped, tested tool-support
extension is required before a model-driven run through that launcher.

## First operational demo

Ask the agent to create a work order for a harmless, observable task. Inspect and
claim it before recording progress. Record only evidence the agent actually has;
a checkpoint reference is not proof of a saved checkpoint. Submit a handoff with
the exact stopping point and next work order. Have a separately authenticated
operator inspect the record and review it. Capture the returned actor IDs,
timestamps, revisions and resulting successor without recording credentials.

Do not call this a real two-person handoff until two real participants have used
their own credentials. Automated test clients are not contest installs or usage.

## Transport and limits

The adapter implements newline-delimited JSON-RPC over stdio, matching the
[MCP stdio transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports).
It reads only its configured credential file, connects only to IPv4 loopback,
does not follow redirects, bounds requests/responses and does not retry writes.
An ambiguous write failure requires inspection before retrying, especially create.
API errors are returned without raw response bodies or authorization headers.
The adapter cannot prevent an authorized participant from writing inaccurate
evidence. Review and verification remain necessary.

It does not start or supervise the API, refresh credentials, provide hosted
signup, report contest metrics or enable external repair actions. The API and
adapter must run on the same machine. Do not expose the loopback API publicly.

Validation: `python -m unittest discover -s tests -p test_team_mcp.py -v`.
Three tests cover actual HTTP handoff/attribution/revocation, denied authority and
identity overrides, and subprocess MCP discovery/call/notification/framing/bounds.
All three passed locally; no provider calls were made.
