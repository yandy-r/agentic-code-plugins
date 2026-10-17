#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# install.sh — sync plugin assets to target IDE config directories
# ---------------------------------------------------------------------------

# Resolve symlinks so the linked `ycc` command (see 'cli') still finds the repo.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
CLI_NAME="ycc"
# shellcheck disable=SC2034  # read by steps.sh (target resolution).
ALL_TARGETS=(claude cursor codex opencode agents)

# shellcheck source=scripts/lib/install/core.sh
source "${SCRIPT_DIR}/scripts/lib/install/core.sh"
# shellcheck source=scripts/lib/install/steps.sh
source "${SCRIPT_DIR}/scripts/lib/install/steps.sh"
# shellcheck source=scripts/lib/install/bundle.sh
source "${SCRIPT_DIR}/scripts/lib/install/bundle.sh"
# shellcheck source=scripts/lib/install/cli.sh
source "${SCRIPT_DIR}/scripts/lib/install/cli.sh"
# shellcheck source=scripts/lib/install/migrate.sh
source "${SCRIPT_DIR}/scripts/lib/install/migrate.sh"
# Each target implements the contract described in its targets/<t>.sh header.
for _target in "${ALL_TARGETS[@]}"; do
    # shellcheck source=/dev/null
    source "${SCRIPT_DIR}/scripts/lib/install/targets/${_target}.sh"
done
unset _target

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [options]

Commands:
  install     Initial setup: base step plus opt-in steps (flags below).
              $(basename "$0") install --target <targets> [--mode <mode>] [--settings] [--rules] [--mcp] [--hooks] [--only <steps>] [--package <ids>] [--mcps <servers>] [--project|--global] [--force]
  sync        Sync what you name, nothing else.
              $(basename "$0") sync --target <targets> --intent <intents> [--mcps <servers>] [--mode <mode>] [--project|--global] [--force]
  remove      Strip installer-managed config.
              $(basename "$0") remove --target <targets> (--only <steps> | --intent <intents>) [--mcps <servers>] [--project|--global] [--force]
  migrate     Preview a global native-package migration (no writes by default).
              $(basename "$0") migrate --target claude|codex|cursor|all [--apply] [--marketplace-source <dir>]
              all resolves only claude,codex,cursor. --marketplace-source is Codex-only
              and must contain an eligible native ycc catalog (not a gate bypass).
  cli         Put this installer on PATH as '${CLI_NAME}'.
              $(basename "$0") cli [--dir <dir>] [--force]
  completion  Print or install shell completion.
              $(basename "$0") completion [--shell bash|zsh|fish] [--install [--force]]
  list-mcps   Print the MCP servers the repo manages (names for --mcps).
              $(basename "$0") list-mcps [--target <targets>]

A command is required; a bare '$(basename "$0") install --target ...' is rejected.

Sync plugin assets to an IDE configuration directory.

Command on PATH ('cli' / 'completion' subcommands):
  cli         Symlink this install.sh as '${CLI_NAME}' into the first of
              \$XDG_BIN_HOME, ~/.local/bin, ~/bin that is on PATH (else
              ~/.local/bin, with a warning). --dir overrides. Then run
              '${CLI_NAME} sync ...' from any project; --project targets the
              current directory's git toplevel.
  completion  Print the completion script for --shell (default: \$SHELL).
              --install symlinks it where the shell autoloads it:
                bash  \${BASH_COMPLETION_USER_DIR:-\${XDG_DATA_HOME:-~/.local/share}/bash-completion}/completions/${CLI_NAME}
                zsh   \${XDG_DATA_HOME:-~/.local/share}/zsh/site-functions/_${CLI_NAME}
                fish  \${XDG_CONFIG_HOME:-~/.config}/fish/completions/${CLI_NAME}.fish
  Both refuse to replace an existing file or foreign symlink without --force.

  ./install.sh cli && ${CLI_NAME} completion --install

