# apexai-ops

Read-only inspection of the ApexAI DevOps engine's control plane over MCP.

| Part | What it is |
|---|---|
| `.claude-plugin/plugin.json` | The plugin manifest |
| `.mcp.json` | One stdio MCP server, `ops`, started by `bin/ops-mcp` |
| `bin/ops-mcp` | The launcher: verifies the pinned engine installation, then starts its MCP server |
| `bin/verify_pin.py` | The verification: distribution, exact version, every `RECORD` digest, and the package resolved from those files |
| `pin.json` | The engine distribution and version this plugin runs |
| `commands/ops-triage.md` | `/apexai-ops:ops-triage`: a structured triage of health and what needs attention |
| `skills/ops-inspection/SKILL.md` | Which `ops_*` tool answers which question, and what an answer does and does not prove; per-tool detail in `references/` |

## Settings

| Variable | Meaning |
|---|---|
| `OPS_CONTROL_STATE_PATH` | The control store the server reads (required for every read; unset, `ops_status` answers `store_not_configured`) |
| `OPS_EVIDENCE_DIR` | The evidence directory, for evidence packets (optional) |
| `APEXAI_OPS_PYTHON` | The Python 3.11 or 3.12 that has the engine installed (default: `python3`) |
| `OPS_PROFILE` | `production` (default): only the pinned, verified installation runs. `development`: an engine installed on the interpreter's path, unverified, for engine developers only |

## What the server exposes

Only reads: status, health, targets and ownership, incidents, work decisions, effects, authority grants,
effect budgets, recovery holds, control events, attention and rearm records, and sanitized
evidence. Lists are bounded pages (`limit`, `after`). The skill describes each tool. There is no
tool that requests a remediation, grants authority or executes a command.

Setup, checks and troubleshooting are in the repository's [README](../../README.md).
