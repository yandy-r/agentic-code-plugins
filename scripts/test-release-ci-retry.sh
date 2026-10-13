#!/usr/bin/env bash
#
# Offline tests for release-ci-monitor.sh exact-run mode (--run-id/--expected-sha)
# and tag-mode compatibility. A stub gh on PATH answers from GH_* env vars; no
# network, no release or tag mutation.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR="$(cd "${SCRIPT_DIR}/.." && pwd)/ycc/skills/_shared/scripts/release-ci-monitor.sh"

PASS=0
FAIL=0
SANDBOX="$(mktemp -d)"
trap 'rm -rf "${SANDBOX}"' EXIT

while IFS= read -r git_var; do unset "$git_var"; done < <(git rev-parse --local-env-vars)
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null

git init -q "${SANDBOX}/repo"
git -C "${SANDBOX}/repo" remote add origin https://github.com/example/repo.git

mkdir -p "${SANDBOX}/bin"
cat >"${SANDBOX}/bin/gh" <<'STUB'
#!/usr/bin/env bash
# Stub gh. Env: GH_RUN_ID GH_SHA GH_EVENT GH_PATH GH_CONCLUSION GH_WATCH_RC
# GH_FETCH_FAIL GH_LOG. Every call is appended to $GH_CALLS.
echo "$*" >>"$GH_CALLS"
case "$1 $2" in
  "run view")
    if [[ "$*" == *databaseId* ]]; then
      [[ -n "${GH_FETCH_FAIL:-}" ]] && exit 1
      printf '%s\t%s\t%s\tRelease\n' "$GH_RUN_ID" "$GH_SHA" "$GH_EVENT"
    elif [[ "$*" == *--log-failed* ]]; then printf '%s\n' "${GH_LOG:-}"
    elif [[ "$*" == *jobs* ]]; then echo build
    else echo "${GH_CONCLUSION:-success}"; fi ;;
  "run watch") exit "${GH_WATCH_RC:-0}" ;;
  "run list") echo '[{"databaseId":777,"headBranch":"v1.0.0","workflowName":"Release"}]' ;;
  "run rerun") ;;
  "api repos/example/repo/actions/runs/${GH_RUN_ID}") printf '%s\t%s\n' "$GH_RUN_ID" "$GH_PATH" ;;
  *) exit 1 ;;
esac
STUB
chmod +x "${SANDBOX}/bin/gh"
export PATH="${SANDBOX}/bin:${PATH}"
export GH_CALLS="${SANDBOX}/calls.log"

SHA="$(printf 'a%.0s' {1..40})"
OTHER_SHA="$(printf 'b%.0s' {1..40})"

ok() { PASS=$((PASS + 1)); printf '[pass] %s\n' "$1"; }
ko() { FAIL=$((FAIL + 1)); printf '[FAIL] %s\n       %s\n' "$1" "${2:-}"; }

# run_case <name> <expected-exit> <expected-stdout-substring> <expect-watch:yes|no> -- <monitor args...>
# Defaults (override by exporting GH_* before calling): a matching dispatch run.
run_case() {
  local name="$1" want_rc="$2" want_out="$3" want_watch="$4"
  shift 5
  : >"$GH_CALLS"
  local out rc watched=no
  out="$(cd "${SANDBOX}/repo" && "$MONITOR" --max-pushes 3 --max-same-failure 3 \
    --timeout-min 60 --log-file "${SANDBOX}/log.jsonl" "$@" 2>/dev/null)"
  rc=$?
  grep -q '^run watch' "$GH_CALLS" && watched=yes
  if [[ "$rc" == "$want_rc" && "$out" == *"$want_out"* && "$watched" == "$want_watch" ]]; then
    ok "$name"
  else
    ko "$name" "rc=$rc (want $want_rc) watched=$watched (want $want_watch) out=$out"
  fi
}

