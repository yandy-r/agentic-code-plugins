---
name: code-review
description: 'Reviews local changes or GitHub PRs and saves actionable findings. Use when reviewing a PR, requesting a full local review, or creating a review-fix artifact.'
argument-hint: '[--quick] [--approve | --request-changes] [--parallel | --team] [--no-worktree] [--keep-draft] [--keep-worktree] [--yes] [--save] [pr-number | pr-url | blank for local review]'
allowed-tools:
  - Read
  - Grep
  - Glob
  - Write
  - Skill
  - Agent
  - Task
  - TeamCreate
  - TeamDelete
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - SendMessage
  - Bash(git:*)
  - Bash(gh:*)
  - Bash(ls:*)
  - Bash(cat:*)
  - Bash(test:*)
  - Bash(find:*)
  - Bash(npm:*)
  - Bash(pnpm:*)
  - Bash(yarn:*)
  - Bash(bun:*)
  - Bash(npx:*)
  - Bash(cargo:*)
  - Bash(go:*)
  - Bash(pytest:*)
  - Bash(python:*)
  - Bash(python3:*)
  - Bash(make:*)
  - 'mcp__github__*'
  - 'Bash(${CURSOR_PLUGIN_ROOT}/skills/_shared/scripts/*.sh:*)'
---

# Code Review

Review local changes or a GitHub PR; save machine-parseable findings for
`/review-fix`. Input: `$ARGUMENTS`. Use `/quick-review` for inline-first
local review. PR review mode adapted from PRPs-agentic-eng by Wirasm.

## Parse flags and select mode

Extract flags before interpreting the remaining text as the selector:

| Flag                | Effect                                                       |
| ------------------- | ------------------------------------------------------------ |
| `--approve`         | Override PR decision to APPROVE; still report findings       |
| `--request-changes` | Override PR decision to REQUEST CHANGES                      |
| `--parallel`        | 3 standalone `code-reviewer` reviewers                   |
| `--team`            | Same roster, Claude Code agent team                          |
| `--worktree`        | Legacy no-op; PR worktree isolation is default               |
| `--no-worktree`     | PR: skip worktree, artifact commit/push and cleanup          |
| `--keep-draft`      | PR: skip draft-to-ready promotion; draft decision is COMMENT |
| `--keep-worktree`   | PR: keep worktree after successful publish                   |
| `--quick`           | Alias for `/quick-review` after validation               |

Strip these from `$ARGUMENTS` and set `QUICK_MODE=true|false`, `PARALLEL_MODE=true|false`, `AGENT_TEAM_MODE=true|false`, `NO_WORKTREE_MODE=true|false`, `KEEP_DRAFT=true|false`, and `KEEP_WORKTREE=true|false`. Compute `WORKTREE_MODE=true` unless `--no-worktree` is present (default-on in PR mode; ignored for local mode as before). The remaining text is the mode selector (PR number/URL or blank for local).

Gates (abort on invalid combinations):

- Both `--parallel` and `--team`:
  `--parallel and --team are mutually exclusive. Pick one.`
- `--team` in Cursor/Codex bundles:
  `--team is not supported in bundle invocations; use --parallel instead.`
- `--team` without `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`:
  `--team requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1. Use --parallel instead, or set CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in your Claude Code settings if you intentionally want agent-team dispatch.`
- `--quick` with PR number/URL:
  `--quick only reviews uncommitted local changes; remove the PR argument or drop --quick.`
- `--quick` with `--approve`/`--request-changes`:
  `--approve / --request-changes have no meaning in quick mode (no GitHub review is posted). Drop the flag or use PR mode.`
- Quick mode accepts `--no-worktree`, `--keep-draft`, `--keep-worktree` as
  no-ops; print `<flag> has no effect in quick mode.`

Mode selection: `--quick` first; PR number/URL (or branch selector) means PR;
blank means local. Local/quick mode MUST NOT post to GitHub, promote drafts,
commit/push artifacts, or remove worktrees.

### Quick delegation

Print:
`--quick delegated to /quick-review. Run /quick-review directly for full option surface (--yes, --save, --severity).`

Invoke `Skill: quick-review`, forwarding its accepted flags (`--parallel`
or `--team`, `--yes`, `--save`, `--write-and-apply`, `--severity <level>`).
Drop code-review-owned flags (`--quick`, decision and worktree flags).
After delegation exit; quick-review owns artifact lifecycle.

## REVIEW path (both modes)

Read changed files in full. Apply mode-specific checklist and severity rubric:

`${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md`

Flag only gaps that affect correctness or the stated requirements. Checklist
items are investigation prompts, not automatic style findings.

The shape of this phase depends on `PARALLEL_MODE` and `AGENT_TEAM_MODE`:

| Flags             | Path                                        |
| ----------------- | ------------------------------------------- |
| Neither set       | **Path A** — single-pass review (default)   |
| `PARALLEL_MODE`   | **Path B** — 3 parallel sub-agent reviewers |
| `AGENT_TEAM_MODE` | **Path C** — 3-reviewer agent team          |

Read only on the selected fan-out path:

- `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-dispatch.md`
- `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/standalone-dispatch.md`
  (`--parallel` only; dispatch contract and scratch recovery)
- `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`
  (`--team` only; team creation, tasks up front, shutdown, deletion)

