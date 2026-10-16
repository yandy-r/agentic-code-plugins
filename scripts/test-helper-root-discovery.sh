#!/usr/bin/env bash
# test-helper-root-discovery.sh — source-checkout discovery for the two helpers
# that need canonical repo sources (YAN-1199 / GH #334):
#   - report-bundle-drift.sh  (needs ycc/skills + scripts/generate_*.py)
#   - build-hook-config.sh    (needs ycc/rules/*/hooks.md, capability matrix, templates)
#
# Runs every generated copy of both helpers (claude, cursor, codex, opencode,
# agents, opencode npm package) from throwaway scratch directories and asserts:
#   - unrelated cwd, no args: resolves the checkout that holds the helper
#   - explicit --repo-root=<repo> (and positional / nested path for the reporter)
#   - a detached copy (simulating a native or file-copy install) outside any
#     checkout fails with exit 2 and an actionable --repo-root message
#   - the same detached copy run from inside the checkout succeeds
#   - a marketplace-only fake root and an unsuitable explicit root are rejected
#     (explicit input is authoritative: no fallthrough to PWD)
#   - a minimal source tree whose path contains spaces is accepted
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/ycc-helper-roots.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

FAILED=0
pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; FAILED=1; }

CLEAN_ENV=(env -u CLAUDE_PLUGIN_ROOT -u CURSOR_PLUGIN_ROOT)

OUT_F="${SCRATCH}/stdout"
ERR_F="${SCRATCH}/stderr"
RC=0

# run <cwd> <cmd...> — sets RC and fills OUT_F / ERR_F.
run() {
  local cwd="$1"
  shift
  RC=0
  (cd "$cwd" && "${CLEAN_ENV[@]}" "$@") >"$OUT_F" 2>"$ERR_F" || RC=$?
}

assert_rc_in() { # <label> <allowed-rc-regex> — checks RC
  local label="$1" allowed="$2"
  if [[ "$RC" =~ ^(${allowed})$ ]]; then
    pass "$label (exit $RC)"
  else
    fail "$label: expected exit ${allowed}, got ${RC}: $(tr '\n' ' ' <"$ERR_F" | cut -c1-300)"
  fi
}

# Reporter success: exit 0 or 1 (drift is a valid result), JSON on stdout,
# discovery message names the checkout.
assert_reporter_ok() { # <label> [expected-root]
  local label="$1" root="${2:-$REPO_ROOT}"
  assert_rc_in "$label" "0|1"
  if python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$OUT_F" 2>/dev/null; then
    pass "$label: stdout is valid JSON"
  else
    fail "$label: stdout is not valid JSON"
  fi
  if grep -qF "repo root is ${root}" "$ERR_F"; then
    pass "$label: resolved ${root}"
  else
    fail "$label: stderr does not name ${root}: $(tr '\n' ' ' <"$ERR_F" | cut -c1-300)"
  fi
}

assert_builder_ok() { # <label> [expected-root]
  local label="$1" root="${2:-$REPO_ROOT}"
  assert_rc_in "$label" "0"
  if grep -qF "hooks-workflow: advisory — Cursor does not execute hooks natively" "$OUT_F" \
    && grep -qF "<!-- Event: PostToolUse -->" "$OUT_F"; then
    pass "$label: cursor advisory output for PostToolUse"
  else
    fail "$label: missing cursor advisory/PostToolUse marker: $(tr '\n' ' ' <"$OUT_F" | cut -c1-300)"
  fi
  if grep -qF "repo root is ${root}" "$ERR_F"; then
    pass "$label: resolved ${root}"
  else
    fail "$label: stderr does not name ${root}: $(tr '\n' ' ' <"$ERR_F" | cut -c1-300)"
  fi
}

assert_exit2_actionable() { # <label>
  local label="$1"
  assert_rc_in "$label" "2"
  if grep -qF -- "--repo-root" "$ERR_F"; then
    pass "$label: message mentions --repo-root"
  else
    fail "$label: message lacks --repo-root: $(tr '\n' ' ' <"$ERR_F" | cut -c1-300)"
  fi
}

