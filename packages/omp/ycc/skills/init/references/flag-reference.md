# Flag Reference

## Contents

- Flag Matrix
- Per-Flag Examples
- Composition Rules

Detailed reference for every flag accepted by `/skill:init`. See also `SKILL.md` for the live phase logic.

---

## Flag Matrix

| Flag                        | Default     | Affects phases | Writes to                                                                                                                                                                                         | Example                                    |
| --------------------------- | ----------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `--dry-run`                 | off         | 5 (halt)       | nothing                                                                                                                                                                                           | `/skill:init --dry-run`                       |
| `--docs-only`               | off         | 2, 4 (skip)    | `AGENTS.md`, optional `CLAUDE.md`                                                                                                                                                                 | `/skill:init --docs-only`                     |
| `--templates`               | off         | 3 (extend)     | `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md`, `.github/labels.md`, `.github/copilot-instructions.md`, `.github/workflows/pr-title.yml`, `.github/workflows/pr-title-autofix.yml` | `/skill:init --templates`                     |
| `--git`                     | off         | 3 (extend)     | `.gitignore`, `.gitmessage`, `commitlint.config.cjs` (JS/TS only), `lefthook.yml`, `scripts/install-lefthook.sh`, `docs/lefthook-usage.md`                                                        | `/skill:init --git`                           |
| `--vendor-neutral`          | off         | 3 (extend)     | `.ai/rules/project.md` (pointer to `AGENTS.md`)                                                                                                                                                   | `/skill:init --vendor-neutral`                |
| `--formatters`              | off         | 6.5 (delegate) | (delegates to `/skill:formatters` — see its flag matrix)                                                                                                                                             | `/skill:init --formatters`                    |
| `--release-model[=<model>]` | off (offer) | 5.5 (delegate) | `RELEASING.md` (via `/skill:release-model`)                                                                                                                                                          | `/skill:init --release-model=trunk-only`      |
| `--no-release-model`        | off         | 5.5 (skip)     | nothing                                                                                                                                                                                           | `/skill:init --no-release-model`              |
| `--migrate-rules`           | off         | 5.7 (migrate)  | `AGENTS.md` (moved content), `CLAUDE.md` (pointer) — preview only with `--dry-run`                                                                                                                | `/skill:init --migrate-rules --dry-run`       |
| `--allow-non-git`           | off         | 5.7            | timestamped backups of the rules files before migrating outside git                                                                                                                               | `/skill:init --migrate-rules --allow-non-git` |
| `--no-claude-md`            | off         | 3              | skips the `@AGENTS.md` CLAUDE.md shim (needs Claude Code 2.1.277+)                                                                                                                                | `/skill:init --no-claude-md`                  |
| `--update`                  | off         | 6 (merge)      | existing targets only                                                                                                                                                                             | `/skill:init --update`                        |
| `--force`                   | off         | 6 (overwrite)  | all target files                                                                                                                                                                                  | `/skill:init --force`                         |
| `--profile=<name>`          | auto-detect | 1 (skip)       | (drives template variables)                                                                                                                                                                       | `/skill:init --profile=rust`                  |

### `--profile` accepted values

| Value     | Skips detection? | Effect                                                              |
| --------- | ---------------- | ------------------------------------------------------------------- |
| `rust`    | yes              | Sets `PRIMARY_LANG=rust`, `BUILD_CMD=cargo build`                   |
| `ts-node` | yes              | Sets `PRIMARY_LANG=typescript`, `PACKAGE_MANAGER=npm/pnpm/yarn/bun` |
| `python`  | yes              | Sets `PRIMARY_LANG=python`                                          |
| `go`      | yes              | Sets `PRIMARY_LANG=go`, `BUILD_CMD=go build ./...`                  |
| `mixed`   | yes              | Sets primary + secondary from manifest count                        |
| `empty`   | yes              | Triggers name/purpose/language prompts                              |

---

## Per-Flag Examples

### `--dry-run`

Preview everything without writing a single file. Combines with any other flag.

```
/skill:init --dry-run
/skill:init --dry-run --templates --git
```

