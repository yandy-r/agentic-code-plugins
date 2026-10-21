# shellcheck shell=bash
# claude.sh — the Claude target: implements the per-target contract that install.sh
# dispatches through (see scripts/lib/install/steps.sh):
#   claude_valid_steps, claude_intent_steps <intent>, claude_config_groups,
#   claude_supports_repo_mode, claude_reads_agents_skills, sync_claude_target, remove_claude_target
#
# Sourced by install.sh (never run directly); inherits SCRIPT_DIR and the
# shared helpers from core.sh / steps.sh / bundle.sh.

# claude_valid_steps — comma-separated steps Claude accepts for --only.
claude_valid_steps() { echo "base,skills,agents,commands,settings,rules,mcp,hooks,mods"; }

# claude_intent_steps <intent> — steps <intent> maps to; empty means no-op.
claude_intent_steps() {
    case "$1" in
        base|settings|rules|mcp) echo "$1" ;;
        # Hook activation lives in settings.json; hook scripts live in hooks/.
        hooks) echo "settings,hooks" ;;
        # Claude plugin enablement is pure settings.json state (enabledPlugins,
        # extraKnownMarketplaces). Add 'base' explicitly to also run the CLI's
        # marketplace registration, which needs network access.
        plugins) echo "settings" ;;
        # Mods install from the ycc-mods marketplace via the claude CLI.
        mods) echo "mods" ;;
        # skills/agents/commands install standalone entries into the tool's
        # own user dirs; 'base' ships the whole bundle/plugin.
        skills|agents|commands) echo "$1" ;;
        *) echo "" ;;
    esac
}

# claude_config_groups — default managed config groups for settings.json.
# The intent filter (and its order) lives in config_groups_for_target.
claude_config_groups() { echo "settings,hooks,plugins"; }

claude_supports_repo_mode() { return 0; }

# Claude Code does not read ~/.agents/skills.
claude_reads_agents_skills() { return 1; }

# ---------------------------------------------------------------------------
# Claude marketplace — registers ycc as a marketplace via the canonical CLI:
#
#   local mode:  claude plugin marketplace add <repo-path>            --scope user
#   repo  mode:  claude plugin marketplace add yandy-r/ystack --scope user
#                followed by:
#                claude plugin install ycc@ycc --scope user
#
# The CLI writes to ~/.claude/settings.json regardless of source type. That
# path is typically a symlink to ycc/settings/settings.json (via the
# 'settings' step), so we break the symlink first in BOTH modes — otherwise
# the CLI would follow the link and pollute the committed source-of-truth
# file with the marketplace registration.
#
# After this step, ~/.claude/settings.json is a REAL file. Re-running
# `install.sh install --target claude --only settings` would symlink over it and wipe
# the marketplace entry; the 'settings' step detects this and refuses
# without --force.
#
# CLI source form (verified via `claude plugin marketplace add --help`):
#   "Add a marketplace from a URL, path, or GitHub repo" — the
#   <owner>/<repo> slug is accepted directly for repo mode.
# ---------------------------------------------------------------------------
register_claude_marketplace() {
    local mode="${1:-local}"
    if [[ ! "$mode" =~ ^(local|repo)$ ]]; then
        err "register_claude_marketplace: invalid mode '${mode}' (expected local|repo)"
        exit 1
    fi

    command -v claude >/dev/null 2>&1 || {
        err "'claude' CLI is required but not found in PATH"
        exit 1
    }
    command -v python3 >/dev/null 2>&1 || { err "python3 is required but not found"; exit 1; }
    command -v realpath >/dev/null 2>&1 || { err "realpath is required but not found"; exit 1; }

    local source_arg
    if [[ "$mode" == "local" ]]; then
        source_arg="$(realpath "${SCRIPT_DIR}")"
    else
        source_arg="yandy-r/ystack"
    fi

    local settings="${HOME}/.claude/settings.json"

    # Break the symlink safely if it points into this repo (or anywhere).
    # We materialize the current content before the CLI writes to it.
    if [[ -L "${settings}" ]]; then
        local link_target
        link_target="$(readlink -f "${settings}")"
        info "${settings} is a symlink to ${link_target}"
        info "Breaking the symlink before CLI write (protects the committed source file from pollution)"
        local tmp
        tmp="$(mktemp)"
        cat "${settings}" > "${tmp}"
        rm "${settings}"
        mv "${tmp}" "${settings}"
    fi

    # Ensure parent dir exists (fresh $HOME case)
    mkdir -p "$(dirname "${settings}")"

    info "Running: claude plugin marketplace add ${source_arg} --scope user  (mode=${mode})"
    claude plugin marketplace add "${source_arg}" --scope user
    info "Running: claude plugin install ycc@ycc --scope user"
    claude plugin install ycc@ycc --scope user || warn "plugin install returned non-zero — check 'claude plugin list'"

    # Cleanup orphans from earlier broken attempts of this installer
    cleanup_claude_local_orphans
}

