# bash completion for ycc (install.sh) — install: ycc completion --shell bash --install

# _ycc_mcps — managed MCP servers, from 'ycc list-mcps' for the --target on the line.
_ycc_mcps() {
    local i targets="all"
    for ((i = 1; i < COMP_CWORD; i++)); do
        [[ "${COMP_WORDS[i]}" == "--target" ]] && targets="${COMP_WORDS[i+1]}"
    done
    "${COMP_WORDS[0]}" list-mcps --target "${targets}" 2>/dev/null | tr '\n' ' '
}

_ycc() {
    local cur="${COMP_WORDS[COMP_CWORD]}" prev="${COMP_WORDS[COMP_CWORD-1]}"
    local sub="" values=""
    [[ ${COMP_CWORD} -gt 1 ]] && sub="${COMP_WORDS[1]}"

    case "${prev}" in
        --target) values="claude cursor codex opencode agents all"; [[ "${sub}" == migrate ]] && values="claude codex cursor all" ;;
        --skills-home) mapfile -t COMPREPLY < <(compgen -W "agents native" -- "${cur}"); return ;;
        --intent) values="base skills agents commands settings rules mcp hooks plugins mods" ;;
        --package) [[ "${sub}" == "install" ]] && values="ycc ycc-mcp ycc-hooks ycc-rules" ;;
        --mcps)   values="$(_ycc_mcps)" ;;
        --only)   values="base skills agents commands settings rules mcp hooks mods" ;;
        --mode)   mapfile -t COMPREPLY < <(compgen -W "local repo" -- "${cur}"); return ;;
        --shell)  mapfile -t COMPREPLY < <(compgen -W "bash zsh fish" -- "${cur}"); return ;;
        --dir|--marketplace-source) mapfile -t COMPREPLY < <(compgen -d -- "${cur}"); return ;;
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

    local words
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        words="install sync remove migrate cli completion list-mcps"
    else
        case "${sub}" in
            cli)        words="--dir --force --help" ;;
            completion) words="--shell --install --force --help" ;;
            list-mcps)  words="--target --help" ;;
            install)    words="--target --package --only --mode --skills-home --settings --rules --mcp --mcps --hooks --project --global --force --help" ;;
            sync)       words="--target --intent --mcps --mode --skills-home --project --global --force --help" ;;
            remove)     words="--target --only --intent --mcps --project --global --force --help" ;;
            migrate)    words="--target --apply --marketplace-source --help" ;;
            *)          words="" ;;
        esac
    fi
    mapfile -t COMPREPLY < <(compgen -W "${words}" -- "${cur}")
}

complete -F _ycc ycc
