# Generic User-Global Rules

`CLAUDE.md` is the source of truth for tool-neutral, cross-project defaults (at
most 120 lines). `AGENTS.md` is a relative symlink to that same body for compatibility
with existing links and Codex's native filename; it is not a pointer prompt.
`.opencode-plugin/AGENTS.md` copies the source verbatim after a generated header.
No runtime-name, path, or filename substitution runs over these rules.

## Installation and runtime evidence

`install.sh install --rules` (or `sync --intent rules`) provisions only documented
native global instruction files:

| Target   | Global instructions                                             | Official reference                                                                  |
| -------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Claude   | `~/.claude/CLAUDE.md`                                           | [User memory](https://code.claude.com/docs/en/memory)                               |
| Codex    | `~/.codex/AGENTS.md`                                            | [Global instructions](https://learn.chatgpt.com/docs/agent-configuration/agents-md) |
| opencode | `~/.config/opencode/AGENTS.md`                                  | [Global rules](https://opencode.ai/docs/rules)                                      |
| Cursor   | User Rules in Settings → Customize → Rules; no file provisioned | [User Rules](https://cursor.com/docs/rules)                                         |

Codex also supports `AGENTS.override.md` and a custom `CODEX_HOME`; this installer
uses the default home path and does not alter overrides. Its `default.rules` link
is a separate command-approval policy, not an instruction file. Cursor file-based
user-global provisioning is unsupported/unverified by the official docs; the
`rules` step prints manual settings instructions without creating global files.
Project `.cursor/rules/` and repository `AGENTS.md` are separate scopes.

Older installs linked `~/.claude/AGENTS.md`, `~/.codex/CLAUDE.md`, and both filenames
under `~/.cursor/`. Install/sync leaves these existing links alone but creates no
new ones. `remove --target <target> --intent rules` still unlinks legacy links
pointing to this checkout only. Real files and foreign links are never removed,
even with `--force`. New native rule links refuse to replace real files without
`--force`.

## Editing and verification

- Edit `CLAUDE.md` only. Keep runtime-specific install guidance in target docs,
  not in the global prompt. The directory-source plugin explanation belongs in
  `docs/install/claude.md`, not in every project's instructions.
- Run `./scripts/sync.sh && ./scripts/validate.sh`; the opencode validator enforces
  the source/output budgets and rejects duplicated filename/runtime lists and
  personal graphify rules, with failing-case regression tests.
- Verify install placement using sandbox HOMEs, never by installing newly shipped
  rules into your real home directory.

The repo-root rules and `/ycc:init` templates have different scopes and are not
sources for this user-global prompt.
