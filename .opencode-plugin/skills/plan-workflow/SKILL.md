---
name: plan-workflow
description: Researches, analyzes, and validates feature plans with checkpoints. Use
  when running research-to-plan workflow, producing shared.md and parallel-plan.md,
  or reviewing research before planning.
---

# Unified Planning Workflow

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.


Flow: Research → Checkpoint → Analysis → Plan Generation → Validation → optional `--visual`.

## Dispatch lifecycle (applies to every agent-spawning step below)

Read `~/.config/opencode/shared/references/standalone-dispatch.md` for standalone dispatch.

## Critical gates (read first)

1. **Mutual exclusion — abort before any write**: if both `--research-only` and `--plan-only` are present, print and **STOP** (no directory creation, no file writes):

   ```
   Error: --research-only and --plan-only are mutually exclusive
   Usage: /plan-workflow [--research-only | --plan-only] [--no-checkpoint] [--optimized] [--dry-run] [--no-worktree] [--visual] [feature-name]
   ```

2. **Feature name required**: kebab-case (lowercase, hyphens), no other special characters. If missing or invalid, abort with the matching error block from `references/checkpoint-messages.md` ("Error Messages": Missing Feature Name / Invalid Feature Name).
4. **Dry-run writes nothing**: handled before the prereq gate, overwrite prompt, any `mkdir`, write, dispatch, or rendering. Never prompts for input. It prints the preview and then **STOP**s.


5. **`--plan-only` prerequisite gate (before any `mkdir` or write)**: `scripts/check-prerequisites.sh` must exit 0. On failure, print its output plus `run /shared-context <feature> or /plan-workflow <feature> --research-only first`, then **STOP**. Never fall back to running research inline under `--plan-only`.
6. **`--optimized --plan-only` restriction**: the five unified analysis files must already exist (prior `--optimized` full run); there is no Phase 5 to regenerate them. If any is missing, **STOP** with: `--optimized --plan-only needs a prior --optimized full run. Run /plan-workflow <feature> --optimized first.` Enforced at Step 4B, re-checked by the Phase 7 PRE-CHECK.
7. **Pre-generation gate (Step 22, cannot be skipped)**: `scripts/persist-or-fail.sh` must exit 0 before plan generation. On `MISSING_FILES`/`ACTION_REQUIRED`, re-dispatch the failing agent to write the missing file(s) and re-run until exit 0. The orchestrator must never write agent output files itself from captured summaries — that bypasses the contract (root cause of the May 2026 reproducer with 3 of 5 unified files missing).
8. **Validator flags**: `validate-research-artifacts.sh` (Step 11), `validate-analysis-artifacts.sh` (Step 21), and `persist-or-fail.sh` (Step 22) must be invoked with `--optimized` whenever `--optimized` was passed; without it they look for the standard file sets and fail wrongly.
9. **Validation-fail fix loop**: message the failing sub-agent (team mode) or re-dispatch the failing sub-agent via `subagent` (standalone). Wait, re-validate until pass. Never synthesize the missing file.
11. **Terminal STOP points**: dry-run preview (Step 4A), missing prereq (Step 4B), research-only stop (Step 15A), checkpoint "Stop here" (Step 16), `--optimized --plan-only` missing artifacts. At each, stop all writes and dispatch.

## Arguments

Parse flags first, then the feature name (first non-flag argument, required; directory name in `${PLANS_DIR}/`).

- **--research-only**: stop after research (creates shared.md only).
- **--plan-only**: skip research, use existing shared.md. Skips Phases 1–4, NOT Phase 5 (Analysis).
- **--no-checkpoint**: no pause between research and planning.
- **--optimized**: 7-agent unified deployment (default: 10-agent standard).
- **--worktree**: legacy no-op (worktree annotations are the default; safe to omit).
- **--no-worktree**: opt out of worktree annotations in the generated `parallel-plan.md`. No effect with `--research-only` (no plan file). Honored with `--plan-only`.
- **--visual**: render the finished plan as an Agent-Native visual artifact (MDX) via `visual-plan`; local files by default, hosted link requires `--share`.

