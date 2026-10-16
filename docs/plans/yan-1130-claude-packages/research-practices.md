# Practices Research: yan-1130-claude-packages

## Executive Summary

Build one small stdlib-only `scripts/generate_claude_packages.py`, a thin wrapper, direct `unittest` regression tests, and a dedicated `claude` sync/validate/scope target. Reuse `scripts/package_model.py` as the only package selector and version source, and follow `scripts/generate_codex_plugin.py`'s build-before-write, owned-root pruning, deterministic JSON, and `--check`/`--dry-run` conventions. Do not generalize a multi-runtime framework for two consumers, regenerate source `ycc/`, or couple generation to marketplace, settings, install, or migration behavior.

## Existing Reusable Code

- `scripts/package_model.py:19-55,200-267` provides validated immutable packages and lookup. Select Claude entries with `status="included"` and `mechanism="native"` regardless of `listed`. Generate only `ycc-mcp`, `ycc-hooks`, and `ycc-all`; treat source `ycc` as an existing dependency target, and keep deferred `ycc-agents` absent.
- `ycc/settings/packages.json:65-198` already models `ycc-mcp` as `{"mcp"}`, `ycc-hooks` as `{"hooks"}`, and `ycc-all` with components `[]` and bare `requires=["ycc","ycc-mcp","ycc-hooks"]`, all `listed:false`. Derive plugin `dependencies` from `requires`.
- `scripts/generate_codex_plugin.py:101-125` is the model-selection and fail-closed component/unsafe-name pattern. Mirror it with Claude-supported payloads and an explicit skip/dependency-target rule for source `ycc`; reject unsupported eligible payloads.
- `generate_codex_plugin.py:146-189` reads lockstep version from `model.version_source` and resolves metadata before writes. Source is `ycc/.claude-plugin/plugin.json`, currently `5.3.0`; fail before output mutation when absent.
- `generate_codex_plugin.py:192-299,345-386` gives symlink guards, owned-root extras/pruning, unchanged-skip JSON writes, byte and owner-executable-bit comparison, and temporary-regeneration drift checks. Adapt destination paths to in-repository `packages/claude/`; do not copy Codex external-export checkout-overlap restrictions wholesale.
- `generate_codex_plugin.py:405-432` and `scripts/generate-codex-plugin.sh` establish mutually exclusive `--check`/`--dry-run`, parse/validation errors on stderr, and executable kebab-case wrapper via `exec python3`.
- `scripts/validate_codex_native.py:20-82` is the independent structural-policy pattern. Adapt it because `hooks` is legitimate on Claude. `scripts/validate-codex-plugin.sh:25-29` runs generator drift then policy validation.
- `scripts/test_generate_codex_plugin.py:30-195` is the direct-unittest template: temp destinations, subprocess CLI, byte snapshots, model mutation, sentinel-environment checks, drift/pruning/symlink negative cases.
- `scripts/test_package_model.py:50-73` pins only `ycc@claude` as listed and `ycc-all` requirements. Preserve those invariants rather than broadening listing scope.

## Modularity Design

- A small Claude generator exposes pure manifest/hooks/inventory builders over `Package` inputs and a narrow write/check/main layer, similar to `generate_codex_plugin.py`. This permits tests without touching checkout files.
- Keep it independent of `generate_codex_plugin.py` and `generate_codex_common.py`; the latter imports PyYAML at `scripts/generate_codex_common.py:13`, while Claude packaging needs only standard-library JSON, paths, copy, argparse, and temporary directories. Tiny version/write helper duplication is acceptable; extraction is warranted when a third generator needs the same machinery.
- Copy `mcp-configs/mcp.json:1-48` byte-for-byte into `ycc-mcp/.mcp.json`, retaining literal `${XERO_CLIENT_*}` placeholders. Claude needs no Codex MCP translation.
- Copy hook scripts from `ycc/settings/hooks/` into a self-contained `ycc-hooks/hooks/` tree, preserving mode `100755`. `scripts/claude_hooks_spike.py:56-61,222-224` grounds `hooks/hooks.json`, the outer `hooks` object, event arrays, and `${CLAUDE_PLUGIN_ROOT}` command paths.
- `ycc/settings/settings.json:14-25` registers only `WorktreeCreate`; `herdr-agent-state.sh:10-23` is the `session` script. If the approved payload includes both events, build both registrations explicitly. Do not assume copying every script alone activates it.

## KISS Assessment

- Use model `requires` as the bare dependency list; no resolver, ranges, `@marketplace` qualifiers, or dependency graph language.
- Do not create a generated duplicate of `ycc`, shared runtime engine, YAML/config DSL, publication path, or migration hooks in this issue.
- A few explicit pure builders beat a cross-runtime abstraction. Similar Codex names aid review without risking Codex byte-stable behavior.
- Use either an independent read-only policy validator or structural assertions in generator tests—not both initially—unless maintainers require external-output auditing. Output comparison alone does not independently enforce package shape.

