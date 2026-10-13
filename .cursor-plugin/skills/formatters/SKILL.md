---
name: formatters
description: 'Bootstraps project linting and formatting tools. Use when installing formatters, adding lint scripts, or wiring lint CI and pre-commit hooks.'
argument-hint: '[--dry-run] [--force] [--yes] [--sync] [--copy] [--ci] [--no-autofix] [--hooks] [--no-aliases] [--no-docs] [--target=<dir>] [--profile=<lang>] [--rust] [--ts] [--python] [--go] [--docs] [--shell] [--all]'
allowed-tools:
  - Read
  - Grep
  - Glob
  - Write
  - Edit
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(cp:*)
  - Bash(mkdir:*)
  - Bash(diff:*)
  - Bash(jq:*)
  - Bash(chmod:*)
  - Bash(test:*)
  - 'Bash(${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/*.sh:*)'
  - 'Bash(${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/bundle/*.sh:*)'
---

# Formatters Bootstrap

Installs a best-practices lint/format environment into a target project. Does not reimplement linter dispatch — it drives the repo's own `scripts/style.sh init --copy|--sync` machinery and adds documentation, aliases, CI, and hook wiring on top.

**Operational context:** Install the self-contained scripts/style.sh bundle and per-language configs, add package.json/Makefile/justfile aliases and project docs, and optionally wire CI and pre-commit hooks. Preserve managed-manifest idempotency; --sync is the rerun path.

## Current Target Context

- **Working Directory**: !`pwd`
- **Profile detection**: !`${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/profile-style.sh 2>/dev/null | head -30`

## Arguments

| Flag                                                           | Meaning                                                                         | Example                                  |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------- |
| `--dry-run`                                                    | Preview every planned file; make no writes                                      | `formatters --dry-run`               |
| `--force`                                                      | Overwrite existing tool configs / aliases / docs without prompting              | `formatters --force`                 |
| `--yes`                                                        | Non-interactive; keep existing files on conflict                                | `formatters --yes`                   |
| `--sync`                                                       | Install bundle + prune stale managed files (preferred on re-run)                | `formatters --sync`                  |
| `--copy`                                                       | Install bundle without pruning (default when no manifest exists)                | `formatters --copy`                  |
| `--ci`                                                         | Also emit `.github/workflows/lint.yml` and `.github/workflows/lint-autofix.yml` | `formatters --ci`                    |
| `--no-autofix`                                                 | With `--ci`: skip `lint-autofix.yml`, install the check workflow only           | `formatters --ci --no-autofix`       |
| `--hooks`                                                      | Also wire a pre-commit hook (lefthook preferred, husky if detected)             | `formatters --hooks`                 |
| `--no-aliases`                                                 | Skip package.json / Makefile / justfile alias injection                         | `formatters --no-aliases`            |
| `--no-docs`                                                    | Skip README section append                                                      | `formatters --no-docs`               |
| `--target=<dir>`                                               | Target directory (default: `$PWD`)                                              | `formatters --target=~/projects/app` |
| `--profile=<lang>`                                             | Override detection: `rust`, `ts-node`, `python`, `go`, `docs`, `mixed`          | `formatters --profile=rust`          |
| `--rust` / `--ts` / `--python` / `--go` / `--docs` / `--shell` | Enable specific stack(s); suppresses auto-detection                             | `formatters --rust --go`             |
| `--all`                                                        | Install every supported stack's configs regardless of detection                 | `formatters --all`                   |

Flags are composable. See `references/flag-reference.md` for the full matrix and precedence rules. See `references/best-practices.md` for per-language tool rationale.

## Task

Execute the phases in order. Phases are short — do not add narrative prose between them.

### Phase 0 — Parse flags

Extract booleans from `$ARGUMENTS`:

- `DRY_RUN`, `FORCE`, `YES`, `CI`, `NO_AUTOFIX`, `HOOKS`, `NO_ALIASES`, `NO_DOCS`
- `TARGET` — value of `--target=<dir>`; default to `$PWD`
- `PROFILE` — value of `--profile=<lang>`; empty if unset
- Per-stack booleans: `RUST`, `TS`, `PYTHON`, `GO`, `DOCS`, `SHELL`; `ALL` for `--all`
- `SYNC_MODE` — true if `--sync` passed; `COPY_MODE` — true if `--copy` passed

