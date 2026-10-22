# YAN-925 — `--mods` and `--hooks` selection (claude)

Linear: YAN-925 (child of YAN-918, built on YAN-919). GitHub: #423. Target release: v6.1.0.

## Acceptance (from YAN-925)

- `--mods status-bar` installs just that mod. Remove leaves the `ycc-mods` marketplace in
  place while other ycc mods remain. Tested with the stubbed `claude` CLI in
  `scripts/tests/install/claude.sh`, with a second fixture mod so selection is exercised.
- `--hooks WorktreeCreate` merges only that event. Unselected managed events and their
  ownership state are untouched.
- `--mods`/`--hooks` on a run where no target has the step: preflight error. Completion
  lists mods and hook events.

## Design decisions

1. **`mods` kind** (`select.sh`): `SELECTION_STEP[mods]=mods`; `mods_names claude` =
   `mods_plugin_names`; other targets print nothing (no mods step).
2. **`hooks` kind**: narrows the `hooks` config group of the settings step, exactly like
   `plugins` (`SELECTION_STEP[hooks]=settings`, `SELECTION_GROUP[hooks]=hooks`).
   `hooks_names <t>` = `merge_managed_config.py --list-entries --groups hooks` for targets
   whose `<t>_config_groups` has `hooks` (claude only). Selection is per **event**, not per
   script.
3. **One settings-selection path.** `plugins_selection` becomes a generic
   `config_group_selection <target> <groups>` in `core.sh` that applies every
   `SELECTION_GROUP` kind. Several narrowed groups pass one `--entry-groups g1,g2` and the
   union of names as `--entries` (plugin keys and event names never collide; the merge
   helper validates every name). Outputs renamed `CONFIG_GROUPS` / `CONFIG_SELECT` /
   `PLUGINS_CATALOG_SELECT`; every caller (claude, codex, opencode, opencode-catalog) is
   migrated. No change to `merge_managed_config.py`.
4. **`--hooks` flag collision.** `install --hooks` stays the boolean "also run the hooks
   step" flag. On `sync` and `remove` (where the boolean is already rejected) `--hooks
<events>` is the selector. Completions follow: install's `--hooks` takes no value.
5. **Mods sync** with `--mods`: register the marketplace, install only selected mods;
   `warn_sideloaded_mods` checks only the selected mods.
6. **Mods remove** with `--mods`: uninstall only selected mods; remove the `ycc-mods`
   marketplace only when no other `*@ycc-mods` key remains in `~/.claude/settings.json`
   `enabledPlugins` (selected names excluded, so a CLI that has not yet rewritten
   settings does not keep it alive). Otherwise say why it was kept. Without `--mods`,
   behaviour is unchanged.
7. **Hooks remove** with `--hooks`: the `~/.claude/hooks` link (one directory link) is kept
   while any managed hook event outside the selection is still recorded in the
   managed-config ownership state for `~/.claude/settings.json`; else unlinked. Sync with
   `--hooks` still creates/keeps the link.
8. **Test seam**: `YCC_MODS_ROOT` (default `${SCRIPT_DIR}/ycc/mods`) lets the claude suite
   point at a two-mod fixture marketplace. No second real mod ships.

## Files

- `scripts/lib/install/select.sh` — kinds, adapters, hints.
- `scripts/lib/install/core.sh` — `config_group_selection`.
- `scripts/lib/install/targets/claude.sh` (+ new `claude-mods.sh` if needed to stay
  ≲500 lines), `codex.sh`, `opencode.sh`, `opencode-catalog.sh` — callers.
- `install.sh` — parser (`--hooks` dual role), usage text.
- `scripts/completions/{ycc.bash,_ycc,ycc.fish}`.
- `docs/install/README.md`.
- Tests: `scripts/tests/install/claude.sh`, `scripts/tests/install/select.sh`.
