# Install Guides

This directory contains the runtime-specific install guides for `ycc`. The root
[`README.md`](../../README.md) stays short and links here instead of duplicating
every target's installer behavior.

## Runtime Guides

| Runtime  | Guide                        | Best for                                                                   |
| -------- | ---------------------------- | -------------------------------------------------------------------------- |
| Claude   | [`claude.md`](claude.md)     | Claude Code plugin installs, Claude rules/config, Claude Desktop MCP setup |
| Cursor   | [`cursor.md`](cursor.md)     | Cursor-native skills, agents, rules, and MCP sync                          |
| Codex    | [`codex.md`](codex.md)       | Codex plugin installs, custom agents, Codex Desktop setup                  |
| opencode | [`opencode.md`](opencode.md) | opencode-native skills, agents, commands, config, and rules                |

## Installer Model

Use `install.sh` from the repository root (or `ycc` once it is on `PATH`). Every
invocation starts with a command — `install`, `sync`, `remove`, `migrate`, `cli`, or
`completion`; a bare `./install.sh --target ...` is rejected. `install` is the
first-time setup (base step plus opt-in `--settings`/`--rules`/`--mcp`/`--hooks`
or `--only`); `sync` is the recommended entry point after that:

```bash
./install.sh sync --target <claude|cursor|codex|opencode|all> --intent <intents>
```

You say **what** you want synced; each target maps the intent onto the steps it
actually supports, and reports (rather than silently substitutes) anything it
cannot do.

```bash
./install.sh sync --target claude --intent hooks,settings,mcp,plugins
./install.sh sync --target all --intent settings,rules
./install.sh sync --target codex --intent settings,mcp --global
./install.sh remove --target all --only mcp --global
```