The 'sync' subcommand is the recommended entry point: say WHAT you want synced
and each target maps it onto the steps it actually supports. Structured config
files are MERGED (repo-managed keys only), so local edits, tokens, trusted
projects and CLI-written marketplace entries survive. 'install' is the
step-flag form used for first-time setup.

  $(basename "$0") sync --target claude --intent hooks,settings,mcp,plugins
  $(basename "$0") sync --target codex,claude,opencode --intent mcp
  $(basename "$0") sync --target opencode --intent mcp --mcps github,linear
  $(basename "$0") sync --target claude --intent mods
  $(basename "$0") sync --target claude,codex --intent skills,agents

Intents (valid: base, skills, agents, commands, settings, rules, mcp, hooks,
plugins, mods):
  base      Install/register the target's whole bundle (claude/codex: the
            ycc plugin; cursor/opencode: the mirrored bundle dirs).
  skills    Standalone skills, one entry each, in the tool's own skills dir.
            On claude these skills are the slash commands; 'commands' below
            is an alias for this step there.
  agents    Standalone agents, one entry each, in the tool's own agents dir.
  commands  Slash-command surface. claude: alias for 'skills' (public skills
            are native slash invocations; a successful skills install also
            retires the command wrappers an older ycc wrote to
            ~/.claude/commands — only entries recorded in
            ~/.config/ycc/installed-units.json, never foreign files).
            opencode: one thin generated command per public skill, each
            loading its skill via the skill tool.

  Slices (skills/agents/commands) need no plugin. Each entry is copied with
  plugin-root paths and 'ycc:' prefixes rewritten so it works on its own;
  only entries ycc installed (or identical copies) are ever replaced or
  removed, so your own skills/agents in those dirs are left alone (--force
  overrides). Destinations:
    claude    ~/.claude/{skills,agents}/<name> (skills are the slash commands;
              'commands' installs the same skills — nothing lands in
              ~/.claude/commands)
    cursor    ~/.cursor/{skills,agents}/<name>
    codex     ~/.codex/skills/<name> (+ _shared), ~/.codex/agents/<name>.toml
    opencode  ~/.config/opencode/{skills,agents,commands}/<name> (+ shared/)
  The agents target ships ycc skills ONLY, once, into the cross-tool dir:
    agents    ~/.agents/skills/<name> (+ ~/.agents/ycc-shared/), read by Zed,
              Codex, opencode, Cursor, Gemini CLI, Copilot, Amp, Goose, Windsurf
  settings  Merge repo-managed config keys (models, effort levels, ...).
  rules     Link native global instructions (Cursor: manual Settings guidance).
  mcp       Merge MCP server definitions.
  hooks     Merge hook config; claude also links the hook scripts directory.
  plugins   Merge plugin enablement and marketplace entries. Add 'base' too
            when you also want the target's CLI to perform registration.
  mods      Install the Claude Code mods under ycc/mods (claude only for now).

  Intents a target cannot execute are reported and skipped. 'sync' is exclusive:
  it never implicitly runs 'base'.

  Intent → step mapping per target:
    claude    base→base  settings→settings  rules→rules  mcp→mcp
              hooks→settings+hooks  plugins→settings  mods→mods
              skills→skills  agents→agents  commands→skills (alias)
    cursor    base→base  skills→skills  agents→agents  settings→settings
              rules→rules  mcp→mcp
              commands, hooks, plugins, mods → no-op
    codex     base→base  skills→skills  agents→agents  settings→settings
              rules→rules  mcp→mcp  plugins → settings (config.toml)
              commands, hooks, mods → no-op
    opencode  base→base  skills→skills  agents→agents  commands→commands
              settings→settings  rules→rules  mcp→mcp
              plugins → settings (opencode.json)  hooks, mods → no-op
    agents    base→skills  skills→skills  everything else → no-op
              (~/.agents/skills + ycc-shared/ is the whole target)

