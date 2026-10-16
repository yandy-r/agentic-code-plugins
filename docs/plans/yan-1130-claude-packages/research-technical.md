# YAN-1130 — Technical Research: Model-Driven Claude Packages

Tracking: YAN-1130 / GH #302. Scope: generate unlisted Claude-native packages
`packages/claude/{ycc-mcp,ycc-hooks,ycc-all}` from the existing package model.
Out of scope (later work): public marketplace listing, `ycc/settings/` surface
changes, `install.sh` migration/dedupe, version-bump tooling changes.

## Executive Summary

The Codex native generator (`scripts/generate_codex_plugin.py`) already implements
every mechanism this feature needs: immutable model loading, deterministic JSON,
owned-root pruning, symlink guards, temp-dir `--check`, and byte + executable-bit
drift comparison. The Claude generator should be a structural clone of that
pipeline's **in-repo mode** (`write_all` / `run_check`), retargeted at
`runtime == "claude"`. The model (`ycc/settings/packages.json`) already declares the
graph: `ycc` (included, listed, native, `[skills, agents, shared]`), `ycc-mcp`
(included, unlisted, native, `[mcp]`), `ycc-hooks` (included, unlisted, native,
`[hooks]`), `ycc-all` (included, unlisted, native, `[]`,
`requires: [ycc, ycc-mcp, ycc-hooks]`), all `target_release: v6.0.0`. Version is
lockstep `5.3.0` from `ycc/.claude-plugin/plugin.json` via `version_source`; the
generator must never hardcode it. Two corrections to prior notes: the official
manifest dependency key is **`dependencies`** (bare strings), not
`pluginDependencies`; and the `ycc-hooks` payload should register **both**
`WorktreeCreate` (settings-sourced) and `SessionStart` with the `session` argv
(spike-sourced) — copying the herdr script alone registers nothing.

## Architecture Design

### Approach

One new stdlib-only script, `scripts/generate_claude_packages.py` (+ thin
`scripts/generate-claude-packages.sh` wrapper per `generate-codex-plugin.sh`
convention), mirroring `generate_codex_plugin.py`'s in-repo mode (lines 302–386) —
**not** the out-of-repo native export (`preflight_native_destination`, lines
221–236), because `packages/claude/` lives in the repository.

```
ycc/settings/packages.json ──load_package_model()──► PackageModel (frozen)
        │                        scripts/package_model.py:248-258
        ▼
  select claude/native/included/unlisted, key != ycc ──► packages/claude/<key>/
        │
        ├─ mcp-configs/mcp.json ──byte copy──► ycc-mcp/.mcp.json
        ├─ ycc/settings/hooks/*.sh ──byte copy──► ycc-hooks/hooks/
        │                + generated hooks/hooks.json (WorktreeCreate, SessionStart)
        └─ model requires ──► ycc-all/.claude-plugin/plugin.json (dependencies)
```

Pipeline invariants, copied from the Codex implementation:

- **Resolve everything before any write.** `native_metadata` (lines 179–189)
  builds the full `dict[Path, dict]` before filesystem mutation; the Claude
  generator likewise builds manifests, `hooks.json`, and the expected file
  inventory up front, so a bad model never leaves a half-generated tree.
- **Selection is model-driven, never a hardcoded list.** Codex selects with
  `status == "included" and mechanism == "native"` and rejects unsupported
  component sets (`native_packages`, lines 113–125). Claude equivalent:
  `runtime == "claude"`, `status == "included"`, `mechanism == "native"`,
  `listed is False`, with an allowlist of component sets `{mcp}`, `{hooks}`, and
  the empty set (meta package). Anything else fails closed. `ycc` itself is
  excluded — it stays at `ycc/` as the sole listed package.
- **Package key is the directory name.** Codex validates
  `Path(package.key).name == package.key` (lines 107–108, 122–123); reuse it so a
  model key can never escape `packages/claude/`.
- **Stdlib only.** `generate_codex_common.py` imports `yaml` (line 13); the Claude
  generator needs only `json`/`shutil`/`stat`/`tempfile`, so it must not depend on
  the Codex common module — copy the small patterns (`write_json`,
  `guard_managed_paths`, `compare_files`) instead.

### Output layout (safe defaults)

