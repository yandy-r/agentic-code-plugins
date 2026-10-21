# shellcheck shell=bash
# cli.sh — 'cli' / 'completion' subcommands: put install.sh on PATH as `ycc`.
#
# Sourced by install.sh (never run directly); uses usage(), CLI_NAME and
# SCRIPT_DIR from it, and the FORCE global (set here).

# link_owned <src> <dest> — link_file, but an existing real file or a symlink
# pointing elsewhere is someone else's and needs --force.
link_owned() {
    local src="$1" dest="$2"
    if [[ ( -e "$dest" || -L "$dest" ) && "$(readlink "$dest" || true)" != "$src" && "${FORCE}" != "1" ]]; then
        err "refusing to replace existing ${dest} (re-run with --force)"
        exit 1
    fi
    link_file "$src" "$dest"
}

on_path() {
    [[ ":${PATH}:" == *":$1:"* ]]
}

# cli_bin_dir — first conventional user bin dir already on PATH.
cli_bin_dir() {
    local dir
    for dir in ${XDG_BIN_HOME:+"${XDG_BIN_HOME}"} "${HOME}/.local/bin" "${HOME}/bin"; do
        on_path "${dir}" && { echo "${dir}"; return 0; }
    done
    echo "${XDG_BIN_HOME:-${HOME}/.local/bin}"
}

run_cli_command() {
    local dir=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dir)
                [[ $# -lt 2 ]] && { err "--dir requires an argument"; exit 1; }
                dir="$2"
                shift 2
                ;;
            --force) FORCE=1; shift ;;
            --help|-h) usage; exit 0 ;;
            *) err "Unknown option for cli: $1"; exit 1 ;;
        esac
    done
    dir="${dir:-$(cli_bin_dir)}"
    link_owned "${SCRIPT_DIR}/install.sh" "${dir}/${CLI_NAME}"
    on_path "${dir}" || warn "${dir} is not on PATH; add it in your shell profile"
    info "Shell completion: ${CLI_NAME} completion --install"
}

# completion_dest <shell> — per-user dir the shell autoloads completions from.
completion_dest() {
    local data="${XDG_DATA_HOME:-${HOME}/.local/share}"
    case "$1" in
        bash) echo "${BASH_COMPLETION_USER_DIR:-${data}/bash-completion}/completions/${CLI_NAME}" ;;
        zsh)  echo "${data}/zsh/site-functions/_${CLI_NAME}" ;;
        fish) echo "${XDG_CONFIG_HOME:-${HOME}/.config}/fish/completions/${CLI_NAME}.fish" ;;
    esac
}

run_completion_command() {
    local shell="" install=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --shell)
                [[ $# -lt 2 ]] && { err "--shell requires an argument (bash|zsh|fish)"; exit 1; }
                shell="$2"
                shift 2
                ;;
            --install) install=1; shift ;;
            --force) FORCE=1; shift ;;
            --help|-h) usage; exit 0 ;;
            *) err "Unknown option for completion: $1"; exit 1 ;;
        esac
    done
    shell="${shell:-$(basename "${SHELL:-}")}"
    local src="${SCRIPT_DIR}/scripts/completions"
    case "${shell}" in
        bash) src+="/${CLI_NAME}.bash" ;;
        zsh)  src+="/_${CLI_NAME}" ;;
        fish) src+="/${CLI_NAME}.fish" ;;
        *) err "unsupported shell '${shell}' (supported: bash, zsh, fish; pass --shell)"; exit 1 ;;
    esac
    [[ -f "${src}" ]] || { err "completion script not found: ${src}"; exit 1; }

    if [[ ${install} -eq 0 ]]; then
        cat "${src}"
        return 0
    fi
    local dest
    dest="$(completion_dest "${shell}")"
    link_owned "${src}" "${dest}"
    case "${shell}" in
        bash) info "Loaded by bash-completion in new shells (or add: eval \"\$(${CLI_NAME} completion --shell bash)\" to ~/.bashrc)" ;;
        zsh)  info "Needs $(dirname "${dest}") in fpath before compinit; then: rm -f ~/.zcompdump*; exec zsh" ;;
        fish) info "Loaded automatically in new fish sessions" ;;
    esac
}
