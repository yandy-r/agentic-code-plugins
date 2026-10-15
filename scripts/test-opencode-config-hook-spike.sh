#!/usr/bin/env bash
# Opt-in YAN-1125: installed V2 binary, disposable lab, loopback-only services.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: test-opencode-config-hook-spike.sh [--keep] [--output-dir DIR]

Explicit opt-in; not wired into CI or scripts/validate.sh. Requires Linux,
opencode v2.0.29 on PATH or $OPENCODE_BIN, python3, timeout, setsid and coreutils.
No npm installs, downloads, real provider credentials, or writes outside the lab
and /tmp/opencode; the real user config is compared by metadata/hash only.
Isolation is best-effort environment scrubbing, NOT an OS sandbox/firewall.
--keep            Retain lab and evidence (default deletes it).
--output-dir DIR  Existing parent under /tmp/opencode; implies --keep.
-h, --help        Show usage without executing anything.
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
for tool in python3 timeout setsid mktemp realpath sha256sum; do
  command -v "$tool" >/dev/null || die "missing prerequisite: $tool"
done
binary=${OPENCODE_BIN:-$(command -v opencode || true)}
[[ -n "$binary" && -x "$binary" ]] || die 'installed opencode binary not found (PATH or OPENCODE_BIN)'
binary=$(realpath "$binary")
[[ -d "$parent" ]] || die 'output parent must exist'
parent=$(realpath "$parent")
[[ "$parent" == /tmp/opencode || "$parent" == /tmp/opencode/* ]] || die 'output must be under /tmp/opencode'
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
real_home=$HOME
root=$(mktemp -d "$parent/opencode-config-hook-spike.XXXXXX")
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
# env -i allowlist: no user plugins, auth, proxies, NODE_OPTIONS, or service discovery.
env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 TERM=dumb NO_COLOR=1 HOME="$root/home" \
  XDG_CONFIG_HOME="$root/config" XDG_DATA_HOME="$root/data" XDG_STATE_HOME="$root/state" \
  XDG_CACHE_HOME="$root/cache" XDG_RUNTIME_DIR="$root/runtime" OPENCODE_DB="$root/data/opencode.db" \
  TMPDIR="$root/tmp" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$script_dir" \
  setsid timeout -k 10 480 python3 "$script_dir/opencode_config_hook_spike.py" \
  "$root" "$binary" "$real_home" >"$root/transcript.log" 2>&1 &
driver_pid=$!
rc=0
wait "$driver_pid" || rc=$?
driver_pid=
cat "$root/transcript.log"
((rc == 0)) || die "matrix verification failed (exit=$rc)"
grep -qx 'assert_matrix: all expectations verified' "$root/transcript.log" \
  || die 'missing verification marker'
