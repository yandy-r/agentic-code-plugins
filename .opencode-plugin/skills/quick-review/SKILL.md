---
name: quick-review
description: Reviews uncommitted changes inline without saving by default. Use when
  requesting a quick review, checking a small local diff, or reviewing without a saved
  artifact.
---

# Quick Review

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.

Interactive low-friction review of uncommitted changes. Output is **inline**. The default fix path is artifact-free.

**Operational context:** "Apply fixes" delegates inline findings to /quick-fix without an artifact; "Save to file" saves under docs/prps/reviews/; "Write file and apply fixes" saves an artifact and delegates to /review-fix. Writes require confirmation unless a documented scripted action selects them.

**Input**: `$ARGUMENTS`

**Core rule**: "Apply fixes" must not write a review artifact. It hands the
inline findings directly to `/quick-fix`. Only "Save to file" and
"Write file and apply fixes" write `docs/prps/reviews/quick-*.md`.

---

## Phase 0 — Parse flags

Extract flags from `$ARGUMENTS`:

| Flag                 | Effect                                                                                                                                                                                                    |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--parallel`         | Fan out REVIEW across 3 standalone `code-reviewer` sub-agents (correctness, security, quality) and merge findings. Works in opencode, Cursor, and Codex bundles.                                   |
| `--yes`              | Skip the confirmation prompt and behave as "Apply fixes" through `/quick-fix`. Mutually exclusive with `--save` and `--write-and-apply`.                                                              |
| `--save`             | Skip the confirmation prompt and behave as "Save to file" (write artifact, print Next steps, exit). Mutually exclusive with `--yes` and `--write-and-apply`.                                              |
| `--write-and-apply`  | Skip the confirmation prompt, write the review artifact, then hand off to `/review-fix`. Mutually exclusive with `--yes` and `--save`.                                                                |
| `--severity <level>` | Forwarded to `/quick-fix` or `/review-fix` during hand-off. Valid: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`. Default: `HIGH`. Ignored on "Save to file" / "Discard".                                   |
| `--no-worktree`      | Accepted as a **no-op**. Quick mode never creates a worktree. Emit a note: `--no-worktree has no effect in quick mode.`                                                                                   |

Strip these from `$ARGUMENTS` and set `PARALLEL_MODE`, ``,
`AUTO_YES`, `AUTO_SAVE`, `AUTO_WRITE_AND_APPLY`, and `MIN_SEVERITY` (default
`HIGH`). The remaining text MUST be empty; if not, abort with:

```
Error: /quick-review takes no positional argument (only flags).
```

**Validation**:

- More than one of `--yes`, `--save`, `--write-and-apply` present -> abort with: `--yes, --save, and --write-and-apply are mutually exclusive. Pick one.`
- `--severity` value not one of `CRITICAL|HIGH|MEDIUM|LOW` -> abort with: `Invalid --severity value. Use CRITICAL, HIGH, MEDIUM, or LOW.`

---

## Phase 1 — GATHER

```bash
git diff --name-only HEAD
```

If the output is empty, print `Nothing to review.` and exit. Do NOT prompt,
do NOT write anything.

Capture the list of changed files as `CHANGED_FILES` for the REVIEW phase.

---

## Phase 2 — REVIEW

Neither flag: **Path A** single-pass (default). `PARALLEL_MODE`: **Path B**,

Findings from all paths stay **in memory**. Do not write to disk here.

### Path A — Single-Pass Review (default)

Read each changed file in full and apply the **Local / Quick Review —
Single-Pass Checklist** and **Severity Rubric**. Flag only gaps that affect
correctness or the stated requirements. From:

```
~/.config/opencode/shared/references/review-checklist.md
```

<<<<<<< HEAD
||||||| parent of 4bc30c8 (fix(agents): scope db-modifier Bash, drop stray write tools, clarify reviewer duties)
### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Generate `TIMESTAMP=$(date +%Y%m%d-%H%M%S)` once, here, and reuse the same
variable for the scratch run-id below and, if the user later selects an
artifact-writing path in Phase 5, for the `quick-<TIMESTAMP>-review.md`
filename — one canonical timestamp per invocation (the same pattern Path C
uses for its team name when that path runs instead). Set
`run-id = quick-<TIMESTAMP>`.

