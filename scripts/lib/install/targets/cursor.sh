# shellcheck shell=bash
# cursor.sh — the Cursor target: implements the per-target contract that install.sh
# dispatches through (see scripts/lib/install/steps.sh):
#   cursor_valid_steps, cursor_intent_steps <intent>, cursor_config_groups,
#   cursor_supports_repo_mode, cursor_reads_agents_skills, sync_cursor_target, remove_cursor_target
#
# Sourced by install.sh (never run directly); inherits SCRIPT_DIR and the
# shared helpers from core.sh / steps.sh / bundle.sh.

CURSOR_PLUGIN_DIR="${SCRIPT_DIR}/.cursor-plugin"
CURSOR_CLI_CONFIG_SRC="${SCRIPT_DIR}/.cursor-plugin/config/cli-config.json"

# cursor_valid_steps — comma-separated steps Cursor accepts for --only.
cursor_valid_steps() { echo "base,skills,agents,settings,rules,mcp"; }

# cursor_intent_steps <intent> — steps <intent> maps to; empty means no-op.
cursor_intent_steps() {
    case "$1" in
        skills|agents) echo "$1" ;;
        # Cursor has no command layer.
        commands) echo "" ;;
        base|rules|mcp) echo "$1" ;;
        settings) echo "settings" ;;
        hooks|plugins) echo "" ;;
        # Mods are Claude Code only for now. A target gains them by mapping
        # 'mods' to a step that translates ycc/mods/<name> into that tool's
        # extension format; until then the intent is reported and skipped.
        mods) echo "" ;;
        *) echo "" ;;
    esac
}

# cursor_config_groups — default managed config groups for cli-config.json.
cursor_config_groups() { echo "settings"; }

# Cursor reads bundles from local directories only.
cursor_supports_repo_mode() { return 1; }

# Cursor reads ~/.agents/skills plus ~/.cursor/skills; installing both duplicates them.
cursor_reads_agents_skills() { return 0; }
# cursor_native_skills_dirs — where this target installs ycc skills natively.
cursor_native_skills_dirs() { printf '%s\n' "${HOME}/.cursor/skills"; }

