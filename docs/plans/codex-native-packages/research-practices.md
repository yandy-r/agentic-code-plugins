# Practices research — codex-native-packages (YAN-1131 / GitHub #300)

## Executive Summary

Reuse-first view: what already exists, what to extend in place, and the smallest
test set that proves the acceptance criteria. All paths are repo-relative to the
worktree root. Line numbers verified against the checked-out tree unless marked
`[INFERENCE]`.

## Current-state facts that shape every recommendation

1. **`.agents/plugins/marketplace.json` already exists at the Codex-preferred
   catalog location.** Its checked-in content is
   `{"name": "local-ycc-plugins", "interface": {"displayName": "Local YCC Plugins"}, "plugins": [{"name": "ycc", "source": {"source": "local", "path": "./plugins/ycc"}, "policy": {...}, "category": "Productivity"}]}`,
   produced by `scripts/generate_codex_plugin.py:70-90` (`build_repo_marketplace`)
   via `REPO_MARKETPLACE_PATH` (`scripts/generate_codex_common.py:27`). There is
   **no `plugins/` directory in the repo**, so the entry's `./plugins/ycc` source
   does not resolve to the generated `.codex-plugin/ycc/` payload. ADR 0001
   ("Context" and "Codex" matrix rows) says exactly this: the catalog "still uses
   the name `local-ycc-plugins` with path `./plugins/ycc`" and the rename to the
   `ycc` marketplace with `./.codex-plugin/ycc` happens "at the flip".
