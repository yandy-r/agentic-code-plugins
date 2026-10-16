# Validation Agent Prompts

## Contents

- Global Output Contract
- Standard Mode: 3 Validation Sub-agents
- Optimized Mode: 2 Validation Sub-agents
- Usage Instructions
- Sub-agent Configuration

These prompts are used to spawn validation sub-agents or sub-agents after creating a parallel plan. This is Phase 9 of the unified planning workflow.

## Global Output Contract

Apply this contract to every prompt in this file:

- Validators **report** findings; they never write or edit any artifact file (the orchestrator applies fixes to `parallel-plan.md`).
- Do not touch files under `{{FEATURE_DIR}}` or anywhere else.
- Read only `{{FEATURE_DIR}}/parallel-plan.md` (and `shared.md` where listed).
- **Path A (standalone, default)**: no `re-dispatch the affected sub-agent with the needed guidance`, `the todo tracker`, `update the todo tracker` — report all findings in your final response.

---

## Standard Mode: 3 Validation Sub-agents

### Agent 1: File Path Validator

**Sub-agent Role**: `path-validator`

**Subagent Type**: `explore`

**Task Description**: Verify file path references

**Prompt Template**:

```
Verify all file paths referenced in the parallel implementation plan exist in the codebase.

## Context

Read: {{FEATURE_DIR}}/parallel-plan.md

## Your Task

Scan the plan and check:

1. **Critically Relevant Files section**
   - Verify each listed file path exists
   - Check if paths are relative to project root

2. **Task Instructions**
   - Verify files in "READ THESE BEFORE TASK" sections
   - Check "Files to Create" for conflicts with existing files
   - Verify "Files to Modify" exist

3. **Documentation References**
   - Check any /docs/ references are valid

## Task Coordination


1. Check the todo tracker for your assigned task
2. Claim your task with update the todo tracker (set status to in_progress, owner to your name)
3. Do your validation
4. Share findings with sub-agents
5. Mark your task complete with update the todo tracker

## Output Format

Provide a report with:

**Valid Paths** (checkmark)
- /path/to/file.ext
- /path/to/another.ext

**Missing Paths** (X)
- /path/to/nonexistent.ext - File not found
- /path/to/missing.ext - File not found

**Potential Issues** (warning)
- /path/to/file.ext - Listed in "Files to Create" but already exists
- /path/to/ambiguous - Multiple files match pattern

**Suggestions**
- Correct path for /wrong/path.ext might be /correct/path.ext
- Consider adding missing file references

Focus on accuracy - verify each path exists before marking valid.
```

---

### Agent 2: Dependency Graph Validator

**Sub-agent Role**: `dependency-validator`

**Subagent Type**: `explore`

**Task Description**: Analyze task dependencies

**Prompt Template**:

```
Analyze the task dependency graph in the parallel implementation plan for issues.

## Context

Read: {{FEATURE_DIR}}/parallel-plan.md

## Your Task

Extract all tasks and their dependencies, then check for:

1. **Circular Dependencies**
   - Tasks that depend on each other (directly or indirectly)
   - Example: Task 2.1 depends on 3.1, and 3.1 depends on 2.1

2. **Missing Dependencies**
   - Tasks that reference or modify files created by prior tasks
   - Tasks that should depend on each other but don't

3. **Orphaned Tasks**
   - Tasks that nothing depends on and don't contribute to later work

4. **Parallelization Opportunities**
   - Tasks marked as dependent that could actually run in parallel
   - Tasks that share no file modifications or data dependencies

## Task Coordination


1. Check the todo tracker for your assigned task
2. Claim your task with update the todo tracker (set status to in_progress, owner to your name)
3. Do your validation
4. Share findings with sub-agents
5. Mark your task complete with update the todo tracker

## Output Format

**Dependency Graph** (text visualization, indented — no nested code fence)

    Phase 1:
    1.1 [none] ----+
    1.2 [none] ----+--> Phase 2
    1.3 [1.1] ----+

    Phase 2:
    2.1 [1.1, 1.2] ---> 2.3
    2.2 [none] ---> 2.3
    2.3 [2.1, 2.2]

**Issues Found**

Circular Dependencies: [count]
- Task 2.1 -> 3.1 -> 2.1 (circular)

Missing Dependencies: [count]
- Task 3.1 modifies file created in 2.2 but doesn't depend on it

Orphaned Tasks: [count]
- Task 1.3 creates file never used

**Parallelization Analysis**

Current parallelizable tasks: [count]
Potential additional parallel tasks: [count]
- Tasks 2.1 and 2.2 could run in parallel (no shared dependencies)

**Recommendations**
- Add dependency: 3.1 depends on [2.2]
- Consider removing orphaned task 1.3 or clarify its purpose
- Tasks 2.1 and 2.2 can be marked [none] to increase parallelism
```

