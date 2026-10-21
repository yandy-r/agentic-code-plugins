# YAN-919 — Generic install item-selection plumbing

Linear: YAN-919 (foundation for YAN-918). GitHub: #403. Target release: next minor from
`main` (v6.1.0 line; RELEASING.md tracker is `none`).

## Problem

`--mcps` is wired by hand through `install.sh` (`MCP_SERVERS` global, `--mcps` case,
`list-mcps` dispatch), `cli.sh` (`parse_mcp_servers`, `run_list_mcps_command`),
`steps.sh` (`mcp_step_selected`, `preflight_mcp_selection`), `core.sh`
(`mcp_server_names`, `mcp_selection_for_target`, `run_mcp_step`) and three completion
files (`_ycc_mcps` helpers). Siblings YAN-920..925 would each copy all of it.

## Decisions

| Decision                                                                                      | Why                                                                                                   |
| --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Registry holds only `mcps` in this PR                                                         | Kinds without an adapter and step wiring are unreachable; trunk stays releasable. Siblings add a row. |
| Keep `ycc list-mcps` as a hidden compatibility alias of `ycc list mcps`                       | `--mcps`/`list-mcps` shipped in v5.2.1; scripts may call it.                                          |
| Bare `ycc list` prints the selectable kinds, one per line                                     | Completion needs the kind list without hard-coding it; pure bash, no Python.                          |
| Unknown-name hint now says `ycc list mcps --target <targets>`                                 | Only message change; points at the new canonical command. Everything else is byte-identical.          |
| Completions derive selector flags from `ycc list`                                             | Acceptance: adding a kind needs no completion edits.                                                  |
| New logic lives in `scripts/lib/install/select.sh`; `install.sh`, `steps.sh`, `cli.sh` shrink | Files stay near 500 lines; one code path.                                                             |

## Contract (`scripts/lib/install/select.sh`)

- `SELECTABLE_KINDS=(mcps)`; per-kind registry rows in associative arrays:
  `SELECTION_STEP[mcps]=mcp`, `SELECTION_NOUN[mcps]="MCP server"`,
  `SELECTION_NOUNS[mcps]="MCP servers"`,
  `SELECTION_STEP_HINT[mcps]="sync/remove --intent mcp, install --mcp or --only mcp"`.
- `SELECTION=()` associative; `parse_selection <kind> <csv>` (trim spaces, dedupe in
  order, empty item → `--<kind> contains an empty value`, none →
  `--<kind> requires at least one <noun>`).
- `selection_for <kind>` (CSV), `has_selection <kind>`, `is_selectable_kind <name>`.
- `<kind>_names <target>` adapter; `mcps_names` = today's `mcp_server_names`.
- `selection_for_target <kind> <target>`: selected names that target ships (CSV).
- `kind_step_selected <kind> <target>`: generalised `mcp_step_selected`.
- `preflight_selections`: loops kinds with a selection; same errors as
  `preflight_mcp_selection` with noun/step/hint from the registry.
- `run_list_command [<kind>] [--target <targets>]`: no kind → print kinds; else union
  of `<kind>_names` across targets whose valid steps include the kind's step,
  first-seen order. Unknown kind → error listing kinds.
- `install.sh` parses any `--<kind>` for `<kind>` in `SELECTABLE_KINDS` generically
  (missing value → `--<kind> requires a comma-separated list of <nouns>`).

## Tests

- Existing `scripts/tests/install/mcps.sh` stays green (update the completion-source
  assertion to the generic mechanism).
- New `scripts/tests/install/select.sh`, registered in `scripts/test-install-sync.sh`:
  parse (dedupe, empty item, spaces), unknown name, name missing on one target (warn
  and skip, using a fake kind registered in a subshell to prove the extension
  contract), selector without its step (error), `ycc list` union order, `ycc list
mcps --target opencode` == `ycc list-mcps --target opencode`, bare `ycc list`.

## Docs

`install.sh` usage, `docs/install/README.md`, `README.md`.
