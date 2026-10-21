# YAN-923: `--plugins` selection for managed plugin entries

Linear: YAN-923 (parent YAN-918). GitHub: #415. Target release: `ystack v6.1.0`
(trunk-only, `tracker: none`; no backport). Builds on YAN-919 (#405),
YAN-920/921 (#410) and YAN-922 (#414). Third-party opencode plugin add/remove is
YAN-924 (out of scope): `--plugins` only selects entries the repo already manages.

## Research summary (current tree, `main` @ eb3a7589)

| target              | source → destination                                                  | `plugins` group rules (`merge_managed_config.py` `PROFILES`)                                        | entries today                                                                                                                                                                                               |
| ------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| claude              | `ycc/settings/settings.json` → `~/.claude/settings.json`              | `enabledPlugins` map-entries; `extraKnownMarketplaces` map-entries; `pluginMarketplaces` list-union | 26 `name@mkt` (25 `@claude-plugins-official`, `ycc@ycc`); marketplaces `ycc`, `yci` (no plugin uses it), `claude-plugins-official`; one list item `{name: claude-plugins-official, url}`                    |
| codex               | `.codex-plugin/config/config.toml` → `~/.codex/config.toml`           | `plugins` deep                                                                                      | legacy: 6 tables incl. `ycc@local-ycc-plugins`. **Native is enabled in this repo** (`codex_install.py enabled` exits 0): `codex_install.py:settings` swaps the legacy selector for `ycc@ycc`, `ycc-mcp@ycc` |
| opencode            | `.opencode-plugin/opencode.json` → `~/.config/opencode/opencode.json` | `plugins` list-union                                                                                | `@prevalentware/opencode-goal-plugin`, `./ycc-sensitive-guard` (the guard dir ships with the entry, `opencode.sh:161-167`, `:212-215`)                                                                      |
| cursor, agents, omp | —                                                                     | no `plugins` group (`cursor_intent_steps plugins` → none, omp → `base`)                             | —                                                                                                                                                                                                           |

Code paths:

- `scripts/managed_config_entries.py`: `ENTRY_POLICIES = ("deep", "map-entries")`;
  `entry_rule_paths`, `available_entries` (`--list-entries`), `select_source_entries`
  (filters every map rule of the given groups by the same names), `outside_selection`,
  `selected_state` (hides state pointers of unselected entries from planning).
- `scripts/merge_managed_config.py`: `main` (1402) validates `--entries` against
  `available_entries` over **all** `--groups`, filters the source, builds `plan_state`;
  `plan_merge` (511) list-union branch calls `union_lists` (360, whole-item compare →
  version bumps duplicate) and records `list_additions` hashes; `main` writes
  `ADDED_ITEMS_KEY = "added_item_sha256"` as `sorted({*previous, *additions})` (1543,
  never drops stale hashes); `plan_remove` (968) + `plan_list_removals` (921) take back
  every owned hash in the list and mark the whole `/plugins` state key spent (no
  selection awareness); `run_remove` (1328) pops `stale_keys` from the full state entry.
- Shell: `core.sh:merge_settings_config` (112, `"${@:5}"` passthrough) /
  `remove_settings` (171, no passthrough); `steps.sh:config_groups_for_target` (159:
  intents filter to `settings,plugins,hooks` order; `--package` drops `plugins`);
  callers: `claude.sh:278-285,398-399`, `codex.sh:423-435,508-517` (native →
  `codex_install.py settings --groups …`), `opencode.sh:153-167,209-215`.
  `core.sh:run_mcp_step` (315) is the selection pattern to mirror (skip + warn when a
  target ships none of the names; `info "<Nouns>: a, b"`).
- `select.sh`: kind registry (`SELECTABLE_KINDS`, `SELECTION_STEP/NOUN/NOUNS/STEP_HINT`,
  `<kind>_names`), `parse_selection`, `selection_for_target`, `kind_step_selected` →
  `target_runs_step` (subshell applying intents/package, then `step_enabled`),
  `preflight_selections`, `run_list_command`. `install.sh:648-655` parses any registered
  `--<kind>`. Completions (`scripts/completions/{ycc.bash,_ycc,ycc.fish}`) read kinds
  and names from `ycc list` / `ycc list <kind> --target <t>` — no edits needed.
- `codex_install.py:settings` (372) already passes `--entries <all plugin keys>` with
  `--groups settings,plugins`; harmless today only because codex `settings` has no
  entry-policy rule. opencode `settings` does (`agents`, `providers` deep), so a
  shared `--entries` across groups would wrongly filter them.
- `validate_opencode_config.py:validate_plugins`: items are a non-empty specifier
  string or `{package: str, options?}`; V2 key `plugins` (do not "fix" to `plugin`).

## Decisions

1. **Rule metadata, not bash special-casing.** Two optional rule fields in `PROFILES`:
   - `entry_key: "marketplace"` — a _derived_ rule: its keys/items are selected by
     mapping each selected entry name through `marketplace_of(name)` (text after the
     last `@`; `None` when there is no `@` or it is empty). Derived rules are never
     listed by `--list-entries` and their keys are not valid `--entries` names
     (`--plugins claude-plugins-official` → "unknown entries").
   - `item_key: "package" | "name"` — list-union items are keyed (decision 3); makes
     the list rule an entry rule.
     Claude: `extraKnownMarketplaces` gets `entry_key: "marketplace"`;
     `pluginMarketplaces` gets `item_key: "name", entry_key: "marketplace"`. opencode
     `plugins` gets `item_key: "package"`. Codex unchanged (deep works as-is; codex
     `[marketplaces.*]` stays unmanaged).
2. **`pluginMarketplaces` is selectable through its `name`** (not left out): a
   selective sync merges the item whose `name` is a selected plugin's marketplace,
   so `--plugins superpowers@claude-plugins-official` on a fresh machine writes the
   same three surfaces a full sync would. `--plugins ycc@ycc` touches no list item.
   Why: leaving it out makes selective and full syncs disagree on fresh machines.
3. **Item keys** (`managed_config_entries.item_key(rule, item) -> str | None`):
   - `"package"`: string → the specifier; dict → `item["package"]` if a non-empty
     string. Normalize the specifier: strip; if it starts with `.`, `/` or `~`, or
     contains `:` (`file:`, `git+…`, `https:`, `npm:` aliases) it is a path/URL —
     key is the spec with trailing `/` removed (`./ycc-sensitive-guard/` ≡
     `./ycc-sensitive-guard`, matching `opencode_config_loads_guard`). Else strip a
     version: scoped `@scope/pkg[@ver]` → cut at the first `@` after index 0;
     unscoped `pkg[@ver]` → cut at the first `@` at index > 0. Empty → `None`.
   - `"name"`: dict with non-empty string `name`, else `None`.
   - Items with key `None` are never listed/selected and keep today's whole-item
     union semantics.
     Used by `--list-entries` (opencode prints `@prevalentware/opencode-goal-plugin`,
     `./ycc-sensitive-guard`), `--entries` filtering, merge replacement and removal.
4. **Version bump replaces, never duplicates** (all keyed list rules, selection or
   not). In the keyed list planner, for each source item with key `k`:
   identical item present → no-op; same-key items present that are owned (hash in
   `added_item_sha256`) → replace the first one in place with the source item and drop
   the other owned same-key items (heals duplicates left by the old bug); same-key
   item present that is **not** owned (user-written) → keep it, do not append, report
   conflict `"/plugins[k]"` (printed by the existing `kept your local value at …
(re-run with --force to take the repo value)` line); with `--force` replace it in
   place and own the new hash; no same-key item → append. The planner returns the
   complete new owned-hash list per list pointer (previous − replaced/removed + added);
   `main` writes it verbatim instead of `sorted({*previous, *additions})`.
5. **Selective list removal.** Only current items whose key is selected are removal
   candidates: owned hash → removed; `--force` → also same-key items (the user's
   version); unowned same-key item without `--force` → conflict `"/plugins[k]"`.
   Unselected items are untouched and never conflicts. State: the pointer's owned
   list loses exactly the removed hashes; the key is spent only when no owned hash
   remains and the list was deleted (full remove keeps today's behavior).
6. **Marketplace retention on remove (all removes, selective or full).** After the
   primary rules (rules of the group without `entry_key`) are planned, compute
   `in_use = {marketplace_of(k) for k in destination enabledPlugins keys not being
removed}` — this counts user-added plugins and selected plugins kept as conflicts.
   Derived candidates whose key/`name` is in `in_use` are dropped from the plan, their
   state pointers/hashes are kept, and a note is printed:
   `[ok] kept /extraKnownMarketplaces/<mkt> (still used by <first plugin>)` (list:
   `/pluginMarketplaces[<mkt>]`). Why: removing a marketplace an enabled plugin
   still references breaks that plugin; data integrity over tidiness. Merge-time
   pruning of repo-dropped marketplaces is unchanged (non-goal).
7. **Scope `--entries` to named groups: new `--entry-groups <csv>`** on
   `merge_managed_config.py` (default: all `--groups`, preserving every current
   caller). Shell passes `--entry-groups plugins --entries <sel>` so `settings` and
   `hooks` in the same invocation stay whole, in one atomic write and one state save.
   `--list-entries` lists over the entry groups. Implementation: `main` derives a
   narrowed profile copy (`managed_config_entries.narrow_profile(profile,
entry_groups, entries)`) that sets `selected: set[str]` on each entry rule of the
   entry groups (derived rules get the mapped marketplaces); `select_source_entries`,
   `outside_selection`, `selected_state`, the list planners and retention read
   `rule.get("selected")` — no extra parameters threaded through
   `merge_json/merge_toml/remove_*`. `select_source_entries` deletes any container a
   selection empties (prevents writing `"pluginMarketplaces": []` or `{}` deep tables
   for `--plugins ycc@ycc`). `selected_state` never hides list pointers (hash lists
   are filtered by key at plan time instead).
8. **Codex native path.** `codex_install.py settings` gains `--entries <csv>` and
   `--list-entries` (list = plugin keys of the composed native text, i.e. shipped
   tables minus `ycc@local-ycc-plugins` plus `ycc@ycc`, `ycc-mcp@ycc`). Unknown names
   → `ValueError("unknown plugins …")` (exit 2). `merge_config` passes
   `--entry-groups plugins` whenever it passes `--entries`.
9. **Shell kind `plugins`.** `SELECTION_STEP[plugins]=settings`; noun `plugin`/`plugins`;
   hint `it narrows the plugins config group; use --intent plugins, or install --only settings`.
   New optional registry `SELECTION_GROUP=([plugins]=plugins)`: `kind_step_selected`
   for such kinds requires the step **and** the group in
   `config_groups_for_target` (subshell, same setup as `target_runs_step`), so
   `--intent settings --plugins x` and `install --package … --plugins x` are rejected
   by preflight before any write. `plugins_names <target>`: claude/opencode/legacy
   codex → `merge_managed_config.py --groups plugins --list-entries` on the target's
   source (new `plugins_source <target>` in `core.sh` beside `mcp_source`); codex with
   `codex_repository_native_enabled` → `codex_install.py settings --groups plugins
--list-entries`; other targets print nothing.
10. **Settings steps.** New `core.sh:plugins_selection <target> <groups>` sets
    `PLUGINS_GROUPS` (groups, with `plugins` dropped when the target ships none of the
    names: `warn "none of the selected plugins (a b) is managed for <t> — skipping its plugins group"`)
    and `PLUGINS_SELECT` (`--entry-groups plugins --entries <sel>` + `info "Plugins: a, b"`;
    empty array without `--plugins` or without the `plugins` group). `remove_settings`
    forwards `"${@:5}"`. opencode guard dir: synced/removed with the `plugins` group
    only when no `--plugins` was given or the selection includes `./ycc-sensitive-guard`.

## Tasks

Slices A and B share only the CLI contract above (flags `--entry-groups`,
`--entries`, `--list-entries`; `codex_install.py settings --entries/--list-entries`;
message strings in decisions 4–6, 9–10) and run in parallel. Slice C writes tests
against that contract and can start in parallel; it finishes after A/B land.

### Slice A — Python merge helper (`scripts/managed_config_entries.py`, `scripts/merge_managed_config.py`, `scripts/codex_install.py`)

1. `managed_config_entries.py` (keep new logic here; `merge_managed_config.py` is
   1581 lines): `ENTRY_POLICIES` gains `list-union` **only for rules with
   `item_key`**; add `marketplace_of`, `item_key`, `narrow_profile`, a rule-level
   `selection(rule)` accessor, keyed `available_entries` (skip derived rules; lists by
   item key), keyed `select_source_entries` (+ drop emptied containers),
   `outside_selection`/`selected_state` reading `selected` (lists never hidden),
   `plan_keyed_list(...)` for decision 4, and `retained_marketplaces(...)` for
   decision 6. Full type hints (strict-clean).
2. `merge_managed_config.py`: `PROFILES` metadata (decision 1); argparse
   `--entry-groups` (validate ⊆ `--groups`); `main` uses `narrow_profile`; `plan_merge`
   list branch delegates keyed rules to `plan_keyed_list`, unkeyed rules keep
   `union_lists`; replace `list_additions` with the complete owned-hash list per
   pointer and write it verbatim in `main`; `plan_list_removals` honors `selected`
   and returns owned-after per pointer (decision 5); `plan_remove` applies retention
   and returns notes; `remove_json`/`remove_toml`/`remove_hook_commands` and
   `run_remove` carry `owned_after` (update `state_entry[key][ADDED_ITEMS_KEY]`, spend
   only when empty and deleted) and print notes. Update the policy comment block.
3. `codex_install.py`: `settings(groups, *, remove, force, entries=None, list_only=False)`
   per decision 8; argparse `--entries`, `--list-entries`; `merge_config` adds
   `--entry-groups plugins` with `--entries`.

Validate: `python3 -m pytest scripts/test_managed_config_entries.py scripts/test_merge_managed_config.py scripts/test_codex_install.py -q`;
`ruff check scripts/managed_config_entries.py scripts/merge_managed_config.py scripts/codex_install.py && ruff format --check` on the same files;
`./scripts/validate.sh --only types`.

### Slice B — shell wiring, help, docs

1. `scripts/lib/install/select.sh`: register `plugins` (decision 9), `SELECTION_GROUP`,
   `plugins_names`, group-aware `kind_step_selected`; update the header comment.
2. `scripts/lib/install/core.sh`: `plugins_source`, `plugins_selection`,
   `remove_settings` passthrough.
3. Targets: `claude.sh` sync (278-285) and remove (398-399); `codex.sh` legacy merge
   (430-434), native settings (426) and both remove branches (509-517) — native gets
   `--entries <sel>` (no `--entry-groups`; `codex_install.py` adds it); `opencode.sh`
   sync (153-167) and remove (209-215) incl. the guard condition (decision 10).
4. `install.sh`: `[--plugins <names>]` in the install/sync/remove synopses (39-43) and
   the `list` example (54); an option block after `--commands` (285): narrows the
   plugins group (claude `enabledPlugins` + the marketplaces they use, codex
   `[plugins."name@mkt"]`, opencode `plugins` items by package name); settings/hooks in
   the same run stay whole; requires the plugins group (`--intent plugins`, or
   `install --only settings`); marketplaces follow their plugins and are kept on
   remove while an enabled plugin still uses them; names: `list plugins`.
5. Docs: `docs/install/README.md` — new `### Selecting Plugins` (after Selecting MCP
   Servers) with the four spec examples and the rules above, version-bump replace in
   Merge Semantics, retention in the remove table's `settings, plugins, hooks` row;
   `docs/install/opencode.md` Plugins section (selection by package name, version
   bump replaces only installer-added items). No new files besides this plan.

Validate: `shellcheck -x install.sh scripts/lib/install/*.sh scripts/lib/install/targets/*.sh`;
`bash scripts/tests/install/select.sh`; `npm run lint:modified`.

### Slice C — tests

1. `scripts/test_managed_config_entries.py` (direct imports allowed, as
   `test_codex_install.py` does): `item_key` table (`pkg`, `pkg@1.2.3`, `@s/p`,
   `@s/p@1.2.3`, `{package: "@s/p@1"}`, `{package: "p", options: {}}`,
   `./ycc-sensitive-guard/`, `file:../x`, `""`, `3` → `None`); `marketplace_of`
   (`a@m`, `a`, `a@`); claude `--list-entries` = enabledPlugins keys only; select one
   plugin → exactly that key + its `extraKnownMarketplaces` entry + its
   `pluginMarketplaces` item, other state pointers byte-identical; `--entries ycc@ycc`
   writes no `pluginMarketplaces`; marketplace name alone rejected, nothing written;
   `--entry-groups plugins` with `--groups settings,plugins` (opencode: `agents` /
   `providers` merged whole).
2. `scripts/test_merge_managed_config.py`: opencode selective sync/remove of one item
   (other owned item and its hash survive); version bump `pkg@1` → `pkg@2` replaces in
   place, state hash swapped; owned duplicates collapse; user `pkg@0` kept + `/plugins[pkg]`
   warning; `--force` replaces it; `{package, options}` keyed; remove `--force` takes
   the user's same-key item; claude retention: remove one of two same-mkt plugins keeps
   the marketplace (+ note, state kept), removing the last removes it and the list
   item; user-added `mine@claude-plugins-official` retains it on a full remove.
3. `scripts/test_codex_install.py`: `settings --list-entries` prints native keys (no
   `ycc@local-ycc-plugins`); `--entries` passes the subset + `--entry-groups plugins`
   (patch `subprocess.run`), unknown → exit 2.
4. Shell (`HOME` sandboxes via `new_home`): `select.sh` — kinds list
   `mcps skills agents commands plugins` (lines 15, 26, 88 expectations);
   `claude.sh` — `list plugins --target claude` has `superpowers@claude-plugins-official`
   and no bare `claude-plugins-official`; spec example 1 writes exactly two
   `enabledPlugins` keys + one marketplace; `--intent settings,plugins --plugins X`
   still merges `model`; remove one keeps the other + marketplace; `--intent settings
--plugins X` rejected with the hint, nothing written; unknown name rejected.
   `codex.sh` — spec example 2 after a full sync removes only `cloudflare@openai-curated`;
   selective sync writes one table. `opencode.sh` — spec example 3 writes the goal
   plugin only (no guard entry, no guard dir); selective remove keeps a user plugin.
   Completion: one bash assert that `ycc sync --plugins` completes names for the
   line's `--target` (pattern: `mcps.sh:100-105`).

Validate: the pytest line from Slice A; `bash scripts/tests/install/{select,claude,codex,opencode,mcps}.sh`;
`shellcheck -x scripts/tests/install/*.sh`; `ruff check` on the test files.

### Final (main agent, once)

`python3 -m pytest scripts/test_managed_config_entries.py scripts/test_merge_managed_config.py scripts/test_codex_install.py -q`,
`bash scripts/test-install-sync.sh`, `./scripts/validate.sh --only types,config`, `npm run lint:modified`.

## Risks / notes

- bash `COMP_WORDBREAKS` may contain `@` (non-interactive default); completing
  `name@mkt` then splits words. Interactive shells here exclude it; tests build
  `COMP_WORDS` directly. Not addressed (out of scope).
- `yci` marketplace has no enabled plugin, so only full syncs manage it.
- Full-remove behavior change (decision 6) is intentional; document it.
