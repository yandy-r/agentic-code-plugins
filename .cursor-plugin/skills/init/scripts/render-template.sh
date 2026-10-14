#!/usr/bin/env bash
# render-template.sh
# Render an init template to stdout from profile-project.sh key=value output.
# Pure function of its inputs: never writes files.
#
# Usage:
#   render-template.sh --template <file> [--profile <file>|-] [--set KEY=VALUE]...
#                      [--keep BLOCK]...
#
#   --template <file>   Template to render (required).
#   --profile <file>    key=value profile (default: read stdin when piped; "-" forces stdin).
#   --set KEY=VALUE     Extra placeholder, e.g. PROJECT_PURPOSE=... (wins over the profile).
#   --keep BLOCK        Keep the {{#BLOCK}}...{{/BLOCK}} body. Repeatable.
#
# Placeholders: PROJECT_NAME, PROJECT_PURPOSE, PRIMARY_LANG, SECONDARY_LANGS,
#   PACKAGE_MANAGER, TEST_CMD, LINT_CMD, BUILD_CMD (from the profile), plus any --set.
#   A command whose value is "unknown" renders as "# not detected" so no fake command
#   is ever emitted.
# Language blocks: IF_RUST, IF_TS (typescript|javascript), IF_GO, IF_PYTHON,
#   IF_TERRAFORM are kept from primary_language. Every other block is dropped unless
#   named with --keep (IF_RELEASE_MODEL, IF_LABELS, IF_CONTRIBUTING, IF_CLAUDE_ONLY).
# Block markers must sit alone on their line; blocks do not nest.
# Exit codes: 0 ok, 1 usage error. Unresolved {{PLACEHOLDER}} tokens are a failure (1).
set -euo pipefail
# Bash 5.2 expands '&' in replacement text; commands like `a && b` must stay literal.
shopt -u patsub_replacement 2>/dev/null || true

template=""
profile=""
declare -A vars=()
keep=","

while [[ $# -gt 0 ]]; do
    case "$1" in
        --template) template="${2:?--template requires a file}"; shift 2 ;;
        --profile)  profile="${2:?--profile requires a file}"; shift 2 ;;
        --set)
            [[ "${2:-}" == *=* ]] || { echo "render-template: --set needs KEY=VALUE" >&2; exit 1; }
            vars["${2%%=*}"]="${2#*=}"
            shift 2
            ;;
        --keep) keep+="${2:?--keep requires a block name},"; shift 2 ;;
        -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "render-template: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -f "$template" ]] || { echo "render-template: template not found: ${template}" >&2; exit 1; }

declare -A prof=()
if [[ -z "$profile" && ! -t 0 ]]; then profile="-"; fi
if [[ -n "$profile" ]]; then
    if [[ "$profile" == "-" ]]; then
        profile_input="$(cat)"
    else
        [[ -f "$profile" ]] || { echo "render-template: profile not found: ${profile}" >&2; exit 1; }
        profile_input="$(cat "$profile")"
    fi
    while IFS='=' read -r k v; do
        [[ -n "$k" && "$k" != \#* ]] && prof["$k"]="$v"
    done <<<"$profile_input"
fi

val() { # val <PLACEHOLDER> <profile_key>
    local name="$1" key="$2"
    if [[ -v "vars[$name]" ]]; then printf '%s' "${vars[$name]}"; else printf '%s' "${prof[$key]:-}"; fi
}

cmd() { # cmd <PLACEHOLDER> <profile_key>
    local v
    v="$(val "$1" "$2")"
    if [[ -z "$v" || "$v" == "unknown" ]]; then printf '# not detected'; else printf '%s' "$v"; fi
}

lang="${prof[primary_language]:-unknown}"
[[ -v "vars[PRIMARY_LANG]" ]] && lang="${vars[PRIMARY_LANG]}"
case "$lang" in
    rust) keep+="IF_RUST," ;;
    typescript|javascript) keep+="IF_TS," ;;
    go) keep+="IF_GO," ;;
    python) keep+="IF_PYTHON," ;;
    terraform) keep+="IF_TERRAFORM," ;;
esac

declare -A out=(
    [PROJECT_NAME]="$(val PROJECT_NAME project_name)"
    [PROJECT_PURPOSE]="$(val PROJECT_PURPOSE project_purpose)"
    [PROJECT_CONVENTIONS]="$(val PROJECT_CONVENTIONS project_conventions)"
    [PRIMARY_LANG]="$lang"
    [SECONDARY_LANGS]="$(val SECONDARY_LANGS secondary_languages)"
    [PACKAGE_MANAGER]="$(val PACKAGE_MANAGER package_manager)"
    [TEST_CMD]="$(cmd TEST_CMD test_cmd)"
    [LINT_CMD]="$(cmd LINT_CMD lint_cmd)"
    [BUILD_CMD]="$(cmd BUILD_CMD build_cmd)"
)
[[ -n "${out[PROJECT_CONVENTIONS]}" ]] || out[PROJECT_CONVENTIONS]="No additional project-specific conventions detected."
for k in "${!vars[@]}"; do out["$k"]="${vars[$k]}"; done

rendered=""
active=true
in_block=false
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^\{\{#([A-Z_]+)\}\}[[:space:]]*$ ]]; then
        in_block=true
        [[ "$keep" == *",${BASH_REMATCH[1]},"* ]] && active=true || active=false
        continue
    fi
    if [[ "$line" =~ ^\{\{/([A-Z_]+)\}\}[[:space:]]*$ ]]; then
        in_block=false
        active=true
        continue
    fi
    $active || continue
    for k in "${!out[@]}"; do line="${line//\{\{${k}\}\}/${out[$k]}}"; done
    rendered+="${line}"$'\n'
done <"$template"

if $in_block; then
    echo "render-template: unterminated block in ${template}" >&2
    exit 1
fi
if grep -qE '\{\{[A-Z_]+\}\}' <<<"$rendered"; then
    echo "render-template: unresolved placeholders: $(grep -oE '\{\{[A-Z_]+\}\}' <<<"$rendered" | sort -u | tr '\n' ' ')" >&2
    exit 1
fi
printf '%s' "$rendered"