> **OpenCode V2 standalone dispatch:** Issue the independent calls in one
> parallel tool batch and set `background=false` on every call. Each call waits
> for a candidate report. Require nonempty report text, validate the declared
> artifact or diff independently, and do not treat a terminal lifecycle state
> as proof of the deliverable. Apply the contentless-completion and bounded
> retry policy from
> [standalone-dispatch.md](~/.config/opencode/shared/references/standalone-dispatch.md).


Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE native `subagent` calls. Use the **Local / Quick Mode Roster**
and **Standard Findings Format** from:

```
~/.config/opencode/shared/references/review-checklist.md
```

Each reviewer prompt must include:

1. The list of changed files (`git diff --name-only HEAD`)
2. Its assigned focus and checklist items (from the roster table)
3. The severity rubric
4. A directive to return findings in the Standard Findings Format
5. Its own scratch backstop path — `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/<reviewer-name>.md`
   — per the scratch-backstop contract in that reference

After all 3 native `subagent` calls return: for any reviewer whose inline return is
empty, missing, or malformed, re-read its scratch file at that path before
merging. Apply the **Merge Procedure** defined in the reference to produce a
single combined findings list for Phase 3.

**Scratch cleanup is unconditional**: unlike the permanent review artifact
(only written on "Save to file" / "Write file and apply fixes"), the scratch
directory `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/` is always
removed at the end of Phase 5 (HAND-OFF) — even on "Discard" or "Apply
fixes", which never write a permanent artifact. This is the one ephemeral
exception to quick-review's artifact-free guarantee: the scratch file exists
only transiently during this Path B dispatch and is gone before the skill
returns control to the user.

=======
### Path B — Parallel Sub-Agent Review (`PARALLEL_MODE=true`)

Generate `TIMESTAMP=$(date +%Y%m%d-%H%M%S)` once, here, and reuse the same
variable for the scratch run-id below and, if the user later selects an
artifact-writing path in Phase 5, for the `quick-<TIMESTAMP>-review.md`
filename — one canonical timestamp per invocation (the same pattern Path C
uses for its team name when that path runs instead). Set
`run-id = quick-<TIMESTAMP>`.

> **OpenCode V2 standalone dispatch:** Issue the independent calls in one
> parallel tool batch and set `background=false` on every call. Each call waits
> for a candidate report. Require nonempty report text, validate the declared
> artifact or diff independently, and do not treat a terminal lifecycle state
> as proof of the deliverable. Apply the contentless-completion and bounded
> retry policy from
> [standalone-dispatch.md](~/.config/opencode/shared/references/standalone-dispatch.md).


Dispatch **3 standalone `code-reviewer` sub-agents in parallel** in a SINGLE
message with MULTIPLE native `subagent` calls. Use the **Local / Quick Mode Roster**
and **Standard Findings Format** from:

```
~/.config/opencode/shared/references/review-checklist.md
```

Each reviewer prompt must include:

1. The list of changed files (`git diff --name-only HEAD`)
2. Its assigned focus and checklist items (from the roster table)
3. The severity rubric
4. A directive to return findings in the Standard Findings Format
5. Diff and command output; reviewers are read-only. The calling skill writes
   each valid inline return to its scratch backstop path — `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/<reviewer-name>.md`
   — per the scratch-backstop contract in that reference

After all 3 native `subagent` calls return: persist each valid inline return to its scratch
path; mark empty, missing, or malformed returns as failed before merging. Apply the **Merge Procedure** defined in the reference to produce a
single combined findings list for Phase 3.

**Scratch cleanup is unconditional**: unlike the permanent review artifact
(only written on "Save to file" / "Write file and apply fixes"), the scratch
directory `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/` is always
removed at the end of Phase 5 (HAND-OFF) — even on "Discard" or "Apply
fixes", which never write a permanent artifact. This is the one ephemeral
exception to quick-review's artifact-free guarantee: the scratch file exists
only transiently during this Path B dispatch and is gone before the skill
returns control to the user.

>>>>>>> 4bc30c8 (fix(agents): scope db-modifier Bash, drop stray write tools, clarify reviewer duties)
## Phase 3 — REPORT (inline)

