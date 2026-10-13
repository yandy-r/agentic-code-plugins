# Agent Prompt Templates

## Contents

- Template Variables
- Path A Coordination Block (default — standalone sub-agents)
- Path B Team Communication Section (Include ONLY

- Pattern 1: Feature Implementation
- Pattern 2: Bug Investigation & Fix
- Pattern 3: Refactoring
- Pattern 4: Documentation Update
- Pattern 5: Testing Strategy
- Pattern 6: API Development
- Pattern 7: Database Schema Changes
- Best Practices for Using Templates
- Customizing Templates

Standard prompt templates for common orchestration patterns. Use these to ensure consistent, high-quality agent instructions.

Every template contains a coordination section that must be swapped based on the dispatch path chosen by the `orchestrate` skill:

- **Path A — Standalone sub-agents (default)**: replace the embedded `## Team Communication` block with the **Path A Coordination Block** defined below.

---

## Template Variables

All templates support these variables:

| Variable              | Description                      | Example                                    |
| --------------------- | -------------------------------- | ------------------------------------------ |
| `{{TASK}}`            | The main task being orchestrated | "Implement user authentication"            |
| `{{SUBTASK}}`         | Specific subtask for this agent  | "Create user model and schema"             |
| `{{CONTEXT_FILES}}`   | Files agent should read first    | "src/models/base.ts, docs/architecture.md" |
| `{{OUTPUT_FILES}}`    | Files agent should create/modify | "src/models/user.ts"                       |
| `{{CONSTRAINTS}}`     | What agent should NOT do         | "Don't modify authentication middleware"   |
| `{{DEPENDENCIES}}`    | What must be complete first      | "User model (Task 1.1)"                    |
| `{{BATCH_NUMBER}}`    | Current execution batch number   | "1", "2", "3"                              |
| `{{BATCH_TEAMMATES}}` | Other sub-agents in this batch    | "- **subtask-2**: Create test plan"        |

---

## Path A Coordination Block (default — standalone sub-agents)


```markdown
## Coordination

You are a standalone implementor — no inter-agent coordination, no shared task list, no inter-agent messaging. You are running in parallel with other sub-agents, but you cannot see or communicate with them.

### Task Execution

1. Read all context files listed in "Required Reading"
2. Implement your subtask exactly as specified
3. Validate your work (lint, parse, type-check where applicable)
4. Return a complete summary covering:
   - Files created
   - Files modified
   - Decisions made and why
   - Any issues, blockers, or surprises encountered
   - Integration notes that dependent subtasks will need
```

The orchestrator uses your returned summary to decide how to proceed with dependent subtasks.

---

## Pattern 1: Feature Implementation

### Use Case

Implementing a new feature across multiple components (frontend, backend, database).

### Agent Prompt Template

```markdown
You are implementing part of the "{{TASK}}" feature.

## Your Specific Task

{{SUBTASK}}

## Context

This is part of a larger orchestrated effort. Other agents are handling:

- [List other subtasks being handled in parallel]

Your work will be used by: [Agents depending on this work]

## Required Reading

Before starting, read these files to understand existing patterns:
{{CONTEXT_FILES}}

## Your Deliverables

Create/modify these files:
{{OUTPUT_FILES}}

## Implementation Requirements

1. **Follow Existing Patterns**: Match the style and conventions in the codebase
2. **Stay in Scope**: Only implement {{SUBTASK}}, nothing more
3. **Integration Points**: Ensure your code integrates with [related components]
4. **Error Handling**: Include appropriate error handling and validation
5. **Code Quality**: Write clean, maintainable, well-documented code

## Constraints

{{CONSTRAINTS}}

## Output Format

After completing the task, provide:

- List of files created
- List of files modified
- Brief description of changes
- Any issues or concerns
- Integration notes for dependent tasks
```

---

## Pattern 2: Bug Investigation & Fix

### Use Case

Investigating and fixing a bug through root cause analysis and implementation.

### Phase 1: Root Cause Analysis Agent

```markdown
Investigate the following bug: {{TASK}}

## Bug Description

{{BUG_DESCRIPTION}}

## Your Task

Perform systematic root cause analysis to identify WHY this bug is occurring.

## Investigation Approach

1. **Reproduce the Issue**: Understand the exact conditions
2. **Generate Hypotheses**: Create 3-5 possible root causes
3. **Gather Evidence**: Find code, logs, or data supporting each hypothesis
4. **Identify Root Cause**: Determine the most likely explanation

## Files to Investigate

{{CONTEXT_FILES}}

## Output Format

Provide a diagnostic report with: Bug Summary, Reproduction Steps, Root Cause Analysis (hypotheses with evidence and likelihood), Conclusion, Recommended Fix, Files That Need Changes.

**Important**: Diagnose only — DO NOT implement the fix.
```

### Phase 2: Fix Implementation Agent

```markdown
Implement a fix for: {{TASK}}

## Root Cause

[Insert findings from root-cause-analyzer]

## Your Task

{{SUBTASK}}

## Context

The root cause analysis identified: [summary]

Read the diagnostic report: {{DIAGNOSTIC_REPORT_PATH}}

## Files to Modify

{{OUTPUT_FILES}}

## Fix Requirements

1. **Address Root Cause**: Fix the underlying issue, not symptoms
2. **Avoid Regressions**: Ensure fix doesn't break other functionality
3. **Add Safety**: Include validation or checks to prevent recurrence
4. **Follow Patterns**: Match existing error handling patterns

## Output Format

Provide: Files modified, description of fix, how it addresses root cause, regression test suggestions.
```

---

## Pattern 3: Refactoring

### Use Case

Refactoring code to improve structure, performance, or maintainability.

### Phase 1: Analysis Agent

```markdown
Analyze the current implementation for refactoring: {{TASK}}

## Your Task

{{SUBTASK}} - Analyze current architecture and recommend refactoring approach

## Analysis Scope

{{CONTEXT_FILES}}

## Analysis Objectives

1. **Current State**: Document existing architecture and patterns
2. **Issues**: Identify problems, code smells, technical debt
3. **Opportunities**: Find areas for improvement
4. **Risks**: Identify risks in refactoring
5. **Approach**: Recommend refactoring strategy

## Output Format

Create analysis document with: Current Architecture, Issues Identified, Recommended Refactoring Approach, Risks & Mitigation, Files to Refactor (prioritized).
```

### Phase 2: Refactoring Implementation Agent

```markdown
Refactor code as part of: {{TASK}}

## Your Task

{{SUBTASK}}

## Refactoring Context

Read the analysis: {{ANALYSIS_PATH}}

The recommended approach is: [Summary from analysis]

## Files to Refactor

{{OUTPUT_FILES}}

## Refactoring Requirements

1. **Preserve Behavior**: Functionality must remain identical
2. **Improve Structure**: Follow the recommended patterns
3. **Maintain Tests**: Ensure existing tests still pass
4. **Incremental Changes**: Make focused, reviewable changes
5. **Document Changes**: Update comments and documentation

## Constraints

{{CONSTRAINTS}}

## Output Format

Provide: Files refactored, key changes made, test updates needed, before/after for complex changes.
```

---

## Pattern 4: Documentation Update

### Use Case

Creating or updating comprehensive documentation.

### Agent Prompt Template

```markdown
Create/update documentation for: {{TASK}}

## Your Task

{{SUBTASK}}

## Documentation Scope

Document the following aspects:

- [Aspect 1]
- [Aspect 2]
- [Aspect 3]

## Source Files to Document

Read and understand these files:
{{CONTEXT_FILES}}

## Output Files

Create/update:
{{OUTPUT_FILES}}

## Documentation Requirements

1. **Accuracy**: Documentation must match actual code behavior
2. **Completeness**: Cover all public APIs and features
3. **Examples**: Include working code examples
4. **Structure**: Use clear headings and organization
5. **Cross-References**: Link to related documentation

## Output Format

After completing documentation: files created/updated, sections added, examples included, cross-references made.
```

---

## Pattern 5: Testing Strategy

### Use Case

Creating comprehensive test plans and strategies.

### Agent Prompt Template

```markdown
Create a testing strategy for: {{TASK}}

## Your Task

{{SUBTASK}}

## Code to Test

Analyze these files:
{{CONTEXT_FILES}}

## Testing Objectives

Create a comprehensive test plan covering:

1. **Unit Tests**: Individual functions and components
2. **Integration Tests**: Component interactions
3. **End-to-End Tests**: Full user workflows
4. **Edge Cases**: Boundary conditions and error scenarios
5. **Performance Tests**: If applicable

## Output Format

Provide: Complete test plan with Unit Tests, Integration Tests, End-to-End Tests, Edge Cases, Performance Tests (if applicable), Test Data Requirements. Include priority (H/M/L) for each test case.
```

---

## Pattern 6: API Development

### Use Case

Designing and implementing RESTful API endpoints.

### Agent Prompt Template

```markdown
Implement API endpoints for: {{TASK}}

## Your Task

{{SUBTASK}}

## API Scope

Create the following endpoints:

- [Endpoint 1: Method + Path]
- [Endpoint 2: Method + Path]
- [Endpoint 3: Method + Path]

## Context

Read existing API patterns:
{{CONTEXT_FILES}}

## Files to Create/Modify

{{OUTPUT_FILES}}

## API Requirements

For each endpoint:

1. **Route Definition**: Clear path and HTTP method
2. **Request Validation**: Validate all inputs
3. **Authentication**: Apply appropriate auth middleware
4. **Error Handling**: Return proper error responses
5. **Response Format**: Consistent JSON structure
6. **Status Codes**: Use appropriate HTTP status codes

## Constraints

{{CONSTRAINTS}}

## Output Format

After implementation: endpoints implemented, request/response examples, authentication requirements, error scenarios handled.
```

---

## Pattern 7: Database Schema Changes

### Use Case

Creating or modifying database schemas and migrations.

### Agent Prompt Template

````markdown
Implement database changes for: {{TASK}}

## Your Task

{{SUBTASK}}

## Database Changes Required

- [Change 1: Create table / Alter table / Add column]
- [Change 2: Add index / Foreign key]
- [Change 3: Migration script]

## Context

Review existing schema:
{{CONTEXT_FILES}}

## Files to Create

{{OUTPUT_FILES}}

## Schema Requirements

1. **Data Integrity**: Proper constraints and foreign keys
2. **Performance**: Appropriate indexes
3. **Migration Safety**: Reversible migrations
4. **Naming Conventions**: Follow existing patterns
5. **Documentation**: Comment complex schemas

## Migration Structure

```sql
-- Migration Up
-- [Create tables, add columns, create indexes]

-- Migration Down
-- [Rollback changes]
```

## Constraints

{{CONSTRAINTS}}

## Output Format

Provide: Migration file created, tables/columns added, indexes created, rollback script included.
````

---

## Best Practices for Using Templates

1. **Always fill all variables**: Don't leave placeholders like {{TASK}} in the actual prompt
2. **Select the right coordination block**: Use the Path A standalone coordination block. Never include the Path B block in Path A prompts — there are no sub-agents to communicate with.
4. **Add specific context**: Templates are starting points — add project-specific details
5. **Adjust scope**: Narrow or expand based on subtask complexity
6. **Include examples**: Reference actual files from the codebase
7. **Set clear boundaries**: Explicitly state what NOT to do
8. **Specify output format**: Be clear about expected deliverables
9. **Link related work**: Help agents understand their place in the bigger picture

---

## Customizing Templates

When adapting templates:

1. **Add technology-specific details**: Framework, libraries, tools being used
2. **Include architectural constraints**: Design patterns, conventions, restrictions
3. **Reference style guides**: Code style, naming conventions, formatting
4. **Specify integration points**: How this connects to other components
5. **Add validation criteria**: How to verify the work is complete and correct
6. **Customize team communication**: Tailor what each agent should share based on their role

---

_These templates should be customized for your specific project, technology stack, and team conventions._