Remove ('remove' subcommand):
  Undoes what the selected steps installed, for every target and intent (same
  intent → step mapping as 'sync'). Requires --only or --intent; rejects
  --mode. Only installer-owned things go:
    settings/plugins/hooks/mcp  managed config keys; keys you added are never
                                touched, a managed value you edited is kept
                                with a warning unless --force. A config file
                                left empty is deleted.
    rules, claude hooks dir     symlinks, only while they still point here.
    claude statusline script    only while identical to the repo (or --force).
    base                        claude: 'claude plugin uninstall ycc@ycc' +
                                marketplace remove; cursor/opencode: the
                                bundle entries from the synced dirs; codex:
                                plugin links, plugin cache, custom agents
                                and the marketplace.json entry.
    skills / agents / commands  the standalone entries ycc installed (or
                                that are still identical to the bundle);
                                never the plugin, never your own entries.
                                claude commands: only the legacy ~/.claude/
                                commands wrappers ycc recorded.
    mods (claude)               uninstall each mod + the ycc-mods marketplace.

  $(basename "$0") remove --target claude --only mcp            # project scope
  $(basename "$0") remove --target all --intent mcp --global    # user-global
  $(basename "$0") remove --target codex --intent settings,rules
  $(basename "$0") remove --target all --intent base,settings,rules,hooks,plugins,mods
  $(basename "$0") remove --target opencode --intent agents,commands

Scope (--project | --global, mutually exclusive):
  Without a flag, steps that support project scope use it; all others stay
  global. --project with a step lacking project support is an error. The
  project is the git toplevel of the current directory (else the directory).
  Project-capable steps today: mcp.

    target    mcp --project                   mcp --global
    claude    <project>/.mcp.json             ~/.claude.json
    cursor    <project>/.cursor/mcp.json      ~/.cursor/mcp.json
    codex     <project>/.codex/config.toml    ~/.codex/config.toml
              (Codex loads it only for trusted projects)
    opencode  <project>/opencode.json         ~/.config/opencode/opencode.json

Merge semantics (all structured config files):
  - Keys this repo declares as managed are written; every other key is kept.
  - A managed value the installer previously wrote is updated automatically.
  - A managed value YOU changed is preserved, with a warning; --force takes
    the repo value instead.
  - Ownership is tracked by hash in ~/.config/ycc/managed-config-state.json
    (hashes only — never values).