# claude_ycc_plugin_installed — print the registry file when ycc@ycc is installed.
claude_ycc_plugin_installed() {
    local registry="${HOME}/.claude/plugins/installed_plugins.json"
    [[ -f "${registry}" ]] && grep -q '"ycc@ycc"' "${registry}" && echo "${registry}"
    return 0
}

# Remove 'local-ycc-plugins' detritus from earlier (broken) versions of the
# installer that wrote to the wrong files with the wrong schema.
# ponytail: the inline Python here and in warn_sideloaded_mods stays inline;
# move it to a tested scripts/*.py helper if it grows or gains branches.
cleanup_claude_local_orphans() {
    local files=("${HOME}/.claude.json" "${HOME}/.claude/settings.local.json")
    local f
    for f in "${files[@]}"; do
        [[ -f "$f" ]] || continue
        python3 - "$f" <<'PY' || true
import json
import sys
from pathlib import Path

p = Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    sys.exit(0)
if not isinstance(data, dict):
    sys.exit(0)

changed = False
extras = data.get("extraKnownMarketplaces")
if isinstance(extras, dict) and "local-ycc-plugins" in extras:
    del extras["local-ycc-plugins"]
    if not extras:
        del data["extraKnownMarketplaces"]
    changed = True

enabled = data.get("enabledPlugins")
if isinstance(enabled, dict) and "ycc@local-ycc-plugins" in enabled:
    del enabled["ycc@local-ycc-plugins"]
    if not enabled:
        del data["enabledPlugins"]
    changed = True

if changed:
    # If the file is now empty after cleanup and it's settings.local.json,
    # just delete it rather than leaving an empty file.
    if not data and p.name == "settings.local.json":
        p.unlink()
        print(f"removed empty orphan file {p}")
    else:
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"removed orphaned 'local-ycc-plugins' entries from {p}")
PY
    done
}

# ---------------------------------------------------------------------------
# Claude mods (ycc/mods)
# ---------------------------------------------------------------------------
# Mods are Claude Code plugins whose hooks module (hooks/hooks.json
# "modules") hooks into Claude Code itself. They ship from their own local
# marketplace, 'ycc-mods', so each one installs, enables and uninstalls like
# any plugin, in the CLI and the desktop app alike. The marketplace is a
# directory source: Claude Code loads each mod in place from ycc/mods/<name>,
# so edits apply on /reload-plugins.
MODS_MARKETPLACE_NAME="ycc-mods"

# mods_plugin_names — echo one mod name per line from the mods marketplace.
mods_plugin_names() {
    python3 - "${SCRIPT_DIR}/ycc/mods/.claude-plugin/marketplace.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    for plugin in json.load(f).get("plugins", []):
        print(plugin["name"])
PY
}

# warn_sideloaded_mods — a mod also listed in CLAUDE_CODE_PLUGIN_DIRS (the
# per-machine sideload a mod is usually developed under) would load twice.
warn_sideloaded_mods() {
    local settings="${HOME}/.claude/settings.json"
    [[ -f "${settings}" ]] || return 0
    local dirs
    dirs="$(python3 - "${settings}" <<'PY' 2>/dev/null || true
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as f:
        env = json.load(f).get("env") or {}
except (OSError, ValueError):
    sys.exit(0)
print(env.get("CLAUDE_CODE_PLUGIN_DIRS", "") if isinstance(env, dict) else "")
PY
)"
    [[ -n "${dirs}" ]] || return 0
    local name
    while IFS= read -r name; do
        if [[ "${dirs}" == *"/${name}"* ]]; then
            warn "env.CLAUDE_CODE_PLUGIN_DIRS in ${settings} also loads a '${name}' folder (${dirs})."
            warn "Remove that entry, or '${name}' loads twice once the ${MODS_MARKETPLACE_NAME} plugin is enabled."
        fi
    done < <(mods_plugin_names)
}

