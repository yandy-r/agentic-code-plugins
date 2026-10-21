---
name: feature-research
description: Researches features with seven specialists and consolidates a feature
  spec. Use when investigating APIs, assessing feature risks, or researching UX before
  planning.
---

# Feature Research

> **OpenCode V2 compatibility:** `--team` is unsupported. If it is supplied, abort before setup or dispatch and ask the caller to rerun without it. This target uses native standalone `subagent` calls only.


**Operational context:** Dispatch api-researcher, business-analyzer, tech-designer, ux-researcher, security-researcher, practices-researcher, and recommendations-agent; write seven research-*.md files plus feature-spec.md under docs/plans/[feature-name]/, never docs/prps/. Use /prp-spec for lightweight single-pass PRP specs.

## Workflow Integration

```
feature-research  -->  plan-workflow  -->  implement-plan
(this skill)           (Step 2)            (Step 3)
Creates:               Uses:               Executes:
feature-spec.md        feature-spec.md     parallel-plan.md
```

**Key Distinctions — This skill vs. other planning/research skills**:

| Skill                     | Agents                            | Output Dir           | Output Files                          | Use When                                       |
| ------------------------- | --------------------------------- | -------------------- | ------------------------------------- | ---------------------------------------------- |
| `feature-research` (THIS) | 7 parallel agents                 | `docs/plans/[name]/` | 7 `research-*.md` + `feature-spec.md` | Deep multi-agent research before plan-workflow |
| `prp-spec`                | Single pass (optional researcher) | `docs/prps/specs/`   | `{name}.spec.md`                      | Lightweight spec for PRP workflow              |
| `prp-prd`                 | Interactive + researcher          | `docs/prps/prds/`    | `{name}.prd.md`                       | Full PRD with hypothesis-driven questioning    |
| `prp-plan`                | Single pass + researcher          | `docs/prps/plans/`   | `{name}.plan.md`                      | Implementation plan from PRD or description    |

**This skill ALWAYS**:

- Deploys all 7 researchers in parallel (never skips agents)
- Creates 7 `research-*.md` files + 1 `feature-spec.md`
- Outputs ONLY to `docs/plans/[feature-name]/`

**This skill NEVER**:

- Writes to `docs/prps/` (that is the PRP workflow directory)
- Generates a single-file spec without the research pipeline
- Skips the multi-agent research pipeline to produce output directly
- Acts as a lightweight spec generator

## Arguments

**Target**: `$ARGUMENTS`

Parse arguments (flags first, then the feature name):

- **--description "..."**: Brief description of the feature (guides research agents)
- **feature-name**: Required. Directory name in `docs/plans/`

If no feature name provided, abort with usage instructions:

```
Usage: /feature-research [--description "..."] [--dry-run] [feature-name]

Examples:
  /feature-research plex-integration --description "Advanced Plex media library integration with filters and playlists"
  /feature-research payment-system --description "Stripe payment integration for subscriptions"
  /feature-research user-dashboard --dry-run
```

**Questions:** class `choose-path` (regenerate or enhance an existing spec); headless (no question tool or chat turn): enhance. See `~/.config/opencode/shared/references/question-policy.md`.

---

## Phase 0: Initialize

### Step 1: Parse Arguments

Extract from `$ARGUMENTS`:

2. **--description**: Quoted string after flag (optional but recommended)
3. **--dry-run**: Boolean flag. Set `DRY_RUN=true` if present, else `false`.
4. **feature-name**: First non-flag argument (required)

Validate the feature name: must be kebab-case, no special characters except hyphens.



### Step 2: Create Directory

**CRITICAL**: Output goes to `docs/plans/[feature-name]/` — NEVER to `docs/prps/` or any other directory, regardless of the user's current working directory. If the user invokes this skill from inside `docs/prps/` or any subdirectory, still resolve the output path from the repository root as `docs/plans/[feature-name]/`.

```bash
test -d "docs/plans/[feature-name]" && echo "exists" || mkdir -p "docs/plans/[feature-name]"
```

### Step 3: Check Existing Research

List any existing files. If `feature-spec.md` exists, read it and ask user if they want to regenerate or enhance.

### Step 4: Handle Dry Run

If `--dry-run` is present:

Display:

