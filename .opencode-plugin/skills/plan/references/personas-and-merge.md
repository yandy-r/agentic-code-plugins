# Planning Personas, Dry Run and Merge

## Contents

- Standalone Dry-Run (Path C)
- Agent-Team Dry-Run (Path B)
- Persona prompt contract
- Failure policy
- Re-dispatch
- Merge outputs (B.7)

| Sub-agent name      | `agent`                 | Role focus                                                                         |
| ------------------- | ------------------------------- | ---------------------------------------------------------------------------------- |
| `architect`         | `planner`                   | Structural plan, phases, file layout, dependencies                                 |
| `risk-analyst`      | `codebase-research-analyst` | Risks, edge cases, rollback, migration concerns                                    |
| `test-strategist`   | `test-strategy-planner`     | Testing strategy, validation commands, acceptance criteria                         |
| `security-reviewer` | `research-specialist`       | Threat model, input validation, authn/authz, secrets handling, dependency risk     |
| `ux-reviewer`       | `research-specialist`       | User-facing impact (UI, CLI, API responses, error messages); skip if internal-only |

## Standalone Dry-Run (Path C)

When `DRY_RUN=true`:

Print:

```
Dispatch:    standalone parallel sub-agents (no team)
Sub-agents:  5
  - architect         agent=planner                    task=Structural plan, phases, file layout, dependencies
  - risk-analyst      agent=codebase-research-analyst  task=Risks, edge cases, rollback, migration concerns
  - test-strategist   agent=test-strategy-planner      task=Testing strategy, validation commands, acceptance criteria
  - security-reviewer agent=research-specialist        task=Threat model, input validation, authn/authz, secrets, dependency risk
  - ux-reviewer       agent=research-specialist        task=User-facing impact (UI, CLI, API responses, error messages); skip if internal-only
Batches:     1  (single message, 5 parallel native subagent calls)
```

Do **not** spawn any agents. Exit the skill.

## Persona prompt contract

Each baseline prompt must include:

- Original request verbatim; referenced files/context; role focus from the roster (which slice of the plan this persona owns); standard confirmation instruction to follow Plan Format and end with `**WAITING FOR CONFIRMATION**: Proceed with this plan? (yes / no / modify)`.
- Team only: instruction to coordinate via `re-dispatch the affected sub-agent with the needed guidance` with the roster for overlapping scope; standalone omits that line and standalone calls omit the team-only parameters.
- Append parallel output directives when PARALLEL_MODE=true and worktree annotation directive when WORKTREE_MODE=true (omit for --no-worktree).

For security-reviewer and ux-reviewer use enhanced-personas prompts verbatim and append same output directives.

## Failure policy

- Architect failure: critical, abort with clear error.
- Risk-analyst/test-strategist failure: record "partial plan — {role} did not complete", proceed with reduced merge and visible gap.
- Security-reviewer/ux-reviewer failure: non-critical, record "partial plan — {role} did not complete; security/UX coverage may be incomplete", proceed.

## Re-dispatch

Standalone enhanced (Path C) re-dispatch fires a fresh batch of 5 parallel standalone sub-agent calls; the team-only parameters belong exclusively to the team dispatch primitive and are never set here. Path C created no team, so there is nothing to tear down.


## Merge outputs (B.7)

Synthesize the sub-agent outputs (3 or 5) into a single unified plan following the standard
`planner` Plan Format. Merging rules:

- **Overview / Summary**: use `architect`'s framing.
- **Architecture Changes / Implementation Steps**: primarily `architect`; fold in
  `risk-analyst`'s findings as per-step risk callouts or a dedicated `## Risks &
Mitigations` section.
- **Testing Strategy / Success Criteria**: use `test-strategist`'s content verbatim.
- **Batches section** (if `PARALLEL_MODE=true`): use `architect`'s numbering; re-index
  if `risk-analyst` or `test-strategist` added follow-on steps.
- When `ENHANCED_MODE=true`, also fold in:
  - **`security-reviewer`** → add a top-level `## Security Considerations` section listing the threat-model findings and validation requirements. If specific steps need callouts (e.g., "input must be validated against …"), also annotate the matching `architect` step with `> **Security**: …`. If `security-reviewer` returned no significant findings, omit the section entirely (do not write "N/A").
  - **`ux-reviewer`** → add a top-level `## UX Impact` section with Before / After / Interaction Changes. If `ux-reviewer` returned "Internal change — no user-facing UX impact", omit the section entirely.
- End with the standard confirmation prompt: `**WAITING FOR CONFIRMATION**: Proceed
with this plan? (yes / no / modify)`