2. **Therefore any rename/repoint of that file is user-visible today.** The
   YAN-1123 spike (`docs/internal/spikes/codex-marketplace.md`, verified cases)
   proves `codex plugin marketplace add <git-source>` discovers
   `.agents/plugins/marketplace.json` first, ahead of the
   `.claude-plugin/marketplace.json` fallback. Renaming the catalog to `ycc`
   and listing working `local` entries would make `ycc@ycc` / `ycc-mcp@ycc`
   installable from `main` immediately — violating RELEASING.md "Unfinished
   work" ("Anything a user could reach before it is finished stays hidden") and
   the "v6.0.0 package-model gates" table ("Packages stay unlisted; no catalog
   lists them… the legacy Codex `ycc` entry remains"). **Recommendation: the
   generator filters catalog entries by `listed` (see Interface), so with
   `listed: false` for both Codex entries the discovered catalog keeps its
   current name/legacy entry byte-for-byte; the flip PR changes only
   `listed` in `ycc/settings/packages.json` and re-runs sync.** Do not emit a
   zero-entry `ycc` catalog or a renamed empty catalog pre-flip — that still
   changes the discovered marketplace name. `[INFERENCE]` that today's
   `./plugins/ycc` entry fails at install with "missing plugin.json"; only the
   analogous sparse-checkout case is spike-proven.
3. **The `ycc` payload already exists and is already native-shaped.**
   `.codex-plugin/ycc/` contains `skills/`, `shared/`,
   `.codex-plugin/plugin.json` (`build_plugin_manifest`,
   `generate_codex_plugin.py:33-67`), and `.mcp.json` (verbatim copy of
   `mcp-configs/mcp.json`, line 122). The manifest currently embeds MCP
   (`"mcpServers": "./.mcp.json"`, line 48). The future split removes MCP
   from native `ycc` and adds sibling `ycc-mcp`; default legacy output keeps
   its MCP unchanged before the flip.
4. **The user-level marketplace is a different file and must not be touched.**
   `scripts/lib/install/targets/codex.sh:52-53,170-188` writes
   `~/.agents/plugins/marketplace.json` through `scripts/codex_marketplace.py
merge` (name `local-ycc-plugins`, cache dir
   `~/.codex/plugins/cache/local-ycc-plugins/ycc`). Nothing in this feature
   changes that path; `codex_marketplace.py` stays as-is.
5. **`ycc-hooks@codex` needs no special-casing in new code.** In
   `ycc/settings/packages.json` it is already
   `{status: "excluded", listed: false, components: ["hooks"]}`. A generator
   that selects `status == "included" and mechanism == "native"` Codex entries
   skips it automatically (YAN-1123 no-go / YAN-1149 pending).

## Evaluated design direction: opt-in `--native-output <DEST>`

**Verdict: adopt.** It satisfies the RELEASING off-by-default/unwired gate more
cleanly than emitting the split into the repo pre-flip: default generation
keeps the legacy `.codex-plugin/ycc` (manifest with `mcpServers`, `.mcp.json`
payload) and the discovered `.agents` catalog byte-identical while both Codex
entries are `listed: false`; the future repo-shaped tree exists only where a
caller explicitly asks for it, outside the repo. It also retires Open Question
2 below (no pre-flip MCP removal from the shipping `ycc` payload).

### Minimal implementation (all inside `generate_codex_plugin.py` + path constants)

1. **Mode predicate, derived from the model — no new config:**
   `native_split_active(model)` is true iff `ycc@codex.listed and
ycc-mcp@codex.listed`; exactly one listed is a hard generator error
   (the flip is atomic; a half-split catalog — `ycc` native without its MCP
   split, or vice versa — is never a valid intermediate state).
   `--native-output` forces the predicate true for that invocation only.
   Note the split is _mode_-driven, not purely component-driven pre-flip:
   the legacy `ycc` manifest embeds MCP even though `ycc@codex.components`
   is `[skills, shared]`, so builders take an explicit `native_split: bool`
   parameter rather than inferring everything from `components`.
2. **Builders parameterized once:** `build_plugin_manifest(package,
native_split)` and `build_repo_marketplace(model, native_split)`.
   Default (split inactive): legacy `ycc` manifest/catalog exactly as today,
   **plus** the new unlisted `.codex-plugin/ycc-mcp/` manifest + `.mcp.json`
   (undiscovered — the catalog does not name it). Split active: `ycc`
   manifest drops `mcpServers`, no `ycc/.mcp.json` is written, catalog is
   `{name: "ycc", plugins: [ycc → ./.codex-plugin/ycc, ycc-mcp →
./.codex-plugin/ycc-mcp]}` with `local` sources.
3. **Skills payload reuse — mind the actual interface:** the skills
   generator's entry point is `write_tree(dest_root, dry_run) -> set[Path]`
   (`scripts/generate_codex_skills.py:143-217`), and its `dest_root` is a
   **plugin root** (paths returned are relative to it: `skills/…`,
   `shared/…`, via `plugin_output_path` + `PLUGIN_ROOT` rebasing at lines
   56-59, 168-170), whereas `generate_codex_plugin.write_all` takes a
   **repo root**. So the native tree writer is a two-line composition:
   `write_tree(dest / ".codex-plugin" / "ycc", dry_run)` then
   `write_all(dest, dry_run, native_split=True)`. This generates from `ycc/`
   source — no copying of the checked-in generated tree, and no second
   skills pipeline. No import cycle: `generate_codex_skills` imports only
   `generate_codex_common`.
4. **DEST guard (the safety-critical 5 lines):** `dest = Path(arg).resolve()`;
   reject with exit 2 if `dest` overlaps the repo in either direction
   (`dest == REPO_ROOT`, `REPO_ROOT in dest.parents`, or
   `dest in REPO_ROOT.parents` — i.e. DEST inside the repo, equal to it, or
   an ancestor of it). Overlap either way would let the native catalog land
   in a discovered location or clobber the legacy tree. `--native-output`
   and `--check` are mutually exclusive (`argparse` group; `--check` is
   defined against the repo tree only). `--dry-run` composes fine — both
   writers already support it.
5. **Scope of "complete tree":** catalog + `ycc` (skills/shared/manifest) +
   `ycc-mcp` (manifest/`.mcp.json`). `write_all` also emits
   `.codex-plugin/config/mcp-servers.json` relative to the repo root; in the
   native tree that file is harmless extra payload — keep it (one code path)
   rather than special-casing it out. Agents (`generate_codex_agents.py`)
   stay out: Codex plugins cannot carry them (ADR matrix).

### Flag naming: keep `--native-output`

- `--output-dir` implies "same default output, different directory" — wrong:
  this flag changes _which_ tree is generated (native split vs legacy), not
  just where. A user passing `--output-dir` would reasonably expect the
  legacy catalog.
- `--preview-native` reads as a boolean mode switch and still needs a
  separate destination argument; two flags where one suffices.
- `--native-output <DEST>` pairs the variant with its destination in one
  argument and matches the vocabulary already in `packages.json`
  (`mechanism: "native"`). Help text should state the constraint:
  "write the unlisted native-package tree to DEST (must be outside the repo)".

### Flip lifecycle (`listed: false → true`)

- **Automatic routing:** the flip PR changes only the two `listed` flags in
  `packages.json` and re-runs `./scripts/sync.sh --only codex`. The predicate
  flips default generation to the native manifests + `ycc` catalog in-repo;
  no generator code changes at flip time. This is the payoff of deriving the
  mode from the model instead of from the flag.
- **`--native-output` after the flip:** keep it. Its meaning converges to
  "emit the native tree at DEST instead of the repo root" — still exactly
  what the hermetic install harness wants (generate from source into a
  sandbox fixture). Removing it at the flip would force the harness back to
  copying checked-in generated files. The DEST-overlap guard stays valid.
- **Prune:** `write_all` today never deletes (lines 120-124), so at the flip
  the legacy `.codex-plugin/ycc/.mcp.json` would linger as an orphan.
  Minimal fix, no tree-walking: keep a bounded constant of managed metadata
  paths (the two packages' `plugin.json`/`.mcp.json`, the catalog, the MCP
  config JSON) and, when the split is active, `unlink(missing_ok=True)` any
  managed path not in the emitted file set (in practice just
  `ycc/.mcp.json`). The same bounded prune makes repeated `--native-output`
  runs into a reused DEST safe. Skills/shared orphans need nothing new —
  `write_tree` already prunes its owned subdirs
  (`prune_orphans`, `generate_codex_skills.py:113-140`), deliberately
  leaving plugin-metadata files to `generate_codex_plugin.py`.
- **Check:** `--check` needs one addition, because `compare_files`
  (lines 128-138) only iterates the generated set and cannot see orphans:
  when the split is active, assert the bounded stale paths are absent in
  the repo (pre-flip this assertion is inert). Skills already handle the
  analogous case via the "extra in repo" scan in `compare_trees`
  (`generate_codex_skills.py:239-242`) — mirror that idea, bounded to the
  managed-paths constant. There is no `--check` for a `--native-output`
  tree and none is needed: it is generated fresh in tests/harness, never
  checked in.

### Critical tests for the opt-in design

- Unit: predicate truth table over synthetic models (neither listed →
  legacy; both → native; exactly one → error); DEST guard (repo root,
  repo subdir, and repo ancestor all rejected; sibling temp dir accepted).
- Unit: `write_native_tree(tmp_path)` asserts the full shape — catalog name
  `ycc` with both `local` entries, `ycc` manifest without `mcpServers`, at
  least one generated `skills/*/SKILL.md` present (proves from-source
  generation, not copying), `ycc-mcp/.mcp.json` equals
  `{"mcpServers": build_codex_mcp_config()["mcp_servers"]}`, no `ycc/.mcp.json`; second run is idempotent and
  a hand-planted `ycc/.mcp.json` + orphan skill file are pruned.
- Unit (unchanged from below): default generation with the checked-in model
  returns today's catalog dict byte-for-byte — the pre-flip invisibility
  regression test.
- Harness: `test-codex-native-packages.sh` builds its git fixture by running
  the generator with `--native-output "$root/fixture-src"` instead of
  hand-writing a fixture catalog or rsyncing `.codex-plugin/` — one less
  fixture-only JSON literal to drift from the real builder, and the exact
  flip-time tree is what gets install-tested.

## Existing Reusable Code

| Existing code (path:lines)                                                                                                                                                                                                                                                                | Reuse for                                                                           | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/generate_codex_common.py:15-32` path constants (`REPO_ROOT`, `CODEX_PLUGIN_CONTAINER`, `PLUGIN_ROOT`, `PLUGIN_MANIFEST_PATH`, `PLUGIN_MCP_PATH`, `REPO_MARKETPLACE_PATH`, `SOURCE_PLUGIN_PATH`, `SOURCE_MCP_PATH`)                                                               | Single source of output paths                                                       | Add `MCP_PLUGIN_ROOT = CODEX_PLUGIN_CONTAINER / "ycc-mcp"`, `MCP_PLUGIN_MANIFEST_PATH`, `MCP_PLUGIN_MCP_PATH` next to the `ycc` ones. Constants `PLUGIN_MANIFEST_PATH`/`PLUGIN_MCP_PATH`/`REPO_MARKETPLACE_PATH` are consumed **only** by `generate_codex_plugin.py` (verified by grep), so extending/renaming is low-blast-radius.                                                                                                      |
| `generate_codex_plugin.py:29-67` `load_source_plugin()` + `build_plugin_manifest()`                                                                                                                                                                                                       | Lockstep version/description/author from `ycc/.claude-plugin/plugin.json`           | Parameterize by package + components instead of duplicating; `version` already comes from the same file named by `version_source` in `packages.json`.                                                                                                                                                                                                                                                                                    |
| `generate_codex_plugin.py:93-100` `write_json()` (idempotent, write-only-on-change)                                                                                                                                                                                                       | Both new `plugin.json` files and the catalog                                        | Reuse verbatim.                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `generate_codex_plugin.py:103-155` `write_all(dest_root, dry_run)` returning a `set[Path]`, `compare_files()`, `run_check()` (tempdir regenerate + byte-compare drift)                                                                                                                    | Emit the two package payloads + catalog; `--check` drift detection                  | Extend the `files` set and the write block; the `dest_root / X.relative_to(CODEX_PLUGIN_CONTAINER.parent)` rebasing trick (lines 105-108) already supports temp-root checks for any new path under repo root.                                                                                                                                                                                                                            |
| `generate_codex_plugin.py:70-90` `build_repo_marketplace()` entry literal (`policy: AVAILABLE/ON_INSTALL`, `category: Productivity`)                                                                                                                                                      | Catalog entries                                                                     | Turn into a per-package entry builder + loop over listed packages. Do **not** import `codex_marketplace.build_entry`: it hardcodes `name: "ycc"` and calls `sys.exit` on bad input (`scripts/codex_marketplace.py:31-52`) — a CLI helper, not a library.                                                                                                                                                                                 |
| `scripts/package_model.py:261-267` `load_package_model()`, `PackageModel.lookup(pkg, runtime)` (53-55), frozen dataclasses `RuntimePackage`/`Package`/`PackageModel` (23-51)                                                                                                              | Generator input: which Codex packages exist, their `components`, `listed`, `status` | Import it; never re-parse `packages.json` with bare `json.load`. The loader already validates schema + cross-field rules (incl. "`listed=true` requires included native", line 238-239). Catch `PackageModelError` the way `scripts/build_package_graph.py:156-159` does. Sibling bare import (`from package_model import …`) matches how `generate_codex_plugin.py:15-24` already imports `generate_codex_common`/`generate_codex_mcp`. |
| `scripts/generate_codex_mcp.py:90-98` `build_codex_mcp_config()` / `write_codex_mcp_config()`                                                                                                                                                                                             | Installer merge payload and native translated server entries                        | Reuse translated `mcp_servers` entries under the plugin wrapper: `{"mcpServers": build_codex_mcp_config()["mcp_servers"]}`. Same-name credential references become `env_vars`; legacy `.mcp.json` remains the raw copy. Do not emit the installer's top-level wrapper in `ycc-mcp`.                                                                                                                                                      |
| `scripts/sync.sh:80-87` `codex` target (skills → agents → plugin) and `scripts/generate-codex-plugin.sh` (thin `exec python3 … "$@"` wrapper)                                                                                                                                             | Regeneration entry points                                                           | No change. All new output flows through the existing `generate-codex-plugin.sh` step.                                                                                                                                                                                                                                                                                                                                                    |
| `scripts/validate-codex-plugin.sh` (50 lines): `--check` (8), `json.tool` lints (11-13), local-files MCP policy heredoc (15-30)                                                                                                                                                           | Package validation                                                                  | `--check` covers new files once added to `write_all`'s set. Lint the new `ycc-mcp` files; retain the legacy MCP policy check before flip and check native MCP where emitted.                                                                                                                                                                                                                                                             |
| `scripts/test-codex-marketplace-spike.sh`: `clean()` env-`i` sandbox (72-85), `run()`/`assert_rc()` (91-113), version gate ≥0.160 (114-124), `fixture_commit()` (162-168), `.invalid` URL→`file://` rewrite, `matrix_case(name, source, ref, market, plugin, expected, marker)` (185-222) | Hermetic fork-install proof for `ycc@ycc` + `ycc-mcp@ycc`                           | Copy the pattern into a new slim harness (Testability). Do not mutate the spike file — it is the YAN-1123 evidence record.                                                                                                                                                                                                                                                                                                               |
| `scripts/build_package_graph.py:19-26,42-65` (`COMPONENT_OF_KIND`, per-`(package, runtime)` iteration over the model)                                                                                                                                                                     | Precedent for component-driven logic over `package_model`                           | Reference only; no code sharing needed. Its `packages` validator group already guards component duplication per runtime (so `skills`+`shared` in `ycc`, `mcp` in `ycc-mcp` cannot silently collide).                                                                                                                                                                                                                                     |

## Modularity

- **One generator file grows, nothing new is created.** `generate_codex_plugin.py`
  is 176 lines; the multi-package version lands around 260 `[INFERENCE]`. That
  is well within the repo's norm (`generate_codex_common.py` 342,
  `package_model.py` 290). A new `generate_codex_packages.py` would just split
  one cohesive "Codex plugin metadata" concern and force a second
  `sync.sh` step, a second wrapper, and a second `--check` call in the
  validator.