Reviewers use checklist roster, pre-ID findings format and merge procedure,
plus the prompt contract in review-dispatch.md. PR prompts include head revision and Phase 2 context. Assign IDs only
after merging; record partial-review gaps, never fabricate failed-role findings.

## Local Review Mode

Uncommitted changes cannot be branch-isolated. Set `WORKTREE_ACTIVE=false`.
If explicit `--worktree`, print:
`Note: --worktree has no effect in local mode; uncommitted changes are not branch-isolated.`

1. **GATHER** — `git diff --name-only HEAD`. Empty: `Nothing to review.`; stop.
2. **REVIEW** — Read changed files, project rules and relevant requirements;
   follow REVIEW path above (Local / Quick checklist).
3. **REPORT** — Read canonical artifact schema before writing:
   `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-artifact-format.md`.
   Generate one timestamp per invocation, reused for any fan-out run-id and
   `docs/prps/reviews/local-{YYYYMMDD-HHMMSS}-review.md`. Write even when no
   findings. Apply the schema's Finding ID rules — IDs ordered by severity
   (CRITICAL first), then by file path — plus initial Status and required
   fields.
   Omit Worktree Setup. Include validation table; mark unrun checks Skipped.
   After successful write remove this invocation's parallel scratch directory.

<<<<<<< HEAD
Print artifact path, severity counts, and `/review-fix <path>` (optionally
`--parallel`) as next steps. Block commit if CRITICAL/HIGH issues exist; never
approve security vulnerabilities.
||||||| parent of 4bc30c8 (fix(agents): scope db-modifier Bash, drop stray write tools, clarify reviewer duties)
```bash
git diff --name-only HEAD
```

If no changed files, stop: "Nothing to review."

### Phase 2 — REVIEW

The shape of this phase depends on `PARALLEL_MODE` and `AGENT_TEAM_MODE`:

| Flags             | Path                                        |
| ----------------- | ------------------------------------------- |
| Neither set       | **Path A** — single-pass review (default)   |
| `PARALLEL_MODE`   | **Path B** — 3 parallel sub-agent reviewers |
| `AGENT_TEAM_MODE` | **Path C** — 3-reviewer agent team          |

#### Path A — Single-Pass Review (default, neither flag set)

Read each changed file in full and apply the **Local / Quick Review —
Single-Pass Checklist** (Security CRITICAL, Code Quality HIGH, Best Practices
MEDIUM) and the **Severity Rubric** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

#### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Generate `TIMESTAMP=$(date +%Y%m%d-%H%M%S)` once, here, and reuse the same
variable for the Phase 3 review filename (`local-<TIMESTAMP>-review.md`) — one
canonical timestamp per invocation. Set `run-id = local-<TIMESTAMP>`.

> **Standalone dispatch rule**: Dispatch the 3 reviewers via the blocking
> `Task` tool in ONE message — never the async `Agent` tool, and never with
> `name`, `team_name`, or `run_in_background` set. In the normal case `Task`
> blocks and its return value IS each reviewer's findings, delivered inline in
> the same turn. If a batch doesn't return inline (async fallback), don't
> `sleep`-loop or poll — yield/end the turn so the completion notification can
> flush, then resume. See
> [standalone-dispatch.md](${CURSOR_PLUGIN_ROOT}/skills/_shared/references/standalone-dispatch.md)
> for the full contract.

Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE `Task` tool calls. Use the **Local / Quick Mode Roster**
(`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) and
**Standard Findings Format** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

Per the scratch-backstop contract in that reference, also pass each reviewer
its own scratch path — `docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/<reviewer-name>.md`
(e.g. `.../correctness-reviewer.md`) — alongside the changed files, its focus +
checklist items, the severity rubric, and the findings-format directive.

After all 3 `Task` calls return: for any reviewer whose inline return is
empty, missing, or malformed, re-read its scratch file at that path before
merging (Merge Procedure in the reference). Pass the merged findings to
Phase 3 (REPORT) as if they came from a single-pass review. Phase 3 removes
the `docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/` directory once the
review artifact has been written successfully.

#### Path C — Agent Team Review (`AGENT_TEAM_MODE=true`, Claude Code only)

> **MANDATORY — AGENT TEAMS REQUIRED**
>
> In Path C you MUST follow the agent-team lifecycle. Do NOT mix standalone sub-agents
> with team dispatch. Every `Agent` call below MUST include `team_name=` AND `name=`.
>
> 1. `TeamCreate` once at the start
> 2. `TaskCreate` for all 3 reviewer subtasks up front (flat graph — no dependencies)
> 3. Spawn 3 teammates: single message, three `Agent` calls with `team_name=` + `name=`
> 4. `TaskList` to monitor until all reviewers mark complete
> 5. `SendMessage({type:"shutdown_request"})` to all 3 teammates
> 6. `TeamDelete` before merging
>
> If `TeamCreate` or `TaskCreate` fails, abort the skill. Refer to
> `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`
> for the full lifecycle contract.

Same 3-reviewer roster as Path B, but dispatched as a coordinated team with a shared task list. Use this when reviewers may surface overlapping findings (e.g., a security hole that's also a correctness bug) and you want them to cross-reference each other via `SendMessage` during review.

##### C.1 Build the team name

Team name: `crev-local-<YYYYMMDD-HHMMSS>`. Use the same timestamp you will use later when writing the review artifact so the team name and the output filename share a traceable identifier.

##### C.2 Create the team

```
TeamCreate: team_name="crev-local-<timestamp>", description="Code review team for uncommitted local changes"
```

On failure, abort.

##### C.3 Register subtasks

Create 3 tasks in the shared task list (flat graph — reviewers are independent):

```
TaskCreate: subject="correctness-reviewer: code-quality review of uncommitted changes", description="<full reviewer prompt>"
TaskCreate: subject="security-reviewer: security review of uncommitted changes",        description="<full reviewer prompt>"
TaskCreate: subject="quality-reviewer: best-practices review of uncommitted changes",   description="<full reviewer prompt>"
```

If any `TaskCreate` fails → `TeamDelete`, then abort.

##### C.4 Spawn the 3 reviewers (single message, three Agent calls)

Dispatch all three teammates in **ONE message** with **THREE `Agent` tool calls**. Every call MUST include:

- `team_name`: `"crev-local-<timestamp>"`
- `name`: the reviewer name (`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) — must match the `TaskCreate` subject prefix
- `subagent_type`: `"code-reviewer"`
- `description`: One-line task title (e.g., `"Code-quality review of local changes"`)
- `prompt`: The same reviewer prompt used in Path B (changed files, focus + checklist items, severity rubric, expected findings format) PLUS a note that the teammate shares a task list with two sibling reviewers (name them) and may `SendMessage` them if it discovers a finding that overlaps their scope, and must call `TaskUpdate` to mark its task complete before returning.

