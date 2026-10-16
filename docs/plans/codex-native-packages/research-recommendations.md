# Codex native packages: recommendations

## Executive Summary

Implement YAN-1131 / GitHub #300 as **one preparatory PR for v6.0.0**. The PR adds deterministic generation of the native Codex `ycc` and `ycc-mcp` packages and the future `ycc` repository catalog, adds validator and lifecycle coverage, and proves both installs with an opt-in hermetic Git-fixture harness. It does **not** perform the production catalog cutover or change what `install.sh` installs.

The package contract is already settled in `ycc/settings/packages.json`:

- Codex `ycc` has components `skills` and `shared` (`26–42`).
- Codex `ycc-mcp` has the single component `mcp` (`84–97`).
- Codex `ycc-hooks` has `status: "excluded"` (`140–156`).

Both included packages are `listed: false`. Generators must use the existing validated loader, `scripts/package_model.py:261–267`, and must not parse the manifest a second way.

**Two live surfaces must stay byte-compatible until the flip:**

1. **The discovered catalog.** `.agents/plugins/marketplace.json:1–20` already exists. It contains marketplace `local-ycc-plugins`, plugin `ycc`, and local source `./plugins/ycc`, and `scripts/generate_codex_plugin.py:70–90` generates it. Codex reads this path before `.claude-plugin/marketplace.json` (`docs/internal/spikes/codex-marketplace.md:10–15`). Renaming it to `ycc`, even with zero entries, changes discovery today. A dot directory, an empty catalog, or a source-only `listed: false` flag does not hide that change.
2. **The installer payload.** `.codex-plugin/ycc` is what the installer uses: `scripts/lib/install/targets/codex.sh:10` reads it, local mode regenerates it (`268–280`), and repo mode installs it through a `git-subdir` at `./.codex-plugin/ycc` (`scripts/codex_marketplace.py`). Its manifest declares `mcpServers`, and generation copies `.mcp.json` into it (`generate_codex_plugin.py:47–48,120–122`). Splitting MCP out of that root in place would change what current users install.

