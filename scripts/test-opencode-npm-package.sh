#!/usr/bin/env bash
# Opt-in YAN-1143: pack and relocate the generated npm artifact in a disposable lab.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: test-opencode-npm-package.sh [--keep] [--output-dir DIR] [--package-dir DIR]

Explicit opt-in; not wired into CI or validate.sh. Generate the npm package first.
Requires Linux, installed OpenCode V2 >=2.0.30 (the exercised version), npm, node,
python3, timeout, setsid and coreutils. OPENCODE_BIN defaults to /home/yandy/.opencode/bin/opencode.
No installs, downloads, publication, real credentials or real runtime config writes.
The packed artifact is extracted into a moved disposable path. Only MCP transport
fixture data is changed there; the generated adapter is executed unchanged.
Isolation is an environment allowlist, NOT an OS sandbox or network firewall.
--keep             Retain lab and evidence (otherwise deletes it).
--output-dir DIR   Existing parent under /tmp/opencode; implies --keep.
--package-dir DIR  Generated package (defaults to packages/opencode/ycc-opencode).
-h, --help         Show usage without executing anything.
EOF
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
package_dir=$script_dir/../packages/opencode/ycc-opencode
repo_root=$(cd -- "$script_dir/.." && pwd)
keep=0
parent=/tmp/opencode
while (($#)); do
  case "$1" in
    --keep) keep=1; shift ;;
    --output-dir) (($# >= 2)) || die '--output-dir requires DIR'; parent=$2; keep=1; shift 2 ;;
    --package-dir) (($# >= 2)) || die '--package-dir requires DIR'; package_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
for tool in python3 timeout setsid mktemp realpath npm node; do
  command -v "$tool" >/dev/null || die "missing prerequisite: $tool"
done
binary=${OPENCODE_BIN:-/home/yandy/.opencode/bin/opencode}
[[ -x "$binary" ]] || die 'installed opencode binary not found (set OPENCODE_BIN)'
binary=$(realpath "$binary")
npm_bin=$(command -v npm)
# `npm` is a `#!/usr/bin/env node` script; version-managed node (mise/pnpm/nvm) is not on the scrubbed PATH.
npm_bin=$(realpath "$npm_bin")
node_bin=$(command -v node)
node_bin=$(realpath "$node_bin")
[[ -f "$package_dir/package.json" ]] || die 'generated package missing; run scripts/generate_opencode_package.py first'
package_dir=$(realpath "$package_dir")
[[ -d "$parent" ]] || die 'output parent must exist'
parent=$(realpath "$parent")
[[ "$parent" == /tmp/opencode || "$parent" == /tmp/opencode/* ]] || die 'output must be under /tmp/opencode'
real_home=$HOME
root=$(mktemp -d "$parent/opencode-npm-package.XXXXXX")
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
  setsid timeout -k 10 360 python3 "$script_dir/opencode_npm_package_smoke.py" \
  "$root" "$binary" "$real_home" "$package_dir" "$npm_bin" "$repo_root" "$node_bin" >"$root/transcript.log" 2>&1 &
driver_pid=$!
rc=0
wait "$driver_pid" || rc=$?
driver_pid=
cat "$root/transcript.log"
((rc == 0)) || die "npm runtime verification failed (exit=$rc)"
# Do not accept a driver that exited early without completing the assertion matrix.
grep -qx 'assert_npm_package: all expectations verified' "$root/transcript.log" \
  || die 'missing verification marker'