##### C.5 Monitor and collect results

Use `TaskList` to confirm all 3 tasks are `completed` before merging. If a teammate messages the orchestrator, respond via `SendMessage`. Failure policy:

- All 3 error → `TeamDelete`, abort with a clear error.
- 1 or 2 error → record "partial review — {role} did not complete" and proceed with the remaining reviewers' findings. Note the gap in the Phase 3 artifact Summary.

##### C.6 Shutdown and cleanup

After all teammates have marked their tasks complete (or been recorded as failed):

```
SendMessage(to="correctness-reviewer", message={type:"shutdown_request"})
SendMessage(to="security-reviewer",    message={type:"shutdown_request"})
SendMessage(to="quality-reviewer",     message={type:"shutdown_request"})
TeamDelete
```

Always `TeamDelete` — even on abort or partial failure.

##### C.7 Merge findings

Apply the same merge procedure as Path B (combine by severity, de-dupe at `file:line`, sort by file path, attach reviewer source tags). Pass the merged findings to Phase 3 (REPORT).

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
remaining flags — `--parallel` or `--team`, plus anything quick-review
accepts — but drop the flags this skill owns (`--quick`, `--approve`,
`--request-changes`, `--no-worktree`, `--keep-draft`, `--keep-worktree`;
Phase 0 already consumed them).

```
Skill: quick-review
  args: "<stripped flags: --parallel | --team | --yes | --save | --severity <level>>"
```

Print a single one-line notice before delegating so the user sees what
happened:

```
--quick delegated to /quick-review. Run /quick-review directly for full option surface (--yes, --save, --severity).
```

After the Skill call returns, exit. Do NOT run Phase 4/5/6/7/8. Do NOT
write an artifact here — quick-review owns the artifact lifecycle.

---
=======
```bash
git diff --name-only HEAD
```

If no changed files, stop: "Nothing to review."

### Phase 2 — REVIEW

The shape of this phase depends on `PARALLEL_MODE` and `AGENT_TEAM_MODE`:

| Flags             | Path                                        |
| ----------------- | ------------------------------------------- |
| Neither set       | **Path A** — single-pass review (default)   |
| `PARALLEL_MODE`   | **Path B** — 3 parallel sub-agent reviewers |
| `AGENT_TEAM_MODE` | **Path C** — 3-reviewer agent team          |

#### Path A — Single-Pass Review (default, neither flag set)

Read each changed file in full and apply the **Local / Quick Review —
Single-Pass Checklist** (Security CRITICAL, Code Quality HIGH, Best Practices
MEDIUM) and the **Severity Rubric** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

#### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Generate `TIMESTAMP=$(date +%Y%m%d-%H%M%S)` once, here, and reuse the same
variable for the Phase 3 review filename (`local-<TIMESTAMP>-review.md`) — one
canonical timestamp per invocation. Set `run-id = local-<TIMESTAMP>`.