| Package     | Files                                                                                                      | Source                                                                                                                |
| ----------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `ycc-mcp`   | `.claude-plugin/plugin.json`, `.mcp.json`                                                                  | manifest generated; `.mcp.json` byte-copied from `mcp-configs/mcp.json` (10 servers, `${XERO_*}` preserved literally) |
| `ycc-hooks` | `.claude-plugin/plugin.json`, `hooks/hooks.json`, `hooks/worktree-create.sh`, `hooks/herdr-agent-state.sh` | manifest + `hooks.json` generated; scripts byte-copied from `ycc/settings/hooks/` with executable bits preserved      |
| `ycc-all`   | `.claude-plugin/plugin.json` only                                                                          | generated; `dependencies` from model `requires`, in model order                                                       |

Manifest fields follow `build_plugin_manifest` (lines 41–75) minus Codex-specific
`interface`: `name` = package key, `version` = lockstep source version,
`description`/`author` derived from `ycc/.claude-plugin/plugin.json`. Do **not**
emit inline `mcpServers` or `hooks` manifest keys — `.mcp.json` is auto-discovered
and `hooks/hooks.json` is the conventional file; redundant declarations create a
second merge source / double registration (see research-external.md). `ycc-all`
manifest is `{name, version, description, author, dependencies: ["ycc",
"ycc-mcp", "ycc-hooks"]}` — bare strings, same-marketplace resolution, no version
objects (constrained ranges would need `<plugin>--v<version>` git tags, which do
not exist; see official `dependencies` doc).

Generated `hooks/hooks.json` registrations:

- `WorktreeCreate` (provenance: `ycc/settings/settings.json:14-25`, currently
  `bash ~/.claude/hooks/worktree-create.sh`) → plugin-root-relative
  `bash "${CLAUDE_PLUGIN_ROOT}/hooks/worktree-create.sh"`, `${CLAUDE_PLUGIN_ROOT}`
  kept literal until runtime, path quoted.
- `SessionStart` with `matcher: "*"` → `sh
"${CLAUDE_PLUGIN_ROOT}/hooks/herdr-agent-state.sh" session` (provenance: the
  YAN-1122 spike's herdr-style argv; `settings.json` declares no `SessionStart`,
  so this registration is spike-sourced by explicit decision, not inferred from
  the file copy — copying the script alone registers nothing).

### Ownership, determinism, drift

- The generator owns exactly three roots —
  `packages/claude/{ycc-mcp,ycc-hooks,ycc-all}` — mirroring
  `native_package_roots` (lines 101–110). Files not in the expected inventory are
  deleted (`prune_native_output` / `native_extras`, lines 243–252); `--check`
  reports them as `extra in output`. Nothing outside owned roots is written: no
  `.claude-plugin/marketplace.json` (stays single `ycc`), no `ycc/settings/*`, no
  migration logic. Unlisted means unlisted.
- JSON: `write_json` (lines 292–299) — `json.dumps(payload, indent=2) + "\n"`,
  no-op when bytes match, so regeneration is idempotent. Copies are byte-for-byte
  (`shutil.copyfile`, line 336). Model order preserved for
  `requires → dependencies`; `sorted(...)` only for drift reporting.
- `--check` regenerates into `tempfile.TemporaryDirectory()` and compares without
  touching the repo (`run_check`, lines 367–386). All four drift classes apply:
  `missing file`, `drift`, `executable-bit drift`, `extra in output`. The Claude
  check **must** compare executable bits (`compare_executable=True`, as in
  `run_native_check`, line 395, using Git's owner-bit model `is_owner_executable`,
  lines 362–364): both hook scripts ship `+x`, and a lost bit silently breaks
  dispatch while byte comparison stays green. Exit codes follow `main()` (lines
  405–436): `0` clean, `1` drift, `2` tool error.

### CLI contract (mirroring Codex in-repo mode)

| Invocation                                                                       | Behavior                                                         |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `generate-claude-packages.sh` (or `python3 scripts/generate_claude_packages.py`) | Regenerate owned roots in-repo; print summary line               |
| `--dry-run`                                                                      | Print `Would write <rel>` / `Would remove <rel>`, mutate nothing |
| `--check`                                                                        | Temp-dir regeneration; exit 1 on any drift class                 |

## Data Models

No new schema. The existing model (`scripts/package_model.py`) is sufficient:

