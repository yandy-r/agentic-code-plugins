---
name: code-review
description: Reviews local changes or GitHub PRs and saves actionable findings. Use
  when reviewing a PR, requesting a full local review, or creating a review-fix artifact.
---

# Code Review

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.

> PR review mode adapted from PRPs-agentic-eng by Wirasm. Part of the PRP workflow series.

**Input**: `$ARGUMENTS` **Operational context:** Save machine-parseable findings under docs/prps/reviews/ with finding IDs and Open/Fixed/Failed Status fields for /review-fix. PR mode reads changed files, runs validation, assigns severity, and posts via gh; use /quick-review for an inline-first local review.

---

## Flag Parsing

Before selecting mode, extract flags from `$ARGUMENTS`:

| Flag                | Effect                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--approve`         | Force the final decision to APPROVE regardless of findings (still reports all findings)                                                                                                                                                                                                                                                                                                                                                                                                                |
| `--request-changes` | Force the final decision to REQUEST CHANGES regardless of findings                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `--parallel`        | Fan out the REVIEW phase across 3 **standalone** `code-reviewer` sub-agents (correctness, security, quality) dispatched in parallel and merge findings. Works in opencode, Cursor, and Codex.                                                                                                                                                                                                                                                                                                   |
| `--worktree`        | (legacy / now default; safe to omit) Check out the PR head branch into an isolated worktree at `<repo-root>/.config/opencode/worktrees/<repo>-pr-<N>/`. Worktree mode is on by default in PR mode; pass `--no-worktree` to opt out.                                                                                                                                                                                                                                                                             |
| `--no-worktree`     | Opt out of worktree isolation in PR mode. Skip worktree creation, artifact commit+push, and cleanup. Files are read directly from the main checkout.                                                                                                                                                                                                                                                                                                                                                   |
| `--keep-draft`      | Skip the automatic draft→ready promotion in PR mode. Default: PR is promoted to Ready for Review before posting the review.                                                                                                                                                                                                                                                                                                                                                                            |
| `--keep-worktree`   | Skip removal of the PR worktree after the review is posted. The artifact is still committed and pushed to the PR branch. Default: worktree is removed via `git worktree remove <path>` after a clean review post.                                                                                                                                                                                                                                                                                      |
| `--quick`           | **Alias for `/quick-review`.** Fast interactive review of uncommitted changes — prints findings inline and asks Apply fixes / Save to file / Discard. Writes only on confirmation. Compatible with `--parallel`. Mutually exclusive with a PR argument, `--approve`, and `--request-changes`. This skill validates the combination and then delegates to `/quick-review` with the remaining flags. See that skill's `--yes`, `--save`, and `--severity` options for scripted use. |

Strip the supported flags from `$ARGUMENTS` and set `QUICK_MODE=true|false`, `PARALLEL_MODE=true|false`, `NO_WORKTREE_MODE=true|false`, `KEEP_DRAFT=true|false`, and `KEEP_WORKTREE=true|false`. Compute `WORKTREE_MODE=true` unless `--no-worktree` is present. The remaining text is the mode selector (PR number/URL or blank for local).

**Validation**:

- `--quick` with a PR number/URL is **not allowed**. If both are passed → abort with: `--quick only reviews uncommitted local changes; remove the PR argument or drop --quick.`
- `--quick` with `--approve` or `--request-changes` is **not allowed**. Quick mode does not publish a GitHub review, so these flags have no meaning. Abort with: `--approve / --request-changes have no meaning in quick mode (no GitHub review is posted). Drop the flag or use PR mode.`
- `--quick` with `--no-worktree`, `--keep-draft`, or `--keep-worktree` is accepted as a **no-op** (quick mode never creates a worktree or touches GitHub). Emit a note: `<flag> has no effect in quick mode.`



---

## Phase 0½ — SETUP (PR mode default; skipped with `--no-worktree`)

Skip this phase entirely when `WORKTREE_MODE=false` (i.e., `--no-worktree` was passed).

### Local mode with `--worktree`

Uncommitted changes cannot be branch-isolated in a worktree. Emit:

```
Note: --worktree has no effect in local mode; uncommitted changes are not branch-isolated.
```

Continue with Local Review Mode but set `WORKTREE_ACTIVE=false`. **Do NOT** emit a `## Worktree Setup` section in the artifact.

