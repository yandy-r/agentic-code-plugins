# Engineering practices: reuse, modularity, KISS

## Executive Summary

Reuse the managed-config merge, the slice ledger, the existing harness shape and the connection-key mirror. Add only two pure functions and one CLI subcommand, and delete the old warning helper.

## Existing Reusable Code

| Need                                                            | Reuse                                                                                                                                                                            | Why not new code                                                                                                                                                 |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Write and remove OMP config entries with user-edit safety       | `merge_managed_config.py` `omp-config` profile, YAML branch, `list-union` policy with `ADDED_ITEMS_KEY` ownership and `plan_list_removals`                                       | Already handles symlink refusal, YAML 1.2, backup, dry-run, owned-only removal and empty-file deletion. YAN-1175 built it for this file                          |
| Know which `~/.agents` / `~/.codex` / opencode skills are ycc's | `install_slices.state_path()` / `load_state()` (`installed-units.json`)                                                                                                          | It is the ownership ledger the slice installer already writes. No content hashing or heuristics                                                                  |
| OMP package skill names                                         | `omp_install.agents_overlap` logic (`packages/omp/<pkg>/skills/*/SKILL.md`)                                                                                                      | Generalize it into `coexistence_plan()`; delete `warn_agents_overlap` (clean cutover)                                                                            |
| Shell plumbing                                                  | `merge_settings_config`, `omp_agent_dir`, `omp_config_dest`, `config_groups_for_target` (`targets/omp.sh:120-160`)                                                               | The `settings` step already wires these exact calls                                                                                                              |
| Live sandbox                                                    | `test-omp-native-packages.sh` / `test-omp-install-lifecycle.sh` shape (bwrap, env -i, null model, export marketplace, `--ro-bind "$repo"`), `omp_native_smoke.py` check dispatch | Same isolation guarantees; the new harness only adds cases                                                                                                       |
| MCP connection identity                                         | `omp_native_smoke.connection()` mirrors `isSameMCPConnection`                                                                                                                    | Move the key function into `generate_omp_packages.py` (`mcp_connection_key`) and import it in the smoke script. One definition for the generator and the harness |
| Overlap message from the agents target                          | `agents_duplicate_hint` (`targets/agents.sh:61-78`)                                                                                                                              | Extend that hint with a call to `omp_install.py coexistence --warn`; no new hook point                                                                           |

## Modularity

- `omp_install.py` gains one public function, `coexistence_plan(packages) -> CoexistencePlan`
  (a dataclass of entries, owned overlaps, unowned names and claude overlap), plus two thin CLI
  subcommands: `coexistence --emit PATH`, and `coexistence --warn [--if-installed]`.
- No shell-side scanning: the shell only calls the helper and the merge.
- `generate_omp_packages.py` gains `mcp_connection_key(server)` and `omp_mcp_bytes(source)`. These are
  pure functions, and they are unit-tested without the filesystem.
- The validator compares against `omp_mcp_bytes(source)`. It does not duplicate the transform.

## KISS decisions

- Use `skills.ignoredSkills` aliases instead of deleting files or editing per-skill
  `disabledExtensions`. Glob entries on the alias self-heal, which removes any "re-enable" code path.
- Do not add opencode command dedupe. Its only lever (`slash-command:<name>`) hides user commands too,
  so it fails BR2. The duplicates only appear under the explicit `*`/`opencode` opt-in, and the docs
  cover them.
- Do not add a hostile-repo wrapper or alias. Document the two flags and test them. A ycc-installed
  `omp` alias would be a new executable surface and a second convention.
- For YAN-1291, add one generator transform and no source change. Keep `mcp-configs/mcp.json` as the
  single source for every runtime.

## Testability

- **Hermetic.** These run in CI (`validate.sh` config/install-sync, `test-install-sync.sh`):
  - `test_omp_install.py` (fake omp; `config get` added);
  - `test_merge_managed_config.py` (dedupe group);
  - `test_generate_omp_packages.py` (transform plus validator);
  - `scripts/tests/install/{omp,agents}.sh`.
- **Live.** `test-omp-coexistence.sh` is opt-in and not in CI, like the other `test-omp-*` harnesses.
  It is wired in `validate-scope.sh` so a change selects the `omp` scope.
- **Snippet length.** Keep plan and test snippets to 5 lines. Patterns are listed in the plan.

## Anti-patterns to avoid

- Calling `omp config set skills.ignoredSkills` from the installer. It replaces the array, so user
  items are lost and ownership cannot be taken back.
- Hard-coding the 49 skill names. Derive them from `packages/omp/*/skills`.
- Adding `requestIdFormat` to `mcp-configs/mcp.json`. Plugin `.mcp.json` drops it (live), and other
  runtimes may reject unknown keys.
- Using a trailing-slash URL for YAN-1291. Linear advertises a different RFC 8707 resource (`…/mcp/`)
  for it.