- `RuntimePackage` (lines 23–36): `runtime, status, listed, mechanism,
components, requires, target_release, experimental, opt_in, evidence, gates,
notes` — frozen dataclass; `components`/`requires` are tuples.
- `Package` (lines 39–44): `key, description, version_policy, runtimes`.
- `PackageModel.lookup(package, runtime)` (lines 47–55), e.g.
  `model.lookup("ycc-all", "claude").requires == ("ycc", "ycc-mcp", "ycc-hooks")`.
- `version_source = "ycc/.claude-plugin/plugin.json"`; `native_version` pattern
  (lines 146–152) reads `5.3.0` and fails on a missing/blank version.

Semantic invariants enforced by `validate_package_model` (lines 200–245),
directly load-bearing here:

| Invariant                                                                     | Line    | Consequence                                                                |
| ----------------------------------------------------------------------------- | ------- | -------------------------------------------------------------------------- |
| Empty `components` requires non-empty `requires`                              | 222     | `ycc-all`'s bare-meta shape is legal precisely because it has dependencies |
| `requires` only for `claude` + `native`                                       | 224     | `dependencies` generation is Claude-only by construction                   |
| Each requirement exists as included native claude package; no self-dependency | 226–237 | Generator never emits a dangling `dependencies` entry                      |
| `listed=true` ⇒ included + native                                             | 238     | Unlisted generation cannot accidentally list a package                     |
| Evidence paths exist under repo root, no escapes                              | 182–197 | Model claims stay source-grounded                                          |

`scripts/build_package_graph.py` validates the closure: `package_sets` (lines
42–65) computes transitive `provides` with cycle detection, and
`check_duplicates` (lines 101–113) rejects two included native packages shipping
the same component on one runtime. The three new packages are clean by
construction: `mcp` and `hooks` are unique to `ycc-mcp`/`ycc-hooks` (`ycc` ships
only `[skills, agents, shared]`), and `ycc-all` provides the union transitively
without owning any component.

Runtime package facts (`ycc/settings/packages.json`):

| Key                  | Status   | Listed | Components                                | Requires                | Target                           |
| -------------------- | -------- | ------ | ----------------------------------------- | ----------------------- | -------------------------------- |
| `ycc`                | included | true   | skills, agents, shared                    | —                       | v6.0.0                           |
| `ycc-mcp`            | included | false  | mcp                                       | —                       | v6.0.0                           |
| `ycc-hooks`          | included | false  | hooks                                     | —                       | v6.0.0                           |
| `ycc-all`            | included | false  | (none)                                    | ycc, ycc-mcp, ycc-hooks | v6.0.0                           |
| `ycc-agents`         | deferred | false  | agents                                    | —                       | v7.0.0 (must not be generated)   |
| `installer-fallback` | included | false  | rules, instructions, settings, statusline | —                       | file-copy, not native — excluded |

## API Design

