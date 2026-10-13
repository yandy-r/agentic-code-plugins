---
name: plan
description: Creates lightweight conversational implementation plans and waits for
  approval. Use when outlining an approach, breaking down a change before coding,
  or comparing implementation options.
---

# Plan Skill

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.

Create a comprehensive implementation plan before writing any code. This is the lightweight conversational planner. For heavier planning tracks, see the comparison table at the bottom.

**Core rule**: You will **NOT** write any code until the user explicitly confirms the plan with "yes", "proceed", "approved", or similar affirmative.

---

## What This Skill Does

1. Parse `--parallel`, `--enhanced`, `--dry-run`, `--no-worktree`, `--worktree`,
   and `--visual`, then read the request and referenced files.
2. Dispatch one planner by default, three standalone planning perspectives when
   the user explicitly asks for a multi-perspective plan, or five perspectives
   when `--enhanced` is present.
3. Validate and merge every returned perspective into one plan.
4. Wait for explicit user confirmation before any implementation.

## Flags

| Flag | Effect |
| --- | --- |
| `--parallel` | Shape the plan for dependency-batched parallel implementation. |
| `--enhanced` | Use five standalone perspectives: architecture, risk, testing, security, and UX. |
| `--dry-run` | Print the selected multi-perspective roster and stop without dispatching. |
| `--worktree` | Legacy no-op; shared worktree annotations are enabled by default. |
| `--no-worktree` | Omit shared worktree annotations. |
| `--visual` | Force-write the confirmed plan and render it with `visual-plan`. |

`--parallel` changes the output shape, independently of whether one, three, or
five planning perspectives are dispatched. `--enhanced` selects five
perspectives. An explicit natural-language request for a multi-perspective plan
selects three perspectives when `--enhanced` is absent.

## When to Use

Use this skill when:

- Starting a new feature
- Making significant architectural changes
- Working on complex refactoring
- Multiple files/components will be affected
- Requirements are unclear or ambiguous

---

## Process

### Step 1 — Parse flags and the user's request

Strip the supported flags from `$ARGUMENTS`. Set `PARALLEL_MODE`,
`ENHANCED_MODE`, `DRY_RUN`, `VISUAL_MODE`, and `WORKTREE_MODE` explicitly.
Default `WORKTREE_MODE=true`; `--no-worktree` sets it false and `--worktree` is
a legacy no-op. Set `PERSPECTIVE_COUNT=5` when `ENHANCED_MODE=true`, otherwise
set it to `3` only when the remaining request explicitly asks for a
multi-perspective plan; default it to `1`.

Read the stripped request and any referenced files. Ask one focused question
before dispatch if the request is ambiguous. `--dry-run` with
`PERSPECTIVE_COUNT=1` aborts because the single-agent path has no roster to
preview.

### Step 2 — Dispatch

- `PERSPECTIVE_COUNT=1`: one foreground `planner` call.
- `PERSPECTIVE_COUNT=3`: `architect` (`planner`), `risk-analyst`
  (`codebase-research-analyst`), and `test-strategist`
  (`test-strategy-planner`) in one parallel foreground batch.
- `PERSPECTIVE_COUNT=5`: the same three plus `security-reviewer` and
  `ux-reviewer` (both `research-specialist`) in one parallel foreground batch.

Every call uses the native shape below, with a complete role-specific prompt and
no `sessionID` for a new child:

```text
subagent(agent="<configured-agent>", description="<perspective>",
         prompt="<complete planning prompt>", background=false)
```

Do not set `model`; each configured agent supplies or inherits its model. Include
the original request, referenced context, role focus, confirmation instruction,
and the parallel/worktree directives selected by the flags.

When `DRY_RUN=true`, print the selected three- or five-persona roster and stop
without calling `subagent`.

For a single planner, relay the validated report. For three or five perspectives,
merge architecture, risks, testing, and optional security/UX slices without
dropping a role. A terminal lifecycle state alone is insufficient: require each
candidate report and validate any declared artifact. For contentless completion,
record `sessionID`, inspect edits/artifacts, preserve work, retry at most once,
then report the missing perspective. Follow
`~/.config/opencode/shared/references/standalone-dispatch.md`.