## Interface Design

- Selection is model-driven, supports only the intended Claude component payloads, and errors with package context on unknown eligible components.
- Every manifest gets `package.key` and canonical version. `ycc-mcp` contains `.mcp.json`; `ycc-hooks` contains `hooks/`; `ycc-all` contains `dependencies == list(runtime.requires)` and no copied functional payload.
- Never serialize internal model fields such as `listed`, `status`, `mechanism`, `components`, `runtimes`, or raw `requires` into manifests.
- `write_all(dest_root, dry_run)` returns a deterministic owned inventory; `--check` verifies missing/changed/extra and script executable-bit drift without mutation; `--dry-run` creates nothing.

## Sync, Validation, and Scoping

- `scripts/sync.sh:15,68-100` uses explicit target registration/dispatch and lists generated aliases through `package.json:48-58`. Add Claude generation through an explicit `claude` target and matching npm aliases; keep existing target behavior unchanged.
- Recommended validation is also a dedicated `claude` target running the drift/policy wrapper and generator tests. Current runtime/package separation appears at `scripts/validate.sh:221-232,261-268`; target name is a design default, not an existing contract.
- `scripts/lib/validate-scope.sh:30-39` currently maps package manifest/schema/model to `packages` only. Once Claude output depends on them, scope must also select Claude drift/policy validation. Update scope tests in `scripts/test-validate-scope.sh:50-97` with affected generator, MCP, generated-root, and hook paths. Existing settings paths select `all` and must retain coverage.
- `scripts/validate-hooks.sh` is only a non-fatal user-home WorktreeCreate symlink warning; it does not validate plugin-native commands.
- `packages/claude/` is new. Consider adding it to generated-output style exclusions in `.prettierignore`/style excludes, like established generated roots, but do not blanket-ignore unrelated packages.

## Testability Patterns

- Test exact generated inventory, distinct manifest names, component isolation, shared version, and `ycc-all` dependencies equal to model requirements.
- Assert source MCP byte parity and literal `${XERO_CLIENT_*}` survival; add an environment sentinel that must not appear, following `test_generate_codex_plugin.py:53-78`.
- Assert hook JSON, plugin-root command paths, copied content, owner executable bits, and no execution of production worktree hooks during unit tests.
- Cover failed input/version before writes, modeled unsupported components, unsafe managed paths, dry-run no mutation, check drift/missing/extra/exec-bit, and rerun pruning with neighboring files preserved.
- Patch model entries to prove selection/dependencies are not a hard-coded three-name snapshot and deferred packages stay absent.
- Guard public `/.claude-plugin/marketplace.json`, source `ycc/`, and `ycc/settings/settings.json` against mutation during generation tests.
- Hermetic unit tests do not replace isolated runtime acceptance. Preserve the coordinator’s real-payload expectation: `claude plugin validate` each package and isolated `ycc-all` install evidence naming the tested client version. The 2.1.301 stub proves dependency mechanics, not real MCP/hooks payloads.

## Build vs. Depend

Use only Python stdlib and `package_model.py`. No YAML, schema engine, template framework, MCP translator, or dependency resolver is justified. Claude CLI validation is a complementary acceptance probe, not a network/runtime-dependent unit-test substitute.

## Lint and Script Conventions

- `AGENTS.md:31-32,50-71` and `.claude/rules/scripts.md:9-18`: typed public Python APIs, strict executable kebab-case Bash wrappers, existing `scripts/test_*` suites, no npm test/build target.
- `pyproject.toml:1-15` sets Python 3.11, Black/Ruff 120 columns, Ruff `B/E/F/I/UP`. `package.json:5-14` routes lint/format through repo scripts; `scripts/style.sh:81-105` requires lockfile-installed Node CLIs rather than arbitrary `npx` resolution.
- Never hand-format generated package outputs; change source/generator then regenerate.

## Safe Defaults and Open Questions

- **Scope:** only `packages/claude/{ycc-mcp,ycc-hooks,ycc-all}`; preserve `listed:false`, version `5.3.0`, public marketplace, settings, install, and migration behavior.
- **Hooks:** document Claude Code ≥2.1.300 and duplicate settings/plugin dispatch; dedupe remains later migration work (`docs/internal/spikes/claude-hooks.md:10-19`).
- **Unresolved hook choice:** explicitly decide whether both `WorktreeCreate` and herdr `SessionStart` activate in this package. Copying source scripts does not settle registrations.
- **Unresolved validator choice:** dedicated policy validator versus structural assertions in the generator suite. [Safe default: generator suite first unless maintainers want a standalone read-only audit command.]
- **Dependency baseline:** do not claim a minimum `dependencies` client from the 2.1.301 stub; baseline remains unestablished.
- No builds, tests, linters, formatters, or runtime validation were run for this research assignment, as instructed.