Output: a table of planned files with their rendered content previewed inline.

### `--docs-only`

Emit canonical `AGENTS.md` and optional Claude-only/path-scoped files; skip MCP/agent selection (phase 4) and profiler agent dispatch (phase 2).

```
/skill:init --docs-only
/skill:init --docs-only --profile=go
```

### `--templates`

Adds the full GitHub templates bundle. Extends the default run or combines with `--docs-only`:

- `.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`,
  `docs_request.yml`, `config.yml` — YAML issue forms
- `.github/pull_request_template.md` — PR template with a required-check
  preamble pointing at the PR-title workflow and copilot instructions
- `.github/labels.md` — reference list of the project's label taxonomy
  (`gh label create` commands included)
- `.github/copilot-instructions.md` — a short pointer to `AGENTS.md` plus the
  detected commands (test / lint / build), for GitHub Copilot's coding agent
- `.github/workflows/pr-title.yml` — required GitHub Actions check that
  validates PR titles as Conventional Commits and rejects placeholder
  prefixes (`[WIP]`, `Draft:`, `Initial plan`) that agents often open PRs
  with. Enable as a required status check in branch protection — see the
  `--templates` next-step emitted at end of `/skill:init`.
- `.github/workflows/pr-title-autofix.yml` — runs alongside the validator
  in two passes, server-side using the repo's `GITHUB_TOKEN`: (1) strips
  placeholder prefixes and toggles the PR to draft; (2) normalizes a
  leading Conventional Commit type that was written without a colon or
  with capitalization (e.g. `Refactor X` → `refactor: X`,
  `Feat(auth): X` → `feat(auth): X`). Exists because GitHub Copilot's
  coding-agent token typically lacks `pull_requests:write` and cannot
  fix its own title after the instructions file has been ignored. Not a
  required check — it is an auto-correcting side effect.

```
/skill:init --templates
/skill:init --docs-only --templates
```

### `--git`

Adds the full git-conventions bundle:

- `.gitignore` (always) — best-practices universal entries (OS, editors, env
  files, secrets, agent scratch) **plus** language-specific blocks activated
  by `primary_language` and any `secondary_languages` (rust, go, python,
  node/ts, terraform). Respects `--profile=<lang>` override.
- `.gitmessage` (always) — Conventional Commits template. Wire with
  `git config commit.template .gitmessage`.
- `commitlint.config.cjs` (JS/TS ecosystems only) — enforced via the
  lefthook `commit-msg` hook below.
- `lefthook.yml` (always) — git hook manager config with stack-specific
  pre-commit lint/format commands (staged scope), a `pre-push` test stage,
  and a commitlint `commit-msg` stage on JS/TS projects.
- `scripts/install-lefthook.sh` (always) — idempotent, cross-platform
  bootstrap. Installs the `lefthook` binary and runs `lefthook install`.
- `docs/lefthook-usage.md` (always) — reference doc explaining what the
  hooks do, how to extend them, how to bypass, and how they skip in CI.

```
/skill:init --git
/skill:init --git --profile=ts-node
```

### `--vendor-neutral`

Add `.ai/rules/project.md` — a one-line pointer to the canonical `AGENTS.md` for vendor-neutral tooling.

```
/skill:init --vendor-neutral
```

### `--release-model[=<model>]` / `--no-release-model`

Phase 5.5 handles projects without a repo-root `RELEASING.md` (profile key
`has_releasing_md=false`). By default it **offers** to run `/skill:release-model`, which
chooses a branching and release model and writes `RELEASING.md`. When the file already
exists, nothing runs.

- `--release-model` — run `/skill:release-model` without asking. It proposes a model from the
  repo's signals and confirms with you.
- `--release-model=<model>` — `<model>` is `trunk-only` or `release-branches`. Runs
  `/skill:release-model --model <model> --yes`, accepting the proposal without questions.
  `/skill:blueprint` emits this form from its `release_model` bootstrap key.
- `--no-release-model` — never offer. Conflicts with `--release-model` (error).
- `--docs-only` skips the offer unless `--release-model` is also passed.
- `--dry-run` only reports what Phase 5.5 would do.