### Step 2.5 — Validate the plan before relaying

After the `planner` agent returns its plan, perform these quick checks BEFORE presenting it to the user. Use only the tools already available to this skill.

#### Check 1: Structure completeness

Scan the agent's response for these sections. If any **required** section is missing, re-dispatch the planner with a note to include the missing section(s).

**Required** (re-dispatch if missing):

- `## Overview` or `## Summary`
- `## Implementation Steps` or `## Step-by-Step Tasks`
- `## Testing Strategy`
- `**WAITING FOR CONFIRMATION**`

**Expected** (append a note to the plan if missing, but do NOT re-dispatch):

- `## Architecture Changes` or `## Requirements`
- `## Risks` or `## Risks & Mitigations`
- `## Success Criteria`

#### Check 2: File path spot-check

Extract up to 10 file paths from the plan (backtick-quoted paths or paths after `File:` annotations). For each, use Glob or `Bash: test -f "<path>"` to check existence.

- If **all paths exist**: clean pass, append nothing.
- If **>30% of checked paths are missing**: append a validation note before relaying:

  > **Validation Note**: {N} of {M} file paths in this plan could not be found in the current codebase. This may indicate renamed files, planned new files, or stale references. Review the paths in the Implementation Steps before confirming.

- If **a few paths are missing** (≤30%): append a lighter note listing only the missing paths.

#### Check 3: Parallel mode integrity (`PARALLEL_MODE=true` only)

If the plan was requested with `--parallel`, verify:

- A `## Batches` section exists in the response
- At least one `Depends on` annotation exists
- Step IDs use hierarchical format (N.N)


#### Check 4: Multi-agent merge integrity (Path B and Path C)

Whenever three or five sub-agents contributed to the plan, verify the unified plan reflects every spawned perspective:

- `architect` slice: `## Implementation Steps` (or equivalent) is present and non-empty
- `risk-analyst` slice: a `## Risks` / `## Risks & Mitigations` section OR per-step risk callouts are present
- `test-strategist` slice: `## Testing Strategy` is present and non-empty
- When `ENHANCED_MODE=true`, also verify:
  - `security-reviewer` slice: `## Security Considerations` is present **OR** the merged plan documents that no significant security risks were found (e.g., a one-line note in `## Risks` such as "Security-reviewer: no significant risks identified"). Per-step `> **Security**:` callouts also satisfy this check.
  - `ux-reviewer` slice: `## UX Impact` is present **OR** the merged plan documents "Internal change — no user-facing UX impact". Both forms count as covered.

If the merge dropped a slice (e.g., because a sub-agent errored), append a visible note:

> **Validation Note**: The {role} perspective could not be included in this plan (sub-agent error). Review the plan for gaps in {area} before confirming.

---

### Step 3 — Relay the plan

Present the agent's plan to the user verbatim, including any validation notes appended in Step 2.5. Do not summarize, do not shorten, do not add your own commentary above it.

### Step 4 — WAIT

Do not touch any code until the user responds.

Valid user responses:

- **"yes" / "proceed" / "approved"** → proceed to implement
- **"different approach: ..."** → discard and re-dispatch the selected native planning mode with the new direction
- **"skip phase N and do phase M first"** → re-dispatch with the reorder request
- **"no"** → stop, do not implement



---

### Step 5 — Visual rendering (if `VISUAL_MODE=true`)

This step runs **only after** the user confirms the plan in Step 4 (it is the terminal decorator step). It never re-orders or substitutes for any earlier phase.

- **If `DRY_RUN=true`**: print `visual generation would run` and skip — do not force any write and do not invoke `visual-plan`. (`--dry-run` already exits earlier at the dispatch gate; this is the no-op contract for the combination.)
- **Otherwise**:
  1. **Force-write the plan to a file.** `/plan` keeps the plan in-chat and writes no artifact by default, so there is nothing on disk to visualize. Write the confirmed plan verbatim to a concrete path. Default location: `docs/prps/plans/<slug>.plan.md`, where `<slug>` is the user's request sanitized to kebab-case (same scheme as Path B §B.1: lowercase, non-`[a-z0-9-]` → `-`, collapse runs, trim, truncate to 20 chars, fallback `untitled`). Create the directory first (`mkdir -p docs/prps/plans`). Resolve the path to an **absolute** path.
  2. **Invoke** `visual-plan <absolute-plan-path>` with the absolute path written in the previous step.
  3. **Surface the link** that `visual-plan` prints (hosted URL, localhost preview, or `local files only`). Do not re-derive the output directory yourself.

