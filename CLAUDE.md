# Claude Plugins - Project Instructions

## Overview

This repository ships the `ycc` Claude Code plugin from a single marketplace at
`.claude-plugin/marketplace.json`. `ycc` — Yandy's Claude Code bundle — covers
dev-focused workflows: planning, implementation, git, research, docs, and
orchestration. Source lives under `ycc/`; invoke skills as `/ycc:{skill}` and agents
as `subagent_type: "ycc:{agent}"`. `user-invocable: false` hides skills from Claude slash invocation.

The `ycc/` source tree is the single source of truth; it generates native
compatibility bundles for Cursor, Codex, and opencode:

- Cursor bundle: `.cursor-plugin/`
- Codex bundle: `.codex-plugin/ycc/`
- Codex custom agents: `.codex-plugin/agents/`
- opencode bundle: `.opencode-plugin/` (skills, agents, commands, AGENTS.md, opencode.json)
- Cross-tool skills bundle: `.agents-plugin/` (skills + `ycc-shared/` → `~/.agents/`; see `docs/install/agents.md`)

> Pre-2.0 versions shipped 9 separate `ycc` sub-plugins. 2.0.0 collapsed them into
> one `ycc` bundle so every ycc skill is reachable via the same `ycc:` namespace
> prefix. See `docs/plans/` for the consolidation plan.
>
> **2026-04 split**: the consulting/SI toolkit previously shipped here as `yci`
> was extracted into its own sibling repo
> [`yandy-r/claude-infra-plugins`](https://github.com/yandy-r/claude-infra-plugins).
> That plugin's customer-guard PreToolUse hook was fail-closing on every tool call
> in this (dev-only) workspace, which is wrong for a ycc development repo and
> correct for a customer-engagement repo. Two repos, two threat models — one
> hook posture each.

## Repository Layout

```
claude-plugins/
├── .claude-plugin/
│   └── marketplace.json      # single plugin entry (ycc)
├── .codex-plugin/            # Codex bundle
│   ├── agents/               # generated Codex custom agents
│   └── ycc/                  # generated Codex plugin root
├── .cursor-plugin/           # Cursor bundle
├── .opencode-plugin/         # opencode bundle
│   ├── skills/               # → ~/.config/opencode/skills/
│   ├── agents/               # → ~/.config/opencode/agents/
│   ├── commands/             # → ~/.config/opencode/commands/
│   ├── AGENTS.md             # opencode rules file
│   └── opencode.json         # schema + default model + MCP translation
├── .agents-plugin/           # cross-tool skills bundle
│   ├── skills/               # → ~/.agents/skills/
│   └── ycc-shared/           # → ~/.agents/ycc-shared/
├── ycc/                      # ycc plugin source (dev workflows)
│   ├── .claude-plugin/
│   │   └── plugin.json       # name: "ycc", version bumped by /ycc:bundle-release
│   ├── mods/                 # Claude Code mods + their own 'ycc-mods' marketplace
│   ├── agents/               # agents (one .md per agent)
│   └── skills/
│       ├── _shared/          # cross-skill helper scripts
│       └── {skill-name}/
│           ├── SKILL.md      # skill prompt (required)
│           ├── references/   # templates, examples, reference docs
│           └── scripts/      # validation and helper scripts
└── docs/
    ├── plans/                # implementation plans
    └── prps/                 # product requirements documents, specs, reports, reviews
```

## Plugin Development Conventions

### Naming

- The plugin namespace `ycc:` is stable and must NOT change.
- Skills: `kebab-case` directory under `ycc/skills/`. The directory name becomes
  the skill identifier within the `ycc:` namespace (e.g., `ycc/skills/git-workflow/`
  → `ycc:git-workflow`).
- Public skills are native Claude slash invocations; `user-invocable: false` hides
  passive skills from the slash menu.
- Agents: `kebab-case.md` under `ycc/agents/`. The basename becomes the agent
  identifier (e.g., `ycc/agents/codebase-advisor.md` → `subagent_type: "ycc:codebase-advisor"`).
- Scripts: `kebab-case.sh` with bash shebang.

### Scripts

All scripts must:

- Start with `#!/usr/bin/env bash`
- Use `set -euo pipefail` for safety
- Include validation guards (check required inputs exist)
- Exit with meaningful codes (0 = success, 1 = error)
- Write output to stdout, errors to stderr

When a script needs to reference its own plugin path, use `${CLAUDE_PLUGIN_ROOT}` —
this resolves to the plugin's source directory at runtime (`ycc/`). Paths inside
skills follow the form `${CLAUDE_PLUGIN_ROOT}/skills/{skill-name}/...`.

Codex-generated skills are not source-edited directly. The Codex generator rewrites
those paths to the managed install location `~/.codex/plugins/ycc/...`.

### Skills

Each skill directory contains:

- `SKILL.md` — the skill prompt (required)
- `references/` — templates, examples, and reference docs
- `scripts/` — validation and helper scripts

### Cross-skill helpers

Shared helpers (used by more than one skill) live under `ycc/skills/_shared/scripts/`.
Skills source them via `${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/{name}.sh`.

### Registration

The marketplace registry at `.claude-plugin/marketplace.json` contains a single
entry: `ycc`. Adding a second plugin to this repo is NOT on the roadmap — the
2026-04 split of `yci` into
[`yandy-r/claude-infra-plugins`](https://github.com/yandy-r/claude-infra-plugins)
is the reference precedent: when scope cannot coexist with ycc without harming
it (cross-contamination, descriptor pollution, fragility-cliff proximity),
split into a sibling repo rather than accumulate plugins here. See
`CONTRIBUTING.md` → Scope & Guardrails for the full decision gate.

### Mods (`ycc/mods/`)

Claude Code mods (plugins with a `hooks/hooks.json` `modules` entry) live under
`ycc/mods/<name>/`, one complete plugin per folder, listed in their own local
marketplace `ycc/mods/.claude-plugin/marketplace.json` (`ycc-mods`). This is the
one deliberate exception to the single-entry rule above: mods are small,
independently toggled UI/behavior add-ons, not a second workflow bundle, and
the ycc generators never read `ycc/mods/`. `ycc sync --target claude --intent
mods` installs them; other targets report the intent as unsupported until a
translator step exists. Validate with `./scripts/validate.sh --only mods`. See
[`ycc/mods/README.md`](ycc/mods/README.md).

### Local install model (directory-source, in-place)

This repo's `ycc` marketplace is registered as a **`directory` source**, so Claude
Code loads it **in place** from the repo — it never copies the plugin into
`~/.claude/plugins/cache/`. A missing `~/.claude/plugins/cache/ycc/ycc/<version>` is
**expected, not breakage**; the `installPath` in `installed_plugins.json` is a nominal
record for directory sources. Install health is proven by `ycc:` skills and agents being
available in-session, not by cache presence. When an agent needs to read plugin content,
read source at `ycc/skills/{skill}/SKILL.md` and `ycc/agents/` — **not** the cache
or generated `.opencode-plugin/` mirror. `${CLAUDE_PLUGIN_ROOT}` resolves to
`…/claude-plugins/ycc` at runtime.

## Generated Compatibility Targets

- `ycc/skills/` is the source of truth for Cursor, Codex, and opencode skill generation.
- `ycc/agents/` is the source of truth for Cursor, Codex, and opencode agent generation.
- Claude slash invocation comes from public skills. opencode retains generated thin native
  commands sourced from public skill `SKILL.md` files for commands-only installs; command
  bodies load the skill through the skill tool, not command recursion.
- Do not hand-edit generated files under `.cursor-plugin/`, `.codex-plugin/`, or
  `.opencode-plugin/` unless you are first changing the generator.
- Codex does not support this repo's custom slash-command layer as installable artifacts.
  The native Codex target exposes skills via the plugin bundle and agents via TOML files.
- opencode has first-class support for skills, agents, AND commands. The opencode bundle
  ships all three, plus an `opencode.json` config (with MCP translated from
  `mcp-configs/mcp.json`) and an `AGENTS.md` rules file derived from this document.
- See [`ycc/skills/_shared/references/target-capability-matrix.md`](ycc/skills/_shared/references/target-capability-matrix.md)
  for the authoritative per-target capability table.

## Testing Changes

After modifying anything under `ycc/`:

1. Validate JSON with `python3 -m json.tool`:
   - `python3 -m json.tool .claude-plugin/marketplace.json`
   - `python3 -m json.tool ycc/.claude-plugin/plugin.json`
2. Verify all `${CLAUDE_PLUGIN_ROOT}` paths resolve (no broken references).
3. Confirm shell scripts remain executable:
   `find ycc/skills -name "*.sh" -not -executable` (should output nothing).
4. Test the skill or agent in a live Claude Code session via its `ycc:` prefix.

If you changed `ycc/skills/` or `ycc/agents/`, also regenerate and
validate the compatibility bundles (Cursor / Codex / opencode). When adding, renaming,
or removing an agent under `ycc/agents/`, you **must** also add or update its entry in
`ycc/settings/models.json` under `targets.opencode.agents` mapped to an appropriate model
tier (`openai/gpt-6-astra` for deep architecture/high-risk, `openai/gpt-5.6-terra` for docs/lookup/routine,
`openai/gpt-5.6-sol` default). The generator `scripts/generate_opencode_plugin.py` fails fast
if any agent is missing.

The recommended pair is the unified entrypoints:

```bash
./scripts/sync.sh         # regenerate every compatibility bundle
./scripts/validate.sh     # run every validator (this is what CI runs)
```

Both accept `--only <targets>` with comma-separated values (`inventory, cursor, codex,
opencode, json`). The individual generator / validator scripts are still available
for targeted iteration:

1. Codex:
   - `./scripts/generate-codex-skills.sh`
   - `./scripts/generate-codex-agents.sh`
   - `./scripts/generate-codex-plugin.sh`
   - `./scripts/validate-codex-skills.sh`
   - `./scripts/validate-codex-agents.sh`
   - `./scripts/validate-codex-plugin.sh`
2. Cursor:
   - `./scripts/generate-cursor-skills.sh`
   - `./scripts/generate-cursor-agents.sh`
   - `./scripts/generate-cursor-rules.sh`
   - `./scripts/validate-cursor-skills.sh`
   - `./scripts/validate-cursor-agents.sh`
   - `./scripts/validate-cursor-rules.sh`
3. opencode:
   - `./scripts/generate-opencode-skills.sh`
   - `./scripts/generate-opencode-agents.sh`
   - `./scripts/generate-opencode-commands.sh`
   - `./scripts/generate-opencode-plugin.sh`
   - `./scripts/validate-opencode-skills.sh`
   - `./scripts/validate-opencode-agents.sh`
   - `./scripts/validate-opencode-commands.sh`
   - `./scripts/validate-opencode-plugin.sh`

## Precedence

1. System, developer, and explicit user instructions for the task.
2. This file and [`AGENTS.md`](AGENTS.md) as repo policy.
3. General best practices when nothing above conflicts.

## MUST / MUST NOT

- **Secrets**: **Never** commit `.env`, `.env.encrypted`, tokens, or API keys.
- **Issues**: Use the YAML form templates under `.github/ISSUE_TEMPLATE/` when present. **Do not** create title-only or template-bypass issues. If `gh issue create --template` fails, create the issue via GitHub API/tooling with a body that mirrors the form fields, then apply correct labels — **not** a vague one-liner.
- **Pull requests**: Follow `.github/pull_request_template.md` when present. **Always** link the related issue (`Closes #…`). **Label** PRs using the project taxonomy — **never** invent ad-hoc labels.
- **Commits**: Use **Conventional Commits 1.0.0** — `feat|fix|docs|refactor|perf|test|build|ci|chore(scope): …`. Write the title as you want it to appear in `CHANGELOG.md`.
- **Internal docs commits**: Files under `docs/plans`, `docs/research`, or `docs/internal` **must** use `docs(internal): …`. Other non-user-facing churn: prefer `chore(…): …` to stay out of release notes.
- **Large features**: Split into smaller phases and tasks with clear dependencies and order of execution.
- **File size (~500 lines)**: Aim for **around 500 lines** per file as a soft cap. Files that drift meaningfully past that **must** be refactored into smaller modules unless the content is inherently contiguous (generated code, schemas, large test fixtures). The intent is maintainability, not a hard ceiling.
- **Modularity & reuse**: Code **must** decompose into small, cohesive units — submodules, libraries, or reusable components — with a clear public surface and minimal cross-module coupling. **No copy-paste duplication** (DRY): extract shared logic into a shared module. Prefer composition over inheritance. Avoid circular dependencies.
- **Single responsibility**: Each function, module, and component **must** have one clear reason to exist. Split when a unit grows more than one responsibility.
- **MCP**: When an MCP server fits the task (GitHub, docs, browser, etc.), **prefer it**. **Read** each tool's schema/descriptor before calling.

## SHOULD (implementation)

### General

- **Naming**: Intention-revealing names for functions, types, and modules. Public APIs should read like documentation.
- **No dead code**: Remove unused code, imports, and commented-out blocks. Git preserves history.
- **Dependency hygiene**: Before adding a new dependency, check whether an existing one does the job. New deps need a justification (maintenance cost, license, security).
- **Fail fast at boundaries**: Validate inputs at module and system boundaries; propagate via typed errors. Never silently swallow errors.
- **Tests alongside changes**: New or modified behavior ships with tests in the same change.
- **Default to worktrees**: For non-trivial work (multi-step features, refactors, changes touching multiple files), start in a git worktree instead of the main checkout. See [Git Worktrees](#git-worktrees) below. Fall back to the main checkout only when the task is a one-liner, must observe the current working tree state, or worktree creation is blocked (detached HEAD, shallow clone, submodule issues).

### Languages

- **Python** (`scripts/generate_*.py`): PEP 8 throughout; type hints required on all public API signatures; prefer `ruff` for linting and `mypy --strict` for type checking.
- **Shell** (`scripts/*.sh`, `ycc/skills/*/scripts/*.sh`): `#!/usr/bin/env bash` + `set -euo pipefail`; validation guards on required inputs; stdout for results, stderr for errors; exit 0 on success, 1 on error.

## Git & Conventional Commits

This project uses **Conventional Commits 1.0.0**. Every commit title must match:

```
<type>[optional scope]: <description>
```

### Types

| Type       | Purpose                                     | Version bump |
| ---------- | ------------------------------------------- | ------------ |
| `feat`     | New user-facing feature                     | minor        |
| `fix`      | User-facing bug fix                         | patch        |
| `docs`     | Documentation only                          | —            |
| `refactor` | Code change that is neither fix nor feature | —            |
| `perf`     | Performance improvement                     | —            |
| `test`     | Adding or correcting tests                  | —            |
| `build`    | Build system or external dependency changes | —            |
| `ci`       | CI/CD configuration changes                 | —            |
| `chore`    | Other non-user-facing changes               | —            |
| `style`    | Formatting/whitespace only                  | —            |

### Scope

`feat(auth): …` — scope is the module, crate, package, or area of change. Keep it concise.

### Breaking changes

Append `!` after the type/scope (`feat!: …`) **or** add a `BREAKING CHANGE: …` footer. Either triggers a major version bump.

### Internal docs

Use `docs(internal): …` for files under `docs/plans`, `docs/research`, or `docs/internal`. These stay out of release notes.

## Git Worktrees

**Strong preference**: work in a git worktree for any non-trivial task. Worktrees keep the main checkout clean for parallel work, let multiple agents run concurrently without stepping on each other, and make it trivial to abandon a failed attempt (`git worktree remove`). Use the main checkout only when the task is a one-liner, requires observing the current working tree state, or worktree creation is blocked.

The Claude Code harness defaults to creating worktrees inside the current repo at `<repo>/.claude/worktrees/`. That location pollutes the working tree, shows up in `git status` of unrelated repos, and is easy to forget and hard to reap.

- **Preferred parent**: `~/.claude-worktrees/` for all agent-managed worktrees, named `<repo>-<branch>/`. Keeps them outside every repo and trivially bulk-clean.
- **Manual creation**: when invoking `git worktree add` yourself, target `~/.claude-worktrees/<repo>-<branch>/` — never a path inside the current repo.
- **Harness-created worktrees** (`isolation: "worktree"`, `EnterWorktree`): the only way to relocate these is a `WorktreeCreate` hook in `~/.claude/settings.json`. No environment variable or settings key controls the parent directory directly — the hook receives the intended path and returns a replacement path.
- **Repo hygiene**: if the harness has already created `<repo>/.claude/worktrees/`, add `.claude/worktrees/` to `.gitignore` before committing.

## GitHub Workflow

- **Labels**: Use only the project's defined label taxonomy (`type:`, `area:`, `priority:`, `status:` families). Never create ad-hoc labels.
- **Issues**: File an issue before starting non-trivial work. Link the issue number in the PR (`Closes #…`).
- **PRs**: Follow the PR template; fill every checklist item honestly. Small, focused PRs over large omnibus ones.

## Stack Overview

| Layer            | Technology                   | Notes                                                      |
| ---------------- | ---------------------------- | ---------------------------------------------------------- |
| Primary language | **mixed** (Shell + Markdown) | Plugin source under `ycc/`                                 |
| Generators       | Python 3                     | `scripts/generate_*.py` emit Cursor/Codex/opencode bundles |
| Helper scripts   | Bash                         | `scripts/lint.sh`, `scripts/format.sh`                     |
| Package manager  | npm                          | Drives lint/format only — no test or build target          |

## Commands

```bash
# One-time: install pinned shellcheck (matches scripts/lib/shellcheck-version.sh; same binary as CI)
./scripts/install-shellcheck.sh

# Lint (Python + Shell)
npm run lint              # or: scripts/lint.sh --python --shell
npm run lint:modified     # only files changed vs. git HEAD
npm run lint:fix          # auto-apply fixes

# Format
npm run format            # Python + docs
npm run format:modified   # only modified files
```

New projects should bootstrap this same lint/format environment via `/ycc:formatters` (or `/ycc:init --formatters`), which installs the `scripts/style.sh` bundle, tool configs, aliases, and docs into the target repo.

Testing and validation are defined in `## Testing Changes` above — JSON validation plus the Codex/Cursor/opencode generate-and-validate pipelines are the real verification loop for this repository.

## Branching & releases

[`RELEASING.md`](RELEASING.md) is the source of truth for branches and releases. Branch
off `main` and PR back into it; every release is tagged from `main`. Never merge one
long-lived branch into another to sync it.
