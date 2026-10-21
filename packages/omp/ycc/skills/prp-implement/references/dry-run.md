# PRP Agent-Team Dry-Run Output

C.2: if `DRY_RUN=true`, print:

```
Team name:    prpi-<sanitized-plan-basename>
Total tasks:  <N>  (across <M> batches, max parallel width <X>)
Dependencies: <K edges>  (from plan's `Depends on` annotations)

Batch 1: <comma-separated task IDs>
Batch 2: <comma-separated task IDs>  (depends on Batch 1)
...
Batch M: <comma-separated task IDs>  (depends on Batch M-1)

Per-batch teammate roster:
  Batch 1:
    - <task-id-1>  agent=implementor  task=<short>
    - <task-id-2>  agent=implementor  task=<short>
  ...
```

Do **not** call any team/task/agent tools. Exit the skill.