See the canonical contract for the full force-write-first rule and `--dry-run` short-circuit:

```
~/.config/opencode/shared/references/visual-mode.md
```

---

## Visual mode

`--visual` is the single, shared visual decorator described in
`~/.config/opencode/shared/references/visual-mode.md`. It is a
**terminal decorator step** — it does not change how the plan is researched,
dispatched, or relayed. It runs once, last, on the confirmed plan.

**FORCE-WRITE-FIRST (mandatory for `/plan`)**: unlike the other planning
skills, `/plan` writes **no** plan artifact by default — the plan stays
in-chat. There is therefore nothing on disk to visualize. When `VISUAL_MODE` is
set (and **not** `--dry-run`), the skill MUST:

1. **Write the otherwise-inline plan to a concrete file path first.** Default:
   `docs/prps/plans/<slug>.plan.md` (absolute path; directory created if
   missing). This forced write happens even though it would normally be skipped.
2. **Then invoke** `visual-plan <absolute-plan-path>` with that absolute
   path.

Without the forced write there is no input for `visual-plan`, so the
force-write is required, not optional. Under `--dry-run` this is moot: the
skill prints `visual generation would run` and forces no write (see §2.1 and §4
of the canonical reference). `visual-plan` derives its `visual/` output
directory relative to the plan path it is handed and never edits the plan file.

---

## Important Notes

**CRITICAL**: This skill will NOT write any code until the user explicitly confirms.

Do not summarize, do not touch files, do not run commands beyond read-only analysis. Wait.

If the user's instructions are unclear after the planner produces a draft, ask a focused clarifying question rather than guessing, then re-dispatch the planner with the clarification.

The `planner` agent owns the plan format, worked examples, sizing/phasing guidance, and red-flag checks. This skill is an orchestration layer — it decides _when_ to plan and _what_ to do with the plan, not _how_ a plan should be structured.



---

## Integration with ycc

After planning, depending on what the user approves:

- Use `/prp-implement` if they want rigorous per-task validation loops (requires a PRP-format plan file — consider running `/prp-plan` first if you want that workflow)
- Use `/implement-plan` if the work was structured via `/parallel-plan`
- Use `/code-review` to review completed implementation
- Use `/git-workflow --commit` or `/prp-commit` to commit

### Executing a Parallel Plan

If the plan was produced with `--parallel` (has a `Batches` section and `Depends on` annotations), after the user confirms you have two options for parallel execution:

**Option 1 — In-conversation parallel execution (lightweight)**

Before dispatching any `implementor` agents, prepare the feature branch so agents do not commit on `main`:

- **`WORKTREE_MODE=true` (default)** — the plan already names the parent worktree at `<repo-root>/.config/opencode/worktrees/<repo>-<feature>/` (branch `feat/<feature>`). Run `setup-worktree.sh parent <repo> <feature>` once, then dispatch agents with `Working directory: <parent path>`.
- **`WORKTREE_MODE=false` (`--no-worktree`)** — derive `FEATURE_SLUG` from the user's request using the same sanitization as Path B §B.1 (lowercase, non-`[a-z0-9-]` → `-`, collapse runs, truncate to 20 chars, fallback `untitled`), then run:

  ```bash
  FEATURE_BRANCH=$(bash ~/.config/opencode/shared/scripts/prepare-feature-branch.sh "${FEATURE_SLUG}")
  ```

  The script is idempotent on `feat/${FEATURE_SLUG}`, creates it from a trunk branch, exits 1 on unrelated dirty tree, and exits 2 on a different feature branch (re-run with `--allow-existing-feature-branch` after user confirmation) or, when `RELEASING.md` exists, on `release/*` (re-run with `--allow-release-branch` only for a release-only fix). See `~/.config/opencode/shared/references/branch-prep.md`. **Do not skip this step** — it is what prevents implementor agents from committing to `main`.