Assign IDs and initial Status after merge using the shared artifact schema
loaded below (Finding ID rules: ordered by severity, CRITICAL first, then by
file path); the same contract applies to inline findings.

Compute:

- `critical_count`, `high_count`, `medium_count`, `low_count`
- `total_findings`
- `finding_file_count` (unique files with findings)
- `large_review = total_findings >= 5 || finding_file_count >= 3`

**Print** the review to stdout in the quick-mode variant of the Review Artifact
Format, **without** writing a file. Read the schema:

`~/.config/opencode/shared/references/review-artifact-format.md`

Header: `# Quick Review — Uncommitted Changes`, `**Mode**: Quick (inline)`,
`**Author**: local`, `**Branch**: <current-branch>`,
`**Decision**: (pending user confirmation)`, then Summary, Findings (all four
fields per finding, `Status: Open`) and Files Reviewed. No Worktree Setup or
Validation Results sections. Categories: Security | Correctness | Code Quality
| Best Practices.

After the artifact block, print:

```
Findings: [C] {critical_count}  [H] {high_count}  [M] {medium_count}  [L] {low_count}
```

If `large_review=true`, also print:

```
Large quick review: {total_findings} findings across {finding_file_count} files.
You can still apply fixes directly, or write an artifact before applying fixes for an audit trail.
```

If the count is zero across all severities, skip Phase 4 entirely. Print
`No findings. Nothing to do.` and exit.

Keep the exact printed review block in memory as `INLINE_REVIEW_PAYLOAD` for
`/quick-fix` or artifact writing.

---

## Phase 4 — DECIDE (confirmation)

If `AUTO_YES=true` -> skip this phase, proceed directly to Phase 5 as if the
user selected "Apply fixes".

If `AUTO_SAVE=true` -> skip this phase, proceed directly to Phase 5 as if the
user selected "Save to file".

If `AUTO_WRITE_AND_APPLY=true` -> skip this phase, proceed directly to Phase 5
as if the user selected "Write file and apply fixes".

Otherwise, ask the user with `ask the user`.

For normal reviews (`large_review=false`):

```
question: "What should I do with this review?"
header:   "Review action"
options:
  - label: "Apply fixes"
    description: "Hand findings directly to /quick-fix. No review file is written. (recommended)"
  - label: "Save to file"
    description: "Write docs/prps/reviews/quick-<timestamp>-review.md and stop."
  - label: "Discard"
    description: "Write nothing, exit"
```

For large reviews (`large_review=true`):

```
question: "This is a larger quick review. What should I do?"
header:   "Review action"
options:
  - label: "Apply fixes"
    description: "Hand findings directly to /quick-fix. No review file is written."
  - label: "Write file and apply fixes"
    description: "Write docs/prps/reviews/quick-<timestamp>-review.md, then use /review-fix for an audit trail. (recommended)"
  - label: "Save to file"
    description: "Write docs/prps/reviews/quick-<timestamp>-review.md and stop."
  - label: "Discard"
    description: "Write nothing, exit"
```

Mark "Apply fixes" with `(Recommended)` when `large_review=false` and
`critical_count + high_count > 0`. Mark "Write file and apply fixes" with
`(Recommended)` when `large_review=true`.

**Text-mode fallback** (if `ask the user` is unavailable — Cursor/Codex
bundles without that tool): print the available choices explicitly and WAIT for
the user's next message. Parse their reply case-insensitively:

- `yes` / `apply` / `apply fixes` / `fix` -> "Apply fixes"
- `write and apply` / `write file and apply fixes` / `file and fix` / `artifact and fix` -> "Write file and apply fixes"
- `save` / `save to file` / `write` / `file` -> "Save to file"
- `no` / `discard` / `cancel` / `skip` -> "Discard"
- Anything else -> re-prompt once, then default to `Discard` if still ambiguous.

---

## Phase 5 — HAND-OFF

Branch on the user's selection (or auto-confirm flag). If `PARALLEL_MODE=true`
(Path B was used), remove the `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/`
scratch directory before exiting — **regardless of which branch below is
taken**, including "Discard" and "Apply fixes".

### Selection: "Discard"

Print `Discarded. No artifact written.` and exit. Do NOT write any file.