# ---------------------------------------------------------------------------
# Cursor sync (base + optional MCP + optional settings/rules)
# ---------------------------------------------------------------------------
sync_cursor_target() {
    validate_only_steps "cursor"

    local cursor_dir="${HOME}/.cursor"
    local scripts_dir="${SCRIPT_DIR}/scripts"

    command -v python3 >/dev/null 2>&1 || { err "python3 is required but not found"; exit 1; }

    mkdir -p "${cursor_dir}"

    # 'base' ships every bundle unit; 'skills' / 'agents' ship one each.
    local -a units=()
    read -r -a units <<< "$(skills_filter cursor "$(selected_bundle_units skills agents rules)")"
    local do_bundle=0 do_settings=0 do_mcp=0 do_rules=0
    [[ ${#units[@]} -gt 0 ]] && do_bundle=1
    step_enabled settings && do_settings=1
    step_enabled mcp && do_mcp=1
    step_enabled rules && do_rules=1

    [[ $do_bundle -eq 1 ]] && { command -v rsync >/dev/null 2>&1 || { err "rsync is required but not found"; exit 1; }; }

    if [[ $do_bundle -eq 0 && $do_settings -eq 0 && $do_mcp -eq 0 && $do_rules -eq 0 ]]; then
        warn "Cursor target ran no steps"
        printf '\n%sCursor %s complete.%s\n' "${BOLD}" "${COMMAND}" "${NC}"
        return 0
    fi

    local total=0
    [[ $do_bundle -eq 1 ]] && total=$((total + 4))
    [[ $do_settings -eq 1 ]] && total=$((total + 1))
    [[ $do_mcp -eq 1 ]] && total=$((total + 1))
    [[ $do_rules -eq 1 ]] && total=$((total + 1))
    local step=0

    if [[ $do_bundle -eq 1 ]]; then
        if [[ ! -d "${CURSOR_PLUGIN_DIR}" ]]; then
            err "Cursor plugin source directory not found: ${CURSOR_PLUGIN_DIR}"
            exit 1
        fi

        # Each unit has its own generator + validator: generate-cursor-<unit>.sh.
        local unit
        for unit in "${units[@]}"; do
            require_scripts "${scripts_dir}/generate-cursor-${unit}.sh" "${scripts_dir}/validate-cursor-${unit}.sh"
        done

        step=$((step + 1))
        printf '\n%s[%d/%d] Generate Cursor-native bundle (%s)%s\n' "${BOLD}" "$step" "$total" "${units[*]}" "${NC}"
        for unit in "${units[@]}"; do
            run_build_script "${scripts_dir}/generate-cursor-${unit}.sh"
        done

        step=$((step + 1))
        printf '\n%s[%d/%d] Validate generated bundle%s\n' "${BOLD}" "$step" "$total" "${NC}"
        for unit in "${units[@]}"; do
            run_build_script "${scripts_dir}/validate-cursor-${unit}.sh"
        done

        step=$((step + 1))
        printf '\n%s[%d/%d] Format modified repository files%s\n' "${BOLD}" "$step" "$total" "${NC}"
        run_repo_style_format_modified

        step=$((step + 1))
        printf '\n%s[%d/%d] Sync bundle to ~/.cursor%s\n' "${BOLD}" "$step" "$total" "${NC}"
        # base mirrors every unit dir; a slice installs just its entries.
        if step_enabled base; then
            sync_bundle_units "${CURSOR_PLUGIN_DIR}" "${cursor_dir}" "${units[@]}"
        fi
        local slice
        for slice in $(skills_filter cursor "$(selected_slices skills agents)"); do
            run_slice cursor "${slice}"
        done
    fi

    if [[ $do_settings -eq 1 ]]; then
        step=$((step + 1))
        printf '\n%s[%d/%d] Merge Cursor CLI settings%s\n' "${BOLD}" "$step" "$total" "${NC}"
        merge_settings_config \
            "cursor-cli" \
            "${CURSOR_CLI_CONFIG_SRC}" \
            "${cursor_dir}/cli-config.json" \
            "settings"
    fi

    if [[ $do_mcp -eq 1 ]]; then
        step=$((step + 1))
        printf '\n%s[%d/%d] %s MCP servers%s\n' "${BOLD}" "$step" "$total" "${COMMAND}" "${NC}"
        run_mcp_step cursor
    fi

    if [[ $do_rules -eq 1 ]]; then
        step=$((step + 1))
        printf '\n%s[%d/%d] Cursor rules: user rules are settings-managed%s\n' "${BOLD}" "$step" "$total" "${NC}"
        # Official docs describe User Rules in Settings (Customize → Rules).
        # File-based global provisioning is unsupported/unverified, so link nothing.
        # Project rules use .cursor/rules/*.mdc or AGENTS.md. https://cursor.com/docs/rules
        info "To install these rules for Cursor, paste ycc/settings/rules/CLAUDE.md"
        info "into Cursor Settings → Rules (User Rules)."
        # Links from older installs are left alone; 'remove --intent rules' still unlinks them.
    fi

    printf '\n%sCursor %s complete.%s\n' "${BOLD}" "${COMMAND}" "${NC}"
}

# ---------------------------------------------------------------------------
# Cursor remove
# ---------------------------------------------------------------------------
remove_cursor_target() {
    validate_only_steps "cursor"
    local cursor_dir="${HOME}/.cursor"

    if step_enabled rules; then
        printf '\n%sCursor: unlink rules (CLAUDE.md + AGENTS.md)%s\n' "${BOLD}" "${NC}"
        unlink_owned_link "${SCRIPT_DIR}/ycc/settings/rules/CLAUDE.md" "${cursor_dir}/CLAUDE.md"
        unlink_owned_link "${SCRIPT_DIR}/ycc/settings/rules/AGENTS.md" "${cursor_dir}/AGENTS.md"
    fi
    if step_enabled mcp; then
        printf '\n%sCursor: remove MCP servers%s\n' "${BOLD}" "${NC}"
        run_mcp_step cursor
    fi
    if step_enabled settings; then
        printf '\n%sCursor: remove managed CLI settings%s\n' "${BOLD}" "${NC}"
        remove_settings "cursor-cli" "${CURSOR_CLI_CONFIG_SRC}" "${cursor_dir}/cli-config.json" "settings"
    fi
    remove_slices cursor skills agents
    if step_enabled base; then
        printf '\n%sCursor: remove bundle from ~/.cursor%s\n' "${BOLD}" "${NC}"
        local unit
        for unit in skills agents rules; do
            remove_mirrored_entries "${CURSOR_PLUGIN_DIR}/${unit}" "${cursor_dir}/${unit}"
        done
    fi
    printf '\n%sCursor remove complete.%s\n' "${BOLD}" "${NC}"
}