Options:
  --target <targets>  Comma-separated targets: claude, cursor, codex, opencode,
                      agents, or all (which must stand alone). Every target is
                      validated before any of them runs.
  --mode <mode>       Marketplace source mode (default: local). Supported:
                        local — register the local repo checkout as the
                                marketplace source. claude target adds the
                                local path as a directory marketplace; codex
                                target symlinks .codex-plugin/ycc/ into
                                ~/.codex/plugins/ycc/ and
                                ~/.agents/plugins/ycc, writes a {source:
                                local, path: ./.agents/plugins/ycc}
                                marketplace entry, then runs 'codex plugin
                                add'. cursor/opencode rsync the bundles.
                        repo  — register the upstream github repo
                                yandy-r/ystack as the marketplace
                                source. claude target adds the github slug
                                via the CLI; codex target writes a
                                {source: git-subdir,
                                url: https://github.com/yandy-r/ystack.git,
                                path: ./.codex-plugin/ycc,
                                ref: main} marketplace entry and skips
                                local generation/symlink/agents-sync.
                                cursor, opencode and agents REJECT --mode repo
                                (they have no remote-source concept).
                                With --target all + --mode repo, cursor,
                                opencode and agents are skipped with a warning.
  --settings          Additive: MERGE repo-managed keys into per-machine config
                      files while preserving local model choices, tokens,
                      marketplace entries written by the CLI, trusted-project
                      lists, and unknown keys. Managed values changed locally
                      are preserved unless --force is passed. Non-structured
                      companion files (for example the Claude statusline script)
                      still use copy semantics.
                      Mode-agnostic. Scope per target:
                        claude   — settings.json, statusline-command.sh
                        codex    — config.toml
                        opencode — opencode.json
                        cursor   — cli-config.json (CLI model preference)
  --rules             Additive: SYMLINK rules files so edits flow across
                      systems (this is the old --settings behavior for rules).
                      Refuses to replace a real rules file without --force;
                      replaces existing symlinks idempotently. Mode-agnostic.
                      Scope per target:
                        claude   — CLAUDE.md at ~/.claude/
                        cursor   — manual User Rules in Settings; no file links
                        codex    — default.rules + AGENTS.md at ~/.codex/
                        opencode — AGENTS.md at ~/.config/opencode/
  --mcp               Additive: also run the target's 'mcp' step. Mode-agnostic.
                      Scope follows --project (default) / --global.
  --mcps <servers>    Comma-separated MCP servers to merge (or remove) instead
                      of every managed one; requires the mcp step. Servers not
                      named are left untouched. A target that manages none of
                      them skips its MCP step; a name no selected target
                      manages is an error. Names: '$(basename "$0") list-mcps'
                      (shell completion offers them).
  --project           Scope-capable steps (today: mcp) write into the current
                      project. Default when neither flag is given.
  --global            Scope-capable steps write into user-global config.
  --hooks             Additive: also run the target's 'hooks' step.
                      Currently supported by the claude target only; silently
                      ignored by targets without hook support. Mode-agnostic.
  --force             Let repo-managed config values win over local edits, and
                      replace real rules files with repo symlinks when needed.
                      Unknown/unmanaged config keys are never removed.
  --only <steps>      Exclusive: run only the comma-separated steps
                      (e.g. --only settings, --only rules,settings).
                      Overrides defaults and --settings/--rules/--mcp/--hooks.
                      A skills/agents/commands step a target has no home for
                      is skipped with a notice (e.g. commands on cursor).
  --skills-home <dir> Resolve duplicate skills when ycc skills would land in
                      several of codex/opencode/cursor's own skills dirs (all
                      read ~/.agents/skills too):
                        agents — skills once in ~/.agents/skills (agents
                                 target); each tool keeps only its non-skill
                                 pieces natively (codex: ~/.codex/agents slice
                                 instead of plugin registration).
                        native — keep per-tool native skills (duplicates
                                 possible). Without the flag, an interactive
                                 prompt offers the choice (non-TTY: warn and
                                 proceed as requested).
  --intent <intents>  'sync' / 'remove' subcommands only. Comma-separated intents (see
                      above). Cannot be combined with --only or the additive
                      --settings/--rules/--mcp/--hooks flags.
  --package <ids>     'install' only. Comma-separated ids from the package model:
                      ycc, ycc-mcp, ycc-hooks (Claude only), ycc-rules (Cursor only).
                      Expands dependency and installer-fallback components into
                      existing installer steps. Only the already-listed Claude
                      and Codex ycc entries use native registration; unlisted
                      packages use file/config delivery, never new catalog entries.
                      Codex agents are always copied (including --mode repo).
                      A foreign Codex ycc is skipped only when enabled AND its
                      installed payload is valid; stale config or caches do not
                      suppress registration. Cursor copies only the units a
                      package names (ycc-rules never copies skills/agents).
                      A package whose own components cannot all be delivered
                      (Cursor ycc: commands; ycc-hooks: hooks) fails before any
                      writes; --target all warns and skips that target.
                      Cannot combine with --intent, --only or additive flags.
  --help              Show this help message

install semantics:
  Default (no --only):
    - Run the target's 'base' step (if any).
    - Additionally run 'settings' / 'rules' / 'mcp' / 'hooks' if their flag is
      passed.
  With --only <steps>:
    - Run exactly the listed steps. Nothing else.
  With --package <ids>:
    - Run the validated closure's deliverable steps for each selected target.
    - Example: $(basename "$0") install --package ycc,ycc-mcp --target claude

  Transport semantics:
    - --settings (copy)   dest absent: cp; dest is a symlink: warn + rm + cp;
                          dest is a real file: error unless --force.
    - --rules    (symlink) idempotent link; refuses to replace a real file
                          without --force.