### PR mode with `--worktree`

1. Resolve `<repo>`:

   ```bash
   REPO=$(basename "$(git rev-parse --show-toplevel)")
   ```

2. Resolve `<pr-head-branch>`:

   ```bash
   PR_HEAD=$(gh pr view <N> --json headRefName --jq .headRefName)
   ```

3. Compute slug = `pr-<N>`.

4. Check out the PR head branch into an isolated worktree:

   ```bash
   PARENT_WORKTREE_PATH=$(
     bash "~/.config/opencode/shared/scripts/setup-worktree.sh" \
       parent "${REPO}" "pr-<N>" --base-ref "${PR_HEAD}"
   )
   ```

   The script is idempotent: re-running it on an existing worktree on the same branch reuses the path.

5. Record `WORKTREE_ACTIVE=true`, `PARENT_BRANCH=<PR_HEAD>`, and `PARENT_WORKTREE_PATH=<captured path>`.

6. If the checkout fails (e.g., the branch is already checked out in the main repo or conflicts exist), abort with:

   ```
   Error: could not check out PR head '<PR_HEAD>' into a worktree.
   Likely cause: the branch is currently checked out in the main repository.
   Switch away from it (git switch <other-branch>) and re-run.
   ```

### Behavior summary

| Flag state                              | Effect                                                                     |
| --------------------------------------- | -------------------------------------------------------------------------- |
| `WORKTREE_MODE=false` (`--no-worktree`) | No worktree. Files read from main working tree (local) or GitHub API (PR). |
| `WORKTREE_MODE=true` (default), local   | Warning printed; no worktree created; behaves as `WORKTREE_MODE=false`.    |
| `WORKTREE_MODE=true` (default), PR      | Parent worktree created; files read from `$PARENT_WORKTREE_PATH`.          |

Proceed to Mode Selection.

---

## Mode Selection

- If `QUICK_MODE=true` → **Quick Review Mode** below. (Validation in Phase 0 already rejected any combination that would be ambiguous, so we know the user wants an uncommitted-diff-only pass.)
- If a PR number/URL was provided → **PR Review Mode** below.
- Otherwise → **Local Review Mode** below.

---

## Local Review Mode

Comprehensive security and quality review of uncommitted changes.

### Phase 1 — GATHER

```bash
git diff --name-only HEAD
```

If no changed files, stop: "Nothing to review."

### Phase 2 — REVIEW

The shape of this phase depends on `PARALLEL_MODE`:

| Flags             | Path                                        |
| ----------------- | ------------------------------------------- |
| Neither set       | **Path A** — single-pass review (default)   |
| `PARALLEL_MODE`   | **Path B** — 3 parallel sub-agent reviewers |

#### Path A — Single-Pass Review (default, neither flag set)

Read each changed file in full and apply the **Local / Quick Review —
Single-Pass Checklist** (Security CRITICAL, Code Quality HIGH, Best Practices
MEDIUM) and the **Severity Rubric** from:

```
~/.config/opencode/shared/references/review-checklist.md
```

#### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Generate `TIMESTAMP=$(date +%Y%m%d-%H%M%S)` once, here, and reuse the same
variable for the Phase 3 review filename (`local-<TIMESTAMP>-review.md`) — one
canonical timestamp per invocation. Set `run-id = local-<TIMESTAMP>`.

