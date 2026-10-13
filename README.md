# claude-plugins

A single Claude Code plugin (`ycc`) bundling workflow orchestration, parallel planning, documentation, research, and project management. The repository also generates native compatibility bundles for Cursor, Codex, and opencode.

> **2.0.0 breaking change.** Versions ≤ 1.x shipped 9 separate plugins (`ask`, `plan-workflow`, `git-workflow`, `implement-plan`, `code-report`, `deep-research`, `orchestrate`, `write-docs`, `project`). 2.0.0 collapses all of them into a single `ycc` plugin so every skill is accessible via `ycc:{skill}`. Re-install after upgrading.

> **Migration: `/ycc:ask` and `ycc:ask` retired.** For read-only codebase questions, ask the main session to delegate to `ycc:codebase-advisor`. Request explicit search gaps, assumptions, and analyzed/skipped scope in the answer. Request implementation separately.

## What's inside

<!-- BEGIN:GENERATED-COUNTS -->

The source plugin ships **49 skills**, **49 slash-invocable skills**, and **55 agents**.

<!-- END:GENERATED-COUNTS -->

<!-- BEGIN:GENERATED-COMMANDS -->

| Command / Skill            | Purpose                                                                                                                                                                                 |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/ycc:backport`            | Cherry-pick merged trunk PRs onto active maintenance branches (release/X.Y) and open one backport PR per target — driven by the project's RELEASING.md release-branches model and it... |
| `/ycc:blueprint`           | Interactive, whole-project source-of-truth spec generator.                                                                                                                              |
| `/ycc:bundle-author`       | Maintainer-only (ycc repo) — This skill should be used when the user asks to "scaffold a new ycc skill", "add a skill to the bundle", "extend ycc", "add an agent to ycc", or when t... |
| `/ycc:bundle-release`      | Maintainer-only (ycc repo) — This skill should be used when the user asks to "release ycc", "bump ycc version", "prepare a ycc release", "cut a new ycc release", "tag a ycc release... |
| `/ycc:clean`               | This skill should be used when the user asks to "clean project files", "remove unnecessary files", "clean up project", "find unused files", "project cleanup", or mentions removing...  |
| `/ycc:code-report`         | Generate structured implementation reports documenting changes made during plan execution.                                                                                              |
| `/ycc:code-review`         | Dual-mode code review — local uncommitted changes or a GitHub PR.                                                                                                                       |
| `/ycc:compatibility-audit` | Maintainer-only (ycc repo) — This skill should be used when the user asks to "audit ycc compatibility", "check Cursor/Codex bundle health", "verify cross-target parity", "run a com... |
| `/ycc:deep-research`       | Conduct strategic multi-perspective research using the Asymmetric Research Squad methodology with 8 specialized personas.                                                               |
| `/ycc:feature-research`    | Run the 7-agent research pipeline for a new feature — deploys api-researcher, business-analyzer, tech-designer, ux-researcher, security-researcher, practices-researcher, and recomm... |
| `/ycc:formatters`          | Use this skill when the user asks to "initialize formatters", "bootstrap linting", "add lint and format scripts", "set up prettier / biome / ruff / clippy / golangci-lint / shellch... |
| `/ycc:frontend-design`     | Create distinctive, production-grade frontend interfaces with intentional visual direction — typography, color, spacing rhythm, layout composition, motion, and atmosphere.             |
| `/ycc:frontend-patterns`   | Frontend patterns for React and Next.js — composition, compound components, render props, custom hooks, state management with Context+useReducer, data fetching, performance optimiz... |
| `/ycc:git-cleanup`         | This skill should be used when the user asks to "clean up git", "prune stale branches", "clean up worktrees", "close stale PRs/issues", "tidy up my repo", or mentions removing aban... |
| `/ycc:git-workflow`        | Git commit and documentation workflow manager.                                                                                                                                          |
| `/ycc:go-patterns`         | Idiomatic Go patterns, best practices, and conventions for building robust, efficient, and maintainable Go applications.                                                                |
| `/ycc:go-testing`          | Go testing patterns including table-driven tests, subtests, benchmarks, fuzzing, and test coverage.                                                                                     |
| `/ycc:hooks-workflow`      | Convert rule-file hook guidance into target-appropriate config.                                                                                                                         |
| `/ycc:implement-plan`      | Execute a parallel implementation plan by deploying implementor agents in dependency-resolved batches.                                                                                  |
| `/ycc:init`                | This skill should be used when the user asks to "initialize workspace", "init project", "bootstrap CLAUDE.md", "generate AGENTS.md", "set up cursor rules", "add github issue templa... |
| `/ycc:orchestrate`         | Orchestrate multiple specialized agents in parallel to accomplish complex tasks.                                                                                                        |
| `/ycc:parallel-plan`       | Create detailed parallel implementation plans (alias for plan-workflow plan-only).                                                                                                      |
| `/ycc:plan`                | Lightweight conversational planner — dispatches ycc:planner (or a multi-perspective fan-out) to produce a phased plan with file paths, dependencies, risks, and tests, then WAITS fo... |
| `/ycc:plan-workflow`       | Unified planning workflow - research, analyze, and generate parallel implementation plans in one command.                                                                               |
| `/ycc:pr-autofix`          | Vendor-neutral PR comment auto-fix — discover every review thread, file-level review comment, and top-level PR comment from any author (bot or human), dispatch per-comment fix agen... |
| `/ycc:prp-commit`          | Lightweight natural-language git commit helper.                                                                                                                                         |
| `/ycc:prp-implement`       | Execute a PRP plan file with per-task validation loops.                                                                                                                                 |
| `/ycc:prp-plan`            | Create a self-contained feature implementation plan with codebase pattern extraction and optional external research.                                                                    |
| `/ycc:prp-pr`              | Create a GitHub pull request from the current branch — validates preconditions, discovers PR templates, analyzes commits and file diffs, references PRP artifacts (prds/plans/report... |
| `/ycc:prp-prd`             | Interactive, problem-first PRD generator that runs an iterative questioning workflow — Foundation → Market Grounding → Vision → Technical Feasibility → Decisions → Generate.           |
| `/ycc:prp-spec`            | Generate a lightweight feature spec for the PRP workflow — single-pass with optional codebase/market grounding via ycc:prp-researcher.                                                  |
| `/ycc:python-patterns`     | Idiomatic Python patterns, PEP 8 conventions, type hints, dataclasses, context managers, decorators, and best practices for building robust, maintainable Python applications.          |
| `/ycc:python-testing`      | Python testing patterns using pytest — TDD methodology, fixtures (function/module/session scopes), parametrization, markers, mocking with unittest.mock, async tests with pytest-asy... |
| `/ycc:quick-fix`           | Apply fixes directly from an inline /ycc:quick-review findings block without creating a review artifact.                                                                                |
| `/ycc:quick-review`        | Fast interactive review of uncommitted changes — prints findings inline, writes nothing by default.                                                                                     |
| `/ycc:release-model`       | This skill should be used when the user asks to "create a RELEASING.md", "set up a branching model", "define a release process", "document how we branch and release", "add release...  |
| `/ycc:releaser`            | This skill should be used when the user asks to "prepare a release", "cut a release", "tag a release", "create a GitHub release", "draft release notes", "set up release CI", "add a... |
| `/ycc:research-to-issues`  | This skill should be used when the user asks to "create issues from research", "turn research into GitHub issues", "create issues from feature spec", "turn plan into issues", "issu... |
| `/ycc:resume-session`      | Load the most recent session file from ~/.claude/session-data/ (or a specified one by date or path) and produce a structured briefing of what was built, what worked, what NOT to re... |
| `/ycc:review-fix`          | Plan and apply fixes for findings in a /ycc:code-review artifact.                                                                                                                       |
| `/ycc:rust-patterns`       | Idiomatic Rust patterns, ownership, error handling, traits, concurrency, and best practices for building safe, performant applications.                                                 |
| `/ycc:rust-testing`        | Rust testing patterns including unit tests, integration tests, async testing, property-based testing, mocking, and coverage.                                                            |
| `/ycc:save-session`        | Capture the current session state — what was built, what worked, what failed, open questions, and exact next step — to a dated file at ~/.claude/session-data/YYYY-MM-DD-{shortid}-s... |
| `/ycc:shared-context`      | Create shared context documentation for a feature (alias for plan-workflow research-only).                                                                                              |
| `/ycc:ts-patterns`         | Idiomatic TypeScript patterns — strict type system, discriminated unions, generic inference, `satisfies`, branded types, errors as values, ESM/CJS modules with `exports` maps, Prom... |
| `/ycc:ts-testing`          | TypeScript testing patterns using Vitest as the primary runner — TDD workflow, unit tests, integration tests, async tests with fake timers, parameterized tests via `test.each`, pro... |
| `/ycc:visual-plan`         | Turn an existing text plan into a rich, interactive visual plan — diagrams, file maps, annotated code, open questions, and an optional UI/prototype review surface.                     |
| `/ycc:visual-recap`        | Turn a finished change — a git range, branch, or tracked working-tree diff — into a LOCAL-ONLY interactive visual recap (annotated diffs, file map, schema/API deltas, diagrams, wir... |
| `/ycc:write-docs`          | Orchestrate 5 specialized documentation agents in parallel to analyze codebase and create comprehensive documentation.                                                                  |

<!-- END:GENERATED-COMMANDS -->

### Maintainer-only workflows

`/ycc:bundle-author`, `/ycc:bundle-release`, and `/ycc:compatibility-audit`
are maintainer-only workflows for this repo's layout. General users can ignore
them — they are not general-purpose tooling. They stay shipped in the single
`ycc` plugin (not excluded from generated targets): `/ycc:bundle-release` backs
the release flow in [RELEASING.md](RELEASING.md), and the other two stay for
single-plugin parity rather than because scripts import them.

### Agents

<!-- BEGIN:GENERATED-AGENTS -->

The plugin bundles **55** specialized agents covering codebase analysis, language experts (Go, Rust, Python, TypeScript), reviewers, planners, documenters, and infrastructure architects.

<details>
<summary>Full agent list (55 agents, grouped by role)</summary>

- **Language experts & implementors** (12): `frontend-ui-developer`, `go-api-architect`, `go-expert-architect`, `nextjs-ux-ui-expert`, `nodejs-backend-architect`, `nodejs-backend-developer`, `python-developer`, `python-expert-architect`, `rust-build-resolver`, `rust-expert-architect`, `typescript-developer`, `typescript-expert-architect`
- **Code review & quality** (7): `backport-conflict-resolver`, `code-reviewer`, `code-simplifier`, `pr-comment-fixer`, `release-fix-applier`, `review-fixer`, `rust-reviewer`
- **Research & discovery** (10): `code-explorer`, `code-finder`, `code-researcher`, `codebase-advisor`, `feature-researcher`, `library-docs-writer`, `practices-researcher`, `prp-researcher`, `research-specialist`, `root-cause-analyzer`
- **Architecture & planning** (5): `architect`, `architecture-analyst`, `code-architect`, `planner`, `test-strategy-planner`
- **Documentation** (7): `api-docs-expert`, `api-documenter`, `code-documenter`, `docs-git-committer`, `documentation-writer`, `feature-writer`, `readme-generator`
- **Infrastructure & DevOps** (7): `ansible-automation-expert`, `cloudflare-architect`, `cloudflare-developer`, `reverse-proxy-architect`, `systems-engineering-expert`, `terraform-architect`, `terraform-developer`
- **Databases** (3): `db-modifier`, `sql-database-developer`, `turso-database-architect`
- **Workflow utilities** (4): `git-cleanup`, `implementor`, `project-file-cleaner`, `releaser`

</details>

<!-- END:GENERATED-AGENTS -->

- **Claude Code:** reference any of them via `subagent_type: "ycc:{agent-name}"`. Canonical source lives in [`ycc/agents/`](ycc/agents/).
- **Cursor:** generated, Cursor-native copies live in [`.cursor-plugin/agents/`](.cursor-plugin/agents/) (produced from `ycc/agents/` — see the [Cursor install guide](docs/install/cursor.md)).
- **Codex:** generated, Codex-native custom-agent TOMLs live in [`.codex-plugin/agents/`](.codex-plugin/agents/) (produced from `ycc/agents/` — see the [Codex install guide](docs/install/codex.md)).
- **opencode:** generated, opencode-native agent markdown files live in [`.opencode-plugin/agents/`](.opencode-plugin/agents/) (produced from `ycc/agents/` — see the [opencode install guide](docs/install/opencode.md)). Invoke via `@agent-name` or the native v2 `subagent` tool.

**Contributing:** before proposing a new skill or agent, read the Scope & Guardrails policy in [`CONTRIBUTING.md`](CONTRIBUTING.md#scope--guardrails).

- **Credits:** `ycc:visual-plan` and `ycc:visual-recap` are adapted from [BuilderIO/skills](https://github.com/BuilderIO/skills).

## Installation

For Claude Code, install the published `ycc` plugin from the marketplace:

```bash
# Add the marketplace
/plugin marketplace add yandy-r/claude-plugins

