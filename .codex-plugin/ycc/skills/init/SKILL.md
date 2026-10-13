---
name: init
description: Initializes project AI-agent docs and workspace conventions. Use when
  generating agent rules docs, adding GitHub templates, or bootstrapping project rules.
---

# Codex CLI Workspace Initialization

Profiles the project, authors the AI-agent doc trio (AGENTS.md, AGENTS.md, .cursor/rules/project.mdc), and optionally emits GitHub issue templates and git convention files — all flag-driven, non-destructive by default.

## Current Project Context

- **Working Directory**: !`pwd`
- **Project Files**: !`ls -la 2>/dev/null | head -25`
- **Profile detection**: !`~/.codex/plugins/ycc/skills/init/scripts/profile-project.sh 2>/dev/null | head -20`

## Arguments

| Flag                        | Meaning                                                                            | Example                                |
| --------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------- |
| `--dry-run`                 | Preview every planned file; make no writes                                         | `$init --dry-run`                  |
| `--docs-only`               | Skip MCP/agent selection; emit doc trio only                                       | `$init --docs-only`                |
| `--templates`               | Also emit `.github/` issue forms, PR template, labels                              | `$init --templates`                |
| `--git`                     | Also emit `.gitignore`, `.gitmessage`, commitlint (JS/TS), and the lefthook bundle | `$init --git`                      |
| `--vendor-neutral`          | Also emit `.ai/rules/project.md` mirror of Cursor rule                             | `$init --vendor-neutral`           |
| `--formatters`              | Also bootstrap lint/format via `formatters` (scripts, configs, aliases, docs)  | `$init --formatters`               |
| `--release-model[=<model>]` | Run `release-model` without asking when `RELEASING.md` is missing              | `$init --release-model=trunk-only` |
| `--no-release-model`        | Never offer `release-model`                                                    | `$init --no-release-model`         |
| `--update`                  | Structured refresh of existing artifacts (merge/migrate, never clobber)            | `$init --update`                   |
| `--force`                   | Overwrite existing files without prompting                                         | `$init --force`                    |
| `--profile=<lang>`          | Override detected language (`rust`, `ts-node`, `python`, `go`, `mixed`, `empty`)   | `$init --profile=rust`             |

Flags are composable. See `references/flag-reference.md` for the full matrix.

## Task

Execute the following phases in order. Phases are short — do not add narrative prose between steps.

### Phase 0 — Parse flags

Extract mode booleans from `$ARGUMENTS`:

- `DRY_RUN` — true if `--dry-run` present
- `DOCS_ONLY` — true if `--docs-only` present
- `TEMPLATES` — true if `--templates` present
- `GIT` — true if `--git` present
- `VENDOR_NEUTRAL` — true if `--vendor-neutral` present
- `FORMATTERS` — true if `--formatters` present
- `RELEASE_MODEL` — true if `--release-model` or `--release-model=<model>` present
- `RELEASE_MODEL_VALUE` — `<model>` from `--release-model=<model>`, else empty. Must be `trunk-only` or `release-branches`; any other value is an error before any phase runs.
- `NO_RELEASE_MODEL` — true if `--no-release-model` present. Combining it with `--release-model` is an error before any phase runs.
- `UPDATE` — true if `--update` present
- `FORCE` — true if `--force` present
- `PROFILE` — value of `--profile=<lang>` if provided, else empty

Defaults: all booleans off; no profile override. `--update` and `--force` are mutually reinforcing: `--update` controls merge/migrate behavior, `--force` controls conflict resolution. Without either, existing files are preserved with a diff-and-ask prompt.

### Phase 1 — Profile