> **Standalone dispatch rule**: Dispatch the 3 reviewers via the blocking
> `Task` tool in ONE message — never the async `Agent` tool, and never with
> `name`, `team_name`, or `run_in_background` set. In the normal case `Task`
> blocks and its return value IS each reviewer's findings, delivered inline in
> the same turn. If a batch doesn't return inline (async fallback), don't
> `sleep`-loop or poll — yield/end the turn so the completion notification can
> flush, then resume. See
> [standalone-dispatch.md](${CURSOR_PLUGIN_ROOT}/skills/_shared/references/standalone-dispatch.md)
> for the full contract.

Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE `Task` tool calls. Use the **Local / Quick Mode Roster**
(`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) and
**Standard Findings Format** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

Reviewers are read-only: supply each prompt's diff and command output; after each
inline return, the calling skill writes its scratch copy at
`docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/<reviewer-name>.md`
(e.g. `.../correctness-reviewer.md`).

After all 3 `Task` calls return: persist each valid inline return to its scratch
path; mark empty, missing, or malformed returns as failed (Merge Procedure in
the reference). Pass the merged findings to
Phase 3 (REPORT) as if they came from a single-pass review. Phase 3 removes
the `docs/prps/reviews/.review-scratch/local-<TIMESTAMP>/` directory once the
review artifact has been written successfully.

#### Path C — Agent Team Review (`AGENT_TEAM_MODE=true`, Claude Code only)

> **MANDATORY — AGENT TEAMS REQUIRED**
>
> In Path C you MUST follow the agent-team lifecycle. Do NOT mix standalone sub-agents
> with team dispatch. Every `Agent` call below MUST include `team_name=` AND `name=`.
>
> 1. `TeamCreate` once at the start
> 2. `TaskCreate` for all 3 reviewer subtasks up front (flat graph — no dependencies)
> 3. Spawn 3 teammates: single message, three `Agent` calls with `team_name=` + `name=`
> 4. `TaskList` to monitor until all reviewers mark complete
> 5. `SendMessage({type:"shutdown_request"})` to all 3 teammates
> 6. `TeamDelete` before merging
>
> If `TeamCreate` or `TaskCreate` fails, abort the skill. Refer to
> `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`
> for the full lifecycle contract.

Same 3-reviewer roster as Path B, but dispatched as a coordinated team with a shared task list. Use this when reviewers may surface overlapping findings (e.g., a security hole that's also a correctness bug) and you want them to cross-reference each other via `SendMessage` during review.

##### C.1 Build the team name

Team name: `crev-local-<YYYYMMDD-HHMMSS>`. Use the same timestamp you will use later when writing the review artifact so the team name and the output filename share a traceable identifier.

##### C.2 Create the team

```
TeamCreate: team_name="crev-local-<timestamp>", description="Code review team for uncommitted local changes"
```

On failure, abort.

##### C.3 Register subtasks

Create 3 tasks in the shared task list (flat graph — reviewers are independent):

```
TaskCreate: subject="correctness-reviewer: code-quality review of uncommitted changes", description="<full reviewer prompt>"
TaskCreate: subject="security-reviewer: security review of uncommitted changes",        description="<full reviewer prompt>"
TaskCreate: subject="quality-reviewer: best-practices review of uncommitted changes",   description="<full reviewer prompt>"
```

If any `TaskCreate` fails → `TeamDelete`, then abort.

##### C.4 Spawn the 3 reviewers (single message, three Agent calls)

Dispatch all three teammates in **ONE message** with **THREE `Agent` tool calls**. Every call MUST include:

- `team_name`: `"crev-local-<timestamp>"`
- `name`: the reviewer name (`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) — must match the `TaskCreate` subject prefix
- `subagent_type`: `"code-reviewer"`
- `description`: One-line task title (e.g., `"Code-quality review of local changes"`)
- `prompt`: The same reviewer prompt used in Path B (changed files, focus + checklist items, severity rubric, expected findings format) PLUS a note that the teammate shares a task list with two sibling reviewers (name them) and may `SendMessage` them if it discovers a finding that overlaps their scope, and must call `TaskUpdate` to mark its task complete before returning.

##### C.5 Monitor and collect results

Use `TaskList` to confirm all 3 tasks are `completed` before merging. If a teammate messages the orchestrator, respond via `SendMessage`. Failure policy:

- All 3 error → `TeamDelete`, abort with a clear error.
- 1 or 2 error → record "partial review — {role} did not complete" and proceed with the remaining reviewers' findings. Note the gap in the Phase 3 artifact Summary.

##### C.6 Shutdown and cleanup

After all teammates have marked their tasks complete (or been recorded as failed):

```
SendMessage(to="correctness-reviewer", message={type:"shutdown_request"})
SendMessage(to="security-reviewer",    message={type:"shutdown_request"})
SendMessage(to="quality-reviewer",     message={type:"shutdown_request"})
TeamDelete
```

Always `TeamDelete` — even on abort or partial failure.

##### C.7 Merge findings

Apply the same merge procedure as Path B (combine by severity, de-dupe at `file:line`, sort by file path, attach reviewer source tags). Pass the merged findings to Phase 3 (REPORT).

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
remaining flags — `--parallel` or `--team`, plus anything quick-review
accepts — but drop the flags this skill owns (`--quick`, `--approve`,
`--request-changes`, `--no-worktree`, `--keep-draft`, `--keep-worktree`;
Phase 0 already consumed them).

```
Skill: quick-review
  args: "<stripped flags: --parallel | --team | --yes | --save | --severity <level>>"
```

Print a single one-line notice before delegating so the user sees what
happened:

```
--quick delegated to /quick-review. Run /quick-review directly for full option surface (--yes, --save, --severity).
```

After the Skill call returns, exit. Do NOT run Phase 4/5/6/7/8. Do NOT
write an artifact here — quick-review owns the artifact lifecycle.

---
>>>>>>> 4bc30c8 (fix(agents): scope db-modifier Bash, drop stray write tools, clarify reviewer duties)

## PR Review Mode