# label | bundle dir to detach | reporter (relative to bundle dir) | builder (relative)
BUNDLE_SPECS=(
  "claude|ycc/skills|_shared/scripts/report-bundle-drift.sh|hooks-workflow/scripts/build-hook-config.sh"
  "cursor|packages/cursor/ycc|skills/_shared/scripts/report-bundle-drift.sh|skills/hooks-workflow/scripts/build-hook-config.sh"
  "codex|.codex-plugin/ycc|shared/scripts/report-bundle-drift.sh|skills/hooks-workflow/scripts/build-hook-config.sh"
  "opencode|.opencode-plugin|shared/scripts/report-bundle-drift.sh|skills/hooks-workflow/scripts/build-hook-config.sh"
  "agents|.agents-plugin|ycc-shared/scripts/report-bundle-drift.sh|skills/hooks-workflow/scripts/build-hook-config.sh"
  "opencode-npm|packages/opencode/ycc-opencode|shared/scripts/report-bundle-drift.sh|skills/hooks-workflow/scripts/build-hook-config.sh"
)

BUILDER_ARGS=(--language=python --target=cursor --event=PostToolUse --dry-run)
REPORTER_ARGS=(--target=inventory --format=json)

UNRELATED="${SCRATCH}/unrelated cwd"
mkdir -p "$UNRELATED"

# Marketplace-only lookalike root: both manifests, no ycc sources.
FAKE_MARKET="${SCRATCH}/fake-marketplace"
mkdir -p "${FAKE_MARKET}/.claude-plugin" "${FAKE_MARKET}/.cursor-plugin"
printf '{}\n' >"${FAKE_MARKET}/.claude-plugin/marketplace.json"
printf '{}\n' >"${FAKE_MARKET}/.cursor-plugin/marketplace.json"

# Existing directory that is not a checkout (and has no checkout ancestor).
UNSUITABLE="${SCRATCH}/unsuitable root"
mkdir -p "$UNSUITABLE"

for spec in "${BUNDLE_SPECS[@]}"; do
  IFS='|' read -r label bundle_rel reporter_rel builder_rel <<<"$spec"
  bundle_dir="${REPO_ROOT}/${bundle_rel}"
  reporter="${bundle_dir}/${reporter_rel}"
  builder="${bundle_dir}/${builder_rel}"

  if [[ ! -f "$reporter" ]]; then fail "${label}: reporter missing: ${reporter}"; continue; fi
  if [[ ! -f "$builder" ]]; then fail "${label}: builder missing: ${builder}"; continue; fi

  # --- In-checkout copy, unrelated cwd, no args -----------------------------
  run "$UNRELATED" bash "$reporter" "${REPORTER_ARGS[@]}"
  assert_reporter_ok "${label} reporter: unrelated cwd"
  run "$UNRELATED" bash "$builder" "${BUILDER_ARGS[@]}"
  assert_builder_ok "${label} builder: unrelated cwd"

  # --- Explicit --repo-root / positional / nested path -----------------------
  run "$UNRELATED" bash "$reporter" "${REPORTER_ARGS[@]}" "--repo-root=${REPO_ROOT}"
  assert_reporter_ok "${label} reporter: --repo-root"
  run "$UNRELATED" bash "$reporter" "${REPORTER_ARGS[@]}" "$REPO_ROOT"
  assert_reporter_ok "${label} reporter: positional root"
  run "$UNRELATED" bash "$reporter" "${REPORTER_ARGS[@]}" "--repo-root=${REPO_ROOT}/ycc/skills"
  assert_reporter_ok "${label} reporter: nested --repo-root"
  run "$UNRELATED" bash "$builder" "${BUILDER_ARGS[@]}" "--repo-root=${REPO_ROOT}"
  assert_builder_ok "${label} builder: --repo-root"
  run "$UNRELATED" bash "$builder" "${BUILDER_ARGS[@]}" "--repo-root=${REPO_ROOT}/docs"
  assert_builder_ok "${label} builder: nested --repo-root"

  # --- Detached copy (native / file-copy install simulation) -----------------
  detached="${SCRATCH}/home/${label}/.${label}/skills"
  mkdir -p "$(dirname "$detached")"
  cp -a "$bundle_dir" "$detached"
  d_reporter="${detached}/${reporter_rel}"
  d_builder="${detached}/${builder_rel}"

  run "$UNRELATED" bash "$d_reporter" "${REPORTER_ARGS[@]}"
  assert_exit2_actionable "${label} detached reporter: unrelated cwd"
  run "$UNRELATED" bash "$d_builder" "${BUILDER_ARGS[@]}"
  assert_exit2_actionable "${label} detached builder: unrelated cwd"

  run "$REPO_ROOT" bash "$d_reporter" "${REPORTER_ARGS[@]}"
  assert_reporter_ok "${label} detached reporter: cwd = checkout"
  run "$REPO_ROOT" bash "$d_builder" "${BUILDER_ARGS[@]}"
  assert_builder_ok "${label} detached builder: cwd = checkout"

  run "$UNRELATED" bash "$d_reporter" "${REPORTER_ARGS[@]}" "--repo-root=${REPO_ROOT}"
  assert_reporter_ok "${label} detached reporter: --repo-root"
  run "$UNRELATED" bash "$d_builder" "${BUILDER_ARGS[@]}" "--repo-root=${REPO_ROOT}"
  assert_builder_ok "${label} detached builder: --repo-root"

  # --- Rejections ------------------------------------------------------------
  run "$UNRELATED" bash "$reporter" "${REPORTER_ARGS[@]}" "--repo-root=${FAKE_MARKET}"
  assert_exit2_actionable "${label} reporter: marketplace-only root"
  run "$UNRELATED" bash "$builder" "${BUILDER_ARGS[@]}" "--repo-root=${FAKE_MARKET}"
  assert_exit2_actionable "${label} builder: marketplace-only root"

  # Explicit input is authoritative: running from the checkout must not rescue it.
  run "$REPO_ROOT" bash "$reporter" "${REPORTER_ARGS[@]}" "--repo-root=${UNSUITABLE}"
  assert_exit2_actionable "${label} reporter: unsuitable explicit root from checkout cwd"
  run "$REPO_ROOT" bash "$builder" "${BUILDER_ARGS[@]}" "--repo-root=${UNSUITABLE}"
  assert_exit2_actionable "${label} builder: unsuitable explicit root from checkout cwd"
  run "$REPO_ROOT" bash "$reporter" "${REPORTER_ARGS[@]}" "--repo-root=${SCRATCH}/does-not-exist"
  assert_rc_in "${label} reporter: nonexistent explicit root from checkout cwd" "2"
  run "$REPO_ROOT" bash "$builder" "${BUILDER_ARGS[@]}" "--repo-root=${SCRATCH}/does-not-exist"
  assert_rc_in "${label} builder: nonexistent explicit root from checkout cwd" "2"