---

### Agent 3: Task Completeness Validator

**Sub-agent Role**: `completeness-validator`

**Subagent Type**: `codebase-research-analyst`

**Task Description**: Evaluate task quality

**Prompt Template**:

```
Evaluate whether each task in the parallel implementation plan is actionable and complete.

## Context

Read:
- {{FEATURE_DIR}}/parallel-plan.md
- {{FEATURE_DIR}}/shared.md

## Your Task

For each task, evaluate:

1. **Clear Purpose**
   - Is it obvious what this task accomplishes?
   - Is the task title descriptive?

2. **Specific File Changes**
   - Are file paths specific (not placeholders)?
   - Are both creation and modification clear?

3. **Actionable Instructions**
   - Can a developer implement without guessing?
   - Are integration points clear?
   - Are patterns to follow specified?

4. **Gotchas Documented**
   - Are non-obvious issues mentioned?
   - Are dependencies on existing code noted?
   - Are edge cases addressed?

5. **Appropriate Scope**
   - Is the task small enough (1-3 files)?
   - Should it be broken into subtasks?

## Task Coordination


1. Check the todo tracker for your assigned task
2. Claim your task with update the todo tracker (set status to in_progress, owner to your name)
3. Do your validation
4. Share findings with sub-agents
5. Mark your task complete with update the todo tracker

## Output Format

**Task Quality Summary**

Total Tasks: [count]
High Quality: [count] (checkmark)
Needs Minor Improvements: [count] (warning)
Needs Significant Work: [count] (X)

**Detailed Findings**

(checkmark) Task 1.1: [Title] - Well-defined and actionable
(checkmark) Task 1.2: [Title] - Clear purpose and instructions

(warning) Task 2.1: [Title]
  - Missing: Gotchas or edge cases
  - Suggestion: Mention how this integrates with existing auth system

(warning) Task 2.3: [Title]
  - Issue: Scope too large (modifies 5 files)
  - Suggestion: Split into 2.3a and 2.3b

(X) Task 3.1: [Title]
  - Missing: Specific file paths (uses placeholders)
  - Missing: Clear instructions for implementation
  - Missing: Pattern to follow
  - Needs: Complete rewrite with specific details

**Recommendations**

Priority Improvements:
1. Task 3.1 - Add specific file paths and detailed instructions
2. Task 2.3 - Split into smaller tasks
3. Task 2.1 - Document integration gotchas

Overall Assessment:
[Summary of plan quality and readiness for implementation]
```

---

## Optimized Mode: 2 Validation Sub-agents

### Agent 1: Path and Dependency Validator (Combined)

**Sub-agent Role**: `path-dep-validator`

**Subagent Type**: `explore`

**Task Description**: Verify paths and dependencies

**Prompt Template**:

```
Verify all file paths and analyze the dependency graph in the parallel implementation plan.

## Context

Read: {{FEATURE_DIR}}/parallel-plan.md

## Your Task

### Part 1: File Path Validation
Verify all paths in: Critically Relevant Files, READ THESE BEFORE TASK, Files to Create/Modify, docs references. Check for conflicts.

### Part 2: Dependency Analysis
Extract tasks and dependencies. Check for: circular dependencies, missing dependencies, orphaned tasks, parallelization opportunities.

## Task Coordination


Claim your task, do validation, share findings, mark complete.

## Output Format

File Path Validation summary, Dependency Graph, Combined Issues, Recommendations.
```

---

### Agent 2: Task Quality Validator

**Sub-agent Role**: `completeness-validator`

**Subagent Type**: `codebase-research-analyst`

**Task Description**: Evaluate task completeness

**Prompt Template**:

```
Evaluate whether each task in the parallel implementation plan is actionable and complete.

## Context

Read:
- {{FEATURE_DIR}}/parallel-plan.md
- {{FEATURE_DIR}}/shared.md

## Your Task

For each task evaluate: Clear Purpose, Specific Files, Actionable Instructions, Gotchas Documented, Appropriate Scope (1-3 files).

## Task Coordination


Claim your task, do validation, share findings, mark complete.

## Output Format

Task Quality Summary, Detailed Findings, Priority Improvements, Overall Assessment.
```

---

## Usage Instructions

Common to both paths:

1. **Read this file** to get the prompt templates
2. **Substitute variables**:
   - `{{FEATURE_NAME}}` - The feature directory name
   - `{{FEATURE_DIR}}` - Full output directory path

**Path A — standalone sub-agents (default)**:

4. **Collect results** from each sub-agent's final response
5. **Review results** - Address issues found before finalizing plan


3. **Create tasks** - Use track the task for validation tasks
5. **Monitor progress** - Use the todo tracker to check when all tasks complete
6. **Review results** - Address issues found before finalizing plan