1. Run `~/.codex/plugins/ycc/skills/init/scripts/profile-project.sh` and parse the `key=value` output into variables. See `references/project-profile-heuristics.md` for the key list.
2. If `PROFILE` flag is set, override `primary_language` with that value.
3. If `is_empty=true` OR `primary_language=unknown`: ask the user conversationally for project name, purpose, and primary language. Set `project_name`, `project_purpose`, and `primary_language` from their answers.
4. If `UPDATE=false` AND at least two of `has_claude_md`, `has_agents_md`, `has_cursor_rules`, `has_issue_templates`, `has_gitmessage`, `has_gitignore` are true: warn the user "Existing doc/workflow files detected — consider re-running with `--update` for structured refresh, or `--force` to overwrite. Continuing with default skip-on-conflict behavior."
5. Surface the resolved profile summary to the user and wait for confirmation before writing anything — except when `DRY_RUN=true`, which proceeds directly to preview.

### Phase 2 — Optional deep analysis

Skip this phase when `DOCS_ONLY=true`.

Otherwise, estimate source file count:

```bash
find . -type f | head -n 51 | wc -l
```

If count is 51 (i.e., >50 files), dispatch `codebase-research-analyst` with a prompt requesting:

- Key architectural patterns and conventions to encode in `AGENTS.md`
- Critical commands (test, lint, build, deploy) to embed
- Project-specific MUST/MUST NOT rules worth adding

Feed the agent's output into the AGENTS.md rendering in Phase 3.

### Phase 3 — Render templates

Load each applicable `.tmpl` file from `~/.codex/plugins/ycc/skills/init/templates/`. Substitute all `{{PLACEHOLDER}}` variables using profile values from Phase 1 (and Phase 2 if run). For language-conditional blocks (`{{#IF_RUST}}...{{/IF_RUST}}` etc.), include only the block matching `primary_language`. Leave `{{#IF_RELEASE_MODEL}}...{{/IF_RELEASE_MODEL}}` blocks (in `AGENTS.md.tmpl` and `github/labels.md.tmpl`) unresolved — Phase 5 (dry run) or Phase 5.5 resolves them. Render all files in memory — do NOT write yet.

Rendering map:

| Condition                                                      | Source template                              | Target path                                  |
| -------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------- |
| Always                                                         | `AGENTS.md.tmpl`                             | `AGENTS.md`                                  |
| Always                                                         | `AGENTS.md.tmpl`                             | `AGENTS.md`                                  |
| Always                                                         | `cursor-rule.mdc.tmpl`                       | `.cursor/rules/project.mdc`                  |
| `VENDOR_NEUTRAL=true`                                          | `ai-rule.md.tmpl`                            | `.ai/rules/project.md`                       |
| `TEMPLATES=true`                                               | `github/bug_report.yml.tmpl`                 | `.github/ISSUE_TEMPLATE/bug_report.yml`      |
| `TEMPLATES=true`                                               | `github/feature_request.yml.tmpl`            | `.github/ISSUE_TEMPLATE/feature_request.yml` |
| `TEMPLATES=true`                                               | `github/docs_request.yml.tmpl`               | `.github/ISSUE_TEMPLATE/docs_request.yml`    |
| `TEMPLATES=true`                                               | `github/config.yml.tmpl`                     | `.github/ISSUE_TEMPLATE/config.yml`          |
| `TEMPLATES=true`                                               | `github/pull_request_template.md.tmpl`       | `.github/pull_request_template.md`           |
| `TEMPLATES=true`                                               | `github/labels.md.tmpl`                      | `.github/labels.md`                          |
| `TEMPLATES=true`                                               | `github/copilot-instructions.md.tmpl`        | `.github/copilot-instructions.md`            |
| `TEMPLATES=true`                                               | `github/workflows/pr-title.yml.tmpl`         | `.github/workflows/pr-title.yml`             |
| `TEMPLATES=true`                                               | `github/workflows/pr-title-autofix.yml.tmpl` | `.github/workflows/pr-title-autofix.yml`     |
| `GIT=true`                                                     | `git/gitignore.tmpl`                         | `.gitignore`                                 |
| `GIT=true`                                                     | `git/gitmessage.tmpl`                        | `.gitmessage`                                |
| `GIT=true`                                                     | `git/lefthook.yml.tmpl`                      | `lefthook.yml`                               |
| `GIT=true`                                                     | `git/install-lefthook.sh.tmpl`               | `scripts/install-lefthook.sh`                |
| `GIT=true`                                                     | `git/lefthook-usage.md.tmpl`                 | `docs/lefthook-usage.md`                     |
| `GIT=true` AND `primary_language` in `{typescript,javascript}` | `git/commitlint.config.cjs.tmpl`             | `commitlint.config.cjs`                      |