Then process batches sequentially. Within each batch, dispatch one `implementor` agent per step in a SINGLE message with MULTIPLE native `subagent` calls (standalone dispatch — see `~/.config/opencode/shared/references/standalone-dispatch.md`). Between batches, run the project's type-check and unit-test commands. On failure, stop and ask the user how to proceed.

This keeps everything in the current conversation — no file artifact needed.

For unattended loop-to-completion of a parallel plan, hand off to `/implement-plan` and pair it with the `/goal` session directive — see that skill's `## /goal pairing` section for the recommended done condition (`ALL_BATCHES_DONE`, `FILES_CHANGED_NONEMPTY`, `LINT_PASS`) and the transcript-output contract.

**Option 2 — Save to file and hand off (rigorous)**

Write the plan to `docs/prps/plans/{name}.plan.md` (adapting it to the PRP plan template if needed: add `Patterns to Mirror`, `Files to Change`, `Validation Commands`, etc.), then run `/prp-implement --parallel docs/prps/plans/{name}.plan.md` for the full 5-level validation pipeline.

Use Option 1 for small features and quick iterations. Use Option 2 when the user wants an implementation report, per-task validation logs, and the plan archived for audit.

---

## Comparison with other ycc planning tracks

| Track                  | When to use                                                                                                                                                                                                                                                               |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/plan` (this one) | Quick conversational plan via `planner` agent. No artifact file. Add `--parallel` to shape the output for parallel execution (no research fan-out). Add `--enhanced` to widen to 5 personas (security + UX), dispatched as standalone parallel sub-agents by default. |
| `/prp-plan`        | Artifact-producing plan with codebase pattern extraction. Single-pass. Add `--parallel` for 3-researcher fan-out + batched plan. Add `--enhanced` for the full 7-researcher fan-out.                                                                                      |
| `/prp-prd`         | Interactive PRD first, then prp-plan. Problem-first hypothesis workflow.                                                                                                                                                                                                  |
| `/plan-workflow`   | Heavyweight parallel-agent planning. Multi-task features. Artifact output.                                                                                                                                                                                                |
| `/parallel-plan`   | Lower-level component of `/plan-workflow` for dependency-aware plans.                                                                                                                                                                                                 |

### Which `--parallel` should I use?

- **`/plan --parallel`** — You want a quick parallel-capable plan without creating an artifact file. Planner does its own research. Best for small/medium features.
- **`/prp-plan --parallel`** — You want research fan-out (3 parallel researchers covering 8 categories) plus a full artifact file with patterns to mirror and validation commands. Best for medium/large features where you want a rigorous, auditable plan.
- **`/plan-workflow`** — You want heavyweight team orchestration with shared context and multi-phase validation. Best for very large features spanning many tasks.

### When to use `--enhanced`


- **`/plan --enhanced <request>`** — Fans out 5 standalone parallel sub-agents (Path C). Works in every bundle. Best for medium-complexity features where a 3-persona plan would miss security or UX considerations and you don't need the team coordination overhead.
- **`/plan --enhanced --parallel <request>`** — 5-persona plan formatted for parallel execution (Batches section, `Depends on` annotations).
- **`/plan --enhanced --dry-run <request>`** — Print the 5-persona roster without spawning anyone. Useful to confirm the team shape before paying the dispatch cost.
- **`/prp-plan --enhanced <request>`** — The heavier sibling: 7 researchers, artifact-producing. Use when you want the enhanced perspectives _and_ a saved plan file, not just an in-conversation plan.

### When to use `--no-worktree`

Worktree annotations are emitted by default. Pass `--no-worktree` to suppress the `## Worktree Setup` section and all per-task `**Worktree**:` annotations when you do not intend to use git worktree isolation:

- **`/plan --parallel <request>`** — Parallel-capable plan with full worktree annotations (default). Hand off to `/prp-implement` for isolated execution.
- **`/plan --no-worktree --parallel <request>`** — Parallel-capable plan without worktree annotations. Use when worktree isolation is not desired.