```markdown
# Dry Run: Feature Research for [feature-name]

## Research Pipeline

Dispatch Mode: [standalone sub-agents]
Researchers: 7 (api-researcher, business-analyzer, tech-designer, ux-researcher, security-researcher, practices-researcher, recommendations-agent)

1. api-researcher - External APIs, libraries, integration patterns
2. business-analyzer - Requirements, user stories, business rules
3. tech-designer - Architecture, data models, API design
4. ux-researcher - User experience, workflows, best practices
5. security-researcher - Security analysis, dependency risks, secure coding (severity-leveled)
6. practices-researcher - Modularity, code reuse, KISS, engineering best practices
7. recommendations-agent - Ideas, improvements, risks

## Files That Would Be Created

- docs/plans/[feature-name]/research-external.md
- docs/plans/[feature-name]/research-business.md
- docs/plans/[feature-name]/research-technical.md
- docs/plans/[feature-name]/research-ux.md
- docs/plans/[feature-name]/research-security.md
- docs/plans/[feature-name]/research-practices.md
- docs/plans/[feature-name]/research-recommendations.md
- docs/plans/[feature-name]/feature-spec.md

## Execution Model

- Default (`STANDALONE_MODE=true`): deploy 7 researchers as standalone sub-agents in a single message with multiple native `subagent` calls. No team coordination; each sub-agent writes its assigned `research-*.md`. Orchestrator validates and synthesizes `feature-spec.md`.
```



Do **not** call `track the task`, `subagent`, or `re-dispatch the affected sub-agent with the needed guidance` in dry-run mode.

**STOP** without creating files or deploying agents.

---

## Phase 1: Research Pipeline

### Step 7: Read Research Prompts

Read the research prompts template:

```bash
cat ~/.config/opencode/skills/feature-research/templates/research-agents.md
```

### Step 8: Deploy the 7 Researchers

| Name / Sub-agent role  | Subagent Type               | Output File                   | Model   | Focus                                                                 |
| ----------------------- | --------------------------- | ----------------------------- | ------- | --------------------------------------------------------------------- |
| `api-researcher`        | `research-specialist`       | `research-external.md`        | configured | External APIs, libraries, documentation, integration patterns         |
| `business-analyzer`     | `codebase-research-analyst` | `research-business.md`        | configured | Requirements, user stories, business rules, domain logic              |
| `tech-designer`         | `codebase-research-analyst` | `research-technical.md`       | configured | Architecture, data models, API design, system constraints             |
| `ux-researcher`         | `research-specialist`       | `research-ux.md`              | configured | User experience, workflows, best practices, accessibility             |
| `security-researcher`   | `research-specialist`       | `research-security.md`        | configured | Security analysis, dependency risks, secure coding (severity-leveled) |
| `practices-researcher`  | `codebase-research-analyst` | `research-practices.md`       | configured | Modularity, code reuse, KISS, engineering best practices              |
| `recommendations-agent` | `codebase-research-analyst` | `research-recommendations.md` | configured | Ideas, improvements, related features, risks                          |


Use the prompts from `research-agents.md` with variables substituted:

- `{{FEATURE_NAME}}` - The feature directory name
- `{{FEATURE_DIR}}` - Full output directory path (`docs/plans/[feature-name]`)
- `{{FEATURE_DESCRIPTION}}` - The description provided (or feature name if none)

#### Path A — Standalone sub-agents (`STANDALONE_MODE=true`, default)

**CRITICAL**: Deploy all 7 researchers in a **SINGLE message** with **MULTIPLE native `subagent` calls**. Every call sets `background=false`, uses the configured agent model, and follows the shared result policy below.

If a child report is empty or contentless, record its `sessionID`, inspect the declared artifact or working-tree edits, preserve valid work, and make at most one retry before reporting the child result incomplete. An artifact can preserve work but does not prove a child response. Follow `~/.config/opencode/shared/references/standalone-dispatch.md`.

### Step 9: Monitor Research Progress

Wait for all 7 researchers to complete their work.

If a child report is empty or contentless, record its `sessionID`, inspect the declared artifact or working-tree edits, preserve valid work, and make at most one retry before reporting the child result incomplete. An artifact can preserve work but does not prove a child response. Follow `~/.config/opencode/shared/references/standalone-dispatch.md`.
  - `api-researcher` tells `tech-designer` about discovered API endpoints and auth patterns
  - `api-researcher` tells `security-researcher` about dependency versions and auth methods
  - `api-researcher` tells `practices-researcher` about discovered libraries for build-vs-depend analysis
  - `tech-designer` tells `business-analyzer` about data model constraints
  - `tech-designer` tells `security-researcher` about proposed architecture for review
  - `tech-designer` tells `practices-researcher` about proposed component structure for modularity review
  - `ux-researcher` tells `business-analyzer` about user workflow requirements
  - `security-researcher` tells `tech-designer` about security constraints (with severity levels)
  - `security-researcher` tells `recommendations-agent` about full risk summary by severity
  - `practices-researcher` tells `tech-designer` about reusable code discoveries and simplification opportunities
  - `practices-researcher` tells `recommendations-agent` about modularity and reuse findings
  - `recommendations-agent` synthesizes insights from all sub-agents including security and practices findings

  If a sub-agent gets stuck, send them guidance via `re-dispatch the affected sub-agent with the needed guidance`.