`mcp` defaults to project scope on every target; see
[Project Vs Global Scope](#project-vs-global-scope). To undo any of it, see
[Removing Installed Config](#removing-installed-config).

### Migrating To Native Packages

`migrate` moves an existing file-copy/managed-config install toward the
native packages for one runtime. It is **dry-run by default**: it reports what
it would change and writes no config, state, build output, or CLI state.
Pass `--apply` to make the reported changes:

```bash
./install.sh migrate --target claude           # dry-run
./install.sh migrate --target claude --apply
./install.sh migrate --target codex            # dry-run
./install.sh migrate --target codex --apply
./install.sh migrate --target cursor           # dry-run
./install.sh migrate --target cursor --apply
```

- `--target` accepts `claude`, `codex`, or `cursor`; `--target all` resolves
  to exactly those three. `opencode` and `agents` have no migration and are
  rejected when named explicitly — their file-copy installs stay as they are.
- Migration preserves user edits and data. It removes only entries it can
  prove are installer-owned (managed-config ownership, byte-identical copies,
  or symlinks pointing at this checkout), reports anything uncertain as a
  conflict instead of deleting it, and is safe to run repeatedly. `--force`
  is rejected for `migrate` and never widens what migration deletes.
  Symlinked configuration files are retained with a notice rather than
  replaced, preserving dotfiles links.
- **Claude:** settings hooks are pruned only when `ycc-hooks@ycc` is
  explicitly enabled, and managed MCP entries only when `ycc-mcp@ycc` is
  explicitly enabled; enabling `ycc-all@ycc` alone proves neither. User hooks
  in the same event groups are preserved, link cleanup removes only owned
  symlinks, and only global config files are touched.
- **Codex:** production apply fails closed before any cleanup or CLI call
  while this checkout's catalog is still the legacy `local-ycc-plugins`
  catalog (the native listing gate is YAN-1140); dry-run explains that gate
  and retains the legacy install. `--marketplace-source <dir>` (Codex only)
  points migration at a staged directory carrying an eligible native `ycc`
  catalog and payloads, validated by the same checks — it is not a bypass.
  On apply, the marketplace is registered and each package is installed and
  verified installed and enabled **before** any legacy entry is retired,
  including exact installer matches in the standalone `~/.codex/skills/`
  slice. Edited skills stay, and shared helpers stay while any skills remain.
  Everything under `~/.codex/agents/` is preserved.
- **Cursor:** only copies that match the canonical source byte-for-byte, or
  owned symlinks pointing exactly at it, are removed — across skills, agents,
  rules, and shared helpers as actually installed. Edited or foreign entries
  stay, along with shared helpers while any skills remain. Migration prints
  the interactive `/add-plugin` step; it does not install the Cursor plugin itself.

The runtime guides above remain the supported install documentation.
Migration does not list hidden native packages in production catalogs or
establish runtime installation, session, or hook-dispatch verification.

### `ycc` Command On PATH

Project-scoped runs happen from inside the other project, where `./install.sh`
does not exist. Link the installer onto `PATH` once:

```bash
./install.sh cli                 # symlink install.sh as `ycc`
ycc completion --install         # shell completion for $SHELL
cd ~/code/other-project && ycc sync --target opencode --intent mcp
```

- `cli` links into the first of `$XDG_BIN_HOME`, `~/.local/bin`, `~/bin` already
  on `PATH` (else `~/.local/bin`, with a warning); `--dir <dir>` overrides.
- `ycc` is the installer itself, reached through a symlink, so it always runs
  this checkout's HEAD. `--project` targets the git root of your current directory.
- `completion --shell bash|zsh|fish` prints the script (default: `$SHELL`);
  `--install` symlinks it into the shell's per-user completion directory:

| Shell | Destination                                                                                     |
| ----- | ----------------------------------------------------------------------------------------------- |
| bash  | `${BASH_COMPLETION_USER_DIR:-${XDG_DATA_HOME:-~/.local/share}/bash-completion}/completions/ycc` |
| zsh   | `${XDG_DATA_HOME:-~/.local/share}/zsh/site-functions/_ycc` (must be in `fpath`)                 |
| fish  | `${XDG_CONFIG_HOME:-~/.config}/fish/completions/ycc.fish`                                       |

Both `cli` and `completion --install` refuse to replace an existing file or a
symlink pointing elsewhere unless you pass `--force`. Without bash-completion or
the zsh `fpath` entry, source the script instead: `eval "$(ycc completion --shell bash)"`
or `source <(ycc completion --shell zsh)`.

| Intent     | Meaning                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------- |
| `base`     | Install or register the target's native bundle surface.                                     |
| `skills`   | Standalone skills, one entry each, in the tool's own skills dir (no plugin).                |
| `agents`   | Standalone agents, one entry each, in the tool's own agents dir (no plugin).                |
| `commands` | Slash commands: standalone skills on claude (alias), generated native commands on opencode. |
| `settings` | Merge repo-managed config keys (models, effort levels, statusline, ...).                    |
| `rules`    | Symlink the global rules file each runtime reads (Cursor: manual, see its page).            |
| `mcp`      | Merge MCP server definitions into the target's MCP surface.                                 |
| `hooks`    | Merge hook configuration; Claude also links the hook scripts directory.                     |
| `plugins`  | Merge plugin enablement and marketplace entries. Add `base` for CLI-side registration too.  |
| `mods`     | Install the Claude Code mods under `ycc/mods` (claude only for now).                        |

Per-target mapping (intents a target cannot execute are skipped with a notice):

| Intent     | claude             | cursor     | codex      | opencode   |
| ---------- | ------------------ | ---------- | ---------- | ---------- |
| `base`     | `base`             | `base`     | `base`     | `base`     |
| `skills`   | `skills`           | `skills`   | `skills`   | `skills`   |
| `agents`   | `agents`           | `agents`   | `agents`   | `agents`   |
| `commands` | `skills` (alias)   | no-op      | no-op      | `commands` |
| `settings` | `settings`         | `settings` | `settings` | `settings` |
| `rules`    | `rules`            | `rules`    | `rules`    | `rules`    |
| `mcp`      | `mcp`              | `mcp`      | `mcp`      | `mcp`      |
| `hooks`    | `settings`+`hooks` | no-op      | no-op      | no-op      |
| `plugins`  | `settings`         | no-op      | `settings` | `settings` |
| `mods`     | `mods`             | no-op      | no-op      | no-op      |

`sync` is exclusive: it never implicitly runs `base`.

Global instructions are linked as `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or
`~/.config/opencode/AGENTS.md`, not both filenames. Cursor User Rules are
settings-configured; `rules` prints manual guidance and provisions no files
(file-based user-global provisioning is unsupported/unverified). See each target
page for official loading references. Install/sync preserves legacy rule links;
remove still unlinks only links to this checkout.

### Standalone Slices

`skills`, `agents` and `commands` install entries one by one into each tool's
own user directories, with no plugin or marketplace registration. On claude the
`commands` intent is an alias for `skills` — public skills are native slash
invocations there, so there is nothing separate to copy:

| Target   | Destinations                                                                                   |
| -------- | ---------------------------------------------------------------------------------------------- |
| claude   | `~/.claude/skills/<name>`, `~/.claude/agents/<name>.md` (skills are the slash commands)        |
| cursor   | `~/.cursor/skills/<name>`, `~/.cursor/agents/<name>.md`                                        |
| codex    | `~/.codex/skills/<name>` (helpers in `~/.codex/skills/_shared`), `~/.codex/agents/<name>.toml` |
| opencode | `~/.config/opencode/{skills,agents,commands}/<name>` (+ `shared/`)                             |

- Entries are copied with plugin-root paths (`${CLAUDE_PLUGIN_ROOT}`,
  `~/.codex/plugins/ycc`) re-pointed at the new location and `ycc:` prefixes
  dropped, so each works without the plugin.
- What ycc installed is recorded in `~/.config/ycc/installed-units.json`. An
  existing entry is replaced only when ycc installed it or it is identical;
  your own skills or agents with the same name need `--force`. Entries the
  bundle no longer ships are pruned on the next sync.
- On claude, older ycc installs wrote wrappers to `~/.claude/commands/`. A
  successful skills install (via `--intent skills` or the `commands` alias)
  retires only wrappers recorded in `~/.config/ycc/installed-units.json`;
  foreign or unrecorded entries stay, even with `--force`.
- With the plugin (`base`) also installed, skills appear twice (`ycc:<name>`
  and `<name>`); the installer warns.
- `--only` / `--intent` skip a slice a target has no home for (e.g.
  `commands` on cursor), so `--target all --only agents` just works.

### Merge Semantics

Structured config files (`~/.claude/settings.json`, `~/.claude.json`,
`~/.codex/config.toml`, `~/.config/opencode/opencode.json`,
`~/.cursor/cli-config.json`) are **merged**, not copied:

- Only keys this repository declares as managed are written; every other key
  in your file is preserved.
- A managed value the installer previously wrote is updated automatically on
  later runs.
- A managed value **you** changed is preserved with a warning; `--force` takes
  the repo value instead.
- Ownership is tracked by hash in `~/.config/ycc/managed-config-state.json`
  (hashes only, never values, so tokens never leak into state).

This is what makes new-machine setup reliable: run the same `sync` command on
any machine and repo-managed settings land without clobbering machine-local
trusted projects, provider credentials, or CLI-written marketplace entries.

### Project Vs Global Scope

`--project` and `--global` (mutually exclusive) work with `install`, `sync`,
and `remove`. Without either flag, steps that support project scope use it and
every other step stays global. The project is the git root of the current
directory, else the current directory. Today only the `mcp` step is
project-capable:

| Target   | `--project` (default)          | `--global`                         |
| -------- | ------------------------------ | ---------------------------------- |
| claude   | `<project>/.mcp.json`          | `~/.claude.json`                   |
| cursor   | `<project>/.cursor/mcp.json`   | `~/.cursor/mcp.json`               |
| codex    | `<project>/.codex/config.toml` | `~/.codex/config.toml`             |
| opencode | `<project>/opencode.json`      | `~/.config/opencode/opencode.json` |

Codex loads a project `.codex/config.toml` only for trusted projects; the
installer warns when it writes one. An explicit `--project` combined with a step
that has no project scope (for example `--only settings,mcp --project`) is
rejected before anything runs: the error is about `settings`, not `mcp`. Drop
`--project` to get project MCP plus global settings in one run.

### Selecting MCP Servers

### GitHub MCP prerequisite

Install [GitHub CLI](https://cli.github.com/) and sign in with `gh auth login`
before enabling GitHub MCP. The runtime's `PATH` must also provide a POSIX `sh`
and [Node.js/npm](https://nodejs.org/) with `npx`.

ycc launches `mcp-remote` through `npx` to bridge the runtime's stdio connection
to GitHub's remote endpoint, `https://api.githubcopilot.com/mcp/`. No
`github-mcp-server` binary or Docker installation is needed. At each server
startup, `gh auth token` supplies the token; a failed authentication lookup stops
startup before launching the bridge. The token is passed through the bridge's
environment-variable header substitution, not written into managed config or
included in process arguments. Restart the MCP server after changing GitHub
accounts or credentials.

Normal `ycc sync --intent mcp` migrates recognized legacy
`github-mcp-server stdio`, `npx @modelcontextprotocol/server-github`, and
`https://api.githubcopilot.com/mcp` entries even without ownership state.
Obsolete transport/auth fields are removed; unrelated settings, servers and tools
remain. Custom GitHub connections stay untouched unless `--force` is explicit.
`--mcps` selection and `--dry-run` apply
to migration too.

By default the `mcp` step merges every server the repo manages for a target.
`--mcps <names>` (comma-separated) narrows `install`, `sync`, and `remove` to
just those servers, for every MCP-capable target (claude, cursor, codex,
opencode):

```bash
ycc list-mcps                                   # every managed server
ycc list-mcps --target codex                    # just codex's
ycc sync --target opencode --intent mcp --mcps github,linear
ycc sync --target all --intent mcp --mcps playwright --global
ycc install --target claude --only mcp --mcps github
ycc remove --target cursor --intent mcp --mcps stripe
```

- Servers not named are left alone: a partial sync never removes the other
  managed servers, and a partial remove takes only the named ones.
- Each name must be a managed server, else the run stops before writing
  anything. A target that manages none of the named servers skips its MCP step
  with a warning.
- Every MCP-capable target manages the same servers: `mcp-configs/mcp.json` is
  the single list. Codex gets a generated translation
  (`.codex-plugin/config/mcp-servers.json`); a server defined under
  `[mcp_servers.*]` in `.codex-plugin/config/config.toml` replaces its
  translation (Codex-only extras such as `bearer_token_env_var` and per-tool
  `approval_mode`).
- `--mcps` requires the `mcp` step (`--intent mcp`, `--mcp`, or `--only mcp`).
- Shell completion offers the managed server names after `--mcps`, narrowed to
  the `--target` already on the command line (via `ycc list-mcps`).

> **Behavior change:** the `mcp` step used to write only user-global files.
> Pass `--global` to keep that. Cursor MCP is now merged instead of symlinked,
> and Codex/opencode MCP servers moved from the `settings` step to the `mcp`
> step.

### Removing Installed Config

```bash
./install.sh remove --target claude --only mcp                  # project scope
./install.sh remove --target all --intent mcp --global          # user-global
./install.sh remove --target codex --intent settings,plugins,rules
./install.sh remove --target all --intent base,settings,rules,hooks,plugins,mods
./install.sh remove --target opencode --intent agents,commands
```

`remove` undoes any intent on any target, using the same intent → step mapping
as `sync` (an intent a target does not support is reported and skipped). It
requires `--only` or `--intent`, and rejects `--mode` and the additive
`--settings`/`--rules`/`--mcp`/`--hooks` flags. Only what the installer owns is
taken back:

| Step / intent                  | What `remove` does                                                                                                                                                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `settings`, `plugins`, `hooks` | Strips repo-managed keys from the structured config (`settings.json`, `cli-config.json`, `config.toml`, `opencode.json`). List entries (plugin lists, Cursor permissions) lose only the items the installer appended.                       |
| `mcp`                          | Strips managed MCP servers, including ones the repo has since dropped. Servers you added are never touched.                                                                                                                                 |
| `rules`, claude `hooks` dir    | Removes the symlinks, only while they still point at this checkout. A real file you put there is never deleted.                                                                                                                             |
| claude statusline script       | Removed while identical to the repo copy; an edited copy needs `--force`.                                                                                                                                                                   |
| `base`                         | claude: `claude plugin uninstall ycc@ycc` + marketplace remove. cursor / opencode: the bundle's entries in the synced dirs (your own skills stay). codex: plugin links, plugin cache, custom agents, marketplace entry.                     |
| `skills`, `agents`, `commands` | Removes the standalone entries ycc recorded (or that are still identical to the bundle). Never the plugin, never your own entries without `--force`. On claude, `commands` retires only the recorded legacy `~/.claude/commands/` wrappers. |
| `mods` (claude)                | Uninstalls each mod and the `ycc-mods` marketplace.                                                                                                                                                                                         |

- A managed value you edited is kept with a warning; `--force` removes it.
- A config file left empty is deleted. Codex TOML removal keeps comments,
  trusted projects and unrelated tables.

### Legacy Flag Form

The original flag CLI keeps working unchanged:

```bash
./install.sh install --target <claude|cursor|codex|opencode|all> [flags]
```

Without `--only`, the target's `base` step runs by default, and additive flags
run additional steps.

Common flags:

```bash
./install.sh install --target claude --settings --rules --mcp --hooks
./install.sh install --target cursor --rules --mcp
./install.sh install --target codex --settings --rules
./install.sh install --target opencode --settings --rules
./install.sh install --target all --settings --rules --mcp
```

Use `--only <steps>` to run exactly the listed steps and skip the default `base`
step:

```bash
./install.sh install --target claude --only rules
./install.sh install --target codex --only settings,rules
```

## Source Modes

`--mode local` is the default. It registers or syncs the current checkout so
contributors can iterate locally.

`--mode repo` registers the upstream GitHub repository instead of the local
checkout. It is supported by the `claude` and `codex` targets only:

```bash
./install.sh install --target claude --mode repo
./install.sh install --target codex --mode repo
./install.sh install --target all --mode repo
```

With `--target all --mode repo`, Cursor and opencode are skipped because they do
not have a remote-source install surface.

## Regenerate And Validate

When editing source-of-truth files under `ycc/`, regenerate derived bundles and
validate them before committing:

```bash
./scripts/sync.sh
./scripts/validate.sh
```

Both scripts accept `--only <targets>` for narrower runs, such as
`./scripts/sync.sh --only codex`.
