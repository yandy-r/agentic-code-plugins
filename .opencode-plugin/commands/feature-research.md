---
description: 'Run the 7-agent research pipeline for a new feature — deploys api-researcher,
  business-analyzer, tech-designer, ux-researcher, security-researcher, practices-researcher,
  and recommendations-agent in parallel to produce 7 research-*.md files and a consolidated
  feature-spec.md under docs/plans/[feature-name]/. Default is standalone parallel
  sub-agents via the native `subagent` tool. Outputs to docs/plans/, NOT docs/prps/.
  Use when the user asks to "research a feature", "run feature research", "deep-dive
  a feature before planning", or says "/feature-research". For lightweight single-pass
  specs in the PRP workflow, use prp-spec instead. Usage: [--description "..."] [--dry-run]
  [feature-name]'
---

Use the skill tool to load the `feature-research` skill, then follow its instructions with these arguments:

$ARGUMENTS
