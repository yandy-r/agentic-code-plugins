#!/usr/bin/env bash
# Shared harness for the install.sh test suites under scripts/tests/install/:
# sandbox HOMEs, stub claude/codex CLIs, run_install and pass/fail counters.
#
# Every test runs against a throwaway HOME so the caller's real ~/.claude,
# ~/.codex, ~/.cursor and ~/.config/opencode are never touched. Sourced once
# per shell (load guard), so the runner's suites share one sandbox, one EXIT
# trap and one set of counters.
[[ -n "${INSTALL_TESTS_LIB_LOADED:-}" ]] && return 0
INSTALL_TESTS_LIB_LOADED=1
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
INSTALL="${REPO_ROOT}/install.sh"

PASS=0
FAIL=0

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

# Per-user dir overrides would escape the sandbox HOME.
unset XDG_BIN_HOME XDG_DATA_HOME XDG_CONFIG_HOME BASH_COMPLETION_USER_DIR

SANDBOX_ROOT="$(mktemp -d)"
INSTALL_TESTS_FINISHED=0
# on_exit — drop the sandbox; a run that exits before install_tests_finish
# (an 'exit' or 'set -u' abort inside a suite) fails instead of passing silently.
on_exit() {
    local rc=$?
    rm -rf "${SANDBOX_ROOT}"
    if [[ ${INSTALL_TESTS_FINISHED} -eq 0 ]]; then
        printf '%s[FAIL]%s install tests aborted before the totals (exit %d)\n' "${RED}" "${NC}" "${rc}" >&2
        [[ ${rc} -eq 0 ]] && rc=1
    fi
    exit "${rc}"
}
trap on_exit EXIT

# new_home — create an isolated HOME and echo its path.
new_home() {
    local home
    home="$(mktemp -d "${SANDBOX_ROOT}/home.XXXXXX")"
    mkdir -p "${home}/.claude" "${home}/.codex" "${home}/.cursor" "${home}/.config/opencode" "${home}/project"
    echo "${home}"
}

# Stub 'claude' and 'codex' CLIs record their arguments, so plugin steps are
# checked without touching a real plugin registry.
STUB_BIN="${SANDBOX_ROOT}/stub-bin"
mkdir -p "${STUB_BIN}"
cat > "${STUB_BIN}/claude" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${CLAUDE_STUB_LOG}"
SH
cat > "${STUB_BIN}/codex" <<'SH'
#!/usr/bin/env bash
[[ " $* " == *" --help "* ]] && exit 0
printf 'codex %s\n' "$*" >> "${CLAUDE_STUB_LOG}"
SH
# style.sh needs ruff/black on PATH when install runs its repo-style step;
# the tests assert placement, not formatting, so no-op them.
cat > "${STUB_BIN}/ruff" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "${STUB_BIN}/black" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${STUB_BIN}/claude" "${STUB_BIN}/codex" "${STUB_BIN}/ruff" "${STUB_BIN}/black"

# run_install <home> <args...> — run install.sh sandboxed; capture output.
# Runs from <home>/project (not a git repo) so project-scoped steps write
# there and never into this checkout. Installs the bundles as committed
# (YCC_INSTALL_SKIP_BUILD=1) unless the caller's environment says otherwise;
# build.sh covers the real generate/validate/format steps once per target.
run_install() {
    local home="$1"
    shift
    (
        cd "${home}/project" || exit 1
        HOME="${home}" \
        PATH="${STUB_BIN}:${PATH}" \
        CLAUDE_STUB_LOG="${home}/claude-calls.log" \
        YCC_MANAGED_CONFIG_STATE="${home}/.config/ycc/managed-config-state.json" \
        YCC_INSTALL_SKIP_BUILD="${YCC_INSTALL_SKIP_BUILD:-1}" \
            bash "${INSTALL}" "$@" 2>&1
    )
}

# run_install_build <home> <args...> — run_install with the real bundle build
# (generators, validators and the repo style pass run against this checkout).
run_install_build() {
    YCC_INSTALL_SKIP_BUILD=0 run_install "$@"
}

ok() {
    PASS=$((PASS + 1))
    printf '%s[pass]%s %s\n' "${GREEN}" "${NC}" "$1"
}

ko() {
    FAIL=$((FAIL + 1))
    printf '%s[FAIL]%s %s\n' "${RED}" "${NC}" "$1"
    [[ -n "${2:-}" ]] && printf '       %s\n' "$2"
}

assert_contains() {
    local haystack="$1" needle="$2" name="$3"
    if [[ "${haystack}" == *"${needle}"* ]]; then
        ok "${name}"
    else
        ko "${name}" "expected to find: ${needle}"
    fi
}

assert_not_contains() {
    local haystack="$1" needle="$2" name="$3"
    if [[ "${haystack}" != *"${needle}"* ]]; then
        ok "${name}"
    else
        ko "${name}" "unexpectedly found: ${needle}"
    fi
}

# run_install_stubbed — alias kept for the mods tests; run_install already
# puts the stub claude/codex CLIs first on PATH.
run_install_stubbed() {
    run_install "$@"
}

# shellcheck disable=SC2034  # read by the suites.
REPO_REAL="$(realpath "${REPO_ROOT}")"

# source_install_libs — load install.sh's libs (no side effects at source time)
# into the current shell, the same way install.sh does.
# shellcheck disable=SC1090,SC1091,SC2034  # runtime paths; the libs read SCRIPT_DIR.
source_install_libs() {
    SCRIPT_DIR="${REPO_ROOT}"
    eval "$(sed -n 's/^ALL_TARGETS=(\(.*\))$/ALL_TARGETS=(\1)/p' "${INSTALL}")"
    local f
    for f in core steps bundle cli; do source "${REPO_ROOT}/scripts/lib/install/${f}.sh"; done
    for f in "${ALL_TARGETS[@]}"; do source "${REPO_ROOT}/scripts/lib/install/targets/${f}.sh"; done
}

# install_tests_finish — print the totals line; fail on any failure.
install_tests_finish() {
    INSTALL_TESTS_FINISHED=1
    echo
    printf 'test-install-sync: %d passed, %d failed\n' "${PASS}" "${FAIL}"
    [[ ${FAIL} -eq 0 ]]
}
