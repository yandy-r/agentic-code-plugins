#!/usr/bin/env bash
# Opt-in actual Codex installs; no model sessions, auth, or MCP server execution.
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: test-codex-native-packages.sh [--keep]
       test-codex-native-packages.sh --public URL --ref SHA [--keep]

Requires Codex >=0.160.0 (CODEX_BIN overrides PATH), git, python3 with the
repository's generator dependencies, timeout, and standard Linux utilities.
Installs both packages using full and sparse immutable Git checkouts.
--keep retains the sandbox and sanitized command transcript; default removes both.

Default: generate a temporary fixture; rewrite its HTTPS-shaped .invalid URL
to file:// with GIT_ALLOW_PROTOCOL=file. This is NOT OS network isolation.
--public: explicitly opt into real GitHub HTTPS transport, requiring an exact
https://github.com/OWNER/REPO.git URL, full 40-hex commit SHA, and Codex 0.160.0.
The already-published fixture must match a fresh native export. No publishing,
URL rewrites, credentials, prompts, model inference, login, hooks, or MCP server
execution. This networked profile is opt-in, not part of CI.
EOF
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
keep=0
public=0
public_url=
public_ref=
while (($#)); do
  case "$1" in
    --keep) keep=1; shift ;;
    --public)
      [[ $# -ge 2 && -n "$2" && "$public" == 0 ]] || die '--public requires one URL'
      public=1; public_url=$2; shift 2 ;;
    --ref)
      [[ $# -ge 2 && -n "$2" && -z "$public_ref" ]] || die '--ref requires one full commit SHA'
      public_ref=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
if ((public)); then
  [[ "$public_url" =~ ^https://github\.com/[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9_][A-Za-z0-9_.-]*\.git$ ]] ||
    die '--public requires https://github.com/OWNER/REPO.git (no credentials, query, or fragment)'
  [[ "$public_ref" =~ ^[[:xdigit:]]{40}$ ]] || die '--ref requires a full 40-hex commit SHA'
  public_ref=${public_ref,,}
else
  [[ -z "$public_ref" ]] || die '--ref requires --public URL'
fi
for tool in git python3 timeout mktemp realpath; do
  command -v "$tool" >/dev/null || die "missing prerequisite: $tool"
done
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
checks=$repo/scripts/codex_native_smoke.py
codex=${CODEX_BIN:-$(command -v codex || true)}
[[ -n "$codex" && -x "$codex" ]] || die 'install codex or set CODEX_BIN'
codex=$(realpath -s "$codex")
python=$(command -v python3)
# Include the selected Python (possibly a venv) and Node for Codex npm shims,
# without inheriting credentials, proxy settings, Python paths, or Git config.
safe_path="$(dirname "$python"):$(dirname "$codex"):$(dirname "$(command -v node || command -v python3)"):/usr/local/bin:/usr/bin:/bin"
root=$(mktemp -d /tmp/codex-native-packages.XXXXXX)
cleanup() {
  local rc=$?
  if ((keep)); then
    printf 'Retained transcript: %s/transcript.log (exit=%s)\n' "$root" "$rc"
  else
    printf 'Sandbox removed (use --keep for evidence; exit=%s): %s\n' "$rc" "$root"
    rm -rf -- "$root"
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$root"/{work,tmp,logs}
# mktemp's private 700 root protects evidence. Git preserves only regular-file
# type and its executable bit; umask 022 makes disposable harness paths normal.
umask 022
cd "$root/work"
bare=$root/fixture.git
url=https://codex-native.invalid/fixture.git
if ((public)); then url=$public_url; fi
case_home=$root/bootstrap
clean() {
  local -a transport
  if ((public)); then
    # Only HTTPS is permitted, with no URL rewrite or inherited auth mechanism.
    transport=(GIT_ALLOW_PROTOCOL=https GIT_CONFIG_COUNT=1
      GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0=)
  else
    transport=(GIT_ALLOW_PROTOCOL=file GIT_CONFIG_COUNT=2
      GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0=
      GIT_CONFIG_KEY_1="url.file://$bare.insteadOf" GIT_CONFIG_VALUE_1="$url")
  fi
  mkdir -p "$case_home"/{home,codex,config,data,state,cache,runtime}
  env -i PATH="$safe_path" LANG=C.UTF-8 TERM=dumb NO_COLOR=1 \
    HOME="$case_home/home" CODEX_HOME="$case_home/codex" \
    XDG_CONFIG_HOME="$case_home/config" XDG_DATA_HOME="$case_home/data" \
    XDG_STATE_HOME="$case_home/state" XDG_CACHE_HOME="$case_home/cache" \
    XDG_RUNTIME_DIR="$case_home/runtime" TMPDIR="$root/tmp" \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
    GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false "${transport[@]}" "$@"
}
log() { printf '%s\n' "$*" | tee -a "$root/transcript.log"; }
# Keep raw stdout/stderr for machine assertions; all inputs are disposable or
# authored source. env -i ensures no user's secrets enter this transcript.
run() {
  local label=$1 rc=0; shift
  clean timeout -k 5 90 "$@" >"$root/logs/$label.stdout" 2>"$root/logs/$label.stderr" || rc=$?
  {
    printf '\n[%s] cwd=%q argv:' "$label" "$PWD"
    printf ' %q' "$@"
    printf '\nexit=%s\nstdout:\n' "$rc"
    cat "$root/logs/$label.stdout"
    printf '\nstderr:\n'
    cat "$root/logs/$label.stderr"
    printf '\n'
  } >>"$root/transcript.log"
  if ((rc)); then
    cat "$root/logs/$label.stderr" >&2
    die "$label exited $rc; see $root/transcript.log"
  fi
}
expected_rc() {
  local expected=$1 label=$2 rc=0; shift 2
  clean timeout -k 5 90 "$@" >"$root/logs/$label.stdout" 2>"$root/logs/$label.stderr" || rc=$?
  {
    printf '\n[%s] cwd=%q argv:' "$label" "$PWD"
    printf ' %q' "$@"
    printf '\nexit=%s\nstdout:\n' "$rc"
    cat "$root/logs/$label.stdout"
    printf '\nstderr:\n'
    cat "$root/logs/$label.stderr"
    printf '\n'
  } >>"$root/transcript.log"
  [[ "$rc" == "$expected" ]] || die "$label expected exit=$expected, got $rc; see $root/transcript.log"
}
run version "$codex" --version
version=$(<"$root/logs/version.stdout")
if ((public)); then
  run version-check "$python" "$checks" version "$version" 0.160.0
  log "YAN-1163 | $version | public GitHub HTTPS (no URL rewrites)"
  log "Public fixture URL: $url"
  log "Pinned fixture SHA: $public_ref"
  log 'Auth: env -i; fresh HOME/CODEX_HOME/XDG; no inherited Git config; empty credential.helper; prompts/askpass disabled; HTTPS only'
else
  run version-check "$python" "$checks" version "$version"
  log "YAN-1131 | $version | local immutable Git fixture (not OS network isolation)"
fi
run export "$python" "$repo/scripts/generate_codex_plugin.py" --native-output "$root/source"
if ((public)); then
  # Fetch and verify remote bytes before asking Codex to install anything. Neither
  # the current branch nor a stale but self-consistent fixture can satisfy this.
  commit=$public_ref
  run fixture-init git init -q "$root/published"
  run fixture-fetch git -C "$root/published" fetch --no-tags --depth=1 "$url" "$commit"
  run fixture-checkout git -C "$root/published" -c advice.detachedHead=false checkout -q --detach FETCH_HEAD
  run fixture-sha git -C "$root/published" rev-parse HEAD
  [[ "$(<"$root/logs/fixture-sha.stdout")" == "$commit" ]] || die 'fetched fixture SHA mismatch'
  run fixture-proof "$python" "$checks" fixture "$root/source" "$root/published"
  source_root=$root/published
else
  # Fixture-only sentinel outside every sparse selection; it is never exported.
  mkdir -p "$root/source/outside-sparse"
  printf '%s\n' 'outside sparse selection' >"$root/source/outside-sparse/sentinel"
  run init git -C "$root/source" init -q -b fixture
  run stage git -C "$root/source" add -A
  run commit git -C "$root/source" -c user.name=native-smoke -c user.email=native-smoke@localhost \
    -c commit.gpgsign=false commit -qm 'immutable generated native fixture'
  run sha git -C "$root/source" rev-parse HEAD
  commit=$(<"$root/logs/sha.stdout")
  run fork git clone -q --bare "$root/source" "$bare"
  log "Pinned fixture SHA: $commit"
  source_root=$root/source
fi

matrix_case() {
  local name=$1 first=$2 second=$3; shift 3
  case_home=$root/$name
  run "$name-register" "$codex" plugin marketplace add "$url" --ref "$commit" "$@" --json
  run "$name-checkout" "$python" "$checks" checkout "$root/logs/$name-register.stdout" "$commit" "$name"
  if ((public)); then
    run "$name-staging" "$python" "$checks" staging "$root/logs/$name-register.stdout" "$name" "$source_root"
  else
    run "$name-staging" "$python" "$checks" staging "$root/logs/$name-register.stdout" "$name"
  fi
  run "$name-available" "$codex" plugin list --available --json
  run "$name-catalog" "$python" "$checks" catalog "$root/logs/$name-register.stdout" "$root/logs/$name-available.stdout"
  run "$name-first-install" "$codex" plugin add "$first@ycc" --json
  run "$name-first-list" "$codex" plugin list --json
  run "$name-first-mcp" "$codex" mcp list --json
  run "$name-first-proof" "$python" "$checks" installed "$source_root" "$case_home/codex" \
    "$root/logs/$name-first-list.stdout" "$root/logs/$name-first-mcp.stdout" "$first"
  run "$name-second-install" "$codex" plugin add "$second@ycc" --json
  run "$name-both-list" "$codex" plugin list --json
  # metadata `mcp list` should not launch servers/model sessions; if Codex
  # appears to start them, stop and report rather than adding broader tests.
  run "$name-both-mcp" "$codex" mcp list --json
  run "$name-both-proof" "$python" "$checks" installed "$source_root" "$case_home/codex" \
    "$root/logs/$name-both-list.stdout" "$root/logs/$name-both-mcp.stdout" ycc ycc-mcp
  mkdir -p "$case_home/user-project"
  run "$name-project" git -C "$case_home/user-project" init -q -b user-work
  run "$name-helper-path" "$python" "$checks" helper-path "$case_home/codex"
  local helper before
  helper=$(<"$root/logs/$name-helper-path.stdout")
  before=$PWD
  (
    cd "$case_home/user-project"
    # Check the shell cwd on both sides as well as the Python subprocess cwd.
    local project_before=$PWD
    run "$name-helper" "$python" "$checks" helper-run "$helper" "$case_home/user-project" "$case_home/codex"
    [[ "$PWD" == "$project_before" ]] || die 'helper changed project shell cwd'
  )
  [[ "$PWD" == "$before" ]] || die 'helper changed harness cwd'
  log "PASS $name: independent installs, complete cache bytes/exec bits, enabled IDs, MCP metadata, cache-relative helper"
}
# Reverse installation order proves each package works independently in a fresh
# Codex home, not merely after its companion has provided missing resources.
matrix_case full ycc ycc-mcp
matrix_case sparse ycc-mcp ycc --sparse .agents/plugins --sparse .codex-plugin/ycc --sparse .codex-plugin/ycc-mcp
catalog_only_case() {
  case_home=$root/catalog-only
  run catalog-only-register "$codex" plugin marketplace add "$url" --ref "$commit" --sparse .agents/plugins --json
  run catalog-only-staging "$python" "$checks" staging "$root/logs/catalog-only-register.stdout" catalog-only
  run catalog-only-available "$codex" plugin list --available --json
  run catalog-only-catalog "$python" "$checks" catalog "$root/logs/catalog-only-register.stdout" \
    "$root/logs/catalog-only-available.stdout" --catalog-only
  expected_rc 1 catalog-only-install "$codex" plugin add ycc@ycc --json
  run catalog-only-proof "$python" "$checks" failed-install "$case_home/codex" "$root/logs/catalog-only-install.stderr"
  log 'PASS catalog-only: catalog visible without payload roots; install=1; no cache'
}
if ((!public)); then catalog_only_case; fi
log 'PASS native packages: full + sparse catalog/both payloads; no inference, hooks, login, or MCP server execution requested'