- **Boundaries stay where they are:** `generate_codex_common.py` = paths + text
  transforms; `generate_codex_plugin.py` = plugin/catalog JSON builders +
  writing; `generate_codex_mcp.py` = installer MCP config translation;
  `codex_marketplace.py` = user-level catalog mutation at install time;
  `package_model.py` = validated manifest input. New edges are plugin generator
  → package model and plugin generator → existing skills writer for explicit
  native-output generation.
- **Reuse skills generation with an explicit native path policy.**
  `rewrite_plugin_paths` (`generate_codex_skills.py:62-71`) currently rewrites
  plugin-root paths to `HOME_INSTALL_PLUGIN_ROOT = "~/.codex/plugins/ycc"`.
  That legacy flat location is wrong for Codex's versioned native cache.
  Thread a small policy parameter through `write_tree`/text rewriting, keeping
  the existing default unchanged. Native mode must retain a runtime plugin-root
  token supported by Codex or resolve helpers relative to the installed skill;
  installed harness assertions must check shared-path resolution, not just bytes.
  This is a focused extension of the existing writer, not a duplicate pipeline.

## KISS

- Extend `generate_codex_plugin.py`, not the sync pipeline. Preserve default
  legacy output; add only `--native-output <DEST>` for the explicit future tree.
- Reuse `generate_codex_skills.write_tree` from source and its owned-subtree
  pruning; no generated-tree copies or second skills generator.