Target steps:
  claude    base | skills | agents | commands | settings | rules | mcp | hooks | mods
            base:     invoke 'claude plugin marketplace add <repo> --scope user'
                      + 'claude plugin install ycc@ycc --scope user'. Breaks
                      ~/.claude/settings.json symlink (if any) first so the CLI
                      write doesn't pollute the committed source file. Edits
                      in ycc/ apply on /reload-plugins.
            settings: MERGE managed keys from ycc/settings/settings.json into
                      ~/.claude/settings.json and COPY statusline-command.sh.
                      Local edits and CLI-written marketplace entries are
                      preserved unless --force resolves a managed conflict.
            rules:    symlink ycc/settings/rules/CLAUDE.md into
                      ~/.claude/.
            mcp:      merge mcp-configs/mcp.json mcpServers into <project>/.mcp.json
                      (--project, default) or ~/.claude.json (--global).
            hooks:    symlink ycc/settings/hooks/ into ~/.claude/hooks/, enabling
                      the WorktreeCreate hook (keeps harness-managed
                      worktrees inside <repo>/.claude/worktrees/).
            mods:     'claude plugin marketplace add ycc/mods --scope user'
                      (the local 'ycc-mods' marketplace) + 'claude plugin
                      install <mod>@ycc-mods --scope user' for each mod it
                      lists. Mods load in place; edits apply on /reload-plugins.
            skills / agents / commands:
                      copy ycc/{skills,agents,commands} entries into
                      ~/.claude/<slice>/ (paths re-pointed, 'ycc:' dropped).
                      With the ycc plugin also installed they appear twice.
  cursor    base | skills | agents | settings | mcp | rules
            base:     generate + validate + format + rsync bundle to ~/.cursor/.
            skills:   generate + install each skill into ~/.cursor/skills/.
            agents:   generate + install each agent into ~/.cursor/agents/.
            settings: merge packages/cursor/installer-fallback/config/cli-config.json into
                      ~/.cursor/cli-config.json (main CLI model preference).
            mcp:      merge mcp-configs/mcp.json mcpServers into
                      <project>/.cursor/mcp.json or ~/.cursor/mcp.json.
            rules:    print manual User Rules instructions (Settings → Rules).
                      File-based user-global provisioning is unsupported/unverified;
                      no ~/.cursor/CLAUDE.md or AGENTS.md links are created.
                      Cursor sub-agent models are set per generated agent file
                      in packages/cursor/ycc/agents/, not in cli-config.json.
  codex     base | skills | agents | settings | rules | mcp
            base:     generate + validate + format + sync custom agents, then
                      register the repo's .codex-plugin/ycc/ as a local
                      marketplace source in ~/.agents/plugins/marketplace.json
                      via ~/.agents/plugins/ycc -> .codex-plugin/ycc/, then
                      installs + enables it with 'codex plugin add
                      ycc@local-ycc-plugins' (Codex 0.160+; older builds get
                      the legacy hand-written cache).
                      Rerun this step after ./scripts/sync.sh --only codex to
                      refresh Codex's snapshot of the plugin.
            skills:   generate + install each skill into ~/.codex/skills/
                      (shared helpers at ~/.codex/skills/_shared). No plugin
                      link, cache or marketplace entry.
            agents:   generate + install each custom agent into ~/.codex/agents/.
            settings: MERGE managed keys from .codex-plugin/config/config.toml
                      into ~/.codex/config.toml. Comments, trusted projects,
                      MCP bearer tokens, connector entries and unknown tables
                      are preserved; the 'plugins' intent maps here too.
            mcp:      merge [mcp_servers.*] from .codex-plugin/config/config.toml
                      into <project>/.codex/config.toml or ~/.codex/config.toml.
            rules:    symlink .codex-plugin/config/default.rules AND
                      ycc/settings/rules/AGENTS.md into ~/.codex/.
  opencode  base | skills | agents | commands | settings | rules | mcp
            base:     generate + validate + format + rsync skills/agents/commands
                      into ~/.config/opencode/.
            skills:   generate + install each skill into skills/ (+ shared/).
            agents:   generate + install each agent into agents/.
            commands: generate + install each command into commands/.
            settings: MERGE managed keys from .opencode-plugin/opencode.json
                      into ~/.config/opencode/opencode.json. Local model
                      choices, provider credentials and unknown keys are
                      preserved; the 'plugins' intent maps here too.
            mcp:      merge mcp.servers from .opencode-plugin/opencode.json into
                      <project>/opencode.json or ~/.config/opencode/opencode.json.
            rules:    symlink .opencode-plugin/AGENTS.md into
                      ~/.config/opencode/ (generator-produced from
                      ycc/settings/rules/CLAUDE.md — the same user-global
                      ruleset as every other target).
  agents    base | skills (both run the same thing)
            base/skills:  generate + validate the .agents-plugin bundle, then
                      install each skill into ~/.agents/skills/ (+ shared
                      helpers in ~/.agents/ycc-shared/). Foreign skills and
                      ~/.agents/plugins/ are never touched.
  all       Run claude then cursor then codex then opencode then agents; step
            flags propagate.