done

# --- Minimal source tree whose path contains spaces ---------------------------
MIN="${SCRATCH}/with space/min checkout"
mkdir -p "${MIN}/ycc/skills" "${MIN}/scripts" "${MIN}/ycc/rules/common" \
  "${MIN}/ycc/skills/_shared/references" "${MIN}/ycc/skills/hooks-workflow/references"
cat >"${MIN}/scripts/generate_inventory.py" <<'PYEOF'
import sys
sys.exit(0 if "--check" in sys.argv else 2)
PYEOF
cp "${REPO_ROOT}/ycc/rules/common/hooks.md" "${MIN}/ycc/rules/common/hooks.md"
cp "${REPO_ROOT}/ycc/skills/_shared/references/target-capability-matrix.md" \
  "${MIN}/ycc/skills/_shared/references/target-capability-matrix.md"
cp -R "${REPO_ROOT}/ycc/skills/hooks-workflow/references/templates" \
  "${MIN}/ycc/skills/hooks-workflow/references/templates"

for spec in "${BUNDLE_SPECS[@]}"; do
  IFS='|' read -r label bundle_rel reporter_rel builder_rel <<<"$spec"
  bundle_dir="${REPO_ROOT}/${bundle_rel}"
  run "$UNRELATED" bash "${bundle_dir}/${reporter_rel}" "${REPORTER_ARGS[@]}" "--repo-root=${MIN}"
  assert_rc_in "${label} reporter: spaced minimal checkout" "0"
  grep -qF "repo root is ${MIN}" "$ERR_F" \
    && pass "${label} reporter: resolved spaced minimal checkout" \
    || fail "${label} reporter: spaced root not named: $(tr '\n' ' ' <"$ERR_F" | cut -c1-300)"
  run "$UNRELATED" bash "${bundle_dir}/${builder_rel}" --language=common --target=cursor --event=PostToolUse --dry-run "--repo-root=${MIN}"
  assert_builder_ok "${label} builder: spaced minimal checkout" "$MIN"
done

# --- Reporter: missing generator entrypoint is a setup error, not drift --------
run "$UNRELATED" bash "${REPO_ROOT}/ycc/skills/_shared/scripts/report-bundle-drift.sh" --target=cursor --format=json "--repo-root=${MIN}"
assert_rc_in "reporter: missing generator entrypoint" "2"
grep -qF "generate_cursor_skills.py" "$ERR_F" \
  && pass "reporter: missing generator is named" \
  || fail "reporter: missing generator not named: $(tr '\n' ' ' <"$ERR_F" | cut -c1-300)"

if [[ "$FAILED" -ne 0 ]]; then
  echo "test-helper-root-discovery.sh: FAILED" >&2
  exit 1
fi
echo "test-helper-root-discovery.sh: all checks passed"
