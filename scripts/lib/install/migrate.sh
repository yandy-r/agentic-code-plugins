# shellcheck shell=bash
# migrate.sh — deliberately separate from destructive remove/slice paths.
# Dry-run never builds bundles or invokes a plugin CLI. Python performs one
# preflight over the full target selection before any --apply mutation.
run_migrate_command() {
    local target_csv="" apply=0 marketplace_source="" arg target
    while [[ $# -gt 0 ]]; do
        arg="$1"
        case "${arg}" in
            --target|--marketplace-source)
                [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { err "${arg} requires an argument"; return 1; }
                if [[ "${arg}" == "--target" ]]; then target_csv="$2"; else marketplace_source="$2"; fi
                shift 2
                ;;
            --apply) apply=1; shift ;;
            --help|-h) usage; return 0 ;;
            *) err "migrate does not accept ${arg}; use --target, --apply, or --marketplace-source"; return 1 ;;
        esac
    done
    [[ -n "${target_csv}" ]] || { err "Missing required --target flag"; return 1; }
    if [[ "${target_csv}" == "all" ]]; then
        target_csv="claude,codex,cursor"
        info "migrate --target all resolves only claude,codex,cursor (opencode and agents are unsupported)"
    fi
    [[ "${target_csv}" != ,* && "${target_csv}" != *, && "${target_csv}" != *,,* ]] || {
        err "--target contains an empty value"; return 1;
    }
    local -a requested=() targets=()
    IFS=',' read -r -a requested <<< "${target_csv}"
    for target in "${requested[@]}"; do
        case "${target}" in
            claude|codex|cursor) ;;
            all) err "'all' cannot be combined with other targets"; return 1 ;;
            *) err "migrate is not supported for target '${target}' (supported: claude, codex, cursor)"; return 1 ;;
        esac
        [[ " ${targets[*]:-} " == *" ${target} "* ]] || targets+=("${target}")
    done
    if [[ -n "${marketplace_source}" && " ${targets[*]} " != *" codex "* ]]; then
        err "--marketplace-source is only supported with the codex migration"; return 1
    fi
    command -v python3 >/dev/null 2>&1 || { err "python3 is required for migration"; return 1; }
    local -a command=(python3 "${SCRIPT_DIR}/scripts/install_migrate.py" --targets "$(IFS=,; printf '%s' "${targets[*]}")")
    [[ "${apply}" == 1 ]] && command+=(--apply)
    [[ -n "${marketplace_source}" ]] && command+=(--marketplace-source "${marketplace_source}")
    "${command[@]}"
}

# print_native_deprecation_hints <target>... — v6 lists native packages for
# claude, codex and cursor, so install/sync there is the fallback path. Hints go
# to stderr to keep scripted stdout stable; other targets have no native listing.
print_native_deprecation_hints() {
    local target
    for target in "$@"; do
        case "${target}" in
            claude|codex|cursor)
                warn "deprecated: ${target} native packages are listed in the ycc marketplace as of v6.0.0; installer copies are the fallback. Preview the move with: $(basename "$0") migrate --target ${target}" >&2
                ;;
        esac
    done
}