**Language-block selection**: for every template except `gitignore.tmpl`, include only the block matching `primary_language`. For `gitignore.tmpl`, include every block whose language appears in `primary_language` or `secondary_languages` (comma-separated) so mixed-stack repos get every applicable section. For `gitignore.tmpl`, `javascript` is treated as `typescript` for `{{#IF_TS}}` activation; `terraform` activates `{{#IF_TERRAFORM}}`.

See `references/template-library.md` for placeholder definitions.

### Phase 4 — MCP/agent selection

Skip this phase when `DOCS_ONLY=true`.

Run the catalog generators:

```bash
~/.codex/plugins/ycc/skills/init/scripts/generate-mcp-catalog.sh
~/.codex/plugins/ycc/skills/init/scripts/generate-agent-catalog.sh
```

Present all available options as checkboxes organized by category. Pre-check items that align with the detected profile (language, infrastructure, workflow). Let the user freely adjust the selection before proceeding.

### Phase 5 — Dry-run check

If `DRY_RUN=true`:

- Print a listing of every planned file with a preview snippet (first ~15 lines each). Resolve `IF_RELEASE_MODEL` blocks as kept when `has_releasing_md=true` or `RELEASE_MODEL=true`, else drop them.
- Show the planned `.mcp.json` content.
- List agent files that would be copied.
- Print the release-model step Phase 5.5 would take: "skip (RELEASING.md exists)", "skip (--no-release-model)", "would run `release-model` [--model <value> --yes]", or "would offer `release-model`".
- STOP — make no writes.

### Phase 5.5 — Release model