If no feature name is provided, abort with the full usage instructions from `references/checkpoint-messages.md` — read when the feature name is missing ("Usage Instructions" section).

## Visual mode

See `~/.config/opencode/shared/references/visual-mode.md` for the canonical `--visual` contract. `--visual` is a terminal decorator step, orthogonal to `--optimized` and `--no-worktree`; it runs once at the very end. With `VISUAL_MODE=true` and no `--dry-run`, after the final phase invoke `visual-plan <absolute-plan-path>` where the path is the **actual written plan** at `${feature_dir}/parallel-plan.md` (resolved in Phase 0) — never a hardcoded `docs/prps/plans` path; `visual-plan` derives its `visual/` output directory from it. With `--dry-run`, short-circuit: print `visual generation would run` and do not invoke `visual-plan`. `--research-only` produces no plan file, so `--visual` does not run.

## Phase 0: Initialize

### Step 1: Parse Arguments


```bash
# Default ON; pass --no-worktree to opt out. --worktree accepted as legacy no-op.
WORKTREE_MODE=true
case " $ARGUMENTS " in
  *" --no-worktree "*) WORKTREE_MODE=false ;;
esac
ARGUMENTS="${ARGUMENTS//--no-worktree/}"
ARGUMENTS="${ARGUMENTS//--worktree/}"  # legacy no-op

VISUAL_MODE=false
case " $ARGUMENTS " in
  *" --visual "*) VISUAL_MODE=true ;;
esac
ARGUMENTS="${ARGUMENTS//--visual/}"
```

Apply critical gates 1–3. **feature-name** = first non-flag argument.

### Step 2: Resolve Plans Directory

```bash
source ~/.config/opencode/shared/scripts/resolve-plans-dir.sh
feature_dir="$(get_feature_plan_dir "[feature-name]")"
```

Handles monorepo detection, `.plans-config` files, and git root resolution automatically. See "Monorepo Support" below.

### Step 3: Run State Detection

```bash
~/.config/opencode/skills/plan-workflow/scripts/check-state.sh [feature-name]
```

Reports whether `${feature_dir}/` exists, `shared.md`, `parallel-plan.md`, and any research files.

### Step 4: Determine Execution Mode

| State                | --plan-only | --research-only | Action                                                                                              |
| -------------------- | ----------- | --------------- | --------------------------------------------------------------------------------------------------- |
| No shared.md         | No          | No              | Full workflow from Phase 1                                                                          |
| No shared.md         | No          | Yes             | Full workflow from Phase 1, stop at Step 15A (research-only stop)                                   |
| No shared.md         | Yes         | No              | Fail fast in Step 4B — never fall back to research                                                  |
| Has shared.md        | Yes         | No              | Skip to Phase 5 (Analysis)                                                                          |
| Has shared.md        | No          | Yes             | Regenerate only if overwrite chosen in Step 4C, then stop at Step 15A; else STOP and reuse existing |
| Has shared.md        | No          | No              | Full workflow from Phase 1 (shared.md regenerates only if overwrite chosen in Step 4C)              |
| Has parallel-plan.md | Any         | Any             | Warn about overwrite (Step 4C)                                                                      |

"Planning" = Phase 8 (Plan Generation); "Analysis" = Phase 5.

### Step 4A: Dry-Run Preview (when `--dry-run`, before anything else)

Read `references/checkpoint-messages.md` — read when previewing a dry run. Display its "Dry Run Output" section with values substituted (`{{FEATURE_NAME}}`, `{{FEATURE_DIR}}`, dispatch mode, execution mode), then **STOP** (gate 4). If `--plan-only` is also set and `check-state.sh` shows no `shared.md`, state in the preview that a real run would fail fast at Step 4B (missing prerequisite) and **STOP**.

### Step 4B: Plan-Only Prerequisite Gate (when `--plan-only`, before any write)

Run `scripts/check-prerequisites.sh "[feature-name]"` per gate 5. Then, for `--optimized --plan-only`, verify the five unified files exist before any write or dispatch (gate 6): `analysis-architecture.md`, `analysis-patterns.md`, `analysis-integration.md`, `analysis-docs.md`, `analysis-tasks.md`.

### Step 4C: Overwrite Choice (when shared.md or parallel-plan.md exists)

