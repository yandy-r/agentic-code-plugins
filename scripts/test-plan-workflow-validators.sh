#!/usr/bin/env bash
# Regression checks for validate-workflow-plan.sh and validate-shared.sh
# Usage: scripts/test-plan-workflow-validators.sh
# - temp fixtures via mktemp, trap cleanup; no test framework
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../ycc/skills/plan-workflow/scripts" && pwd)"
VAL_PLAN="${SCRIPT_DIR}/validate-workflow-plan.sh"
VAL_SHARED="${SCRIPT_DIR}/validate-shared.sh"
FAIL=0

ok() { echo "PASS: $1"; }
bad() { echo "FAIL: $1"; FAIL=1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- structurally complete plan fixture ---
cat > "${TMP}/good.md" <<'EOF'
# Feature X

This overview sentence one. Sentence two here. Sentence three here. Sentence four here. Sentence five here. Sentence six here. Sentence seven here. Sentence eight here.

## Critically Relevant Files

- src/a.ts
- src/b.ts

## Worktree Setup

- **Parent**: repo/.claude/worktrees/repo-x/ (branch: feat/x)

## Implementation Plan

### Phase 1: Foundation

#### Task 1.1: Build

Depends on [none]

READ THESE BEFORE TASK

Files to Create

Files to Modify

#### Task 1.2: Wire

Depends on [1.1]

READ THESE BEFORE TASK

Files to Create

Files to Modify

## Advice

- keep it simple
EOF

out="$("${VAL_PLAN}" "${TMP}/good.md" 2>&1)"
rc=$?
if [[ $rc -eq 0 ]]; then ok "valid plan exits 0"; else bad "valid plan exits 0 (got $rc)"; fi
if echo "$out" | grep -qiE "syntax error|command not found|unbound variable|bad substitution"; then
  bad "stderr has shell/arithmetic syntax errors"
else
  ok "no arithmetic/syntax errors in stderr"
fi

# --- missing ### Phase ---
sed '/^### Phase/d' "${TMP}/good.md" > "${TMP}/nophase.md"
"${VAL_PLAN}" "${TMP}/nophase.md" >/dev/null 2>&1
if [[ $? -ne 0 ]]; then ok "missing ### Phase exits nonzero"; else bad "missing ### Phase exits nonzero"; fi

# --- missing #### Task ---
sed '/^#### Task/d; s/Depends on \[[^]]*\]/Depends on [none]/g' "${TMP}/good.md" > "${TMP}/notask.md"
"${VAL_PLAN}" "${TMP}/notask.md" >/dev/null 2>&1
if [[ $? -ne 0 ]]; then ok "missing #### Task exits nonzero"; else bad "missing #### Task exits nonzero"; fi

# --- zero-match counts still compute (regression for the || echo "0" bug) ---
sed '/^- src/d' "${TMP}/good.md" > "${TMP}/nofiles.md"
out2="$("${VAL_PLAN}" "${TMP}/nofiles.md" 2>&1)"
if echo "$out2" | grep -qiE "syntax error|command not found|unbound variable|bad substitution"; then
  bad "zero-match counts still compute"
else
  ok "zero-match counts still compute"
fi

# --- validate-shared zero-warning path ---
cat > "${TMP}/shared.md" <<'EOF'
# Shared X

Overview sentence one. Sentence two here. Sentence three here. Sentence four here and more words here.

## Relevant Files

- src/a.ts - core module

## Relevant Patterns

- **Repo**: the repo pattern (/src/a.ts) — see [code](src/a.ts)

## Relevant Docs

- You _must_ read this doc first.
EOF
out3="$("${VAL_SHARED}" "${TMP}/shared.md" 2>&1)"
rc3=$?
if echo "$out3" | grep -qiE "syntax error|command not found|unbound variable|bad substitution"; then
  bad "validate-shared zero-warning path errors"
else
  ok "validate-shared zero-warning path clean (exit $rc3)"
fi

if [[ $FAIL -eq 0 ]]; then echo "ALL PASS"; else echo "SOME FAILED"; fi
exit $FAIL