# Install the bundle
/plugin install ycc@ycc
```

Or enable in `~/.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "ycc@ycc": true
  }
}
```

For local development installs, generated compatibility bundles, model defaults,
and desktop app notes, use the dedicated install guides. Recommended sync form:

```bash
./install.sh sync --target claude --intent hooks,settings,mcp,plugins
./install.sh sync --target claude --intent mods                          # Claude Code mods (ycc/mods)
./install.sh sync --target all --intent settings,rules
./install.sh install --target all --only agents                         # standalone agents, no plugin
./install.sh sync --target codex,claude,opencode --intent mcp            # current project
./install.sh sync --target codex,claude,opencode --intent mcp --global   # user-global
./install.sh sync --target opencode --intent mcp --mcps github,linear    # only these servers
./install.sh list-mcps                                                   # managed MCP server names
./install.sh remove --target all --only mcp                              # undo project MCP
./install.sh remove --target all --intent settings,rules                 # undo any intent, any target
./install.sh cli && ycc completion --install                             # `ycc` on PATH for other projects
```

The `mcp` step defaults to the current project; pass `--global` for user-global
config. `base` ships a target's whole bundle (the `ycc` plugin for Claude and
Codex). `skills`, `agents` and `commands` instead install standalone entries,
one per skill/agent/command, into each tool's own directories
(`~/.claude/skills/<name>`, `~/.codex/agents/<name>.toml`, ...) with no plugin.
On Claude, `commands` is an alias for `skills` (skills are the slash commands);
your own entries there are never touched. `remove` undoes any intent on any target
(`base`, `skills`, `agents`, `commands`, `settings`, `rules`, `mcp`, `hooks`,
`plugins`, `mods`), taking back only what the installer owns and leaving your
own keys, files and servers alone. See
[Project Vs Global Scope](docs/install/README.md#project-vs-global-scope).

`--target` takes a comma-separated list (or `all`); every target is validated
before any of them runs.

Structured config is merged rather than copied: repo-managed keys update while
unknown and locally edited keys remain intact. First-time setup uses `install`
(`./install.sh install --target <t> [--settings --rules --mcp --hooks]`); every
invocation needs a command — a bare `--target ...` is rejected.

Dedicated guides:

| Runtime                      | Install guide                                          |
| ---------------------------- | ------------------------------------------------------ |
| Claude Code / Claude Desktop | [`docs/install/claude.md`](docs/install/claude.md)     |
| Cursor                       | [`docs/install/cursor.md`](docs/install/cursor.md)     |
| Codex / Codex Desktop        | [`docs/install/codex.md`](docs/install/codex.md)       |
| opencode                     | [`docs/install/opencode.md`](docs/install/opencode.md) |
| `~/.agents/skills` (Zed etc) | [`docs/install/agents.md`](docs/install/agents.md)     |
| Shared installer concepts    | [`docs/install/README.md`](docs/install/README.md)     |

## Workflow composition

The planning skills compose into a pipeline:

```
ycc:feature-research → ycc:shared-context → ycc:parallel-plan → ycc:implement-plan → ycc:code-report → ycc:git-workflow
   (research)            (gather files)       (design tasks)      (deploy agents)      (document)         (commit/PR)