- Use model components for native manifests, model listing for catalog routing,
  and an explicit legacy mode for pre-flip compatibility. No new config file.
- Keep per-package interface copy literal and small. No template engine.

## Abstraction vs Repetition

- **Parameterize the manifest builder once:** `build_plugin_manifest(package_key,
entry)` where `entry.components` decides `"skills": "./skills/"` (only when
  `skills ∈ components`) and `"mcpServers": "./.mcp.json"` (only when
  `mcp ∈ components`). Two near-identical 35-line literals would drift on the
  next version/copy change; one builder + a small per-package
  `{displayName, shortDescription, …}` constant keyed by package name is the
  right amount of abstraction for exactly two call sites.
- **Parameterize the catalog entry, keep the catalog builder explicit:**
  `_catalog_entry(name, source_path)` returning the
  `{name, source: {source: "local", path}, policy, category}` shape; the
  catalog builder then reads as: legacy entry (today) vs listed entries (post
  flip). This is a third copy of the entry shape in the repo (others:
  `codex_marketplace.py:47-52`, current `build_repo_marketplace`) — acceptable
  because the current copy is being replaced, not added to, and the installer
  copy serves a different file/lifecycle.
- **Resist a general "package → files" framework.** `write_all` with an explicit
  per-file write list (as today, lines 120-124) stays greppable and matches
  every other generator in `scripts/`. A component-to-artifact dispatch table
  pays off only at ≥4 packages per runtime; Codex has 2 (+1 excluded).