<<<<<<< HEAD
GitHub-only. Before any `gh pr` call, detect provider on `origin` using
`forge_detect_provider origin`; read
`${CURSOR_PLUGIN_ROOT}/skills/_shared/references/forge-detection.md`.
Non-GitHub provider: state limitation, offer local mode; do not call `gh pr`.
Prefer available `mcp__github__*` for fetch/view/review; otherwise use `gh`.
If neither is available, warn and fall back to local-only review without publish.

Read `${CURSOR_PLUGIN_ROOT}/skills/code-review/references/pr-procedure.md`
only after selecting PR mode; it contains setup commands, validation examples,
posting procedure and edge cases. Read canonical schema for REPORT:
`${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-artifact-format.md`.
For release-base checks in CONTEXT, also read
`${CURSOR_PLUGIN_ROOT}/skills/_shared/references/pr-base-and-backport.md#checking-an-existing-pr`.

Phase checklist (execute in order):

- [ ] **SETUP (0½)** — Unless `--no-worktree`, resolve PR head and create/reuse
      parent feature worktree via `setup-worktree.sh`; abort checkout failures.
      All subsequent reads, validation and artifact commands run in that worktree.
- [ ] **FETCH (1)** — Resolve selector, fetch metadata and diff; stop if absent.
- [ ] **CONTEXT (2)** — Rules, PRP artifacts, PR intent, changed files and
      release-base compatibility. Skip release-base check if no release state.
- [ ] **REVIEW (3)** — Full files at PR head (worktree or GitHub API),
      PR checklist; optional fan-out follows REVIEW path above.
- [ ] **VALIDATE (4)** — Run applicable project checks sequentially; record each
      Pass/Fail/Skipped. Review fan-out never parallelizes validation.
- [ ] **DECIDE (5)** — Zero CRITICAL/HIGH and validation pass: APPROVE (comments
      for MEDIUM/LOW); HIGH or failed validation: REQUEST CHANGES; CRITICAL: BLOCK.
      Draft retained with `--keep-draft`: COMMENT. Explicit decision flags override
      recommendation, not findings. Docs/config-only changes get lighter review.
- [ ] **REPORT (6)** — Unless `--keep-draft`, promote draft before reporting.
      Write `docs/prps/reviews/pr-<N>-review.md` under active checkout using shared
      schema. With active worktree, commit only artifact and push before publish.
      Gitignored artifact: skip commit, preserve worktree. Clean scratch only after
      successful artifact write and applicable commit/push.
- [ ] **PUBLISH (7)** — Post review and inline comments per PR procedure.
      BLOCK maps to request-changes. Cleanup only after successful review post,
      only clean worktree, and only without `--keep-worktree`. Keep branch.
- [ ] **OUTPUT (8)** — PR title, decision, counts, validation, artifact path,
      GitHub URL and contextual next steps.

## Safety gates

- PR argument explicitly selects GitHub publishing; local/quick never do.
- Do not remove dirty worktrees or destroy source changes. Failed publish or
  failed commit/push leaves worktree available for recovery.
- PR worktree is snapshot of head at SETUP. New head commits require re-review.
- Large PRs (>50 files): warn; prioritize source, tests, then config/docs.
||||||| parent of 4bc30c8 (fix(agents): scope db-modifier Bash, drop stray write tools, clarify reviewer duties)
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

1. **Project rules** — Read `CLAUDE.md`, `RELEASING.md` (when present), `.claude/docs/`, and any contributing guidelines
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

The shape of this phase depends on `PARALLEL_MODE` and `AGENT_TEAM_MODE`:

| Flags             | Path                                        |
| ----------------- | ------------------------------------------- |
| Neither set       | **Path A** — single-pass review (default)   |
| `PARALLEL_MODE`   | **Path B** — 3 parallel sub-agent reviewers |
| `AGENT_TEAM_MODE` | **Path C** — 3-reviewer agent team          |

#### Path A — Single-Pass Review (default, neither flag set)

Apply the **PR Review — Single-Pass Checklist** (7 categories: Correctness,
Type Safety, Pattern Compliance, Security, Performance, Completeness,
Maintainability) and the **Severity Rubric** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

#### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Set `run-id = pr-<NUMBER>` (PR numbers are unique, so no timestamp is needed).