**Recommended design (Main's direction, endorsed with refinements):**

- **Default generation** keeps the legacy `.codex-plugin/ycc` and the legacy discovered catalog unchanged while the model has `listed: false`. It may additionally generate the new, unlisted `.codex-plugin/ycc-mcp` payload. No catalog references that payload yet.
- **An explicit `--native-output DEST` mode** on `generate_codex_plugin.py` writes the complete future repo-shaped tree into a separate, dedicated, non-repository root:
  - `.codex-plugin/ycc`: skills and shared only.
  - `.codex-plugin/ycc-mcp`: MCP only.
  - `.agents/plugins/marketplace.json`: catalog named `ycc`.
- The native skills come from `ycc/` through the existing skill generator's `generate_codex_skills.write_tree(dest_root, dry_run)` (`143–217`). Nothing is copied from already-generated output, and no second full skill tree is kept under `packages/codex`.

This follows RELEASING.md "Unfinished work" (`55–61`): anything users could reach stays unwired and off by default.

One correction to the direction: the reusable skills API is `write_tree`, not `write_all(dest)`. `write_all(dest_root, dry_run)` exists only in the metadata generator (`generate_codex_plugin.py:103–125`). Native export should import and call `write_tree` in the same process. It should not shell out to `scripts/generate-codex-skills.sh`, because that wrapper always writes to `PLUGIN_ROOT` (`generate_codex_skills.py:262–283`).

This document is research only. No generator, validator, installer, or live Codex command was run for it. Spike observations are historical evidence, not new verification.

## Implementation Recommendations

### 1. Output surfaces

| Surface                                                 | Default `sync.sh --only codex` (all `listed:false`)                 | `--native-output DEST` (opt-in)                                        | After `ycc.codex.listed=true` (listing PR)                   |
| ------------------------------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| `.codex-plugin/ycc`                                     | Legacy bundle, unchanged: skills, shared, `.mcp.json`, `mcpServers` | `DEST/.codex-plugin/ycc`: skills and shared only, no MCP keys or files | Native skills/shared bundle generated in the repo            |
| `.codex-plugin/ycc-mcp`                                 | Generated payload, unlisted; reachable through no catalog           | `DEST/.codex-plugin/ycc-mcp`                                           | Listed native MCP package                                    |
| `.agents/plugins/marketplace.json`                      | `local-ycc-plugins` / `./plugins/ycc`, unchanged                    | `DEST/.agents/plugins/marketplace.json`, named `ycc`                   | Native `ycc` catalog in the repo                             |
| `.codex-plugin/config/mcp-servers.json`                 | Unchanged installer MCP merge input                                 | Not emitted                                                            | Unchanged until migration/dedupe (separate issue)            |
| `codex_marketplace.py` (user-level `local-ycc-plugins`) | Unchanged                                                           | Not involved                                                           | Changed only by the migrate work (roadmap `install-migrate`) |
| Codex agents, config, rules                             | Installer only                                                      | Not emitted                                                            | Installer only (ADR 0001:75)                                 |
| `ycc-hooks`                                             | Never emitted                                                       | Never emitted                                                          | Never emitted until YAN-1149                                 |

Generating `.codex-plugin/ycc-mcp` by default is acceptable. No discovered catalog references it. The legacy installer never reads it (`codex.sh:10` pins `/ycc`), and repo mode's `git-subdir` points only at `./.codex-plugin/ycc`. Release discovery already checks direct children of `.codex-plugin` (`release_versions.py:179–185`), so its version stays in lockstep for free.

What it costs: the repository temporarily carries MCP declarations in two places, legacy `ycc/.mcp.json` and `ycc-mcp`. Nobody can install both through a catalog until the flip, and the flip removes the legacy copy. Document this as intended pre-flip duplication.

### 2. CLI naming: `--native-output DEST`

| Candidate                  | Assessment                                                                                                                                                                                                                                  |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`--native-output DEST`** | **Recommended.** Says _what_ is produced (the native package model's tree) and that it is written. It cannot be confused with redirecting the default legacy output, and it reads clearly in harness code and docs.                         |
| `--output-dir DIR`         | Too generic. It implies "write the normal default output somewhere else". It would be ambiguous if a legacy relocation flag is ever needed, and readers could assume the result matches `sync.sh` output, which it does not.                |
| `--preview-native`         | Misleading. "Preview" suggests `--dry-run`-like, side-effect-free behavior and possibly stdout output, but this mode writes a complete tree. The name also hard-codes temporary status into an interface whose output the listing PR keeps. |

Semantics:

- `--native-output` writes only below `DEST`.
- `--native-output` with `--check` regenerates into a private temporary directory and compares it with `DEST`. It never writes to `DEST`.
- `--native-output` with `--dry-run` lists the owned output paths and writes nothing.
- The flag is unrelated to repository defaults. `run_check()` without the flag keeps checking only the repository's default outputs.

### 3. Destination safety (required, not optional hardening)

Resolve `DEST` with `Path.resolve(strict=False)` after `expanduser`. Reject it when any of the following holds:

- It equals the repository root, lies inside it, or is an ancestor of it. Any of these would let the export overwrite or prune the live catalog or payload.
- It is `/` or the user's home directory itself.
- It, or any existing ancestor between it and its first existing parent, is a symlink that resolves into the repository.
- It exists, is non-empty, and contains no owned-tree marker from a previous `--native-output` run. Never prune a directory the tool did not create.

Accept a dedicated child directory such as `/tmp/opencode/<case>/fixture` or a `tempfile.mkdtemp()` root. The harness should create a fresh `DEST` per run, and generator `--check` uses `TemporaryDirectory`.

Root-level `/tmp` itself should not be accepted, because a stray prune there could touch unrelated files. The marker can be a plain owned-path manifest (for example `DEST/.ycc-native-output.json` listing generated paths and the generator version). Prune and check use it. It must not appear inside a plugin root, where it would be installed. [INFERENCE] Codex copies the whole local plugin directory into its cache, so any extra file inside `.codex-plugin/<pkg>` ships.

### 4. Minimal implementation shape

Keep the change in the existing modules. Do not add a new framework.

1. **`generate_codex_common.py`:** add relative layout constants or helpers for the native package roots (for example `native_plugin_root(dest, package)` returning `dest/.codex-plugin/<package>`) and for the final catalog path (`dest/.agents/plugins/marketplace.json`). Leave the existing absolute repository constants alone; the legacy path keeps using them.
2. **`generate_codex_skills.py`:** `write_tree(dest_root, dry_run)` already accepts an arbitrary `PLUGIN_ROOT`-shaped root. Only `plugin_output_path()` (`56–59`) is bound to `PLUGIN_ROOT`, and it already maps back with `.relative_to(PLUGIN_ROOT)` (`169`). No change is needed beyond a test proving that `write_tree(DEST/.codex-plugin/ycc)` output matches the default output byte for byte for skills and shared.
3. **`generate_codex_plugin.py`:**
   - Load the model with `load_package_model()`. Select Codex runtimes with `status == "included"` and `mechanism == "native"`, mapping components to builders: `skills` and `shared` go to the skill tree, `mcp` goes to the MCP payload. Fail with an error naming the package and component if an included Codex package names an unsupported component, such as `hooks` reaching `included` without a builder change. Never fall through to copying a tree.
   - Split the manifest builder into one shared function parameterized by package name and present components. Legacy `ycc` keeps its current bytes, including `mcpServers`. Native `ycc` omits `mcpServers`. `ycc-mcp` gets its own name and `interface` text and only `mcpServers`.
   - Split the catalog builder into a pure function that takes the selected entries (`build_native_marketplace(entries)`) and keep the legacy `build_repo_marketplace()`. Entries use `{"source": "local", "path": "./.codex-plugin/<pkg>"}` plus the existing `policy` and `category`. No source-only field (`listed`, `status`, `gates`, `evidence`, `target_release`) leaks into any runtime JSON.
   - Add `write_native(dest_root, dry_run)`. It calls `generate_codex_skills.write_tree(dest/.codex-plugin/ycc)`, writes the native manifests and the MCP payload, writes the catalog, records the owned-path manifest, and prunes previously owned paths that are no longer expected.
4. **`scripts/sync.sh`:** no new target and no new wrapper. `generate-codex-plugin.sh` keeps producing the default outputs, now including the unlisted `.codex-plugin/ycc-mcp`. Only the harness and tests invoke `--native-output`.
5. **`validate-codex-plugin.sh`:** extend it in place (see section 7).

Native MCP shape: legacy `.mcp.json` remains copied from `mcp-configs/mcp.json`. Native `ycc-mcp` reuses the existing translator and reviewed Codex overrides as `{"mcpServers": build_codex_mcp_config()["mcp_servers"]}`. Same-name credential references become symbolic `env_vars`; never read developer secrets or expand them at generation time. Do not ship the installer's top-level `mcp_servers` wrapper.

### 5. Catalog membership and future routing for `listed: true`

Separate **which packages are generated** from **which ones a catalog lists**.

- **Generated set:** Codex runtimes with `status: included`, `mechanism: native`, and only supported components. Today that is `ycc` and `ycc-mcp`. Excluded hooks are never generated.
- **Repository default catalog:** the legacy catalog while `ycc.codex.listed == false`. Once the main `ycc.codex.listed` flips to `true` on `main`, the default generation path switches automatically: `.codex-plugin/ycc` becomes the native skills/shared bundle and `.agents/plugins/marketplace.json` becomes the `ycc` catalog listing every package that has `listed: true`. Regenerating after the flag change produces the cutover. Nobody hand-edits catalogs.
- **Fail on partial or inconsistent states** instead of guessing:
  - `ycc-mcp.listed == true` while `ycc.listed == false` would list an add-on in a catalog that does not exist yet, or force `local-ycc-plugins` to list native packages. Reject it with a clear error.
  - `ycc.listed == true` while the legacy catalog or installer still references `./plugins/ycc` is the listing PR's job (with migration). The generator should flip deterministically; installer/migration readiness is a gate in RELEASING.md, not something the generator can infer.
- **`--native-output` catalog membership:** list every _generated_ package (`ycc`, `ycc-mcp`) regardless of the production `listed` flag. The export is the off-by-default projection of the post-flip state, and the acceptance requires `ycc@ycc` and `ycc-mcp@ycc` to be discoverable. Document the export as "the catalog as it will be at the flip". It does not redefine `listed`, which stays production catalog visibility in the repository.

The alternative of an in-memory model copy with selected `listed` flags flipped is viable. It reuses the exact production routing code. But it needs model-path plumbing in the CLI, and readers can confuse it with a real flag change. Prefer the simple rule above, with a unit test proving that a model with `listed: true` produces the same catalog JSON as the export. That keeps one catalog function covering both.

### 6. Prune and check lifecycle

The existing generators follow an owned-subtree discipline. `generate_codex_skills.prune_orphans()` removes only files under `skills/` and `shared/` (`107–140`), and `compare_trees()` reports `extra in repo` only there (`229–243`). The metadata generator's `compare_files()` (`128–138`) checks only the files it returns, so it cannot detect leftovers.

Recommended lifecycle:

- **Default outputs.** Extend metadata `--check` so it also fails on unexpected files directly under `.codex-plugin/ycc-mcp/` and its manifest directory, and on an unexpected `.codex-plugin/ycc-hooks/` directory (a hooks guard). Leave unrelated `.codex-plugin/agents/` and `.codex-plugin/config/` alone; other generators own them.
- **`--native-output` writes.** Prune only paths listed in the previous owned-path manifest that the new plan no longer expects. Prune empty owned directories bottom-up. Never use `rmtree` on `DEST`.
- **`--native-output --check`.** Generate into a temporary directory and diff the full set of files under `DEST/.codex-plugin/{ycc,ycc-mcp}` and the catalog file, both ways: missing, changed, and extra. Any `DEST/.codex-plugin/ycc-hooks` fails. The check never writes or prunes.
- **Required tests (pytest style, like the existing `scripts/test_*.py`):**
  1. The default run leaves the legacy catalog and legacy `ycc` manifest byte-identical to the checked-in files (golden comparison), and `.mcp.json` stays in legacy `ycc`.
  2. Export into a fresh temporary directory, then check passes. A second export makes no changes (idempotence).
  3. Planting a stale file in `DEST/.codex-plugin/ycc/skills/x/` or an extra file in `ycc-mcp` makes check fail, and the next export prunes it. Planting `DEST/.codex-plugin/ycc-hooks/` fails check.
  4. Planting an unowned file under `DEST` outside the owned set survives export. A non-empty, unmarked `DEST` is refused.
  5. `DEST` equal to the repository root, inside it, an ancestor of it, or a symlink into it is refused.
  6. Native `ycc` contains no `mcpServers` and no `.mcp.json`. `ycc-mcp` contains no `skills/` or `shared/`. Every manifest path reference exists, and every manifest `version` equals `ycc/.claude-plugin/plugin.json`'s version.
  7. Routing: the export catalog lists both packages. A copy of the model with `listed: true` reproduces the same catalog. A model with only `ycc-mcp` listed raises. Flipping hooks to included without a builder raises.
  8. Native `skills/` and `shared/` bytes equal the default `.codex-plugin/ycc/{skills,shared}` bytes, proving one generator with no forked transformations.

### 7. Validator changes (`scripts/validate-codex-plugin.sh`)

Keep the existing local-files planning policy (`15–48`). Add:

- The extended metadata `--check` (section 6), which also covers `.codex-plugin/ycc-mcp`.
- A JSON lint for `.codex-plugin/ycc-mcp/.codex-plugin/plugin.json` and its MCP file.
- Apply the forbidden-planning-server policy (`plan`, `agent-native-plans`) to the `ycc-mcp` MCP payload as well as legacy `ycc/.mcp.json`. Otherwise the split silently bypasses an existing guard.
- A native export round trip: `--native-output "$(mktemp -d)/native"`, then `--native-output … --check`, then the component-boundary assertions from section 6. This runs without a Codex binary and without network, so it can stay in the default validator.

Live Codex installation stays in the opt-in harness. Do not make the ordinary validator depend on `codex`.

### 8. Hermetic install harness

Build a new opt-in script modeled on `scripts/test-codex-marketplace-spike.sh`. Reuse its isolation (`63–85`) and its version gate (`114–123`, `>= 0.160.0`), but install real generated payloads instead of its synthetic marker plugin.

1. Run `generate_codex_plugin.py --native-output "$root/source"`, `git init`, commit, and clone to a bare `fixture.git`. Record the commit SHA.
2. Add `https://codex-spike.invalid/fixture.git --ref <sha>`, rewritten to the bare repository with `GIT_ALLOW_PROTOCOL=file`. The spike recorded that `file://` URLs are rejected (`codex-marketplace.md:28–34`). Assert that the selected marketplace is named `ycc`.
3. Assert that `codex plugin list --available` shows `ycc@ycc` and `ycc-mcp@ycc` at the canonical version. Run `codex plugin add` for each and assert exit code 0.
4. Compare the installed caches (`$CODEX_HOME/plugins/cache/ycc/<pkg>/<version>/`) byte for byte with the source fixture. Assert that `ycc` has no MCP and that `ycc-mcp` has no skills, shared files, or hooks.
5. Sparse case: `--sparse .agents/plugins --sparse .codex-plugin/ycc --sparse .codex-plugin/ycc-mcp` succeeds. Optionally keep the catalog-only negative control from the spike.
6. Do not start a session, inference, login, MCP servers, or hooks. Write a sanitized transcript and record the observed CLI version. Locally installed `0.161.0` is evidence for that version only; it does not cover every `>= 0.160` release.

This is fork-_shaped_ proof through Codex's Git marketplace path, not proof of public GitHub transport or authentication. State that limit in the PR.

### 9. Release and docs

- **Version parity:** `release_versions.py` discovers `.codex-plugin/ycc-mcp/.codex-plugin/plugin.json` automatically (`179–185`). Add a regression test asserting that the file is discovered and that a stale version fails `check`. Do not hand-bump it; it is checked-only and regenerated.
- **Bundle release:** `bundle-release` regenerates through sync, so the default `ycc-mcp` stays current. The export catalog lives outside the repository and is not a release surface before the flip.
- **Docs:** update existing internal status text only:
  - RELEASING.md gate row 79, `listed` "no generator consumes it". It becomes "the Codex generator consumes it; flip pending".
  - ADR 0001's "Not implemented" note.
  - `packages.json` `codex` notes, if needed.
    Do not change public install guides or README commands.

## Improvement Ideas

- Expose one "owned output plan" function that returns expected paths per package. Write, prune, `--check`, `--dry-run`, and the tests should all consume it, so the four can never disagree about ownership.
- Make the catalog builder pure, taking entries in and returning JSON, so routing tests need no filesystem.
- Have the validator export round trip reuse the generator's check mode instead of reimplementing diff logic in shell.
- Keep the owned-path marker outside plugin roots, so it never enters an installed cache.
- Record the generator's source commit in the harness transcript (not in generated JSON, to stay deterministic) to tie evidence to code.

## Risk Assessment

| Risk                                                  | Evidence / failure mode                                                                                                                                       | Impact                                                                                   | Mitigation                                                                                                                                                                            |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User-visible catalog change before flip               | The discovered `.agents/plugins/marketplace.json` is the live `local-ycc-plugins` catalog. Renaming it, emptying it, or adding entries changes discovery now. | High: violates RELEASING.md:55–84                                                        | The default keeps legacy bytes (golden test 1). The `ycc` catalog is emitted only under `--native-output DEST` outside the repository. A partial-listing guard prevents ad hoc flips. |
| Breaking the `install.sh` Codex path                  | `codex.sh:10,268–280` and repo-mode `git-subdir ./.codex-plugin/ycc` consume the legacy root, including its MCP.                                              | High                                                                                     | Legacy `ycc` stays unchanged. `ycc-mcp` is a sibling the installer never reads. Run the existing installer tests unchanged.                                                           |
| Export overwrites the repository or prunes user files | A buggy `DEST` value (repository root, a parent, a symlink) combined with prune logic.                                                                        | High                                                                                     | Destination validation (section 3), marker-scoped prune, no `rmtree`, and tests 4–5.                                                                                                  |
| Validator drift / false green                         | `compare_files()` ignores extra files, and JSON parsing does not prove component separation.                                                                  | High                                                                                     | Two-way owned-tree diff, boundary assertions, hooks guard, and the export round trip in the validator.                                                                                |
| Release tooling misses manifests                      | Bounded discovery.                                                                                                                                            | Medium                                                                                   | `.codex-plugin/ycc-mcp` is covered automatically. Add the regression test. Keep the export catalog out of the repository.                                                             |
| Hooks accidentally shipped                            | Generic tree copies, or a future `included` flip without review.                                                                                              | High                                                                                     | Component allowlist with no generic copying, fail-loud on unsupported components, `ycc-hooks` directory guard in both checks, and model-status filtering.                             |
| Duplicate MCP declarations                            | Legacy `ycc/.mcp.json` and `ycc-mcp` coexist before the flip.                                                                                                 | Low before the flip (`ycc-mcp` is unreachable); medium after it, if migration is skipped | Documented intended duplication. The flip removes the legacy MCP from `ycc`. Installer MCP dedupe stays the migrate issue's job.                                                      |
| Forked skill transformations                          | A second conversion path for native `ycc`.                                                                                                                    | Medium                                                                                   | Call `write_tree` directly. Test 8 checks byte equality with the default tree.                                                                                                        |
| Harness overclaims or leaks                           | Real `HOME` or credentials, or claims about public transport, MCP runtime, or 0.160.                                                                          | High                                                                                     | Reuse the spike's isolation, assert the recorded version, and state evidence limits explicitly.                                                                                       |
| Silent future cutover mistakes                        | `ycc.listed` flipped without migration readiness.                                                                                                             | Medium                                                                                   | The generator flips deterministically; RELEASING.md gates and the listing PR own readiness. The partial-listing guard catches the common mismatch.                                    |

## Alternative Approaches

| Approach                                                            | Pros                                                                                                                                                              | Cons / verdict                                                                                                                                                              |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Legacy default plus `--native-output DEST` export (recommended)** | No pre-flip user-visible change. One skill generator. Final repository shape proven with real bytes. Minimal new surface. Release covers `ycc-mcp` automatically. | Needs destination-safety and ownership logic, and carries temporary MCP duplication. **Recommended.**                                                                       |
| Dormant full tree under `packages/codex/{ycc,ycc-mcp}`              | Fits release discovery and is inspectable in the repository.                                                                                                      | Duplicates about 350 generated skill files in git. It is a second staging layout that must later be moved, and it adds churn on every skill edit. Superseded by the export. |
| Replace the discovered catalog with `ycc` and zero entries          | Tiny change.                                                                                                                                                      | Changes marketplace identity and removes the legacy entry. User-visible. Reject.                                                                                            |
| Split `.codex-plugin/ycc` in place now                              | Final layout immediately.                                                                                                                                         | Removes MCP from current installer and `git-subdir` users. Reject.                                                                                                          |
| Fixture-only model copy with flipped `listed` flags                 | Exercises the production routing function exactly.                                                                                                                | Plumbing a model path through the CLI, and readers can mistake it for a real flag change. Acceptable alternative. Prefer the simple export rule plus an equivalence test.   |
| Defer all native generation to the flip                             | Zero risk now.                                                                                                                                                    | Fails this issue's acceptance and loads all the risk onto the flip PR. Reject.                                                                                              |
| Generate `ycc-hooks` unlisted                                       | Symmetry.                                                                                                                                                         | Contradicts `status: excluded` (YAN-1123 no-go). Reject until YAN-1149.                                                                                                     |

## Task Breakdown Preview

These slices all land in **one PR**.

| #   | Slice                                                                                                                                      | Files                                                                                                        | Depends on | Done when                                                                                                                                                                |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Confirm the native MCP manifest shape for `ycc-mcp` (API research)                                                                         | none, or notes in the plan                                                                                   | none       | The format is decided: the legacy `.mcp.json` shape or a documented alternative                                                                                          |
| 2   | Layout helpers and destination validation                                                                                                  | `scripts/generate_codex_common.py`                                                                           | none       | Helpers and `validate_native_dest()` behave as specified in sections 3 and 4                                                                                             |
| 3   | Manifest and catalog builder split, model-driven package selection, partial-listing guard                                                  | `scripts/generate_codex_plugin.py`                                                                           | 1, 2       | Legacy bytes unchanged; native builders are pure                                                                                                                         |
| 4   | `write_native()`, `--native-output`, owned-path marker, prune, two-way `--check`, `--dry-run`; default `ycc-mcp` emission and extras check | `scripts/generate_codex_plugin.py` (imports `generate_codex_skills.write_tree`)                              | 2, 3       | Export plus check round trip passes; default sync emits `.codex-plugin/ycc-mcp`                                                                                          |
| 5   | Generator tests 1–8                                                                                                                        | new `scripts/test_generate_codex_plugin.py` (or the existing test module, if one covers the Codex generator) | 3, 4       | All pass                                                                                                                                                                 |
| 6   | Validator extensions                                                                                                                       | `scripts/validate-codex-plugin.sh`                                                                           | 4          | Planning policy covers `ycc-mcp`; export round trip and boundaries pass                                                                                                  |
| 7   | Release discovery regression                                                                                                               | release tests for `ycc/skills/bundle-release/scripts/release_versions.py`                                    | 4          | `ycc-mcp` is discovered; stale version fails                                                                                                                             |
| 8   | Hermetic install harness                                                                                                                   | new `scripts/test-codex-native-packages.sh`, sharing patterns with `test-codex-marketplace-spike.sh`         | 4          | Full and sparse installs of `ycc@ycc` and `ycc-mcp@ycc` pass on the local Codex; transcript recorded                                                                     |
| 9   | Regenerate, then update internal docs                                                                                                      | `.codex-plugin/ycc-mcp/**`, RELEASING.md row 79, ADR "Not implemented", `packages.json` notes if needed      | 4          | Sync is clean; public docs are untouched                                                                                                                                 |
| 10  | One final verification pass (main agent)                                                                                                   | —                                                                                                            | 5–9        | Generator `--check` (default and export), `validate-codex-plugin.sh`, package validator group, release tests, the opt-in harness, and the existing Codex installer tests |

Slices 2 and 7 can run in parallel with 3. Slices 5, 6 and 8 run in parallel after 4.

Out of scope: `install.sh --package`, `migrate`, new global validator groups, hooks, the repository rename, and the listing flip.

## Key Decisions Needed

1. **Adopt `--native-output DEST`** (not `--output-dir` or `--preview-native`), with the destination rules in section 3. Recommended.
2. **Export catalog membership:** list every generated package regardless of production `listed` (recommended, with a routing-equivalence test), versus feeding the export a copied model with flipped flags.
3. **Emit `.codex-plugin/ycc-mcp` by default before the flip?** Recommended yes. It keeps the version in lockstep and is validated continuously, at the cost of documented temporary MCP duplication. The alternative is to emit it only under `--native-output`, which leaves nothing in the repository but loses default-tree validation of `ycc-mcp`.
4. **Automatic routing on `ycc.codex.listed=true`:** recommended yes, deterministic regeneration, with a hard error for partial listing. Confirm that the listing PR, not this one, owns migration readiness.
5. **Native MCP shape:** settled: translated Codex server entries under `mcpServers`, including `env_vars`; legacy raw MCP remains unchanged.
6. **Evidence scope:** the hermetic Git fixture on the locally installed Codex, recorded version `0.161.0`, satisfies the "≥0.160" acceptance for this PR. Public transport, MCP runtime, and a literal `0.160.0` run are explicitly not claimed.

Already settled and not reopened: package names, lockstep versioning, root-relative `local` sources, the `.agents/plugins` location, the hooks exclusion, installer ownership of agents/config/rules, and no public docs flip or rename.

## Open Questions

- Does Codex expose a read-only way, through the CLI or app-server RPC, to list an installed plugin's MCP server registrations without starting them? That would strengthen the `ycc-mcp` evidence beyond cache bytes.
- Is there an existing Python test module for `generate_codex_plugin.py` that should be extended instead of adding a new one? Check `scripts/test_*codex*` before adding a file.
- Should the owned-path marker file be named and versioned so a later listing PR can reuse `--native-output` for promotion, or should promotion simply regenerate in the repository after the `listed` flip? Recommended: regenerate. The marker is export-local.
- Will CI provision a Codex binary for the harness, or does it remain maintainer-run evidence attached to the PR?