- **`write_json`/`compare_files`/`run_check` are already the shared idiom** —
  reuse, don't re-derive. `[INFERENCE]` other generators (Cursor/opencode)
  follow the same regenerate-into-tempdir `--check` idiom; not re-verified
  here.

## Interface

- **Inputs:** validated `load_package_model()`; source plugin version/author;
  `mcp-configs/mcp.json`; `ycc/skills/` through the existing skills generator.
- **Default before flip:** legacy catalog and `ycc` manifest/MCP payload stay
  byte-identical. Additive `ycc-mcp` metadata may be generated unlisted.
- **Explicit native output:** `--native-output <DEST>` writes repo-shaped
  `.codex-plugin/ycc/{skills,shared,.codex-plugin/plugin.json}`,
  `.codex-plugin/ycc-mcp/{.codex-plugin/plugin.json,.mcp.json}`, and
  `.agents/plugins/marketplace.json` named `ycc` with both root-relative local
  sources. `ycc` contains no MCP in this mode. Destination cannot overlap repo.
- **After listing flip:** default generation emits the native manifests/catalog;
  bounded stale-file pruning removes legacy `ycc/.mcp.json`. `--check` detects
  stale managed metadata as well as missing/drifting files.
- **Unchanged:** sync target, existing wrapper, installer user-level marketplace
  mutation, and installer-managed MCP config translation. `listed` never appears
  as a runtime JSON field.

