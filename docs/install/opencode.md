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
| `base`     | Generates and validates `.opencode-plugin/{skills,agents,commands,shared,ycc-sensitive-guard}/`, then rsyncs them into `~/.config/opencode/`.      |
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

## Global Rules

opencode loads `~/.config/opencode/AGENTS.md`; see the
[official rules guide](https://opencode.ai/docs/rules). The generated bundle copies
the tool-neutral source `ycc/settings/rules/CLAUDE.md` verbatim after a generated
header, without filename or runtime substitutions. The `rules` step refuses to
replace a real user rules file without `--force`. No additional global filename
is linked. This is distinct from repo-local `AGENTS.md` loading and Claude
compatibility fallbacks.

## Plugins

The generated `opencode.json` declares the bundle's shared OpenCode V2 plugins in
`plugins`:

| Plugin                                | Purpose                                                                      |
| ------------------------------------- | ---------------------------------------------------------------------------- |
| `@prevalentware/opencode-goal-plugin` | Goal mode — `/goal` commands, persistent goal state, and the goal tool suite |
| `./ycc-sensitive-guard`               | Sensitive-file policy for restricted ycc specialists (see below)             |

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

The V2 `plugins` array is the correct key (the V1 singular `plugin` key is
rejected). The plugin API spike ran on opencode **v2.0.29**, and the
experimental npm package declares an `engines.opencode` floor of **>=2.0.30**,
the version its package smoke targets; other versions are unverified. The
package is opt-in and experimental, and registry publication is separate from
generating it. The file-copy install above stays primary, and a native or npm
plugin installed alongside the file copy would register the same components
twice. See the [v6 opencode guide](v6/opencode.md) before opting in.

### Sensitive-file guard

Some specialists must never handle secret-bearing files: `pr-comment-fixer`,
`release-fix-applier`, `backport-conflict-resolver`, `review-fixer`, and
`db-modifier`. The list of agents and path patterns (`.env` and variants other than
`*.env.example`, keys and certificates, `credentials.json`, `.ssh/`, `.aws/`,
`.kube/config`, `.netrc`, and similar) lives in
[`ycc/settings/sensitive-files.json`](../../ycc/settings/sensitive-files.json).
Two layers enforce it:

- **Native rules.** The generated agent `permissions` end with `read` and `edit`
  denies for those paths, and their shell allowlists contain no general
  file-printing commands such as `cat`. The `*.env.example` exception lifts
  only the `.env` patterns, so a key file such as `id_rsa.env.example` stays
  denied. `git diff --no-index` is denied for every restricted agent.
- **Guard plugin.** `~/.config/opencode/ycc-sensitive-guard` is a local
  OpenCode V2 plugin registered through the relative `plugins` entry above. It
  is its own bundle unit: `base` mirrors it, and `--settings` (the `plugins`
  group) installs it with the entry and takes it back on removal. It does not
  depend on `skills/` or `shared/`, so `--skills-home agents` keeps it. For the
  restricted agents it resolves paths against the calling session's directory
  (not the server's; when neither can be determined, the call is rejected) on `read`, `edit`, `write`, `patch`,
  `grep`, `glob`, and `shell` calls, following symlinks (including links whose
  target does not exist yet) and the `read` tool's look-alike file-name
  fallback. It rejects calls that name a sensitive path (including git object
  names such as `HEAD:.env`), shell commands it cannot resolve to file names
  (brace expansion, any `$` expansion or backtick substitution such as `$HOME`,
  `${PWD}`, `$(…)` and `$'…'`, tilde prefixes other than `~/` such as `~user`,
  `~+` and `~-`, and `git diff --no-index`), and `git` commands
  that leave the session directory (a path argument or working directory
  outside it, `-C`, `-c`, `--git-dir`, `--work-tree`, or `GIT_*` variables), and
  removes sensitive files from `grep` and `glob` results. Other agents are unaffected.
  The experimental npm package ships the same guard directory and registers it
  from its own setup.

The guard plugin must be loaded. Keep the entry in your `opencode.json`. A
project config that removes the plugin, or a plugin that fails to load, leaves
only the native `read`/`edit` rules. The guard checks the text of each shell
command, so some allowed commands stay outside it:

- Build, test, and interpreter commands (`npm`, `pytest`, `make`, `python`, …)
  execute project code.
- Read-only git history commands print committed file contents without naming
  the file. `backport-conflict-resolver` may run `git show`, `git log`,
  `git blame`, and `git diff`, and `review-fixer` may run `git log` and
  `git diff`. A history-wide `git log -p` or `git show <commit>` can therefore
  show a secret that was once committed.

Maintainers can exercise the guard on an isolated host with
`scripts/test-opencode-sensitive-guard.sh`. This opt-in check is not part of
`validate.sh`.

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
unused: V2 parses the field but does not resolve its files, globs, or URLs. The
opt-in npm plugin delivers its instructions through the verified context hook
instead.

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

opencode hook guidance is otherwise advisory in this bundle. The only shipped
lifecycle plugin is the sensitive-file guard described under Plugins.

## Regenerate Only opencode Artifacts

After editing source files under `ycc/`, regenerate opencode artifacts directly
or through the unified sync script:

```bash
./scripts/sync.sh --only opencode
./scripts/validate.sh --only opencode
```
