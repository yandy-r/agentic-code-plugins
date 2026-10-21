# bash completion for ycc (install.sh) — install: ycc completion --shell bash --install

# _ycc_list [<kind>] — 'ycc list' output (the selectable kinds, or a kind's
# names for the --target on the line), space-separated.
_ycc_list() {
    local i targets="all"
    for ((i = 1; i < COMP_CWORD; i++)); do
        [[ "${COMP_WORDS[i]}" == "--target" ]] && targets="${COMP_WORDS[i+1]}"
    done
    if [[ $# -eq 0 ]]; then
        "${COMP_WORDS[0]}" list 2>/dev/null | tr '\n' ' '
    else
        "${COMP_WORDS[0]}" list "$1" --target "${targets}" 2>/dev/null | tr '\n' ' '
    fi
}

_ycc() {
    local cur="${COMP_WORDS[COMP_CWORD]}" prev="${COMP_WORDS[COMP_CWORD-1]}"
    local sub="" values="" kinds="" kind
    [[ ${COMP_CWORD} -gt 1 ]] && sub="${COMP_WORDS[1]}"
    [[ "${sub}" =~ ^(install|sync|remove|list)$ ]] && kinds="$(_ycc_list)"

    case "${prev}" in
        --target) values="claude cursor codex opencode agents omp all"; [[ "${sub}" == migrate ]] && values="claude codex cursor omp all" ;;
        --skills-home) mapfile -t COMPREPLY < <(compgen -W "agents native" -- "${cur}"); return ;;
        --intent) values="base skills agents commands settings rules mcp hooks plugins mods" ;;
        --package) [[ "${sub}" == "install" ]] && values="ycc ycc-mcp ycc-hooks ycc-rules" ;;
        --only)   values="base skills agents commands settings rules mcp hooks mods" ;;
        --mode)   mapfile -t COMPREPLY < <(compgen -W "local repo" -- "${cur}"); return ;;
        --shell)  mapfile -t COMPREPLY < <(compgen -W "bash zsh fish" -- "${cur}"); return ;;
        --dir|--marketplace-source) mapfile -t COMPREPLY < <(compgen -d -- "${cur}"); return ;;
        --*)
            # --<kind> selectors: names from 'ycc list <kind>'.
            kind="${prev#--}"
            [[ "${sub}" != list && " ${kinds} " == *" ${kind} "* ]] && values="$(_ycc_list "${kind}")"
            ;;
    esac

    # Comma lists: complete the item after the last comma, keep the prefix.
    if [[ -n "${values}" ]]; then
        local head="" item="${cur}"
        if [[ "${cur}" == *,* ]]; then
            head="${cur%,*},"
            item="${cur##*,}"
        fi
        mapfile -t COMPREPLY < <(compgen -P "${head}" -W "${values}" -- "${item}")
        compopt -o nospace 2>/dev/null
        return
    fi

    local words selectors=""
    for kind in ${kinds}; do selectors+=" --${kind}"; done
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        words="install sync remove migrate cli completion list list-mcps"
    else
        case "${sub}" in
            cli)        words="--dir --force --help" ;;
            completion) words="--shell --install --force --help" ;;
            list)       words="--target --help"; [[ ${COMP_CWORD} -eq 2 ]] && words+=" ${kinds}" ;;
            list-mcps)  words="--target --help" ;;
            install)    words="--target --package --only --mode --skills-home --settings --rules --mcp --hooks --project --global --force --dry-run --help${selectors}" ;;
            sync)       words="--target --intent --mode --skills-home --project --global --force --dry-run --help${selectors}" ;;
            remove)     words="--target --only --intent --project --global --force --dry-run --help${selectors}" ;;
            migrate)    words="--target --apply --marketplace-source --help" ;;
            *)          words="" ;;
        esac
    fi
    mapfile -t COMPREPLY < <(compgen -W "${words}" -- "${cur}")
}

complete -F _ycc ycc
