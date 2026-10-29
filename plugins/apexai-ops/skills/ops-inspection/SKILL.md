---
name: ops-inspection
description: Inspect the ApexAi Ops autonomous control plane through the read-only `ops_*` MCP tools - control-plane status, targets and ownership, incidents, work decisions, logical external effects, authority grants, effect budgets, recovery holds, control events and sanitized evidence packets. Use when asked what the Ops controller did, why a remediation failed or escalated, whether work is unresolved, whether a budget is exhausted, or to read an evidence packet.
version: 0.1.0
---

# Ops control-plane inspection

The `ops` MCP server exposes the durable state of the ApexAi Ops autonomous
control plane. On the plugin's own stdio server everything is a read: the
store is opened read-only, and nothing can tick, remediate, grant authority
or run a command from here. A host that embeds the server may add one
request that is not a read (the last section).
Remediation decisions belong to the controller; this surface explains them.

## Where identifiers come from

Never invent identifiers. Obtain them from a listing tool and pass them
unchanged:

| Need | Tool | Yields |
|---|---|---|
| overall picture | `ops_status` | counts (from maintained counters), schema, the durable integrity verdict, evidence availability (`packets_at_least`) |
| health | `ops_health` (optional `scope`: `full`, `liveness`, `readiness`, `store`; optional `supervisor_id`) | every fail-closed condition with its status (`clear`, `holds`, `unknown`, `unevaluated`), severity, `since` and runbook key; the aggregate and its exit code; `complete` is false while any condition is unevaluated, and an unknown or unevaluated condition is never ok |
| targets | `ops_list_targets`, `ops_get_target` (page with `after`) | `target_id`, ownership, latest work, live work, `escalated_at_least`; one target's work newest first |
| ownership | `ops_ownership` (page with `after`) | owner, incarnation, epoch, lease, fence floor per target |
| incidents | `ops_list_incidents`, `ops_get_incident` (page with `after`) | `incident_id`, latest `work_id` and state, whether open; one incident's decisions oldest first |
| work | `ops_list_work` (filter by `state`, `target_id`, `incident_id`; page with `after`) | `work_id`, newest first in creation order |
| unresolved / escalated | `ops_unresolved_work`, `ops_escalated_work` (page with `after`) | work still owed a resolution; decisions settled `ESCALATED`; `total` is exact (a maintained counter; at schema 14 unresolved's is counted on 14's own index, and escalated's page has `total_at_least` instead, a lower bound) |
| attention | `ops_attention` (page with `after`) | every revision blocker (latest blocking decision of an incident and desired revision) and unacknowledged recovery dead end, with notification state; one page of `limit` (default 50), `truncated`, `total_at_least` |
| rearm authorizations | `ops_rearms` (filter by `blocking_work_id`, `incident_id`, `live_only`; page with `after`) | who authorized another decision for a blocked one, live or consumed, newest first; `total_at_least` is the rows fetched, `live` is exact; read-only |
| obligations | `ops_obligations` (optional `limit`) | what is owed a look, `owed_since` (when it first became owed) and `due_at` (next eligible), `due_total` and `truncated`, and the stuck read with which stuck classes are and are not evaluated; read-only |
| watches | `ops_watches` (optional `include_retired`, `limit`; page with `after`) | each declared (target, predicate) generation, its interval, latest look and next due look; read-only |
| remedy memory | `ops_remedy_memory` (optional `limit`; continue one `list` with its `after`) | latest decisive remedy evidence, retained candidates per exact scope, clearances, and retained-selection refusal bypasses, each a page with `totals_at_least` and `next_after`; read-only |
| one decision | `ops_get_work` (events page with `after`) | effects (`effect_id`), grants, `latest_transition` (its newest accepted transition, whatever page is shown), a page of events, the `evidence_packet_ids` that page cites |
| one effect | `ops_get_effect` (events page with `after`) | intent, dispatched flag, envelope, recovery hold and contract, a page of events |
| history | `ops_events` (filter by `work_id`, `effect_id`, `target_id`, `kind`; page with `after`, or `after_seq`) | authoritative append-only events; `total_at_least` is the rows fetched, never a count of the history; a `kind`-only page can be short while `truncated`, so continue from `next_after` |
| budgets | `ops_budget` (page with `after`) | envelopes, their recovery holds, the durable integrity verdict |
| evidence | `ops_list_evidence` (page with `after`) then `ops_get_evidence` | sanitized packets, by packet id |

Some reads also exist as resources (`ops://status`, `ops://work/{work_id}`,
`ops://effect/{effect_id}`, `ops://incident/{incident_id}`,
`ops://target/{target_id}`, `ops://evidence/{evidence_packet_id}`,
`ops://unresolved`, `ops://escalated`, `ops://budget`, `ops://evidence`).

## Reading the answers

- A work item's `state` is the projection; `ops_get_work` also reports
  `projection_matches_events`. If it is false, trust the events and say so.
- `terminal`, `success`, `escalated` and `stabilizing` are computed with the
  production lifecycle predicates. `succeeded` is only reached after a
  stabilization window; a passing verification alone is `stabilizing`.
- An effect's `dispatched` flag means it physically entered dispatch. Its
  `latest_effect_state` of `observed` means an independent observation saw
  the change; `execution_settled` alone proves nothing about the target.
- An expired lease in `ops_ownership` is not proof the owner died; the
  control plane fences the old generation rather than assuming absence.
- A non-null `integrity_verdict` (in `ops_status` or `ops_budget`) is an
  integrity finding to report verbatim; the accounting invariant and orphan
  holds or charges are part of the check behind it.
- A list read returns one page: follow `next_after` as `after` for the next
  one. `total_at_least` is the rows fetched, never the total; only a
  maintained counter's `total` is exact.
- Recovery work carries a different `incident_id` from the forward work it
  recovers; follow `recovers_work_id` / `recovers_effect_id`, not the incident.
- An `ops_remedy_memory` `retained` entry is only a candidate. The host's
  current eligibility and current mutation fingerprint still decide whether
  it can be admitted; memory never grants authority or rewrites host policy.

## Embedded hosts only: what is registered

`ops_host_capabilities` (and `ops://host`) exist only when a host embeds the
server. They list registered actions with `approval_class`, `required_role`,
`capability` (the declared operation capability; `unclassified` is never
executed autonomously),
`resolution.resolvable` (whether the static specification resolves today,
with the resolver's reason when not), `resolution.mutation_fingerprint` and
`authorized_by_policy`, plus other registered extensions by category, the
autonomous actor and standing policy, and the controller's declared
surfaces. Command lines are never included. Compare an action's
`mutation_fingerprint` with an effect's `mutation_fingerprint` from
`ops_get_effect` to detect specification drift.

## The one request that is not a read

Hosts that embed the server from their own code may expose
`ops_request_tick` (`target_id`, optional `detection_predicate_id`). It asks
the live controller for one bounded cycle; the controller decides whether a
condition exists, which registered remedy applies, whether policy grants
authority, whether the budget admits it, and how it settles. It cannot pick
an action or grant anything. The plugin's own stdio server never lists it.
When it is present, read `mutation_dispatched` and `outcome` in the result
and then re-read state with the inspection tools; do not loop on it.

## Errors

Tools return `{"error": {"code", "message", "detail"}}` with `isError`
true. Codes: `store_not_configured`, `store_not_found`,
`store_not_control_store`, `store_schema_stale` (`apexai-ops-migrate`
upgrades the store; the inspector never migrates. A schema-14 store is read
in place: `ops_status` answers with `migration_required: true`, gives the
unresolved total counted on 14's own index, and names under `unavailable`
the counters 14 does not maintain; the work lists and attention answer in
14's own order, under cursors that never cross the migration; and only a
read with no schema-14 form answers this code, with `detail.reason_code`
`migration_required`), `store_schema_unsupported`,
`store_unavailable`, `store_unreadable`, `evidence_not_configured`, `evidence_not_found`,
`evidence_invalid_id`, `evidence_unavailable`, `not_found` (with
`detail.kind`), `invalid_argument`. Report the code; do not retry blindly.

## Configuration

The server reads the host's `OPS_*` environment: `OPS_CONTROL_STATE_PATH`
(the SQLite control store) and `OPS_EVIDENCE_DIR` (the evidence root), or
the full host configuration when `OPS_OWNER_IDS` is present. A missing
store is reported by `ops_status` as `store.available: false` rather than
by a failed server start, so check `ops_status` first.