> **Standalone dispatch rule**: Dispatch the 3 reviewers via the blocking
> `Task` tool in ONE message — never the async `Agent` tool, and never with
> `name`, `team_name`, or `run_in_background` set. In the normal case `Task`
> blocks and its return value IS each reviewer's findings, delivered inline in
> the same turn. If a batch doesn't return inline (async fallback), don't
> `sleep`-loop or poll — yield/end the turn so the completion notification can
> flush, then resume. See
> [standalone-dispatch.md](${CURSOR_PLUGIN_ROOT}/skills/_shared/references/standalone-dispatch.md)
> for the full contract.

Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE `Task` tool calls. Use the **PR Mode Roster**
(`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) and
**Standard Findings Format** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

Each reviewer prompt must additionally include:

1. The PR number, head revision, and the list of changed files
2. Relevant context from Phase 2 (CLAUDE.md rules, PRP artifacts, PR description)
3. Its own scratch backstop path — `docs/prps/reviews/.review-scratch/pr-<NUMBER>/<reviewer-name>.md`
   — per the scratch-backstop contract in that reference

The reviewer-prompt contract (focus + categories, severity rubric, findings
format directive) and the **Merge Procedure** are defined in that reference.
After all 3 `Task` calls return: for any reviewer whose inline return is
empty, missing, or malformed, re-read its scratch file at that path before
merging. Pass the merged findings to Phase 4 (VALIDATE) and downstream phases
as if they came from a single-pass review. Phase 6 removes the
`docs/prps/reviews/.review-scratch/pr-<NUMBER>/` directory once the review
artifact has been written and (when applicable) committed successfully.

**Note**: Validation commands (Phase 4) still run sequentially in the main
skill — parallelization here only applies to the review pass.

#### Path C — Agent Team Review (`AGENT_TEAM_MODE=true`, Claude Code only)

> **MANDATORY — AGENT TEAMS REQUIRED**
>
> In Path C you MUST follow the agent-team lifecycle. Do NOT mix standalone sub-agents
> with team dispatch. Every `Agent` call below MUST include `team_name=` AND `name=`.
>
> 1. `TeamCreate` once at the start
> 2. `TaskCreate` for all 3 reviewer subtasks up front (flat graph — no dependencies)
> 3. Spawn 3 teammates: single message, three `Agent` calls with `team_name=` + `name=`
> 4. `TaskList` to monitor until all reviewers mark complete
> 5. `SendMessage({type:"shutdown_request"})` to all 3 teammates
> 6. `TeamDelete` before merging
>
> If `TeamCreate` or `TaskCreate` fails, abort the skill. Refer to
> `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`
> for the full lifecycle contract.

Same 3-reviewer roster and category split as Path B, but dispatched as a coordinated team with a shared task list. Use this for larger PRs where reviewers will likely surface overlapping findings (e.g., a security hole that's also a correctness bug, or a performance issue that stems from a pattern violation) and you want them to cross-reference via `SendMessage` during review.

##### C.1 Build the team name

Team name: `crev-pr-<NUMBER>`. Use the PR number directly (no sanitization needed since PR numbers are always digits).

##### C.2 Create the team

```
TeamCreate: team_name="crev-pr-<NUMBER>", description="Code review team for PR #<NUMBER>: <PR title>"
```

On failure, abort.

##### C.3 Register subtasks

Create 3 tasks in the shared task list (flat graph — reviewers are independent):

```
TaskCreate: subject="correctness-reviewer: correctness/type-safety/completeness review for PR #<NUMBER>", description="<full reviewer prompt>"
TaskCreate: subject="security-reviewer: security/performance review for PR #<NUMBER>",                    description="<full reviewer prompt>"
TaskCreate: subject="quality-reviewer: pattern-compliance/maintainability review for PR #<NUMBER>",       description="<full reviewer prompt>"
```

If any `TaskCreate` fails → `TeamDelete`, then abort.

##### C.4 Spawn the 3 reviewers (single message, three Agent calls)

Dispatch all three teammates in **ONE message** with **THREE `Agent` tool calls**. Every call MUST include:

- `team_name`: `"crev-pr-<NUMBER>"`
- `name`: the reviewer name (`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) — must match the `TaskCreate` subject prefix
- `subagent_type`: `"code-reviewer"`
- `description`: One-line task title (e.g., `"Correctness review for PR #42"`)
- `prompt`: The same reviewer prompt used in Path B (PR number, head revision, list of changed files, Phase 2 context — CLAUDE.md rules, PRP artifacts, PR description, assigned categories, severity rubric, expected findings format) PLUS a note that the teammate shares a task list with two sibling reviewers (name them) and may `SendMessage` them if it discovers a finding that overlaps their scope, and must call `TaskUpdate` to mark its task complete before returning.

##### C.5 Monitor and collect results

Use `TaskList` to confirm all 3 tasks are `completed` before merging. If a teammate messages the orchestrator, respond via `SendMessage`. Failure policy:

- All 3 error → `TeamDelete`, abort with a clear error.
- 1 or 2 error → record "partial review — {role} did not complete" and proceed with the remaining reviewers' findings. Note the gap in the Phase 6 artifact Summary.

##### C.6 Shutdown and cleanup

After all teammates have marked their tasks complete (or been recorded as failed):

```
SendMessage(to="correctness-reviewer", message={type:"shutdown_request"})
SendMessage(to="security-reviewer",    message={type:"shutdown_request"})
SendMessage(to="quality-reviewer",     message={type:"shutdown_request"})
TeamDelete
```

Always `TeamDelete` — even on abort or partial failure.

##### C.7 Merge findings

Apply the same merge procedure as Path B (combine by severity, de-dupe at `file:line`, sort by file path, attach reviewer source tags). Pass the merged findings to Phase 4 (VALIDATE).

**Note**: Validation commands (Phase 4), decision (Phase 5), report (Phase 6), and publish (Phase 7) all still run sequentially in the main skill — team-based coordination applies only to the review pass.

Assign severity to each finding:

| Severity     | Meaning                                     | Action                  |
| ------------ | ------------------------------------------- | ----------------------- |
| **CRITICAL** | Security vulnerability or data loss risk    | Must fix before merge   |
| **HIGH**     | Bug or logic error likely to cause issues   | Should fix before merge |
| **MEDIUM**   | Code quality issue or missing best practice | Fix recommended         |
| **LOW**      | Style nit or minor suggestion               | Optional                |

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

