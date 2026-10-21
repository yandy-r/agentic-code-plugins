# YAN-922: `--commands` selection for the commands intent

Linear: YAN-922 (parent YAN-918). GitHub: #413. Target release: `ystack v6.1.0`
(trunk-only, `tracker: none`; no backport). Builds on YAN-919 (#405) and
YAN-920/921 (#410).

## Research summary (current tree, `main` @ 3e19a9d4)

| target             | commands step | source → destination                                                      | mechanism                                                                                                                           |
| ------------------ | ------------- | ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| claude             | yes (alias)   | `ycc/skills/<n>` → `~/.claude/skills/<n>`                                 | `install_slices.py` maps `commands` → `skills` on install; `remove` only retires recorded legacy `~/.claude/commands/*.md` wrappers |
| cursor             | yes           | `packages/cursor/ycc/commands/<n>.md` → `~/.cursor/commands/<n>.md`       | strict carrier (`strict_unit`): byte hashes, fail-closed ownership, every command references `<skills-home>/<n>/SKILL.md`           |
| opencode           | yes           | `.opencode-plugin/commands/<n>.md` → `~/.config/opencode/commands/<n>.md` | plain unit; each file loads skill `<n>`                                                                                             |
| codex, agents, omp | no            | —                                                                         | `valid_steps` lacks `commands`                                                                                                      |

All 49 commands pair 1:1 with a public skill of the same name on every target.

Selection plumbing to reuse: `scripts/lib/install/select.sh` (kind registry,
preflight, `ycc list`), `run_slice <t> <slice> select` (`bundle.sh`),
`scripts/slice_selection.py` (`plan_run`, `plan_selection`, `Availability`,
`print_dependency_warnings`), `install_slices.py list|install|remove --entries`.
Completions (`scripts/completions/*`) read kinds and names through `ycc list`.

## Decisions

1. **Claude `--commands` narrows the skills slice** (commands are skills there).
   When both `skills` and `commands` steps run on claude, the slice runs once with
   the union of the kinds that carry a selection; a kind without a selection does
   not widen it (keeps today's `--intent skills,commands --skills a` → only `a`);
   neither selected → whole slice. Dependency warnings stay the skills warnings.
2. **Claude selective install does not retire legacy wrappers** (unchanged
   YAN-920 decision). **Claude `remove --intent commands --commands a`** retires
   only the recorded legacy wrapper `a.md`; unknown names exit 1.
3. **Cursor strict carrier narrows** to the picked entries: ownership/hash checks
   and the missing-skill fail-closed check apply to picked entries only; state and
   hashes merge (unselected owned entries untouched, never pruned); selective
   remove takes back only picked owned entries. The carrier dry-run preflight
   receives the same `--entries`.
4. **Cursor `--skills` with the commands step** is allowed only when `--commands`
   is given and every selected command cursor ships is in the cursor `--skills`
   selection; otherwise `cursor_preflight` rejects before any target writes (keeps
   "nothing written before an error"). Hint names the fix.
5. **Paired-skill warning** (opencode; claude is the skill itself, cursor fails
   closed): after a clean selective opencode commands install, for each selected
   command whose skill `Availability.has("skills", n)` is false, print
   `[!!]  opencode: command '<n>' needs skill '<n>', not installed — add it: ycc sync --target opencode --intent skills --skills <n>`.
   Sources counted: standalone/`base` mirror on disk or recorded in state,
   `~/.agents/skills/<n>`, `YCC_PENDING_SKILLS` from the same run. Never
   auto-installs, never fails the run. One helper in `slice_selection.py`.
6. Targets without a commands step skip `--commands`; preflight errors only when
   no selected target runs a commands step (existing `preflight_selections`).

## Tasks

1. `select.sh`: register `commands` (`SELECTION_STEP=commands`, nouns, hint,
   `commands_names` → `install_slices.py list --slice commands`). Update header.
2. `bundle.sh` `run_slice`: claude skills/commands union (decision 1); pending env
   for `commands` slice sets `YCC_PENDING_SKILLS` (skills step on the target).
3. `claude.sh`: run the alias with the right kind; `remove` path unchanged
   (`remove_slices` already passes `select`).
4. `cursor.sh`: `run_slice cursor commands select`; carrier dry-run passes
   `--entries` (skip when the selection names none for cursor);
   `cursor_preflight` per decision 4.
5. `install_slices.py`: `strict_unit(..., pick)`; drop the strict rejection in
   `plan_run` for commands (hooks never gets `--entries`); claude commands remove
   with `--entries` → validate + retire only those wrappers; opencode paired-skill
   warnings. Keep new logic in `slice_selection.py` where possible (file sizes).
6. `install.sh` usage/help (`--commands`, cursor `--skills` note);
   `docs/install/README.md` selection section and cursor note.
7. Tests: `scripts/test_install_slices_select.py` (strict pick install/remove,
   claude wrapper retire subset, paired-skill warning: absent / standalone /
   base mirror / `~/.agents/skills` / pending) and
   `scripts/tests/install/slices-select.sh` (list per target, codex-only error,
   claude/opencode/cursor narrowing, cursor subset preflight).
