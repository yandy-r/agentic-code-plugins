# YAN-1292 + YAN-1293: `--with-deps` closure and the `install_slices.py` split

Linear: YAN-1292 (parent YAN-918), YAN-1293. GitHub: #428, #429. Target release:
`ystack v6.1.0` (trunk-only, `tracker: none`; no backport).

## Verified facts (2026-10-22)

- `scripts/install_slices.py` is 546 lines. `scripts/slice_selection.py` is 355 lines and
  holds both selection planning and the dependency-warning code (`References`,
  `Availability`, `dependency_warnings`, `paired_skill_warnings`).
- Warnings run only after a clean selective install (`print_dependency_warnings`), using
  `YCC_PENDING_SKILLS` / `YCC_PENDING_AGENTS` set by `run_slice` (`scripts/lib/install/bundle.sh`)
  from `selection_for_target`.
- The `ycc:` reference graph is dense: the closure of `code-review` is 41 units (12
  agents, 29 skills). `implementor` references nothing.
- `run_target` (`scripts/lib/install/steps.sh`) already saves and restores per-target
  state (`ONLY_STEPS`) around the target function; per-target selection expansion fits
  there.

## Design

### Semantics

- `--with-deps` is valid on `install` and `sync` only (error on `remove`), and only with
  `--skills` or `--agents` (error otherwise: `--with-deps needs --skills or --agents`).
- Per target, before the target runs, the seeds are the `--skills` / `--agents` names that
  target ships. The closure walks `ycc:<name>` references transitively (the existing
  `References.of` / `References.kinds` rules, including `/ycc:<name>` = skill).
- It extends only kinds that **already have a selection** and whose step runs on that
  target (claude: the skills slice runs for the skills or commands step). A kind without
  a selection already ships whole, so nothing changes for it. A kind whose step does not
  run is never enabled; its references keep warning. Narrowing, never widening steps.
- A reachable unit is added when the target ships it and it is not already available,
  or when ycc owns it in `installed-units.json` (so a sync refreshes it). It is skipped
  when it is available from elsewhere (installed ycc plugin, a foreign/user-owned entry,
  `~/.agents/skills` for readers). This never makes a run conflict on a user's own entry.
- Names the target does not ship are skipped; the post-install warning still names them.
- Each target prints what was added: `<target>: --with-deps adds skills: a, b` (and agents).
- The expansion is per target and restored after it: other targets see the original
  selection. Preflight validates the user's original names only.
- Without `--with-deps`, nothing changes (warn only).
- The dispatcher-only agent warning (an agent used only by a skill) is not resolved by
  `--with-deps`: a dispatcher is a reverse edge and picking one would be a guess.

### Python

- New `scripts/slice_deps.py` (mypy strict): move `References`, `Availability`,
  `dependency_warnings`, `paired_skill_warnings`, `print_dependency_warnings` out of
  `slice_selection.py`, and add `closure(...)` plus `print_closure(...)`.
- `install_slices.py closure --target T [--skills CSV] [--agents CSV]`: prints one line per
  passed kind, `<kind>\t<added csv>` (empty csv when nothing is added). Unknown names are
  ignored (preflight already validated them). Read-only: no state is written.
- YAN-1293: new `scripts/slice_carriers.py` (mypy strict) with `entry_hash`, `strict_unit`
  (with its missing-skill check) and `retire_legacy_commands`. `install_slices.py` ends at
  ≤ ~500 lines. No behavior change.
- Add `slice_selection.py`, `slice_deps.py`, `slice_carriers.py`, `install_slices.py` and
  `test_install_slices_select.py` to `[tool.mypy].files`; add the new modules to the
  `scripts/lib/validate-scope.sh` `config` case.

### Shell

- `install.sh`: `--with-deps) WITH_DEPS=1`, validation (remove; no selection), usage line
  for install and sync, option reference entry, an example.
- `select.sh`: `expand_with_deps <target>` called from `run_target` after intent mapping,
  saving and restoring `SELECTION[skills]` / `SELECTION[agents]`.
- Completions: `--with-deps` for install and sync in `ycc.bash`, `_ycc`, `ycc.fish`.

### Docs

- `docs/install/README.md` selection section: `--with-deps`, its per-target and
  existing-selection-only rules, and the example from the acceptance criteria.

## Tests (critical only)

- `scripts/test_install_slices_select.py`:
  - `closure` for claude `--skills code-review --agents implementor` adds `code-reviewer`
    and `review-fix`; a second run after installing them adds nothing that is foreign.
  - a user-owned (unrecorded) skill on disk is not added; a ycc-owned one is.
  - with the ycc plugin recorded, nothing is added.
- `scripts/tests/install/slices-select.sh`:
  - `sync --target claude --intent skills,agents --skills code-review --agents implementor --with-deps`
    installs `code-review`, `code-reviewer` and `review-fix`, and prints no `[!!]`.
  - `sync --target claude --intent skills,agents --skills code-review --with-deps` (agents
    whole) prints no dependency warning.
  - without `--with-deps` the warning is unchanged.
  - `remove … --with-deps` and `sync … --with-deps` without a selection are rejected.

## Decisions

| decision                                                               | why                                                                              |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Extend only kinds that already have a selection                        | Narrowing contract: `--with-deps` never turns a step on or a whole slice partial |
| Skip deps available elsewhere unless ycc owns them                     | Never conflict with or overwrite a user-owned entry; owned deps still refresh    |
| Per-target expansion, restored after                                   | Closure differs per target (what it ships, what is installed)                    |
| No dispatcher resolution                                               | Reverse edge; choosing a dispatcher skill would be a guess                       |
| `install`/`sync` only                                                  | Removing dependencies others may use is destructive                              |
| Split warnings into `slice_deps.py`, carriers into `slice_carriers.py` | Keeps every touched module ≤ ~500 lines (YAN-918, YAN-1293)                      |
