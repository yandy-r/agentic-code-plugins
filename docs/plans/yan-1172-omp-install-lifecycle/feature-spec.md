# Feature Spec: YAN-1172 — `install.sh --target omp` lifecycle

- **Linear:** YAN-1172 (P-YAN-21). **GitHub:** #393. **Target release:** v6.1.0 (trunk-only PR into `main`).
- **Blocked by (done):** YAN-1171 (#391, OMP package tree and catalog), YAN-1164. **Blocks:** YAN-1173–1177.
- **Contract:** [ADR 0002](../../internal/adr/0002-omp-runtime-contract.md), [spike](../../internal/spikes/omp-runtime-contract.md), [YAN-1171 plan](../yan-1171-omp-native-packages/plan.md).
- **Format:** condensed `feature-research` spec. One researcher pass (live omp CLI plus a codebase map), not the seven-file pipeline.

## Executive Summary

`install.sh` gains an `omp` target. It installs, updates, removes, migrates and previews the generated
OMP packages through the `omp plugin` CLI only (never hard-coded `~/.omp` paths), at user scope by default
or project scope with `--project`. A new `scripts/omp_install.py` helper mirrors `scripts/codex_install.py`.
It exports the packages into a ycc-owned local marketplace directory, registers it as the `ycc`
marketplace, installs and upgrades each selected `<pkg>@ycc`, and records ownership in
`~/.config/ycc/omp-native-install.json`, so `remove` deletes only what ycc created. Live probing of
omp 18.12.3 found four behaviours that shape the design:

- `--dry-run` is honoured only by `install` and `uninstall`. `upgrade`, `enable` and `marketplace add`
  mutate even with `--dry-run`.
- A user-scope upgrade garbage-collects cache directories that project installs outside the current cwd
  still link to.
- A marketplace registered at the unlisted checkout root silently falls back to the Claude catalog.
- Re-running `marketplace add` or `install` exits 1.

The helper therefore plans every action from read-only queries, implements dry-run itself, and calls
each mutating verb only when needed.

## External Dependencies

### APIs and Services

#### omp CLI (oh-my-pi) — verified live, omp 18.12.3

- **Binary:** `~/.local/bin/omp` (a self-contained ELF). The supported floor is `>=18.12.2`
  (`MIN_OMP_VERSION` in `scripts/generate_omp_packages.py`).
- **Sandbox:** every call ran under `env -i` with `HOME`, `XDG_{CONFIG,DATA,STATE,CACHE}_HOME`,
  `XDG_RUNTIME_DIR` and `TMPDIR` pointing into `mktemp -d /tmp/omp1172.*`, and with
  `GIT_CONFIG_GLOBAL=/dev/null`. The marketplace source was `python3 scripts/generate_omp_packages.py --export <sandbox>/export`.
- **Help surface:** there is one help page for all actions:
  - `omp plugin [ACTION] [TARGETS...]`
  - Actions: `install|uninstall|list|link|doctor|features|config|enable|disable|marketplace|discover|upgrade`
  - Flags: `--json`, `--fix`, `--force`, `--dry-run`, `-l/--local`, `--enable`, `--disable`, `--set`,
    and `--scope=user|project` (default `user`).

| Command (sandboxed)                                                                  | rc  | Observed output / effect                                                                                                                     |
| ------------------------------------------------------------------------------------ | --- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `omp --version`                                                                      | 0   | `omp/18.12.3`                                                                                                                                |
| `omp plugin marketplace list` (also with `--json`)                                   | 0   | `No marketplaces configured` / `Configured Marketplaces:\n\n  ycc  <source>`. **`--json` is ignored** (text only)                            |
| `omp plugin list --json` (empty)                                                     | 0   | `{"npm": [], "marketplace": []}`                                                                                                             |
| `omp plugin marketplace add <export>`                                                | 0   | `✔ Added marketplace: <export>`. Registry `marketplaces.json` gets `sourceType: local`, `sourceUri`, `catalogPath`                           |
| same, repeated                                                                       | 1   | `✘ Failed to add marketplace: Error: Marketplace "ycc" already exists` (also when the existing `ycc` has a different source)                 |
| `omp plugin marketplace add --dry-run <export>`                                      | 0   | **mutates**: `✔ Added marketplace` and the registry is written                                                                               |
| `omp plugin marketplace add --scope project <export>` (in a project)                 | 0   | registers in the **user** registry; marketplaces have no project scope                                                                       |
| `omp plugin marketplace add <dir without catalog>`                                   | 1   | `Marketplace catalog not found at "<dir>/.omp-plugin/marketplace.json" or "<dir>/.claude-plugin/marketplace.json"`                           |
| `omp plugin marketplace add <this checkout>` (no `.omp-plugin/marketplace.json`)     | 0   | **falls back to `.claude-plugin/marketplace.json`**: `discover` lists Claude `ycc`, `ycc-mcp`, `ycc-hooks`, `ycc-all`                        |
| `omp plugin discover ycc`                                                            | 0   | `Available Plugins (ycc):\n\n  ycc@6.0.0\n    <description>`                                                                                 |
| `omp plugin install --dry-run ycc@ycc`                                               | 0   | `[dry-run] Would install ycc@ycc`; nothing written                                                                                           |
| `omp plugin install ycc@ycc`                                                         | 0   | `✔ Installed ycc from ycc (6.0.0)`; cache `plugins/cache/plugins/ycc___ycc___6.0.0` (a full copy), `node_modules/ycc` symlink, lock entry    |
| same, repeated                                                                       | 1   | `Plugin "ycc@ycc" is already installed. Use force option to reinstall.`                                                                      |
| `omp plugin install --scope project ycc@ycc` (in a git repo)                         | 0   | creates `<root>/.omp/plugins/{installed_plugins.json,omp-plugins.lock.json,node_modules/ycc}`; the cache stays shared in the user data root  |
| `omp plugin install --scope project --dry-run ycc@ycc` (cwd `$HOME`)                 | 1   | `project-scoped install requires running inside a project directory`                                                                         |
| `omp plugin list --json` (both scopes)                                               | 0   | entries `{"id":"ycc@ycc","scope":"project",...}` and a user entry with `"shadowedBy": "project"`; `enabled` appears once toggled             |
| `omp plugin disable ycc@ycc --dry-run` (both scopes)                                 | 1   | `installed in both user and project scope. Use --scope user or --scope project`                                                              |
| `omp plugin disable --scope user ycc@ycc`                                            | 0   | lock `"enabled": false`. The project entry still shadows                                                                                     |
| `omp plugin enable --dry-run --scope project ycc@ycc`                                | 0   | **mutates**: lock flips to `"enabled": true`                                                                                                 |
| `omp plugin marketplace update ycc`                                                  | 0   | `✔ Updated marketplace: ycc`. Re-reads the **source dir**; it fails if the source was deleted (`Marketplace catalog not found …`)            |
| `omp plugin upgrade --dry-run` / `upgrade --dry-run ycc@ycc` (after a lockstep bump) | 0   | **mutates**: `ycc@ycc (user): 6.0.1 -> 6.0.2` / `Upgraded ycc@ycc (user) to 6.0.8`, with a new cache and registry                            |
| `omp plugin upgrade` (version unchanged)                                             | 0   | `All marketplace plugins are up to date.`                                                                                                    |
| `omp plugin upgrade ycc@ycc` (no scope)                                              | 0   | upgrades **every** installed scope (`(project) … (user)`)                                                                                    |
| `omp plugin upgrade --scope user ycc@ycc`                                            | 0   | user scope only. **When run outside the project, the old cache that a project install links to is GC'd** and the project link dangles        |
| `omp plugin install --force ycc@ycc` (disabled)                                      | 0   | reinstalls and keeps `"enabled": false`; upgrade also keeps the disabled state                                                               |
| `omp plugin uninstall --scope project --dry-run ycc@ycc`                             | 0   | `[dry-run] Would uninstall ycc@ycc`; nothing removed                                                                                         |
| `omp plugin uninstall --scope project ycc@ycc`                                       | 0   | removes the project registry entry and link (empty files stay); the cache is kept while user scope uses it                                   |
| `omp plugin uninstall …` (not installed)                                             | 1   | `Plugin "ycc@ycc" is not installed in project scope` / `ycc@ycc is not installed`                                                            |
| `omp plugin marketplace remove ycc` (plugin installed)                               | 0   | removes the registry entry and catalog cache only. Installs stay; a later `install --force` fails (`Package "ycc" with tag "ycc" not found`) |
| `omp plugin link <export>/packages/omp/ycc`, then `install ycc@ycc`                  | 0/1 | the link appears under `"npm"`; the marketplace install fails: `Runtime package name "ycc" conflicts with installed package "ycc"`           |
| `OMP_PROFILE=work …` / `omp --profile work …`                                        | 0   | separate `~/.omp/profiles/work/{marketplaces.json,plugins/}`; `omp config path` → `…/profiles/work/agent`                                    |
| `mkdir $XDG_DATA_HOME/omp` (XDG opt-in), then the same commands                      | 0   | state moves to `$XDG_DATA_HOME/omp/{marketplaces.json,plugins/}`; `installPath` reflects it                                                  |
| `omp plugin doctor --json`                                                           | 0   | a JSON array of `{name,status,message}`; it did **not** flag the dangling project link                                                       |

### Upstream documentation

- [docs/marketplace.md](https://github.com/can1357/oh-my-pi/blob/main/docs/marketplace.md):
  - scopes, and enabled project installs shadow user installs;
  - a disabled project install does not shadow;
  - XDG and profiles;
  - `/reload-plugins` refreshes agents, skills, commands and MCP; a **restart** is needed for new tools,
    hooks and extension modules;
  - only CLI install and uninstall support `--dry-run`;
  - "Removing a marketplace … does not uninstall plugins";
  - `upgrade name@mkt` reinstalls every scope when `--scope` is omitted;
  - user and project share version-keyed cache dirs.
- [docs/plugin-manager-installer-plumbing.md](https://github.com/can1357/oh-my-pi/blob/main/docs/plugin-manager-installer-plumbing.md):
  - the plugin manager is not transactional;
  - there is no cross-process lock on `omp-plugins.lock.json`;
  - the `--dry-run` scope is install and link previews only.

## Business Requirements

### User Stories

- As an OMP user, I run `./install.sh install --target omp` once to get `/ycc:*` commands, `skill:*`
  skills and agents, and I re-run it after `git pull` to update in place.
- As a team member, I run `./install.sh install --target omp --project` inside a repo to pin ycc for that
  project only, and `remove --target omp --only base --project` to undo it.
- As a cautious user, I preview any change with `--dry-run` and see exactly which `omp` commands would run.
- As an early adopter who used `omp plugin link` or added the checkout as a marketplace by hand, I run
  `./install.sh migrate --target omp` (preview), then `--apply`, to end up with one clean ycc install.

### Business Rules (acceptance criteria → rules)

1. **Idempotent.** A re-run with nothing changed makes no mutating `omp` call. It also skips
   `marketplace update` when the export bytes are unchanged.
2. **Ownership.**
   - `remove` acts only on entries recorded in the state file. That covers the marketplace registration,
     each `<pkg>@ycc` install per profile, scope and project, and the export directory.
   - Pre-existing registrations or installs are never claimed. This is the codex precedent.
3. **User data preserved.**
   - The helper never edits `omp-plugins.lock.json`, `marketplaces.json` or `installed_plugins.json` directly.
   - Disabled state survives update. Reinstall and upgrade preserve it, which was verified.
   - It never re-enables a plugin the user disabled.
   - Foreign marketplaces and plugins are untouched.
4. **No duplicates.**
   - It never adds a second marketplace and never installs while a `ycc` link or a foreign `ycc`
     marketplace exists. It refuses with a migrate hint instead.
   - `migrate` retires only proven ycc-owned legacy state.
5. **Scope.** `--global` (default) maps to `--scope user` and `--project` maps to `--scope project` at
   `project_root`. Every scoped `omp` call passes `--scope` explicitly (both-scope ambiguity errors).
6. **Packages.**
   - The default set is every `included` native omp row in `ycc/settings/packages.json` (today: `ycc`).
   - `--package` selects a subset through `package_install_plan.py`.
   - Deferred and excluded rows (`ycc-mcp`, `ycc-hooks`, `ycc-rules`, `ycc-all`) are rejected with the model's reason.
7. **Native only.** There is no file-copy fallback for omp. `installer-fallback` stays deferred (YAN-1175).

### Edge Cases

| Case                                                       | Required behaviour                                                                                                                   |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `omp` missing or `< 18.12.2`                               | explicit `--target omp`: error before any target runs; `--target all`: warn and skip omp                                             |
| `ycc` marketplace exists with a foreign source             | refuse before mutating: "marketplace ycc has a different source; retained (run migrate --target omp or remove it)"                   |
| `ycc` runtime link (`omp plugin link`) present             | refuse: runtime-name conflict; migrate hint                                                                                          |
| `--project` with cwd = `$HOME`                             | refuse in preflight (omp would error)                                                                                                |
| install fails after this run added the marketplace         | roll back: `marketplace remove ycc`, restore the previous export dir, leave state as it was before the run                           |
| upgrade fails mid-way                                      | report `[err]`; recorded versions stay as before; omp's own state is untouched by ycc ([INFERENCE] omp leaves the previous install)  |
| user-scope upgrade GC'd a recorded project install's cache | after every user-scope mutation, check each recorded project `installPath`; warn with the exact repair command                       |
| package disabled at project scope                          | update upgrades it but leaves it disabled and reports "disabled at project scope: kept"                                              |
| `OMP_PROFILE` / XDG data root differs between runs         | state is keyed by profile identity (`omp config path`); entries for other profiles are never touched                                 |
| export dir exists but is unrecorded                        | refuse to overwrite (not ycc-owned)                                                                                                  |
| `remove` with no state                                     | `nothing ycc-owned to remove for omp`, exit 0                                                                                        |
| `--mode repo` while no omp row is listed                   | `omp_supports_repo_mode` is false; explicit: error "needs a listed OMP package (YAN-1180)"; `all`: skipped with the existing warning |

### Success Criteria

- `./scripts/validate.sh` passes with new hermetic tests covering install, update, remove, migrate and
  dry-run × each included package × {user, project}, plus rejection tests for every non-included omp row.
- The opt-in live harness `scripts/test-omp-install-lifecycle.sh` passes against real omp 18.12.3.

## Technical Specifications

### Architecture Overview

```text
install.sh (args: --target omp, --project|--global, --package, --dry-run, --force, --mode)
  └─ steps.sh resolve_targets / preflight (omp availability, repo-mode, --project allowed for omp base)
       └─ targets/omp.sh  sync_omp_target / remove_omp_target   (step: base only)
            └─ python3 scripts/omp_install.py {install|remove|plan|listed|available}
                 --packages CSV --scope user|project --project-root DIR --mode local|repo [--dry-run] [--force]
                 ├─ export: generate_omp_packages.py --export <staging>; validate_omp_native.py --export; atomic swap
                 ├─ omp CLI (read): --version, config path, plugin list --json, plugin marketplace list
                 ├─ omp CLI (mutate): marketplace add|update|remove, plugin install|upgrade|uninstall --scope S
                 └─ state: ~/.config/ycc/omp-native-install.json
install.sh migrate --target omp [--apply] → install_migrate.py Migration.omp() (uses omp_install API)
```

### Data Models — `~/.config/ycc/omp-native-install.json`

```json
{
  "version": 1,
  "export": "~/.local/share/ycc/omp-marketplace (absolute)",
  "export_inventory": { "<rel>": ["sha256", false] },
  "profiles": {
    "<omp config path output>": {
      "marketplace": { "name": "ycc", "source": "<absolute export dir or https://github.com/yandy-r/ystack.git>" },
      "installs": [
        {
          "package": "ycc",
          "scope": "user",
          "project_root": null,
          "version": "6.0.0",
          "cache_root": "<…/plugins/cache/plugins>"
        },
        { "package": "ycc", "scope": "project", "project_root": "/abs/repo", "version": "6.0.0", "cache_root": "<…>" }
      ]
    }
  }
}
```

- The profile key is `omp config path`, which is profile-aware (`…/profiles/<name>/agent`). It is not a
  hard-coded data path. `cache_root` is derived from the `installPath` reported by `plugin list --json`,
  so the XDG and profile relocations come from omp.
- Writes are atomic (`merge_managed_config.atomic_write`) and the path is guarded against symlinks (the
  `codex_install.guarded` pattern). The state is saved **before** each mutating CLI call that creates
  something new (codex precedent: record ownership first), and is pruned only after a verified removal.
- `export` lives under `${XDG_DATA_HOME:-~/.local/share}/ycc/omp-marketplace`. It must persist, because
  `marketplace update` and `install --force` read the source dir (verified).

### API Design (command mapping)

| install.sh                                       | omp calls (only when needed)                                                                                                                                                                                                                                |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `install --target omp [--package P] [--global]`  | export (skipped if unchanged); `plugin marketplace add <export>` if absent, else `plugin marketplace update ycc` if the export changed; per package: `plugin install --scope user P@ycc` if absent, or `plugin upgrade --scope user P@ycc` if older         |
| `… --project`                                    | same with `--scope project`, cwd = `project_root`                                                                                                                                                                                                           |
| `… --force`                                      | `plugin install --force --scope S P@ycc` for owned installs (cache repair; shared cache affects both scopes; this is printed)                                                                                                                               |
| `… --mode repo`                                  | `plugin marketplace add https://github.com/yandy-r/ystack.git` (no export); allowed only when an omp row is listed                                                                                                                                          |
| `install/sync/remove … --dry-run`                | read-only queries plus `plugin install --dry-run` / `plugin uninstall --dry-run`; every other step prints `would …`. **Never** `upgrade`, `enable` or `marketplace add` with `--dry-run`                                                                    |
| `sync --target omp --intent base` (or `plugins`) | same as install. Intents `skills/agents/commands/settings/rules/mcp/hooks/mods` map to no step (the native package is indivisible; settings/rules are YAN-1175) and are skipped with the standard "not supported by target" warning                         |
| `remove --target omp --only base [--project]`    | per recorded install in that scope: `plugin uninstall --scope S P@ycc`; when no recorded install remains in the profile: `plugin marketplace remove ycc` (if recorded and source unchanged), delete the export dir if no profile references it, prune state |
| `migrate --target omp [--apply]`                 | see Migration                                                                                                                                                                                                                                               |

After any mutation the helper prints the reload rule. A running session should run `/reload-plugins`
for skills, commands, agents and MCP. It must restart when a selected package ships hooks or extensions
(computed from package-model components; for `ycc` today only `/reload-plugins` applies). Project
installs print the shadowing note: "a project install shadows your user install here; `omp plugin
disable --scope project ycc@ycc` returns to the user copy".

### Migration (`install_migrate.py Migration.omp`) — dry-run by default

| Legacy / fallback state                                                                                     | Proof of ownership                                                                                | Action (`--apply`)                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `omp plugin link` of `packages/omp/<pkg>` (`"npm"` entry with a ycc package name)                           | the link `path` resolves inside `ROOT/packages/omp/<pkg>` or the recorded export                  | `omp plugin uninstall <name>`; reports "run install --target omp"                                                                                                        |
| `ycc` marketplace registered at this checkout root (Claude-catalog fallback), with `*@ycc` installs from it | the source equals `ROOT`, and the installed root lacks `.omp-plugin/plugin.json` (Claude dialect) | uninstall each affected scope that is reachable (user; project for cwd root), `marketplace remove ycc`, then the normal install into the same scopes (recorded as owned) |
| foreign `ycc` marketplace (fork URL or other dir) or a foreign link                                         | none                                                                                              | kept; `[!!] kept … foreign`                                                                                                                                              |
| ycc skills in `~/.agents/skills` (agents target), loaded by OMP by default                                  | reported only                                                                                     | **not deleted** (other tools read that dir); prints the overlap count and `remove --target agents --only base` guidance. Dedupe policy belongs to YAN-1176               |

The whole selection is preflighted before any `--apply` mutation (existing `install_migrate.py` rule).
A re-run after apply is a no-op.

### Files to create

- `scripts/omp_install.py`: helper (mypy strict).
- `scripts/lib/install/targets/omp.sh`: target contract.
- `scripts/tests/install/fake_omp.py`: a stateful fake `omp` that emulates the 18.12.3 quirks above,
  logs every call and supports failure injection.
- `scripts/test_omp_install.py`: unittest matrix.
- `scripts/tests/install/omp.sh`: install.sh-level suite.
- `scripts/test-omp-install-lifecycle.sh`: opt-in live harness against real omp.
- `docs/install/omp.md`.

### Files to modify

- `install.sh`: `ALL_TARGETS`, `--dry-run`, usage.
- `scripts/lib/install/steps.sh`: `all` skip hook, generic repo-mode skip text, `--project` for omp base,
  `--dry-run` preflight.
- `scripts/lib/install/core.sh`: `step_allows_project`.
- `scripts/lib/install/migrate.sh`: omp target.
- `scripts/completions/{ycc.bash,_ycc,ycc.fish}`.
- `scripts/package_install_plan.py` and `scripts/test_package_install_plan.py`: `TARGETS` and `CARRIERS["omp"]`.
- `scripts/install_migrate.py`.
- `scripts/test-install-sync.sh` and `scripts/tests/install/{core,packages}.sh` as needed.
- `scripts/validate.sh`: config helpers.
- `scripts/lib/validate-scope.sh` and `scripts/test-validate-scope.sh`.
- `pyproject.toml`: mypy `files`.
- `ycc/settings/packages.json`: `ycc`/omp notes; drop the satisfied YAN-1172 gate on `installer-fallback`/omp.
- `ycc/skills/_shared/references/target-capability-matrix.md`: `INSTALL_PATH:omp` → `partial`, plus prose.
- `docs/install/README.md`, `README.md`, `AGENTS.md`, `CONTRIBUTING.md`.

## UX Considerations

### User Workflows

- **Primary workflow:** `./install.sh install --target omp` prints:
  - `[ok] exported OMP packages → <dir>`
  - `[ok] omp plugin marketplace add <dir>`
  - `[ok] omp plugin install --scope user ycc@ycc`
  - `[ok] ycc@ycc 6.1.0 installed (user)`
  - the reload line.

  A re-run prints `[ok] ycc@ycc 6.1.0 up to date (user)` and no mutating commands.

- **Preview:** `--dry-run` prints `would run: omp …` for every planned mutation and runs omp's own
  install/uninstall `--dry-run` as validation. The exit code is 0 when the plan is valid and 2 when
  preflight would refuse.
- **Errors:** they reuse the codex wording: `[err] native OMP install stopped: <reason>` with exit 2,
  and every refusal names the command that resolves it.
- **No interactive prompts.** OMP has no trust prompt, so docs and output state that installed plugin
  code runs with full user privileges (ADR 0002 §6).

## Recommendations

### Implementation Approach

- **Approach:** mirror `codex_install.py` structure, output prefixes and ownership-before-mutation
  ordering. Keep the shell target thin, with all logic in the tested Python helper.
- **Technology decisions:**
  - Python stdlib only, typed under `mypy --strict`.
  - Reuse `generate_omp_packages` (`MIN_OMP_VERSION`, export) and `validate_omp_native` (export check).
  - Reuse `merge_managed_config.atomic_write`, `package_model.load_package_model` and
    `package_install_plan.plan_install`.
- **Future:**
  - YAN-1173–1175 flip rows to `included`, and the installer picks them up with no code change. The
    table-driven tests cover them automatically.
  - YAN-1180 lists the rows, which turns on `--mode repo` and inclusion in `--target all`.

## Risk Assessment

### Technical Risks

| Risk                                                                                  | Mitigation                                                                                                                  |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| omp `upgrade`/`enable`/`marketplace add` ignore `--dry-run` (verified)                | the helper owns dry-run; the fake reproduces the quirk and tests assert those verbs never run in dry-run                    |
| A user-scope upgrade GCs caches of project installs elsewhere (verified upstream bug) | post-mutation dangling check over recorded projects, with a repair hint; report upstream                                    |
| `marketplace list` has no JSON output; text parsing is brittle                        | strict regex over `^  (\S+)  (.+)$` under `Configured Marketplaces:`; unparseable output fails closed                       |
| Non-transactional omp state, no cross-process lock                                    | ownership recorded before mutation; rollback of this run's marketplace add; no concurrent ycc runs ([INFERENCE] acceptable) |
| The checkout falls back to the Claude catalog while unlisted                          | never register the checkout root; always use the export; migrate retires a checkout-root registration                       |
| Future omp output/schema changes                                                      | version floor check; opt-in live harness pinned to the tested version; fail closed on unknown JSON shapes                   |

### Security Considerations

- **Critical:** none.
- **Warning:**
  - Installing grants the plugin full user privileges with no prompt. The docs and success output say so.
  - The export dir must not be world-writable or a symlink. Use the `guarded()` check and umask 077 for
    the state file.
- **Advisory:** pass the omp argv as a list and never through a shell. Package names come only from the
  model.

## Task Breakdown Preview

1. **Core (parallel):** `omp_install.py`, `fake_omp.py`, the planner (`package_install_plan.py`) and
   `targets/omp.sh`.
2. **Wiring and consumers:** `install.sh` and the shell libs (`--dry-run`, project allowance, `all` skip,
   migrate), `install_migrate.py` omp, and `test_omp_install.py`.
3. **Tests, CI and docs:** the install suite, validate and scope wiring, the live harness, docs and the
   model/matrix flips.
4. **Gate:** `./scripts/sync.sh`, `./scripts/validate.sh`, and the live harness.

## Decisions (resolved; rationale)

| #   | Decision                                                                                                                                                                                              | Rationale                                                                                                                                                  |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Target name `omp`, one step `base`. Contract: `omp_valid_steps`=`base`, `omp_supports_repo_mode` = an omp row is listed, `omp_reads_agents_skills` returns 1                                          | The native package cannot drop its skills, so the `~/.agents/skills` consolidation flow cannot apply; dedupe is reported by migrate (YAN-1176 owns policy) |
| D2  | Local mode installs from a ycc-owned export dir (`generate_omp_packages.py --export`), never the checkout root                                                                                        | The checkout has no OMP catalog until listing and omp then reads the Claude catalog (verified); the source dir must persist for update and force           |
| D3  | Unlisted included rows install from a checkout with a pre-release notice                                                                                                                              | `listed` governs the public catalog (YAN-1171 D4); explicit local installs are the pre-release path, matching the export harness                           |
| D4  | `--target all` includes omp only when omp ≥ floor is on PATH **and** an omp row is listed; otherwise it skips with an info line. An explicit `--target omp` errors when omp is missing                | No regression for existing `all` users; a hidden package is never installed implicitly                                                                     |
| D5  | `--dry-run` is a new install.sh flag for install, sync and remove, accepted only when every resolved target is `omp`                                                                                  | Other targets have no preview; a flag silently ignored by some targets is unsafe                                                                           |
| D6  | Default scope is user. `--project` is allowed for omp `base` through a new `step_allows_project`, while `step_supports_project` (the default-to-project rule) stays mcp-only                          | Matches omp's default and keeps every other target unchanged                                                                                               |
| D7  | The ownership state file follows the codex precedent: never claim pre-existing items; record before mutating; remove only recorded and still-matching items                                           | The "removal deletes only ycc-owned state" acceptance criterion                                                                                            |
| D8  | Update = re-run `install`. No new subcommand                                                                                                                                                          | Matches every other target; `upgrade --scope S` only for owned, older installs                                                                             |
| D9  | Never expose enable or disable. Respect the user's choice and document `omp plugin disable --scope project` as the per-project switch                                                                 | ADR 0002; upgrade and force preserve disabled state (verified); re-enabling would overwrite user intent                                                    |
| D10 | Rollback covers only what this run created (the marketplace add and the export swap). There is no compensating uninstall of pre-existing items                                                        | omp is non-transactional; safe partial-failure semantics without touching user state                                                                       |
| D11 | `migrate --target omp` handles link and checkout-root registrations and only **reports** `~/.agents/skills` overlap. `migrate --target all` stays claude, codex, cursor and adds an info hint for omp | Deleting shared skills would break other tools; YAN-1176 owns cross-tool dedupe                                                                            |
| D12 | Tests: a stateful fake `omp` (hermetic, in CI) plus an opt-in live harness (not in CI)                                                                                                                | Same split as YAN-1171 (`test_codex_install.py` fake plus the opt-in live harness)                                                                         |

## Decisions Needed

None block implementation. To confirm at review (reversible):

- **D4:** whether `--target all` should include omp before listing (YAN-1180).
- **D11:** whether `migrate --target omp` should delete proven-owned `~/.agents/skills` copies when no
  other selected target reads them. Proposed: no; this belongs to YAN-1176.

## Research References

- Live probe transcript: commands and outputs in the table above (sandbox `/tmp/omp1172.*`, removed).
- Codebase map: `install.sh`, `scripts/lib/install/**`, `scripts/codex_install.py`,
  `scripts/install_migrate.py`, `scripts/package_install_plan.py`, `scripts/tests/install/lib.sh`,
  `scripts/test-omp-native-packages.sh`.
- Upstream: `docs/marketplace.md` and `docs/plugin-manager-installer-plumbing.md` (can1357/oh-my-pi, main).
