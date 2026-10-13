---
name: releaser
disable-model-invocation: true
description: 'Prepares external-project releases, notes, and release CI. Use when cutting an application release, planning platform artifacts, or auditing a GitHub Actions release workflow.'
argument-hint: '[version] [--arch=list] [--os=list] [--ci-config[=generate|audit]] [--platform=name] [--skip-notes] [--dry-run] [--exclude-internal] [--publish[=create|edit|auto]] [--confirm] [--ci] [--ci-max-pushes=N] [--ci-max-same-failure=N] [--ci-timeout-min=N] [--ci-yes] [--ci-recut=destructive]'
allowed-tools:
  - Read
  - Grep
  - Glob
  - Write
  - Edit
  - Bash(git:*)
  - Bash(gh:*)
  - Bash(ls:*)
  - Bash(test:*)
  - Bash(cat:*)
  - Bash(find:*)
  - Bash(python3:*)
  - Bash(node:*)
  - Bash(go:*)
  - Bash(cargo:*)
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/*.sh:*)'
  - 'Bash(${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/*.sh:*)'
  - 'mcp__github__*'
---

# Generic Release Orchestrator

This skill prepares a release for **any** project: detects the toolchain, drafts a
changelog from conventional commits, plans platform/architecture artifacts, and — on
request — either generates a GitHub Actions release workflow or audits an existing one
against best practices. It emits the exact `git tag`, `git push`, and `gh release
create` commands the user runs; **it never commits, pushes, or publishes without an explicit `--publish` and `--confirm` from the user**.

> **Not for this bundle.** For `ycc` bundle releases use `ycc:bundle-release`, which is
> scoped to this repo's `plugin.json` + `marketplace.json` version-parity contract and
> the Cursor/Codex sync flow.

## Arguments

Parse `$ARGUMENTS`:

- **version** (optional first positional) — target semver (`1.4.0`, `v1.4.0`, or a
  pre-release like `1.4.0-rc.1`). If omitted, the skill proposes one from commit history
  (conventional-commit bump) and asks for confirmation before continuing.
- **--arch=\<list\>** — comma-separated target architectures (e.g. `amd64,arm64`).
  Overrides language defaults.
- **--os=\<list\>** — comma-separated target operating systems (e.g. `linux,darwin,windows`).
  Overrides language defaults.
- **--ci-config** / **--ci-config=generate** — scaffold a GitHub Actions release
  workflow under `.github/workflows/release.yml`. Fails if one already exists unless
  `--ci-config=audit` is also requested. (Renamed from `--ci` so the bare `--ci` flag
  matches the auto-fix-loop family used by `ycc:git-workflow`, `ycc:prp-pr`, and
  `ycc:pr-autofix`.)
- **--ci-config=audit** — invoke the `ycc:releaser` agent to read the existing
  release workflow(s) and emit an optimization report. Read-only.
- **--platform=\<name\>** — explicit toolchain override (`node`, `python`, `go`, `rust`,
  `docker`, `generic`). Skips auto-detection. Useful for monorepos.
- **--skip-notes** — skip drafting `CHANGELOG` updates and release notes.
- **--dry-run** — run detection and print the full release plan. Writes nothing,
  executes no state-changing commands.
- **--exclude-internal** — omit the Maintenance section from the drafted release notes
  entirely. Use only when the release truly has zero internal-only churn worth surfacing.
- **--publish[=create|edit|auto]** — after the user reviews the rendered notes, invoke
  `publish-release.sh` to preview or apply the `gh release` command. Default mode is
  `auto` (creates if no release exists, otherwise proposes `edit`). Use `edit` only to
  intentionally replace an existing release body — this is destructive.
- **--confirm** — when combined with `--publish`, re-runs the helper with `--confirm` to
  actually execute the `gh` command. The skill NEVER passes `--confirm` automatically.
- **--ci** — after a successful `--publish --confirm`, enter the bounded **Release CI
  auto-fix loop** (Phase 8.5): poll the release-event workflow run, classify failures,
  dispatch a fix agent on implicated files, commit + push, re-cut the release, and
  loop until green or a bail cap fires. No-op (with warning) if `--publish --confirm`
  did not succeed in this run. Shares contract with `ci-monitor.sh` / sibling skills.
- **--ci-max-pushes=N** — hard cap on autonomous fix-and-recut iterations per
  invocation. Default `5`. Forwarded to `release-ci-monitor.sh`.
- **--ci-max-same-failure=N** — bail after the same failure signature recurs N
  times. Default `3`. Forwarded to `release-ci-monitor.sh`.
- **--ci-timeout-min=N** — wall-clock cap in minutes from the first iteration.
  Default `30`. Forwarded to `release-ci-monitor.sh`.
- **--ci-yes** — skip the one-time Phase 8.5 authorization prompt. Use only for
  non-interactive callers; safety caps remain enforced.
- **--ci-recut=destructive** — opt in to the destructive re-cut fallback when the
  detected release workflow has no `workflow_dispatch` trigger. Without this flag,
  the loop refuses to enter when the only available re-cut path is
  `gh release delete --cleanup-tag` followed by re-publish.

## Phase 0: Preflight

Before anything else, verify:

1. Working directory is a git repo: `git rev-parse --show-toplevel` succeeds.
2. Working tree is clean: `git status --porcelain` is empty. If dirty, STOP and ask
   whether to stash or abort — never silently move forward with uncommitted changes.
3. `gh` is installed and authenticated when `--ci-config` is absent but the user
   asked for a GitHub release. Also required when `--ci` is set, since the
   auto-fix loop calls `gh run list`, `gh workflow run`, and `gh release` under
   the hood. Surface install/login hints if missing.
4. If `version` was provided, it matches the regex
   `^v?[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?(\+[A-Za-z0-9.-]+)?$`. Reject malformed
   input with a clear error.
5. Read the project's release model:

   ```
   ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/release-state.sh get
   ```

   - `present=0` (no `RELEASING.md`): say so once and offer to run `/ycc:release-model`
     first. If the user declines, continue exactly as this skill always has.
   - Exit 2 (malformed state block): STOP. Show the parse error and point at
     `/ycc:release-model --audit`. Never guess a trunk from a broken block.
   - `present=1`: keep `model` and `trunk`. The model's rules are in
     `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/branching-model.md`; how this skill
     applies them is in
     `${CLAUDE_PLUGIN_ROOT}/skills/releaser/references/release-branches.md`.

If any check fails, STOP and surface a specific remediation — do not continue past
Phase 0 with known-bad preconditions.

## Phase 1: Detect project

Run:

```
${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/detect-project.sh
```

The helper emits a single JSON document to stdout describing:

- `language` — primary language (`node`, `python`, `go`, `rust`, `docker`, `mixed`,
  `generic`).
- `build_system` — `npm` / `pnpm` / `yarn` / `poetry` / `uv` / `hatch` / `setuptools` /
  `cargo` / `go-modules` / `docker` / `none`.
- `manifest_files` — list of version-bearing files.
- `default_os` and `default_arch` — sensible defaults for that language.
- `existing_ci` — list of `.github/workflows/*.yml` files already present.
- `current_version` — extracted from the manifest, or `null` if not found.
- `latest_tag` — output of `git describe --tags --abbrev=0 2>/dev/null` or `null`.

If `--platform` was passed, override the detected `language` field before continuing.

`latest_tag` is the nearest tag reachable from `HEAD`. Under release-branches that is
the latest `vX.Y.*` tag on `release/X.Y`, but the previous minor's `.0` tag (or a
pre-release tag) on the trunk, because patch tags are not reachable from the trunk. See
"Previous tag and changelog range" in `references/release-branches.md` for when to pass
an explicit from-ref instead.

See `references/project-type-matrix.md` for the full language → toolchain → default
matrix.

## Phase 2: Propose version and compute bump

If the user did NOT supply a version:

1. Collect commits since `latest_tag` (or the last 50 if no tag exists):
   `git log <latest_tag>..HEAD --format="%s"`.
2. Classify each commit against conventional-commit types. Determine the bump:
   - Any `!` marker, `BREAKING CHANGE` footer, or `major:` → major.
   - Any `feat:` → minor.
   - Otherwise → patch.
3. Propose the next semver and ASK for confirmation before writing anything.

If the user DID supply a version, sanity-check the bump magnitude against commit
history. Surface a concern if they are mismatched (e.g. `feat:` commits but a patch
bump) and require explicit confirmation before continuing.

The release model (from `release-state.sh get`) decides how commit types map to the bump:

- **No RELEASING.md, or trunk-only:** the rules above apply as written. Every release is
  cut from the trunk, so `feat:` commits mean the next release is a minor; a patch
  requested over `feat:` commits gets the mismatch concern.
- **release-branches, on `release/X.Y`:** the branch bounds the bump to the next
  `X.Y.Z` patch. Everything on the branch is a deliberate backport, so a `feat:`
  cherry-pick is expected and does NOT raise the mismatch concern or make it a minor.
  Only a breaking change (`!` / `BREAKING CHANGE`) on the branch gets a warning: it
  should not have been backported. The patch is still the only valid version there.
- **release-branches, on the trunk:** propose only a minor or major. A fixes-only trunk
  still ships as the next minor; patches come from `release/X.Y`.

### Branch check

Once the version is confirmed, run:

```
${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/check-release-branch.sh <new-version>
```

- Exit 0: keep its `kind`, `branch`, `creates_maintenance`, `backport_label` and
  `forward_port` output for Phases 5, 7 and 8. With `present=0` it only prints a note
  on stderr that repeats Phase 0's; do not show it a second time.
- Exit 1: STOP. Show its stderr verbatim; it names the right branch and the exact fix
  commands (e.g. `git switch release/0.5`, or `git switch <trunk>`). Do not switch
  branches for the user.
- Exit 2: STOP with the parse error, as in Phase 0.

### Backport gate (patch under release-branches)

When the branch check reports `model=release-branches` and `kind=patch`, confirm that
every fix meant for the line reached it **before** writing any file:

```
${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/backport-audit.sh release/X.Y
```

Follow "Backport gate" in `references/release-branches.md`: `missing` and `in-review`
rows STOP the release, `unlabelled` rows need the user's decision, and a gate that cannot
run (`gh` unavailable) fails closed. Never skip it, and never answer its questions for the
user, including under `/goal` or `--dry-run` (which reports the result without asking).

## Phase 3: Resolve release target matrix

Build the final `{os × arch}` matrix:

1. Start with `default_os` / `default_arch` from Phase 1.
2. If `--os` or `--arch` was passed, replace the corresponding axis entirely.
3. Reject combinations with no known build recipe (e.g. `windows × arm` for languages
   where cross-compilation is unsupported) — list the invalid combos and ask whether to
   drop or abort.

Store the matrix for Phases 5, 6, and 7.

## Phase 4: Draft changelog and release notes

Unless `--skip-notes` was passed:

1. Invoke the changelog helper and capture its stdout:

   ```
   ${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/draft-changelog.sh [--exclude-internal] [--template <path>] <new-version> [<from-ref>]
   ```

   Pass an explicit `<from-ref>` when the default (`git describe --tags --abbrev=0`)
   picks the wrong previous tag — on `release/X.Y`, or for a final `X.Y.0` after trunk
   pre-releases; see `references/release-branches.md`.
   Pass `--exclude-internal` if the user requested it. Pass `--template <path>` if the
   user supplied a custom template path. The helper fills the template placeholders
   (`{{VERSION}}`, `{{DATE}}`, `{{HIGHLIGHTS}}`, `{{BREAKING}}`, `{{FEATURES}}`,
   `{{FIXES}}`, `{{INTERNAL}}`, `{{COMMITS}}`, `{{COMPARE_URL}}`, `{{PREVIOUS_TAG}}`)
   from git history and writes the complete rendered document to stdout.

2. Write the captured stdout to `docs/releases/<new-version>.md` (or
   `.github/releases/<version>.md` if the repo already uses that path). This is the
   notes file that the `gh release create` command consumes.

3. Update `CHANGELOG.md` by prepending a slim version of the same content — Summary and
   per-category sections only, no `<details>` blocks — above any `## [Unreleased]`
   marker. If no `CHANGELOG.md` exists, create one using the template seeded from
   `${CLAUDE_PLUGIN_ROOT}/skills/releaser/references/release-notes-template.md`.

Ask the user to review the drafted Summary and Upgrade Notes sections before moving on.

### Internal vs. user-facing commits

Commits typed `docs`, `chore`, `test`, `build`, `ci`, `style`, and `refactor` are
classified as Maintenance. The helper surfaces them in a collapsible `<details>` block
so they are visible but not dominant. Pass `--exclude-internal` to drop the Maintenance
section entirely — use this only when the release genuinely contains no internal-only
churn worth surfacing; otherwise keep the section so reviewers have full context.

## Phase 5: Bump version in manifests

Edit only the files named in `manifest_files` from Phase 1. Common targets:

- `package.json` → `version` field.
- `pyproject.toml` → `[project].version` or `[tool.poetry].version`.
- `Cargo.toml` → `[package].version`.
- `go.mod` does not carry a version; the tag IS the version. Skip the bump step.
- `Dockerfile` or `docker-compose.yml` labels → update if the repo uses
  `org.opencontainers.image.version`.

NEVER edit files outside that list — with one exception: when the Phase 2 branch check
printed a non-empty `creates_maintenance=release/X.Y`, also record the new maintenance
branch so the state change lands in the release commit:

```
${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/release-state-update.sh --add-maintenance release/X.Y
```

It edits only `RELEASING.md` (and may move a branch past the support window to
`frozen`); it never commits. Include `RELEASING.md` in the diff summary. Under
`--dry-run`, add `--dry-run` so it prints the diff instead of writing.

After edits, emit a diff summary and STOP for user review before continuing.

## Phase 6: CI workflow file (optional)

This phase generates or audits the **release.yml** file itself. It is separate from
the **Phase 8.5 release-CI auto-fix loop** (which watches a live workflow run after
publish). Three modes:

### --ci-config=generate

Fails if any file in `existing_ci` looks release-related (matches
`release|publish|deploy`). Otherwise, write a new `.github/workflows/release.yml` by
copying the matching template:

- Node → `references/ci-templates/node-release.yml`
- Python → `references/ci-templates/python-release.yml`
- Go → `references/ci-templates/go-release.yml` (uses goreleaser)
- Rust → `references/ci-templates/rust-release.yml` (uses cargo-dist if configured,
  else actions-rs matrix)
- Docker → `references/ci-templates/docker-release.yml`
- Generic → `references/ci-templates/generic-release.yml` (tag-triggered, uploads
  artifacts via `softprops/action-gh-release`)

Substitute the Phase 3 matrix and project name into the template. Also emit a short
`.github/workflows/README.md` entry documenting the new workflow — required (see
`references/ci-optimization-checklist.md`, "Documentation" section).

### --ci-config=audit

Delegate to the `ycc:releaser` agent. Pass it the list of existing workflow files. The
agent returns a structured report (Findings → Severity → Fix). The skill summarizes the
top items and writes the full report to `docs/prps/reviews/ci-release-audit.md` for
later consumption by `ycc:review-fix`.

### No --ci-config flag

Skip Phase 6 entirely. Print a one-line reminder: "Skipped CI workflow generation.
Run with `--ci-config=generate` or `--ci-config=audit` to include it. (This is
separate from `--ci`, which monitors a live release workflow after publish.)"

## Phase 7: Dry-run check

If `--dry-run` was passed:

1. Print the full release plan: detected project, proposed version, target matrix,
   files that would change, commands that would run. Include the release model, the
   branch-check result, the backport gate result for a patch, and — when
   `creates_maintenance` is set — the `RELEASING.md` diff from
   `release-state-update.sh --dry-run --add-maintenance release/X.Y`.
2. STOP. Write nothing, execute nothing side-effecting.
3. If both `--dry-run` and `--publish` were passed, `--dry-run` wins: the publish helper
   does NOT run.

## Phase 8: Emit next-step commands

Always emit the following block. Substitute `<new-version>`, `<changed-files>`,
`<notes-path>`, and `<branch>` (the `branch=` from the Phase 2 branch check — the
branch being released) with real values. NEVER run these commands automatically.

```
Release prepared. No commits or tags have been created — review the diff, then run:

git add <changed-files>
git commit -m "chore(release): v<new-version>"
git tag -a v<new-version> -m "v<new-version>"
git push origin HEAD:<branch> --follow-tags

# Create the GitHub release from the drafted notes:
gh release create v<new-version> \
  --notes-file <notes-path> \
  --title "v<new-version>"

# If artifacts were produced locally and need uploading:
gh release upload v<new-version> <path-to-artifact> [...]
```

Under release-branches, append the steps the branch check asked for (see
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/branching-model.md`, "Models").
When `creates_maintenance=release/X.Y` (a final minor or major cut from the trunk):

```
# Create the maintenance branch from the tag, and its backport label (skip the
# label if it already exists):
git push origin vX.Y.0^{commit}:refs/heads/release/X.Y
gh label create "<backport_label>" --description "Cherry-pick to release/X.Y"
```

When `forward_port=1` (a patch cut from `release/X.Y`), carry the CHANGELOG entry — not
the version bump — to the trunk in its own PR:

```
# Forward-port the vX.Y.Z CHANGELOG entry to <trunk>:
git fetch origin
git switch -c chore/changelog-vX.Y.Z origin/<trunk>
# Copy the X.Y.Z section from `git show vX.Y.Z:CHANGELOG.md` into CHANGELOG.md,
# in version order. Leave the version manifests alone.
git commit -am "chore(release): record vX.Y.Z in changelog"
git push -u origin HEAD
gh pr create --base <trunk> --title "chore(release): record vX.Y.Z in changelog" \
  --body "Forward-port of the vX.Y.Z CHANGELOG entry from release/X.Y. No version bump."
```

See "Forward-porting a patch's CHANGELOG entry" in `references/release-branches.md`.

If `--ci-config=generate` ran, append:

```
# Verify the new workflow in CI by pushing the tag — the release workflow will
# build the matrix and attach artifacts to the GitHub release.
```

**Forge provider detection**: release creation is provider-aware.
`publish-release.sh` detects the forge provider on `origin` first and routes
through the matching CLI — `gh release create` for `github`, `tea release
create --tag <tag> [--note-file]` for `forgejo`/`gitea` (per the
operation-equivalence map). The `gh release create`/`gh release upload` commands
emitted in the Phase 8 block above are the `github` path; on a `forgejo`/`gitea`
remote the helper drives `tea release create` instead. Log the resolved provider

- CLI. See
  [`../_shared/references/forge-detection.md`](../_shared/references/forge-detection.md).

When the user passed `--publish[=create|edit|auto]`, after they review the rendered
notes, run:

```
${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/publish-release.sh v<new-version> <notes-path> --mode=<mode>
```

**Examples:**

```
# Preview only — prints the resolved gh command without executing it:
${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/publish-release.sh v1.4.0 docs/releases/v1.4.0.md --mode=auto

# Apply — executes the resolved gh command:
${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/publish-release.sh v1.4.0 docs/releases/v1.4.0.md --mode=auto --confirm
```

This prints the resolved `gh` command without executing it. Re-run with `--confirm` to
apply. Use `--mode=edit` only when intentionally replacing an existing release body —
this is destructive.

## Phase 8.5: Release CI auto-fix loop (--ci)

Runs **only** when ALL of the following hold:

- `--ci` was passed.
- `--publish` was passed.
- `--confirm` was passed AND `publish-release.sh --confirm` exited 0 (the release
  exists on GitHub and the release-event workflow has been triggered).

Otherwise, print a one-line warning — `--ci ignored: no successful publish in this
run` — and skip to Phase 9. Never enter the loop without a live release to watch.

The contract (exit codes, `RESULT=` signaling, JSONL audit log, failure classification,
signature dedup, default-branch refusal) mirrors `ci-monitor.sh` verbatim. See
[`_shared/references/ci-monitoring.md`](../_shared/references/ci-monitoring.md),
section "Release mode", for the single source of truth.

**GitHub-only:** the release-CI auto-fix loop is GitHub-only — it depends on
`gh run list`, `gh workflow run`, and `gh release` controls that have no `tea`
equivalent. On a non-GitHub remote `release-ci-monitor.sh` returns
`RESULT=unsupported-provider` (exit 2). Treat it like `not-found`: report that
the loop is GitHub-only, render an 8.5.4-style diagnosis, and exit Phase 8.5
cleanly without retrying. (Release _creation_ in Phase 8 remains provider-aware
via `tea release create`; only this post-publish monitoring loop is gated.) See
[`../_shared/references/forge-detection.md`](../_shared/references/forge-detection.md).

### 8.5.0 Detect re-cut strategy

Read `.github/workflows/<resolved-release-workflow>.yml` and inspect the `on:`
triggers:

- If `workflow_dispatch` is present → **preferred path**: re-trigger via
  `gh workflow run <name> --ref <tag>`. Non-destructive.
- Else if `--ci-recut=destructive` was passed → **fallback path**:
  `gh release delete <tag> --cleanup-tag --yes` then re-run
  `publish-release.sh ... --confirm` to recreate the tag and release.
- Else → REFUSE to enter the loop. Print: "Release workflow has no
  `workflow_dispatch` trigger; re-running it requires destroying and recreating the
  release. Add a `workflow_dispatch:` trigger to your release workflow, or re-run
  this command with `--ci-recut=destructive` to opt in." Exit Phase 8.5.

### 8.5.1 Authorization gate (skipped if --ci-yes)

Render a one-time block showing:

- Resource: tag `v<new-version>`, workflow `<file>`, repo `<owner/name>`.
- Resolved caps: `--ci-max-pushes` (default 5), `--ci-max-same-failure` (default 3),
  `--ci-timeout-min` (default 30).
- Re-cut strategy detected in 8.5.0: `workflow_dispatch` (preferred) or
  `delete-release-and-retag` (destructive — only if `--ci-recut=destructive`).
- Non-toggleable safety constraints:
  - Never `git push --force` to any branch.
  - Never `git push --no-verify`.
  - Never edits files outside the failed workflow step's implicated paths.
  - Never amends published release notes without an explicit user opt-in.

Wait for `yes`/`no`. Any other input aborts the loop and proceeds to Phase 9 with
"loop declined" status.

#### `/goal` re-confirmation (safety)

If a `/goal` session directive is active when Phase 8.5 is reached, this gate is the
one human approval the bounded, destructive-capable loop depends on. Therefore:

- **`--ci-yes` does NOT suppress this gate under an active `/goal`.** When `/goal` is
  active, always render the 8.5.1 block and wait for an explicit `yes`/`no`, even if
  `--ci-yes` was passed. `--ci-yes` is honored only when no `/goal` directive is active.
- A `/goal` evaluator is transcript-only and cannot answer this prompt, so the loop
  **pauses here until you respond in person**. That pause is intentional: `/goal` may
  drive the Phase 8.5.2+ fix-and-recut loop to green, but it must never auto-authorize
  entry into that loop. Print one line making the pause legible:
  `/goal active — Phase 8.5.1 authorization stays interactive; --ci-yes ignored. Waiting for yes/no.`
- This guard applies **only** to the post-publish CI loop. The Phase 2 version confirm
  and the Phase 5 manifest diff review are likewise never auto-approved under `/goal`;
  see `## /goal pairing` for the full out-of-scope list.

### 8.5.2 Loop protocol

1. Initialize audit log:

   ```
   mkdir -p ~/.claude/session-data/release-ci-watch/
   AUDIT_LOG=~/.claude/session-data/release-ci-watch/<tag>-<utc-iso>.log
   ```

2. Invoke the monitor:

   ```
   ${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/release-ci-monitor.sh \
     --tag v<new-version> \
     --workflow <detected-or-passed> \
     --repo <owner/name> \
     --max-pushes <N> \
     --max-same-failure <N> \
     --timeout-min <N> \
     --log-file "$AUDIT_LOG"
   ```

3. Branch on the exit code (identical contract to `ci-monitor.sh`):

   | Exit | `RESULT=`              | Action                                                                     |
   | ---- | ---------------------- | -------------------------------------------------------------------------- |
   | 0    | `green`                | Success. Exit Phase 8.5, continue to Phase 9.                              |
   | 20   | `handoff`              | Step **8.5.3** (fix and re-cut), then loop to step 2.                      |
   | 21   | `rerun-pending`        | `sleep 30`, then loop to step 2 (no fix applied).                          |
   | 10   | `bail-recurrence`      | Step **8.5.4** (diagnosis), exit Phase 8.5.                                |
   | 11   | `bail-nonfixable`      | Step **8.5.4**, exit Phase 8.5.                                            |
   | 12   | `bail-pushes`          | Step **8.5.4**, exit Phase 8.5.                                            |
   | 13   | `bail-timeout`         | Step **8.5.4**, exit Phase 8.5.                                            |
   | 2    | `not-found`            | Step **8.5.4**, exit Phase 8.5.                                            |
   | 2    | `unsupported-provider` | Remote is not GitHub; loop is GitHub-only. Step **8.5.4**, exit Phase 8.5. |

### 8.5.3 Fix and re-cut on handoff

The monitor wrote one JSONL line to the audit log with the failed run's metadata:
`run_id`, `workflow_name`, `job_name`, `step_name`, `category`, `signature`,
`log_excerpt_path`, `implicated_files`.

1. **Dispatch the fix agent** via the Task tool with
   `subagent_type: "ycc:release-fix-applier"`. Pass the JSONL line verbatim. The
   agent edits ONLY the implicated files, returns the proposed commit message
   (conventional-commit prefix matching the category — `fix`, `ci`, `build`, etc.)
   and the diff summary.

2. **Validate the commit message**:

   ```
   ${CLAUDE_PLUGIN_ROOT}/skills/git-workflow/scripts/validate-commit.sh "<message>"
   ```

3. **Pre-push branch-protection check** on the branch that was released — the trunk,
   or `release/X.Y` for a patch under release-branches — not a hard-coded `main`:

   ```
   RELEASE_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
   gh api "repos/<owner>/<name>/branches/${RELEASE_BRANCH}/protection" 2>/dev/null
   ```

   `RELEASE_BRANCH` must equal the Phase 2 `branch=`; if it does not (or is `HEAD`),
   exit Phase 8.5 with `loop-blocked`. If the branch has
   `required_pull_request_reviews`, the loop cannot push directly. Surface: "Direct
   push to `<RELEASE_BRANCH>` blocked by branch protection — open a PR with the fix
   into `<RELEASE_BRANCH>`, merge it, and re-run with `--ci`." Exit Phase 8.5 with
   `loop-blocked` status (renders an 8.5.4-style block without retrying).

4. **Commit and push** to the release branch:

   ```
   git add <implicated-files>
   git commit -m "<validated-message>"
   git push origin "HEAD:${RELEASE_BRANCH}"
   ```

   NEVER `--force`. NEVER `--no-verify`. When `RELEASE_BRANCH` is `release/X.Y`, the fix
   also needs a trunk PR after the loop ends (see `references/release-branches.md`).

5. **Re-trigger the release workflow** per the strategy detected in 8.5.0.
   - **Preferred** (`workflow_dispatch` available):

     ```
     gh workflow run <name> --ref v<new-version>
     ```

   - **Fallback** (only if `--ci-recut=destructive` was set):

     ```
     gh release delete v<new-version> --cleanup-tag --yes
     ${CLAUDE_PLUGIN_ROOT}/skills/releaser/scripts/publish-release.sh \
       v<new-version> <notes-path> --mode=create --confirm
     ```

6. `push_count++`. Loop back to 8.5.2 step 2.

### 8.5.4 Bail diagnosis block

Render to the user:

- **Reason** — one of `recurrence` / `nonfixable` / `pushes` / `timeout` /
  `not-found` / `loop-blocked`.
- **Cap that fired** and its resolved value.
- **Last failure** — `run_id`, `workflow_name`, `job_name`, `step_name`,
  `category`, `signature`.
- **Log excerpt path** (from the monitor's `--log-file`).
- **Audit log path**.
- **Next steps** — concrete guidance keyed off the bail reason (e.g., for
  `recurrence`: "The same failure (`<signature>`) recurred. Inspect
  `<log-excerpt-path>` and apply a manual fix before retrying.").

Always print this block — even on `not-found` — so the user has a single
post-mortem surface.

## Phase 9: Final summary

Report to the user:

- Detected language / build system / manifest files.
- Proposed vs. requested version.
- Release model and branch: `model` and `branch` from the Phase 2 check (or "no
  `RELEASING.md`"), plus the follow-ups it requires — the new `release/X.Y` branch and
  label, or the CHANGELOG forward-port PR.
- Backport gate (patches under release-branches): `clean` with the number of PRs verified
  and the `since=` window, or the rows the user chose to ship without, listed as
  "Deferred backports".
- Target `{os × arch}` matrix.
- Files modified (changelog, notes, manifests, workflow).
- CI workflow-file outcome (generate / audit / skipped) and report path if audit ran.
- Publish mode outcome: whether the release was published (applied with `--confirm`),
  previewed only (print-only via `--publish` without `--confirm`), or emit-only
  (no `--publish` flag).
- Release CI loop outcome (if `--ci` was set): `green` (final status), `bail-*`
  (with reason and cap that fired), `loop-blocked`, `declined`, or `skipped` (no
  successful publish). Include the audit log path so the user can inspect it.
- The exact command block from Phase 8.

Then, as the **last lines** of the summary, print the Goal Signals block verbatim:

```
Goal Signals (machine-readable — printed verbatim for /goal)
RELEASE_PUBLISHED: <PASS|FAIL|n/a>
GATES_INTERACTIVE: <PASS|FAIL>
CI_GREEN: <PASS|FAIL|n/a>
CI_BAIL_VISIBLE: <PASS|n/a>
AUDIT_LOG_PRINTED: <PASS|FAIL|n/a>
```

Print one `KEY: PASS|FAIL` per line. Use `PASS` only when the matching `## Success
Criteria` item holds; otherwise `FAIL`. See `## Success Criteria` for each key's exact
condition and `n/a` rules.

## Success Criteria

- **RELEASE_PUBLISHED**: `--publish --confirm` ran and `publish-release.sh --confirm` exited 0 (the release exists on GitHub). `n/a` when `--publish` was not set or ran in preview-only mode.
- **GATES_INTERACTIVE**: Every human gate that applied this run — Phase 2 version confirm, the Phase 2 backport gate decisions, Phase 5 manifest diff review, and the Phase 8.5.1 authorization — was satisfied by explicit user input and **none** was auto-approved or bypassed (including under an active `/goal`). `FAIL` if any applicable gate was skipped without a human `yes`. This is the safety invariant that keeps `/goal` from wrapping the whole skill.
- **CI_GREEN**: If `--ci` ran, the Phase 8.5 loop reached `RESULT=green` and the Phase 9 summary shows "Release CI loop outcome: `green`". `n/a` when `--ci` was not set or the loop was skipped (no successful publish).
- **CI_BAIL_VISIBLE**: If `--ci` ended without green, the summary states the terminal outcome (`bail-*`, `loop-blocked`, or `declined`) and the cap/constraint that fired. `n/a` when `--ci` reached green or was not set.
- **AUDIT_LOG_PRINTED**: If `--ci` ran, the Phase 9 summary printed the audit-log path. `n/a` when `--ci` was not set or the loop was skipped.

These keys are emitted verbatim in the Phase 9 Goal Signals block so a `/goal` evaluator can observe completion from the transcript alone.

## /goal pairing

Pair this skill with the `/goal` session directive **only for the bounded Phase 8.5 release-CI auto-fix loop** — never for the skill as a whole. The full `ycc:releaser` flow has four human approval gates that exist specifically to prevent unattended publishing and looping; `/goal` must never auto-satisfy them:

- **Phase 2 — version confirm.** The user must approve the proposed version bump.
- **Phase 2 — backport gate (patches).** The user decides each unlabelled fix and any shipping without a missing backport.
- **Phase 5 — manifest diff review.** The user must approve what changed before any commit.
- **Phase 8.5.1 — CI authorization gate.** The user must approve before the bounded, destructive-capable loop starts. `--ci-yes` does **not** bypass this gate under an active `/goal` (see the 8.5.1 `/goal` re-confirmation guard).

Because the `/goal` evaluator is transcript-only it cannot answer these prompts, so a `/goal` loop will **pause** at each gate until you respond in person. That is the intended behavior: only after you have published (`--publish --confirm`) and authorized the loop does `/goal` add value — driving Phase 8.5.2+ through every `handoff` fix-and-recut and `rerun-pending` retry to green without returning control between iterations. The `GATES_INTERACTIVE` Goal Signal records that none of these gates was auto-approved.

The Phase 8.5 loop's `RESULT=` markers (from `release-ci-monitor.sh`, sharing the `ci-monitor.sh` contract with `ycc:pr-autofix` and `ycc:prp-pr`) tell the evaluator when to keep looping versus when to stop:

- **Keep looping** — `handoff` (8.5.3 fix-and-recut) and `rerun-pending` (8.5.2 wait-and-retry). Recoverable progress markers, not endpoints.
- **Done** — `RESULT=green`, with the Phase 9 summary showing "Release CI loop outcome: `green`" and the audit-log path (`CI_GREEN: PASS`, `AUDIT_LOG_PRINTED: PASS`).
- **Stop** — any terminal `bail-*` (`bail-recurrence`, `bail-nonfixable`, `bail-pushes`, `bail-timeout`, `not-found`) or `loop-blocked`. `release-ci-monitor.sh` exhausts recoverable retries internally before emitting a bail, so a printed terminal marker means no further automatic progress is possible. The evaluator distinguishes "loop again" from "stop" by `green` vs `bail-*`/`loop-blocked` in the Phase 9 summary — never by re-classifying bail codes. See [`../_shared/references/ci-monitoring.md`](../_shared/references/ci-monitoring.md) ("Release mode") for the authoritative bail taxonomy.

Recommended condition template (set this **after** you have approved Phases 2 and 5, published with `--publish --confirm`, and authorized the loop at 8.5.1):

```
/goal Drive the ycc:releaser Phase 8.5 release-CI loop to green, continuing through every
handoff and rerun-pending iteration without returning control to me. Done when the Phase 9
summary shows "Release CI loop outcome: green", the audit-log path is printed, and the Goal
Signals print verbatim — GATES_INTERACTIVE: PASS, CI_GREEN: PASS, and AUDIT_LOG_PRINTED:
PASS. If CI_GREEN prints FAIL alongside CI_BAIL_VISIBLE: PASS (a terminal bail-*, loop-blocked,
or declined), stop and report it — do not re-run. Never auto-approve the Phase 2 version
confirm, the Phase 5 manifest review, or the Phase 8.5.1 authorization. Stop after 25 turns
if not achieved.
```

The transcript-output contract and shared caveats (worktree cwd, interactive failure prompts, platform availability) live in the shared reference — read it before relying on a `/goal` loop:

```
${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/goal-pairing.md
```

## Important Notes

- **Never auto-commits, pushes, or publishes.** The user reviews every change and runs
  the emitted commands manually. This is the same discipline as `ycc:bundle-release`.
- **Publish helper = operator workflow, not a guardrail.** `publish-release.sh` runs in
  print-only mode by default: it prints the resolved `gh` command (including
  `--verify-tag` for creates) and exits successfully. The operator reviews that line,
  then re-runs the same invocation with `--confirm` when they intend to publish.
  The script sets an internal confirm flag only when `--confirm` is passed; without
  it, no mutating `gh` call runs.
- **`--dry-run` beats `--publish`.** If both flags are present, the publish helper does
  not run. Dry-run always exits before any side-effecting step.
- **Never edits files outside the detected `manifest_files` list** — except
  `RELEASING.md`, and only through `release-state-update.sh --add-maintenance` when a
  minor or major creates `release/X.Y`. If the repo has unusual version ownership
  (e.g. a `VERSION` file, a `_version.py`, multi-package workspaces), add it to the
  list via `--platform=generic` and the user confirms before edit.
- **Releases come from the branch `RELEASING.md` names.** The Phase 2 branch check
  refuses a version on the wrong branch and prints the fix; the skill never switches
  branches itself.
- **Never regenerates third-party lockfiles as a side effect.** If `package.json` bumps
  require `package-lock.json`, the skill instructs the user to run the lockfile command
  themselves and surfaces any drift.
- **CI generation is opinionated, not magic.** The templates are starting points; the
  skill calls out which inputs require human configuration (secrets, environments,
  signing keys, provenance) before the workflow will run green.
- For existing CI workflow files, always prefer `--ci-config=audit` first. Do not
  overwrite a working workflow without the user's explicit confirmation.
- **`--ci` (Phase 8.5) is opt-in and post-publish.** It enters only after
  `--publish --confirm` has actually created/edited the release on GitHub. The
  authorization gate (8.5.1) cannot be bypassed except with `--ci-yes`, and the
  destructive re-cut fallback cannot be reached except with `--ci-recut=destructive`.
- **The release-CI loop never edits release notes or manifest files.** It only
  touches files implicated by the failed workflow step. Notes and manifests are
  considered immutable for the lifetime of the loop.
- See `references/project-type-matrix.md` for the full language → toolchain map.
- See `references/ci-optimization-checklist.md` for the audit criteria used by the
  agent and the default quality gate for generated workflows.
- See `references/release-notes-template.md` for the drafted notes format.
- See `references/release-branches.md` for the branch-check output, the backport gate,
  previous-tag ranges, and the maintenance-branch and forward-port steps.
- See [`../_shared/references/ci-monitoring.md`](../_shared/references/ci-monitoring.md)
  ("Release mode" section) for the loop contract, exit-code table, and audit-log
  schema.
