---
description: 'Convert rule-file hook guidance into target-appropriate config. Reads
  hook recommendations from the resolved language rules, consults the target-capability
  matrix, and emits only config the target can execute (Claude → JSON; Cursor → advisory
  rule embedding where supported; Codex → advisory-only). Use when the user asks to
  "generate hook config", "configure Claude hooks from ycc rules", "apply ycc hooks",
  "cross-target hook setup", "hook matrix for this repo", or "verify my hook config".
  Usage: <language> [--target=claude|cursor|codex] [--event=PreToolUse|PostToolUse|Stop|all]
  [--out=<path>] [--dry-run] [--verify] [--force]'
---

Use the skill tool to load the `hooks-workflow` skill, then follow its instructions with these arguments:

$ARGUMENTS
