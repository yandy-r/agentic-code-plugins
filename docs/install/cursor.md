# Cursor Install Guide

Cursor support is generated from the `ycc/` source tree and synced into
Cursor-native config directories.

## Quick Start

From the repository root:

```bash
./install.sh install --target cursor
```

The default `base` step generates, validates, formats, and rsyncs the Cursor
bundle into `~/.cursor/`.

## Add Settings, Rules, And MCP

For the full Cursor setup:

```bash
./install.sh sync --target cursor --intent settings,rules,mcp
```

The step-flag `install` form is equivalent:

```bash
./install.sh install --target cursor --settings --rules --mcp
```

Step behavior:

| Step       | Effect                                                                                                                                                                                                           |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `base`     | Generates and validates `packages/cursor/ycc/{skills,agents}` and `packages/cursor/ycc-rules/rules`, then rsyncs them into `~/.cursor/`.                                                                         |
| `skills`   | Generates the skills and installs each into `~/.cursor/skills/<name>`, leaving your own skills alone.                                                                                                            |
| `agents`   | Generates the agents and installs each into `~/.cursor/agents/<name>.md`.                                                                                                                                        |
| `settings` | Merges `packages/cursor/installer-fallback/config/cli-config.json` into `~/.cursor/cli-config.json`. This file is generated from `ycc/settings/cursor/cli-config.json`; edit the source, not the generated copy. |
| `rules`    | Links nothing: Cursor User Rules are set in Settings → Rules, not a file. Prints how to paste `ycc/settings/rules/CLAUDE.md`.                                                                                    |
| `mcp`      | Merges `mcp-configs/mcp.json` into `<project>/.cursor/mcp.json` (or `~/.cursor/mcp.json` with `--global`).                                                                                                       |

Cursor has no `commands`, `hooks` or `plugins` step; those intents are reported
as no-ops. The generated `rules/` bundle unit ships with `base` only.

## Model Configuration

Cursor splits model selection across two surfaces, so this repository manages
both:

| Surface         | File                        | Value                                   |
| --------------- | --------------------------- | --------------------------------------- |
| Main CLI model  | `~/.cursor/cli-config.json` | `claude-fable-5-1`                      |
| Sub-agent model | `~/.cursor/agents/*.md`     | `claude-opus-5[effort=high,context=1m]` |

Sub-agent models live in each generated agent's frontmatter because that is
where Cursor resolves them. `scripts/cursor_fast_agents.json` remains an
explicit opt-in escape hatch for individual agents, but is empty by default so
every generated subagent uses Opus High.

Both values are placeholders in the sense that Cursor may override them: model
availability is plan- and admin-gated, and legacy request-based plans can force
subagents onto Composer regardless of configuration.

## Selective Steps

Use `--only` to run exactly the listed steps:

```bash
./install.sh install --target cursor --only base
./install.sh install --target cursor --only settings
./install.sh install --target cursor --only rules
./install.sh install --target cursor --only mcp                   # <project>/.cursor/mcp.json
./install.sh install --target cursor --only mcp --global          # ~/.cursor/mcp.json
./install.sh remove --target cursor --only mcp --global   # remove managed servers
```

MCP servers are merged, not symlinked, so servers you add survive; a symlink
left at `~/.cursor/mcp.json` by older installers becomes a real file on the
next `--global` run. See
[Project Vs Global Scope](README.md#project-vs-global-scope) and
[Removing Installed Config](README.md#removing-installed-config).

`--mode repo` is not supported for Cursor. Cursor reads files from local config
directories, so use the default local mode.

## Installed Surfaces

| Surface      | Location                                             |
| ------------ | ---------------------------------------------------- |
| Skills       | `~/.cursor/skills/`                                  |
| Agents       | `~/.cursor/agents/`                                  |
| Cursor rules | `~/.cursor/rules/`                                   |
| CLI config   | `~/.cursor/cli-config.json`                          |
| MCP config   | `<project>/.cursor/mcp.json` or `~/.cursor/mcp.json` |

Cursor User Rules live in Cursor Settings (Customize → Rules); file-based
user-global provisioning is unsupported/unverified per
[cursor.com/docs/rules](https://cursor.com/docs/rules), so `rules` creates no
files. Older `~/.cursor/CLAUDE.md` / `AGENTS.md` links are left in place on
install and removed by `remove --intent rules` only while they point at this checkout.

## Regenerate Only Cursor Artifacts

After editing source files under `ycc/`, regenerate Cursor artifacts directly or
through the unified sync script:

```bash
./scripts/sync.sh --only cursor
./scripts/validate.sh --only cursor,cursor-native,packages
```

Generated hidden native packages also live under `packages/cursor/` (`ycc-rules`,
`ycc-mcp`, and `ycc-hooks` alongside `ycc`). They are all unlisted, there is no
root marketplace, and native listing/install is not yet available; the installer
above remains the user-facing path.