- **Interactive (checkpoint enabled)**: surface the matching warning from `references/checkpoint-messages.md` ("Existing State Warnings") and let the user choose regenerate vs reuse/stop.
- **Non-interactive (`--no-checkpoint`)**: default is **regenerate (overwrite)** so pipelines stay non-blocking. State the choice when proceeding (e.g. "shared.md exists — regenerating (non-interactive default)").
- **Research-only reuse**: report the existing `shared.md` path, state that no files were changed, print `/parallel-plan <feature>` as the next step, and **STOP** without dispatching agents.

### Step 5: Create Directory

Only when `--dry-run` is not set: `mkdir -p "${feature_dir}"` if missing.

## Phase 1: Research Stage (unless --plan-only)

### Step 8: Read Research Prompts

- Standard mode: read `~/.config/opencode/skills/plan-workflow/references/research-agents.md` — read when spawning Phase 1 research agents in standard mode.
- Optimized mode: read `~/.config/opencode/skills/plan-workflow/references/research-agents-optimized.md` — read when `--optimized` replaces the 4 researchers with 5 unified analysts.

Substitute `{{FEATURE_NAME}}` (feature directory name) and `{{FEATURE_DIR}}` (`${feature_dir}`, resolved in Step 2).

### Step 10: Spawn Research Agents (standard mode)

Read `references/research-agents.md`. **CRITICAL**: Deploy all 4 research agents in a **SINGLE message** with **MULTIPLE native `subagent` calls**. Every call sets `background=false`, uses the configured agent model, and follows the shared result policy below.

| Name                      | Subagent Type               | Output File                | Model  | Focus                                    |
| ------------------------- | --------------------------- | -------------------------- | ------ | ---------------------------------------- |
| `architecture-researcher` | `codebase-research-analyst` | `research-architecture.md` | configured | System structure, components, data flow  |
| `patterns-researcher`     | `codebase-research-analyst` | `research-patterns.md`     | configured | Existing patterns, conventions, examples |
| `integration-researcher`  | `codebase-research-analyst` | `research-integration.md`  | configured | APIs, databases, external systems        |
| `docs-researcher`         | `codebase-research-analyst` | `research-docs.md`         | configured | Relevant documentation files             |




## Phase 2: Validate Research Artifacts

### Step 11: Validate Research Artifacts

If a child report is empty or contentless, record its `sessionID`, inspect the declared artifact or working-tree edits, preserve valid work, and make at most one retry before reporting the child result incomplete. An artifact can preserve work but does not prove a child response. Follow `~/.config/opencode/shared/references/standalone-dispatch.md`.

```bash
# Standard mode (4-file research-*.md set):
~/.config/opencode/skills/plan-workflow/scripts/validate-research-artifacts.sh "${feature_dir}"

# Optimized mode (5-file unified analysis-*.md set):
~/.config/opencode/skills/plan-workflow/scripts/validate-research-artifacts.sh "${feature_dir}" --optimized
```

Append `--optimized` whenever the flag was passed (gate 8). On failure, apply the fix loop (gate 9). Do not proceed to shared.md synthesis until validation passes.

## Phase 3: Consolidate Research

### Step 13: Read Research Results

After validation passes, read the input set for the active mode:

- **Standard (4 files)**: `${feature_dir}/research-architecture.md`, `research-patterns.md`, `research-integration.md`, `research-docs.md`.
- **Optimized (5 unified files; no `research-*.md` exist)**: `${feature_dir}/analysis-architecture.md`, `analysis-patterns.md`, `analysis-integration.md`, `analysis-docs.md`, `analysis-tasks.md`.

### Step 14: Generate shared.md

Read `~/.config/opencode/skills/plan-workflow/references/shared-structure.md` — read when writing `shared.md`. Create `${feature_dir}/shared.md` following the template exactly.

### Step 15: Validate shared.md

```bash
~/.config/opencode/skills/plan-workflow/scripts/validate-shared.sh "${feature_dir}/shared.md"
```

Fix any errors before proceeding.

### Step 15A: Research-Only Stop (if `--research-only`)