**Failure policy for Path B** (mirrors deep-research):

- **Single sub-agent failure**: record the gap in the corresponding `research-*.md` (stub note) and continue — downstream synthesis will adapt.
- **Mid-run user abort**: `re-dispatch the affected sub-agent with the needed guidance(shutdown)` to every active sub-agent, then confirm all sub-agents have shut down. Never exit with sub-agents still live.

---

## Phase 2: Consolidate Research

### Step 10: Validate Research Artifacts

After all 7 sub-agents complete, validate all `research-*.md` files:

```bash
~/.config/opencode/skills/feature-research/scripts/validate-research.sh docs/plans/[feature-name]
```

If validation fails: message the relevant sub-agent to fix their output, wait for correction, rerun validation until pass.

### Step 12: Read Research Results

Read all 7 research files from `docs/plans/[feature-name]/`.

### Step 13: Read Spec Template

```bash
cat ~/.config/opencode/skills/feature-research/templates/spec-structure.md
```

### Step 14: Generate feature-spec.md

Create `docs/plans/[feature-name]/feature-spec.md` following the template.

**Key Consolidation Principles**:

1. Organize by section, not by agent - Synthesize related findings
2. Be information-dense - Every sentence should add value
3. Include actionable details - Links, code examples, specific APIs
4. Highlight decisions needed - Call out areas requiring user input
5. Preserve source references - Link to original research files for details
6. Surface security findings by severity - CRITICAL items must appear in Risk Assessment; WARNING items in relevant technical sections; ADVISORY items in Recommendations

---

## Phase 3: Validate and Complete

### Step 15: Validate Spec

Run after Step 14 creates `feature-spec.md`:

```bash
~/.config/opencode/skills/feature-research/scripts/validate-spec.sh docs/plans/[feature-name]/feature-spec.md
```

Fix any issues reported (missing sections, empty content, formatting).

### Step 17: Display Summary

Provide completion summary with: feature name, description, dispatch mode (standalone sub-agents), files created, research summary counts, key findings, decisions needed, and next steps (review spec, proceed to `/plan-workflow`, or add requirements).

---

## Quality Standards

### feature-spec.md Quality Checklist

- Executive summary is information-dense (3-5 sentences)
- External dependencies include documentation links
- Business requirements are specific and testable
- Technical specs include data models/schemas
- UX considerations address error states
- Recommendations are actionable
- Task breakdown preview is realistic

### Research Quality Checklist

Each research file should: focus on its specific domain, include concrete examples and links, identify gaps and uncertainties, provide actionable recommendations, and avoid duplication with other research files.

## Anti-patterns — Do NOT Do These

1. **Do NOT skip the multi-agent pipeline**: Never generate `feature-spec.md` directly without first deploying all 7 researchers (standalone sub-agents) and collecting their `research-*.md` files. The spec is a synthesis of research, not a standalone generation. If about to write `feature-spec.md` without the 7 research files already on disk, STOP — the pipeline is off-rails.

2. **Do NOT output to `docs/prps/`**: This skill's output directory is `docs/plans/[feature-name]/`. The `docs/prps/` tree belongs to the PRP workflow (`prp-prd`, `prp-spec`, `prp-plan`, `prp-implement`). Even if the user's working directory is `docs/prps/` or any subdirectory, always create output under `docs/plans/`.

3. **Do NOT generate a single file**: The minimum correct output is 8 files (7 research + 1 spec). If about to write only one file, STOP — the user likely wants the lightweight PRP spec skill. Redirect them to `/prp-spec`.

4. **Do NOT conflate with PRP spec generation**: If the user wants a lightweight single-pass spec without the 7-researcher pipeline, they want `/prp-spec`, not this skill. This skill is the heavyweight multi-agent research track regardless of dispatch mode.

## Important Notes

- **You are the research orchestrator** — coordinate the 7 researchers and synthesize the spec
- **Spawn in parallel** — a single message with 7 native `subagent` calls (Path A) or 7 native `subagent` calls with `description` plus the role-specific `prompt` (Path B)
- **Single-owner research files** — each researcher writes only its assigned artifact
- **Gate synthesis with validation** — do not generate `feature-spec.md` before validator pass
- **Use web search** — external APIs require current documentation
- **Be thorough but focused** — quality over quantity
- **Enable plan-workflow** — this spec is the foundation for implementation planning
- **Preserve uncertainty** — mark areas needing clarification rather than guessing
