# Use it with OpenAI: Codex, the ChatGPT desktop app, ChatGPT and the API

The plugin's MCP server is a standard, read-only MCP server. Every tool carries the MCP
annotation `readOnlyHint: true`. OpenAI's clients can use it in two ways.

| Client | How it connects | What you run |
|---|---|---|
| Codex CLI, the Codex IDE extension, the ChatGPT desktop app | **Local stdio** (recommended): nothing leaves your machine | `plugins/apexai-ops/bin/ops-mcp`, the same verified launcher Claude Code runs |
| ChatGPT on the web, the OpenAI API's remote MCP tool | **Remote Streamable HTTP**, over HTTPS | `plugins/apexai-ops/bin/ops_mcp_http.py`, behind a gateway or tunnel you control |

The requirements are those of the [README](../README.md): the licensed engine at the pinned
version, Python 3.11 or 3.12, and an engine control store. Get the plugin's files with
`git clone https://github.com/ApexAiOfficial/devops-plugin`. The paths below are relative to
that checkout.

## Codex and the ChatGPT desktop app (stdio)

The Codex CLI, its IDE extension and the ChatGPT desktop app share one configuration:
`~/.codex/config.toml`. Add the server:

```toml
[mcp_servers.apexai_ops]
command = "/path/to/devops-plugin/plugins/apexai-ops/bin/ops-mcp"
env_vars = ["OPS_CONTROL_STATE_PATH", "OPS_EVIDENCE_DIR", "APEXAI_OPS_PYTHON"]
```

`env_vars` passes those variables through from the environment Codex starts in. To fix them in
the file instead, use a table:

```toml
[mcp_servers.apexai_ops.env]
OPS_CONTROL_STATE_PATH = "/var/lib/apexai-ops/control.sqlite"
APEXAI_OPS_PYTHON = "/opt/apexai-ops/venv/bin/python"
```

Or add it from a shell:

```bash
codex mcp add apexai_ops --env OPS_CONTROL_STATE_PATH=/var/lib/apexai-ops/control.sqlite -- /path/to/devops-plugin/plugins/apexai-ops/bin/ops-mcp
```

In the ChatGPT desktop app, the same server appears under **Settings > MCP servers**, where a
**STDIO** server can also be added by hand.

**The skill.** Codex reads skills from `~/.codex/skills/<name>/SKILL.md`, the same format as
Claude Code's. Copy the plugin's skill there. Codex skips symbolic links, so copy rather than
link:

```bash
cp -R /path/to/devops-plugin/plugins/apexai-ops/skills/ops-inspection ~/.codex/skills/
```

**Check it.** Run `codex mcp list`, then ask, for example: "Use the apexai_ops tools: is anything
unresolved in the control plane?" The launcher refuses with the same closed reasons as under
Claude Code (README, "Troubleshooting").

## The HTTP bridge

`ops_mcp_http.py` serves the same server over MCP's Streamable HTTP transport, at
`http://127.0.0.1:8765/mcp`. It starts one verified `ops-mcp` process per MCP session.

Create its token once, then run it with the engine's variables in its environment:

```bash
python3 -I plugins/apexai-ops/bin/ops_mcp_http.py --init-token ~/.config/apexai-ops/mcp-http.token
```

```bash
OPS_CONTROL_STATE_PATH=/var/lib/apexai-ops/control.sqlite python3 -I plugins/apexai-ops/bin/ops_mcp_http.py --token-file ~/.config/apexai-ops/mcp-http.token
```

What it enforces, whatever is in front of it:
- **A bearer token on every request.** It is read from a file only you can read (mode 0600) and
  compared in constant time. Without it, the answer is 401.
- **Loopback only by default.** `--host` changes that, with a warning. A request whose `Origin`
  header is not allowed (`--allow-origin`) is refused, against DNS rebinding.
- **Reads only.** Only MCP's read methods pass. Only tools the server itself annotates
  `readOnlyHint: true` are listed or callable; anything else is refused before it reaches the
  server.
- **Bounds:** 1 MiB per request, 8 sessions, 15 idle minutes per session, and 120 seconds per
  request.

To use it from Codex over HTTP instead of stdio:

```toml
[mcp_servers.apexai_ops]
url = "http://127.0.0.1:8765/mcp"
bearer_token_env_var = "APEXAI_OPS_MCP_TOKEN"
```

Put the token in `APEXAI_OPS_MCP_TOKEN` in the environment Codex starts in.

## ChatGPT on the web

ChatGPT connects only to a **public HTTPS** MCP endpoint, and authenticates with **OAuth 2.1**. It
cannot send the bridge's bearer token itself. **Never expose the bridge, or a tunnel to it, without
authentication**: the control plane's state is operational data about your systems. Use one of
these:

- **A Secure MCP Tunnel**, where your ChatGPT workspace offers one. It connects ChatGPT to the
  bridge without exposing it to the internet. Run the tunnel client on the bridge's host, pointed
  at `http://127.0.0.1:8765/mcp`.
- **Your own HTTPS gateway that performs MCP's OAuth 2.1** for ChatGPT, for example an
  identity-aware proxy. It authenticates the ChatGPT user, then forwards to the bridge and adds
  `Authorization: Bearer <the bridge's token>`.

Then, in ChatGPT:
1. Open **Plugins** (`chatgpt.com/plugins`) and choose **+**, then **Add custom MCP server**.
   Your plan and workspace policy decide whether this is offered.
2. Enter a name, such as "ApexAI DevOps", and your endpoint's URL, ending in `/mcp`. Or choose
   your tunnel.
3. Configure the authentication your gateway provides, review the warning, and create it.
4. ChatGPT lists the `ops_*` tools, all read-only.

After the plugin is updated, choose **Refresh** on the connection and start a new conversation.
ChatGPT does not load the skill. Its guidance arrives through the server's own instructions and
tool descriptions, and the server also offers an `ops_triage` prompt.

## The OpenAI API

- **Remote MCP tool (Responses API):** OpenAI's servers call the endpoint, so it must be the same
  public HTTPS endpoint, behind your gateway. Pass the gateway's credentials in the tool's
  `headers`.
- **OpenAI Agents SDK:** run the stdio server locally with `MCPServerStdio`. Its command is
  `plugins/apexai-ops/bin/ops-mcp`, and its `env` carries the variables above.

## What is the same for every client

Every client runs the same server: the pinned, verified engine installation, isolated
(`python -I`), with the control store opened read-only. No client, and no bridge setting, can
request a remediation, grant authority or run a command through it.
