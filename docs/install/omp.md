# OMP Install Guide

This guide covers installing `ycc`, `ycc-mcp` and `ycc-rules` into OMP
(oh-my-pi) with `install.sh`, plus the opt-in global instructions, settings,
model roles and approval default.

> **Pre-release:** the OMP packages are generated but unlisted. This repository
> publishes no OMP catalog until the release gate lists them (YAN-1180), so the
> only install path today is `install.sh` from a checkout. `--mode repo` and
> `--target all` do not include OMP yet.

## Prerequisites

- `omp` 18.12.2 or newer on `PATH` (`omp --version`). The installer stops
  with `omp >= 18.12.2 is required for --target omp` otherwise.
- `python3` on `PATH`.
- A checkout of this repository.

OMP has no trust prompt: installed plugin code runs with your user privileges.
Install only from a checkout you trust.

## Quick Start

```bash
./install.sh install --target omp
```

The `base` step generates and validates the OMP packages, then:

1. exports them to `${XDG_DATA_HOME:-~/.local/share}/ycc/omp-marketplace`;
2. registers that export as the OMP marketplace `ycc`
   (`omp plugin marketplace add`);
3. installs each package with `omp plugin install --scope user <package>@ycc`
   (`ycc@ycc`, `ycc-mcp@ycc` and `ycc-rules@ycc`).

What ycc installed is recorded in `~/.config/ycc/omp-native-install.json`.
`update`, `remove` and `migrate` act only on what that file records; an
install or marketplace you created yourself is reported and left untouched.

