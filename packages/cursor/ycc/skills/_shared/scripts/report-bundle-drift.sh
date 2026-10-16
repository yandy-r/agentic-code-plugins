#!/usr/bin/env bash
# report-bundle-drift.sh — wrap generate_*.py --check entry points and emit a
# per-target drift report.
#
# Usage:
#   report-bundle-drift.sh [--target=all|cursor|codex|opencode|inventory]
#                          [--format=human|json]
#                          [--json-out=PATH]
#                          [--repo-root=PATH]
#                          [PATH]
#                          [--help]
#
# Exit codes:
#   0  every sub-check passed (no drift)
#   1  at least one sub-check reported drift
#   2  usage error (bad flag, unknown target, repo root not found)

set -euo pipefail

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
  cat <<'EOF'
Usage: report-bundle-drift.sh [--target=all|cursor|codex|opencode|inventory] [--format=human|json] [--json-out=PATH] [--repo-root=PATH|PATH] [--help]

Wraps the generate_*.py --check entry points and emits a per-target drift
report. Exit 0 iff every target is clean. Exit 1 on drift. Exit 2 on
usage error.
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing (long-form)
# ---------------------------------------------------------------------------

TARGET="all"
FORMAT="human"
JSON_OUT=""
REPO_ROOT_INPUT=""

for arg in "$@"; do
  case "$arg" in
    --target=*)   TARGET="${arg#--target=}" ;;
    --format=*)   FORMAT="${arg#--format=}" ;;
    --json-out=*) JSON_OUT="${arg#--json-out=}" ;;
    --repo-root=*) REPO_ROOT_INPUT="${arg#--repo-root=}" ;;
    --help|-h)    usage; exit 0 ;;
    -*)
      echo "report-bundle-drift.sh: unknown flag: $arg" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$REPO_ROOT_INPUT" ]]; then
        echo "report-bundle-drift.sh: multiple repo roots provided: $REPO_ROOT_INPUT and $arg" >&2
        usage >&2
        exit 2
      fi
      REPO_ROOT_INPUT="$arg"
      ;;
  esac
done

case "$TARGET" in
  all|cursor|codex|opencode|inventory) ;;
  *) echo "report-bundle-drift.sh: unknown --target value: $TARGET" >&2; usage >&2; exit 2 ;;
esac

case "$FORMAT" in
  human|json) ;;
  *) echo "report-bundle-drift.sh: unknown --format value: $FORMAT" >&2; usage >&2; exit 2 ;;
esac

# ---------------------------------------------------------------------------
# Resolve repo root from explicit input, then PWD, then SCRIPT_DIR
# ---------------------------------------------------------------------------

echo "report-bundle-drift.sh: resolving repo root..." >&2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT=""

resolve_repo_root_from() {
  local start="$1"
  local candidate="$start"
  while [[ "$candidate" != "/" ]]; do
    if [[ -f "$candidate/.cursor-plugin/marketplace.json" ]]; then
      REPO_ROOT="$candidate"
      return 0
    fi
    candidate="$(dirname "$candidate")"
  done
  if [[ -f "/.cursor-plugin/marketplace.json" ]]; then
    REPO_ROOT="/"
    return 0
  fi
  return 1
}

if [[ -n "$REPO_ROOT_INPUT" ]]; then
  if [[ ! -d "$REPO_ROOT_INPUT" ]]; then
    echo "report-bundle-drift.sh: --repo-root/positional path is not a directory: $REPO_ROOT_INPUT" >&2
    exit 2
  fi
  resolve_repo_root_from "$(cd "$REPO_ROOT_INPUT" && pwd)" || true
fi

if [[ -z "$REPO_ROOT" ]]; then
  resolve_repo_root_from "$PWD" || true
fi

if [[ -z "$REPO_ROOT" ]]; then
  resolve_repo_root_from "$SCRIPT_DIR" || true
fi

if [[ -z "$REPO_ROOT" ]]; then
  echo "report-bundle-drift.sh: cannot locate repo root (no .cursor-plugin/marketplace.json found from repo-root input/PWD/SCRIPT_DIR search)" >&2
  exit 2
fi

echo "report-bundle-drift.sh: repo root is $REPO_ROOT" >&2
SCRIPTS_DIR="${REPO_ROOT}/scripts"

# ---------------------------------------------------------------------------
# Sub-check runner — appends to three parallel arrays
# ---------------------------------------------------------------------------

NAMES=(); EXITS=(); COMBINED=()   # combined = stdout + stderr merged

run_check() {
  local name="$1"; shift
  echo "report-bundle-drift.sh: running ${name}..." >&2

  local out rc
  set +e
  out="$(cd "$REPO_ROOT" && "$@" 2>&1)"
  rc=$?
  set -e

  NAMES+=("$name")
  EXITS+=("$rc")
  COMBINED+=("$out")
}

# ---------------------------------------------------------------------------
# Target dispatch
# ---------------------------------------------------------------------------

[[ "$TARGET" == "inventory" || "$TARGET" == "all" ]] && \
  run_check "inventory"     python3 "${SCRIPTS_DIR}/generate_inventory.py"      --check

if [[ "$TARGET" == "cursor" || "$TARGET" == "all" ]]; then
  run_check "cursor:skills" python3 "${SCRIPTS_DIR}/generate_cursor_skills.py"  --check
  run_check "cursor:agents" python3 "${SCRIPTS_DIR}/generate_cursor_agents.py"  --check
  run_check "cursor:rules"  python3 "${SCRIPTS_DIR}/generate_cursor_rules.py"   --check
