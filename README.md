# ApexAi DevOps agent plugin

[![validate](https://github.com/ApexAiOfficial/devops-plugin/actions/workflows/validate.yml/badge.svg)](https://github.com/ApexAiOfficial/devops-plugin/actions/workflows/validate.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

A Claude Code plugin that lets an AI agent inspect a DevOps engine installation over the Model
Context Protocol (MCP), read-only: what the engine saw, what it decided, what it changed, and why.

> [!IMPORTANT]
> **Development pre-release, for environments ApexAi operates.** The plugin does nothing on its
> own: it starts the inspection server of a DevOps engine installation on the same machine. The
> engine is proprietary and in development, runs only in environments ApexAi operates, and is not
> distributed, licensed or sold to customers. DevOps for customers is planned as an ApexAi-managed
> service.

| | Status today |
|---|---|
| **Source** | Public on GitHub, under the Apache License 2.0 |
| **Version** | `1.0.0-rc.1.2`, the plugin for the engine's release candidate `1.0.0rc1` ([versioning](#versioning-and-compatibility)) |
| **Releases** | The engine's release candidate `1.0.0rc1` (2026-11-11), released privately by ApexAi for read-only monitoring. This repository has no Git tag or GitHub release yet |
| **Distribution** | This repository's own Claude Code plugin marketplace only. Not published to PyPI, npm, Anthropic's official plugin directory or the MCP Registry |
| **Needs** | An installation of ApexAi's build of the proprietary DevOps engine at exactly version `1.0.0rc1`, with the build digest in [`pin.json`](plugins/apexai-ops/pin.json), on the same machine, in an environment ApexAi operates. The engine is not in this repository and is not distributed |
| **Hosted service** | None. ApexAi hosts no endpoint for this plugin, and it uses no ApexAi account, key or URL |
| **Product** | DevOps is not publicly offered yet. Its status is on the [DevOps page](https://apexaiofficial.com/devops); ApexAi's developer kits are listed in [ApexSDK](https://apexaiofficial.com/apexsdk) |

To integrate an application with the engine (adapters, sinks, contract tests), use the
[ApexAi DevOps SDK](https://github.com/ApexAiOfficial/devops-sdk) instead.

## Contents

- [What it does](#what-it-does)
- [Requirements](#requirements)
- [Quickstart](#quickstart)
- [Install](#install)
- [Configure](#configure)
- [Check that it works](#check-that-it-works)
- [Use it](#use-it)
- [Tools](#tools)
- [Other clients and the HTTP bridge](#other-clients-and-the-http-bridge)
- [Troubleshooting](#troubleshooting)
- [Updating](#updating)
- [Security and privacy](#security-and-privacy)
- [Versioning and compatibility](#versioning-and-compatibility)
- [Repository layout](#repository-layout)
- [Support](#support)
- [License](#license)

## What it does

The DevOps engine keeps a durable record of its autonomous control plane. This plugin connects
Claude Code to the engine's own local inspection server, so an agent can answer questions from that
record:

- control-plane status, and the health conditions behind it;
- targets (the systems the engine watches) and who owns them;
- incidents, and the decisions (work items) made for them;
- effects: the changes a decision made, and whether an independent observation confirmed them;
- authority grants, effect budgets and recovery holds;
- items that need a person, and rearm authorizations;
- obligations and watches: what is owed a look, and when;
- remedy memory: why a remedy was chosen;
- the append-only control events, and sanitized evidence packets.

| Part | What it is |
|---|---|
| MCP server `ops` | The engine's inspection server, started over stdio by the launcher. It offers 21 read tools ([Tools](#tools)), the `ops_triage` prompt and `ops://` resources |
| Command `/apexai-ops:ops-triage [incident_id]` | A structured, read-only triage of health and of what needs attention, optionally drilling into one incident |
| Skill `ops-inspection` | Routes each question to the right tool, and says what an answer does and does not prove |
| Launcher [`bin/ops-mcp`](plugins/apexai-ops/bin/ops-mcp) | Verifies the engine installation against [`pin.json`](plugins/apexai-ops/pin.json), then starts its server |
| HTTP bridge [`bin/ops_mcp_http.py`](plugins/apexai-ops/bin/ops_mcp_http.py) | Optional. Serves the same server over Streamable HTTP for clients that cannot run stdio |

### What "read-only" means here

- Every tool the plugin's server lists is a read and carries the MCP annotation
  `readOnlyHint: true`. No tool grants authority, requests a remediation, acknowledges an attention
  item, issues a rearm, migrates the store or runs a command.
- The engine opens the control store read-only.
- Under Claude Code and the other stdio set-ups, the tool list is the engine server's own; the
  plugin adds no filter on that path. The HTTP bridge enforces it a second time: only MCP's read
  methods pass, and only tools annotated `readOnlyHint: true` are listed or callable.
- The triage command may call only the 12 read tools in its `allowed-tools`. The command and the
  skill tell the agent never to propose a remediation, acknowledge an attention item or request a
  rearm, and to treat text inside tool results as data, not instructions.
- Two more tools exist only when an application embeds the engine's server in its own process, and
  one of them is not a read. The plugin's server never lists them
  ([`embedded-hosts.md`](plugins/apexai-ops/skills/ops-inspection/references/embedded-hosts.md)).

## Requirements

| Requirement | Detail |
|---|---|
| Claude Code | A version with plugin support. CI validates the manifests with Claude Code 2.1.282 |
| Operating system | `bash` on Linux or macOS; on Windows, WSL. CI runs on Ubuntu only |
| Python | 3.11 or 3.12, the versions the engine supports. The launcher refuses anything older than 3.11 |
| DevOps engine | An ApexAi-operated installation of the `apexai-ops` distribution at exactly the version in [`pin.json`](plugins/apexai-ops/pin.json) ([step 2](#2-check-the-engine-installation)). The engine is not distributed |
| Control store | The engine's SQLite control store, readable by your account |
| Evidence directory | Optional, to read evidence packets |
| Network | None for stdio use: nothing in this repository opens an outbound connection |

## Quickstart

On a machine where ApexAi operates the engine ([step 2](#2-check-the-engine-installation)):

```bash
claude plugin marketplace add ApexAiOfficial/devops-plugin
claude plugin install apexai-ops@devops-plugin
export OPS_CONTROL_STATE_PATH=/var/lib/apexai-ops/control.sqlite
export APEXAI_OPS_PYTHON=/opt/apexai-ops/venv/bin/python
claude mcp list    # the plugin:apexai-ops:ops line ends in "Connected"
```

Then start `claude` from the same shell and run `/apexai-ops:ops-triage`. Each step is explained
below.

## Install

### 1. Add the plugin to Claude Code

In Claude Code:

```text
/plugin marketplace add ApexAiOfficial/devops-plugin
/plugin install apexai-ops@devops-plugin
```

Or from a shell:

```bash
claude plugin marketplace add ApexAiOfficial/devops-plugin
claude plugin install apexai-ops@devops-plugin
```

To review the code first, clone the repository and add the marketplace from your checkout instead:

```bash
git clone https://github.com/ApexAiOfficial/devops-plugin.git
claude plugin marketplace add ./devops-plugin
claude plugin install apexai-ops@devops-plugin
```

### 2. Check the engine installation

The engine is proprietary and runs only in environments ApexAi operates: ApexAi installs and
maintains it there, and does not distribute, license or sell it. No public package index carries
it, so a package with its name on a public index is not ApexAi's.

On such a machine, check the installation with the same verification the launcher runs before every
start (`/opt/apexai-ops/venv/bin/python` stands for the Python that has the engine):

```bash
plugin_dir="$(claude plugin list --json | python3 -c 'import json, sys; print(next(p["installPath"] for p in json.load(sys.stdin) if p["id"] == "apexai-ops@devops-plugin"))')"
/opt/apexai-ops/venv/bin/python -I "$plugin_dir/bin/verify_pin.py" "$plugin_dir/pin.json" && echo verified
```

It prints `verified` (the `echo`) when the pinned distribution is installed at its exact version,
every file matches its `RECORD`, the engine's package files are exactly ApexAi's pinned build, and the
`apexai_ops` package Python resolves is made only of those files; otherwise the verifier writes one
line to stderr, `apexai-ops mcp: refused (<reason>); <hint>`, and exits 2
([Troubleshooting](#troubleshooting)). A package that merely has the engine's name and version, from
any package index, fails the build check ([Security and privacy](#security-and-privacy)).

## Configure

The server reads its settings from the environment Claude Code starts in.

| Variable | Required | Meaning |
|---|---|---|
| `OPS_CONTROL_STATE_PATH` | For every read | The control store to read. Unset or empty, every read answers `store_not_configured` |
| `OPS_EVIDENCE_DIR` | No | The evidence directory, for evidence packets |
| `APEXAI_OPS_PYTHON` | No | The Python that has the engine installed. Default: `python3`, then `python`, on `PATH` |
| `OPS_PROFILE` | No | `production` (the default) runs only the pinned, verified installation. `development` skips verification and is for ApexAi's engine developers only ([Security](#security-and-privacy)) |

Set them in the shell you start `claude` from, or in `~/.claude/settings.json`:

```json
{
  "env": {
    "OPS_CONTROL_STATE_PATH": "/var/lib/apexai-ops/control.sqlite",
    "APEXAI_OPS_PYTHON": "/opt/apexai-ops/venv/bin/python"
  }
}
```

The server sees the whole environment, and the engine refuses to start when that environment holds
an `OPS_*` variable it does not recognise. A misspelled or stray `OPS_*` variable therefore stops
the server: remove it.

## Check that it works

```bash
claude mcp list
```

The `plugin:apexai-ops:ops` line ends in `Connected`. In a session, `/mcp` shows the same server.
If it says `Failed to connect`, see [Troubleshooting](#troubleshooting).

Then ask a question, such as "is anything unresolved in the control plane?", or run the triage
command.

## Use it

### Ask questions

The `ops-inspection` skill routes questions to tools. Ask in plain language; for example:

| Question | Tools the skill uses, in order |
|---|---|
| Is it healthy and running? | `ops_status`, then `ops_health` |
| What happened to a target? | `ops_list_targets`, `ops_get_target`, then `ops_get_work` |
| Why did a decision escalate or fail? | `ops_escalated_work` or `ops_get_incident`, then `ops_get_work`, then `ops_get_evidence` for a packet it cites |
| Did the change really happen? | `ops_get_effect` |
| What needs a person? | `ops_attention`; for a `rearmable_blocker`, `ops_rearms` |
| Is anything stuck or overdue? | `ops_unresolved_work`, `ops_obligations`, `ops_watches` |
| Is a budget exhausted? | `ops_status`, then `ops_budget` |
| Who owns a target? | `ops_ownership` |
| Why was this remedy chosen? | `ops_remedy_memory` |

The full routing table is in [`SKILL.md`](plugins/apexai-ops/skills/ops-inspection/SKILL.md).

### Run a triage

```text
/apexai-ops:ops-triage
/apexai-ops:ops-triage <incident_id>
```

The command reads, in order: store status, health conditions, unresolved and escalated work (with
each escalated decision's latest transition), items that need a person and any rearm authorization
for them, and exhausted budgets with the store's integrity verdict. With an incident id, it then
follows that incident's latest decision, its effect and any evidence packet it cites. It reads at
most 20 items per list, takes every number from a read, and reports any error code it receives
([`ops-triage.md`](plugins/apexai-ops/commands/ops-triage.md)).

### Read the answers precisely

- **Pages.** A list read returns one page. To continue, pass its `next_after` as `after`. A page
  can be short and still `truncated`.
- **Counts.** A `total` is exact only where the tool says it comes from a maintained counter. A
  `total_at_least` is a lower bound, never the total.
- **Decisions.** A work item's `state` is a projection. If `ops_get_work` reports
  `projection_matches_events` as false, the events are authoritative.
- **Effects.** `dispatched` means the change entered dispatch; a `latest_effect_state` of
  `observed` means an independent observation saw it.
- **Ownership.** An expired lease is not proof that its owner stopped.
- **Health.** A condition that is `unknown` or `unevaluated` is never healthy.

What each tool returns, its filters and the `ops://` resources are in the
[field guide](plugins/apexai-ops/skills/ops-inspection/references/field-guide.md).

## Tools

The plugin's server lists these 21 tools, all reads. In Claude Code their full names are
`mcp__plugin_apexai-ops_ops__<tool>`.

| Area | Tools |
|---|---|
| Overview | `ops_status`, `ops_health` |
| Targets and ownership | `ops_list_targets`, `ops_get_target`, `ops_ownership` |
| Incidents and decisions | `ops_list_incidents`, `ops_get_incident`, `ops_list_work`, `ops_get_work`, `ops_unresolved_work`, `ops_escalated_work` |
| Effects | `ops_get_effect` |
| What needs a person | `ops_attention`, `ops_rearms` |
| Scheduled looks | `ops_obligations`, `ops_watches` |
| Budgets | `ops_budget` |
| Remedy memory | `ops_remedy_memory` |
| History | `ops_events` |
| Evidence | `ops_list_evidence`, `ops_get_evidence` |

Each tool's description on the server is authoritative.

## Other clients and the HTTP bridge

The same server works with any MCP client that can start a local stdio process, through the same
launcher and the same verification. [`docs/openai.md`](docs/openai.md) describes set-ups for
OpenAI's clients: Codex and the ChatGPT desktop app over stdio, and ChatGPT on the web and the
OpenAI API over the HTTP bridge. Those set-ups follow OpenAI's documentation; this repository's CI
does not test them.

For a client that cannot run stdio, the bridge serves the server over MCP's Streamable HTTP
transport at `http://127.0.0.1:8765/mcp`, one verified launcher process per MCP session. From a
clone of this repository:

```bash
# Once: create a random bearer token in a new file, mode 0600 (it never overwrites one)
python3 -I plugins/apexai-ops/bin/ops_mcp_http.py --init-token ~/.config/apexai-ops/mcp-http.token

# Run it, with the engine's settings in its environment
OPS_CONTROL_STATE_PATH=/var/lib/apexai-ops/control.sqlite APEXAI_OPS_PYTHON=/opt/apexai-ops/venv/bin/python \
  python3 -I plugins/apexai-ops/bin/ops_mcp_http.py --token-file ~/.config/apexai-ops/mcp-http.token
```

| The bridge enforces | Detail |
|---|---|
| A bearer token on every request | Read from a file that must be yours and closed to group and others (mode `0600`), at least 32 characters, compared in constant time. Without it: `401` |
| Loopback by default | Listens on `127.0.0.1`; `--host` changes that, with a warning for a non-loopback address. A request whose `Origin` is not allowed (`--allow-origin`, repeatable) gets `403` |
| Reads only | Other MCP methods are refused; tools not annotated `readOnlyHint: true` are neither listed nor callable |
| Bounds | 1 MiB per request, 8 sessions, 15 idle minutes per session, 120 seconds per request |

Never expose the bridge, or a tunnel to it, without authentication in front of it.
[`docs/openai.md`](docs/openai.md#chatgpt-on-the-web) describes the options for ChatGPT on the web.

## Troubleshooting

### The server fails to connect

The launcher or the engine refused to start and wrote one line to stderr, beginning
`apexai-ops mcp:`. To find it:

- **In Claude Code's MCP log**, after `Server stderr:`. On Linux, the log is under
  `~/.cache/claude-cli-nodejs/<project>/mcp-logs-plugin-apexai-ops-ops/`.
- **Or run the launcher by hand**, with the same environment:

```bash
plugin_dir="$(claude plugin list --json | python3 -c 'import json, sys; print(next(p["installPath"] for p in json.load(sys.stdin) if p["id"] == "apexai-ops@devops-plugin"))')"
"$plugin_dir/bin/ops-mcp" < /dev/null
```

| The line says | Meaning | What to do |
|---|---|---|
| `no python interpreter found` | Neither `python3` nor `python` is on `PATH` | Set `APEXAI_OPS_PYTHON` |
| `APEXAI_OPS_PYTHON is not an executable Python` | The path is wrong | Fix the path |
| `the engine needs Python 3.11 or later` | That Python is too old | Point `APEXAI_OPS_PYTHON` at Python 3.11 or 3.12 |
| `OPS_PROFILE must be production or development` | Unknown profile | Unset `OPS_PROFILE`, or set it to `production` |
| `refused (pin_unreadable)` | The plugin's `pin.json` is missing or malformed | Reinstall the plugin |
| `refused (pinned_distribution_missing)` | The engine is not installed in that Python | Point `APEXAI_OPS_PYTHON` at the Python that has the engine installation ([step 2](#2-check-the-engine-installation)) |
| `refused (version_mismatch)` | Another engine version is installed | The installation and the plugin's pin differ: ApexAi brings the installation to the version the line names |
| `refused (record_missing)`, `refused (record_malformed)`, `refused (record_unhashed_file)`, `refused (record_hash_unsupported)`, `refused (record_file_missing)`, `refused (record_digest_mismatch)` | The installed files do not match the installation's own `RECORD` | The installation was damaged or altered: ApexAi reinstalls it from its own artifact (see below) |
| `refused (package_digest_mismatch)` | The installed package is not the build the plugin pins: its files differ from the build digest in `pin.json`, as they would for a package that only shares the engine's name and version, or for another build of the engine | Do not run it. ApexAi reinstalls the engine from its own artifact, or installs the plugin version made for that build |
| `refused (module_not_in_record)` | Python would import another copy of the engine module, not the verified installation | Remove the other copy, so that Python imports the verified installation |
| `refused (package_unrecorded_file)` | The engine's package directory holds files its `RECORD` does not list, or a symbolic link to a directory | Remove them, or have ApexAi reinstall the engine |
| `refused (package_unreadable)` | Part of the engine's package directory cannot be read, so the verifier cannot check it | Fix the permissions |
| `unknown OPS_* setting(s): <names>` | The engine does not recognise those variables | Remove or correct them |
| `invalid OPS_* configuration: ...`, or another `invalid ... configuration` line | The engine refused a setting's value | Correct the setting it names |

The verifier's hints never name a package index or an install command: the engine is installed
only by ApexAi, from its own artifact, never by name from a package index.

### The server connects, but a tool answers an error

A failed call returns `{"error": {"code", "message", "detail"}}` with `isError` true. Start with
`ops_status`, which reports the store's state first.

| Code | Meaning | What to do |
|---|---|---|
| `store_not_configured` | No control store is configured | Set `OPS_CONTROL_STATE_PATH` |
| `store_not_found` | The path does not exist (`detail.path`) | Check the path |
| `store_not_control_store` | The file is not an engine control store | Point at the engine's control store |
| `store_schema_stale` | The store awaits migration | ApexAi migrates it with the engine; the plugin never does |
| `store_schema_unsupported` | The store's schema is newer than, or unknown to, this engine version | Check which engine version wrote the store: this plugin version runs only the pinned one |
| `store_unavailable`, `store_unreadable` | The store could not be opened or read now | Check the file and its permissions |
| `evidence_not_configured` | No evidence directory is configured | Set `OPS_EVIDENCE_DIR` |
| `evidence_not_found`, `evidence_invalid_id`, `evidence_unavailable` | The packet is missing, its id is malformed, or the evidence directory cannot be read | Take ids from `ops_list_evidence`; check the directory |
| `not_found` | The identifier is unknown to the store (`detail.kind`) | Take identifiers from a listing tool |
| `invalid_argument` | An argument does not match the tool's schema (`detail.tool`) | Correct the argument |

More detail, including how an older store is read in place, is in
[`errors-and-schema.md`](plugins/apexai-ops/skills/ops-inspection/references/errors-and-schema.md).

## Updating

```bash
claude plugin marketplace update devops-plugin
claude plugin update apexai-ops@devops-plugin
```

Restart Claude Code to apply an update. Each plugin change raises the plugin's version, so updates
reach existing installs. When an update changes [`pin.json`](plugins/apexai-ops/pin.json),
the launcher refuses with `version_mismatch` or `package_digest_mismatch` until the installation runs
the matching engine build, which ApexAi installs in the environments it operates.

**Marketplace added before `1.0.0-dev.12.4`.** The marketplace then had an earlier name. Find it
with `claude plugin marketplace list`: the entry whose source is this repository and whose name is
not `devops-plugin`. Remove it with `claude plugin marketplace remove <that name>`, then add and
install as in [step 1](#1-add-the-plugin-to-claude-code).

## Security and privacy

### What runs, and what it contacts

| Part | Runs | Reads | Network |
|---|---|---|---|
| Launcher and verifier (`bin/ops-mcp`, `bin/verify_pin.py`) | Locally, standard library only | `pin.json`, and the engine installation's metadata and files | None |
| Engine inspection server | Locally, as a child process over stdio, isolated (`python -I`) | The control store, opened read-only, and the evidence directory when set. If the environment carries more of the engine's own `OPS_*` configuration, it reads within that configuration too | The plugin gives it no URL, endpoint or credential |
| HTTP bridge (optional) | Locally, standard library only | Its token file | Listens on `127.0.0.1:8765` by default; opens no outbound connection |

What the tools return becomes part of your agent's conversation, and your client sends that
conversation to the model it uses. Control-plane state is operational data about your systems:
decide which clients may see it.

### Where the engine comes from, and what the launcher verifies

In the default `production` profile, the launcher starts the server only when:

- the pinned distribution is installed, at exactly the pinned version;
- every file listed in the installation's own `RECORD` matches its SHA-256 digest and size;
- the engine's package files are exactly ApexAi's build: their paths and digests hash to the
  `package_sha256` in [`pin.json`](plugins/apexai-ops/pin.json);
- the engine package Python resolves is made only of those verified files.

It then runs the server isolated (`python -I`: no `PYTHONPATH`, no user site). Anything else
refuses, with exit status 2 and one line on stderr; nothing but MCP protocol goes to stdout.

A `RECORD` only proves that files match the list shipped beside them, which any package with the
engine's name and version could satisfy. The build digest ties the engine package's files to ApexAi's
build, so the launcher refuses to start a look-alike package from a public index. It is a check at
start-up, not a defence against what is already installed: a package installed into that Python can
run its own code during installation and, through `.pth` files, whenever that Python starts, before
any check. That is why the engine is never installed by name from a package index. The digest is not
a signature either: it proves which files are installed, not who installed them, and anyone who can
change the plugin's own files could change the pin too. The engine comes only from ApexAi's own artifacts, installed by
ApexAi in the environments it operates; no public index carries it
([step 2](#2-check-the-engine-installation)).

### The development profile

`OPS_PROFILE=development` skips every check above. It runs whatever engine the chosen Python can
import, or an engine source checkout around the plugin, unverified. It exists for ApexAi's engine
developers only: do not set it anywhere else.

### The HTTP bridge

Keep the token file private: the bridge refuses one that is not yours, or that group or others can
access. Leave the bridge on loopback unless TLS and access control are in front of it, and never
expose it, or a tunnel to it, without authentication.

### Reporting a vulnerability

Email **support@apexaiofficial.com** with what you found, how to reproduce it, and the plugin
version. Do not open a public issue for a vulnerability. [`SECURITY.md`](SECURITY.md) states what
the plugin promises.

## Versioning and compatibility

- **Plugin version.** The plugin's version is the pinned engine version in SemVer form plus a
  plugin revision: engine `1.0.0.dev12` gave plugin `1.0.0-dev.12.<revision>`, a release candidate
  `1.0.0rc1` gives `1.0.0-rc.1.<revision>`, and the current version is `1.0.0-rc.1.2`. Each plugin
  change raises the revision. CI checks that the
  marketplace and plugin manifests carry one version and that it extends the pinned engine version.
- **Pre-1.0.** These are development versions. No release has been tagged, and the tool surface,
  settings and error codes can still change.
- **Engine.** Each plugin version runs exactly one engine build: the version and the build digest in
  [`pin.json`](plugins/apexai-ops/pin.json). To pin a new engine version, ApexAi sets the version in
  `pin.json` and runs `verify_pin.py pin.json --print-package-sha256` with the Python of an
  installation made from its own artifact. That mode prints the digest of whatever is installed and
  cannot tell where it came from. The engine reports a store it cannot read as `store_schema_stale`
  or `store_schema_unsupported`.
- **Claude Code.** CI validates the marketplace and the plugin in strict mode with Claude Code
  2.1.282. Other versions are not tested.
- **What CI covers.** Manifest validation; that the launcher refuses without the pinned engine; that
  the verifier refuses a package with the engine's name and version but another build, accepts an
  installation whose files match its pin, and refuses files added inside the package; that the
  bridge answers `401` without its token and `403` for a disallowed `Origin`; and version
  consistency. CI does not run against a real engine, so it cannot check the pinned digest itself,
  and it does not test the OpenAI set-ups.

## Repository layout

| Path | What it is |
|---|---|
| [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) | The marketplace `devops-plugin`, with one plugin, `apexai-ops` |
| [`plugins/apexai-ops/.claude-plugin/plugin.json`](plugins/apexai-ops/.claude-plugin/plugin.json) | The plugin manifest |
| [`plugins/apexai-ops/README.md`](plugins/apexai-ops/README.md) | The plugin's own summary of its parts and settings |
| [`plugins/apexai-ops/.mcp.json`](plugins/apexai-ops/.mcp.json) | One stdio MCP server, `ops`, started by `bin/ops-mcp` |
| [`plugins/apexai-ops/pin.json`](plugins/apexai-ops/pin.json) | The engine distribution, the exact version, and the build digest the plugin runs |
| [`plugins/apexai-ops/bin/`](plugins/apexai-ops/bin) | The launcher, the pin verifier and the HTTP bridge |
| [`plugins/apexai-ops/commands/ops-triage.md`](plugins/apexai-ops/commands/ops-triage.md) | The triage command |
| [`plugins/apexai-ops/skills/ops-inspection/`](plugins/apexai-ops/skills/ops-inspection) | The skill and its references: field guide, errors and configuration, embedded hosts |
| [`docs/openai.md`](docs/openai.md) | Using the server from OpenAI's clients, and the HTTP bridge |
| [`.github/workflows/validate.yml`](.github/workflows/validate.yml), [`ci/pinned-cli/`](ci/pinned-cli) | CI, with a pinned, lockfile-installed Claude Code CLI |
| [`SECURITY.md`](SECURITY.md), [`LICENSE`](LICENSE), [`NOTICE`](NOTICE) | Security promises, license and notice |

## Support

- **Bugs and questions about the plugin:** open an issue in
  [this repository](https://github.com/ApexAiOfficial/devops-plugin/issues). Never paste tokens,
  store contents or evidence packets into an issue.
- **Email:** support@apexaiofficial.com.
- **Vulnerabilities:** by email, as described in [Reporting a vulnerability](#reporting-a-vulnerability).
- **DevOps itself:** sales@apexaiofficial.com. DevOps for customers is planned as an ApexAi-managed
  service.

## License

This plugin is licensed under the Apache License 2.0: see [`LICENSE`](LICENSE) and
[`NOTICE`](NOTICE). The DevOps engine it starts is proprietary: it is not part of this
repository, and it is not distributed, licensed or sold to customers.