> **OpenCode V2 standalone dispatch:** Issue the independent calls in one
> parallel tool batch and set `background=false` on every call. Each call waits
> for a candidate report. Require nonempty report text, validate the declared
> artifact or diff independently, and do not treat a terminal lifecycle state
> as proof of the deliverable. Apply the contentless-completion and bounded
> retry policy from
> [standalone-dispatch.md](~/.config/opencode/shared/references/standalone-dispatch.md).


Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE native `subagent` calls. Use the **Local / Quick Mode Roster**
(`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) and
**Standard Findings Format** from:

```
~/.config/opencode/shared/references/review-checklist.md
```

Per the scratch-backstop contract in that reference, also pass each reviewer
its own scratch path — `docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/<reviewer-name>.md`
(e.g. `.../correctness-reviewer.md`) — alongside the changed files, its focus +
checklist items, the severity rubric, and the findings-format directive.

After all 3 native `subagent` calls return: for any reviewer whose inline return is
empty, missing, or malformed, re-read its scratch file at that path before
merging (Merge Procedure in the reference). Pass the merged findings to
Phase 3 (REPORT) as if they came from a single-pass review. Phase 3 removes
the `docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/` directory once the
review artifact has been written successfully.

### Phase 3 — REPORT

Assign a sequential finding ID to each issue (`F001`, `F002`, `F003`, ...) ordered by severity (CRITICAL first) then by file path. Every finding receives `Status: Open` on first write.

Generate the review artifact and write it to `docs/prps/reviews/local-{YYYYMMDD-HHMMSS}-review.md`:

```bash
mkdir -p docs/prps/reviews
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
REVIEW_FILE="docs/prps/reviews/local-${TIMESTAMP}-review.md"
```

Use the **Review Artifact Format** defined at the bottom of this skill. Include:

- Finding ID (`**[F001]**`)
- Severity bucket (CRITICAL, HIGH, MEDIUM, LOW)
- `Status: Open` (always on first write)
- Category tag
- `file:line` reference
- Description
- Suggested fix

**Always write the file**, even if there are no findings (empty sections are acceptable — they give `/review-fix` a consistent target and preserve history).

If `PARALLEL_MODE=true` (Path B was used), remove the
`docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/` scratch directory now
that the artifact has been written successfully.

Print a concise summary to stdout with the file path and a hint to run fixes:

```
Local review written to: docs/prps/reviews/local-20260408-143022-review.md
Findings: [C] 2  [H] 3  [M] 1  [L] 0

Next steps:
  /review-fix docs/prps/reviews/local-20260408-143022-review.md   # apply fixes
  /review-fix docs/prps/reviews/local-20260408-143022-review.md --parallel
```

Block commit if CRITICAL or HIGH issues found.
Never approve code with security vulnerabilities.

---

## Quick Review Mode

> Triggered by `--quick`. This mode is now a **thin delegator** to
> `/quick-review` — the interactive inline-review skill. Phase 0 above
> has already validated the flag combination; this section hands off.

### Delegation

Invoke the `quick-review` skill via the `Skill` tool. Forward the
remaining flags — `--parallel`, plus anything quick-review
accepts — but drop the flags this skill owns (`--quick`, `--approve`,
`--request-changes`, `--no-worktree`, `--keep-draft`, `--keep-worktree`;
Phase 0 already consumed them).

```
Skill: quick-review
  args: "<stripped flags: --parallel | --yes | --save | --severity <level>>"
```

Print a single one-line notice before delegating so the user sees what
happened:

```
--quick delegated to /quick-review. Run /quick-review directly for full option surface (--yes, --save, --severity).
```

After the Skill call returns, exit. Do NOT run Phase 4/5/6/7/8. Do NOT
write an artifact here — quick-review owns the artifact lifecycle.

---

## PR Review Mode

Comprehensive GitHub PR review — fetches diff, reads full files, runs validation, posts review.

**GitHub-only.** PR mode is GitHub-only: it reads and posts on PRs through the
`gh` PR/review plumbing (`gh pr view`/`gh pr diff`/`gh pr review` + the GitHub
review-comments API), which has no `tea` equivalent. Detect the forge provider
on `origin` first (`forge_detect_provider origin`); if it is **not** `github`,
state that PR mode is GitHub-only and offer **Local Review Mode** instead
(local-diff review works on any provider). Do not attempt the `gh` PR calls on a
non-GitHub remote. See
[`../_shared/references/forge-detection.md`](../_shared/references/forge-detection.md).

Detect whether GitHub MCP tools are available (look for `mcp__github__*`). If they are, prefer those for PR fetch/view/review operations. Otherwise fall back to the `gh` CLI examples shown below.

### Phase 1 — FETCH

Parse input to determine PR:

| Input                          | Action                                   |
| ------------------------------ | ---------------------------------------- |
| Number (e.g. `42`)             | Use as PR number                         |
| URL (`github.com/.../pull/42`) | Extract PR number                        |
| Branch name                    | Find PR via `gh pr list --head <branch>` |

```bash
gh pr view <NUMBER> --json number,title,body,author,baseRefName,headRefName,changedFiles,additions,deletions
gh pr diff <NUMBER>
```

If PR not found, stop with error. Store PR metadata for later phases.

### Phase 2 — CONTEXT

Build review context:

1. **Project rules** — Read `AGENTS.md`, `RELEASING.md` (when present), `.claude/docs/`, and any contributing guidelines
2. **PRP artifacts** — Check `docs/prps/reports/` and `docs/prps/plans/` (including `completed/`) for implementation context related to this PR
3. **PR intent** — Parse PR description for goals, linked issues, test plans
4. **Changed files** — List all modified files and categorize by type (source, test, config, docs)
5. **PR base vs. release model** — Skip silently when `release-state.sh get` prints `present=0`. Otherwise fetch the head (`git fetch origin <headRefName>`, or `pull/<N>/head` for a fork) and compare `baseRefName` with `release-state.sh base --head FETCH_HEAD`, per [`../_shared/references/pr-base-and-backport.md#checking-an-existing-pr`](../_shared/references/pr-base-and-backport.md#checking-an-existing-pr). On a mismatch, record a **MEDIUM** finding anchored at `RELEASING.md` (Category: Pattern Compliance) naming both branches, with the suggested fix `gh pr edit <N> --base <expected>` (a retarget, not a code change).

### Phase 3 — REVIEW

Read each changed file **in full** (not just the diff hunks — you need surrounding context).

For PR reviews, fetch the full file contents at the PR head revision:

**When `WORKTREE_ACTIVE=true`**: read files directly from the parent worktree using the `Read` tool — the worktree has the PR head branch checked out, so the files on disk match the PR head revision. Skip the `gh api` fetch entirely:

```bash
# Instead of: gh api "repos/{owner}/{repo}/contents/$file?ref=<head-branch>"
# Read from:  ${PARENT_WORKTREE_PATH}/$file
```

**When `WORKTREE_ACTIVE=false`** (the existing path): continue to use `gh api` to fetch each file at the PR head ref:

```bash
gh pr diff <NUMBER> --name-only | while IFS= read -r file; do
  gh api "repos/{owner}/{repo}/contents/$file?ref=<head-branch>" --jq '.content' | base64 -d
done
```

The shape of this phase depends on `PARALLEL_MODE`:

| Flags             | Path                                        |
| ----------------- | ------------------------------------------- |
| Neither set       | **Path A** — single-pass review (default)   |
| `PARALLEL_MODE`   | **Path B** — 3 parallel sub-agent reviewers |

#### Path A — Single-Pass Review (default, neither flag set)

Apply the **PR Review — Single-Pass Checklist** (7 categories: Correctness,
Type Safety, Pattern Compliance, Security, Performance, Completeness,
Maintainability) and the **Severity Rubric** from:

```
~/.config/opencode/shared/references/review-checklist.md
```

#### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Set `run-id = pr-<NUMBER>` (PR numbers are unique, so no timestamp is needed).

> **OpenCode V2 standalone dispatch:** Issue the independent calls in one
> parallel tool batch and set `background=false` on every call. Each call waits
> for a candidate report. Require nonempty report text, validate the declared
> artifact or diff independently, and do not treat a terminal lifecycle state
> as proof of the deliverable. Apply the contentless-completion and bounded
> retry policy from
> [standalone-dispatch.md](~/.config/opencode/shared/references/standalone-dispatch.md).


Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE native `subagent` calls. Use the **PR Mode Roster**
(`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) and
**Standard Findings Format** from:

```
~/.config/opencode/shared/references/review-checklist.md
```

Each reviewer prompt must additionally include:

1. The PR number, head revision, and the list of changed files
2. Relevant context from Phase 2 (AGENTS.md rules, PRP artifacts, PR description)
3. Its own scratch backstop path — `docs/prps/reviews/.review-scratch/pr-<NUMBER>/<reviewer-name>.md`
   — per the scratch-backstop contract in that reference

The reviewer-prompt contract (focus + categories, severity rubric, findings
format directive) and the **Merge Procedure** are defined in that reference.
After all 3 native `subagent` calls return: for any reviewer whose inline return is
empty, missing, or malformed, re-read its scratch file at that path before
merging. Pass the merged findings to Phase 4 (VALIDATE) and downstream phases
as if they came from a single-pass review. Phase 6 removes the
`docs/prps/reviews/.review-scratch/pr-<NUMBER>/` directory once the review
artifact has been written and (when applicable) committed successfully.

**Note**: Validation commands (Phase 4) still run sequentially in the main
skill — parallelization here only applies to the review pass.

### Phase 4 — VALIDATE

Run available validation commands.

Detect the project type from config files (`package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml`, etc.), then run the appropriate commands:

**Node.js / TypeScript** (has `package.json`):

```bash
npm run typecheck 2>/dev/null || npx tsc --noEmit 2>/dev/null  # Type check
npm run lint                                                    # Lint
npm test                                                        # Tests
npm run build                                                   # Build
```

**Rust** (has `Cargo.toml`):

```bash
cargo clippy -- -D warnings  # Lint
cargo test                   # Tests
cargo build                  # Build
```

**Go** (has `go.mod`):

```bash
go vet ./...    # Lint
go test ./...   # Tests
go build ./...  # Build
```

**Python** (has `pyproject.toml` / `setup.py`):

```bash
pytest  # Tests
```

Run only the commands that apply to the detected project type. Record pass/fail for each.

### Phase 5 — DECIDE

Form recommendation based on findings:

| Condition                                    | Decision                          |
| -------------------------------------------- | --------------------------------- |
| Zero CRITICAL/HIGH issues, validation passes | **APPROVE**                       |
| Only MEDIUM/LOW issues, validation passes    | **APPROVE** with comments         |
| Any HIGH issues or validation failures       | **REQUEST CHANGES**               |
| Any CRITICAL issues                          | **BLOCK** — must fix before merge |

Special cases:

- Draft PR (with `--keep-draft`) → Always use **COMMENT** (not approve/block). Without `--keep-draft`, the PR is auto-promoted to ready before this decision runs, so normal severity-based decisions apply.
- Only docs/config changes → Lighter review, focus on correctness
- Explicit `--approve` or `--request-changes` flag → Override decision (but still report all findings)

### Phase 6 — REPORT

Assign sequential finding IDs (`F001`, `F002`, ...) ordered by severity (CRITICAL first) then by file path. Every finding receives `Status: Open` on first write.

#### Draft Promotion

At the very start of Phase 6, in PR mode, run the draft→ready promotion unless `--keep-draft` was set:

```bash
if [[ "$KEEP_DRAFT" != "true" ]]; then
  IS_DRAFT=$(gh pr view "$PR_NUMBER" --json isDraft --jq .isDraft)
  if [[ "$IS_DRAFT" == "true" ]]; then
    gh pr ready "$PR_NUMBER"
    echo "Promoted PR #$PR_NUMBER from draft to ready for review."
  fi
fi
```

#### Artifact Write

Write the artifact to `$(git rev-parse --show-toplevel)/docs/prps/reviews/pr-<N>-review.md`. When `WORKTREE_ACTIVE=true` this resolves to the worktree top-level (e.g., `<repo-root>/.config/opencode/worktrees/<repo>-pr-<N>/docs/prps/reviews/pr-<N>-review.md`); when `--no-worktree` is in effect, it resolves to the main repo. The artifact intentionally lives **with the PR branch** so it travels with the review history.

```bash
mkdir -p "$(git rev-parse --show-toplevel)/docs/prps/reviews"
```

Use the **Review Artifact Format** defined at the bottom of this skill. The artifact must include finding IDs and `Status: Open` on every finding so that `/review-fix` can later update the file in place.

- Write the artifact to `$(git rev-parse --show-toplevel)/docs/prps/reviews/pr-<N>-review.md`. When `WORKTREE_ACTIVE=true` this resolves to the worktree top-level (e.g., `<repo-root>/.config/opencode/worktrees/<repo>-pr-<N>/docs/prps/reviews/pr-<N>-review.md`); when `--no-worktree` is in effect, it resolves to the main repo. The artifact intentionally lives **with the PR branch** so it travels with the review history.
- **Note**: the artifact will be committed to the PR branch (see commit step below). If you do not want the review record on the PR branch, add `docs/prps/reviews/` to `.gitignore` — the skill detects this and skips the commit.

#### Artifact Commit + Push

After the artifact has been written, in PR mode when `WORKTREE_ACTIVE=true`, commit and push it to the PR branch before posting the review:

```bash
if [[ "$WORKTREE_ACTIVE" == "true" ]]; then
  ARTIFACT_REL="docs/prps/reviews/pr-${PR_NUMBER}-review.md"
  pushd "$WORKTREE_PATH" >/dev/null
  if git check-ignore -q "$ARTIFACT_REL"; then
    echo "Artifact path is gitignored; skipping commit. Worktree preserved at $WORKTREE_PATH."
    KEEP_WORKTREE=true
  else
    git add "$ARTIFACT_REL"
    git commit -m "docs(review): add review artifact for PR #${PR_NUMBER}"
    git push
    echo "Committed and pushed review artifact to PR #${PR_NUMBER} branch."
  fi
  popd >/dev/null
fi
```

If `PARALLEL_MODE=true` (Path B was used), remove the
`docs/prps/reviews/.review-scratch/pr-<NUMBER>/` scratch directory now that
the artifact has been written (and, when `WORKTREE_ACTIVE=true`, committed
and pushed) successfully.

Example of the Findings section:

```markdown
## Findings

### CRITICAL

- **[F001]** `src/auth.ts:42` — SQL injection in user lookup query
  - **Status**: Open
  - **Category**: Security
  - **Suggested fix**: Use parameterized query via `db.query('... WHERE id = $1', [userId])`

### HIGH

- **[F002]** `src/api/payments.ts:17` — Missing null check on `req.body.amount`
  - **Status**: Open
  - **Category**: Correctness
  - **Suggested fix**: Validate `typeof amount === 'number' && amount > 0` before processing

### MEDIUM

- **[F003]** `src/utils/format.ts:83` — Function exceeds 50 lines (78 lines)
  - **Status**: Open
  - **Category**: Maintainability
  - **Suggested fix**: Extract the date parsing block into a helper

### LOW

- **[F004]** `src/app.ts:5` — Missing JSDoc on public export `initApp`
  - **Status**: Open
  - **Category**: Maintainability
  - **Suggested fix**: Add a one-line JSDoc describing arguments and return type
```

The artifact MUST also include these sections:

- **Header**: PR number, title, author, branch, decision, reviewed timestamp
- **Summary**: 1-2 sentence overall assessment
- **Validation Results**: type-check / lint / tests / build pass-fail table
- **Files Reviewed**: list of changed files with Added/Modified/Deleted tags

### Phase 7 — PUBLISH

Post the review to GitHub:

```bash
# If APPROVE
gh pr review <NUMBER> --approve --body "<summary of review>"

# If REQUEST CHANGES
gh pr review <NUMBER> --request-changes --body "<summary with required fixes>"

# If BLOCK (GitHub has no dedicated BLOCK event; map to request-changes)
gh pr review <NUMBER> --request-changes --body "<blocking issues must be fixed before merge>"

# If COMMENT only (draft PR or informational)
gh pr review <NUMBER> --comment --body "<summary>"
```

For inline comments on specific lines, use the GitHub review comments API:

```bash
gh api "repos/{owner}/{repo}/pulls/<NUMBER>/comments" \
  -f body="<comment>" \
  -f path="<file>" \
  -F line=<line-number> \
  -f side="RIGHT" \
  -f commit_id="$(gh pr view <NUMBER> --json headRefOid --jq .headRefOid)"
```

Alternatively, post a single review with multiple inline comments at once:

```bash
gh api "repos/{owner}/{repo}/pulls/<NUMBER>/reviews" \
  -f event="COMMENT" \
  -f body="<overall summary>" \
  --input comments.json  # [{"path": "file", "line": N, "body": "comment"}, ...]
```

#### Worktree Cleanup

After `gh pr review` succeeds, remove the worktree unless `--keep-worktree` is set or the worktree is dirty:

```bash
if [[ "$WORKTREE_ACTIVE" == "true" && "$KEEP_WORKTREE" != "true" && -n "$WORKTREE_PATH" ]]; then
  DIRTY=$(git -C "$WORKTREE_PATH" status --porcelain)
  if [[ -n "$DIRTY" ]]; then
    echo "Worktree has uncommitted changes; skipping cleanup. Inspect: $WORKTREE_PATH"
  else
    git worktree remove "$WORKTREE_PATH"
    echo "Removed worktree $WORKTREE_PATH."
  fi
fi
```

The local PR branch is intentionally left alone; branch deletion is out of scope.

### Phase 8 — OUTPUT

Report to user:

```
PR #<NUMBER>: <TITLE>
Decision: <APPROVE|REQUEST_CHANGES|BLOCK>

Issues: <critical_count> critical, <high_count> high, <medium_count> medium, <low_count> low
Validation: <pass_count>/<total_count> checks passed

Artifacts:
  Review: docs/prps/reviews/pr-<NUMBER>-review.md
  GitHub: <PR URL>

Next steps:
  - <contextual suggestions based on decision>
```

---

## Review Artifact Format

Both Local Review Mode and PR Review Mode write an artifact using this exact format. The format is the contract that `/review-fix` parses — do not deviate.

### File locations

| Mode  | Path                                                  |
| ----- | ----------------------------------------------------- |
| Local | `docs/prps/reviews/local-{YYYYMMDD-HHMMSS}-review.md` |
| PR    | `docs/prps/reviews/pr-{NUMBER}-review.md`             |
| Quick | `docs/prps/reviews/quick-{YYYYMMDD-HHMMSS}-review.md` |

### Template

```markdown
# [Local Review | PR Review #<NUMBER>] — <TITLE or "Uncommitted Changes">

**Reviewed**: <ISO date>
**Mode**: Local | PR
**Author**: <author | "local">
**Branch**: <head> → <base>
**Decision**: APPROVE | REQUEST CHANGES | BLOCK | COMMENT

## Worktree Setup

<!-- Only emitted when WORKTREE_ACTIVE=true. Lists only the feature worktree; fixers run inside this path. -->

- **Parent**: <repo-root>/.config/opencode/worktrees/<repo>-pr-<N>/ (branch: <pr-head-branch>)

## Summary

<1-2 sentence overall assessment>

## Findings

### CRITICAL

- **[F001]** `file.ts:42` — <description>
  - **Status**: Open
  - **Category**: <Security | Correctness | Type Safety | Performance | Pattern Compliance | Completeness | Maintainability>
  - **Suggested fix**: <concrete, actionable fix>

### HIGH

- **[F002]** `file.ts:73` — <description>
  - **Status**: Open
  - **Category**: ...
  - **Suggested fix**: ...

### MEDIUM

- **[F003]** ...
  - **Status**: Open
  - ...

### LOW

- **[F004]** ...
  - **Status**: Open
  - ...

## Validation Results

| Check      | Result                |
| ---------- | --------------------- |
| Type check | Pass / Fail / Skipped |
| Lint       | Pass / Fail / Skipped |
| Tests      | Pass / Fail / Skipped |
| Build      | Pass / Fail / Skipped |

## Files Reviewed

- `file1.ts` (Modified)
- `file2.ts` (Added)
- `file3.ts` (Deleted)
```

> **Quick mode variant**: Quick reviews omit `## Validation Results` (no toolchain runs) and `## Worktree Setup` (no worktree is ever created). All other sections — Header, Summary, Findings (with full `[F###]`, `Status:`, `Category:`, `Suggested fix:` fields per finding), Files Reviewed — are identical to the standard template. This keeps the file parseable by `/review-fix` without special-casing.

### Finding ID rules

- **Sequential**: IDs start at `F001` and increment by one.
- **Stable per file**: Once assigned in a given review artifact, an ID is never renumbered, even after a fix is applied.
- **Per-artifact**: IDs are scoped to a single review file. A fresh code-review pass generates a new file with its own `F001`-restart counter.
- **Assigned in REPORT phase**: In both sequential and parallel paths, IDs are assigned during the REPORT phase (Phase 3 for local, Phase 6 for PR), AFTER merge and sort. Reviewer agents in parallel mode do NOT assign IDs.

### Status field rules

Every finding MUST have a `Status` field. Valid values:

| Status | Meaning                                                                                                      |
| ------ | ------------------------------------------------------------------------------------------------------------ |
| Open   | Default on first write. Not yet processed by `/review-fix`, or below the fix skill's severity threshold. |
| Fixed  | Successfully fixed by `/review-fix`. Set by the fix skill — code-review itself never writes this.        |
| Failed | Attempted by `/review-fix` but the fix broke validation. Set by the fix skill.                           |

`/code-review` only ever writes `Status: Open`. All other states are set in-place by `/review-fix`.

### Required fields per finding

Every finding must include these four lines (in this order) so the artifact is machine-parseable:

```
- **[F###]** `file:line` — <description>
  - **Status**: <Open|Fixed|Failed>
  - **Category**: <category>
  - **Suggested fix**: <concrete fix>
```

Findings missing a `Suggested fix` line are valid but will be **skipped** by `/review-fix` (flagged for human judgment).

---

## Edge Cases

- **No `gh` CLI and no GitHub MCP**: Fall back to local-only review (read the diff, skip GitHub publish). Warn user.
- **Diverged branches**: Suggest `git fetch origin && git rebase origin/<base>` before review.
- **Large PRs (>50 files)**: Warn about review scope. Focus on source changes first, then tests, then config/docs.
- **Stale PR head (default worktree mode)**: the worktree is a snapshot of the PR head at SETUP time. If new commits land on the PR after the review starts, re-run to resync.
- **Concurrent runs**: two `/code-review <N>` invocations on different PR numbers never collide (each gets its own `<repo>-pr-<N>/` directory). Two invocations on the SAME PR number share the same parent worktree (idempotent), which is by design.
- **Cleanup**: worktrees are removed automatically after the review is posted (Phase 7 Worktree Cleanup). Pass `--keep-worktree` to retain the worktree. If the worktree is dirty, cleanup is skipped and you are told where to inspect. Use `--no-worktree` for the previous behavior (no worktree created or removed).

---