Write the artifact to `$(git rev-parse --show-toplevel)/docs/prps/reviews/pr-<N>-review.md`. When `WORKTREE_ACTIVE=true` this resolves to the worktree top-level (e.g., `<repo-root>/.cursor/worktrees/<repo>-pr-<N>/docs/prps/reviews/pr-<N>-review.md`); when `--no-worktree` is in effect, it resolves to the main repo. The artifact intentionally lives **with the PR branch** so it travels with the review history.

```bash
mkdir -p "$(git rev-parse --show-toplevel)/docs/prps/reviews"
```

Use the **Review Artifact Format** defined at the bottom of this skill. The artifact must include finding IDs and `Status: Open` on every finding so that `/review-fix` can later update the file in place.

- Write the artifact to `$(git rev-parse --show-toplevel)/docs/prps/reviews/pr-<N>-review.md`. When `WORKTREE_ACTIVE=true` this resolves to the worktree top-level (e.g., `<repo-root>/.cursor/worktrees/<repo>-pr-<N>/docs/prps/reviews/pr-<N>-review.md`); when `--no-worktree` is in effect, it resolves to the main repo. The artifact intentionally lives **with the PR branch** so it travels with the review history.
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

- **Parent**: <repo-root>/.cursor/worktrees/<repo>-pr-<N>/ (branch: <pr-head-branch>)

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

## Agent Team Lifecycle Reference