reset_env() {
  export GH_RUN_ID=4242 GH_SHA="$SHA" GH_EVENT=workflow_dispatch
  export GH_PATH=.github/workflows/release.yml GH_CONCLUSION=success GH_WATCH_RC=0
  unset GH_FETCH_FAIL GH_LOG
  rm -f "${SANDBOX}/log.jsonl"
}

EXACT=(--tag v1.0.0 --workflow release.yml --repo example/repo --run-id 4242 --expected-sha "$SHA")
exact() { run_case "$1" "$2" "$3" "$4" -- "${EXACT[@]}" "${@:5}"; }

# --- selector validation (exit 1, never reaches gh) ---
reset_env
run_case "run-id without sha"       1 "" no -- --tag v1.0.0 --workflow release.yml --run-id 4242
run_case "sha without run-id"       1 "" no -- --tag v1.0.0 --workflow release.yml --expected-sha "$SHA"
run_case "run-id zero"              1 "" no -- --tag v1.0.0 --workflow release.yml --run-id 0 --expected-sha "$SHA"
run_case "run-id non-numeric"       1 "" no -- --tag v1.0.0 --workflow release.yml --run-id 12x --expected-sha "$SHA"
run_case "short sha"                1 "" no -- --tag v1.0.0 --workflow release.yml --run-id 4242 --expected-sha abc123
run_case "uppercase sha"            1 "" no -- --tag v1.0.0 --workflow release.yml --run-id 4242 --expected-sha "${SHA^^}"
run_case "run-id needs --workflow"  1 "" no -- --tag v1.0.0 --run-id 4242 --expected-sha "$SHA"

# --- green exact run ---
reset_env
exact "exact run green" 0 "RESULT=green" yes
if grep -q '"run_id":4242' "${SANDBOX}/log.jsonl" && grep -q "\"head_sha\":\"$SHA\"" "${SANDBOX}/log.jsonl"; then
  ok "audit log has run id + sha"
else
  ko "audit log has run id + sha" "$(cat "${SANDBOX}/log.jsonl")"
fi
if grep -q 'run list' "$GH_CALLS"; then ko "exact mode skips tag selection"; else ok "exact mode skips tag selection"; fi

# --- correlation mismatches fail closed, no watch ---
MISMATCH="RESULT=not-found"
reset_env; export GH_SHA="$OTHER_SHA"
exact "mismatch sha"          2 "REASON=retry-correlation-mismatch" no
reset_env; export GH_EVENT=push
exact "mismatch event"        2 "REASON=retry-correlation-mismatch" no
reset_env; export GH_PATH=.github/workflows/other.yml
exact "mismatch workflow"     2 "$MISMATCH" no
reset_env; export GH_PATH=.github/workflows/release.yml@refs/heads/other
exact "mismatch workflow ref" 2 "$MISMATCH" no
reset_env; export GH_RUN_ID=9999
exact "mismatch run id"       2 "$MISMATCH" no
reset_env; export GH_FETCH_FAIL=1
exact "metadata fetch fails"  2 "REASON=retry-correlation-mismatch" no

# --- tag mode unchanged ---
reset_env
run_case "tag mode green" 0 "RESULT=green" yes -- --tag v1.0.0 --workflow release.yml --repo example/repo
if grep -q 'run list' "$GH_CALLS"; then ok "tag mode uses run list"; else ko "tag mode uses run list"; fi

# --- caps and classification reused in exact mode ---
reset_env; export GH_WATCH_RC=1 GH_CONCLUSION=failure GH_LOG="eslint error in src/a.js"
exact "failed fixable run hands off" 20 "RESULT=handoff" yes
reset_env; export GH_WATCH_RC=1 GH_CONCLUSION=failure GH_LOG="eslint error in src/a.js"
exact "push cap" 12 "RESULT=bail-pushes" no --max-pushes 0
reset_env; printf '{"timestamp":"2000-01-01T00:00:00Z","action":"x"}\n' >"${SANDBOX}/log.jsonl"
exact "timeout cap" 13 "RESULT=bail-timeout" no

printf '\n%s passed, %s failed\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
