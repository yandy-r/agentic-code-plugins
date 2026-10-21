# shellcheck shell=bash
# bundle.sh — bundle selection, mirroring and removal for the install/sync/remove steps.
#
# Sourced by install.sh (never run directly); relies on its helpers (info,
# warn, err, step_enabled) and globals (SCRIPT_DIR, COMMAND, FORCE).
#
# 'base' ships a target's whole bundle (claude/codex: the registered plugin;
# cursor/opencode: the mirrored bundle dirs). The 'skills', 'agents' and
# 'commands' slices install just those entries, standalone, into the tool's
# own user directories (~/.claude/skills/<name>, ~/.codex/agents/<name>.toml,
# ...) via scripts/install_slices.py — no plugin registration involved.

SLICE_HELPER="${SCRIPT_DIR}/scripts/install_slices.py"

# selected_slices <slice...> — echo the given slices whose step is enabled.
selected_slices() {
    local -a picked=()
    local slice
    for slice in "$@"; do
        step_enabled "${slice}" && picked+=("${slice}")
    done
    echo "${picked[*]}"
}

# run_slice <target> <slice> [select] — install (or, under 'remove', take
# back) one standalone slice. Entries ycc did not install are never replaced
# or removed without --force. With 'select' (passed only where the slice STEP
# runs, never for 'base'), a --skills / --agents selection narrows the slice
# to the named entries <target> ships; it ships none of them → skip.
run_slice() {
    command -v python3 >/dev/null 2>&1 || { err "python3 is required but not found"; exit 1; }
    local target="$1" slice="$2" action="install"
    # shellcheck disable=SC2153  # COMMAND is install.sh's subcommand global.
    [[ "${COMMAND}" == "remove" ]] && action="remove"
    local -a command=(python3 "${SLICE_HELPER}" "${action}" --target "${target}" --slice "${slice}")
    [[ "${FORCE:-0}" == "1" ]] && command+=(--force)
    if [[ "${3:-}" == "select" ]] && is_selectable_kind "${slice}" && has_selection "${slice}"; then
        local names selected
        names="$(selection_for_target "${slice}" "${target}")"
        if [[ -z "${names}" ]]; then
            selected="$(selection_for "${slice}")"
            warn "none of the selected ${SELECTION_NOUNS[${slice}]} (${selected//,/ }) ship for ${target} — skipping"
            return 0
        fi
        info "${SELECTION_NOUNS[${slice}]^}: ${names//,/, }"
        command+=(--entries "${names}")
        # What the other kind's step installs on this target in the same run
        # counts as available for the dependency warnings ('*': its whole slice).
        local other pending
        for other in skills agents; do
            [[ "${other}" != "${slice}" ]] && step_enabled "${other}" || continue
            pending='*'
            has_selection "${other}" && pending="$(selection_for_target "${other}" "${target}")"
            command=(env "YCC_PENDING_${other^^}=${pending}" "${command[@]}")
        done
    fi
    "${command[@]}"
}

# selected_bundle_units <unit...>
# Echo (space-separated) which generated bundle <unit>s need (re)generating:
# all of them when 'base' is enabled, otherwise the ones an enabled slice
# step installs. 'shared' (cross-skill helpers that skill bodies reference)
# rides along with 'skills'.
selected_bundle_units() {
    if step_enabled base; then
        echo "$*"
        return 0
    fi
    local -a picked=()
    local unit
    for unit in "$@"; do
        case "${unit}" in
            skills|agents|commands) step_enabled "${unit}" && picked+=("${unit}") ;;
            shared) step_enabled skills && picked+=(shared) ;;
        esac
    done
    echo "${picked[*]}"
}

# require_scripts <path...> — fail unless every helper script exists and is readable.
require_scripts() {
    local s
    for s in "$@"; do
        [[ -f "${s}" ]] || { err "Missing required script: ${s}"; exit 1; }
        [[ -r "${s}" ]] || { err "Script not readable: ${s}"; exit 1; }
    done
}

# sync_bundle_units <src_root> <dest_root> <unit...>
# Mirror each <src_root>/<unit>/ into <dest_root>/<unit>/ (rsync --delete). A
# unit the bundle no longer ships is removed from the destination.
sync_bundle_units() {
    local src_root="$1" dest_root="$2"
    shift 2
    local unit src_unit dest_unit
    for unit in "$@"; do
        src_unit="${src_root}/${unit}/"
        dest_unit="${dest_root}/${unit}/"
        if [[ -d "${src_unit}" ]]; then
            mkdir -p "${dest_unit}"
            rsync -av --delete "${src_unit}" "${dest_unit}"
            info "Synced ${unit}/ → ${dest_unit}"
        elif [[ -d "${dest_unit}" ]]; then
            rm -rf "${dest_unit}"
            warn "Removed ${dest_unit} (missing from $(basename "${src_root}"))"
        else
            warn "Source not found, skipping: ${src_unit}"
        fi
    done
}

# remove_mirrored_entries <src_dir> <dest_dir> — delete each top-level entry
# the bundle ships from the installed mirror, then the mirror if left empty.
# Entries a newer or older bundle shipped under other names are not touched.
remove_mirrored_entries() {
    local src_dir="$1" dest_dir="$2"
    if [[ ! -d "${dest_dir}" ]]; then
        info "nothing to remove: ${dest_dir}"
        return 0
    fi
    [[ -d "${src_dir}" ]] || { warn "bundle source missing, skipping: ${src_dir}"; return 0; }
    local entry name count=0
    for entry in "${src_dir}"/* "${src_dir}"/.[!.]*; do
        [[ -e "${entry}" || -L "${entry}" ]] || continue
        name="$(basename "${entry}")"
        if [[ -e "${dest_dir}/${name}" || -L "${dest_dir}/${name}" ]]; then
            rm -rf "${dest_dir:?}/${name}"
            count=$((count + 1))
        fi
    done
    info "removed ${count} bundle entr$([[ ${count} -eq 1 ]] && echo y || echo ies) from ${dest_dir}"
    if rmdir "${dest_dir}" 2>/dev/null; then
        info "removed empty directory ${dest_dir}"
    fi
}

# remove_slices <target> <slice...> — take back each enabled standalone slice
# (narrowed by a --skills / --agents selection).
remove_slices() {
    local target="$1" slice
    shift
    for slice in $(selected_slices "$@"); do
        printf '\n%s%s: remove standalone %s%s\n' "${BOLD}" "${target}" "${slice}" "${NC}"
        run_slice "${target}" "${slice}" select
    done
}
