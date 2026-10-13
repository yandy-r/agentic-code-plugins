# opencode Install Guide

opencode support is native. The generated bundle installs skills, agents,
commands, config, and rules into `~/.config/opencode/`.

The generated `opencode.json` targets **OpenCode V2 only**. V1 field shapes
(`provider`, `agent`, `permission`, `plugin`, and server names directly under
`mcp`) are rejected by `scripts/validate-opencode-plugin.sh`. Note that
`https://opencode.ai/config.json` still serves the V1 schema, so an editor
validating against it may flag correct V2 config; the repo validator encodes the
V2 field set from [opencode.ai/v2/docs](https://opencode.ai/v2/docs/config)
instead.

## Quick Start

From the repository root:

```bash
./install.sh install --target opencode
```

The default `base` step generates, validates, formats, and rsyncs the opencode
bundle into `~/.config/opencode/`.

Restart opencode after installing or updating the bundle.

## Add Settings And Rules

For the full opencode setup:

```bash
./install.sh sync --target opencode --intent base,settings,mcp,plugins,rules
```

The step-flag `install` form is equivalent:

```bash
./install.sh install --target opencode --settings --rules
```

Step behavior:

| Step       | Effect                                                                                                                                             |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `base`     | Generates and validates `.opencode-plugin/{skills,agents,commands}/`, then rsyncs them into `~/.config/opencode/`.                                 |
| `skills`   | Generates the skills and installs each into `skills/<name>`, plus the `shared/` helpers.                                                           |
| `agents`   | Generates the agents and installs each into `agents/<name>.md`.                                                                                    |
| `commands` | Generates one thin command per public skill from its `SKILL.md` and installs it as `commands/<name>.md`.                                           |
| `settings` | Merges managed keys from `.opencode-plugin/opencode.json` into `~/.config/opencode/opencode.json`. Plugins live in this same file.                 |
| `mcp`      | Merges `mcp.servers` from `.opencode-plugin/opencode.json` into `<project>/opencode.json` (or `~/.config/opencode/opencode.json` with `--global`). |
| `rules`    | Symlinks `.opencode-plugin/AGENTS.md` into `~/.config/opencode/AGENTS.md`.                                                                         |

MCP servers moved from the `settings` step to the `mcp` step, which defaults to
project scope; pass `--global` to keep writing the user config. See
[Project Vs Global Scope](README.md#project-vs-global-scope) and
[Removing Installed Config](README.md#removing-installed-config).

## Plugins

The generated `opencode.json` declares the bundle's shared OpenCode V2 plugins in
`plugins`:

| Plugin                                | Purpose                                                                      |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| `@prevalentware/opencode-goal-plugin` | Goal mode — `/goal` commands, persistent goal state, and the goal tool suite |

`--settings` installs the server-side half. The TUI half (sidebar goal indicator
and command-palette entry) is read from the global `~/.config/opencode/cli.json`,
which this repository does not manage. Install both halves on a new machine with:

```bash
./install.sh install --target opencode --settings --rules
opencode2 plugin add @prevalentware/opencode-goal-plugin
```

`opencode2 plugin add` writes the package into `~/.config/opencode/opencode.json`
and `~/.config/opencode/cli.json`, and is idempotent. Verify with
`opencode2 plugin list`. Use `opencode` instead of `opencode2` when the V2 binary
is installed under that name.

## Selective Steps

Use `--only` to run exactly the listed steps:

```bash
./install.sh install --target opencode --only base
./install.sh install --target opencode --only settings
./install.sh install --target opencode --only rules
./install.sh install --target opencode --only settings,rules
./install.sh install --target opencode --only mcp                   # <project>/opencode.json
./install.sh remove --target opencode --only mcp --global   # remove managed servers
```

`--mode repo` is not supported for opencode. opencode reads files from local
config directories, so use the default local mode.

## Installed Surfaces

| Surface  | Location                                                        |
| -------- | --------------------------------------------------------------- |
| Skills   | `~/.config/opencode/skills/`                                    |
| Agents   | `~/.config/opencode/agents/`                                    |
| Commands | `~/.config/opencode/commands/`                                  |
| Config   | `~/.config/opencode/opencode.json`                              |
| MCP      | `<project>/opencode.json` or `~/.config/opencode/opencode.json` |
| Rules    | `~/.config/opencode/AGENTS.md`                                  |

Rules reach the model through `~/.config/opencode/AGENTS.md`, which V2 loads as
the global instructions file. The config's `instructions` array is deliberately
unused: V2 parses the field but does not resolve its files, globs, or URLs.

Invoke skills with the built-in `skill` tool, agents with `@agent-name` mentions
or the native v2 `subagent(agent, description, prompt, sessionID?, background?)`
tool, and commands as `/<name>` in the TUI.

Commands are generated from public skills (`user-invocable` not `false`), so
`commands/` mirrors the skill set. Each command has no workflow body of its own: it
tells the agent to load the matching skill with the `skill` tool and passes
`$ARGUMENTS` through. Do not chain commands into other commands. The commands exist
only for commands-only installs (`--intent commands` with no skills); skill logic
stays in `SKILL.md`.

## Model Configuration

The generated `opencode.json` sets the bundle's main model, its reasoning
effort, and a `#subagent` variant carrying the sub-agent reasoning effort.
Beyond that root model, every agent under `ycc/agents/` (plus the built-in
`general` and `explore` subagents) gets its **own** explicit model assignment
in the generated `agents` block — not just `general`/`explore` on the
`#subagent` variant. Assignments are tiered by intended capability:

| Tier                          | Sample Model           | Intended Roles                                                                                                           |
| ----------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Deep architecture / high-risk | `openai/gpt-6-astra`   | e.g. `architect`, `code-architect`, `root-cause-analyzer`, `db-modifier`, `go-expert-architect`, `rust-expert-architect` |
| Docs / lookup / routine       | `openai/gpt-5.6-terra` | e.g. `docs-git-committer`, `code-finder`, `api-documenter`, `documentation-writer`, `readme-generator`                   |
| Everything else               | `openai/gpt-5.6-sol`   | General implementation, review, and specialty agents                                                                     |

**These values are placeholders.** Unlike Claude and Codex, opencode's usable
catalog depends on which provider subscriptions and models you have configured,
so the bundle ships portable defaults rather than fixed models. Change the
preferred models in [`ycc/settings/models.json`](../../ycc/settings/models.json)
(`targets.opencode.main`, `.subagent`, and `.agents`), or simply edit your own
`~/.config/opencode/opencode.json` — the merge keeps local model choices and
provider credentials instead of overwriting them.

`scripts/generate_opencode_plugin.py` fails fast if any agent under `ycc/agents/`
(or the built-ins) is missing from `targets.opencode.agents`, so the mapping in
`models.json` must stay in sync whenever agents are added, renamed, or removed
(see `CONTRIBUTING.md` → Adding, Renaming, or Removing Agents).

## Runtime Settings

The generated config sets the experimental subagent depth:

```json
{
  "experimental": {
    "subagent_depth": 2
  }
}
```

The V2 docs do not describe this field, so its detailed runtime semantics are
not documented here. Change it in `scripts/generate_opencode_plugin.py`
(`DEFAULT_SUBAGENT_DEPTH`) or override it in your own
`~/.config/opencode/opencode.json`.

## Hooks

opencode hook guidance is advisory in this bundle. opencode lifecycle hooks
require a TypeScript plugin module, which `ycc` does not ship currently.

## Regenerate Only opencode Artifacts

After editing source files under `ycc/`, regenerate opencode artifacts directly
or through the unified sync script:

```bash
./scripts/sync.sh --only opencode
./scripts/validate.sh --only opencode
```
