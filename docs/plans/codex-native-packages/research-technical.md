# Codex Native Packages — Technical Research

## Executive Summary

Generate two model-driven native packages: `ycc` owns skills and shared helpers; `ycc-mcp` owns MCP configuration. Both use the product version from `ycc/.claude-plugin/plugin.json`. Do not generate Codex `ycc-hooks`, agents, config, or global instructions inside either package.

**The requested same-path cutover is not hidden merely because `listed` is false.** `.agents/plugins/marketplace.json` already exists and advertises `local-ycc-plugins` with `ycc` at `./plugins/ycc`. The current `.codex-plugin/ycc` manifest advertises MCP, and `install.sh` installs that directory. Renaming the discovered catalog, emptying its entries, fixing its source, or splitting that directory in place changes existing behavior before v6.0.0. RELEASING.md:55–85 expressly preserves the legacy entry and requires an atomic final switch for changes that cannot be hidden.

**Recommendation:** implement the complete native generator behind explicit `--native-output DIR`, with an isolated repository-shaped output tree; preserve default legacy generation and production catalog until the listing/cutover PR. Generate the candidate `.agents/plugins/marketplace.json` only inside that output tree. Normal candidate generation honors `listed:false` and emits zero entries; a hermetic fixture uses a copied package model with only `ycc.codex.listed` and `ycc-mcp.codex.listed` set true to prove both installs. This is a real fork-install test of generated artifacts, not a claim that today's production catalog lists them. No production package-model flags change in this feature.

This report is design research, not implementation or executed acceptance evidence. Statements about proposed behavior are recommendations; runtime acceptance remains unverified here.

## Architecture Design

### Existing boundaries and evidence

| Surface                                                  | Current behavior and evidence                                                                                                                                                                                                                                                                                                       |
| -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/generate_codex_plugin.py`                       | `build_plugin_manifest()` (33–67) hardcodes `ycc`, `skills`, and `mcpServers`; `build_repo_marketplace()` (70–90) hardcodes the legacy catalog; `write_all()` (103–125) writes one manifest, copied `.mcp.json`, catalog, and managed MCP JSON. `run_check()` compares expected bytes but does not detect obsolete extra artifacts. |
| `scripts/generate_codex_common.py`                       | Paths at 15–32 bind generators to `.codex-plugin/ycc`; `PLUGIN_SHARED_DIR` is `shared/`, not `_shared/`. Source MCP is `mcp-configs/mcp.json`. Home path rewrites at 84–88 and the fixed `HOME_INSTALL_PLUGIN_ROOT` at 32 assume installer links. Keep source transforms shared, not duplicated.                                    |
| `scripts/generate_codex_mcp.py`                          | `build_codex_mcp_config()` (90–93) translates source `mcpServers` to installer `mcp_servers` and applies TOML overrides. This is a different artifact from native plugin `.mcp.json`.                                                                                                                                               |
| `scripts/package_model.py`                               | `PackageModel.lookup(package, runtime)` (53–55) returns immutable runtime metadata or `None`; `load_package_model()` (261–267) validates schema, semantics, and evidence. Do not parse the manifest independently.                                                                                                                  |
| `scripts/build_package_graph.py`                         | `package_sets()`, `check_closures()`, and `check_duplicates()` check component ownership and fallback closures (42–113). Codex fallback agents satisfy references from skills; it is not permission to bundle agents natively.                                                                                                      |
| `ycc/settings/packages.json`                             | `ycc.codex` is included/native/unlisted with `["skills","shared"]` (26–43); `ycc-mcp.codex` is included/native/unlisted with `["mcp"]` (84–98); `ycc-hooks.codex` is excluded (140–156). Fallback Codex agents/instructions/settings remain file-copy (287–301).                                                                    |
| `.agents/plugins/marketplace.json`                       | Entire existing file, 1–20: `name: local-ycc-plugins`, one `ycc` entry, local source `./plugins/ycc`, AVAILABLE/ON_INSTALL policy. A filesystem inspection found no repository `plugins/` directory. Preserve this existing mismatch rather than silently repairing it as part of hidden work.                                      |
| `docs/internal/spikes/codex-marketplace.md`              | Historical 0.161.0 evidence at 10–18 and 48–55: `.agents` catalog wins over Claude fallback; root-relative local sources work; catalog-only sparse installs fail; catalog plus payload works. Hook parity remains No-Go.                                                                                                            |
| `AGENTS.md`                                              | 18–46: generated artifacts derive from source; agents target must not own `.agents/plugins`; Codex custom agents are separately installed. 105–114 delegates release gates to RELEASING.md.                                                                                                                                         |
| `docs/internal/adr/0001-package-model-and-versioning.md` | 46–75 plans catalog rename only at flip and assigns skills/shared versus MCP; 110–139 requires lockstep and no production listing before gates.                                                                                                                                                                                     |

### Generated native tree

`DIR` is an isolated output root before the flip, not the active checkout root:

```text
DIR/
  .agents/plugins/marketplace.json
  .codex-plugin/
    ycc/
      .codex-plugin/plugin.json
      skills/<skill>/SKILL.md
      skills/<skill>/agents/openai.yaml       # existing invocation-policy output
      skills/<skill>/...                     # existing references/scripts/assets
      shared/...                            # source ycc/skills/_shared/*
    ycc-mcp/
      .codex-plugin/plugin.json
      .mcp.json