Examples:
  $(basename "$0") install --target claude                         # base only (register local marketplace)
  $(basename "$0") install --target claude --only base             # same, exclusive
  $(basename "$0") install --target claude --settings --rules      # base + merge settings + link rules
  $(basename "$0") install --target claude --settings --rules --mcp
  $(basename "$0") install --target claude --only settings         # copy settings only
  $(basename "$0") install --target claude --only rules            # link rules only
  $(basename "$0") install --target claude --only mcp            # project .mcp.json
  $(basename "$0") install --target claude --only mcp --global   # ~/.claude.json
  $(basename "$0") install --target claude --settings --force      # repo values win for managed-key conflicts
  $(basename "$0") install --target claude --hooks                 # base + WorktreeCreate hook
  $(basename "$0") install --target claude --only hooks            # hooks only
  $(basename "$0") install --target cursor                         # base only
  $(basename "$0") install --target cursor --mcp                   # base + mcp
  $(basename "$0") install --target cursor --rules                 # base + manual User Rules guidance
  $(basename "$0") install --target cursor --only rules            # rules only
  $(basename "$0") install --target codex --settings --rules       # base + merge config + link rules
  $(basename "$0") install --target codex --only settings          # merge config.toml only
  $(basename "$0") install --target codex --only rules             # link default.rules + AGENTS.md
  $(basename "$0") install --target opencode                       # base only
  $(basename "$0") install --target opencode --settings --rules    # base + merge opencode.json + link AGENTS.md
  $(basename "$0") install --target opencode --only skills,agents  # just skills + agents
  $(basename "$0") install --target agents                         # ycc skills → ~/.agents/skills
  $(basename "$0") install --target codex,opencode --skills-home agents  # skills shared via ~/.agents/skills
  $(basename "$0") install --target codex --only agents            # just ~/.codex/agents
  $(basename "$0") install --target all --only agents              # agents everywhere, no plugins
  $(basename "$0") install --target all --settings --rules --mcp
  $(basename "$0") install --target claude,codex --only rules      # rules for two targets
  $(basename "$0") install --target all --rules --force            # force-replace user-authored rules files

  # Upgrading from the symlink-based --settings (<= pre-split): the first run of
  # --settings detects the existing symlink at each destination and replaces it
  # with a copy (emits an info/warn line per file). No --force needed.

  # Repo mode (track the upstream github repo instead of the local checkout):
  $(basename "$0") install --target claude --mode repo             # register yandy-r/ystack
                                                                     # as a github marketplace source
  $(basename "$0") install --target codex  --mode repo             # write the codex marketplace.json
                                                                     # with {source: git-subdir, url: ...,
                                                                     # path: ./.codex-plugin/ycc,
                                                                     # ref: main}; skip symlink/rsync
  $(basename "$0") install --target all    --mode repo             # claude + codex in repo mode;
                                                                     # cursor/opencode are skipped
  $(basename "$0") install --target claude --mode repo --settings --rules
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
TARGET=""
TARGETS=()
MODE="local"
MODE_SET=0
SKILLS_HOME=""
COMMAND=""
MCP=0
SETTINGS=0
RULES=0
HOOKS=0
FORCE=0
EXCLUSIVE_STEPS=0
ONLY_STEPS=()
INTENTS=()
PACKAGE=""
PACKAGE_CONFLICT_FLAG=0
MCP_SERVERS=()
SCOPE=""