fi

if [[ "$TARGET" == "codex" || "$TARGET" == "all" ]]; then
  run_check "codex:skills"  python3 "${SCRIPTS_DIR}/generate_codex_skills.py"   --check
  run_check "codex:agents"  python3 "${SCRIPTS_DIR}/generate_codex_agents.py"   --check
  run_check "codex:plugin"  python3 "${SCRIPTS_DIR}/generate_codex_plugin.py"   --check
fi

if [[ "$TARGET" == "opencode" || "$TARGET" == "all" ]]; then
  run_check "opencode:skills"   python3 "${SCRIPTS_DIR}/generate_opencode_skills.py"   --check
  run_check "opencode:agents"   python3 "${SCRIPTS_DIR}/generate_opencode_agents.py"   --check
  run_check "opencode:commands" python3 "${SCRIPTS_DIR}/generate_opencode_commands.py" --check
  run_check "opencode:plugin"   python3 "${SCRIPTS_DIR}/generate_opencode_plugin.py"   --check
fi

# ---------------------------------------------------------------------------
# Overall exit code
# ---------------------------------------------------------------------------

OVERALL_RC=0
for rc in "${EXITS[@]}"; do
  [[ "$rc" -ne 0 ]] && { OVERALL_RC=1; break; }
done

# ---------------------------------------------------------------------------
# Human output
# ---------------------------------------------------------------------------

print_human_section() {
  local label="$1" prefix="$2"
  echo ""
  echo "## ${label}"
  local i=0
  while [[ $i -lt ${#NAMES[@]} ]]; do
    local name="${NAMES[$i]}"
    if [[ "$name" == "$prefix" || "$name" == "${prefix}:"* ]]; then
      if [[ "${EXITS[$i]}" -eq 0 ]]; then
        echo "- ${name}: PASS"
      else
        echo "- ${name}: FAIL"
        if [[ -n "${COMBINED[$i]}" ]]; then
          while IFS= read -r line; do printf '  %s\n' "$line"; done < <(printf '%s\n' "${COMBINED[$i]}" | head -3)
          echo "  ---"
          while IFS= read -r line; do printf '  %s\n' "$line"; done <<< "${COMBINED[$i]}"
        fi
      fi
    fi
    i=$((i + 1))
  done
}

# ---------------------------------------------------------------------------
# JSON output — delegate serialization entirely to Python
# ---------------------------------------------------------------------------

build_json() {
  # Pass data via stdin as a newline-delimited payload; Python reads it safely.
  local tmpdir
  tmpdir="$(mktemp -d)"
  local i=0
  while [[ $i -lt ${#NAMES[@]} ]]; do
    printf '%s' "${NAMES[$i]}"    > "${tmpdir}/name_${i}"
    printf '%s' "${EXITS[$i]}"    > "${tmpdir}/exit_${i}"
    printf '%s' "${COMBINED[$i]}" > "${tmpdir}/out_${i}"
    i=$((i + 1))
  done

  python3 - "${#NAMES[@]}" "$tmpdir" "$TARGET" <<'PYEOF'
import json, sys
from datetime import datetime, timezone

n, tmpdir, target = int(sys.argv[1]), sys.argv[2], sys.argv[3]

def rd(p):
    try:
        return open(p).read()
    except FileNotFoundError:
        return ""

names  = [rd(f"{tmpdir}/name_{i}")                      for i in range(n)]
exits  = [int(rd(f"{tmpdir}/exit_{i}") or "0")          for i in range(n)]
outs   = [rd(f"{tmpdir}/out_{i}")                       for i in range(n)]

def tgt(prefix):
    details = [{"name": names[i], "exit": exits[i], "stdout": outs[i], "stderr": ""}
               for i in range(n)
               if names[i] == prefix or names[i].startswith(prefix + ":")]
    return {"drift": any(d["exit"] != 0 for d in details), "details": details}

shown = (["inventory", "cursor", "codex", "opencode"] if target == "all" else [target])
targets_out = {t: tgt(t) for t in shown}
print(json.dumps({
    "as_of":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "targets": targets_out,
    "ok":      all(not v["drift"] for v in targets_out.values()),
}, indent=2))
PYEOF
  rm -rf "$tmpdir"
}

# ---------------------------------------------------------------------------
# Emit report
# ---------------------------------------------------------------------------

if [[ "$FORMAT" == "human" ]]; then
  case "$TARGET" in
    inventory) print_human_section "inventory" "inventory" ;;
    cursor)    print_human_section "cursor"    "cursor"    ;;
    codex)     print_human_section "codex"     "codex"     ;;
    opencode)  print_human_section "opencode"  "opencode"  ;;
    all)
      print_human_section "inventory" "inventory"
      print_human_section "cursor"    "cursor"
      print_human_section "codex"     "codex"
      print_human_section "opencode"  "opencode"
      ;;
  esac
  echo ""
  if [[ $OVERALL_RC -eq 0 ]]; then
    echo "All checks passed. No drift detected."
  else
    echo "Drift detected. See FAIL entries above."
  fi
else
  json_output="$(build_json)"
  echo "$json_output"
  if [[ -n "$JSON_OUT" ]]; then
    printf '%s\n' "$json_output" > "$JSON_OUT"
    echo "report-bundle-drift.sh: JSON report written to $JSON_OUT" >&2
  fi
fi

exit $OVERALL_RC
