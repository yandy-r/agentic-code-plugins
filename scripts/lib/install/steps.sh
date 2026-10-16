# shellcheck shell=bash
# steps.sh — step and intent selection, target resolution and preflight.
#
# Per-target data comes from scripts/lib/install/targets/<t>.sh; the
# *_for_target functions and supports_repo_mode dispatch to them by name.
#
# Sourced by install.sh (never run directly); reads its arg globals (INTENTS,
# ONLY_STEPS, EXCLUSIVE_STEPS, SETTINGS, RULES, MCP, HOOKS, SCOPE, MODE,
# MCP_SERVERS) and
# ALL_TARGETS at call time.

# shellcheck disable=SC2034  # VALID_INTENTS is read by install.sh's arg validation.
VALID_INTENTS=(base skills agents commands settings rules mcp hooks plugins mods)

# shellcheck source=scripts/lib/install/packages.sh
source "${SCRIPT_DIR}/scripts/lib/install/packages.sh"

# ---------------------------------------------------------------------------
# Step selection
# ---------------------------------------------------------------------------
# step_enabled <step> <target_valid_steps_csv>
# Decides whether <step> should run for the current target.
# - If --only was passed: run iff <step> is in the --only list.
# - Else: 'base' always runs; 'settings'/'mcp' run only if their flag is set.
# The target's valid steps are used for validation by validate_only_steps().
step_enabled() {
    local step="$1"
    if [[ "${EXCLUSIVE_STEPS:-0}" == "1" ]]; then
        # Exclusive mode: nothing runs unless it was explicitly selected, so a
        # target whose intents are all no-ops must not silently fall back to
        # 'base'.
        local s
        for s in "${ONLY_STEPS[@]}"; do
            [[ "$s" == "$step" ]] && return 0
        done
        return 1
    fi
    if [[ ${#ONLY_STEPS[@]} -gt 0 ]]; then
        local s
        for s in "${ONLY_STEPS[@]}"; do
            [[ "$s" == "$step" ]] && return 0
        done
        return 1
    fi
    case "$step" in
        base)     return 0 ;;
        settings) [[ "${SETTINGS:-0}" == "1" ]] ;;
        rules)    [[ "${RULES:-0}" == "1" ]] ;;
        mcp)      [[ "${MCP:-0}" == "1" ]] ;;
        hooks)    [[ "${HOOKS:-0}" == "1" ]] ;;
        *)        return 1 ;;
    esac
}

# valid_steps_for_target <target>
# Echo the comma-separated steps <target> supports for --only.
valid_steps_for_target() {
    if ! is_known_target "$1"; then
        err "valid_steps_for_target: unknown target '$1'"
        exit 1
    fi
    "${1}_valid_steps"
}

