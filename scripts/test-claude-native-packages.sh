#!/usr/bin/env bash
# Opt-in acceptance for generated Claude native packages.
#
# Uses the Claude CLI found on PATH (or CLAUDE_BIN) only for management
# commands: validate each generated package, add an isolated local marketplace
# containing copied canonical ycc and generated add-ons, install only ycc-all,
# and assert all four appear enabled. No Claude session, inference, MCP server,
# or checked-in hook runs. The sole hook execution is the marketplace-copied
# WorktreeCreate script against a disposable Git repository.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: scripts/test-claude-native-packages.sh [--keep]

Explicit opt-in: runs the local Claude CLI in a disposable lab with isolated
HOME/CLAUDE_CONFIG_DIR/XDG/TMPDIR state and an env -i allowlist, so no user
credentials, proxy settings, HERDR variables, settings, or plugin state are
inherited. Marketplace source is copied (not symlinked) from the checkout; the
checkout itself is never installed from.
--keep     Retain the lab and command transcripts.
-h, --help Show this text.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

keep=0
while (($#)); do
  case "$1" in
    --keep) keep=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

for tool in python3 git timeout mktemp realpath; do
  command -v "$tool" >/dev/null 2>&1 || die "missing prerequisite: $tool"
done

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
smoke=$repo/scripts/claude_native_smoke.py
[[ -f "$smoke" ]] || die "missing smoke driver: $smoke"
claude=${CLAUDE_BIN:-$(command -v claude || true)}
[[ -n "$claude" && -x "$claude" ]] || die 'install Claude Code or set CLAUDE_BIN'
claude=$(realpath "$claude")
python=$(command -v python3)

work_parent=${VERIFY_TEMP_DIR:-/tmp}
[[ -d "$work_parent" ]] || die 'VERIFY_TEMP_DIR must exist'
work_parent=$(realpath "$work_parent")
root=$(mktemp -d "$work_parent/claude-native-packages.XXXXXX")

cleanup() {
  local rc=$?
  trap - EXIT
  if ((keep)); then
    printf 'Retained evidence: %s (exit=%s)\n' "$root" "$rc"
  else
    printf 'Removed evidence: %s (use --keep; exit=%s)\n' "$root" "$rc"
    rm -rf -- "$root"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$root"/{home,config,xdg-config,xdg-data,xdg-state,xdg-cache,runtime,tmp,market,logs}
cd "$root"

# Preserve executable lookup only; child environments do not inherit the caller's
# credentials, proxies, Git/Python/Node options, or HERDR state.
safe_path="$(dirname "$python"):$(dirname "$(command -v git)"):$(dirname "$claude"):$(dirname "$(command -v node || command -v python3)"):/usr/local/bin:/usr/bin:/bin"
clean() {
  env -i PATH="$safe_path" LANG=C.UTF-8 LC_ALL=C.UTF-8 TERM=dumb NO_COLOR=1 \
    HOME="$root/home" CLAUDE_CONFIG_DIR="$root/config" \
    XDG_CONFIG_HOME="$root/xdg-config" XDG_DATA_HOME="$root/xdg-data" \
    XDG_STATE_HOME="$root/xdg-state" XDG_CACHE_HOME="$root/xdg-cache" \
    XDG_RUNTIME_DIR="$root/runtime" TMPDIR="$root/tmp" \
    DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    DISABLE_TELEMETRY=1 DISABLE_ERROR_REPORTING=1 \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
    GIT_ALLOW_PROTOCOL=file PYTHONDONTWRITEBYTECODE=1 "$@"
}

log() { printf '%s\n' "$*" | tee -a "$root/transcript.log"; }
run() {
  local name=$1
  shift
  log "+ $*"
  clean timeout -k 5 120 "$@" >"$root/logs/$name.stdout" 2>"$root/logs/$name.stderr" || {
    local rc=$?
    cat "$root/logs/$name.stdout" "$root/logs/$name.stderr" >&2
    die "command failed ($rc): $name"
  }
  cat "$root/logs/$name.stdout" >>"$root/transcript.log"
  if [[ -s "$root/logs/$name.stderr" ]]; then
    cat "$root/logs/$name.stderr" >&2
  fi
}

run env-check "$python" "$smoke" env-check "$root"
run generator-check "$python" "$repo/scripts/generate_claude_packages.py" --check

run version "$claude" --version
version=$(<"$root/logs/version.stdout")
log "claude CLI: $version"

for key in ycc-all ycc-hooks ycc-mcp; do
  run "validate-$key" "$claude" plugin validate "$repo/packages/claude/$key"
done

run market "$python" "$smoke" market "$root/market"
run list-before "$claude" plugin list --json
run assert-empty "$python" "$smoke" assert-list "$root/logs/list-before.stdout" empty "$root/market"

if clean timeout -k 5 30 "$claude" plugin marketplace add --help 2>/dev/null | grep -q -- '--scope'; then
  run marketplace-add "$claude" plugin marketplace add "$root/market" --scope user
else
  run marketplace-add "$claude" plugin marketplace add "$root/market"
fi
run install "$claude" plugin install ycc-all@ycc-native-lab --scope user
run list-after "$claude" plugin list --json
run assert-installed "$python" "$smoke" assert-list "$root/logs/list-after.stdout" installed "$root/market"

# Run the marketplace copy only, with a lab-contained payload and worktree root.
run hook "$python" "$smoke" hook "$root/market" "$root"

log 'PASS Claude native packages: validate + install-only ycc-all enables ycc, ycc-mcp, ycc-hooks and contained WorktreeCreate smoke'