```

No `.codex-plugin/ycc/.mcp.json`, no MCP field in its native manifest, and no skills/shared/agents/hooks in `ycc-mcp`. No `ycc-hooks` directory or marketplace entry. `_shared` is the source component name; the actual generated directory remains `shared/` to reuse existing generator/reference conventions. `.codex-plugin/agents` and `.codex-plugin/config` remain legacy installer outputs, outside native packages.

At the flip, these same relative native paths become the production tree, replacing—not augmenting—the legacy same-path package. The native generator removes obsolete owned MCP metadata in `ycc`; it must not delete sibling agents/config or arbitrary user files. Before the flip, do not run native output against the active checkout or a containing parent: fail this invocation explicitly.

### Generation pipeline

1. Load the validated model once using `load_package_model(manifest_path)`.
2. For known package keys `ycc`, `ycc-mcp`, `ycc-hooks`, resolve `model.lookup(key, "codex")`; emit included/native entries regardless of listing. Explicitly reject unexpected supported-component combinations rather than silently dropping components. Excluded/deferred/absent entries produce no payload. The current excluded hooks entry must produce neither payload nor catalog row.
3. Read version from `repo_root / model.version_source`; do not default to `0.0.0` when the authoritative version is missing. Use existing source author/repository metadata and package-specific descriptions.
4. Reuse `generate_codex_skills.write_tree(dest_root, dry_run)` for native `ycc/skills` and `shared`, but add a transform context for native relocation; do not invoke a second skill-copy implementation.
5. Build package manifests from components. Emit native `.mcp.json` only for `mcp`; managed installer `config/mcp-servers.json` continues unchanged in legacy generation.
6. Build native marketplace from included/native/**listed** entries only. Sort package keys and JSON formatting deterministically. No `listed`, `status`, `target_release`, or `components` fields leak into runtime JSON.
7. `--check` renders to a temporary tree and checks expected bytes plus obsolete **generator-owned** files. Native and legacy checks operate independently; dry-run never writes or prunes.

### Hidden catalog and fork-install proof

The hidden candidate catalog lives at `DIR/.agents/plugins/marketplace.json` where `DIR` is not a configured marketplace or current working repository. A zero-entry catalog with `name:ycc` is safe only there; zero entries at the existing repository discovery path are **not** safe. A dot-prefixed directory is not inherently hidden from Codex discovery.

The test fixture copies the model, sets the two supported Codex `listed` flags true in that copy, and calls the same native generator into a fresh fixture tree. It commits that generated tree and clones it into a bare repository, following `scripts/test-codex-marketplace-spike.sh:61–123,161–175`. A fake HTTPS `.invalid` URL rewritten to the bare fixture via isolated Git config exercises Git marketplace discovery without public network/auth. Install selectors are exactly `ycc@ycc` and `ycc-mcp@ycc`.

Assert `marketplaceName == "ycc"`; available IDs exactly match both packages; both install exit codes are zero; installed manifests match generated bytes/version; `ycc` includes real skill/shared payload and no MCP; `ycc-mcp` includes exact MCP bytes and no skill tree. Compare a sorted payload/hash inventory, not only one fake marker. Run a full checkout and sparse checkout including `.agents/plugins`, `.codex-plugin/ycc`, and `.codex-plugin/ycc-mcp`. Keep the original spike's catalog-only sparse negative control if extending it. Never start a session, execute hooks, invoke an MCP server, or copy real credentials. Installation success is not server-authentication/runtime proof.

## Data Models (JSON shapes)

### Package-model input

Existing `lookup("ycc", "codex")` fields remain:

```json
{
  "status": "included",
  "listed": false,
  "mechanism": "native",
  "components": ["skills", "shared"],
  "requires": [],
  "target_release": "v6.0.0",
  "experimental": false,
  "opt_in": false,
  "evidence": ["docs/internal/adr/0001-package-model-and-versioning.md", "docs/internal/spikes/codex-marketplace.md"],
  "gates": [
    "v6.0.0 listing PR after rename: package validators, lockstep preflight, per-target migration and dedupe tests, and clean-machine fork installs pass"
  ],
  "notes": "Current catalog is local-ycc-plugins with ./plugins/ycc and stays active until the flip; planned listing is .agents/plugins/marketplace.json with a local source at ./.codex-plugin/ycc."
}
```

Use the existing complete `ycc-mcp.codex` record with `components:["mcp"]` and `listed:false`; no schema addition is required. Preserve current flags, including excluded hooks.

### Native manifests

Minimal exact required candidate shapes below use the currently observed source version `5.3.0` illustratively; generation always reads the live authoritative version. Retain existing optional ycc UI metadata where applicable, but do not blindly copy skills prompts into MCP-only metadata.

`DIR/.codex-plugin/ycc/.codex-plugin/plugin.json`:

```json
{
  "name": "ycc",
  "version": "5.3.0",
  "description": "Planning, implementation, review, and workflow skills for Codex.",
  "author": { "name": "yandy-r" },
  "repository": "https://github.com/yandy-r/claude-plugins",
  "homepage": "https://github.com/yandy-r/claude-plugins",
  "license": "MIT",
  "skills": "./skills/"
}
```

`DIR/.codex-plugin/ycc-mcp/.codex-plugin/plugin.json`:

```json
{
  "name": "ycc-mcp",
  "version": "5.3.0",
  "description": "MCP server integrations for Codex.",
  "author": { "name": "yandy-r" },
  "repository": "https://github.com/yandy-r/claude-plugins",
  "homepage": "https://github.com/yandy-r/claude-plugins",
  "license": "MIT",
  "mcpServers": "./.mcp.json"
}
```

Native `DIR/.codex-plugin/ycc-mcp/.mcp.json` is the existing source document `mcp-configs/mcp.json`, copied without translation, with root `{"mcpServers":{...}}`. Representative concrete server entries:

```json
{
  "mcpServers": {
    "github": { "command": "github-mcp-server", "args": ["stdio"] },
    "context7": { "type": "http", "url": "https://mcp.context7.com/mcp" }
  }
}
```

The example omits other source servers for readability; the actual artifact copies **all** servers, not this subset. Existing source names also include stripe, xero, linear, linear-personal, vercel, railway, playwright, and openaiDeveloperDocs. Native acceptance must verify the plugin parser supports this existing shape; do not claim the installer TOML translation proves native compatibility. `.codex-plugin/config/mcp-servers.json` remains a separate `{"mcp_servers":{...}}` installer input, including TOML overrides and Codex tool approval settings.

### Marketplace shapes

Normal candidate output while both entries are unlisted:

```json
{ "name": "ycc", "interface": { "displayName": "YCC" }, "plugins": [] }
```

Fixture listing and eventual post-gate production catalog:

```json
{
  "name": "ycc",
  "interface": { "displayName": "YCC" },
  "plugins": [
    {
      "name": "ycc",
      "source": { "source": "local", "path": "./.codex-plugin/ycc" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    },
    {
      "name": "ycc-mcp",
      "source": { "source": "local", "path": "./.codex-plugin/ycc-mcp" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
```

No pinned Git URL/ref in this repository catalog. Local sources resolve against the repository root, not against `.agents/plugins/`. Existing user-level `local-ycc-plugins` continues to use local `./.agents/plugins/ycc` or git-subdir `./.codex-plugin/ycc`; these are a different namespace and ownership surface.

## API Design (CLI/generator interfaces)

Recommended additions to `scripts/generate_codex_plugin.py`, preserving current bare invocation, `--check`, and `--dry-run`:

```text
./scripts/generate-codex-plugin.sh [--check | --dry-run]
./scripts/generate-codex-plugin.sh --native-output DIR [--manifest PATH] [--check | --dry-run]
```

Prefer `--native-output DIR` over generic `--output-dir` (would ambiguously relocate legacy output) or `--preview-native` (suggests dry-run rather than complete installable artifacts). It both opts into native layout and names the required isolated output root. Resolve symlinks and reject the active repository root, descendants, or ancestors before writing; require a separate output root. `--manifest` defaults to the existing canonical package-model path and is necessary for controlled fixture listing. Reject conflicting check/dry-run modes. The shell wrapper already forwards arguments unchanged. No production `--include-unlisted` switch: install proofs should change the **copied input model**, leaving one listing rule.

Concrete Python interfaces (new names are proposed, not existing APIs):

- `generate_codex_common.py`: add `native_package_root(output_root: Path, package: str) -> Path` and native manifest/MCP path helpers; preserve existing legacy constants for installer/skills callers until cutover. Pass paths explicitly rather than mutating imported module globals.
- `generate_codex_plugin.py`: add `codex_packages(model: PackageModel)`, `build_native_plugin_manifest(package: str, entry: RuntimePackage, source: dict) -> dict`, `build_native_repo_marketplace(model: PackageModel) -> dict`, `write_native_tree(output_root: Path, model: PackageModel, dry_run: bool) -> set[Path]`, and `check_native_tree(...) -> int`. Keep `build_plugin_manifest()`, `build_repo_marketplace()`, and default `write_all()` behavior legacy-only until flip; remove this transition mode at the atomic cutover rather than retaining permanent aliases.
- `generate_codex_mcp.py`: add `build_native_mcp_config() -> dict` returning the original `mcpServers` document and `write_native_mcp_config(path: Path) -> None`. Keep `translate_env`, `translate_server`, `build_codex_mcp_servers`, `build_codex_mcp_config`, and `write_codex_mcp_config` unchanged for managed config. Never write `mcp_servers` under native `.mcp.json` merely because the installer uses it.
- `generate_codex_skills.py`: extend `write_tree`/text rewriting with an explicit native-versus-installer reference context, retaining the current default. Existing lines 56–69 rewrite source plugin-root references into fixed `~/.codex/plugins/ycc` paths. A native snapshot is installed under `plugins/cache/ycc/ycc/<version>` and must resolve shared helpers without the installer's home symlink. Audit and test actual generated script references; use supported plugin-root substitution only if proven by Codex, otherwise skill-relative references from the containing skill directory. [INFERENCE] A successful file-copy install alone will not catch these runtime reach-ins.

No new `install.sh --package` or migration API in this feature; those belong to the package/migration workstream. At the flip they must consume the native component split rather than rely on the old combined bundle.

### Minimal routing and lifecycle

**Settled direction:** default invocation preserves legacy `.codex-plugin/ycc/**` and `.agents/plugins/marketplace.json` byte-for-byte, and additionally emits the tiny unlisted `.codex-plugin/ycc-mcp/{.codex-plugin/plugin.json,.mcp.json}` in the checkout. No current installer or discovered catalog references that path, so it is dormant; include it in default drift and release-version checks. `--native-output DEST` remains the only off-by-default complete repository-shaped export, generated from `ycc/` through the existing skills generator. No tracked duplicate full skills tree.

Do **not** add automatic listed-flag routing of production output now: it would implement half of the YAN-1140 cutover without migration/dedupe, and partial-listing semantics add avoidable scope. Instead implement and test one pure listed-aware catalog builder, used by native export and reusable unchanged at the flip. YAN-1140 then switches the default production writer, flips both model flags, applies migration/dedupe, and removes transition-only legacy generation. Merely reaching version 6.0.0 must not enable listing. This deferment is acceptable only because every native package generator and the export are real, validated, and fork-install-tested now.

`write_tree` is the existing skills API, not `write_all`; native generation calls it with the candidate ycc root so source `ycc/skills` remains authoritative. A write prunes obsolete files only inside generator-owned package subtrees and metadata paths; check detects the same obsolete files without deleting; dry-run reports the same write/delete plan without mutation. Tests cover repeated generation, included-to-excluded/absent transitions, listed true-to-false removing only catalog rows, stale legacy ycc MCP in native output, hooks exclusion, output-root symlinks, unrelated sibling preservation, and unchanged default legacy ycc/catalog bytes. A newly unlisted package can remain a payload while disappearing from the catalog; never conflate those lifecycles.

## System Constraints

- Minimum acceptance CLI is 0.160.0; existing spike records 0.161.0. Enforce/report actual installed version in the harness. Do not describe one 0.161.0 run as exhaustive compatibility with every later version.
- RELEASING.md:47 requires `main` always releasable. 55–61 requires hidden preparation and one final switch for unavoidable visible changes. 78–85 requires legacy ycc visibility until gated flip; the catalog cannot be renamed now.
- `listed` is generation policy only. Codex does not enforce it as an invented runtime field, and unlisted payload presence does not stop an existing installer from consuming it.
- Codex hooks remain excluded by model and historical No-Go; YAN-1149 is pending. No hooks manifest or runtime probe belongs in native package generation.
- `shared/` remains colocated with skills; agent TOML, AGENTS.md, and config settings remain installer fallbacks. Package graph closures remain an independent required check.
- No changes to public install docs/navigation or repository URL rename before the designated flip. This research does not authorize a rename.
- Pre-flip output artifacts are complete installable candidates, not scaffolds, but live user paths and runtime catalog selection remain unchanged.

## Codebase Changes (files create/modify)

| File                                                                     | Proposed change                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/generate_codex_plugin.py`                                       | Add `--native-output DEST` export and listed-aware catalog builder; default emits exact legacy output plus dormant production `ycc-mcp`; two manifests, included-versus-listed filtering, fail-closed components, deterministic output and owned obsolete-file checks. No automatic production routing.                                                                                                                                              |
| `scripts/generate_codex_common.py`                                       | Explicit output-root/package path helpers; no replacement of legacy constants before cutover.                                                                                                                                                                                                                                                                                                                                                        |
| `scripts/generate_codex_mcp.py`                                          | Separate native MCP writer from existing managed-config translation; retain source server set and existing installer overrides.                                                                                                                                                                                                                                                                                                                      |
| `scripts/generate_codex_skills.py`                                       | Reuse `write_tree`; support native relocatable references and isolated root without changing existing installer defaults.                                                                                                                                                                                                                                                                                                                            |
| `scripts/validate-codex-plugin.sh`                                       | Preserve default legacy checks at 7–29; add native/output-root mode that checks native generator drift, both manifest versions/names, component allowlists, native MCP shape and source parity, no hooks, safe existing local source targets, and no generator policy fields. Apply forbidden plan/agent-native-plans MCP check to native ycc-mcp too. Do not require nonempty normal candidate catalog. Preserve local-files skill policy at 32–47. |
| `scripts/generate-codex-plugin.sh`                                       | Existing argument forwarding is sufficient; update usage comment only if documenting native mode.                                                                                                                                                                                                                                                                                                                                                    |
| `scripts/sync.sh`                                                        | No new step: existing Codex ordering at 80–86 calls the generator, which now also writes dormant `ycc-mcp`. Native export is not a sync side effect and writes nothing to the checkout. YAN-1140 makes native production generation normal.                                                                                                                                                                                                          |
| `scripts/test_generate_codex_plugin.py` (new)                            | Test inclusion versus listing, excluded hooks, component mismatch, two manifest content sets, authoritative version, copied-model listing, safe output root, deterministic check/dry-run, obsolete owned file detection, and byte-compatible default behavior.                                                                                                                                                                                       |
| `scripts/test_generate_codex_mcp.py`                                     | Extend existing tests for native shape/source parity while preserving translation/override tests.                                                                                                                                                                                                                                                                                                                                                    |
| `scripts/test-codex-native-packages.sh` (new)                            | Opt-in generated-tree Git fixture harness for both selectors, full/sparse install, installed payload inventory, and isolated no-auth/no-session operation. Reuse spike isolation pattern; do not weaken existing spike cases.                                                                                                                                                                                                                        |
| `scripts/test_codex_marketplace.py`                                      | Existing helper contract remains unchanged; retain tests for preserving user catalog name, unrelated entries, and local/repo source forms.                                                                                                                                                                                                                                                                                                           |
| `scripts/test-install-sync.sh`                                           | Regression coverage must retain base-only behavior including legacy MCP payload, plus explicit MCP-step behavior; no expectation that base now auto-installs ycc-mcp before flip.                                                                                                                                                                                                                                                                    |
| `ycc/settings/packages.json`                                             | Existing data already describes emission. Do not flip listing flags or hooks status. Evidence/notes may record this feature once genuine acceptance evidence exists.                                                                                                                                                                                                                                                                                 |
| `.codex-plugin/ycc/**`, `.agents/plugins/marketplace.json`               | No pre-flip production split/rename. Native equivalents exist under isolated output root. At flip replace same-relative-path artifacts atomically and retire legacy ycc MCP.                                                                                                                                                                                                                                                                         |
| `.codex-plugin/ycc-mcp/**` (new, tracked)                                | Dormant production-path manifest plus source MCP document; no catalog entry and no installer reference before YAN-1140. Native export writes the same bytes.                                                                                                                                                                                                                                                                                         |
| `scripts/lib/install/targets/codex.sh`, `scripts/codex_marketplace.py`   | Intentionally unchanged now. At flip package-aware installation/migration must preserve required MCP behavior and avoid duplicate native-versus-config server registrations.                                                                                                                                                                                                                                                                         |
| `ycc/skills/bundle-release/scripts/release_versions.py`                  | No new broad recursive discovery needed. Existing bounded discovery already sees production `.codex-plugin/ycc-mcp/.codex-plugin/plugin.json`. Add regression fixture proving this. Isolated candidates must be checked against source version by the native validator, because arbitrary output roots are intentionally outside release discovery.                                                                                                  |
| `scripts/test-release-bundle.sh`                                         | Extend lockstep discovery fixtures to include ycc-mcp, versionless native catalog entries, and mismatch detection; generated manifests are check-only, never directly bumped.                                                                                                                                                                                                                                                                        |
| `RELEASING.md`, `docs/internal/adr/0001-package-model-and-versioning.md` | Update implementation-state wording only when implemented; document native mode default-off/output-root hiding, required fork proof, and explicitly preserved legacy catalog. Do not mark listing gates passed based on this report.                                                                                                                                                                                                                 |

### Installer impact: answer in detail

`codex.sh:10` points `CODEX_PLUGIN_DIR` to `.codex-plugin/ycc`; base mode snapshots it through CLI (`130–143`) or copies the whole directory for older CLIs (`91–127`). Local mode links both `~/.codex/plugins/ycc` and `~/.agents/plugins/ycc` to it (`299–319`), and registers `./.agents/plugins/ycc` (`338–345`). Repo mode registers git-subdir `./.codex-plugin/ycc` on main (`332–337`; helper 37–43). Therefore **yes**, base installs currently carry MCP inside that package even though MCP also has a separate scope-aware installer step (`381–385`). Removing ycc MCP changes the plugin installed by base-only users. Do not infer that independent config merging makes that removal invisible.

`codex_marketplace.py:21–24,55–90` creates `local-ycc-plugins` only when no existing name is present, preserves existing marketplace names/interface and unrelated entries, and mutates only ycc. It does not read repository `.agents/plugins/marketplace.json`. Leave its user-level marketplace name, source forms, merge/remove ownership, cache layout, and selector unchanged. Repository marketplace `ycc` and user marketplace `local-ycc-plugins` can coexist; renaming the former does not justify renaming the latter. Migration/dedupe at flip remains a prerequisite, not an implicit generator side effect.

### Version discovery: answer in detail

The authoritative helper is **`ycc/skills/bundle-release/scripts/release_versions.py`**, not `scripts/release_versions.py`. It defines optional native marketplace locations at 40, allowed manifest subdirectories at 41, and bounded generated directory scanning at 179–185. `_child_dirs(root, ".codex-plugin")` includes `ycc-mcp`; `_manifest_rels` then finds its `.codex-plugin/plugin.json`. It checks parity even for unlisted packages. Production native catalog entries need no version field; `_version_field` intentionally ignores absent fields. Do not add versions solely to satisfy release tooling. Source bumps continue to modify source surfaces; generated native artifacts receive the version on regeneration. No changes to generated copies of the helper by hand.

## Technical Decisions (options + recommendation)

1. **Immediate discovered catalog rename versus empty discovered catalog versus deferred output.** Reject rename: changes identity today. Reject zero entries at production path: removes legacy availability and still selects a differently named native catalog. Recommend complete isolated candidate generation and fixture-only listing; production catalog emitted/renamed only at the atomic flip. This follows RELEASING.md rather than inventing a runtime hiding field.
2. **Immediate same-path package split versus isolated native mode.** Reject same-path split before flip because existing local and repo installers consume it. Recommend isolated mode with exactly the intended final relative layout, then a clean cutover. Do not introduce a second publicly installed compatibility package or silently auto-install ycc-mcp to compensate.
3. **Gate payloads on listed versus gate only catalog rows.** Recommend included/native controls payload generation; listed controls catalog rows. Otherwise acceptance cannot exercise unlisted packages and staged outputs disappear until release.
4. **Native source MCP versus translated installer MCP.** Recommend source `mcpServers` document, consistent with current native manifest, with live parser/install evidence required. Keep translation for managed TOML. Codex-only override semantics are a separate concern; do not silently transpose them into an undocumented native shape.
5. **New universal generator abstraction versus existing functions.** Recommend small package-root helpers plus reuse of skills `write_tree` and model loader. Two packages do not justify a new plugin framework. Transitional legacy/native boundary is explicit and removed at flip, not permanent compatibility aliases.
6. **Commit duplicated dormant tree versus generate on demand.** Settled: export complete native tree on demand and use an immutable Git fixture; track only the tiny dormant `ycc-mcp` package. Avoid tracking a second full skill tree solely to hide it.

## Open Questions

- **Acceptance wording versus nonvisibility:** the literal combination “production `.agents/plugins/marketplace.json` named ycc now”, “production `.codex-plugin/ycc` loses MCP now”, and “nothing visible changes” is incompatible with observed callers. Recommended resolution is fixture/candidate acceptance now and production emission only at flip. Main specification should make this explicit, not silently relax either requirement.
- **Native MCP discovery/runtime semantics:** current native manifest already uses `mcpServers:"./.mcp.json"`, but this report has not executed parser/RPC acceptance for the split MCP-only plugin. Generated-tree install plus metadata inspection must establish discovery; no authentication or server launch should be implied.
- **Relocatable native skill script references (uncertain; pending ApiResearcher runtime proof):** existing skill generation hardcodes the installer's `~/.codex/plugins/ycc` link. The implementation must choose a runtime-proven native path mechanism and add concrete installed-path checks for shared helper reach-ins. Neither generated paths nor a successful copy-install is runtime proof.
- **Post-flip installer ownership:** package-aware migration must decide which explicitly requested packages become native and how existing managed MCP entries are deduped while preserving user-owned config. This feature should not decide that policy incidentally through generator edits.
- **Baseline coverage:** local installed 0.161.0 can satisfy the requested >=0.160 proof; a claim of support specifically on 0.160.0 requires a separate executable/run, not just a numeric version guard.
