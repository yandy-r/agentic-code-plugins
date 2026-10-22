# YAN-924: opt-in catalog of third-party opencode plugins

Linear: YAN-924 (parent YAN-918). GitHub: #420. Target release: `ystack v6.1.0`
(trunk-only, `tracker: none`; no backport). Builds on YAN-923 (#419, keyed list-union
plugin entries).

## Verified facts (2026-10-21)

- On live opencode v2.1.1, `opencode plugin add oh-my-opencode-slim@3.0.5` writes only
  `opencode.json` `plugins: ["oh-my-opencode-slim@3.0.5"]`. It writes no `tui.json` or
  `cli.json`. Under V2 the CLI loads TUI halves from `opencode.json`
  (opencode.ai/v2/docs/cli/plugins). `tui.json` (singular `plugin`) is the V1 layer.
  **Decision: no `tui` field and no `opencode-tui` profile.** The bundle is V2-only.
- The V2 cache layout is `~/.cache/opencode/npm/<pkg>@<spec>/<generation>/node_modules/<pkg>`
  (observed). The V1 layout is `~/.cache/opencode/packages/<pkg>@<spec>/…`, and the legacy
  one is `~/.cache/opencode/node_modules/<pkg>`. `<cache>` = `${XDG_CACHE_HOME:-$HOME/.cache}/opencode`.
  Scoped packages nest (`npm/@scope/name@spec`).
- slim 3.0.5 runtime: it removes the built-in `general`/`explore` subagents unless the host
  config declares them. The ycc bundle declares `agents.{general,explore}.model`, so the
  catalog manages `agents.{general,explore}.disabled: true` (V2 spelling; V1 `disable`
  is rejected).
- slim installer default companion: `<configDir>/oh-my-opencode-slim.json`, with project
  override `<project>/.opencode/oh-my-opencode-slim.json`. ycc ships the 3.0.5
  installer's `--dry-run` default output.
- slim's installer also sets `lsp: true` when no `lsp` key exists, and offers shell-rc
  exports (`OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true`, `OPENCODE_ENABLE_EXA=1`).
  ycc automates neither; both are printed as `notes`.

## Catalog: `ycc/settings/opencode-plugins.json`

```json
{
  "plugins": {
    "oh-my-opencode-slim": {
      "package": "oh-my-opencode-slim@3.0.5",
      "description": "Multi-agent orchestration preset for opencode",
      "homepage": "https://github.com/alvinunreal/oh-my-opencode-slim",
      "default": false,
      "config_files": [
        { "source": "opencode-plugins/oh-my-opencode-slim.json", "destination": "oh-my-opencode-slim.json" }
      ],
      "managed_keys": { "agents": { "explore": { "disabled": true }, "general": { "disabled": true } } },
      "notes": ["…lsp…", "…shell exports…"]
    }
  }
}
```

The catalog name (map key) must equal the version-stripped package name, which is the
`item_key` the merge helper uses. `options` (an object) is optional; when present, the
plugins item is rendered as `{"package", "options"}`. `config_files[].source` is relative
to `ycc/settings/`, and `destination` is a bare filename.

Validation (`opencode_plugin_catalog.py validate`; `validate-opencode-plugin.sh`) rejects:

- a `package` that is not exactly `<name>@<X.Y.Z[-pre]>`, i.e. a missing version, a
  range, or a tag;
- a name that differs from the package's `item_key`;
- `default` other than `false`;
- unknown entry keys;
- a `managed_keys` top-level key other than `agents`;
- a V2-invalid result: `validate_config({"plugins": [item], **managed_keys})` must be
  clean, which also rejects V1 keys such as `disable`;
- a missing `config_files` source, or a destination that is not a plain filename
  (`/`, `..`, empty);
- a name that collides with a bundle plugin name.

## Components

### A. Python: `scripts/opencode_plugin_catalog.py` (mypy strict, < 500 lines)

CLI contract (the shell depends on it exactly):

| subcommand    | args                                                | behavior                                                                                                                                                                                                                                                         |
| ------------- | --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `names`       | —                                                   | catalog names, one per line                                                                                                                                                                                                                                      |
| `validate`    | `[--catalog PATH]`                                  | print errors and exit 1, else exit 0                                                                                                                                                                                                                             |
| `source`      | `--names CSV --out FILE.json`                       | write `{"plugins":[item…], "agents":{…}}` for the named entries (deep-merged managed_keys)                                                                                                                                                                       |
| `companions`  | `sync\|remove --names CSV --dest-dir DIR [--force]` | hash-owned file copies (below)                                                                                                                                                                                                                                   |
| `purge-cache` | `--names CSV [--cache-dir DIR]`                     | delete `npm/<pkg>@*`, `packages/<pkg>@*`, `node_modules/<pkg>` under the cache dir (default `${XDG_CACHE_HOME:-~/.cache}/opencode`); handles scoped names; refuses anything that resolves outside the cache dir or is a symlink escaping it; prints each removal |
| `notes`       | `--names CSV [--remove]`                            | print notes (`--remove`: the rc lines the user may delete)                                                                                                                                                                                                       |

Unknown names are a hard error (exit 2) everywhere.

Companion ownership state: `opencode-plugin-files.json` beside the managed-config state
(the same rule as `install_slices.state_path()`, honoring `YCC_MANAGED_CONFIG_STATE`),
`{"version":1,"sha256":{"<abs dest>":"<hex>"}}`, written atomically.

