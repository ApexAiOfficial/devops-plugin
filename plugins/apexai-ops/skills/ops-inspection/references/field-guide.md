# Field guide: what each `ops_*` tool returns

Each tool's own description on the server is authoritative. This guide adds
what to look for in each answer and how to page through it.

| Need | Tool | Yields |
|---|---|---|
| overall picture | `ops_status` | counts (from maintained counters), schema, the durable integrity verdict, evidence availability (`packets_at_least`) |
| health | `ops_health` (optional `scope`: `full`, `liveness`, `readiness`, `store`; optional `supervisor_id`) | every fail-closed condition with its status (`clear`, `holds`, `unknown`, `unevaluated`), severity, `since` and runbook key; the aggregate, and the exit status the same check gives on the command line; `complete` is false while any condition is unevaluated |
| targets | `ops_list_targets`, `ops_get_target` (page with `after`) | `target_id`, ownership, latest work, live work, `escalated_at_least`; one target's work newest first |
| ownership | `ops_ownership` (page with `after`) | owner, incarnation, epoch, lease, fence floor per target |
| incidents | `ops_list_incidents`, `ops_get_incident` (page with `after`) | `incident_id`, latest `work_id` and state, whether open; one incident's decisions oldest first |
| work | `ops_list_work` (filter by `state`, `target_id`, `incident_id`; page with `after`) | `work_id`, newest first in creation order |
| unresolved / escalated | `ops_unresolved_work`, `ops_escalated_work` (page with `after`) | work still owed a resolution; decisions settled `ESCALATED`; `total` is exact (a maintained counter; at schema 14 unresolved's is counted on 14's own index, and escalated's page has `total_at_least` instead, a lower bound) |
| attention | `ops_attention` (page with `after`) | every revision blocker (the latest blocking decision of an incident and desired revision) and every unacknowledged recovery dead end, with notification state; one page of `limit` (default 50), `truncated`, `total_at_least` |
| rearm authorizations | `ops_rearms` (filter by `blocking_work_id`, `incident_id`, `live_only`; page with `after`) | who authorized another decision for a blocked one, live or consumed, newest first; `total_at_least` is the rows fetched, `live` is exact |
| obligations | `ops_obligations` (optional `limit`) | what is owed a look, `owed_since` (when it first became owed) and `due_at` (next eligible), `due_total` and `truncated`, and which stuck classes are and are not evaluated |
| watches | `ops_watches` (optional `include_retired`, `limit`; page with `after`) | each declared (target, predicate) generation, its interval, latest look and next due look |
| remedy memory | `ops_remedy_memory` (optional `limit`; continue one `list` with its `after`) | latest decisive remedy evidence, retained candidates per exact scope, clearances, and retained-selection refusal bypasses, each a page with `totals_at_least` and `next_after` |
| one decision | `ops_get_work` (events page with `after`) | effects (`effect_id`), grants, `latest_transition` (its newest accepted transition, whatever page is shown), a page of events, the `evidence_packet_ids` that page cites |
| one effect | `ops_get_effect` (events page with `after`) | intent, the dispatched flag, envelope, recovery hold and contract, a page of events |
| history | `ops_events` (filter by `work_id`, `effect_id`, `target_id`, `kind`; page with `after`, or `after_seq`) | the authoritative append-only events; `total_at_least` is the rows fetched, never a count of the history; a `kind`-only page can be short while `truncated` |
| budgets | `ops_budget` (page with `after`) | envelopes, their recovery holds, the durable integrity verdict |
| evidence | `ops_list_evidence` (page with `after`), then `ops_get_evidence` | sanitized packets, by packet id |

## Resources

Some reads also exist as MCP resources: `ops://status`,
`ops://work/{work_id}`, `ops://effect/{effect_id}`,
`ops://incident/{incident_id}`, `ops://target/{target_id}`,
`ops://evidence/{evidence_packet_id}`, `ops://unresolved`, `ops://escalated`,
`ops://budget` and `ops://evidence`.

## Following a decision

- `ops_get_work`'s `latest_transition` names the newest accepted transition
  and its reason code, whatever page of events is shown. When it cites a
  packet (`evidence_packet_id`), read it with `ops_get_evidence`.
  `evidence_packet_ids` holds only what the shown page of events cites.
- An effect's `mutation_fingerprint` (from `ops_get_effect`) identifies the
  exact action specification it ran with.