Once `shared.md` exists and `validate-shared.sh` passed: skip Phases 4–9.5 entirely. Then:

1. Standalone research needs no teardown; proceed directly to the research-only summary.


2. Print the research-only summary: use "Research Complete Summary" from `references/checkpoint-messages.md` — read when emitting the research-only summary (standard or optimized variant), listing the artifacts this run created (standard: `research-*.md` ×4 + `shared.md`; optimized: the five unified `analysis-*.md` + `shared.md`) plus dispatch mode.
3. Next step line: `/parallel-plan <feature>` or `/plan-workflow <feature> --plan-only`.
4. **STOP** — no further writes or dispatch.

## Phase 4: Checkpoint (unless --no-checkpoint or --research-only)

### Step 16: Pause for User Review

Use **ask the user**. Question: "Research complete for [feature-name]. Review the shared context before planning?" Options:

1. **Continue to planning** — proceed to Phase 5.
2. **Review shared.md first** — display `${feature_dir}/shared.md`, then re-prompt with the same question.
3. **Stop here** — display the research-phase completion summary and end the workflow. **STOP** — do not proceed to planning.



Format from `references/checkpoint-messages.md` — read when prompting at the checkpoint ("Checkpoint Question (Phase 2)").

## Phase 5: Analysis Stage (unless --research-only or --optimized)

This phase must run in standard mode, including under `--plan-only` (which skips Research, not Analysis): it produces the `analysis-*.md` files Phase 8 requires.

### Step 18: Read Analysis Prompts

Read `~/.config/opencode/skills/plan-workflow/references/planning-agents.md` — read when spawning Phase 5 analysis agents (standard mode). Same variables: `{{FEATURE_NAME}}`, `{{FEATURE_DIR}}`.

### Step 20: Spawn Analysis Agents

**CRITICAL**: Deploy all 3 analysis agents in a **SINGLE message** with **MULTIPLE native `subagent` calls**. Every call sets `background=false`, uses the configured agent model, and follows the shared result policy below.


| Name                  | Subagent Type               | Output File           | Model  | Focus                  |
| --------------------- | --------------------------- | --------------------- | ------ | ---------------------- |
| `context-synthesizer` | `codebase-research-analyst` | `analysis-context.md` | configured | Condense planning docs |
| `code-analyzer`       | `codebase-research-analyst` | `analysis-code.md`    | configured | Extract code patterns  |
| `task-structurer`     | `codebase-research-analyst` | `analysis-tasks.md`   | configured | Suggest task breakdown |




## Phase 6: Validate and Persist Analysis Artifacts

### Step 21: First Validation Check

If a child report is empty or contentless, record its `sessionID`, inspect the declared artifact or working-tree edits, preserve valid work, and make at most one retry before reporting the child result incomplete. An artifact can preserve work but does not prove a child response. Follow `~/.config/opencode/shared/references/standalone-dispatch.md`.

```bash
# Standard mode (3-file set: analysis-context, analysis-code, analysis-tasks):
~/.config/opencode/skills/plan-workflow/scripts/validate-analysis-artifacts.sh "${feature_dir}"

# Optimized mode (5-file unified set):
~/.config/opencode/skills/plan-workflow/scripts/validate-analysis-artifacts.sh "${feature_dir}" --optimized
```

Pass → Step 22. Fail → fix loop (gate 9), re-validate.

### Step 22: Pre-Generation Gate (cannot be skipped)

```bash
# Standard mode:
~/.config/opencode/skills/plan-workflow/scripts/persist-or-fail.sh "${feature_dir}"

# Optimized mode:
~/.config/opencode/skills/plan-workflow/scripts/persist-or-fail.sh "${feature_dir}" --optimized
```

Exit 0 → Phase 7. Exit 1 → prints `MISSING_FILES` and `ACTION_REQUIRED`; re-dispatch the failing agent, re-run until exit 0 (gate 7). In optimized mode the `MISSING_FILES` set is the 5 unified files.

## Phase 7: Read Analysis Results

**PRE-CHECK — branch on execution mode**:

