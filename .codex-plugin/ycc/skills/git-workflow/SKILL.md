---
name: git-workflow
description: Orchestrates commits, documentation updates, pushes, and PRs. Use when
  finishing a feature with docs, coordinating multiple commits, or shipping changes
  through a full Git workflow.
---

# Git Workflow Manager

Intelligent git commit and documentation workflow orchestration. Analyzes changes, writes conventional commit messages, and coordinates documentation updates through parallel agent deployment when needed.

## Current Task

**Managing git workflow for**: `$ARGUMENTS`

Parse arguments. **At least one action flag is required** in normal use; if none are provided, follow the interactive prompt in Phase 0.5. The one exception is bare `--ci`, which is valid on its own and means "monitor CI on the existing PR for this branch."

**Action flags** (cumulative ladder — `--pr` implies `--push` implies `--commit`):

- **--commit**: Commit only (no push, no PR)
- **--push**: Commit and push (implies `--commit`)
- **--pr**: Commit, push, and create PR (implies `--push` and `--commit`)

**Modifier flags** (do NOT satisfy the action requirement on their own):

- **--dry-run**: Show analysis and plan without making changes
- **--no-docs**: Skip documentation updates (commits only)
- **--draft**: Create PR as draft (requires `--pr`)
- **--base <branch>**: PR base branch (requires `--pr`). Overrides the base picked from `RELEASING.md` or the forge default branch (Step 22b).
- **--ci**: Monitor CI on the PR for the current branch and auto-fix until green or a bail condition. Works with `--pr` (create-then-monitor), `--push` (push-then-monitor existing PR), or bare (monitor only — no commit, no push). An open PR for the current branch must exist by the time Phase 6 starts. Incompatible with `--dry-run` and with `--commit`-only (since CI runs on remote commits).
- **--ci-max-pushes=N**: Cap on auto-pushes per invocation (default 5).
- **--ci-max-same-failure=N**: Bail if the same failure signature recurs N times (default 3).
- **--ci-timeout-min=N**: Wall-clock cap from first iteration (default 30).
- **--ci-yes**: Skip the one-time auth prompt (non-interactive).

Flag order does not matter — only presence matters. If no action flag is provided (and `--ci` is also absent), proceed to Phase 0.5 to resolve the action set interactively.

---

## Tool Preference Strategy

Before beginning Phase 0, determine which tools are available for GitHub operations.

### Step 0: Detect GitHub MCP Server

Check if GitHub MCP tools are available in your current tool list by looking for tools matching the pattern `mcp__github__*` (e.g., `mcp__github__create_pull_request`, `mcp__github__get_pull_request`).

**Set your tool preference for this session:**

| MCP Tools Available?                 | GitHub Operations Strategy                                             |
| ------------------------------------ | ---------------------------------------------------------------------- |
| Yes (`mcp__github__*` tools found)   | **Use MCP tools** for all GitHub operations (PR creation, PR viewing)  |
| No (no `mcp__github__*` tools found) | **Use `gh` CLI** via Bash for all GitHub operations (current behavior) |

**What stays as CLI regardless:**

- All `git` operations (status, diff, add, commit, push) — always use Bash `git` commands
- All bash scripts (analyze-changes.sh, create-pr.sh, validate-commit.sh) — always run via Bash
- File reading and analysis — always use Read/Grep/Glob tools

**Important**: Lack of MCP tools must NEVER block the workflow. If MCP tools are detected but a specific MCP call fails, fall back to the equivalent `gh` CLI command for that operation.

---

## Conventional Commits Requirement

**ALL commits produced by this workflow MUST use the Conventional Commits format.** This is a hard requirement, not a suggestion.

**Format**: `<type>(<scope>): <subject>`