Validation:

- Reject both `--sync` and `--copy` passed together.
- If `TARGET` does not exist as a directory, abort.

### Phase 1 — Profile

Run `${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/profile-style.sh "$TARGET"` and write the output to a temp file (e.g., `mktemp`). Parse it into variables using awk/grep.

Stack-flag resolution:

- If `ALL=true` → enable all per-stack flags.
- Else if `PROFILE` is set → force per-stack flags from the profile mapping (see `references/flag-reference.md` `--profile` table).
- Else if any explicit per-stack flag was passed → use only the ones passed; do NOT override with auto-detection.
- Else → enable each stack whose `detect_*=true` in the profile.

Mode resolution:

- If `SYNC_MODE` → use `--sync`.
- Else if `COPY_MODE` → use `--copy`.
- Else if `has_style_bundle=true` → use `--sync`.
- Else → use `--copy`.

### Phase 2 — Plan preview

Print a plan block listing what will happen. Format:

```
Target:            <TARGET>
Mode:              --sync  |  --copy
Stacks:            rust, ts, python, go, docs, shell
Bundle install:    scripts/style.sh, scripts/format.sh, scripts/lint.sh, scripts/init-formatters.sh,
                   scripts/install-shellcheck.sh, scripts/go-tools.sh, scripts/lib/*,
                   scripts/templates/*  (managed bundle files)
Tool configs:      rustfmt.toml, clippy.toml, .golangci.yml, biome.json, tsconfig.json, package.json*,
                   pyproject.toml*, .markdownlint.json, .markdownlintignore, .prettierrc, .prettierignore
                   (* stack-aware scaffold / refuses to overwrite existing)
Aliases:           (skipped if --no-aliases)  package.json / Makefile / justfile
Docs:              (skipped if --no-docs)     README.md / CONTRIBUTING.md / AGENTS.md / CLAUDE.md
CI workflows:      (only if --ci)             .github/workflows/lint.yml
                                               .github/workflows/lint-autofix.yml (unless --no-autofix)
Pre-commit hook:   (only if --hooks)          lefthook.yml or .husky/pre-commit
```

Note each item that will be skipped (existing config, manifest detected, etc.).

### Phase 3 — Dry-run / Confirm gate

- If `DRY_RUN=true` → run each sub-script with `--dry-run` to preview the writes, then STOP.
- Else if `YES=false` and `FORCE=false` → ask the user "Proceed with install? (yes / no)"; abort on anything other than an affirmative.
- Else proceed.

### Phase 4 — Install bundle + tool configs

Invoke the self-contained installer shipped inside the skill:

```
STYLE_SH="${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/bundle/style.sh"
```

Build `init_args`:

- Mode flag: `--sync` or `--copy` per Phase 1.
- `--target "$TARGET"`.
- Per-stack flags: for each enabled stack, append `--rust|--ts|--python|--go|--docs|--shell` as appropriate.
- Overwrite policy: `--force` if `FORCE=true`, `--yes` if `YES=true`, `--dry-run` never (dry-run is handled in Phase 3).

Run:

```
"$STYLE_SH" init "${init_args[@]}"
```

Surface its stdout. If it exits non-zero, STOP and surface the error verbatim.

### Phase 5 — Aliases, docs, CI, hooks (parallel-safe, sequential-ok)

Unless suppressed, run each applier. Each writes to a distinct file so they can run sequentially with no conflicts. For each, prefer `--force` when `FORCE=true`.

1. **Aliases** (skipped if `NO_ALIASES=true`):

   ```
   ${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/apply-aliases.sh --target "$TARGET" [--force]
   ```

2. **Docs** (skipped if `NO_DOCS=true`):

   ```
   ${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/apply-docs.sh --target "$TARGET" --profile-file "$PROFILE_FILE" [--force]
   ```