- **Standard**: if `analysis-context.md`, `analysis-code.md`, or `analysis-tasks.md` is missing in `${feature_dir}/`, Phase 5 was skipped in error — go back and run Phase 5 now.
- **Optimized**: the five unified files must exist (produced by Phase 1 unified agents, gated by Step 22). If any is missing, **STOP** with the gate-6 message. Optimized mode has no Phase 5 to regenerate them.

### Step 24: Read Analysis Results

- **Standard (3 files)**: `${feature_dir}/analysis-context.md`, `analysis-code.md`, `analysis-tasks.md`.
- **Optimized (5 unified files)**: `${feature_dir}/analysis-architecture.md`, `analysis-patterns.md`, `analysis-integration.md`, `analysis-docs.md`, `analysis-tasks.md`.

## Phase 8: Plan Generation

### Step 25: Read Plan Template

Read `~/.config/opencode/skills/plan-workflow/references/plan-structure.md` — read when generating `parallel-plan.md`.

### Step 26: Generate parallel-plan.md

Create `${feature_dir}/parallel-plan.md` following the template exactly. Required sections: Title & Overview (3-4 information-dense sentences); Critically Relevant Files and Documentation; Implementation Plan with Phases and Tasks; Advice section.


### Step 27: Plan Structure Check (deferred)

Structural validation (`validate-workflow-plan.sh`) runs **once**, on the final artifact, in Step 31A — after validation-agent fixes. Do not run it against the pre-validation draft.

## Phase 9: Validation Stage

### Step 28: Read Validation Prompts

Read `~/.config/opencode/skills/plan-workflow/references/validation-agents.md` — read when spawning Phase 9 validators (standard or optimized).

### Step 30: Spawn Validation Agents

**Standard mode** — 3 agents:

| Name / Sub-agent role   | Subagent Type               | Model  | Focus                                   |
| ------------------------ | --------------------------- | ------ | --------------------------------------- |
| `path-validator`         | `explore`                   | configured | Verify all referenced files exist       |
| `dependency-validator`   | `explore`                   | configured | Check for circular/invalid dependencies |
| `completeness-validator` | `codebase-research-analyst` | configured | Ensure tasks are actionable             |

**Optimized mode** — 2 agents:

| Name / Sub-agent role   | Subagent Type               | Model  | Focus                           |
| ------------------------ | --------------------------- | ------ | ------------------------------- |
| `path-dep-validator`     | `explore`                   | configured | Verify paths + dependency graph |
| `completeness-validator` | `codebase-research-analyst` | configured | Task quality + completeness     |

**CRITICAL**: Deploy all validation agents (3 in standard, 2 in optimized) in a **SINGLE message** with **MULTIPLE native `subagent` calls**. Every call sets `background=false`, uses the configured agent model, and follows the shared result policy below.


### Step 31: Review and Fix Issues

- **Path A (standalone, default)**: review each `subagent` return value for validator findings.

Fix issues: correct invalid file paths, resolve circular dependencies, add missing details to incomplete tasks.

### Step 31A: Validate Final Plan Structure

After all fixes, run once on the final artifact (before visual/completion):

```bash
~/.config/opencode/skills/plan-workflow/scripts/validate-workflow-plan.sh "${feature_dir}/parallel-plan.md"
```

Fix any structural errors it reports (missing `### Phase` is an error); do not proceed until it exits 0.

## Phase 9.5: Visual Mode (if --visual)

Runs only after the plan is written (Phase 8) and validated (Phases 8–9). It never re-orders, re-runs, or substitutes for any earlier phase. See `~/.config/opencode/shared/references/visual-mode.md`.

### Step 32.5: Render Visual Artifact

- `--dry-run` set: print `visual generation would run` and **STOP** this phase (§2.1 short-circuit — no visual artifacts).
- `--research-only` used: no plan file was generated; skip this phase.
- Otherwise invoke `visual-plan` on the **actual written plan path** (feature-dir plan resolved in Phase 0, not a hardcoded `docs/prps/plans` path):

```
visual-plan "${feature_dir}/parallel-plan.md"
```

`visual-plan` derives its `visual/` output directory from the supplied plan path and prints the resulting link (hosted URL, localhost preview, or `local files only`). Surface that link in the Phase 10 summary; do not re-derive the path yourself; do not edit the plan file.