For Path C's team lifecycle contract (sanitization, shutdown sequence, failure policy),
refer to:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md
```
=======
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

1. **Project rules** — Read `CLAUDE.md`, `RELEASING.md` (when present), `.claude/docs/`, and any contributing guidelines
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

The shape of this phase depends on `PARALLEL_MODE` and `AGENT_TEAM_MODE`:

| Flags             | Path                                        |
| ----------------- | ------------------------------------------- |
| Neither set       | **Path A** — single-pass review (default)   |
| `PARALLEL_MODE`   | **Path B** — 3 parallel sub-agent reviewers |
| `AGENT_TEAM_MODE` | **Path C** — 3-reviewer agent team          |

#### Path A — Single-Pass Review (default, neither flag set)

Apply the **PR Review — Single-Pass Checklist** (7 categories: Correctness,
Type Safety, Pattern Compliance, Security, Performance, Completeness,
Maintainability) and the **Severity Rubric** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

#### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Set `run-id = pr-<NUMBER>` (PR numbers are unique, so no timestamp is needed).

> **Standalone dispatch rule**: Dispatch the 3 reviewers via the blocking
> `Task` tool in ONE message — never the async `Agent` tool, and never with
> `name`, `team_name`, or `run_in_background` set. In the normal case `Task`
> blocks and its return value IS each reviewer's findings, delivered inline in
> the same turn. If a batch doesn't return inline (async fallback), don't
> `sleep`-loop or poll — yield/end the turn so the completion notification can
> flush, then resume. See
> [standalone-dispatch.md](${CURSOR_PLUGIN_ROOT}/skills/_shared/references/standalone-dispatch.md)
> for the full contract.

Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE `Task` tool calls. Use the **PR Mode Roster**
(`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) and
**Standard Findings Format** from:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/review-checklist.md
```

Each reviewer prompt must additionally include:

1. The PR number, head revision, and the list of changed files
2. Relevant context from Phase 2 (CLAUDE.md rules, PRP artifacts, PR description)
3. Caller-provided diff and command output; reviewers return findings read-only.
   The caller persists returns under `docs/prps/reviews/.review-scratch/pr-<NUMBER>/`.

The reviewer-prompt contract (focus + categories, severity rubric, findings
format directive) and the **Merge Procedure** are defined in that reference.
After all 3 `Task` calls return: persist each valid inline return to its scratch
path; mark empty, missing, or malformed returns as failed (Merge Procedure in
the reference). Pass the merged findings to Phase 4 (VALIDATE) and downstream phases
as if they came from a single-pass review. Phase 6 removes the
`docs/prps/reviews/.review-scratch/pr-<NUMBER>/` directory once the review
artifact has been written and (when applicable) committed successfully.

**Note**: Validation commands (Phase 4) still run sequentially in the main
skill — parallelization here only applies to the review pass.

#### Path C — Agent Team Review (`AGENT_TEAM_MODE=true`, Claude Code only)

> **MANDATORY — AGENT TEAMS REQUIRED**
>
> In Path C you MUST follow the agent-team lifecycle. Do NOT mix standalone sub-agents
> with team dispatch. Every `Agent` call below MUST include `team_name=` AND `name=`.
>
> 1. `TeamCreate` once at the start
> 2. `TaskCreate` for all 3 reviewer subtasks up front (flat graph — no dependencies)
> 3. Spawn 3 teammates: single message, three `Agent` calls with `team_name=` + `name=`
> 4. `TaskList` to monitor until all reviewers mark complete
> 5. `SendMessage({type:"shutdown_request"})` to all 3 teammates
> 6. `TeamDelete` before merging
>
> If `TeamCreate` or `TaskCreate` fails, abort the skill. Refer to
> `${CURSOR_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md`
> for the full lifecycle contract.

Same 3-reviewer roster and category split as Path B, but dispatched as a coordinated team with a shared task list. Use this for larger PRs where reviewers will likely surface overlapping findings (e.g., a security hole that's also a correctness bug, or a performance issue that stems from a pattern violation) and you want them to cross-reference via `SendMessage` during review.

##### C.1 Build the team name

Team name: `crev-pr-<NUMBER>`. Use the PR number directly (no sanitization needed since PR numbers are always digits).

##### C.2 Create the team

```
TeamCreate: team_name="crev-pr-<NUMBER>", description="Code review team for PR #<NUMBER>: <PR title>"
```

On failure, abort.

##### C.3 Register subtasks

Create 3 tasks in the shared task list (flat graph — reviewers are independent):

```
TaskCreate: subject="correctness-reviewer: correctness/type-safety/completeness review for PR #<NUMBER>", description="<full reviewer prompt>"
TaskCreate: subject="security-reviewer: security/performance review for PR #<NUMBER>",                    description="<full reviewer prompt>"
TaskCreate: subject="quality-reviewer: pattern-compliance/maintainability review for PR #<NUMBER>",       description="<full reviewer prompt>"
```

If any `TaskCreate` fails → `TeamDelete`, then abort.

##### C.4 Spawn the 3 reviewers (single message, three Agent calls)

Dispatch all three teammates in **ONE message** with **THREE `Agent` tool calls**. Every call MUST include:

- `team_name`: `"crev-pr-<NUMBER>"`
- `name`: the reviewer name (`correctness-reviewer`, `security-reviewer`, `quality-reviewer`) — must match the `TaskCreate` subject prefix
- `subagent_type`: `"code-reviewer"`
- `description`: One-line task title (e.g., `"Correctness review for PR #42"`)
- `prompt`: The same reviewer prompt used in Path B (PR number, head revision, list of changed files, Phase 2 context — CLAUDE.md rules, PRP artifacts, PR description, assigned categories, severity rubric, expected findings format) PLUS a note that the teammate shares a task list with two sibling reviewers (name them) and may `SendMessage` them if it discovers a finding that overlaps their scope, and must call `TaskUpdate` to mark its task complete before returning.

##### C.5 Monitor and collect results

Use `TaskList` to confirm all 3 tasks are `completed` before merging. If a teammate messages the orchestrator, respond via `SendMessage`. Failure policy:

- All 3 error → `TeamDelete`, abort with a clear error.
- 1 or 2 error → record "partial review — {role} did not complete" and proceed with the remaining reviewers' findings. Note the gap in the Phase 6 artifact Summary.

##### C.6 Shutdown and cleanup

After all teammates have marked their tasks complete (or been recorded as failed):

```
SendMessage(to="correctness-reviewer", message={type:"shutdown_request"})
SendMessage(to="security-reviewer",    message={type:"shutdown_request"})
SendMessage(to="quality-reviewer",     message={type:"shutdown_request"})
TeamDelete
```

Always `TeamDelete` — even on abort or partial failure.

##### C.7 Merge findings

Apply the same merge procedure as Path B (combine by severity, de-dupe at `file:line`, sort by file path, attach reviewer source tags). Pass the merged findings to Phase 4 (VALIDATE).

**Note**: Validation commands (Phase 4), decision (Phase 5), report (Phase 6), and publish (Phase 7) all still run sequentially in the main skill — team-based coordination applies only to the review pass.

Assign severity to each finding:

| Severity     | Meaning                                     | Action                  |
| ------------ | ------------------------------------------- | ----------------------- |
| **CRITICAL** | Security vulnerability or data loss risk    | Must fix before merge   |
| **HIGH**     | Bug or logic error likely to cause issues   | Should fix before merge |
| **MEDIUM**   | Code quality issue or missing best practice | Fix recommended         |
| **LOW**      | Style nit or minor suggestion               | Optional                |

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

Write the artifact to `$(git rev-parse --show-toplevel)/docs/prps/reviews/pr-<N>-review.md`. When `WORKTREE_ACTIVE=true` this resolves to the worktree top-level (e.g., `<repo-root>/.cursor/worktrees/<repo>-pr-<N>/docs/prps/reviews/pr-<N>-review.md`); when `--no-worktree` is in effect, it resolves to the main repo. The artifact intentionally lives **with the PR branch** so it travels with the review history.

```bash
mkdir -p "$(git rev-parse --show-toplevel)/docs/prps/reviews"
```

Use the **Review Artifact Format** defined at the bottom of this skill. The artifact must include finding IDs and `Status: Open` on every finding so that `/review-fix` can later update the file in place.

- Write the artifact to `$(git rev-parse --show-toplevel)/docs/prps/reviews/pr-<N>-review.md`. When `WORKTREE_ACTIVE=true` this resolves to the worktree top-level (e.g., `<repo-root>/.cursor/worktrees/<repo>-pr-<N>/docs/prps/reviews/pr-<N>-review.md`); when `--no-worktree` is in effect, it resolves to the main repo. The artifact intentionally lives **with the PR branch** so it travels with the review history.
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

- **Parent**: <repo-root>/.cursor/worktrees/<repo>-pr-<N>/ (branch: <pr-head-branch>)

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

## Agent Team Lifecycle Reference

For Path C's team lifecycle contract (sanitization, shutdown sequence, failure policy),
refer to:

```
${CURSOR_PLUGIN_ROOT}/skills/_shared/references/agent-team-dispatch.md
```
>>>>>>> 4bc30c8 (fix(agents): scope db-modifier Bash, drop stray write tools, clarify reviewer duties)