Decide whether to create `RELEASING.md` (the project's branching and release rules — see `~/.codex/plugins/ycc/shared/references/branching-model.md`), then resolve the `IF_RELEASE_MODEL` blocks.

1. **Choose the action** (first match wins):
   - `has_releasing_md=true` → skip. The project already has a release model; init reads only its presence (`$release-model --audit` validates it).
   - `NO_RELEASE_MODEL=true` → skip.
   - `RELEASE_MODEL=true` → run without asking.
   - `DOCS_ONLY=true` (and no `--release-model`) → skip; `--docs-only` stays limited to the doc trio.
   - Otherwise → ask: "This project has no `RELEASING.md`. Run `release-model` to choose a branching and release model (trunk-only or release branches) and write one?" Default: yes. A missing `RELEASING.md` never blocks init — "no" continues normally.
2. **Run** the `release-model` skill when chosen. With `RELEASE_MODEL_VALUE` set, pass `--model <value> --yes`: the model was decided upstream (for example by `blueprint`), so the proposal is accepted without questions. Otherwise run it without arguments so it can propose a model from the repo's signals and confirm with the user.
3. **Resolve** every `IF_RELEASE_MODEL` block rendered in Phase 3: keep the block contents when `RELEASING.md` now exists at the project root, else drop the block. This covers "exists already" and "created in this run", and drops the pointer if `release-model` was declined or failed.
4. If `release-model` errors, record the failure for the Phase 7 summary and continue — do not abort init.

### Phase 6 — Apply

For each rendered file from Phase 3, apply the resolution rule below. Never silently clobber user content.

**Target does not exist** → write the rendered file.

**Target exists AND `FORCE=true`** → overwrite and log the path.

**Target exists AND `UPDATE=true`** → structured refresh per artifact type:

| Artifact                                               | Update behavior                                                                                                                                                                                               |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AGENTS.md`                                            | Parse existing `##`-level section headings. Append any template sections that are missing. Preserve all existing content verbatim. Report the appended section list.                                          |
| `AGENTS.md` (pointer, `agents_md_is_pointer=true`)     | Refresh pointer boilerplate text. Preserve any user-authored content under `## Agent-runtime notes`.                                                                                                          |
| `AGENTS.md` (custom, `agents_md_is_pointer=false`)     | Ask the user: (a) migrate to pointer — preserve original content under `## Agent-runtime notes` and write canonical pointer, or (b) merge — append missing sections, keep existing content. Default: migrate. |
| `.cursor/rules/project.mdc`                            | Overwrite body content; preserve any non-standard frontmatter keys the user added beyond `description`, `globs`, `alwaysApply`.                                                                               |
| `.cursorrules` (legacy, `has_legacy_cursorrules=true`) | Migrate: read legacy content, write `.cursor/rules/project.mdc` (creating it if absent, merging otherwise), then advise the user to delete `.cursorrules` (do not delete automatically).                      |
| `.ai/rules/project.md`                                 | Same rule as `.cursor/rules/project.mdc` body.                                                                                                                                                                |
| `.github/ISSUE_TEMPLATE/*.yml`                         | Per template: if missing → create; if present → show diff and default to skip (issue forms are often customized). `--update --force` overwrites.                                                              |
| `.github/pull_request_template.md`                     | Show diff; default skip. `--update --force` overwrites.                                                                                                                                                       |
| `.github/labels.md`                                    | Always overwrite (reference doc, safe to refresh).                                                                                                                                                            |
| `.github/copilot-instructions.md`                      | Show diff; default skip (users customise agent-facing rules). `--update --force` overwrites.                                                                                                                  |
| `.github/workflows/pr-title.yml`                       | Show diff; default skip (users may customise the Conventional Commits type list or branch filters). `--update --force` overwrites.                                                                            |
| `.github/workflows/pr-title-autofix.yml`               | Show diff; default skip (users may tune the placeholder regex, the type-normalization pass, or the draft-toggle behaviour). `--update --force` overwrites.                                                    |
| `.gitignore`                                           | Show diff; default skip (users curate this file heavily). `--update --force` overwrites. When `has_gitignore=true` at Phase 1, warn the user the file already exists.                                         |
| `.gitmessage`                                          | Show diff; default skip. `--update --force` overwrites (usually safe — it is a reference template).                                                                                                           |
| `commitlint.config.cjs`                                | If present → show diff and default skip with a warning ("commitlint rules are often project-customized"). `--update --force` overwrites.                                                                      |
| `lefthook.yml`                                         | Show diff; default skip (users often extend the config with project-specific commands). `--update --force` overwrites. When `has_lefthook_config=true` at Phase 1, warn the user the file already exists.     |
| `scripts/install-lefthook.sh`                          | Always overwrite (managed bootstrap tooling; tracks upstream improvements).                                                                                                                                   |
| `docs/lefthook-usage.md`                               | Always overwrite (managed reference doc).                                                                                                                                                                     |

**Target exists AND `UPDATE=false` AND `FORCE=false`** → show a unified diff, then prompt the user with three choices: overwrite, merge (only meaningful for `AGENTS.md`), or skip. Default choice: skip.

Then apply MCP/agent selections from Phase 4 (skipped when `DOCS_ONLY=true`):

```bash
${HOME}/.codex/mcp-library/generate-mcp-config.sh <selected-mcps>
```

Create `.claude/agents/` if needed; copy selected agent files from `${HOME}/.codex/agents/`.

### Phase 6.5 — Formatter bootstrap (when `FORMATTERS=true`)

When `FORMATTERS=true`, invoke the `formatters` skill to bootstrap the lint/format environment. Pass through `--dry-run` and `--force`; let the skill handle its own flag defaults for everything else (stack detection, sync vs copy, aliases, docs). Do NOT duplicate formatter logic here — the formatters skill owns every decision about scripts, tool configs, aliases, and docs.

If `DRY_RUN=true`, invoke `formatters --dry-run` and merge its preview output into the Phase 7 summary. Otherwise invoke `formatters` normally.

If the formatters skill exits with an error, record the failure in the Phase 7 summary and continue — do not let a formatter error abort the overall init run.

### Phase 7 — Summary report

Produce a summary using `~/.codex/plugins/ycc/skills/init/templates/workspace-report.md` as the base. Extend it with these sections appended after the existing MCP/agents tables:

**Docs emitted** — list each path written, or "skipped: user chose keep".

**GitHub templates emitted** — list each `.github/` path written (omit section if `TEMPLATES=false`).

**Git conventions emitted** — list each git artifact path written (omit section if `GIT=false`).

**Release model** — the Phase 5.5 outcome: `RELEASING.md` created (with the chosen model), already present, skipped (and why), declined, or failed (with the error).

**Next steps** — suggest:

- `git config commit.template .gitmessage` (if `GIT=true`)
- Review the generated `.gitignore` — confirm language sections match the stack and add project-specific entries (secrets files, generated assets, local scratch dirs). Rust libraries should un-comment the `Cargo.lock` ignore line (if `GIT=true`).
- `bash scripts/install-lefthook.sh` to install the `lefthook` binary and activate the hooks defined in `lefthook.yml` (if `GIT=true`). Re-runnable on every checkout; safe to rerun.
- For JS/TS projects: run `{{PACKAGE_MANAGER}} install` (devDependencies `@commitlint/cli` + `@commitlint/config-conventional` must be installed for the `commit-msg` hook to work).
- Review `.github/labels.md` and run the `gh label create` commands listed there (if `TEMPLATES=true`). Under the release-branches model, create one `backport:X.Y` label per maintenance branch.
- Review `RELEASING.md` and commit it with the rest of the init output (if Phase 5.5 created it). If the offer was declined, `$release-model` can create it later.
- Review `.github/copilot-instructions.md` — it restates the PR-workflow rules for GitHub Copilot's coding agent. Adjust to match project-specific conventions (e.g., if the repo customises the Conventional Commits type list, update the allowed-types line) (if `TEMPLATES=true`).
- Enable the PR title check as a required status: **Settings → Branches → Branch protection rules**, add `Validate Conventional Commit PR title` (the job name from `.github/workflows/pr-title.yml`) to the required checks. Without this, the workflow runs but isn't enforced (if `TEMPLATES=true`).
- `.github/workflows/pr-title-autofix.yml` runs alongside the validator and (1) strips placeholder prefixes (`[WIP]`, `Draft:`, `Initial plan`) from PR titles server-side, then (2) normalizes a leading Conventional Commit type that was written without a colon or with capitalization (e.g. `Refactor X` → `refactor: X`, `Feat(auth): X` → `feat(auth): X`). Runs because GitHub Copilot's coding-agent token often lacks `pull_requests:write` and cannot self-correct. Do **not** add this workflow to required checks — it is an auto-correcting side effect, not a gate (if `TEMPLATES=true`).
- Open `AGENTS.md` to review and refine the generated project rules.
- If `has_legacy_cursorrules=true` and the migration ran: delete the legacy `.cursorrules` file once the new `.cursor/rules/project.mdc` is confirmed working.

## Important Notes

- Default behavior never destroys existing files; always diff-and-ask before overwriting.
- `--update` enables structured merge/migrate semantics and is the recommended flag when re-running `init` in a project that already has docs/templates.
- `--force` is opt-in and always logs every path it overwrote. `--update --force` applies merge semantics but overwrites on conflict instead of skipping.
- No new agents are registered. `codebase-research-analyst` is called only once, conditionally, for large existing repos (>50 source files) when `--docs-only` is not set.
- The MCP and agent selection flow is preserved unchanged behind `--docs-only`.
- A missing `RELEASING.md` never blocks init. Phase 5.5 only offers `release-model`; `--release-model` runs it and `--no-release-model` silences the offer.
- For the full flag matrix with composability examples, see `references/flag-reference.md`.
