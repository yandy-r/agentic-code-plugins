# ystack

Workspace for the `ycc` Claude Code plugin — source of truth for skills, commands, and agents, with generators for Cursor and Codex compatibility bundles.

Full agent rules live in [`CLAUDE.md`](../../CLAUDE.md). Key points surfaced for AI tooling:

## Rules

- Follow Conventional Commits for every commit: `feat|fix|docs|refactor|perf|test|build|ci|chore(scope): …`.
- Never commit `.env` / secrets / tokens.
- Use `.github/ISSUE_TEMPLATE/*.yml` when present; link `Closes #…` in every PR.
- TypeScript / JavaScript: strict mode enabled, `PascalCase` components, `camelCase` hooks/functions, prefer `unknown` over `any`.
- Python: PEP 8, type hints on all public API signatures, `ruff` + `mypy --strict`.

## Repository-specific

This repository's source of truth is the Claude-facing `ycc/` tree.

- Add new workflow logic under `ycc/`, not under `.cursor-plugin/` or `.codex-plugin/`.
- Treat `.cursor-plugin/` and `.codex-plugin/` as generated outputs unless you are changing the generators themselves.
- After changing `ycc/skills/` or `ycc/agents/`, run the Codex and Cursor generators plus their validators.
- Keep the plugin name `ycc` stable across all targets.
- Do not introduce new top-level plugins; extend the existing `ycc` bundle.

## Verification

Run `npm test` and `npm run lint` before marking work complete.
