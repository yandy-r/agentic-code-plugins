# shellcheck shell=bash
# claude-mods.sh — the Claude mods step (ycc/mods): install and remove the
# ycc-mods marketplace's plugins, narrowed by --mods.
#
# Mods are Claude Code plugins whose hooks module (hooks/hooks.json
# "modules") hooks into Claude Code itself. They ship from their own local
# marketplace, 'ycc-mods', so each one installs, enables and uninstalls like
# any plugin, in the CLI and the desktop app alike. The marketplace is a
# directory source: Claude Code loads each mod in place from ycc/mods/<name>,
# so edits apply on /reload-plugins.
#
# Sourced by targets/claude.sh (never run directly); uses info/warn/err from
# core.sh, has_selection / selection_for_target from select.sh, and
# run_claude_cli / require_claude_cli from claude.sh at call time.
# ponytail: the inline Python here stays inline; move it to a tested
# scripts/*.py helper if it grows or gains branches.

MODS_MARKETPLACE_NAME="ycc-mods"

# claude_mods_root — the mods marketplace directory: YCC_MODS_ROOT (a test
# seam for a fixture marketplace), else the checkout's ycc/mods.
claude_mods_root() {
    echo "${YCC_MODS_ROOT:-${SCRIPT_DIR}/ycc/mods}"
}

# mods_plugin_names — echo one mod name per line from the mods marketplace.
mods_plugin_names() {
    python3 - "$(claude_mods_root)/.claude-plugin/marketplace.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    for plugin in json.load(f).get("plugins", []):
        print(plugin["name"])
PY
}

# claude_mods_run_names — the mods this run acts on, one per line: the
# --mods selection, else every mod the marketplace lists.
claude_mods_run_names() {
    if has_selection mods; then
        selection_for_target mods claude | tr ',' '\n'
    else
        mods_plugin_names
    fi
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
        [[ -n "${name}" ]] || continue
        if [[ "${dirs}" == *"/${name}"* ]]; then
            warn "env.CLAUDE_CODE_PLUGIN_DIRS in ${settings} also loads a '${name}' folder (${dirs})."
            warn "Remove that entry, or '${name}' loads twice once the ${MODS_MARKETPLACE_NAME} plugin is enabled."
        fi
    done < <(claude_mods_run_names)
}

# install_claude_mods — register the ycc-mods marketplace (local checkout)
# and install the run's mods (every listed one, or the --mods selection) at
# user scope.
install_claude_mods() {
    require_claude_cli
    command -v python3 >/dev/null 2>&1 || { err "python3 is required but not found"; exit 1; }
    command -v realpath >/dev/null 2>&1 || { err "realpath is required but not found"; exit 1; }

    local mods_root
    mods_root="$(realpath "$(claude_mods_root)")"
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
    done < <(claude_mods_run_names)
    info "Installed ${count} mod(s) from ${mods_root}"

    warn_sideloaded_mods
}

# claude_mods_still_enabled <selected-csv> — the other '<name>@ycc-mods'
# keys in ~/.claude/settings.json enabledPlugins (selected names excluded, so
# a CLI that has not rewritten settings yet does not keep the marketplace
# alive), comma-separated; empty when none remain.
claude_mods_still_enabled() {
    local settings="${HOME}/.claude/settings.json"
    [[ -f "${settings}" ]] || return 0
    python3 - "${settings}" "${MODS_MARKETPLACE_NAME}" "$1" <<'PY' 2>/dev/null || true
import json
import sys

path, marketplace, selected = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
try:
    with open(path, encoding="utf-8") as f:
        enabled = json.load(f).get("enabledPlugins") or {}
except (OSError, ValueError, AttributeError):
    sys.exit(0)
if not isinstance(enabled, dict):
    sys.exit(0)
skip = {f"{name}@{marketplace}" for name in selected if name}
print(",".join(key for key in enabled if key.endswith(f"@{marketplace}") and key not in skip))
PY
}

# remove_claude_mods — uninstall the run's mods. Without --mods the
# ycc-mods marketplace goes too; with --mods it stays while another ycc mod
# is still in enabledPlugins.
remove_claude_mods() {
    require_claude_cli
    local name
    while IFS= read -r name; do
        [[ -n "${name}" ]] && run_claude_cli plugin uninstall "${name}@${MODS_MARKETPLACE_NAME}" --scope user
    done < <(claude_mods_run_names)
    if has_selection mods; then
        local others
        others="$(claude_mods_still_enabled "$(selection_for_target mods claude)")"
        if [[ -n "${others}" ]]; then
            info "kept the ${MODS_MARKETPLACE_NAME} marketplace: ${HOME}/.claude/settings.json enabledPlugins still lists ${others//,/, }"
            return 0
        fi
    fi
    run_claude_cli plugin marketplace remove "${MODS_MARKETPLACE_NAME}" --scope user
}
