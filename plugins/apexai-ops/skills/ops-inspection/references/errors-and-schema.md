# Errors, older stores and configuration

## Error codes

A failed tool call returns `{"error": {"code", "message", "detail"}}` with
`isError` true. Report the code; do not retry blindly.

| Code | Meaning |
|---|---|
| `store_not_configured` | no control store path is configured (`OPS_CONTROL_STATE_PATH` is unset or empty) |
| `store_not_found` | the configured path does not exist (`detail.path`) |
| `store_not_control_store` | the file is not an ApexAI DevOps control store |
| `store_schema_stale` | the store's schema is older than this engine reads, so it awaits migration (`detail.found`, `detail.expected`); on a schema-14 store only a read with no schema-14 form answers it (`detail.reason_code` `migration_required`) |
| `store_schema_unsupported` | the store's schema is newer, or otherwise unknown, to this engine version |
| `store_unavailable`, `store_unreadable` | the store could not be opened or read now |
| `evidence_not_configured` | no evidence directory is configured (`OPS_EVIDENCE_DIR`) |
| `evidence_not_found`, `evidence_invalid_id`, `evidence_unavailable` | the evidence packet is missing, its id is malformed, or the evidence root cannot be read |
| `not_found` | the identifier is unknown to the store (`detail.kind` names what) |
| `invalid_argument` | an argument does not match the tool's schema (`detail.tool`) |

## Reading an older store

Migration is the host operator's act (`apexai-ops-migrate`). The inspector
never migrates, and Claude should not suggest running it. A schema-14 store
is read in place:

- `ops_status` answers with `migration_required: true` and names, under
  `unavailable`, the counters schema 14 does not maintain.
- The unresolved total is counted on 14's own index. `ops_escalated_work`
  gives `total_at_least`, a lower bound, instead of an exact `total`.
- The work lists and attention answer in 14's own order, under cursors that
  never cross the migration.
- Only a read with no form for that schema answers `store_schema_stale`.

## Configuration

The server reads the host's `OPS_*` environment:

- `OPS_CONTROL_STATE_PATH`: the SQLite control store;
- `OPS_EVIDENCE_DIR`: the evidence root;
- or the full host configuration, when `OPS_OWNER_IDS` is present.

A missing store is reported by `ops_status` as `store.available: false`, not
by a failed server start. So check `ops_status` first. The engine refuses to
start when the environment holds an `OPS_*` variable it does not recognise.
