#!/usr/bin/env bash
# Opt-in YAN-1026: drive the ycc sensitive-file guard on an isolated OpenCode V2 host.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: test-opencode-sensitive-guard.sh [--keep] [--output-dir DIR]

Explicit opt-in; not wired into CI or validate.sh. Regenerate first
(./scripts/sync.sh --only opencode). Requires Linux, an installed OpenCode V2
binary, python3, git, timeout, setsid and coreutils. OPENCODE_BIN defaults to
/home/yandy/.opencode/bin/opencode. The lab installs the generated file-copy
bundle and the generated npm package directory into a disposable config root,
uses a loopback fake provider and synthetic canary files only. No installs,
downloads, real credentials or real runtime config writes.
Isolation is an environment allowlist, NOT an OS sandbox or network firewall.
--keep             Retain lab and evidence (otherwise deletes it).
--output-dir DIR   Existing parent under /tmp/opencode; implies --keep.
-h, --help         Show usage without executing anything.
EOF
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
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
for tool in python3 git timeout setsid mktemp realpath; do
  command -v "$tool" >/dev/null || die "missing prerequisite: $tool"
done
binary=${OPENCODE_BIN:-/home/yandy/.opencode/bin/opencode}
[[ -x "$binary" ]] || die 'installed opencode binary not found (set OPENCODE_BIN)'
binary=$(realpath "$binary")
[[ -f "$repo_root/.opencode-plugin/ycc-sensitive-guard/index.js" ]] \
  || die 'generated guard missing; run ./scripts/sync.sh --only opencode first'
mkdir -p "$parent"
[[ -d "$parent" ]] || die 'output parent must exist'
parent=$(realpath "$parent")
[[ "$parent" == /tmp/opencode || "$parent" == /tmp/opencode/* ]] || die 'output must be under /tmp/opencode'
real_home=$HOME
root=$(mktemp -d "$parent/opencode-sensitive-guard.XXXXXX")
driver_pid=
cleanup() {
  local rc=$? pid
  trap - EXIT
  if [[ -f "$root/process-groups" ]]; then
    while read -r pid; do
      [[ "$pid" =~ ^[0-9]+$ ]] || continue
      kill -TERM -- "-$pid" 2>/dev/null || true
      sleep 0.3
      kill -KILL -- "-$pid" 2>/dev/null || true
    done <"$root/process-groups"
  fi
  if [[ -n "$driver_pid" ]]; then
    kill -TERM -- "-$driver_pid" 2>/dev/null || true
    kill -KILL -- "-$driver_pid" 2>/dev/null || true
    wait "$driver_pid" 2>/dev/null || true
  fi
  if ((keep)); then
    printf 'Retained evidence: %s (exit=%s)\n' "$root" "$rc"
  else
    rm -rf -- "$root"
    printf 'Removed evidence: %s (exit=%s)\n' "$root" "$rc"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$root"/{home,config,data,state,cache,runtime,tmp,work}
env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 TERM=dumb NO_COLOR=1 HOME="$root/home" \
  XDG_CONFIG_HOME="$root/config" XDG_DATA_HOME="$root/data" XDG_STATE_HOME="$root/state" \
  XDG_CACHE_HOME="$root/cache" XDG_RUNTIME_DIR="$root/runtime" OPENCODE_DB="$root/data/opencode.db" \
  TMPDIR="$root/tmp" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$script_dir" \
  setsid timeout -k 10 900 python3 "$script_dir/opencode_sensitive_guard_smoke.py" \
  "$root" "$binary" "$real_home" "$repo_root" >"$root/transcript.log" 2>&1 &
driver_pid=$!
rc=0
wait "$driver_pid" || rc=$?
driver_pid=
cat "$root/transcript.log"
((rc == 0)) || die "sensitive-guard runtime verification failed (exit=$rc)"
grep -qx 'assert_sensitive_guard: all expectations verified' "$root/transcript.log" \
  || die 'missing verification marker'