No network API or database. The developer-facing API is the CLI contract above;
runtime-facing contracts are Claude's on-disk plugin format (official docs):
`<root>/.claude-plugin/plugin.json` (manifest reference),
`<root>/.mcp.json` (`{mcpServers: {...}}`, components#mcp-servers),
`hooks/hooks.json` (`{hooks: {...}}`, components#hooks), literal-until-runtime
`${CLAUDE_PLUGIN_ROOT}` (manifest-reference#environment-variables), and the
`dependencies` string array for the bundle (dependencies#bundle-plugins-for-a-team).
`claude plugin validate` is the CLI shape check (needs 2.1.281+ for MCP
validation; native `WorktreeCreate` needs the stricter 2.1.300 floor). Unknown
component sets, unsafe keys, missing version, or unexpected files return nonzero
rather than emitting a partial substitute. Bare `dependencies` resolve against
the installing marketplace — not neighboring directories — so an isolated test
marketplace must contain entries for `ycc` plus all three generated packages
(local directory marketplace per the YAN-1122 harness pattern, or a parent folder
via `--plugin-dir` on v2.1.265+).

## System Constraints

- **Stdlib only, immutable inputs.** Frozen dataclasses, duplicate-key-rejecting
  JSON (`_unique_object`, lines 58–64), small schema vocabulary (lines 85–137).
- **Security posture.** Symlink rejection on every managed path component and
  inside owned trees (`guard_managed_paths`, lines 192–213), package-key
  path-traversal guards, evidence-path escape checks. Never execute hook payloads
  during generation/validation/tests — `worktree-create.sh` runs `git worktree`
  operations; `bash -n` (parse-only) is the maximum permissible static check and
  belongs in a validator, not the generator. Runtime proof runs only against an
  isolated config dir under a temp home (as the 2.1.301 stub evidence did), never
  `~/.claude`.
- **Client floors.** Plugin `WorktreeCreate` is Go only on Claude Code 2.1.300+
  (No-Go on the 2.1.143 floor — silent absence, Git-default worktrees, no
  warning); `SessionStart` fires on both (spike `docs/internal/spikes/claude-hooks.md:10-16,40-47`).
  Generation does not authorize rollout below the floor.
- **No public surface change.** `listed=false` is generator input, never a runtime
  field; the generator gets no marketplace-writing code path in this scope.
- **Fail closed.** Unsupported component sets, unsafe keys, missing version,
  non-directory roots all raise before any write.

## Codebase Changes

Create `scripts/generate_claude_packages.py` (+ `scripts/generate-claude-packages.sh`
wrapper), generated files under `packages/claude/`, and a focused generator unit
test. Wire regeneration into `scripts/sync.sh` (add a `claude` target; current
`VALID_TARGETS` at `sync.sh:15` are `inventory cursor codex opencode agents`) and
`--check` + unit test into the `packages` validate target
(`scripts/validate.sh:261-268`, alongside `package_model.py --check`, model
tests, `build_package_graph.py --check`). New paths need scope rules in
`scripts/lib/validate-scope.sh` plus `test-validate-scope.sh` cases: today
`packages/claude/*` falls through to the catch-all `all` (safe but runs
everything), and the new generator likewise hits `*` → `all`. Contributor docs
and changelog update during implementation. Unchanged: source settings, public
marketplace, `install.sh`/merge-engine migration logic, Codex/Cursor/opencode
generators. No cross-runtime generator framework — reuse `load_package_model`,
copy the small Codex patterns. Note: release tooling already discovers
`packages/` manifests for version parity (`test-release-bundle.sh:335-336`),
so generated manifests are covered automatically once they exist.

## Technical Decisions

1. **`ycc-all` is additive; do not rename `ycc`.** `ycc` is the listed core
   package, marketplace entry, manifest name, version source, and graph key
   (ADR `0001-package-model-and-versioning.md:42-57`). Renaming changes the
   installed plugin identity and forces a migration — explicitly out of scope.
2. **Copy both hook scripts; register two events with labeled provenance.**
   `worktree-create.sh` is authored here and settings-registered
   (`WorktreeCreate`, `settings.json:14-25`, checked by `validate-hooks.sh`);
   `herdr-agent-state.sh` is foreign-managed (header lines 2–6: "installed by
   herdr… overwrites this file") and env-gated (`HERDR_ENV`/`HERDR_SOCKET_PATH`/
   `HERDR_PANE_ID`, lines 20–22), dormant otherwise. Safe default: copy both
   verbatim (assignment names `ycc/settings/hooks` as the payload source) and
   generate exactly the `WorktreeCreate` registration plus the spike-backed
   `SessionStart`/`"*"` → `…herdr-agent-state.sh session` registration. Do not
   invent further handlers; do not silently drop the herdr copy (that needs an
   explicit scope decision).
3. **Empty `components` is first-class, not an edge case**
   (`package_model.py:222`). Never synthesize payload for meta packages; never
   special-case `ycc-all` by name — `components == () and requires` covers future
   meta packages.
4. **Prefer `bash` form with quoted `${CLAUDE_PLUGIN_ROOT}` in hook commands.**
   Works even if an executable bit is lost in transit (the drift check still
   guards the bit), matching the existing settings command shape.

## Open Questions

- **CI runtime proof**: `claude` 2.1.301 exists on this workstation, but CI
  availability is unconfirmed — keep CI to `--check` + unit tests and treat the
  isolated `claude plugin validate` / install-`ycc-all`-only dependency proof as a
  local/release-time gate until confirmed.
- **Manifest prose**: descriptions for the three packages (Codex hardcodes them
  in `build_native_manifest`, lines 164–176 — acceptable, but wording is a
  maintainer choice).
- **Scope-rule narrowness**: explicit `packages/claude/*` + generator mappings in
  `validate-scope.sh`, or accept catch-all `all` for now (conservative, CI still
  catches over-narrow rules).

## Acceptance Criteria (technical)

1. Generator creates exactly `packages/claude/{ycc-mcp,ycc-hooks,ycc-all}` per
   the layout table; a second run is a no-op (clean `git status`).
2. `--check` exits 0 on a fresh tree; exits 1 with `missing file` / `drift` /
   `executable-bit drift` / `extra in output` on deletion, edit, `chmod -x`, or
   planted extra file.
3. All three manifests carry `5.3.0` from `ycc/.claude-plugin/plugin.json`;
   bumping it and regenerating updates all three in lockstep.
4. `ycc-all` manifest `dependencies` equals model `requires` order
   `["ycc", "ycc-mcp", "ycc-hooks"]`; `ycc-all` contains no payload files.
5. `.mcp.json` byte-identical to `mcp-configs/mcp.json` (`${ENV}` unevaluated);
   hook scripts byte-identical with matching executable bits; hook commands use
   quoted `${CLAUDE_PLUGIN_ROOT}` paths.
6. `ycc-agents` (deferred) and `installer-fallback` (file-copy) produce no
   output; `.claude-plugin/marketplace.json` and `ycc/settings/**` untouched.
7. Isolated-environment `claude plugin validate` passes per package, and
   installing only `ycc-all` from an isolated marketplace installs all three
   dependencies (re-confirming the 2.1.301 stub evidence against generated
   output).

## Evidence

- `scripts/package_model.py:23-55` (frozen model, `lookup`), `:58-64`
  (duplicate-key rejection), `:182-197` (evidence paths), `:200-245` (semantic
  invariants), `:248-258` (tuple-preserving load)
- `scripts/generate_codex_plugin.py:34` (component allowlist), `:41-75`
  (manifest build), `:101-125` (roots/selection), `:128-152` (unlisted handling,
  version source), `:155-176` (per-component manifest; Codex `interface` not
  reused), `:179-189` (resolve-before-write), `:192-218` (symlink/key guards),
  `:239-264` (owned/extras/prune), `:292-299` (`write_json`), `:302-342`
  (in-repo `write_all`), `:345-364` (byte + executable drift), `:367-402`
  (`--check` in temp dir), `:405-436` (CLI/exit codes)
- `scripts/generate_codex_common.py:29-30` (source paths), `:13` (`yaml` —
  reason to stay independent); `scripts/generate_codex_mcp.py:41-77`
  (Claude→Codex env translation — explicitly not applied here)
- `scripts/build_package_graph.py:42-65` (transitive provides + cycles),
  `:101-113` (duplicate-component rejection)
- `ycc/settings/packages.json` (table above), `ycc/settings/packages.schema.json`
- `.claude-plugin/marketplace.json` (single listed `ycc`, `5.3.0`),
  `ycc/.claude-plugin/plugin.json` (version source), `mcp-configs/mcp.json`
- `ycc/settings/hooks/` (both scripts `+x`), `ycc/settings/settings.json:14-25`
  (`WorktreeCreate` only), `scripts/validate-hooks.sh`,
  `scripts/claude_hooks_checks.py` (origin/coexistence expectations)
- `docs/internal/spikes/claude-hooks.md:10-20,38-50,86-92` (2.1.300 floor, no
  dedupe, merge-engine `map-entries` constraint — migration out of scope),
  `docs/internal/adr/0001-package-model-and-versioning.md:42-107` (names,
  matrix, bare-name dependencies), `RELEASING.md:78` (listing gates)
- `scripts/validate.sh:261-268` (`packages` target), `scripts/sync.sh:15,66-102`
  (targets), `scripts/lib/validate-scope.sh:11,30-39` (routing),
  `scripts/test-release-bundle.sh:335-336` (`packages/` parity discovery)
- Official docs: manifest reference, components#mcp-servers, components#hooks,
  manifest-reference#environment-variables, dependencies#bundle-plugins-for-a-team,
  manifest-reference#validate-the-manifest
- Coordinator evidence (not re-run here): Claude 2.1.301 stub `ycc-all`
  validated; installing only it from an isolated marketplace installed
  `ycc`, `ycc-mcp`, `ycc-hooks`
