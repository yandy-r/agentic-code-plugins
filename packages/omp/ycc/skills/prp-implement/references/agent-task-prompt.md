# PRP Implementor Task Prompt

Read once before parallel or agent-team dispatch. Substitute complete task details, not summaries.

## Prompt fields

- `agent`: `implementor`
- `name`: CamelCase label for task title (e.g. `Task 1.1: add rate limiter middleware`)
- `task`: complete task spec (ACTION, IMPLEMENT, MIRROR, IMPORTS, GOTCHA, VALIDATE), plus relevant excerpt from the plan's Patterns to Mirror section.
- `solutionSpace`: how open-ended the work is (item shape: `skill://ycc-shared/references/standalone-dispatch.md` §1)

## Prompt template

```text
Implement {{TASK_ID}}: {{TASK_TITLE}}

Plan: {{PLAN_PATH}}
Patterns to Mirror:
{{PATTERNS_TO_MIRROR}}

Task specification:
{{TASK_SPEC}}

Read the MIRROR source file before writing code. Follow its pattern exactly,
apply GOTCHA warnings and use specified IMPORTS. Implement only this task.
Run your own type-check on modified files before reporting complete.
Report files created/modified, validation results, issues and deviations
verbatim (what changed and why).

{{WORKING_DIRECTORY_LINES}}
{{TEAM_COMPLETION_DIRECTIVE}}
```

`WORKING_DIRECTORY_LINES`: use shared execution-directory prompt contract, for
both parallel and sequential tasks. Treat that directory as repo root for all
Read / Write / Edit / Bash calls; no per-agent worktree isolation.
`TEAM_COMPLETION_DIRECTIVE`: empty for standalone; when `--team`, require agent
to call `todo` to mark its own registered task complete.