**Valid types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`, `revert`

**Rules** (enforced by `validate-commit.sh`):

- Subject line: imperative mood, lowercase start, no trailing period, ≤50 chars (≤72 max)
- Scope: optional, lowercase alphanumeric with hyphens
- Breaking changes: use `!` suffix and/or `BREAKING CHANGE:` footer
- Body: optional, wrap at 72 chars

**This applies to:**

- Direct commits (Phase 3a) — validated before committing
- Agent commits (Phase 3b) — validated after agents complete, amended if non-conformant
- PR titles (Phase 5) — must follow `<type>(<scope>): <description>` format

Load the full reference before crafting any commit message:

```bash
cat ~/.codex/plugins/ycc/skills/git-workflow/templates/commit-types.md
```

---

## Phase 0: Analyze Changes

### Step 1: Check Git Status

Run git commands to analyze current state:

```bash
git status --porcelain
git diff --stat
git diff --cached --stat
```

Determine:

- Staged changes vs unstaged changes
- Total files modified
- Types of files changed (source, test, docs, config)
- Lines added/removed

### Step 2: Automated Analysis

Run the analysis script for structured output:

```bash
~/.codex/plugins/ycc/skills/git-workflow/scripts/analyze-changes.sh
```

This provides:

- Change categorization (source, test, docs, config)
- File count and change metrics
- Recommended strategy (direct vs agents)
- Scope suggestions for commit messages

### Step 3: Review Changed Files

For each modified file, understand:

- What feature or fix is this related to?
- Are changes part of single feature or multiple?
- Do changes warrant documentation updates?

Group related changes together for commit organization.

---

## Phase 0.5: Resolve Action Set

### Step 3.5: Determine Requested Actions

Before proceeding to Phase 1, determine which actions the user requested. The action set is what every later phase keys off — Phase 3 commits only when `commit ∈ actions`, Phase 4 pushes only when `push ∈ actions`, Phase 5 creates a PR only when `pr ∈ actions`.

**Resolution algorithm**:

1. Initialize `actions` from explicit flags: include `commit` if `--commit` is present, `push` if `--push` is present, `pr` if `--pr` is present.
2. Apply implications (cumulative ladder):
   - If `pr ∈ actions`, add `push` and `commit`.
   - If `push ∈ actions`, add `commit`.
3. If `actions` is empty after step 2:
   - **If `--ci ∈ flags`**: leave `actions` empty and skip the interactive menu. Bare `--ci` is valid — it means "monitor CI on the existing PR for this branch; do not commit, push, or create a PR." Proceed to step 4.
   - **Otherwise** (no action flag and no `--ci`): present this menu and wait for the user's reply:

     ```
     No action flag provided. What do you want to do?

       1) Commit only
       2) Commit and push
       3) Commit, push, and create PR

     Reply with 1, 2, or 3 (or pass --commit / --push / --pr next time).
     ```

     Map the reply: `1 → {commit}`, `2 → {commit, push}`, `3 → {commit, push, pr}`. Reject other replies and re-prompt.

4. Validate flag combinations:
   - If `--draft` is present and `pr ∉ actions`, stop with the error: "`--draft` requires `--pr`. Re-run with `--pr --draft`, or omit `--draft`."
   - If `--base <branch>` is present and `pr ∉ actions`, stop with the error: "`--base` requires `--pr`."
   - If `--ci ∈ flags AND actions == {commit}` (commit-only, no push), hard-stop with: `--ci requires --push or --pr (CI runs on the remote, so local-only commits can't be monitored). Pass --ci alone to skip commits and monitor an existing PR.`
   - If `--ci ∈ flags AND --dry-run ∈ flags`, hard-stop with: `--ci is incompatible with --dry-run; the loop performs real pushes.`
5. Record the resolved action set; later phases gate on it. **Bare `--ci`** (actions empty, `--ci ∈ flags`) is a valid recorded state: Phases 3, 4, and 5 all skip; only Phase 6 runs.

**Note**: `--dry-run` is honored regardless of the resolved action set — it applies to whichever action(s) the user picked. `--no-docs` likewise applies regardless.

---

## Phase 1: Determine Strategy

### Step 4: Apply Decision Tree

Use this decision tree to determine approach:

```
Is this a small change?
├─ YES (1-3 files, single feature, minor changes)
│  └─> Use Direct Commit (Phase 3a)
│     - Write commit message yourself
│     - Stage and commit in one operation
│     - Skip agent deployment
│
└─ NO (4+ files, multiple features, substantial changes)
   └─> Use Agent Deployment (Phase 3b)
      - Deploy parallel docs-git-committer agents
      - One agent per feature/significant change
      - Each agent handles docs + commit for its scope
```

**Small Change Criteria:**

- Single feature implementation
- Fewer than 4 files changed
- Clear, focused scope
- Minimal documentation needs
- Bug fix or minor improvement

**Large Change Criteria:**

- Multiple features or significant changes
- 4+ files with substantial modifications
- Cross-cutting changes affecting multiple areas
- New features requiring documentation
- Breaking changes or API modifications

### Step 5: Check for Dry Run Mode

If `--dry-run` is present in `$ARGUMENTS`:

Display the analysis and proposed strategy:

```markdown
# Dry Run: Git Workflow Analysis

## Changes Detected

**Files Changed**: [count]
**Insertions**: [count]
**Deletions**: [count]

### By Type

- Source files: [count]
- Test files: [count]
- Documentation: [count]
- Configuration: [count]

## Recommended Strategy

**Approach**: [Direct Commit / Agent Deployment]

**Reasoning**: [why this strategy was chosen]

## Proposed Actions

[For Direct Commit]

- Commit message: [proposed message]
- Documentation: [yes/no] - [reasoning]

[For Agent Deployment]

- Agent 1: [feature/scope] - docs + commit
- Agent 2: [feature/scope] - docs + commit
- Total agents: [count]

## Next Steps

Remove --dry-run flag to execute the workflow.
```

**STOP HERE** - do not make changes.

---

## Phase 2: Documentation Decision

### Step 6: Load Documentation Decision Tree

Read the documentation decision template:

```bash
cat ~/.codex/plugins/ycc/skills/git-workflow/templates/documentation-decision.md
```

This provides guidance on:

- When feature documentation is needed
- When AGENTS.md updates are appropriate (rarely)
- When architecture/API docs should be updated
- What NOT to document

### Step 7: Determine Documentation Needs

For each changed file or feature, decide:

**Feature Documentation** (docs/features/):

- New user-facing features
- Significant API changes
- Complex data flows
- Breaking changes
- NOT internal refactoring
- NOT bug fixes (unless behavior changes)
- NOT style/formatting changes
- NOT minor performance improvements

**AGENTS.md Updates** (RARELY NEEDED):

- New critical patterns specific to a directory
- Security boundary changes within a directory
- Major architectural decisions affecting a directory
- NOT root AGENTS.md (NEVER update root)
- NOT feature-specific details (put in feature docs)
- NOT most changes (don't need AGENTS.md updates)

**Skip Documentation If**:

- `--no-docs` flag is present
- Changes are purely internal refactoring
- Only test files were modified
- Only documentation files were modified
- Changes are trivial or obvious

---

## Phase 3a: Direct Commit (Small Changes)

### Step 8: Load Commit Message Template

Read the conventional commits reference:

```bash
cat ~/.codex/plugins/ycc/skills/git-workflow/templates/commit-types.md
```

### Step 9: Craft Commit Message

Write a conventional commit message:

**Format**: `<type>(<scope>): <subject>`

**Guidelines**:

- Type: feat, fix, docs, style, refactor, test, chore, perf, ci, build, revert
- Scope: Optional, indicates area of change
- Subject: Imperative mood, no period, max 50 chars
- Body: Optional, wrap at 72 chars, explain what and why
- Footer: Optional, breaking changes or issue references

**Example**:

```
feat(auth): implement JWT-based authentication

Add login endpoint with JWT token generation and validation
middleware for protected routes.

BREAKING CHANGE: Session-based auth is no longer supported.
Existing sessions will be invalidated.
```

### Step 10: Validate Commit Message

Run validation script:

```bash
~/.codex/plugins/ycc/skills/git-workflow/scripts/validate-commit.sh "<commit-message>"
```

If validation fails, revise the message and re-validate.

### Step 11: Stage and Commit

Execute the commit:

```bash
git add [files...]
git commit -m "$(cat <<'EOF'
<commit-message>
EOF
)"
```

**CRITICAL**: Stage and commit in single operation to avoid race conditions.

### Step 12: Optional Push

If `push ∈ resolved action set` (from Phase 0.5):

```bash
git push
```

Skip to Phase 4 (Summary). If `pr ∈ resolved action set`, continue through Phase 4 into Phase 5.

---

## Phase 3b: Agent Deployment (Large Changes)

### Step 13: Identify Feature Scopes

Break changes into logical feature scopes:

- Group files by feature or area
- Each scope should be independently committable
- Identify relationships between scopes

Example scopes:

- "User authentication system"
- "Payment integration"
- "API documentation updates"
- "Test infrastructure improvements"

### Step 14: Load Agent Prompt Template

Read the docs-git-committer prompt template:

```bash
cat ~/.codex/plugins/ycc/skills/git-workflow/templates/agent-prompts.md
```

### Step 15: Deploy Agents in Parallel

**CRITICAL**: Deploy all agents in a **SINGLE message** with **MULTIPLE parallel agent runs**.

For each feature scope, deploy a `docs-git-committer` agent:

| Field         | Value                                                             |
| ------------- | ----------------------------------------------------------------- |
| subagent_type | `docs-git-committer`                                              |
| description   | "Commit [feature-name] with docs"                                 |
| prompt        | Complete instructions including scope, files, documentation needs |

**Agent Instructions Template**:

```
You are handling the git commit and documentation for: [FEATURE SCOPE]

## Changed Files in Your Scope

[List of files related to this feature]

## Context

[Brief description of what changed and why]

## Your Tasks

1. Review the changes in your assigned files
2. Determine if documentation updates are needed (see templates)
3. Update or create documentation if appropriate:
   - Feature docs: docs/features/[name].doc.md
   - AGENTS.md: Only if critically needed in specific directory
   - Architecture docs: docs/architecture/ if system-wide changes
4. Stage all files (source + docs) and commit with conventional message
5. Return summary of what you committed

## Important

- Use conventional commit format
- Combine source + docs in ONE commit
- Use git add + commit in single command
- Do NOT push (main skill handles that)
- Focus ONLY on your assigned scope
```

### Step 16: Track Agent Progress

Create todos for each agent:

```
- agent-1: "[Feature 1] - docs-git-committer - status: in_progress"
- agent-2: "[Feature 2] - docs-git-committer - status: in_progress"
```

### Step 17: Wait for Agents to Complete

Monitor agent execution:

- All agents run in parallel
- Each handles its own scope
- Each creates its own commit
- Wait for all to finish before proceeding

### Step 18: Review and Validate Agent Results

After agents complete:

- Update todos to "completed"
- **Validate each agent's commit message** against conventional commit format:

```bash
~/.codex/plugins/ycc/skills/git-workflow/scripts/validate-commit.sh "$(git log -1 --format=%s <commit-hash>)"
```

- If any commit message fails validation, amend it:

```bash
git rebase -x '~/.codex/plugins/ycc/skills/git-workflow/scripts/validate-commit.sh "$(git log -1 --format=%s HEAD)" || echo "NEEDS FIX"' <merge-base>..HEAD
```

Or for a single commit, use `git commit --amend -m "<corrected-message>"` to fix it.

- Check for conflicts or issues
- Verify documentation quality

**CRITICAL**: Do not proceed to Phase 4 until all agent commits pass conventional commit validation.

---

## Phase 4: Summary and Push

### Step 19: Consolidate Results

Gather information about what was committed:

For direct commits:

- Commit hash and message
- Files changed
- Documentation updates (if any)

For agent deployment:

- List of commits made
- Agents deployed and their results
- Documentation files created/updated
- Any issues encountered

### Step 20: Display Summary

Provide comprehensive completion summary:

```markdown
# Git Workflow Complete

## Commits Made

### Commit 1: [hash]

**Message**: [subject line]
**Files**: [count] files changed
**Changes**: +[insertions] -[deletions]

[If multiple commits, repeat above]

## Documentation Updates

[If docs were updated]

- Created: docs/features/[name].doc.md
- Updated: [other docs]

[If no docs]

- No documentation updates needed (minor changes)

## Summary

- **Total Commits**: [count]
- **Files Changed**: [count]
- **Documentation**: [yes/no]
- **Pushed**: [yes/no]

## Next Steps

[If not pushed]

1. Review the commits: `git log --oneline -[count]`
2. View changes: `git show HEAD`
3. Push when ready: `git push`

[If pushed]
Changes have been pushed to remote
```

### Step 21: Push (if requested)

If `push ∈ resolved action set` and not already pushed in Step 12:

```bash
git push
```

Display push result.

---

## Phase 5: Pull Request Creation (Optional)

### Step 22: Check for PR Flag

If `pr ∈ resolved action set`:

**Prerequisites**:

- Branch must be pushed to remote
- GitHub MCP server OR GitHub CLI (`gh`) must be available:
  - If MCP tools available (`mcp__github__*`): no additional prerequisites
  - If using CLI fallback: `gh` must be installed and authenticated
- Phase 0.5 guarantees `push` and `commit` are in the action set whenever `pr` is — this step assumes commits exist and the branch has been pushed in Step 12 or Step 21.

### Step 22a: Detect Existing PR

Before generating description or invoking `create-pr.sh`, check whether a PR already exists for the current branch:

```bash
EXISTING_PR=$(gh pr list --head "$CURRENT_BRANCH" --json number,url --jq '.[0]' 2>/dev/null || echo "")
```

When MCP tools are available, prefer `mcp__github__list_pull_requests` with `head=<branch>` over the `gh` CLI, per the Tool Preference Strategy.

**If no existing PR is found**, proceed to Step 23 normally (full PR-creation path).

**If an existing PR is found**:

- **If `--ci ∈ flags`**: prompt the user:

  ```
  PR #<num> already exists for this branch (<url>).
  Skip PR creation and run --ci against the existing PR? (yes/no):
  ```

  On `yes`: record `PR_NUMBER=<num>` and `PR_URL=<url>`, skip Steps 23-31 (do **not** call `create-pr.sh`), and fall through to Phase 6.

  On `no`: exit cleanly with `PR already exists; --ci not run. Use 'gh pr view <num>' to inspect.` Do not proceed to Phase 6.

- **If `--ci ∉ flags`**: stop with the existing "PR already exists" message — `PR already exists for this branch: #<num>. View: gh pr view <num>. Edit: gh pr edit <num>.` This preserves today's behavior for users who passed `--pr` and only wanted PR creation.

`create-pr.sh` itself still detects an existing PR and exits 1 as a defensive fallback for any path that reaches it.

### Step 22b: Resolve Base, Guard Sync Merges, Offer Backport

Follow [`../_shared/references/pr-base-and-backport.md`](../_shared/references/pr-base-and-backport.md) with `GUARD=~/.codex/plugins/ycc/shared/scripts/pr-guard.sh`:

1. `git fetch origin`, then `BASE=$(bash "$GUARD" base [--base <branch>])` — pass `--base` only when the user gave it. Use `$BASE` everywhere below.
2. `bash "$GUARD" sync-check --base "$BASE"` — exit 3: do **not** create the PR; show the reason, cite `branching-model.md#rules`, and stop (Phase 6 does not run).
3. After the title is drafted (Step 25), `bash "$GUARD" backport-label --base "$BASE" --title "<title>"`; on `backport=1` ask `Backport to <branch>? (yes/no)` and remember the answer for Step 29.

Exit 2 from any call (malformed `RELEASING.md`) stops Phase 5 with the parse error and `$release-model --audit`.

### Step 23: Load PR Template

Read the PR template:

```bash
cat ~/.codex/plugins/ycc/skills/git-workflow/templates/pr-template.md
```

This provides:

- PR title guidelines (based on commits)
- Description structure
- Review checklist
- Testing guidance
- When to use draft PRs

### Step 24: Gather PR Context

Run the PR creation script to gather information:

```bash
~/.codex/plugins/ycc/skills/git-workflow/scripts/create-pr.sh --analyze --base "$BASE"
```

This provides:

- Current branch name
- Base branch (`$BASE` from Step 22b)
- Commit history since divergence
- Changed files summary
- Documentation changes
- Suggested PR title and scope

**Forge provider detection**: `create-pr.sh` runs forge detection on `origin`
first and routes PR creation through the matching CLI — `gh` for `github`,
`tea` for `forgejo`/`gitea` (`gh pr create` ↔ `tea pull create`). The MCP-first
path above applies only to `github`; on a `forgejo`/`gitea` remote the script
drives `tea` directly. See
[`../_shared/references/forge-detection.md`](../_shared/references/forge-detection.md)
for the detection algorithm and operation-equivalence map. Log the resolved
provider + CLI so the user sees which forge the PR targeted.

### Step 25: Generate PR Title

PR titles **MUST** follow the conventional commit format: `<type>(<scope>): <description>`

Based on commits made, create a PR title:

**Single commit**: Use the commit subject line directly (already validated)

**Multiple related commits**: Create a descriptive title that follows the same conventional format

Validate the PR title with the same rules as commit messages:

```bash
~/.codex/plugins/ycc/skills/git-workflow/scripts/validate-commit.sh "<pr-title>"
```

If validation fails, revise the title until it passes.

**Examples**:

```
feat(auth): implement JWT authentication system
fix(api): resolve multiple payment processing issues
docs: update API documentation and examples
refactor(database): migrate to new query builder pattern
```

### Step 26: Generate PR Description

Create comprehensive PR description following this structure:

```markdown
## Summary

[2-4 sentence overview of what this PR does and why]

## Changes

- [Key change 1 with context]
- [Key change 2 with context]
- [Key change 3 with context]

## Documentation

[If docs were created/updated]

- Feature docs: docs/features/[name].doc.md
- API docs: docs/api/[endpoint].md
- Architecture docs: docs/architecture/[topic].md

[If no docs]

- No documentation changes needed

## Testing

[For each feature/change]

### [Feature Name]

**How to test:**

1. Step one
2. Step two
3. Expected result

**Edge cases:**

- Edge case 1 to verify
- Edge case 2 to verify

## Related Issues

[If applicable]
Closes #123
Fixes #456
Related to #789

## Breaking Changes

[If any]
BREAKING CHANGE: [Description]

**Migration steps:**

1. Step one
2. Step two

[If none]

- No breaking changes

## Checklist

- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex logic
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests passing
- [ ] No new warnings
```

### Step 27: Determine PR Type

Decide between regular PR and draft PR:

**Use draft PR** (`--draft` flag) when:

- Work is not fully complete
- Seeking early feedback
- Tests are not passing yet
- Documentation is incomplete
- Breaking changes need discussion

**Use regular PR** when:

- Work is complete and tested
- Ready for immediate review
- All checks passing
- Documentation is complete

### Step 28: Create Pull Request

#### If GitHub MCP tools are available (preferred)

Use `mcp__github__create_pull_request` with:

- `owner`: Repository owner (extract from `git remote get-url origin`)
- `repo`: Repository name (extract from `git remote get-url origin`)
- `title`: PR title from Step 25
- `body`: PR description from Step 26
- `head`: Current branch name
- `base`: `$BASE` from Step 22b
- `draft`: `true` if `--draft` flag is set, `false` otherwise

The MCP tool returns the PR number and URL in structured data.

#### If MCP is unavailable or fails — fall back to GitHub CLI

**For regular PR**:

```bash
gh pr create \
  --title "[PR Title]" \
  --base "$BASE" \
  --body "$(cat <<'EOF'
[PR Description from Step 26]
EOF
)" \
  --web
```

**For draft PR**:

```bash
gh pr create \
  --title "[PR Title]" \
  --base "$BASE" \
  --body "$(cat <<'EOF'
[PR Description from Step 26]
EOF
)" \
  --draft \
  --web
```

The `--web` flag opens the PR in browser for final review.

### Step 29: Handle PR Creation Results

After PR creation:

**Success**:

- Capture PR number and URL
- Display PR link to user
- Note if draft or ready for review
- If the backport prompt (Step 22b) was answered yes: add the `backport:X.Y` label and print `After #<N> merges, run $backport <N>` (see the shared reference)

**Failure scenarios**:

1. **No upstream branch**: Offer to push with `-u origin [branch]`
2. **Branch not pushed**: Automatically push and retry
3. **gh CLI not installed**: If MCP tools are available, use those instead; otherwise provide installation instructions
4. **Not authenticated**: If MCP tools are available, use those instead; otherwise guide to run `gh auth login`
5. **PR already exists**: Offer to update or view existing PR
6. **MCP tool failed**: Fall back to `gh` CLI and retry the operation

### Step 30: Post-PR Summary

Display comprehensive PR creation summary:

```markdown
# Pull Request Created

## PR Details

**Number**: #[number]
**Title**: [PR title]
**URL**: [GitHub URL]
**Status**: [Draft/Ready for Review]
**Base**: [base-branch] <- [current-branch]

## Commits Included

- [hash]: [commit message]
- [hash]: [commit message]

## Files Changed

**Total**: [count] files

- Source: [count]
- Tests: [count]
- Docs: [count]

## Next Steps

1. PR is ready for review
2. View PR: [URL]
3. Request reviewers in GitHub
4. Monitor CI/CD checks
5. Address review feedback

[If draft]

## Draft PR Status

This PR is marked as draft. To mark ready for review:

    gh pr ready [PR number]

Complete these before marking ready:

- [ ] All tests passing
- [ ] Documentation complete
- [ ] Self-review done
```

### Step 31: Optional PR Template Check

If repository has `.github/PULL_REQUEST_TEMPLATE.md`:

- Read the template
- Ensure generated description follows template structure
- Fill in any template-specific sections

---

## Phase 6: CI Monitoring (Optional, `--ci` flag)

**Trigger:** This phase runs ONLY when `--ci ∈ flags`. Skip silently otherwise. Phase 6 does not require Phase 5 to have run — bare `--ci` and `--push --ci` both reach this phase by design.

**GitHub-only:** The CI auto-fix loop is GitHub-only — it depends on `gh run`
controls (`gh run view --log-failed`, `gh run rerun`). On a non-GitHub remote
`ci-monitor.sh` returns `RESULT=unsupported-provider` (exit 2). Treat this like
`pr-not-found`/`refused-default-branch`: report it directly and **skip the loop
without erroring**. State that the loop is GitHub-only and why, then end Phase 6
cleanly. See
[`../_shared/references/forge-detection.md`](../_shared/references/forge-detection.md)
and [`../_shared/references/ci-monitoring.md`](../_shared/references/ci-monitoring.md).

### Step 32: Discover PR for the current branch

If a `PR_NUMBER` was captured in Phase 5 (either newly created in Steps 23-30 or detected as existing in Step 22a), use it directly and skip ahead to Step 33.

Otherwise (bare `--ci`, `--push --ci`, or any path where Phase 5 didn't run), look up the PR for the current branch:

```bash
PR_NUMBER=$(gh pr list --head "$CURRENT_BRANCH" --json number --jq '.[0].number' 2>/dev/null || echo "")
PR_URL=$(gh pr list --head "$CURRENT_BRANCH" --json url --jq '.[0].url' 2>/dev/null || echo "")
```

When MCP tools are available, prefer `mcp__github__list_pull_requests` with `head=<branch>` over the `gh` CLI, per the Tool Preference Strategy.

- If `PR_NUMBER` is empty: hard-stop with `--ci was passed but no open PR exists for branch '<branch>'. Re-run with --pr to create one, or open a PR manually first.`
- Otherwise: record `PR_NUMBER` and `PR_URL`, then proceed to Step 33.

### Step 33: Load policy reference

Read `~/.codex/plugins/ycc/shared/references/ci-monitoring.md` to load the failure-classification table, termination policy, audit log schema, and loop protocol. Treat that file as authoritative — do not duplicate its content here.

### Step 34: One-time authorization prompt

Skip if `--ci-yes`. Otherwise display:

```
CI auto-fix loop authorization
==============================
PR:                 #<pr_number> (<head_branch> → <base_branch>)
Max auto-pushes:    <resolved --ci-max-pushes>
Max same failure:   <resolved --ci-max-same-failure>
Wall-clock timeout: <resolved --ci-timeout-min> minutes
Audit log:          ~/.codex/session-data/ci-watch/<pr>-<timestamp>.log

Safety constraints (non-toggleable):
  - Never `git push --force`
  - Never `--no-verify`
  - Only push to PR head branch
  - Refuse if head equals default branch

Proceed? (yes/no):
```

On `no`, exit cleanly with `CI monitoring declined; PR was created but not monitored.`

### Step 35: Initialize audit log

Create directory `~/.codex/session-data/ci-watch/` if absent. Compute log path `~/.codex/session-data/ci-watch/<pr>-<utc-iso-timestamp>.log` and remember it for the loop.

### Step 36: Loop iteration

Invoke the script:

```
~/.codex/plugins/ycc/shared/scripts/ci-monitor.sh \
  --pr <pr_number> \
  --branch <head_branch> \
  --base <base_branch> \
  --max-pushes <N> \
  --max-same-failure <N> \
  --timeout-min <N> \
  --log-file <audit_log_path>
```

Branch on stdout `RESULT=...` per the **Loop Protocol** section of `ci-monitoring.md`:

- `green` → Render success block (CI passed); end Phase 6.
- `handoff` → Read `RUN_ID`, `WORKFLOW`, `JOB`, `CATEGORY`, `SIGNATURE`, `LOG_EXCERPT_FILE`, `SUGGESTED_COMMIT_TYPE`, `SUGGESTED_COMMIT_SCOPE` from stdout. Apply fix per the Failure Classification table for `CATEGORY` (which lives in `ci-monitoring.md`). Use the same direct-vs-agents decision tree from Phase 1 of THIS skill (constrained to the failure scope). Stage the fix, validate the commit message via `~/.codex/plugins/ycc/skills/git-workflow/scripts/validate-commit.sh`, commit, then push to head branch (NEVER `--force`, NEVER `--no-verify`). Goto Step 36.
- `rerun-pending` → Flake-suspected; the script already triggered `gh run rerun --failed`. Do NOT apply any fix. Sleep 30 seconds (`sleep 30`), then goto Step 36.
- `bail-recurrence` / `bail-nonfixable` / `bail-pushes` / `bail-timeout` → Render a diagnosis block citing the audit log path, the `RESULT=` value, the `REASON=` line if present, and the cap that fired. End Phase 6 (do NOT push further).
- `pr-not-found` / `refused-default-branch` → Surface the error directly; do not retry.
- `unsupported-provider` → Remote is not GitHub; the CI auto-fix loop is GitHub-only. Report that the loop is GitHub-only and skip it cleanly; do not retry and do not treat as an error.

### Step 37: Final report

On `green`, print:

```
✓ CI green for PR #<pr> after <iterations> iteration(s), <pushes> auto-push(es).
  URL: <url>
  Audit log: <path>

Goal Signals (machine-readable — printed verbatim for /goal)
PR_IN_SCOPE: PASS
PR_URL_PRINTED: PASS
CI_GREEN: PASS
CI_BAIL_VISIBLE: n/a
```

On any bail, print:

```
✗ CI monitoring ended: <RESULT> — <REASON>
  Cap fired: <which cap or constraint>
  URL: <url>
  Audit log: <path>

Goal Signals (machine-readable — printed verbatim for /goal)
PR_IN_SCOPE: PASS
PR_URL_PRINTED: PASS
CI_GREEN: FAIL
CI_BAIL_VISIBLE: PASS
```

Print every Goal Signal verbatim, one `KEY: PASS|FAIL|n/a` per line, as the **last lines
of the run** when `--ci` is set. Use `PASS` only when the matching `## Success Criteria`
item holds; otherwise use `FAIL`. `CI_BAIL_VISIBLE` is `PASS` only when a terminal
`bail-*` result and its `REASON=` or equivalent diagnosis were printed; otherwise it is
`n/a`.

See `~/.codex/plugins/ycc/shared/references/ci-monitoring.md` for the full policy (classification, termination, schema).

---

## Success Criteria

- **PR_IN_SCOPE**: A PR is in scope for this run — either created in Phase 5,
  detected as existing in Step 22a, or discovered from the current branch in Step 32.
- **PR_URL_PRINTED**: The final CI report prints the PR URL along with the PR number.
- **CI_GREEN**: The Phase 6 loop reached `RESULT=green` and the Step 37 report shows
  `✓ CI green`.
- **CI_BAIL_VISIBLE**: If the Phase 6 loop bailed, the Step 37 report states the
  `bail-*` result, the reason, and the cap or constraint that fired. `n/a` when CI
  reached green.

These keys are emitted verbatim in the Step 37 Goal Signals block so a `/goal` evaluator
can observe CI-loop completion from the transcript alone.

---

## /goal pairing

Pair this skill with the `/goal` session directive **only in `--ci` mode**. Without
`--ci`, `$git-workflow` may stop after a local commit, push, or PR creation, and
there is no long-running loop for `/goal` to drive. In `--ci` mode, Phase 6 enters the
bounded CI auto-fix loop using the shared `ci-monitor.sh` contract, and `/goal` can keep
the session moving through every `handoff` fix-and-push and `rerun-pending` flake retry.

The Phase 6 loop's stdout `RESULT=` markers tell the evaluator when to keep looping
versus when to stop:

- **Keep looping** — `handoff` (apply the fix per the classification table, commit, push
  to the PR head branch, re-invoke the monitor) and `rerun-pending` (flake suspected;
  sleep, then re-invoke). These are recoverable progress markers, not endpoints.
- **Done** — `RESULT=green` (`CI_GREEN: PASS`), with the PR URL printed in the final
  report.
- **Stop** — any `bail-*` (`bail-recurrence`, `bail-nonfixable`, `bail-pushes`,
  `bail-timeout`). All are terminal: `ci-monitor.sh` exhausts recoverable
  `rerun-pending` retries internally before emitting a bail, so a printed `bail-*` means
  no further automatic progress is possible. The evaluator distinguishes "loop again"
  from "stop" by `green` vs `bail-*` in the Step 37 report — never by re-classifying
  bail codes. See `~/.codex/plugins/ycc/shared/references/ci-monitoring.md` for
  the authoritative bail taxonomy.

Recommended condition template (`--ci` mode):

```
/goal Run $git-workflow --ci using the git-workflow workflow, continuing through
every handoff and rerun-pending iteration of the Phase 6 CI loop without returning control
to me. Done when the transcript shows the final CI report with the PR number and URL,
followed by the Goal Signals printed verbatim — PR_IN_SCOPE: PASS, PR_URL_PRINTED: PASS,
and CI_GREEN: PASS. If CI_GREEN prints FAIL alongside CI_BAIL_VISIBLE: PASS (a terminal
bail-* fired), stop and report the bail — do not re-run. If any other signal prints FAIL,
keep fixing and re-running until all are PASS. Stop after 25 turns if not achieved.
```

The transcript-output contract and shared caveats (worktree cwd, interactive failure
prompts, platform availability) live in the shared reference — read it before relying on a
`/goal` loop:

```
~/.codex/plugins/ycc/shared/references/goal-pairing.md
```

---

## Quality Standards

### Commit Message Checklist

- [ ] Uses conventional commit format
- [ ] Type is appropriate (feat, fix, docs, etc.)
- [ ] Subject line is imperative mood
- [ ] Subject line is <=50 characters
- [ ] No period at end of subject
- [ ] Body explains what and why (if needed)
- [ ] Breaking changes noted in footer (if applicable)

### Documentation Checklist

- [ ] Feature docs created for new features
- [ ] AGENTS.md updated ONLY if critical and directory-specific
- [ ] Architecture docs updated for system-wide changes
- [ ] API docs updated for public API changes
- [ ] Documentation is concise and actionable
- [ ] No documentation for trivial changes

### Agent Deployment Checklist

- [ ] All agents deployed in single message
- [ ] Each agent has clear, non-overlapping scope
- [ ] Agent instructions include file list
- [ ] Agents use conventional commits
- [ ] Each agent commits separately
- [ ] No agent pushes (main skill handles that)

### Pull Request Checklist

- [ ] PR title follows conventional commit format
- [ ] Description includes summary of changes
- [ ] Testing instructions are clear and complete
- [ ] Documentation changes are noted
- [ ] Breaking changes are clearly marked
- [ ] Related issues are referenced
- [ ] PR type is appropriate (draft vs ready)
- [ ] All commits follow conventional format

### Overall Quality Checklist

- [ ] All changes committed (nothing left unstaged)
- [ ] Commits are atomic and focused
- [ ] Documentation appropriate to change scope
- [ ] Push successful (if requested)
- [ ] Summary provided to user

---

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────┐
│ Phase 0: Analyze Changes                                │
│ - git status, git diff                                  │
│ - Categorize files                                      │
│ - Run analysis script                                   │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 1: Determine Strategy                             │
│ - Apply decision tree                                   │
│ - Small (1-3 files) vs Large (4+ files)                 │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴────────────┐
        │                      │
        ▼                      ▼
┌──────────────────┐  ┌────────────────────────┐
│ Phase 3a:        │  │ Phase 3b:              │
│ Direct Commit    │  │ Agent Deployment       │
│                  │  │                        │
│ - Write message  │  │ - Deploy parallel      │
│ - Stage files    │  │   docs-git-committer   │
│ - Commit         │  │   agents               │
└────────┬─────────┘  │ - Each commits scope   │
         │            └──────────┬─────────────┘
         │                       │
         └─────────┬─────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 4: Summary and Push                               │
│ - Consolidate results                                   │
│ - Display summary                                       │
│ - Optional push (--push flag)                           │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ Phase 5: Pull Request (Optional, --pr flag)             │
│ - Gather PR context                                     │
│ - Generate title and description                        │
│ - Create PR (draft or ready)                            │
│ - Display PR URL and next steps                         │
└─────────────────────────────────────────────────────────┘
```

---

## Important Notes

- **Small changes**: Handle directly for speed and simplicity
- **Large changes**: Use agents for parallel documentation + commits
- **Conventional commits**: Always use proper format for consistency
- **Documentation**: Only update when substantial changes warrant it
- **AGENTS.md**: Rarely needed, only for critical directory-specific patterns
- **Atomic commits**: Stage and commit in single operation
- **Explicit actions**: every invocation must select at least one of `--commit`, `--push`, or `--pr` (or pick from the interactive menu). Push and PR are never implicit.
- **Pull requests**: `--pr` implies `--push` and `--commit` — one flag is enough.
- **Cumulative ladder**: `--commit` < `--push` < `--pr`. Each step up adds the prior steps; flag order does not matter.
- **Draft PRs**: Use `--draft` with `--pr` for work-in-progress or early feedback
- **MCP-first**: GitHub operations prefer MCP tools (`mcp__github__*`) when available, with automatic `gh` CLI fallback
- **GitHub tools required**: PR creation requires GitHub MCP server or `gh` CLI tool installed and authenticated

---

## Examples

### Example 1: Small Change (Direct Commit)

**Scenario**: Fixed a bug in user validation

```bash
# Analysis shows: 1 file, 10 lines changed
# Strategy: Direct commit
# User runs: $git-workflow --commit

# Crafted message:
fix(auth): prevent null email validation bypass

# Committed:
git add src/services/auth.ts
git commit -m "fix(auth): prevent null email validation bypass"
```

### Example 2: Large Change (Agent Deployment)

**Scenario**: Implemented user authentication system

```bash
# Analysis shows: 8 files, 450 lines changed
# Strategy: Agent deployment

# Deployed 3 agents:
# 1. docs-git-committer: Auth backend (models, services, middleware)
# 2. docs-git-committer: Auth frontend (components, hooks)
# 3. docs-git-committer: Auth tests (unit + integration)

# Result: 3 commits, feature docs created
```

### Example 3: Documentation-Only Change

**Scenario**: Updated API documentation

```bash
# Analysis shows: 2 doc files changed
# User runs: $git-workflow --commit
# Strategy: Direct commit (no feature changes)

# Message:
docs(api): update authentication endpoint examples

# No documentation agents needed (already docs)
```

### Example 4: Complete Workflow with PR

**Scenario**: Implemented new payment feature, commit and create PR

```bash
# User runs with PR flag
/git-workflow --pr
# Note: --pr implies --push and --commit — one flag is enough

# Workflow executes:
# 1. Analyzes changes (12 files)
# 2. Deploys agents (payment backend, frontend, tests)
# 3. Each agent commits with docs
# 4. Pushes to remote
# 5. Creates PR automatically

# Result:
# - 3 commits made
# - Feature docs created
# - PR #123 created and ready for review
# - PR URL displayed for user
```

### Example 5: Draft PR for Work-in-Progress

**Scenario**: New feature not fully complete, seeking early feedback

```bash
/git-workflow --pr --draft
# Note: --draft requires --pr; it is not an action flag on its own

# Workflow executes:
# 1. Commits current work
# 2. Pushes to remote
# 3. Creates draft PR
# 4. Marks as "not ready for review"

# Result:
# - Draft PR created
# - Reviewers can see progress
# - Can be marked ready later with: gh pr ready [number]
```

### Example 6: Commit Only (No PR)

**Scenario**: Feature complete but not ready to create PR yet

```bash
/git-workflow --push
# Note: --push implies --commit

# Workflow executes:
# 1. Commits and documents
# 2. Pushes to remote
# 3. Stops (no PR created)

# User can create PR later:
# /git-workflow --pr  (will use existing commits)
```

### Example 7: No Flags (Interactive Prompt)

**Scenario**: User invokes the skill without an action flag

```bash
$git-workflow

# Workflow renders the menu:
#   No action flag provided. What do you want to do?
#     1) Commit only
#     2) Commit and push
#     3) Commit, push, and create PR
#
# User replies: 2
# Resolved action set: {commit, push}
# Workflow proceeds: analyze → commit → push → summary
```

### Example 8: CI Monitoring on an Existing PR

**Scenario A**: PR is already open; add a commit and watch CI

```bash
$git-workflow --push --ci

# Workflow:
# 1. Commits and pushes new work to the PR branch
# 2. Phase 5 is skipped (pr ∉ actions)
# 3. Phase 6 discovers the existing PR via `gh pr list --head <branch>`
# 4. Auth prompt, then bounded auto-fix loop
```

**Scenario B**: Nothing new to push; just monitor the existing PR

```bash
$git-workflow --ci

# Bare --ci is valid. Workflow:
# 1. Phases 3, 4, 5 all skip (actions is empty)
# 2. Phase 6 discovers the existing PR for the current branch
# 3. Monitor + auto-fix loop runs against whatever commits are already pushed
```

**Scenario C**: PR already exists and you passed `--pr --ci` by habit

```bash
$git-workflow --pr --ci

# Workflow:
# 1. Commits and pushes
# 2. Step 22a detects the existing PR and prompts:
#    "PR #N already exists. Skip PR creation and run --ci against it? (yes/no)"
# 3. On yes: skip create-pr.sh, proceed to Phase 6 on PR #N
# 4. On no: exit cleanly, no CI monitoring
```

---

## Troubleshooting

### Issue: Validation script fails

**Solution**: Review commit message format, check type is valid, ensure subject <=50 chars

### Issue: Too many agents suggested

**Solution**: Group related changes, combine scopes, or use sequential commits

### Issue: Unclear what changed

**Solution**: Use `git diff` to review changes, `git log` for context, ask user for clarification

### Issue: Conflicts between agent commits

**Solution**: This shouldn't happen with proper scope isolation, but if it does, manually resolve and recommit

### Issue: Documentation decision unclear

**Solution**: When in doubt, skip documentation for minor changes, create it for substantial features

### Issue: MCP tools detected but GitHub operation fails via MCP

**Solution**: The workflow automatically falls back to `gh` CLI. If both fail, check:

- Repository permissions
- Authentication status (`gh auth status`)
- Branch is pushed to remote
- MCP server configuration is correct

### Issue: PR creation fails - gh CLI not installed

**Solution**: If GitHub MCP tools are available, the workflow will use those instead. Otherwise, install GitHub CLI:

```bash
# macOS
brew install gh

# Linux
# See: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
```

### Issue: PR creation fails - not authenticated

**Solution**: Authenticate with GitHub:

```bash
gh auth login
# Follow prompts to authenticate
```

### Issue: PR creation fails - no upstream branch

**Solution**: Push with upstream:

```bash
git push -u origin [branch-name]
# Then retry with --pr flag
```

### Issue: PR already exists for branch

**Solution**: View existing PR or update it:

```bash
# View PR
gh pr view

# Or create new branch for separate PR
git checkout -b [new-branch-name]
```

### Issue: Draft PR but want to mark ready

**Solution**: Mark PR as ready for review:

```bash
gh pr ready [PR-number]
```