## Phase 10: Summary

### Step 34: Display Completion Summary

Skipped when `RESEARCH_ONLY=true` (workflow ended at Step 15A) or the user stopped at the checkpoint. Otherwise use the "Full Workflow Complete Summary" block in `references/checkpoint-messages.md` — read when emitting the final summary. List only files this run actually created (`--plan-only`: omit Research Phase files; `--research-only` never reaches here).

## Optimized Mode

With `--optimized`, deploy 5 unified agents instead of separate research (4) + analysis (3), skipping Phase 5 entirely:

| Unified Agent         | Combines                            | Output                     | Model  |
| --------------------- | ----------------------------------- | -------------------------- | ------ |
| `arch-analyst`        | Arch Research + Context Synthesizer | `analysis-architecture.md` | configured |
| `pattern-analyst`     | Pattern Research + Code Analyzer    | `analysis-patterns.md`     | configured |
| `integration-analyst` | Integration Research                | `analysis-integration.md`  | configured |
| `docs-analyst`        | Doc Research                        | `analysis-docs.md`         | configured |
| `task-planner`        | Task Structure Agent                | `analysis-tasks.md`        | configured |


- **Path A (standalone, default)**: spawn all 5 unified agents in one parallel batch; every native `subagent` call sets `background=false` and inherits the configured agent model.

## Quality Standards

- **shared.md**: clear information-dense overview (3-4 sentences); all file paths verified to exist; brief useful descriptions; patterns linked to example files; documentation marked with required reading topics.
- **parallel-plan.md**: information-dense overview (3-4 sentences); complete critically-relevant file list; tasks in logical phases; at least one independent task per phase; advice section; no circular dependencies; all file paths verified.
- **Each task**: clear descriptive title; explicit dependencies; "READ THESE BEFORE TASK" section; Files to Create list (if any); Files to Modify list; concise actionable instructions.

## Output Contract

All files are written to `${feature_dir}/` (resolved via `resolve-plans-dir.sh`).

| File                       | Producer                | Required Before             |
| -------------------------- | ----------------------- | --------------------------- |
| `research-architecture.md` | architecture-researcher | shared.md synthesis         |
| `research-patterns.md`     | patterns-researcher     | shared.md synthesis         |
| `research-integration.md`  | integration-researcher  | shared.md synthesis         |
| `research-docs.md`         | docs-researcher         | shared.md synthesis         |
| `shared.md`                | Team lead (this skill)  | Analysis phase              |
| `analysis-context.md`      | context-synthesizer     | parallel-plan.md generation |
| `analysis-code.md`         | code-analyzer           | parallel-plan.md generation |
| `analysis-tasks.md`        | task-structurer         | parallel-plan.md generation |
| `parallel-plan.md`         | Team lead (this skill)  | Skill completion            |

Contract rules:

1. Each agent writes its own output file using the Write tool.
2. Team mode: each sub-agent shares key findings with relevant sub-agents via `re-dispatch the affected sub-agent with the needed guidance`. Standalone: inter-agent sharing is unavailable — each sub-agent works independently.
3. The orchestrator runs `validate-research-artifacts.sh` before generating shared.md (Step 11), `validate-analysis-artifacts.sh` after analysis agents complete (Step 21), and `persist-or-fail.sh` as the mandatory pre-generation gate (Step 22).
4. On validation failure, message the failing sub-agent (team) or re-dispatch the sub-agent (standalone) — gate 9.
5. No file may be skipped or deferred — `persist-or-fail.sh` must exit 0 before plan generation.

## Monorepo Support

Plans default to the git repository root `docs/plans/`, regardless of the subdirectory the skill runs from; `resolve-plans-dir.sh` handles detection. A `.plans-config` file customizes it — repo root (`plans_dir: docs/plans`) for centralized plans, or package-level (`plans_dir: docs/plans` + `scope: local`) for local plans.

## Notes

- You are the planning orchestrator — coordinate all phases; choose dispatch mode from `$ARGUMENTS`; spawn each stage in parallel in a single message; pass the model parameters from the tables above; validate with scripts after agents complete; read condensed analysis, not raw files; multiple validation passes ensure quality.