```

Use `ycc:plan-workflow` to run the full pipeline, or invoke individual stages. `ycc:shared-context` and `ycc:parallel-plan` are thin aliases over `ycc:plan-workflow --research-only` and `--plan-only` respectively; the pipeline and its artifacts are unchanged.

## Development Sync

This repository maintains generated compatibility trees under **`.cursor-plugin/`**,
**`.codex-plugin/`**, and **`.opencode-plugin/`**. The canonical source of truth
is the Claude-facing [`ycc/`](ycc/) tree.

Regenerate and validate derived artifacts with:

```bash
./scripts/sync.sh        # regenerate inventory and compatibility bundles
./scripts/validate.sh    # run every validator; CI runs this on push and PR
```

Both accept `--only <targets>` with comma-separated values. Valid targets:

- `inventory` — `docs/inventory.json` and the `GENERATED-*` regions of `README.md`
- `cursor` — `.cursor-plugin/` agents, skills, and rules
- `codex` — `.codex-plugin/` skills, agents, and plugin metadata
- `opencode` — `.opencode-plugin/` skills, agents, commands, and plugin metadata (opencode.json + AGENTS.md)
- `agents` — `.agents-plugin/` cross-tool skills for `~/.agents/skills` (+ `ycc-shared/`)
- `json` — JSON-lint `.claude-plugin/marketplace.json` and `ycc/.claude-plugin/plugin.json` (validate only)

Examples:

```bash
./scripts/sync.sh --only inventory
./scripts/validate.sh --only cursor,codex,opencode
./scripts/sync.sh --only opencode
```

CI runs `./scripts/validate.sh` via [`.github/workflows/validate.yml`](.github/workflows/validate.yml) and fails the job on any generated drift, so local and CI paths are identical.

### OpenCode Per-Agent Model Policy

`ycc/settings/models.json` owns OpenCode model policy. Every `ycc/agents/*.md`
basename, plus built-in `general` and `explore`, must have a full `provider/model`
entry in `targets.opencode.agents`. Select by intended capability: deep architecture
or high-risk work uses `openai/gpt-6-astra`; docs, lookup, and routine work uses
`openai/gpt-5.6-terra`; all other agents use `openai/gpt-5.6-sol`. These are
placeholders (`placeholder: true`); users choose available provider models by
capability and cost. `opencode.json` owns assignments; generated agent Markdown
stays model-free. Update this mapping whenever an agent is added, renamed, or
removed, then run `./scripts/sync.sh` and `./scripts/validate.sh`.

## Repository layout

```
claude-plugins/
├── .claude-plugin/
│   └── marketplace.json     # marketplace registry (single ycc entry)
├── .agents/
│   └── plugins/
│       └── marketplace.json # repo-local Codex marketplace source
├── .codex-plugin/
│   ├── agents/              # generated Codex custom agents (.toml)
│   └── ycc/                 # generated Codex plugin root
│       ├── .codex-plugin/
│       │   └── plugin.json
│       ├── .mcp.json
│       ├── shared/
│       └── skills/
├── .cursor-plugin/            # Cursor IDE bundle (synced by install.sh install --target cursor)
│   ├── agents/                # generated from ycc/agents (run scripts/generate-cursor-agents.sh)
│   ├── rules/                 # generated from ycc/rules (run scripts/generate-cursor-rules.sh)
│   └── skills/                # generated from ycc/skills (run scripts/generate-cursor-skills.sh)
├── .opencode-plugin/          # opencode bundle (synced by install.sh install --target opencode)
│   ├── agents/                # generated from ycc/agents
│   ├── commands/              # generated from public ycc/skills (thin, skill-tool dispatch)
│   ├── skills/                # generated from ycc/skills
│   ├── shared/                # generated from ycc/skills/_shared
│   ├── AGENTS.md              # generated rules file (transformed from CLAUDE.md)
│   └── opencode.json          # generated config: $schema + default model + MCP
├── mcp-configs/
│   └── mcp.json               # shared MCP servers; merged/copied by install.sh
├── install.sh                 # sync Claude/Cursor/Codex/opencode targets
├── scripts/
│   ├── generate-codex-skills.sh    # wrapper → generate_codex_skills.py
│   ├── generate_codex_skills.py    # ycc/skills → .codex-plugin/ycc/skills
│   ├── validate-codex-skills.sh    # sync check + Codex skill lint/content policy
│   ├── generate-codex-agents.sh    # wrapper → generate_codex_agents.py
│   ├── generate_codex_agents.py    # ycc/agents → .codex-plugin/agents
│   ├── validate-codex-agents.sh    # sync check + TOML/content policy
│   ├── generate-codex-plugin.sh    # wrapper → generate_codex_plugin.py
│   ├── generate_codex_plugin.py    # plugin manifest + repo-local marketplace metadata
│   ├── validate-codex-plugin.sh    # JSON + sync check
│   ├── generate-cursor-agents.sh   # wrapper → generate_cursor_agents.py
│   ├── generate_cursor_agents.py   # ycc/agents → .cursor-plugin/agents
│   ├── validate-cursor-agents.sh   # sync check + content policy
│   ├── generate-cursor-skills.sh   # wrapper → generate_cursor_skills.py
│   ├── generate_cursor_skills.py   # ycc/skills → .cursor-plugin/skills
│   ├── validate-cursor-skills.sh   # sync check + content policy
│   ├── generate-cursor-rules.sh    # wrapper → generate_cursor_rules.py
│   ├── generate_cursor_rules.py    # ycc/rules → .cursor-plugin/rules (.md → .mdc)
│   ├── validate-cursor-rules.sh    # sync + frontmatter lint + content policy
│   ├── generate-opencode-skills.sh    # wrapper → generate_opencode_skills.py
│   ├── generate_opencode_skills.py    # ycc/skills → .opencode-plugin/skills
│   ├── validate-opencode-skills.sh    # sync check + frontmatter lint + content policy
│   ├── generate-opencode-agents.sh    # wrapper → generate_opencode_agents.py
│   ├── generate_opencode_agents.py    # ycc/agents → .opencode-plugin/agents
│   ├── validate-opencode-agents.sh    # sync check + frontmatter lint + content policy
│   ├── generate-opencode-commands.sh  # wrapper → generate_opencode_commands.py
│   ├── generate_opencode_commands.py  # public ycc/skills → .opencode-plugin/commands
│   ├── validate-opencode-commands.sh  # sync check + frontmatter lint + content policy
│   ├── generate-opencode-plugin.sh    # wrapper → generate_opencode_plugin.py
│   ├── generate_opencode_plugin.py    # opencode.json + AGENTS.md + MCP translation
│   ├── validate-opencode-plugin.sh    # JSON schema + sync check
│   ├── generate_opencode_common.py    # shared paths / transforms / model + tool maps
│   └── opencode_model_aliases.json    # Claude-shorthand → openai/gpt-5.4-family map
├── ycc/                       # the consolidated Claude Code plugin
│   ├── .claude-plugin/
│   │   └── plugin.json        # name: "ycc", current version in plugin.json
│   ├── agents/                # agents (source for Cursor/Codex/opencode generation)
│   ├── rules/                 # language-specific rules (common + per-language); source for Cursor .mdc generation
│   ├── settings/              # shared Claude settings: settings.json, models.json, hooks/, rules/, statusline
│   └── skills/                # skills + _shared; public skills are Claude slash commands (source for Cursor/Codex/opencode generation)
│       ├── _shared/           # shared scripts (e.g., resolve-plans-dir.sh)
│       └── {skill-name}/
│           ├── SKILL.md
│           ├── references/    # templates and examples
│           └── scripts/       # validation and helpers
└── docs/
    ├── install/               # runtime-specific install guides
    └── plans/                 # implementation plans
```

## License

[MIT](LICENSE)
