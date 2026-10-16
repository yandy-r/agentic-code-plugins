<!-- Generated from ycc/settings/rules/CLAUDE.md by scripts/generate_opencode_plugin.py — do not edit by hand. -->

# Agent Rules (User-Global)

These are cross-project defaults. System, developer, and explicit task instructions
come first; the current project's rules override these defaults.

## Changes and verification

- Before claiming completion, run the relevant project checks and show evidence;
  name any checks skipped or blocked rather than implying they passed.
- Prefer an available MCP server that fits the task; read its tool schema first.
- Aim for a soft cap of about 500 lines per file. Split files that grow meaningfully
  beyond it, except inherently contiguous generated code, schemas, or fixtures.

## Git and collaboration

- Never commit `.env`, `.env.encrypted`, tokens, or API keys.
- Use Conventional Commits 1.0.0: `<type>[optional scope]: <description>`;
  write the title as it should appear in release notes.
- For changes confined to `docs/plans`, `docs/research`, or `docs/internal`, use
  `docs(internal): …`; prefer `chore(…): …` for other non-user-facing churn.
- Use the repository's issue and PR templates when present. If tooling cannot submit
  a YAML issue form, mirror its fields in the issue body instead of bypassing it.
- Link related issues in PRs (`Closes #…` when appropriate) and use only the
  repository's defined label taxonomy; do not invent labels.

## Worktrees

- Prefer a git worktree for non-trivial work. Use the main checkout only for a
  one-line change, when the task needs its current state, or when creation is blocked.
- Create skill-managed worktrees inside the repository: Claude uses
  `.claude/worktrees/`, opencode `.opencode/worktrees/`, Codex `.codex/worktrees/`,
  and Cursor `.cursor/worktrees/`. Portable cross-agent installs detect the runtime
  conservatively and fall back to `.agents/worktrees/`. Name each `<repo>-<branch>/`.
  `YCC_WORKTREE_ROOT` is the explicit override. Native harness features may use
  different roots; do not redirect them to a path the harness cannot enter.
- Add every runtime worktree root to `.gitignore` before committing.