# validate_only_steps <target> [quiet]
# If --only was passed, ensure every requested step is valid for the target.
# A slice step (skills/agents/commands) the target has no home for is skipped
# with a notice instead, so '--target all --only commands' still works; pass
# 'quiet' to suppress that notice (preflight).
validate_only_steps() {
    local target="$1"
    local quiet="${2:-}"
    # The agents target added by resolve_skills_home only acts on base/skills;
    # the rest of the run's --only list belongs to the other targets.
    [[ "${target}" == "agents" && "${AGENTS_AUTO_ADDED:-0}" == "1" ]] && return 0
    local valid_csv
    valid_csv="$(valid_steps_for_target "${target}")"
    if [[ "${EXCLUSIVE_STEPS:-0}" != "1" && ${#ONLY_STEPS[@]} -eq 0 ]]; then
        return 0
    fi

    local -a valid
    IFS=',' read -r -a valid <<< "$valid_csv"
    local requested found v
    for requested in "${ONLY_STEPS[@]}"; do
        found=0
        for v in "${valid[@]}"; do
            [[ "$v" == "$requested" ]] && { found=1; break; }
        done
        if [[ $found -eq 0 && " skills agents commands " == *" ${requested} "* ]]; then
            [[ -n "${quiet}" ]] || warn "step '${requested}' is not supported by target '${target}' — skipping"
        elif [[ $found -eq 0 ]]; then
            err "--only step '${requested}' is not valid for target '${target}' (valid: ${valid_csv})"
            exit 1
        fi
    done
}

# ---------------------------------------------------------------------------
# Intent mapping ('sync' subcommand)
# ---------------------------------------------------------------------------
# Intents describe WHAT the user wants synced; each target maps them onto the
# steps it actually supports. An intent a target cannot execute is reported and
# skipped rather than silently falling back to another step.

# intent_steps_for_target <target> <intent>
# Echo the comma-separated steps <intent> maps to for <target>. Empty output
# means the intent is a no-op there.
intent_steps_for_target() {
    is_known_target "$1" || { echo ""; return 0; }
    "${1}_intent_steps" "$2"
}

# configure_intents_for_target <target>
# Translate INTENTS into ONLY_STEPS for <target> and enable exclusive mode.
configure_intents_for_target() {
    local target="$1"
    local -a steps=()
    local intent mapped step

    for intent in "${INTENTS[@]}"; do
        mapped="$(intent_steps_for_target "${target}" "${intent}")"
        if [[ -z "${mapped}" ]]; then
            # The auto-added agents target only carries skills; its other
            # intents belong to the other targets.
            [[ "${target}" == "agents" && "${AGENTS_AUTO_ADDED:-0}" == "1" ]] && continue
            warn "intent '${intent}' is not supported by target '${target}' — skipping"
            continue
        fi
        local -a mapped_steps=()
        IFS=',' read -r -a mapped_steps <<< "${mapped}"
        for step in "${mapped_steps[@]}"; do
            local seen=0 existing
            for existing in "${steps[@]:-}"; do
                [[ "${existing}" == "${step}" ]] && seen=1 && break
            done
            [[ ${seen} -eq 0 ]] && steps+=("${step}")
        done
    done

    ONLY_STEPS=("${steps[@]:-}")
    # Drop the empty element bash leaves behind when expanding an empty array.
    if [[ ${#ONLY_STEPS[@]} -eq 1 && -z "${ONLY_STEPS[0]}" ]]; then
        ONLY_STEPS=()
    fi
    EXCLUSIVE_STEPS=1
}

intent_requested() {
    local requested="$1"
    local intent
    for intent in "${INTENTS[@]:-}"; do
        [[ "${intent}" == "${requested}" ]] && return 0
    done
    return 1
}

# config_groups_for_target <target>
# Return managed config groups selected for a structured settings file.
config_groups_for_target() {
    local target="$1"
    is_known_target "${target}" || return 0
    local defaults
    defaults="$("${target}_config_groups")"
    if [[ -n "${PACKAGE:-}" ]]; then
        # Registration owns enablement; settings-only must not enable an
        # unregistered or foreign plugin. The Codex legacy-cache path writes
        # exactly the local ycc enablement leaf itself (see codex.sh).
        if [[ "${target}" == "claude" ]] && step_enabled hooks; then
            echo "settings,hooks"
        else
            echo "settings"
        fi
        return 0
    fi
    if [[ ${#INTENTS[@]} -eq 0 ]]; then
        echo "${defaults}"
        return 0
    fi

    # Filtered order is always settings,plugins,hooks (kept from the original
    # table); only groups the target manages by default are eligible.
    local -a groups=()
    local group
    for group in settings plugins hooks; do
        intent_requested "${group}" || continue
        [[ ",${defaults}," == *",${group},"* ]] && groups+=("${group}")
    done
    local IFS=','
    echo "${groups[*]}"
}

# run_target <target> <function>
# Configure intent mapping (sync mode only), then run the target.
run_target() {
    local target="$1"
    local fn="$2"
    if [[ -n "${PACKAGE:-}" ]]; then
        package_configure_steps "$(package_steps_csv "${target}")"
    elif [[ ${#INTENTS[@]} -gt 0 ]]; then
        configure_intents_for_target "${target}"
    fi
    "${fn}"
}

# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------

# is_known_target <target>
is_known_target() {
    local known
    for known in "${ALL_TARGETS[@]}"; do
        [[ "${known}" == "$1" ]] && return 0
    done
    return 1
}

# supports_repo_mode <target>
# Whether <target> can install from the GitHub repo (--mode repo).
supports_repo_mode() {
    is_known_target "$1" && "${1}_supports_repo_mode"
}

# resolve_targets <csv>
# Populate TARGETS from a comma-separated --target value. 'all' expands to
# every target (minus repo-incapable ones under --mode repo) and must stand
# alone. Duplicates are dropped; order is preserved.
resolve_targets() {
    local csv="$1"
    local -a requested=()
    local target existing seen
    IFS=',' read -r -a requested <<< "${csv// /}"
    TARGETS=()

    if [[ ${#requested[@]} -eq 0 ]]; then
        err "--target requires at least one target"
        exit 1
    fi

    if [[ " ${requested[*]} " == *" all "* ]]; then
        if [[ ${#requested[@]} -ne 1 ]]; then
            err "--target 'all' cannot be combined with other targets"
            exit 1
        fi
        if [[ "${MODE}" == "repo" ]]; then
            warn "--mode repo: skipping cursor, opencode and agents targets (no remote-source concept)."
            warn "  use --target cursor / opencode / agents (default --mode local) to install those bundles."
        fi
        for target in "${ALL_TARGETS[@]}"; do
            if [[ "${MODE}" == "repo" ]] && ! supports_repo_mode "${target}"; then
                continue
            fi
            TARGETS+=("${target}")
        done
        return 0
    fi

    for target in "${requested[@]}"; do
        if [[ -z "${target}" ]]; then
            err "--target contains an empty value"
            exit 1
        fi
        if ! is_known_target "${target}"; then
            err "Unknown target: ${target} (supported: ${ALL_TARGETS[*]}, all)"
            exit 1
        fi
        seen=0
        for existing in "${TARGETS[@]:-}"; do
            [[ "${existing}" == "${target}" ]] && { seen=1; break; }
        done
        if [[ ${seen} -eq 0 ]]; then
            TARGETS+=("${target}")
        fi
    done
}

# ---------------------------------------------------------------------------
# Skill overlap (--skills-home)
# ---------------------------------------------------------------------------
# codex, opencode and cursor read ~/.agents/skills AND their own skills dir, so
# installing ycc skills natively for several of them (or for one of them next
# to the agents target) lists every skill twice. resolve_skills_home offers to
# install the skills once into ~/.agents/skills instead: it records the
# affected targets in SKILLS_CONSOLIDATED (the target scripts then drop their
# own skill install, see skills_consolidated) and adds the agents target.
# Reads SKILLS_HOME ('', agents or native), COMMAND, MODE, TARGETS.

SKILLS_CONSOLIDATED=()

# reads_agents_skills <target> — true when <target>'s tool also reads
# ~/.agents/skills. Every target declares <t>_reads_agents_skills (contract);
# new targets opt in there, nothing here is hardcoded.
reads_agents_skills() {
    [[ "$1" != "agents" ]] && is_known_target "$1" && "${1}_reads_agents_skills"
}
AGENTS_AUTO_ADDED=0

# skills_consolidated <target> — true when <target>'s skills go to ~/.agents/skills.
skills_consolidated() {
    [[ " ${SKILLS_CONSOLIDATED[*]:-} " == *" $1 "* ]]
}

# skills_filter <target> "<words>" — echo <words> (bundle units or slices)
# minus the skill-bearing ones (skills, shared) when <target>'s skills were
# consolidated into ~/.agents/skills; unchanged otherwise.
skills_filter() {
    local word
    local -a kept=()
    for word in $2; do
        if skills_consolidated "$1" && [[ "${word}" == "skills" || "${word}" == "shared" ]]; then
            continue
        fi
        kept+=("${word}")
    done
    echo "${kept[*]:-}"
}

# target_has_native_skills <target> — true when the run installs ycc skills
# into <target>'s own dir (base ships them for codex/opencode/cursor too).
# Subshell: intent/package mapping rewrites ONLY_STEPS. Package mode must stay
# closure-aware: a package whose cursor units exclude skills (ycc-rules,
# ycc-mcp) never installs native skills, so it cannot trigger the
# skills-consolidation flow or auto-add the agents target.
target_has_native_skills() {
    if [[ -n "${PACKAGE:-}" && "$1" == "cursor" ]]; then
        [[ " ${PACKAGE_CURSOR_UNITS:-} " == *" skills "* ]]
        return $?
    fi
    if [[ -n "${PACKAGE:-}" && "$1" == "codex" ]]; then
        # A positively detected enabled foreign native ycc already supplies the
        # skills, and base will not register; consolidation would only duplicate.
        codex_native_plugin_detected || true
        [[ -z "${PACKAGE_CODEX_FOREIGN_MARKETPLACE:-}" ]] || return 1
    fi
    (
        if [[ -n "${PACKAGE:-}" ]]; then
            package_configure_steps "$(package_steps_csv "$1")"
        elif [[ ${#INTENTS[@]} -gt 0 ]]; then
            configure_intents_for_target "$1" >/dev/null
        fi
        step_enabled base || step_enabled skills
    )
}

# resolve_skills_home
# For install/sync, detect duplicate-skill overlap and apply the user's choice
# (flag, prompt on a TTY, else warn and proceed as requested).
resolve_skills_home() {
    [[ "${COMMAND}" == "remove" || "${MODE}" == "repo" || "${SKILLS_HOME:-}" == "native" ]] && return 0

    local -a sharing=()
    local t
    for t in "${TARGETS[@]}"; do
        reads_agents_skills "${t}" || continue
        target_has_native_skills "${t}" && sharing+=("${t}")
    done
    local n=${#sharing[@]}
    [[ ${n} -ge 1 ]] || return 0

    local list="${sharing[0]}" i
    for ((i = 1; i < n; i++)); do
        if ((i == n - 1)); then list+=" and ${sharing[i]}"; else list+=", ${sharing[i]}"; fi
    done

    if [[ "${SKILLS_HOME:-}" != "agents" ]]; then
        local agents_present=0
        [[ " ${TARGETS[*]} " == *" agents "* ]] && agents_present=1
        if [[ ${agents_present} -eq 0 ]] && agents_skills_present; then agents_present=1; fi
        [[ ${n} -ge 2 || ${agents_present} -eq 1 ]] || return 0

        if [[ ${n} -ge 2 ]]; then
            local both="all"
            [[ ${n} -eq 2 ]] && both="both"
            warn "${list} will produce duplicate ycc skills (${both} read ~/.agents/skills plus their own dir)."
        else
            warn "${list} will duplicate the ycc skills in ~/.agents/skills (it reads that dir plus its own)."
        fi
        warn "Recommended: install skills once to ~/.agents/skills (agents target) and install everything else (agents, commands, tool-specific config) into each tool's own directory."

        if [[ -t 0 && -t 2 ]]; then
            {
                printf '  [1] Recommended — skills → ~/.agents/skills; %s get only their non-skill pieces natively  (default)\n' "${list}"
                printf '  [2] Keep as requested (native skills per tool; duplicates possible)\n'
                printf '  [3] Abort\n'
            } >&2
            local reply
            while true; do
                printf 'Choice [1]: ' >&2
                read -r reply || reply=3
                case "${reply:-1}" in
                    1) break ;;
                    2) return 0 ;;
                    3) err "aborted"; exit 1 ;;
                esac
            done
        else
            warn "pass --skills-home agents to consolidate (or --skills-home native to keep native skills and silence this)."
            return 0
        fi
    fi

    SKILLS_CONSOLIDATED=("${sharing[@]}")
    if [[ " ${TARGETS[*]} " != *" agents "* ]]; then
        TARGETS+=(agents)
        AGENTS_AUTO_ADDED=1
    fi
    info "skills → ~/.agents/skills; ${list} keep only their non-skill pieces"
}

# preflight_targets
# Reject every invalid target/mode/--only combination before any target runs,
# so a multi-target invocation never stops half-applied.
preflight_targets() {
    local target
    for target in "${TARGETS[@]}"; do
        if [[ "${MODE}" == "repo" ]] && ! supports_repo_mode "${target}"; then
            err "--mode repo is not supported by the ${target} target"
            err "  ${target} has no remote-source concept; it reads bundles from local directories."
            err "  use --mode local (default), or --target all to skip it automatically."
            exit 1
        fi
        if [[ -n "${PACKAGE:-}" ]]; then
            package_configure_steps "$(package_steps_csv "${target}")"
            validate_only_steps "${target}" quiet
        elif [[ ${#INTENTS[@]} -gt 0 ]]; then
            # Warnings for unsupported intents are printed when the target runs.
            configure_intents_for_target "${target}" >/dev/null
        else
            validate_only_steps "${target}" quiet
        fi
        preflight_step_support "${target}"
    done
    preflight_mcp_selection
}

# mcp_step_selected <target> — true when the run executes <target>'s mcp step.
# Subshell: intent mapping rewrites ONLY_STEPS.
mcp_step_selected() {
    [[ ",$(valid_steps_for_target "$1")," == *",mcp,"* ]] || return 1
    (
        if [[ -n "${PACKAGE:-}" ]]; then
            package_configure_steps "$(package_steps_csv "$1")"
        elif [[ ${#INTENTS[@]} -gt 0 ]]; then
            configure_intents_for_target "$1" >/dev/null
        fi
        step_enabled mcp
    )
}

# preflight_mcp_selection
# --mcps needs an mcp step to act on, and every name must be a server the repo
# manages for at least one selected target (targets skip names they lack).
preflight_mcp_selection() {
    [[ ${#MCP_SERVERS[@]} -gt 0 ]] || return 0
    local -a managed=() names=()
    local target name any=0
    for target in "${TARGETS[@]}"; do
        mcp_step_selected "${target}" || continue
        any=1
        mapfile -t names < <(mcp_server_names "${target}")
        for name in "${names[@]}"; do
            [[ " ${managed[*]:-} " == *" ${name} "* ]] || managed+=("${name}")
        done
    done
    if [[ ${any} -eq 0 ]]; then
        err "--mcps needs the mcp step (sync/remove --intent mcp, install --mcp or --only mcp) on a target that has one"
        exit 1
    fi
    for name in "${MCP_SERVERS[@]}"; do
        if [[ " ${managed[*]:-} " != *" ${name} "* ]]; then
            err "unknown MCP server '${name}' (managed for ${TARGETS[*]}: ${managed[*]:-none})"
            err "  list them with: ${CLI_NAME} list-mcps --target <targets>"
            exit 1
        fi
    done
}

# preflight_step_support <target>
# Every step selected for <target> must support project scope (explicit
# --project).
preflight_step_support() {
    local target="$1"
    local step valid_csv
    valid_csv="$(valid_steps_for_target "${target}")"
    for step in ${valid_csv//,/ }; do
        step_enabled "${step}" || continue
        if [[ "${SCOPE}" == "project" ]] && ! step_supports_project "${target}" "${step}"; then
            err "--project is not supported by step '${step}' for target '${target}' (project scope currently supports: mcp)"
            err "  use --global, or select only project-capable steps with --only / --intent."
            exit 1
        fi
    done
}
