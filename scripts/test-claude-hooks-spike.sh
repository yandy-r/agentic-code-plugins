#!/usr/bin/env bash
# Opt-in YAN-1122: safe recording hooks, disposable Git, loopback fake inference.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: test-claude-hooks-spike.sh [--keep] [--output-dir DIR]

Explicit opt-in: installs pinned 2.1.143 and 2.1.300 npm packages into a fresh lab.
Requires Linux, npm, node, python3, git, timeout, setsid and standard utilities.
No production hooks, user settings/plugins, HERDR variables, or real credentials
are loaded. CLI inference points only at a loopback fake API with a dummy key.
Git worktree operations occur only in a disposable fixture repository. Updater
and telemetry disabled; best-effort egress controls, NOT an OS sandbox/firewall.
--keep            Retain private lab and evidence (default removes it).
--output-dir DIR  Existing parent under /tmp/opencode; implies --keep.
-h, --help        Show usage without installing or executing anything.

Each CLI has a 75s timeout; installs 180s; total invocation 1800s. Exit zero means
all declared assertions passed, NOT that every version is a shipping Go. The old
floor's plugin WorktreeCreate may be an explicitly observed No-Go. See results.
Real config snapshots are the caller's responsibility; this harness never reads
user config or creates credential fingerprints. Avoid concurrent real CLI use
when independently comparing snapshots (otherwise false positives are possible).
EOF
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
keep=0
parent=/tmp/opencode
while (($#)); do
  case "$1" in
    --keep) keep=1; shift ;;
    --output-dir) (($# >= 2)) || die '--output-dir requires DIR'; parent=$2; keep=1; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
for tool in npm node python3 git timeout setsid mktemp realpath sha256sum; do
  command -v "$tool" >/dev/null || die "missing prerequisite: $tool"
done
[[ -d "$parent" ]] || die 'output parent must exist'
parent=$(realpath "$parent")
[[ "$parent" == /tmp/opencode || "$parent" == /tmp/opencode/* ]] || die 'output must be under /tmp/opencode'
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
helper=$script_dir/claude_hooks_spike.py
safe_path="$(dirname "$(command -v node)"):$(dirname "$(command -v npm)"):/usr/local/bin:/usr/bin:/bin"
# env -i is the allowlist: no proxies/auth/HERDR/NODE_OPTIONS/Git config inherited.
clean() {
  env -i PATH="$safe_path" LANG=C.UTF-8 TERM=dumb NO_COLOR=1 \
    HOME="$root/bootstrap" CLAUDE_CONFIG_DIR="$root/bootstrap/claude" \
    XDG_CONFIG_HOME="$root/bootstrap/config" XDG_DATA_HOME="$root/bootstrap/data" \
    XDG_STATE_HOME="$root/bootstrap/state" XDG_CACHE_HOME="$root/bootstrap/cache" \
    XDG_RUNTIME_DIR="$root/bootstrap/runtime" TMPDIR="$root/tmp" \
    npm_config_cache="$root/bootstrap/npm-cache" npm_config_userconfig="$root/bootstrap/user.npmrc" \
    npm_config_globalconfig="$root/bootstrap/global.npmrc" npm_config_registry=https://registry.npmjs.org \
    DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    DISABLE_TELEMETRY=1 DISABLE_ERROR_REPORTING=1 \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
    GIT_ALLOW_PROTOCOL=file PYTHONDONTWRITEBYTECODE=1 "$@"
}
# Kill active version driver, its Claude group, install group, and deadline timer.
cleanup() {
  local rc=$? pid
  trap - EXIT
  if [[ -n "${timer_pid:-}" ]]; then
    pkill -P "$timer_pid" 2>/dev/null || true
    kill "$timer_pid" 2>/dev/null || true
  fi
  if [[ -f "$root/driver.pid" ]]; then
    pid=$(<"$root/driver.pid")
    if [[ "$pid" =~ ^[0-9]+$ ]]; then
      kill -TERM -- "-$pid" 2>/dev/null || true
      sleep 1
      kill -KILL -- "-$pid" 2>/dev/null || true
    fi
  fi
  if [[ -n "${command_pid:-}" ]]; then
    kill -TERM -- "-$command_pid" 2>/dev/null || true
    sleep 1
    kill -KILL -- "-$command_pid" 2>/dev/null || true
    wait "$command_pid" 2>/dev/null || true
  fi
  # npm debug logs name the host Node installation; they are not evidence and
  # may contain real-home paths. Delete only this lab's npm-generated cache.
  rm -rf -- "$root/bootstrap/npm-cache"
  if ((keep)); then
    printf 'Retained evidence: %s (exit=%s)\n' "$root" "$rc"
  else
    printf 'Removed evidence: %s (use --keep; exit=%s)\n' "$root" "$rc"
    rm -rf -- "$root"
  fi
  exit "$rc"
}
root=$(mktemp -d "$parent/claude-hooks-spike.XXXXXX")
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Total deadline independent of per-command bounds; no polling.
main_pid=$$
(exec >/dev/null 2>&1; sleep 1800; kill -TERM "$main_pid" 2>/dev/null || true) &
timer_pid=$!
mkdir -p "$root"/{bootstrap,work,tmp,logs}
: >"$root/bootstrap/user.npmrc"
: >"$root/bootstrap/global.npmrc"
cd "$root/work"
printf 'YAN-1122 | %s | pins=2.1.143,2.1.300\n' "$(date -u +%F)" | tee "$root/transcript.log"
for version in 2.1.143 2.1.300; do
  prefix=$root/npm-$version
  # Independent process group makes signal cleanup cover npm descendants too.
  clean setsid timeout -k 5 180 npm install --prefix "$prefix" --no-audit --no-fund --loglevel=error \
    "@anthropic-ai/claude-code@$version" >"$root/logs/install-$version.log" 2>&1 &
  command_pid=$!
  wait "$command_pid" || die "lab npm install failed: $version"
  command_pid=
  binary=$prefix/node_modules/.bin/claude
  actual=$(clean timeout -k 5 30 "$binary" --version 2>/dev/null) || actual=
  if [[ "$actual" != "$version (Claude Code)" ]]; then
    case "$(uname -m)" in x86_64) arch=x64 ;; aarch64) arch=arm64 ;; *) die 'unsupported Linux architecture' ;; esac
    binary=$prefix/node_modules/@anthropic-ai/claude-code-linux-$arch/claude
    [[ -x "$binary" ]] || die "missing pinned native CLI: $version"
    actual=$(clean timeout -k 5 30 "$binary" --version)
  fi
  [[ "$actual" == "$version (Claude Code)" ]] || die 'version mismatch'
  printf 'CLI=%s binary_sha256=%s\n' "$actual" "$(sha256sum "$binary" | cut -d ' ' -f1)" | tee -a "$root/transcript.log"
  clean timeout -k 10 800 python3 "$helper" "$root/run-$version" "$binary" "$version" \
    >"$root/logs/driver-$version.log" 2>&1 &
  command_pid=$!
  rc=0
  wait "$command_pid" || rc=$?
  command_pid=
  rm -f -- "$root/driver.pid"
  tee -a "$root/transcript.log" <"$root/logs/driver-$version.log"
  ((rc == 0)) || die "matrix verification failed: $version"
  grep -q "$version assert_matrix: all expectations verified" "$root/run-$version/transcript.log" \
    || die "missing verification marker: $version"
done
printf 'VERIFIED: both pinned matrices met assertions; consult dossier for release gate.\n' | tee -a "$root/transcript.log"