When `RELEASING.md` exists after Phase 5.5 (already present or just created), the
rendered `AGENTS.md` gains a `## Branching & releases` pointer section and
`.github/labels.md` (with `--templates`) gains the `backport:X.Y` label family. Both come
from `{{#IF_RELEASE_MODEL}}` blocks — see `template-library.md`.

```
/skill:init --release-model
/skill:init --templates --release-model=release-branches
/skill:init --no-release-model
```

### `--migrate-rules`

Rules-only migration: profile, show the full unified diff and content-loss list, then ask
for approval. `--dry-run` changes nothing; `--force` never bypasses the migration prompt.
The helper must run at the git root, refuses dirty, git-ignored or symlinked rules files
(`--allow-non-git` opts in, with timestamped backups), and writes both files atomically.
Routing is by heading: exact Claude runtime headings stay in `CLAUDE.md` after
`@AGENTS.md`; everything else moves to `AGENTS.md`. Headings that merely mention Claude are
routed to `AGENTS.md` and listed as ambiguous. An existing `AGENTS.md` is merged, not
replaced, unless it is the short legacy pointer (its full text is shown). Review the
per-section routing, content-loss list and diff before approving.

```text
/skill:init --migrate-rules --dry-run
/skill:init --migrate-rules
```

### `--update`

Structured refresh of existing artifacts. Never clobbers user content — merges instead.

- `AGENTS.md`: append template sections that are missing; preserve everything else verbatim. A legacy pointer-style `AGENTS.md` (short, names `CLAUDE.md`) triggers the `--migrate-rules` offer instead.
- `CLAUDE.md`: never rewritten by `--update`. A long one triggers the `--migrate-rules` offer; an `@AGENTS.md` one is left as is.
- `.cursorrules` (legacy): fold project-specific lines into `AGENTS.md`; leaves the old file for you to delete.
- `.github/ISSUE_TEMPLATE/*.yml`: create missing templates; skip existing ones with a diff (pair with `--force` to overwrite).
- `.github/labels.md`, `docs/lefthook-usage.md`, `scripts/install-lefthook.sh`: always overwritten (managed reference docs / tooling).
- `commitlint.config.cjs`: diff + skip by default (often customized). Pair with `--force` to overwrite.
- `lefthook.yml`: diff + skip by default (users often extend the config). Pair with `--force` to overwrite.
- `.gitignore`: diff + skip by default (heavily customized per-project). Pair with `--force` to overwrite.

```
/skill:init --update
/skill:init --update --docs-only
/skill:init --update --force --templates
```

### `--force`

Overwrite existing files without prompting. Default behavior diffs and asks; never silently clobbers. Compose with `--update` to bias merges toward overwrite on conflict.

```
/skill:init --force --docs-only
/skill:init --update --force
```

### `--profile=<name>`

Pre-set the project profile, bypassing `profile-project.sh` detection entirely.

```
/skill:init --profile=python --templates --git
```

---

## Composition Rules

Flags are independent and composable. Any combination is valid:

- `--dry-run` is always safe — it suppresses all writes regardless of other flags.
- `--docs-only` narrows scope; adding `--templates` or `--git` extends it back out.
- `--force` applies to every output flag in the same invocation.
- `--profile=` and detection are mutually exclusive; `--profile=` wins.
- `--release-model` and `--no-release-model` are mutually exclusive (error).
- Unrecognised flags are reported as errors before any phase runs.

### Common combinations

| Combination                            | Result                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------- |
| `--docs-only --templates --git`        | Full doc/workflow bundle, no MCP/agent touch                              |
| `--dry-run --templates`                | Preview only the template output                                          |
| `--force --profile=python --templates` | Apply Python doc set + GitHub forms, overwrite freely                     |
| `--docs-only --vendor-neutral`         | Canonical rules + `.ai/rules/project.md` pointer, skip MCP                |
| `--update`                             | Refresh existing rules files in place; skip untouched files               |
| `--update --force --templates`         | Refresh everything aggressively — merge semantics + overwrite on conflict |

---