# install_claude_mods — register the ycc-mods marketplace (local checkout)
# and install every mod it lists at user scope.
install_claude_mods() {
    command -v claude >/dev/null 2>&1 || {
        err "'claude' CLI is required but not found in PATH"
        exit 1
    }
    command -v python3 >/dev/null 2>&1 || { err "python3 is required but not found"; exit 1; }
    command -v realpath >/dev/null 2>&1 || { err "realpath is required but not found"; exit 1; }

    local mods_root
    mods_root="$(realpath "${SCRIPT_DIR}/ycc/mods")"
    [[ -f "${mods_root}/.claude-plugin/marketplace.json" ]] || {
        err "mods marketplace not found: ${mods_root}/.claude-plugin/marketplace.json"
        exit 1
    }

    info "Running: claude plugin marketplace add ${mods_root} --scope user"
    claude plugin marketplace add "${mods_root}" --scope user

    local name count=0
    while IFS= read -r name; do
        [[ -n "${name}" ]] || continue
        info "Running: claude plugin install ${name}@${MODS_MARKETPLACE_NAME} --scope user"
        claude plugin install "${name}@${MODS_MARKETPLACE_NAME}" --scope user \
            || warn "plugin install returned non-zero for '${name}' — check 'claude plugin list'"
        count=$((count + 1))
    done < <(mods_plugin_names)
    info "Installed ${count} mod(s) from ${mods_root}"

    warn_sideloaded_mods
}

