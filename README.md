# ApexAI DevOps plugin for Claude Code

`apexai-ops` is a Claude Code plugin for **read-only inspection** of the ApexAI DevOps engine's
autonomous control plane, over MCP. Ask Claude what the engine did and why: control-plane status,
targets and ownership, incidents, decisions, external effects, budgets, recovery holds, control
events and sanitized evidence. The plugin also adds the `/ops-triage` command.

It never grants authority, requests a remediation or runs a command. Every tool it exposes is a
read.

## What this repository is, and is not

This repository holds the plugin only: its manifest, its MCP configuration, a launcher, one
command and one skill. The DevOps engine, including its MCP server, is proprietary, licensed
separately and **not** in this repository. The plugin starts the engine's MCP server from your
own licensed installation, after verifying it.

To integrate an application with the engine (adapters, sinks, contract tests), use the
[ApexAI DevOps SDK](https://github.com/ApexAiOfficial/devops-sdk).

## Requirements

- The licensed engine distribution `apexai-ops`, installed in a Python on `PATH` (or name the
  interpreter in `APEXAI_OPS_PYTHON`), at exactly the version in
  [`plugins/apexai-ops/pin.json`](plugins/apexai-ops/pin.json).
- `OPS_CONTROL_STATE_PATH`: the engine's control store to read. Optionally `OPS_EVIDENCE_DIR`.

## Install

In Claude Code:

```
/plugin marketplace add ApexAiOfficial/devops-plugin
/plugin install apexai-ops@apexai-universal-ops-plugin
```

Or from a shell:

```bash
claude plugin marketplace add ApexAiOfficial/devops-plugin
claude plugin install apexai-ops@apexai-universal-ops-plugin
```

## How the launcher protects you

`plugins/apexai-ops/bin/ops-mcp` starts the server only from the pinned distribution, at its exact
version, after checking every file against the digests in its installed `RECORD`
(`bin/verify_pin.py`, standard library only), and runs it isolated (`python -I`). Anything else
refuses with exit status 2 and a closed reason on stderr; nothing but MCP protocol goes to stdout.

## Status

The plugin tracks the engine's development line `1.0.0.dev12`. It is **not a release**: it works
with an engine installation at that exact version. Releases will be tagged here.

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## License

Apache License 2.0 ([LICENSE](LICENSE)) for this plugin. The ApexAI DevOps engine is licensed
separately.
