# ApexAI DevOps plugin for Claude Code

`apexai-ops` is a Claude Code plugin for **read-only inspection** of the ApexAI DevOps engine's
autonomous control plane, over MCP. Ask Claude what the engine did and why: control-plane status
and health, targets and ownership, incidents, decisions, external effects, budgets, recovery
holds, control events and sanitized evidence. The plugin also adds the `/apexai-ops:ops-triage`
command.

It never grants authority, requests a remediation or runs a command. Every tool it exposes is a
read.

## What this repository is, and is not

This repository holds the plugin only:
- its manifest and MCP configuration;
- a launcher;
- one command and one skill.

The DevOps engine, including its MCP server, is proprietary, licensed separately and **not** in
this repository. The plugin starts the engine's MCP server from your own licensed installation,
after verifying it.

To integrate an application with the engine (adapters, sinks, contract tests), use the
[ApexAI DevOps SDK](https://github.com/ApexAiOfficial/devops-sdk).

## Requirements

- **Linux or macOS**, with `bash`. On Windows, use WSL.
- **Python 3.11 or 3.12**, with the licensed engine distribution `apexai-ops` installed at exactly
  the version in [`plugins/apexai-ops/pin.json`](plugins/apexai-ops/pin.json).
- **An engine control store** to read (a SQLite file the engine writes).

## Install

In Claude Code:

```
/plugin marketplace add ApexAiOfficial/devops-plugin
/plugin install apexai-ops@apexai-universal-ops-plugin
```

Or from a shell:

```bash
claude plugin marketplace add ApexAiOfficial/devops-plugin
```

```bash
claude plugin install apexai-ops@apexai-universal-ops-plugin
```

## Configure

The server reads these variables from the environment Claude Code starts in.

| Variable | Meaning |
|---|---|
| `OPS_CONTROL_STATE_PATH` | The control store to read. Required for every read; without it, `ops_status` answers `store_not_configured` |
| `OPS_EVIDENCE_DIR` | The evidence directory, for evidence packets (optional) |
| `APEXAI_OPS_PYTHON` | The Python that has the engine installed (default: `python3` on `PATH`) |

Set them in the shell you start `claude` from, or in Claude Code's `settings.json`:

```json
{
  "env": {
    "OPS_CONTROL_STATE_PATH": "/var/lib/apexai-ops/control.sqlite",
    "APEXAI_OPS_PYTHON": "/opt/apexai-ops/venv/bin/python"
  }
}
```

The engine refuses to start if the environment holds an `OPS_*` variable it does not recognise. A
misspelled one stops the server, so remove any stray `OPS_*` setting.

## Check that it works

```bash
claude mcp list
```

The server shows as `plugin:apexai-ops:ops: ... ✔ Connected`. In a session, `/mcp` shows the same.

Then ask a question, such as "is anything unresolved in the control plane?", or run
`/apexai-ops:ops-triage`, optionally with an incident id.

## Troubleshooting

**The server fails to connect.** The launcher refused before the engine started, and wrote one
line to stderr.
- **Find the reason.** Claude Code's MCP log records it, after `Server stderr:`. On Linux the
  log is under `~/.cache/claude-cli-nodejs/<project>/mcp-logs-plugin-apexai-ops-ops/`.
- **Or run the launcher by hand,** with the same environment:

```bash
"$(ls -d ~/.claude/plugins/cache/apexai-universal-ops-plugin/apexai-ops/*/ | tail -1)bin/ops-mcp" < /dev/null
```

| The line says | What to do |
|---|---|
| `refused (pinned_distribution_missing)` | Install the engine at the pinned version into that Python, or point `APEXAI_OPS_PYTHON` at one that has it |
| `refused (version_mismatch)` | Install exactly the version the line names |
| `refused (record_*)` or `refused (module_not_in_record)` | The installed files do not match their own `RECORD`: reinstall the engine (`pip install --force-reinstall --no-deps apexai-ops==<version>`) |
| `APEXAI_OPS_PYTHON is not an executable Python` | Fix the path |
| `the engine needs Python 3.11 or later` | Point `APEXAI_OPS_PYTHON` at Python 3.11 or 3.12 |
| `unknown OPS_* setting(s)` | Remove or correct the named variable |

**The server connects, but the tools answer an error.** `ops_status` reports the store's state
first.

| Code | What to do |
|---|---|
| `store_not_configured` | Set `OPS_CONTROL_STATE_PATH` |
| `store_not_found` | The path does not exist: check it |
| `store_not_control_store` | The file is not an engine control store |
| `store_schema_stale` | The store awaits migration: the engine's operator migrates it |
| `evidence_not_configured` | Set `OPS_EVIDENCE_DIR` to read evidence packets |

## Updating

The plugin's version is the engine version it pins. While both stay on the development line, a
plugin-only fix keeps the same version, and `claude plugin update` answers that the plugin is
already at the latest version. Reinstall to pick up the fix:

```bash
claude plugin marketplace update apexai-universal-ops-plugin
```

```bash
claude plugin uninstall apexai-ops@apexai-universal-ops-plugin
```

```bash
claude plugin install apexai-ops@apexai-universal-ops-plugin
```

## How the launcher protects you

`plugins/apexai-ops/bin/ops-mcp` starts the server only from the pinned distribution, and only
at its exact version:
- it checks every file against the digests in the installation's own `RECORD` first
  (`bin/verify_pin.py`, standard library only);
- it runs the server isolated (`python -I`);
- anything else refuses, with exit status 2 and one closed reason on stderr;
- nothing but MCP protocol goes to stdout.

## Status

The plugin tracks the engine's development line `1.0.0.dev12`. It is **not a release**: it
works with an engine installation at that exact version. Releases will be tagged here.

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0 ([LICENSE](LICENSE)) for this plugin. The ApexAI DevOps engine is licensed
separately.