case "${1:-}" in
    migrate) shift; run_migrate_command "$@"; exit $? ;;
    cli|completion|list-mcps)
        for arg in "$@"; do
            if [[ "${arg}" == "--package" || "${arg}" == --package=* ]]; then
                err "--package is only supported by the 'install' subcommand"
                exit 1
            fi
        done
        case "$1" in
            cli)        shift; run_cli_command "$@"; exit 0 ;;
            completion) shift; run_completion_command "$@"; exit 0 ;;
            list-mcps)  shift; run_list_mcps_command "$@"; exit 0 ;;
        esac
        ;;
esac

case "${1:-}" in
    install|sync|remove) COMMAND="$1"; shift ;;
    --help|-h) usage; exit 0 ;;
    "") usage; exit 1 ;;
    *)
        err "missing or unknown command '$1' (expected: install, sync, remove, migrate, cli, completion, list-mcps)"
        err "  e.g. $(basename "$0") install $*"
        exit 1
        ;;
esac

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)
            [[ $# -lt 2 ]] && { err "--target requires an argument"; exit 1; }
            TARGET="$2"
            shift 2
            ;;
        --mode)
            [[ $# -lt 2 ]] && { err "--mode requires an argument (local|repo)"; exit 1; }
            MODE="$2"
            MODE_SET=1
            if [[ ! "$MODE" =~ ^(local|repo)$ ]]; then
                err "Invalid --mode: ${MODE} (supported: local, repo)"
                exit 1
            fi
            shift 2
            ;;
        --package)
            if [[ "${COMMAND}" != "install" ]]; then
                err "--package is only supported by the 'install' subcommand"
                exit 1
            fi
            [[ $# -lt 2 ]] && { err "--package requires an argument (a comma-separated list of package ids)"; exit 1; }
            [[ "$2" == --* ]] && { err "--package requires an argument (a comma-separated list of package ids)"; exit 1; }
            [[ -n "$2" ]] || { err "--package contains an empty value"; exit 1; }
            PACKAGE="$2"
            shift 2
            ;;
        --only)
            PACKAGE_CONFLICT_FLAG=1
            [[ $# -lt 2 ]] && { err "--only requires a comma-separated list of steps"; exit 1; }
            IFS=',' read -r -a ONLY_STEPS <<< "$2"
            if [[ ${#ONLY_STEPS[@]} -eq 0 ]]; then
                err "--only requires at least one step"
                exit 1
            fi
            shift 2
            ;;
        --skills-home)
            [[ $# -lt 2 ]] && { err "--skills-home requires an argument (agents|native)"; exit 1; }
            SKILLS_HOME="$2"
            if [[ ! "${SKILLS_HOME}" =~ ^(agents|native)$ ]]; then
                err "Invalid --skills-home: ${SKILLS_HOME} (supported: agents, native)"
                exit 1
            fi
            shift 2
            ;;
        --intent)
            PACKAGE_CONFLICT_FLAG=1
            [[ $# -lt 2 ]] && { err "--intent requires a comma-separated list of intents"; exit 1; }
            IFS=',' read -r -a INTENTS <<< "$2"
            shift 2
            ;;
        --mcp)
            MCP=1
            shift
            ;;
        --mcps)
            [[ $# -lt 2 ]] && { err "--mcps requires a comma-separated list of MCP servers"; exit 1; }
            parse_mcp_servers "$2"
            shift 2
            ;;
        --settings)
            SETTINGS=1
            shift
            ;;
        --rules)
            RULES=1
            shift
            ;;
        --hooks)
            HOOKS=1
            shift
            ;;
        --project|--global)
            if [[ -n "${SCOPE}" && "${SCOPE}" != "${1#--}" ]]; then
                err "--project and --global are mutually exclusive"
                exit 1
            fi
            SCOPE="${1#--}"
            shift
            ;;
        --force)
            # shellcheck disable=SC2034  # read by core.sh, cli.sh, and bundle.sh
            FORCE=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ -z "${TARGET}" ]]; then
    err "Missing required --target flag"
    usage
    exit 1
fi

if [[ "${COMMAND}" == "remove" ]]; then
    # remove never guesses: say exactly what to remove.
    if [[ "${SETTINGS}" == "1" || "${RULES}" == "1" || "${MCP}" == "1" || "${HOOKS}" == "1" ]]; then
        err "remove does not accept --settings, --rules, --mcp, or --hooks (use --only or --intent)"
        exit 1
    fi
    if [[ "${MODE_SET}" == "1" ]]; then
        err "remove does not accept --mode (it undoes local and repo installs alike)"
        exit 1
    fi
    if [[ ${#ONLY_STEPS[@]} -eq 0 && ${#INTENTS[@]} -eq 0 ]]; then
        err "remove requires --only <steps> or --intent <intents>"
        exit 1
    fi
fi

if [[ -n "${PACKAGE}" ]]; then
    if [[ "${COMMAND}" != "install" ]]; then
        err "--package is only supported by the 'install' subcommand"
        exit 1
    fi
    if [[ "${PACKAGE_CONFLICT_FLAG}" == 1 || "${SETTINGS}" == "1" || "${RULES}" == "1" || "${MCP}" == "1" || "${HOOKS}" == "1" ]]; then
        err "--package cannot be combined with --intent, --only, --settings, --rules, --mcp, or --hooks"
        exit 1
    fi
fi

if [[ ${#INTENTS[@]} -gt 0 && "${COMMAND}" != "install" ]]; then
    if [[ ${#ONLY_STEPS[@]} -gt 0 || "${SETTINGS}" == "1" || "${RULES}" == "1" || "${MCP}" == "1" || "${HOOKS}" == "1" ]]; then
        err "${COMMAND} --intent cannot be combined with --only, --settings, --rules, --mcp, or --hooks"
        exit 1
    fi

    declare -A seen_intents=()
    unique_intents=()
    for intent in "${INTENTS[@]}"; do
        if [[ -z "${intent}" ]]; then
            err "--intent contains an empty value"
            exit 1
        fi
        intent_valid=0
        for allowed in "${VALID_INTENTS[@]}"; do
            [[ "${intent}" == "${allowed}" ]] && intent_valid=1 && break
        done
        if [[ ${intent_valid} -eq 0 ]]; then
            err "unknown intent '${intent}' (valid: ${VALID_INTENTS[*]})"
            exit 1
        fi
        if [[ -z "${seen_intents[${intent}]:-}" ]]; then
            unique_intents+=("${intent}")
            seen_intents["${intent}"]=1
        fi
    done
    INTENTS=("${unique_intents[@]}")
elif [[ "${COMMAND}" == "sync" ]]; then
    err "sync requires --intent <intent,...>"
    exit 1
elif [[ ${#INTENTS[@]} -gt 0 ]]; then
    err "--intent requires the 'sync' or 'remove' subcommand"
    exit 1
fi

if [[ ${#ONLY_STEPS[@]} -gt 0 ]]; then
    EXCLUSIVE_STEPS=1
    if [[ "${SETTINGS}" == "1" ]]; then
        warn "--settings is ignored when --only is used"
    fi
    if [[ "${RULES}" == "1" ]]; then
        warn "--rules is ignored when --only is used"
    fi
    if [[ "${MCP}" == "1" ]]; then
        warn "--mcp is ignored when --only is used"
    fi
    if [[ "${HOOKS}" == "1" ]]; then
        warn "--hooks is ignored when --only is used"
    fi
fi

resolve_targets "${TARGET}"
[[ "${COMMAND}" == "remove" ]] || print_native_deprecation_hints "${TARGETS[@]}"
if [[ -n "${PACKAGE}" ]]; then
    [[ "${TARGET}" == "all" ]] && PACKAGE_ALL_TARGETS_REQUESTED=1
    package_preflight_targets
    resolve_skills_home
    run_package_targets
else
    resolve_skills_home
    preflight_targets
    action="sync"
    [[ "${COMMAND}" == "remove" ]] && action="remove"
    for target in "${TARGETS[@]}"; do
        run_target "${target}" "${action}_${target}_target"
    done
fi