# ---------------------------------------------------------------------------
# Claude target (settings + mcp; no base)
# ---------------------------------------------------------------------------
sync_claude_target() {
    validate_only_steps "claude"

    local ran=0
    local base_ran=0
    if step_enabled base; then
        if [[ "${MODE:-local}" == "repo" ]]; then
            printf '\n%sClaude: register github repo as marketplace (yandy-r/ystack)%s\n' "${BOLD}" "${NC}"
        else
            printf '\n%sClaude: register repo checkout as local marketplace%s\n' "${BOLD}" "${NC}"
        fi
        register_claude_marketplace "${MODE:-local}"
        ran=1
        base_ran=1
    fi
    if step_enabled settings; then
        printf '\n%sClaude: merge settings + copy statusline%s\n' "${BOLD}" "${NC}"
        # Structured merge keeps CLI-written marketplace entries and local
        # machine preferences while updating repo-managed model, hook and
        # plugin keys. This is safe even when 'base' ran in the same invocation.
        local claude_groups
        claude_groups="$(config_groups_for_target claude)"
        if [[ -n "${claude_groups}" ]]; then
            merge_settings_config \
                "claude-settings" \
                "${SCRIPT_DIR}/ycc/settings/settings.json" \
                "${HOME}/.claude/settings.json" \
                "${claude_groups}"
        fi
        if [[ ${#INTENTS[@]} -eq 0 ]] || intent_requested settings; then
            copy_settings_file "${SCRIPT_DIR}/ycc/settings/statusline-command.sh" "${HOME}/.claude/statusline-command.sh"
        fi
        ran=1
    fi
    if step_enabled rules; then
        printf '\n%sClaude: link rules (CLAUDE.md)%s\n' "${BOLD}" "${NC}"
        # Documented user memory filename; do not also install a pointer prompt.
        # Leave legacy AGENTS.md links intact; remove still unlinks owned links.
        # https://code.claude.com/docs/en/memory
        link_rules_file "${SCRIPT_DIR}/ycc/settings/rules/CLAUDE.md" "${HOME}/.claude/CLAUDE.md"
        ran=1
    fi
    if step_enabled mcp; then
        printf '\n%sClaude: %s MCP servers%s\n' "${BOLD}" "${COMMAND}" "${NC}"
        run_mcp_step claude
        ran=1
    fi
    if step_enabled hooks; then
        printf '\n%sClaude: link hooks directory into ~/.claude/hooks%s\n' "${BOLD}" "${NC}"
        # Directory-level symlink so new hook scripts are picked up automatically.
        # link_file refuses to replace a real directory at the destination, so an
        # existing ~/.claude/hooks (non-symlink) surfaces as an error rather than
        # being silently clobbered.
        link_file "${SCRIPT_DIR}/ycc/settings/hooks" "${HOME}/.claude/hooks"
        ran=1
    fi
    if step_enabled mods; then
        printf '\n%sClaude: install mods from the ycc-mods marketplace%s\n' "${BOLD}" "${NC}"
        install_claude_mods
        ran=1
        warn "Run /reload-plugins or start a new Claude Code session to load the mods."
    fi
    local slice skills_ran=0
    for slice in $(selected_slices skills agents commands); do
        # Skills are Claude's slash commands; install once for either alias.
        if [[ "${slice}" == "commands" ]]; then
            [[ ${skills_ran} -eq 1 ]] && continue
            slice="skills"
        fi
        printf '\n%sClaude: install standalone %s into ~/.claude/%s%s\n' "${BOLD}" "${slice}" "${slice}" "${NC}"
        run_slice claude "${slice}" select
        [[ "${slice}" == "skills" ]] && skills_ran=1
        ran=1
        if [[ -n "$(claude_ycc_plugin_installed)" ]]; then
            warn "The ycc plugin is also installed; its ${slice} now appear twice (ycc:<name> and <name>). Drop one: ${CLI_NAME} remove --target claude --intent base"
        fi
    done
    if [[ $ran -eq 0 ]]; then
        warn "Claude target ran no steps (pass --settings, --rules, --mcp, --hooks, or --only ...)"
    fi
    printf '\n%sClaude %s complete.%s\n' "${BOLD}" "${COMMAND}" "${NC}"
    if [[ $base_ran -eq 1 ]]; then
        if [[ "${MODE:-local}" == "repo" ]]; then
            warn "Run /reload-plugins or start a new Claude Code session. The 'ycc' marketplace in ~/.claude/settings.json now tracks the github source yandy-r/ystack."
            warn "Updates: rerun 'claude plugin install ycc@ycc --scope user' (or use the in-Claude /plugins UI) to pull the latest published commit."
            warn "The Claude settings file now contains the CLI-written marketplace entry. Re-running the settings step merges repo-managed keys and preserves that entry."
        else
            local claude_repo_root_msg
            claude_repo_root_msg="$(realpath "${SCRIPT_DIR}")"
            warn "Run /reload-plugins or start a new Claude Code session. The 'ycc' marketplace in ~/.claude/settings.json now points at ${claude_repo_root_msg} (directory source)."
            warn "Edits in ycc/ apply on plugin reload. No rsync, no cache clear."
            warn "The Claude settings file now contains the CLI-written marketplace entry. Re-running the settings step merges repo-managed keys and preserves that entry."
            warn "If you move or rename this repo, rerun ./install.sh install --target claude --only base."
        fi
    fi
}


# ---------------------------------------------------------------------------
# Claude remove
# ---------------------------------------------------------------------------
# run_claude_cli <args...> — a failed uninstall is reported, not fatal: the
# plugin or marketplace may simply not be registered.
run_claude_cli() {
    info "Running: claude $*"
    claude "$@" || warn "'claude $*' returned non-zero — check 'claude plugin list'"
}

require_claude_cli() {
    command -v claude >/dev/null 2>&1 || { err "'claude' CLI is required but not found in PATH"; exit 1; }
}

remove_claude_target() {
    validate_only_steps "claude"
    local claude_dir="${HOME}/.claude"

    if step_enabled mods; then
        printf '\n%sClaude: uninstall mods + the ycc-mods marketplace%s\n' "${BOLD}" "${NC}"
        require_claude_cli
        local name
        while IFS= read -r name; do
            [[ -n "${name}" ]] && run_claude_cli plugin uninstall "${name}@${MODS_MARKETPLACE_NAME}" --scope user
        done < <(mods_plugin_names)
        run_claude_cli plugin marketplace remove "${MODS_MARKETPLACE_NAME}" --scope user
    fi
    if step_enabled hooks; then
        printf '\n%sClaude: unlink hooks directory%s\n' "${BOLD}" "${NC}"
        unlink_owned_link "${SCRIPT_DIR}/ycc/settings/hooks" "${claude_dir}/hooks"
    fi
    if step_enabled mcp; then
        printf '\n%sClaude: remove MCP servers%s\n' "${BOLD}" "${NC}"
        run_mcp_step claude
    fi
    if step_enabled rules; then
        printf '\n%sClaude: unlink rules (CLAUDE.md + AGENTS.md)%s\n' "${BOLD}" "${NC}"
        unlink_owned_link "${SCRIPT_DIR}/ycc/settings/rules/CLAUDE.md" "${claude_dir}/CLAUDE.md"
        unlink_owned_link "${SCRIPT_DIR}/ycc/settings/rules/AGENTS.md" "${claude_dir}/AGENTS.md"
    fi
    if step_enabled settings; then
        printf '\n%sClaude: remove managed settings + statusline%s\n' "${BOLD}" "${NC}"
        remove_settings "claude-settings" "${SCRIPT_DIR}/ycc/settings/settings.json" \
            "${claude_dir}/settings.json" "$(config_groups_for_target claude)"
        if [[ ${#INTENTS[@]} -eq 0 ]] || intent_requested settings; then
            remove_copied_file "${SCRIPT_DIR}/ycc/settings/statusline-command.sh" "${claude_dir}/statusline-command.sh"
        fi
    fi
    remove_slices claude skills agents commands
    if step_enabled base; then
        printf '\n%sClaude: uninstall ycc + the ycc marketplace%s\n' "${BOLD}" "${NC}"
        require_claude_cli
        run_claude_cli plugin uninstall ycc@ycc --scope user
        run_claude_cli plugin marketplace remove ycc --scope user
    fi
    printf '\n%sClaude remove complete.%s\n' "${BOLD}" "${NC}"
}