### Selection: "Apply fixes"

Invoke the `quick-fix` skill inline via the `Skill` tool. Do NOT write an
artifact first.

- `skill`: `"quick-fix"`
- `args`: `"[--parallel] [--severity <level>] <INLINE_REVIEW_PAYLOAD>"`

Forward `--parallel` if `PARALLEL_MODE=true`. Forward `--severity <level>` when
`MIN_SEVERITY != HIGH` (HIGH is the default on quick-fix).

After the Skill call returns, print:

```
Fixes complete. No review artifact was written.
```

Exit.

### Selection: "Save to file"

Write the artifact to disk using the Phase 3 content plus the canonical header
block:

```bash
mkdir -p docs/prps/reviews
TIMESTAMP=$(date +%Y%m%d-%H%M%S)    # reuse the Path C timestamp if set
REVIEW_FILE="docs/prps/reviews/quick-${TIMESTAMP}-review.md"
```

Write the same artifact content that was printed in Phase 3, but set
`**Decision**: COMMENT` in the header (since a review was produced but no
GitHub decision is being posted).

Print:

```
Quick review written to: docs/prps/reviews/quick-<TIMESTAMP>-review.md
Findings: [C] {critical_count}  [H] {high_count}  [M] {medium_count}  [L] {low_count}

Next steps:
  /review-fix docs/prps/reviews/quick-<TIMESTAMP>-review.md              # apply fixes {recommended_single if 1-2 Open findings}
  /review-fix docs/prps/reviews/quick-<TIMESTAMP>-review.md --parallel   # fan out fixes {recommended_parallel if 3+ Open across 2+ files}
```

Annotate ONE command with `# <- recommended`:

- 1-2 Open findings -> recommend the single-pass form.
- 3+ Open findings spanning 2+ files -> recommend the `--parallel` form.
- Otherwise default to the single-pass form.

Exit.

### Selection: "Write file and apply fixes"

Step 1 — write the artifact to disk exactly as in "Save to file".

Step 2 — invoke the `review-fix` skill inline via the `Skill` tool:

- `skill`: `"review-fix"`
- `args`: `"<REVIEW_FILE> [--parallel] [--severity <level>]"`

Forward `--parallel` if `PARALLEL_MODE=true`. Forward `--severity <level>` when
`MIN_SEVERITY != HIGH`.

Step 3 — after the Skill call returns, print:

```
Fixes complete. Review artifact updated in place: docs/prps/reviews/quick-<TIMESTAMP>-review.md
```

Step 4 — exit.

automatically. The review-phase fan-out is about finding issues quickly; the
fix phase has its own execution decision.

---

## Important Notes

- **Apply fixes is artifact-free**: direct apply routes to `/quick-fix`
  without writing `docs/prps/reviews/quick-*.md`.
- **Scratch is the one ephemeral exception**: when Path B (`--parallel`) is
  used, a transient scratch backstop file exists per reviewer at
  `docs/prps/reviews/.review-scratch/quick-<TIMESTAMP>/<reviewer-name>.md`
  during the `subagent` dispatch in Phase 2. It is always deleted at the end of
  Phase 5 before the skill returns control to the user — including on
  "Discard" and "Apply fixes" — so the "no file written" guarantee still
  holds for anything the user can observe afterward.
- **Large reviews are advisory**: `5+` findings or `3+` finding files adds a
  "Write file and apply fixes" choice. It does not force artifact creation.
- **Explicit artifact-backed apply**: only `--write-and-apply` or the matching
  prompt choice writes the artifact and invokes `/review-fix`.
- **Idempotent filename**: the `quick-{YYYYMMDD-HHMMSS}-review.md` pattern
  produces a new file per artifact-writing invocation — no overwrites.
- **Not a replacement for `/code-review`**: if you need toolchain
  validation (typecheck/lint/test/build), a `## Validation Results` block,
  worktree isolation, or a GitHub review posted, use `/code-review`
  without `--quick`.

---

## Integration with ycc

- `/code-review --quick` delegates to this skill.
- `/quick-fix` consumes inline findings for artifact-free fixing.
- `/review-fix` consumes written artifacts only.
- `/prp-commit` or `/git-workflow --commit` can commit the fixes afterward.