`ycc@ycc` carries the skills, agents and commands (`/ycc:<skill>`) plus the
shared helpers. `ycc-mcp@ycc` carries the MCP servers (see
[MCP Servers](#mcp-servers)). `ycc-rules@ycc` carries the rules (see
[Rules](#rules)). Without `--package` all three are installed;
`--package ycc`, `--package ycc-mcp` or `--package ycc-rules` selects a
subset. `ycc-hooks` and `ycc-all` are excluded. ycc ships no OMP hooks
(herdr reporting comes from herdr itself, see [herdr](#herdr)), and OMP does
not read plugin dependencies; any other package is rejected with the package
model's reason.

Settings and global instructions are never package-implied. They need the
opt-in `--settings` and `--rules` flags (see
[Settings And Model Roles](#settings-and-model-roles---settings) and
[Global Instructions](#global-instructions---rules)), which cannot be
combined with `--package`.

## Update

Re-run the same command after pulling a new release:

```bash
./install.sh install --target omp
./install.sh sync --target omp --intent base   # equivalent
```

A re-run refreshes the export and runs `omp plugin marketplace update ycc`,
then `omp plugin upgrade --scope <scope> <package>@ycc` only when the exported
version differs from the installed one. When nothing changed, omp is not
touched and the installer prints `<package>@ycc <version> up to date`.

omp upgrades by version only. After you regenerate or edit the packages
without a version bump, the installer prints
`the export changed but its version did not … rerun with --force` instead;
run `./install.sh install --target omp --force` to reinstall the new content.

The `plugins` intent maps to the same `base` step
(`./install.sh sync --target omp --intent plugins`). The `settings` and
`rules` intents map to the opt-in `settings` and `rules` steps. Every other
intent is skipped with a notice.

## Reload Or Restart

After an install or update, run `/reload-plugins` in running omp sessions (or
restart them) to pick up skills, commands, agents and MCP servers. Rules and
`AGENTS.md` load at session start: use `/new` or restart. Settings reload
live. A package that ships hooks or extensions needs a session restart; the
installer says so when it applies.

## MCP Servers

`ycc-mcp@ycc` ships the servers from `mcp-configs/mcp.json` unchanged as the
package's `.mcp.json`. omp loads them at session start and names each one
`ycc-mcp:<server>` (for example `ycc-mcp:github`). Generated files hold only
`${VAR}` placeholders, never secret values.

- **Environment.** omp expands `${VAR}` in `env`, `url` and `headers` from
  your environment when it loads the servers. An unset variable arrives
  literally: with `XERO_CLIENT_ID` unset, `ycc-mcp:xero` receives the text
  `${XERO_CLIENT_ID}`. Export the variables before starting omp.
- **OAuth.** The http servers ship without an `auth` block. Sign in with
  `/mcp reauth ycc-mcp:<server>`. omp stores tokens in `agent.db`, keyed by
  profile and URL, never in a config file.
- **Timeouts** are milliseconds. omp ignores a plugin `timeout` below `1000`
  and uses its 30 s default; `OMP_MCP_TIMEOUT_MS` overrides every server.
- **Disable one server.** Add its name to `disabledServers` in the active
  profile's user `mcp.json` (`~/.omp/agent/mcp.json`, or
  `~/.omp/profiles/<name>/agent/mcp.json` under `--profile`). This beats
  every source; `/mcp disable` does the same. `enabledServers` re-enables a
  server whose source sets `enabled: false`, and `disabledServers` wins over
  it.

  ```json
  { "disabledServers": ["ycc-mcp:xero"] }
  ```

- **Disable the whole package** with `omp plugin disable ycc-mcp@ycc` (add
  `--scope project` for a project install), then `/reload-plugins`.
  `omp plugin enable` restores it. `plugin-overrides.json` does not hide
  marketplace MCP servers, so it is not a kill switch.
- **Override a server.** An entry with the same namespaced name
  (`ycc-mcp:github`) in your user or project `mcp.json` wins, because native
  config outranks plugins. A plain `github` entry does not replace it; disable
  `ycc-mcp:github` and define your own name instead.
- **Precedence.** The first definition of a name wins: the project
  `.omp/mcp.json`, then `.omp/.mcp.json`, then the active profile's user
  `mcp.json`, then Claude configs (project `.claude/`; user-level files only
  with `enabledProviders`), then plugins such as `ycc-mcp`, then imported
  Codex, opencode and Cursor configs. `--profile` reads only that profile's
  user file. `mcp.enableProjectConfig: false` drops the project files.
- **Duplicates.** Servers with different names but the same connection (same
  URL and headers, or same command, args and env) collapse to the
  higher-priority one. `ycc-mcp:linear-personal` has the same URL as
  `ycc-mcp:linear`, so it is shadowed and never connects; a native or Claude
  server with the same connection shadows the `ycc-mcp` one; an equivalent
  Codex, opencode or Cursor import is itself shadowed by `ycc-mcp`.
  Foreign user-level configs (`~/.claude.json`, `~/.codex/config.toml`,
  `~/.cursor/mcp.json`, opencode) load only when `enabledProviders` lists
  their provider.
- **Playwright.** omp drops `ycc-mcp:playwright` while `browser.enabled` is on
  (the default), because its built-in browser replaces it. Set
  `browser.enabled: false` to keep the server.
- **Removal.** `./install.sh remove --target omp --only base` uninstalls the
  recorded installs, including `ycc-mcp@ycc`. To drop only the servers, run
  `omp plugin uninstall --scope <scope> ycc-mcp@ycc`.

omp has no `omp mcp` command; use `/mcp list` in a session to see what
loaded.

## Rules

`ycc-rules@ycc` ships the `ycc/rules` families as 31 flat rules named
`ycc-<family>-<stem>.md` (for example `ycc-common-security`,
`ycc-golang-coding-style`). OMP scans plugin `rules/` flat and names each rule
after its file stem.

- **Always on.** `ycc-common-security` and `ycc-common-git-workflow` are
  `alwaysApply` rules; their full bodies go into every main-session prompt.
- **On demand.** Every other rule is a rulebook entry: a one-line
  `- <name> (<globs>): <description>` listing, with the body read through
  `rule://<name>` (for example `rule://ycc-python-testing`).
- **Globs are advisory.** OMP shows a rule's `globs` in the listing but does
  not select a rule by glob when a matching file is touched, unlike Cursor.
  The `alwaysApply` rules above are still included. Language-rule parity is
  partial.
- **Override a rule.** Copy it under the same name to `<agentDir>/rules/`
  (user) or `<cwd>/.omp/rules/` (project) and edit the copy. Native rules
  outrank plugin rules, so your copy wins and survives ycc updates. OMP
  reports no shadowing.
- **Disable a rule.** List it in `ttsr.disabledRules` in your `config.yml`:

  ```yaml
  ttsr:
    disabledRules: [ycc-web-design-quality]
  ```

- **Project rules apply at the `.omp` cwd only.** OMP reads
  `<cwd>/.omp/rules` and `<cwd>/.omp/config.yml` from the session's working
  directory, with no walk up to ancestors. Start omp in the directory that
  holds `.omp/`.
- **Disable the package** with `omp plugin disable ycc-rules@ycc`, or skip it
  at install with `--package ycc,ycc-mcp`.

`<agentDir>` is the active profile's agent directory; `omp config path`
prints it (`~/.omp/agent` by default).

## Global Instructions (`--rules`)

```bash
./install.sh install --target omp --rules
```

`--rules` symlinks `ycc/settings/rules/AGENTS.md` to `<agentDir>/AGENTS.md`,
OMP's user context file. A project `AGENTS.md` or `.omp/AGENTS.md` still
loads after it.

A real (non-symlink) `<agentDir>/AGENTS.md` is your content, and the installer
refuses to replace it:

```text
refusing to replace user-authored rules file: <agentDir>/AGENTS.md
```

Move it aside or re-run with `--force`. To keep your own file, import the ycc
instructions from it instead; OMP expands `@<path>` lines inline:

```markdown
@/path/to/ystack/ycc/settings/rules/AGENTS.md
```

## Settings And Model Roles (`--settings`)

```bash
./install.sh install --target omp --settings
```

`--settings` merges these ycc-owned leaves from `ycc/settings/omp/config.yml`
into your user `<agentDir>/config.yml` (or an existing `config.yaml`):

```yaml
modelRoles:
  default: 'anthropic/claude-fable-5-1:medium, openai/gpt-5.6-sol:high'
  slow: 'anthropic/claude-opus-5:high, openai/gpt-5.6-sol:high'
  task: 'anthropic/claude-opus-5:high, openai/gpt-5.6-sol:high'
tools:
  approvalMode: write
```

Each role is an ordered list: OMP uses the first model that resolves (has a
provider and credentials). The list covers model resolution only; it is not a
retry chain when a request to the resolved model fails. ycc agents use `@slow`
or `@task`, so these roles set their models. Other roles (`smol`, `plan`,
custom roles) and every other key are left alone. ycc never writes
`task.agentModelOverrides`.

- **Ownership.** Each leaf is tracked by hash in
  `~/.config/ycc/managed-config-state.json`. A run prints one summary line,
  `[ok] applied N managed update(s) and M removal(s) to <dest> (omp-config: settings)`,
  or `[ok] up-to-date: <dest> (omp-config: settings)` when nothing changed. A
  leaf you edited is kept on every update, with a warning such as
  `[!!] kept your local value at /modelRoles/slow (re-run with --force to take the repo value)`;
  `--force` replaces it. `--dry-run` lists each planned leaf as
  `would set /modelRoles/default` (or `would remove …`) and writes nothing.
- **`omp config set modelRoles …`** replaces the whole `modelRoles` record,
  so ycc roles you did not set disappear. The next `--settings` run adds them
  back and keeps the roles you set. To keep your own value, set it; to stop ycc
  managing settings, remove them (below).
- **Comments and formatting.** Rewriting the YAML drops comments and
  formatting, as `omp config set` does. Values keep their YAML 1.2 meaning
  (as OMP reads them), so `off`, `12:30` or `1_000` stay strings. Before any
  rewrite that would drop something (the file is not exactly ycc's own
  output), the installer saves the current file to `config.yml.ycc-backup`
  (mode 600) and warns. Backups are never overwritten: when that backup holds
  different bytes, the next one goes to `config.yml.ycc-backup.1`, `.2`, and
  so on. When `remove` deletes an emptied `config.yml`, it also deletes
  backups that hold only ycc's own output and keeps the rest.
- **Refusals.** A symlinked `config.yml` (for example from a dotfiles repo) is
  never written through; the installer prints the keys to add yourself and
  exits non-zero. An invalid YAML file, one whose root is not a mapping, or
  one that uses YAML aliases (`*name`, including `<<: *name` merge keys) is
  left unchanged, since a rewrite would expand them. `--target omp` needs
  PyYAML for `python3`; without it the installer stops before any write or
  `omp` call and prints the install command.
- **Precedence.** OMP layers defaults < user < project < `--config` overlays
  < runtime flags. A project `.omp/config.yml` beats these user values.
- **User scope only.** `--project` with `--settings` or `--rules` is rejected;
  ycc never writes `.omp/config.yml`, `.omp/rules` or `.omp/AGENTS.md`. Edit
  the project file by hand.
- **Missing credentials.** If no listed model resolves, OMP falls back to an
  available model.

Remove only the unchanged ycc leaves and the owned `AGENTS.md` symlink:

```bash
./install.sh remove --target omp --intent settings,rules
```

## Approvals

OMP's default `tools.approvalMode` is `yolo`. `--settings` sets `write`:
read and write tools are auto-approved, and `exec` tools prompt in the main
session. Limits:

- **Subagents run as `yolo`.** OMP forces task subagents to `yolo`, so `write`
  covers main-session prompts only. A per-tool `deny` still applies.
- **Project config wins.** A project `.omp/config.yml` can set any mode,
  including `yolo`, and OMP applies it without a trust prompt. To pin a mode
  for one session above project config, pass `--approval-mode <mode>`.
- **Headless runs.** With no UI, a prompt fails closed, so `omp -p` with
  `write` cannot run shell commands. Use `--approval-mode yolo` for trusted
  automation.

ycc never writes `yolo`, `bash.patterns` or per-tool `allow`/`deny`.

## Status Line

Unsupported. OMP has no command-backed status line, so ycc's
`statusline-command.sh` has no OMP form, and ycc ships no OMP extension.
OMP's built-in status line already shows the model, path and git state;
customize it with the `statusLine.*` keys (`omp config list`).

## herdr

herdr session reporting on OMP is herdr's own integration, not a ycc
package. ycc ships no OMP hook or extension for it.

1. Run `herdr integration install omp` once. It writes
   `~/.omp/agent/extensions/herdr-omp-agent-state.ts`.
2. For a named OMP profile, copy that file to
   `~/.omp/profiles/<name>/agent/extensions/`; herdr writes only the default
   profile path.
3. Restart your omp sessions; omp loads new extensions at session start.
4. Verify with `herdr integration status` and
   `herdr pane get "$HERDR_PANE_ID"` from an omp pane.

Install it once: a project copy under `.omp/extensions` loads twice, because
OMP dedupes extensions only by path. Do not add a hand-made reporter or port
`herdr-session-start.sh`: herdr records session identity only from `herdr:`
sources, and a `herdr:omp` reporter with the Cursor script's nanosecond `seq`
stalls herdr's own state reports.

## Project Scope

```bash
cd ~/code/my-project && ycc install --target omp --project
```

`--project` installs with `--scope project` in the git root of the current
directory. It is refused at `$HOME`; `cd` into a project or use the default
user scope (`--global`).

A project install shadows your user install inside that project. To return to
the user copy there, disable the project install:

```bash
omp plugin disable --scope project ycc@ycc
```

ycc never enables or disables plugins: a disabled install stays disabled
across updates and reinstalls.

A user-scope upgrade can make omp garbage-collect the cache a project install
still points at. The installer detects this and prints the repair command,
using the absolute path of the checkout's `install.sh`:

```bash
cd <project-root> && <checkout>/install.sh install --target omp --project
```

## Preview With `--dry-run`

```bash
./install.sh install --target omp --dry-run
./install.sh install --target omp --settings --rules --dry-run
./install.sh remove --target omp --only base --dry-run
```

`--dry-run` builds nothing and changes nothing. It prints each mutation as
`[dry-run] would run: omp …` and runs omp's own `--dry-run` check where omp
has one. `--settings` and `--rules` print the planned merge and link against
the default agent dir (`$PI_CODING_AGENT_DIR`, else `~/.omp/agent`), because
`omp config path` itself writes files. It works with `install`, `sync` and
`remove`, and only when every `--target` is `omp`.

## Force Reinstall

```bash
./install.sh install --target omp --force
./install.sh install --target omp --project --force
```

`--force` reinstalls the ycc-owned installs (`omp plugin install --force`)
and replaces an export directory that ycc did not record or that was edited.
It never takes over an install ycc did not create.

## Remove

```bash
./install.sh remove --target omp --only base             # user scope
./install.sh remove --target omp --only base --project   # this project
```

`remove` uninstalls only the installs ycc recorded for that scope. The `ycc`
marketplace and the export are removed only when nothing else still uses
them; otherwise the installer prints `kept marketplace ycc: <reason>`. When the
`ycc` marketplace now points somewhere ycc did not register (a fork with the
same name), recorded installs are dropped from the ycc record but never
uninstalled (`kept ycc@ycc (<scope>): marketplace ycc now points at …`).

## Migrate From Older Installs

```bash
./install.sh migrate --target omp           # dry-run
./install.sh migrate --target omp --apply
```

Migration retires two older setups without leaving duplicates:

- `omp plugin link` installs that point at this checkout's `packages/omp/`
  tree (foreign links are kept and reported);
- a `ycc` marketplace registered at the checkout root, which OMP falls back
  to the Claude catalog for. Its installs are uninstalled, the marketplace is
  removed, and the default native packages (`ycc`, `ycc-mcp` and `ycc-rules`) are
  installed in the same scopes.

Before anything is uninstalled, migration builds and validates the export.
It refuses (and changes nothing) while a legacy install is disabled, because
the native reinstall would come back enabled and ycc never toggles plugins
for you, or while a legacy install has no native OMP package
(`ycc-hooks`, `ycc-all` are excluded). The message names the exact `omp`
commands to run first. Project scope means the project root `install
--project` uses (the git toplevel, else the current directory).

If `--apply` stops partway (say, an omp install fails), the scopes still owed
a native install are recorded. Re-run `./install.sh migrate --target omp
--apply` to finish them, or run the printed
`<checkout>/install.sh install --target omp [--project]` commands.
A `ycc` marketplace registered at another source (a fork with the same name)
blocks the owed native install; migrate refuses before changing anything until
you remove it.

ycc skills in `~/.agents/skills` are also loaded by OMP. Migration and install
report them but never delete them; remove them with
`./install.sh remove --target agents --only base` (YAN-1176).

`migrate --target all` does not include OMP; run `migrate --target omp`
separately. Combined with other targets (`--target claude,omp`), every omp
refusal happens in the shared preflight, before any target changes.

## Profiles And XDG

The installer resolves every path through omp, so OMP profiles
(`OMP_PROFILE` or `omp --profile`) and the `$XDG_DATA_HOME/omp` data root
work unchanged. Ownership state is keyed per profile: run the installer once
per profile you want `ycc` in.

## Source Modes And `--target all`

Only `--mode local` (the default) works today. `--mode repo` needs a listed
OMP package and is refused until YAN-1180.

`--target all` includes OMP only once an OMP package is listed and
`omp >= 18.12.2` is on `PATH`. Until then it prints
`--target all: skipping omp (...)` and runs the other targets.

## OMP Notes

- Skills run as `/skill:<name>` and commands as `/ycc:<skill>`; agents are
  OMP task agents with `@role` models.
- OMP never runs shell hooks; `WorktreeCreate` has no OMP event; herdr
  reporting comes from herdr's integration (see [herdr](#herdr)). Rules ship
  in `ycc-rules`; settings, model roles and global instructions are opt-in
  installer steps (`--settings`, `--rules`).
- Details: [ADR 0002](../internal/adr/0002-omp-runtime-contract.md) and the
  [capability matrix](../../ycc/skills/_shared/references/target-capability-matrix.md).
