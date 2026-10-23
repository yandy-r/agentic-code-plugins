# shellcheck shell=bash
# Shared helpers for the opt-in live OMP harnesses (scripts/test-omp-*.sh), sourced after
# `set -euo pipefail`. They keep the harnesses portable to macOS (YAN-1555) without changing
# Linux behaviour: GNU coreutils are required and checked, the sandbox root is resolved
# (macOS /tmp is a symlink to /private/tmp), `env -C` (GNU only) is replaced by a /bin/sh
# wrapper, and the sandbox PATH can carry explicitly named extra directories.
#
# Provided:
#   omp_h_die MSG...                          print "ERROR: MSG" to stderr, exit 1
#   omp_h_require_gnu_tools                   fail with a reason unless realpath -m and timeout -k work
#   omp_h_mktemp_root PREFIX [PARENT]         mktemp -d PARENT(/tmp)/PREFIX.XXXXXX, symlinks resolved
#   omp_h_under_tmp PATH                      true when PATH is /tmp or below (symlinks resolved)
#   omp_h_safe_path ALLOW_ENV_I [LEAD_DIR]    the sandbox PATH: LEAD_DIR, extras, /usr/local/bin:/usr/bin:/bin
#   omp_h_check_path_tools PATH TOOL...       fail unless every TOOL resolves on PATH
#   omp_in_dir                                array: prefix, then DIR and a command (portable `env -C`)
#
# YCC_HARNESS_EXTRA_PATH: colon-separated absolute directories placed after LEAD_DIR and before
# /usr/local/bin in the sandbox PATH. It exists for macOS runners, where GNU coreutils and a
# Bash 4+ live outside /usr/bin; it is honoured only with --allow-env-i on Darwin (a Linux
# bwrap sandbox hides everything but the system tree, so extras would be dead or misleading)
# and every entry must be an existing absolute directory.

omp_h_die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

if ((BASH_VERSINFO[0] < 4)); then
  omp_h_die "bash >= 4 is required (this is ${BASH_VERSION}); on macOS install it with 'brew install bash' and put it first on PATH"
fi

# A command that fails under `set -e` must say why even when no die() ran (a silent exit 1
# is undebuggable in CI). -E makes the trap reach functions and subshells.
omp_h_err_trap() {
  printf 'ERROR: %s: line %s: command failed with exit %s: %s\n' "${0##*/}" "$2" "$1" "$3" >&2
}
set -E
trap 'omp_h_err_trap "$?" "$LINENO" "$BASH_COMMAND"' ERR

# Portable `env -C DIR CMD...`: run as `"${omp_in_dir[@]}" DIR CMD...`.
# shellcheck disable=SC2016 # the script is for /bin/sh, not for this shell
omp_in_dir=(/bin/sh -c 'cd -- "$1" || exit 1; shift; exec "$@"' ycc-in-dir)

# Probe behaviour, not a vendor string: macOS has no `timeout` and its BSD realpath has no -m;
# uutils or GNU coreutils both satisfy the harnesses.
omp_h_require_gnu_tools() {
  local hint="macOS: brew install coreutils and put \$(brew --prefix coreutils)/libexec/gnubin first on PATH"
  realpath -m /ycc-harness-probe/missing >/dev/null 2>&1 ||
    omp_h_die "'realpath -m' is unavailable: GNU-compatible coreutils are required ($hint)"
  timeout -k 1 5 true >/dev/null 2>&1 ||
    omp_h_die "'timeout -k' is unavailable: GNU-compatible coreutils are required ($hint)"
}

omp_h_mktemp_root() {
  local prefix=$1 parent=${2:-/tmp} dir
  dir=$(mktemp -d "$parent/$prefix.XXXXXX") || omp_h_die "mktemp -d $parent/$prefix.XXXXXX failed"
  realpath "$dir"
}

omp_h_under_tmp() {
  local base
  base=$(realpath /tmp)
  [[ "$1" == "$base" || "$1" == "$base"/* ]]
}

omp_h_safe_path() {
  local allow_env_i=${1:-0} lead=${2:-} path=/usr/local/bin:/usr/bin:/bin extra dir
  extra=${YCC_HARNESS_EXTRA_PATH:-}
  if [[ -n "$extra" ]]; then
    if ! { ((allow_env_i)) && [[ "$(uname -s)" == Darwin ]]; }; then
      omp_h_die 'YCC_HARNESS_EXTRA_PATH is only honoured with --allow-env-i on Darwin; unset it'
    fi
    local dirs=() entry
    IFS=: read -r -a dirs <<<"$extra"
    local joined=
    for entry in "${dirs[@]}"; do
      [[ "$entry" == /* && "$entry" != *[[:space:]]* && -d "$entry" ]] ||
        omp_h_die "YCC_HARNESS_EXTRA_PATH entry is not an existing absolute directory: '$entry'"
      dir=$(realpath "$entry")
      joined=${joined:+$joined:}$dir
    done
    path=$joined:$path
  fi
  printf '%s\n' "${lead:+$lead:}$path"
}

omp_h_check_path_tools() {
  local path=$1 tool
  shift
  for tool in "$@"; do
    PATH=$path command -v "$tool" >/dev/null ||
      omp_h_die "missing prerequisite on the sandbox PATH ($path): $tool"
  done
}