## Testability

Follow stdlib `unittest` conventions from `test_generate_codex_mcp.py` and
temporary-directory patterns from `test_codex_marketplace.py:21-40`. Register
the new `test_generate_codex_plugin.py` explicitly in `validate.sh` (Codex
section, near lines 226-228); discovery is not automatic.

Critical checks only:

1. Default catalog + `ycc` payload unchanged while unlisted; native mode emits
   component-correct manifests, excludes hooks, and keeps lockstep versions.
2. Destination safety, complete from-source native tree, idempotence, and owned
   orphan pruning; listing transition + `--check` catch stale `ycc/.mcp.json`.
3. Extend `validate-codex-plugin.sh` to lint the added MCP-only package and
   preserve its local-files MCP prohibition. Existing generator `--check` remains
   its entry point. Default legacy MCP policy check stays valid before flip.
4. Opt-in hermetic harness modeled on `test-codex-marketplace-spike.sh`, using
   `--native-output` to generate the git fixture. Install `ycc@ycc` and
   `ycc-mcp@ycc` on Codex ≥0.160 in `env -i`, isolated HOME/CODEX_HOME/XDG,
   HTTPS-shaped `.invalid` URL rewritten to file-only Git transport; verify
   cached skill/shared and MCP bytes and absence of MCP in native `ycc`.

Do not add Codex CLI dependencies to normal validation or repeat the historical
hook-schema spike matrix. Existing installer and marketplace tests stay unchanged
and remain regression coverage. No tests were run for this research assignment.

## Build vs Depend

- **Build (extend) — no new dependencies.** Everything needed is stdlib
  (`json`, `shutil`, `pathlib`, `tempfile`) plus the in-repo
  `package_model` loader, which is itself deliberately stdlib-only (its own
  small JSON-Schema checker, `package_model.py:85-179`). Do not add
  `jsonschema` or a Codex SDK; the repo's generators are dependency-light by
  design and `install.sh` assumes only `python3`.
- **Depend on the installed `codex` binary only in the opt-in harness**,
  exactly as the spike does (`CODEX_BIN` or PATH, ≥0.160; locally 0.161.0).
  Generation and validation must never require it.
- **No new file formats.** `plugin.json`, `.mcp.json`, and `marketplace.json`
  shapes are the ones already generated today and spike-verified for the
  catalog/source forms.

## Open Questions

1. **Is today's repo catalog entry actually broken for direct discovery?**
   `./plugins/ycc` does not exist in the tree. Before redesigning
   `build_repo_marketplace`, run the hermetic harness shape against the
   _current_ catalog (`marketplace add` a git fixture of HEAD) to record what
   `codex plugin marketplace add yandy-r/claude-plugins` does today — this
   determines whether keeping the legacy entry byte-identical is "no change"
   or "preserving a known-broken entry until the flip" (either way it must not
   be silently "fixed" pre-flip; a fix is a user-visible change).
2. **Legacy MCP preservation:** resolved by the opt-in-output design. Do not
   remove MCP from default `ycc` before the listing flip; no assumption about
   today's plugin-level MCP consumers is needed for this feature.
3. **Native MCP representation — settled:** Codex accepts an MCP-only manifest and
   a `mcpServers` wrapper containing Codex server fields. `ycc-mcp` uses
   `{"mcpServers": build_codex_mcp_config()["mcp_servers"]}`, including
   symbolic `env_vars` and reviewed overrides. It neither raw-copies Claude
   credential interpolation nor emits the installer's `mcp_servers` wrapper;
   authenticated server startup remains outside install proof.
4. **Catalog transition mechanics at the flip:** when the repo catalog name
   changes `local-ycc-plugins` → `ycc`, existing users' state references the
   user-level catalog (installer-owned, unchanged), but anyone who ran
   `marketplace add` against the repo directly has a `local-ycc-plugins`
   registration. Migration/dedupe for that cohort is RELEASING-gate scope for
   the listing PR, not this feature — flagging so the flip doesn't assume the
   rename is free. `[INFERENCE]` on cohort size.
5. **Sparse-checkout guidance:** spike-proven that `--sparse` installs need
   both `.agents/plugins` and each payload dir (now two:
   `.codex-plugin/ycc`, `.codex-plugin/ycc-mcp`). That's install-guide content
   for the v6 docs flip; nothing to generate, but the harness may add one
   sparse case cheaply via the existing `matrix_case` shape if the authors
   want it proven for two payloads.
