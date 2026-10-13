# CI Loop Steps (Phase 7)

Per-step detail for the `--ci` loop. Policy (caps, failure classification, termination, safety constraints, bail taxonomy) lives in `~/.codex/plugins/ycc/shared/references/ci-monitoring.md`; this file only holds the pr-autofix templates and commands.

The loop is GitHub-only. Phase 0 already gates the whole skill to `github`, so it never reaches a non-GitHub remote. If `ci-monitor.sh` returns `RESULT=unsupported-provider`, surface it and exit like the other non-loop terminal results.

## Step 1 — Authorization prompt (skip if `--ci-yes`)

```
CI auto-fix loop authorization
==============================
PR:                 #<PR_NUMBER> (<HEAD_BRANCH> → <BASE_BRANCH>)
Max auto-pushes:    <--ci-max-pushes>
Max same failure:   <--ci-max-same-failure>
Wall-clock timeout: <--ci-timeout-min> minutes
Audit log:          ~/.codex/session-data/ci-watch/<PR_NUMBER>-<utc-iso-timestamp>.log

Safety constraints (non-toggleable):
  - Never `git push --force`
  - Never `--no-verify`
  - Only push to PR head branch
  - Refuse if head equals default branch

Proceed? (yes/no):
```

On `no`: "CI monitoring declined; fixes were pushed but not monitored." Exit cleanly.

## Step 2 — Initialize audit log

```bash
mkdir -p ~/.codex/session-data/ci-watch/
AUDIT_LOG="$HOME/.codex/session-data/ci-watch/${PR_NUMBER}-$(date -u +%FT%H%M%SZ).log"
```

Reuse this single path for every iteration.

## Step 3 — Loop iteration

```bash
bash "~/.codex/plugins/ycc/shared/scripts/ci-monitor.sh" \
  --pr "$PR_NUMBER" \
  --branch "$HEAD_BRANCH" \
  --base "$BASE_BRANCH" \
  --max-pushes "$CI_MAX_PUSHES" \
  --max-same-failure "$CI_MAX_SAME_FAILURE" \
  --timeout-min "$CI_TIMEOUT_MIN" \
  --log-file "$AUDIT_LOG"
```

## Step 4 — Branch on `RESULT=`

Per the Loop Protocol in `ci-monitoring.md`:

- **`green`** → Phase 8 (success).
- **`handoff`** → read `RUN_ID`, `WORKFLOW`, `JOB`, `CATEGORY`, `SIGNATURE`, `LOG_EXCERPT_FILE`, `SUGGESTED_COMMIT_TYPE`, `SUGGESTED_COMMIT_SCOPE` from stdout. Apply the fix per the Failure Classification table in `ci-monitoring.md`:
  - `lint` / `format` → run the repo formatter/linter; commit.
  - `type-check` / `unit-test` / `build` → dispatch a `pr-comment-fixer` agent with a synthesized "comment" containing the failing log excerpt (read `LOG_EXCERPT_FILE`); the fixer applies a typed source fix.

  Validate the commit message via `~/.codex/plugins/ycc/skills/git-workflow/scripts/validate-commit.sh`. Push (never `--force`, never `--no-verify`). Delete `LOG_EXCERPT_FILE` after reading. Go back to Step 3.

- **`rerun-pending`** → sleep 30s; go back to Step 3. Apply no fix.
- **`bail-recurrence`** / **`bail-nonfixable`** / **`bail-pushes`** / **`bail-timeout`** → render a diagnosis block, write the final report (Phase 8), and exit. Push nothing further.
- **`pr-not-found`** / **`refused-default-branch`** → surface the error and exit. These should not fire here because Phase 0 already screens them; if they do, the audit log captures it.
