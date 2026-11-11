# Embedded hosts only

The plugin's own stdio server never lists the tools on this page. They exist
only when an application embeds the engine's MCP server in its own process.
If they are not in the tool list, they do not exist here. Do not mention them
as options.

## What is registered: `ops_host_capabilities` and `ops://host`

These list the registered actions, each with:

- `approval_class` and `required_role`;
- `capability`: the declared operation capability. `unclassified` is never
  executed autonomously;
- `resolution.resolvable`: whether the static specification resolves today,
  with the resolver's reason when it does not;
- `resolution.mutation_fingerprint`;
- `authorized_by_policy`.

They also list other registered extensions by category, the autonomous actor,
the standing policy, and the controller's declared surfaces. Command lines are
never included.

To detect specification drift, compare an action's `mutation_fingerprint`
with an effect's `mutation_fingerprint` from `ops_get_effect`.

## The one request that is not a read: `ops_request_tick`

An embedding host may expose `ops_request_tick` (`target_id`, optional
`detection_predicate_id`). It asks the live controller for one bounded cycle.
The controller decides:

- whether a condition exists;
- which registered remedy applies;
- whether policy grants authority;
- whether the budget admits it;
- how the cycle settles.

The request cannot pick an action or grant anything. When it is present, read
`mutation_dispatched` and `outcome` in its result, then re-read state with the
inspection tools. Do not loop on it.