- sync:
  - destination absent: write it and record the hash;
  - destination equals the source: record the hash (adopt) and report up to date;
  - destination hash equals the recorded hash: overwrite with the new source
    (a version update) and record the hash;
  - otherwise: `[!!] kept <path>: local edits (re-run with --force to replace it)`.
    `--force` overwrites.
- remove:
  - destination hash equals the recorded hash, or equals the source: delete it and drop
    the state entry;
  - absent: drop the state entry;
  - otherwise: `[!!] kept … local edits` unless `--force`.

### B. Merge helper: per-plugin state scope

Add a profile `opencode-catalog` (`json`, `jsonc`) with groups:

- `plugins`: `{"path":["plugins"],"policy":"list-union","item_key":"package"}`
- `agents`: `{"path":["agents"],"policy":"deep"}`

Add `--state-scope NAME`, which makes the state key `"{profile}[{NAME}]:{dest}"`. The
shell runs one merge per catalog plugin with `--state-scope <name>`. This gives each
plugin independent ownership, so syncing plugin B never stale-deletes plugin A's leaves,
and the bundle's `opencode-config` state is untouched. This is the only change to
`merge_managed_config.py`, and the new tests go in the new test file.

### C. Shell (`scripts/lib/install/targets/opencode.sh`, `core.sh`/`select.sh`, `install.sh`)

- `plugins_names opencode`: bundle names, then catalog names (`… names`). This gives
  preflight, `ycc list plugins` and completions for free. Update the
  `scripts/tests/install/opencode.sh` list expectation.
- Split the selection for opencode into bundle names (helper `--entries`, existing path)
  and catalog names (`OPENCODE_CATALOG_SELECT`). With only catalog names, the bundle
  `plugins` group is skipped silently (no "none managed" warning), and its other groups
  (`settings`) still run as today.
- Sync, after the bundle merge, for each selected catalog name:
  1. `source` to a temp `.json` (cleaned up on exit);
  2. `merge_settings_config opencode-catalog <tmp> <dest opencode.json> plugins,agents --state-scope <name>`;
  3. `companions sync`;
  4. `notes`.

  With no `--plugins`, no catalog plugin is touched.

- Remove: with a selection, act on the selected catalog names. Without one (`remove
--intent plugins` or `--only settings`), act on every catalog name; ownership gating
  makes this a no-op for plugins ycc never installed. For each name:
  1. `merge_settings_config … --remove --state-scope <name>`;
  2. `companions remove`;
  3. `purge-cache` when `--purge-cache` is set;
  4. `notes --remove`.
- `--purge-cache`: a new install.sh flag, valid only with `remove` (error otherwise). It
  goes in usage, the option reference, and all three completions (remove only).
- `--project`: add `opencode_project_steps() { echo settings; }`. The settings step in
  project scope is allowed only when the run selects catalog plugins only (an
  `opencode_preflight` error otherwise: the bundle settings/guard are global-only). The
  destination is `$(project_root)/opencode.json`, with companions in
  `$(project_root)/.opencode/`. Global (`~/.config/opencode/`) remains the default.
  Update the `preflight_step_support` error text.

### D. Docs

- `docs/install/opencode.md`: a "Third-party plugins" section covering the catalog, sync,
  remove, `--purge-cache`, `--project`, notes, and why ycc does not run the upstream
  installer and writes no `tui.json`.
- `docs/install/README.md`: scope table, removal table, and selecting-plugins example.
- `install.sh` usage and examples.

## Tests (critical only)

- `scripts/test_opencode_plugin_catalog.py` (registered in `validate.sh` and mypy):
  - validation failures: unpinned, range, tag, V1 `disable`, `default: true`, bad
    destination, name/key mismatch;
  - companion ownership: fresh, adopt, update, user-edited kept, force, remove only when
    unchanged;
  - purge-cache: the three layouts and a scoped name, nothing outside the cache, symlink
    escape refused;
  - merge-helper state scope: two plugins in independent state, removing one leaves the
    other.
- `scripts/tests/install/opencode-catalog.sh` (registered in `test-install-sync.sh`):
  - default `--intent plugins` does not install slim;
  - `--plugins oh-my-opencode-slim` adds the pinned item, agents `disabled`, and the
    companion, and prints notes;
  - a second run is a no-op (byte-identical);
  - a user-edited companion is preserved with a warning;
  - remove restores `opencode.json` byte-identical to the pre-install seed and deletes
    the companion;
  - `--purge-cache` removes the seeded cache layouts;
  - `--purge-cache` without `remove` errors;
  - `--project` writes the project files, and project scope with bundle plugins errors.

## Decisions

| decision                                    | why                                                                        |
| ------------------------------------------- | -------------------------------------------------------------------------- |
| No `tui.json` / `opencode-tui`              | Verified V2 behavior; the bundle is V2-only; avoids a duplicate V1 entry   |
| `agents.*.disabled` managed keys            | Required for slim under the ycc bundle; V2 spelling                        |
| Per-plugin `--state-scope`                  | Independent ownership; no stale deletion across plugins or with the bundle |
| Companion `.json`, not `.jsonc`             | Matches upstream; a `.jsonc` would shadow a user's `.json`                 |
| `lsp` and rc exports printed, never written | ycc does not edit rc files; `lsp` is a user choice                         |
| `ycc list plugins` prints plain names       | Completions parse the output; the docs mark catalog entries as opt-in      |
| Project scope for catalog plugins only      | Bundle settings and the guard path are global-only                         |