3. **CI** (only when `CI=true`):

   ```
   ${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/apply-ci.sh --target "$TARGET" --profile-file "$PROFILE_FILE" [--force] [--no-autofix]
   ```

   Pass `--no-autofix` when `NO_AUTOFIX=true` to install only the check workflow. The check workflow runs on every PR and on pushes to the default branch and `release/**`. The autofix workflow runs on same-repo PRs to the default branch (`origin/HEAD`, falling back to `main`), applies `./scripts/style.sh format` + `lint --fix`, and pushes fixes back as `github-actions[bot]`; fork PRs are skipped because `GITHUB_TOKEN` cannot push to them.

4. **Hooks** (run when `HOOKS=true`, OR when the target already has a `lefthook.yml` / `.husky/pre-commit` — i.e., `has_lefthook=true` or `has_husky=true` in the profile):

   ```
   ${CURSOR_PLUGIN_ROOT}/skills/formatters/scripts/apply-hooks.sh --target "$TARGET" --profile-file "$PROFILE_FILE" [--force]
   ```

   The auto-trigger keeps managed `style-lint` / `style-format` commands in sync on every `--sync` re-run without forcing first-time hook installation on users who never asked for it. `apply-hooks.sh` is idempotent: when managed commands are already present, it logs a no-op; otherwise it merges them in (lefthook) or skips if a non-empty `.husky/pre-commit` exists without `--force` (husky).

If any applier exits non-zero, report the failure and continue with the remaining ones — do not let a single applier abort the whole run.

### Phase 6 — Summary report

Produce a summary with these sections:

- **Bundle install** — lines from `style.sh init` (created, overwritten, skipped counts).
- **Tool configs** — per-stack: written / skipped-existing / refused-to-overwrite (for `pyproject.toml`).
- **Aliases** — strategy chosen (package-json / makefile / justfile) and alias keys installed.
- **Docs** — which file was appended or created; section name.
- **CI** — paths written (`lint.yml` always; `lint-autofix.yml` unless `--no-autofix`), or "not requested".
- **Hooks** — tool used (lefthook / husky / native), path written, or "not requested".
- **Next steps** — any of:
  - `git config commit.template .gitmessage` (unrelated to this skill but often useful alongside)
  - `lefthook install` (if `--hooks` + lefthook chosen)
  - Review `scripts/` bundle in the first commit that adds it
  - Re-run with `formatters --sync` after upstream bundle changes
  - Bypass a single hook run: `git commit --no-verify`

## Important Notes

- **Source of truth is `scripts/style.sh`.** This skill is an orchestrator; it never reimplements linter dispatch. Upgrading the upstream bundle propagates to installed targets via `formatters --sync`.
- **Never overwrites user-authored configs silently.** `apply-aliases.sh` preserves existing `package.json` scripts unless `--force`. `style.sh init-formatters.sh` refuses to overwrite an existing `pyproject.toml`. Tool configs (prettier, biome, markdownlint, clippy, rustfmt) are skipped when present unless `--force`.
- **Detection is ignore-aware.** Auto-detection enumerates only project source — git-tracked and untracked-but-not-gitignored files (via `git ls-files`), or a `find` fallback in non-git dirs — and skips well-known vendored/build directories (`node_modules`, `dist`, `build`, `vendor`, `.venv`, caches, …). A stray `*.rs`/`*.py` inside `node_modules/` or a build-output tree no longer flips `detect_*` to `true`. A vendored tree that is committed **and not gitignored** is still seen as source; list it in a root `.style-excludes` file (or `STYLE_EXTRA_EXCLUDES`) to drop it from detection and linting. See `references/stack-detection.md`.
- **`--hooks` is opt-in.** Hooks change commit behavior repo-wide. The installer always prints the `git commit --no-verify` escape.
- **Re-entrancy.** Re-running the skill with `--sync` on an already-installed target is a no-op for unchanged files, and prunes managed files removed upstream. Safe to schedule periodically.
- **Runtime-neutral aliases.** When the target has no `package.json`, the skill installs Makefile targets instead. Node is never required downstream.
- **Composing with `/init`.** `/init --formatters` delegates here and passes through `--dry-run` and `--force`. Invoke this skill directly for full flag coverage (CI, hooks, per-stack overrides).
- For per-language tool rationale (why biome over eslint, ruff over flake8, etc.), see `references/best-practices.md`.
