#!/usr/bin/env bash
# Regression tests for multi-entry version lockstep in the bundle-release skill.
#
# Exercises the REAL wrappers through YCC_REPO_ROOT sandboxes:
#   - ycc/skills/bundle-release/scripts/bump-version.sh  (semver gate + parity bump)
#   - ycc/skills/bundle-release/scripts/preflight.sh     (clean-tree gate + parity check)
#
# Coverage (roadmap item release-multi-entry / YAN-1120):
#   1. single-entry compatibility (stdout contract, bump, description preserved)
#   2. three-entry marketplace: per-entry parity failures (index 1, 2, metadata),
#      reordered entries, bump updates every entry
#   3. versionless marketplace entries/metadata keep their shape
#   4. optional marketplaces + package manifests: sources bumped, generated
#      surfaces stale-detected, green after simulated regeneration
#   5. ycc-mods / root dev metadata / node_modules / worktree decoys excluded
#   6. malformed later-selected inputs: structured failure, no traceback, no writes
#   7. invalid semver leaves files untouched; dirty tree fails preflight
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPTS="${REPO_ROOT}/ycc/skills/bundle-release/scripts"
BUMP="${SCRIPTS}/bump-version.sh"
PREFLIGHT="${SCRIPTS}/preflight.sh"
PASS=0
FAIL=0
# Git hooks export GIT_DIR/GIT_WORK_TREE and friends; clear them so sandbox
# git calls never point at the caller's repository.
while IFS= read -r git_var; do
  unset "$git_var"
done < <(git rev-parse --local-env-vars)
unset git_var
SANDBOX_ROOT="$(mktemp -d)"
trap 'rm -rf "${SANDBOX_ROOT}"' EXIT
export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="${SANDBOX_ROOT}/gitconfig"
cat >"${GIT_CONFIG_GLOBAL}" <<'EOF'
[user]
	name = ycc test
	email = ycc-test@example.invalid
[init]
	defaultBranch = main
[commit]
	gpgsign = false
[tag]
	gpgsign = false
EOF
FIX=""
ok() {
  PASS=$((PASS + 1))
  echo "ok ${PASS} - $1"
}
not_ok() {
  FAIL=$((FAIL + 1))
  echo "NOT ok - $1" >&2
  [[ -n "${2:-}" ]] && printf '%s\n' "$2" >&2
}
assert_eq() { # <label> <want> <got>
  if [[ "$3" == "$2" ]]; then
    ok "$1"
  else
    not_ok "$1 (got '$3' want '$2')"
  fi
}
assert_contains() { # <label> <haystack> <needle>
  if printf '%s\n' "$2" | grep -Fq -- "$3"; then
    ok "$1"
  else
    not_ok "$1 (missing '$3')" "$2"
  fi
}
assert_not_contains() { # <label> <haystack> <needle>
  if printf '%s\n' "$2" | grep -Fq -- "$3"; then
    not_ok "$1 (unexpected '$3')" "$2"
  else
    ok "$1"
  fi
}
new_fixture() { # <name>
  FIX="${SANDBOX_ROOT}/$1"
  mkdir -p "${FIX}/ycc/.claude-plugin" "${FIX}/.claude-plugin"
  git -C "${FIX}" init -q
}
wf() { # <rel-path-under-fix> (JSON from stdin)
  local path="${FIX}/$1"; mkdir -p "$(dirname "${path}")" && cat >"${path}"
}
commit_fix() { # <message>
  git -C "${FIX}" add -A >/dev/null && git -C "${FIX}" commit -q -m "$1" >/dev/null
}
jexpr() { # <file-under-fix> <python-expr over d> -> prints (expr)(d)["version"]
  python3 - "${FIX}/$1" "$2" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
print((eval(sys.argv[2]))(data)["version"])
PY
}
jset_version() { # <file-under-fix> <python-expr over d> <new-version>
  python3 - "${FIX}/$1" "$2" "$3" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
(eval(sys.argv[2]))(data)["version"] = sys.argv[3]
path.write_text(json.dumps(data, indent=2) + "\n")
PY
}
jset_all_versions() { # <file-under-fix> <new-version> (every "version" key)
  python3 - "${FIX}/$1" "$2" <<'PY'
import json, pathlib, sys
def walk(node: object) -> None:
    if isinstance(node, dict):
        if "version" in node:
            node["version"] = sys.argv[2]
        for value in node.values():
            walk(value)
    elif isinstance(node, list):
        for value in node:
            walk(value)
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
walk(data)
path.write_text(json.dumps(data, indent=2) + "\n")
PY
}
jget_subtree() { # <file-under-fix> <python-expr over d> -> json dump of subtree
  python3 - "${FIX}/$1" "$2" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
print(json.dumps((eval(sys.argv[2]))(data), sort_keys=True))
PY
}
sha() { # <file-under-fix>
  sha256sum "${FIX}/$1" | awk '{print $1}'
}

gen_hashes() { # joined hashes of every generated manifest in the multi fixture
  local g
  for g in packages/ycc/.claude-plugin/plugin.json packages/ycc/package.json \
    packages/claude/ycc-rules/.claude-plugin/plugin.json \
    .codex-plugin/.codex-plugin/plugin.json .codex-plugin/package.json \
    .codex-plugin/ycc/.codex-plugin/plugin.json .cursor-plugin/.cursor-plugin/plugin.json; do
    sha "$g"
  done | tr '\n' ' '
}
OUT=""
run_bump() { # <fixture> <version>...
  OUT="$(YCC_REPO_ROOT="$1" "${BUMP}" "${@:2}" 2>&1)"
}
run_pf() { # <fixture>
  OUT="$(YCC_REPO_ROOT="$1" "${PREFLIGHT}" 2>&1)"
}
write_source_fixture() { # <version>
  local ver="$1"
  wf "ycc/.claude-plugin/plugin.json" <<EOF
{"name": "ycc", "version": "${ver}", "description": "test plugin"}
EOF
  wf ".claude-plugin/marketplace.json" <<EOF
{
  "name": "ycc",
  "metadata": {"version": "${ver}", "repository": "https://example.invalid"},
  "plugins": [
    {"name": "ycc", "version": "${ver}", "description": "bundle", "source": "./ycc"},
    {"name": "bravo", "version": "${ver}", "source": "./packages/ycc"},
    {"name": "alpha", "version": "${ver}", "source": "./ycc-rules"}
  ]
}
EOF
}
# === Case 1: single-entry compatibility =====================================
FIX="${SANDBOX_ROOT}/single"
mkdir -p "${FIX}/ycc/.claude-plugin" "${FIX}/.claude-plugin"
git -C "${FIX}" init -q
wf "ycc/.claude-plugin/plugin.json" <<<'{"name": "ycc", "version": "1.2.3", "description": "test plugin"}'
wf ".claude-plugin/marketplace.json" <<'EOF'
{"name":"ycc","metadata":{"version":"1.2.3"},"plugins":[{"name":"ycc","version":"1.2.3","description":"bundle","source":"./ycc"}]}
EOF
commit_fix "init"
if run_pf "${FIX}"; then
  ok "single: preflight passes"
  assert_contains "single: reports current_version" "${OUT}" "current_version=1.2.3"
  assert_contains "single: reports branch" "${OUT}" "branch=main"
else
  not_ok "single: preflight passes" "${OUT}"
fi
if run_bump "${FIX}" "2.0.0"; then
  assert_eq "single: plugin bumped" "2.0.0" "$(jexpr "ycc/.claude-plugin/plugin.json" 'lambda d: d')"
  assert_eq "single: metadata bumped" "2.0.0" "$(jexpr ".claude-plugin/marketplace.json" 'lambda d: d["metadata"]')"
  assert_eq "single: entry bumped" "2.0.0" "$(jexpr ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][0]')"
  assert_eq "single: description preserved" "bundle" \
    "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plugins"][0]["description"])' "${FIX}/.claude-plugin/marketplace.json")"
else
  not_ok "single: bump succeeds" "${OUT}"
fi
# === Case 2: three entries, reordered, per-entry parity =====================
new_fixture three
write_source_fixture "1.2.3"
commit_fix "init"
if run_pf "${FIX}"; then
  ok "three: preflight passes in lockstep"
else
  not_ok "three: preflight passes in lockstep" "${OUT}"
fi
jset_version ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][1]' "9.9.9"
commit_fix "drift plugins[1]"
if run_pf "${FIX}"; then
  not_ok "three: parity fails on plugins[1] drift"
else
  assert_contains "three: failure names plugins[1].version" "${OUT}" ".claude-plugin/marketplace.json plugins[1].version = 9.9.9"
  assert_not_contains "three: no traceback (plugins[1])" "${OUT}" "Traceback"
fi
jset_version ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][1]' "1.2.3"
jset_version ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][2]' "8.8.8"
commit_fix "drift plugins[2]"
if run_pf "${FIX}"; then
  not_ok "three: parity fails on plugins[2] drift"
else
  assert_contains "three: failure names plugins[2].version" "${OUT}" "plugins[2].version = 8.8.8"
fi
jset_version ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][2]' "1.2.3"
jset_version ".claude-plugin/marketplace.json" 'lambda d: d["metadata"]' "7.7.7"
commit_fix "drift metadata"
if run_pf "${FIX}"; then
  not_ok "three: parity fails on metadata.version drift"
else
  assert_contains "three: failure names metadata.version" "${OUT}" "metadata.version = 7.7.7"
fi
jset_version ".claude-plugin/marketplace.json" 'lambda d: d["metadata"]' "1.2.3"
commit_fix "restore lockstep"
if run_bump "${FIX}" "3.0.0"; then
  assert_eq "three: bump updates plugins[1]" "3.0.0" "$(jexpr ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][1]')"
  assert_eq "three: bump updates plugins[2]" "3.0.0" "$(jexpr ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][2]')"
  assert_eq "three: bump updates metadata" "3.0.0" "$(jexpr ".claude-plugin/marketplace.json" 'lambda d: d["metadata"]')"
else
  not_ok "three: bump succeeds" "${OUT}"
fi
# === Case 3: versionless entries and metadata keep their shape ==============
new_fixture versionless
wf "ycc/.claude-plugin/plugin.json" <<<'{"name": "ycc", "version": "3.0.0", "description": "test plugin"}'
wf ".claude-plugin/marketplace.json" <<'EOF'
{"name":"ycc","plugins":[{"name":"ycc","version":"3.0.0","source":"./ycc"},{"name":"bravo","description":"no version field","source":"./packages/ycc"}]}
EOF
commit_fix "init"
if run_pf "${FIX}"; then
  ok "versionless: preflight passes"
else
  not_ok "versionless: preflight passes" "${OUT}"
fi
BRAVO_BEFORE="$(jget_subtree ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][1]')"
if run_bump "${FIX}" "4.0.0"; then
  assert_eq "versionless: versioned entry bumped" "4.0.0" "$(jexpr ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][0]')"
  assert_not_contains "versionless: versionless entry gains no version" \
    "$(jget_subtree ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][1]')" '"version"'
  assert_eq "versionless: versionless entry unchanged" "${BRAVO_BEFORE}" \
    "$(jget_subtree ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][1]')"
  assert_not_contains "versionless: metadata gains no version" \
    "$(jget_subtree ".claude-plugin/marketplace.json" 'lambda d: d.get("metadata")')" '"version"'
else
  not_ok "versionless: bump succeeds" "${OUT}"
fi
commit_fix "bump"
if run_pf "${FIX}"; then
  ok "versionless: preflight passes after bump"
else
  not_ok "versionless: preflight passes after bump" "${OUT}"
fi
# === Case 4: optional marketplaces + package manifests ======================
new_fixture multi
write_source_fixture "5.0.0"
wf "ycc/package.json" <<<'{"name": "ycc", "version": "5.0.0", "description": "npm package"}'
wf "packages/ycc/.claude-plugin/plugin.json" <<<'{"name": "ycc", "version": "5.0.0"}'
wf "packages/ycc/package.json" <<<'{"name": "@ycc/ycc", "version": "5.0.0"}'
wf "packages/claude/ycc-rules/.claude-plugin/plugin.json" <<<'{"name": "ycc-rules", "version": "5.0.0"}'
wf ".agents/plugins/marketplace.json" <<'EOF'
{
  "name": "local-ycc-plugins",
  "metadata": {"version": "5.0.0"},
  "plugins": [
    {"name": "ycc", "version": "5.0.0"},
    {"name": "bravo", "version": "5.0.0"},
    {"name": "alpha", "version": "5.0.0"}
  ]
}
EOF
wf ".cursor-plugin/marketplace.json" <<'EOF'
{
  "plugins": [
    {"name": "ycc", "version": "5.0.0"},
    {"name": "bravo", "version": "5.0.0"},
    {"name": "alpha", "version": "5.0.0"}
  ]
}
EOF
wf ".codex-plugin/.codex-plugin/plugin.json" <<<'{"name": "ycc", "version": "5.0.0"}'
wf ".codex-plugin/package.json" <<<'{"name": "ycc-codex", "version": "5.0.0"}'
wf ".codex-plugin/ycc/.codex-plugin/plugin.json" <<<'{"name": "ycc", "version": "5.0.0"}'
wf ".cursor-plugin/.cursor-plugin/plugin.json" <<<'{"name": "ycc", "version": "5.0.0"}'
wf ".codex-plugin/versionless/package.json" <<<'{ "name": "versionless", "scripts": {} }'
VERSIONLESS_HASH="$(sha ".codex-plugin/versionless/package.json")"
commit_fix "init"
if run_pf "${FIX}"; then
  ok "multi: preflight passes across all surfaces"
else
  not_ok "multi: preflight passes across all surfaces" "${OUT}"
fi
GEN_HASHES="$(gen_hashes)"
if run_bump "${FIX}" "5.1.0"; then
  assert_eq "multi: generated files preserved byte-identically by bump" "${GEN_HASHES}" "$(gen_hashes)"
  assert_eq "multi: source plugin bumped" "5.1.0" "$(jexpr "ycc/.claude-plugin/plugin.json" 'lambda d: d')"
  assert_eq "multi: ycc/package.json bumped" "5.1.0" "$(jexpr "ycc/package.json" 'lambda d: d')"
  assert_eq "multi: packages/ycc plugin stays old (generated)" "5.0.0" "$(jexpr "packages/ycc/.claude-plugin/plugin.json" 'lambda d: d')"
  assert_eq "multi: packages/claude/ycc-rules stays old (generated)" "5.0.0" "$(jexpr "packages/claude/ycc-rules/.claude-plugin/plugin.json" 'lambda d: d')"
  assert_eq "multi: marketplace entry 2 bumped" "5.1.0" "$(jexpr ".claude-plugin/marketplace.json" 'lambda d: d["plugins"][2]')"
else
  not_ok "multi: bump succeeds" "${OUT}"
fi
assert_eq "multi: versionless generated manifest byte-unchanged" "${VERSIONLESS_HASH}" "$(sha ".codex-plugin/versionless/package.json")"

assert_eq "multi: generated codex plugin stays old" "5.0.0" "$(jexpr ".codex-plugin/.codex-plugin/plugin.json" 'lambda d: d')"
assert_eq "multi: generated agents marketplace stays old" "5.0.0" "$(jexpr ".agents/plugins/marketplace.json" 'lambda d: d["plugins"][1]')"
commit_fix "bump without sync"
if run_pf "${FIX}"; then
  not_ok "multi: preflight fails on stale generated surfaces"
else
  assert_contains "multi: stale generated packages manifest named" "${OUT}" "packages/ycc/.claude-plugin/plugin.json version = 5.0.0"
  assert_contains "multi: stale codex plugin named" "${OUT}" ".codex-plugin/.codex-plugin/plugin.json version = 5.0.0"
  assert_contains "multi: stale agents marketplace named" "${OUT}" ".agents/plugins/marketplace.json plugins[2].version = 5.0.0"
  assert_not_contains "multi: no traceback (stale)" "${OUT}" "Traceback"
fi
# Bump again while generated surfaces are still at 5.0.0; bump must succeed and keep them byte-identical.
if run_bump "${FIX}" "5.2.0"; then
  assert_eq "multi: bump succeeds with stale generated surfaces" "${GEN_HASHES}" "$(gen_hashes)"
else
  not_ok "multi: bump succeeds with stale generated surfaces" "${OUT}"
fi
# Simulate ./scripts/sync.sh regenerating the derived surfaces.
for gen in "packages/ycc/.claude-plugin/plugin.json" "packages/ycc/package.json" \
  "packages/claude/ycc-rules/.claude-plugin/plugin.json" ".agents/plugins/marketplace.json" ".cursor-plugin/marketplace.json" \
  ".codex-plugin/.codex-plugin/plugin.json" ".codex-plugin/package.json" \
  ".codex-plugin/ycc/.codex-plugin/plugin.json" \
  ".cursor-plugin/.cursor-plugin/plugin.json"; do
  jset_all_versions "${gen}" "5.2.0"
done
commit_fix "simulated sync"
if run_pf "${FIX}"; then
  ok "multi: preflight passes after simulated regeneration"
else
  not_ok "multi: preflight passes after simulated regeneration" "${OUT}"
fi
# === Case 5: exclusions =====================================================
new_fixture excluded
write_source_fixture "6.0.0"
wf ".claude-plugin/marketplace.json" <<'EOF'
{
  "name": "ycc",
  "metadata": {"version": "6.0.0"},
  "plugins": [
    {"name": "ycc", "version": "6.0.0", "source": "./ycc"},
    {"name": "ycc-mods", "version": "1.0.0", "source": "./ycc/mods"},
    {"name": "alpha", "version": "6.0.0"},
    {"name": "status-bar-extra", "version": "1.0.0", "source": "./ycc/mods/status-bar"},
    {"name": "charlie", "version": "6.0.0"}
  ]
}
EOF
wf "ycc/mods/.claude-plugin/marketplace.json" <<<'{ "name": "ycc-mods", "metadata": {"version": "1.0.0"}, "plugins": [{"name": "status-bar", "version": "1.0.0"}] }'
wf "ycc/mods/status-bar/.claude-plugin/plugin.json" <<<'{"name": "status-bar", "version": "1.0.0"}'
wf "ycc/mods/package.json" <<<'{"name": "ycc-mods", "version": "1.0.0"}'
wf "package.json" <<<'{"name": "repo-dev-deps", "version": "9.9.9", "devDependencies": {"lefthook": "^1.8.0"}}'
wf "node_modules/thing/.claude-plugin/plugin.json" <<<'{"name": "thing", "version": "0.0.1"}'
wf ".opencode/worktrees/other/.codex-plugin/.codex-plugin/plugin.json" <<<'{"name": "ycc", "version": "0.0.1"}'
wf ".agents/plugins/marketplace.json" <<'EOF'
{
  "plugins": [
    {"name": "ycc", "version": "6.0.0"},
    {"name": "ycc", "version": "6.0.0"},
    {"name": "mod-alias", "version": "1.0.0", "source": {"source": "local", "path": "./ycc/mods"}},
    {"name": "bar-alias", "version": "1.0.0", "source": {"source": "local", "path": "ycc/mods/status-bar"}}
  ]
}
EOF
commit_fix "init"
if run_pf "${FIX}"; then
  ok "excluded: ycc-mods and dev decoys do not break parity"
else
  not_ok "excluded: ycc-mods and dev decoys do not break parity" "${OUT}"
fi
MODS_HASH="$(sha "ycc/mods/.claude-plugin/marketplace.json");$(sha "ycc/mods/status-bar/.claude-plugin/plugin.json");$(sha "ycc/mods/package.json")"
SRC_ENTRIES_BEFORE="$(jget_subtree ".claude-plugin/marketplace.json" 'lambda d: [e for e in d["plugins"] if e["name"] in ("ycc-mods","status-bar-extra")]')"
AGENTS_ENTRIES_BEFORE="$(jget_subtree ".agents/plugins/marketplace.json" 'lambda d: [e for e in d["plugins"] if e["name"] in ("mod-alias","bar-alias")]')"
ROOT_PKG_HASH="$(sha "package.json")"
if run_bump "${FIX}" "6.1.0"; then
  assert_eq "excluded: mods marketplace untouched" "${MODS_HASH}" \
    "$(sha "ycc/mods/.claude-plugin/marketplace.json");$(sha "ycc/mods/status-bar/.claude-plugin/plugin.json");$(sha "ycc/mods/package.json")"
  assert_eq "excluded: root package.json untouched" "${ROOT_PKG_HASH}" "$(sha "package.json")"
  assert_eq "excluded: string-source ycc/mods entries unchanged" "${SRC_ENTRIES_BEFORE}" \
    "$(jget_subtree ".claude-plugin/marketplace.json" 'lambda d: [e for e in d["plugins"] if e["name"] in ("ycc-mods","status-bar-extra")]')"
  assert_eq "excluded: dict-source ycc/mods entries unchanged" "${AGENTS_ENTRIES_BEFORE}" \
    "$(jget_subtree ".agents/plugins/marketplace.json" 'lambda d: [e for e in d["plugins"] if e["name"] in ("mod-alias","bar-alias")]')"
else
  not_ok "excluded: bump succeeds" "${OUT}"
fi
# === Case 6: malformed later-selected inputs ================================
new_fixture malformed
write_source_fixture "2.0.0"
wf ".agents/plugins/marketplace.json" <<<'{"plugins": [{"name": "ycc", "version": "2.0.0"}]}'
commit_fix "init"
printf '{"plugins": [{"name": "ycc", "version": ' >"${FIX}/.agents/plugins/marketplace.json"
commit_fix "corrupt agents marketplace"
HASHES="$(sha "ycc/.claude-plugin/plugin.json");$(sha ".claude-plugin/marketplace.json")"
if run_pf "${FIX}"; then
  not_ok "malformed: preflight fails on invalid JSON"
else
  assert_contains "malformed: invalid JSON named" "${OUT}" ".agents/plugins/marketplace.json: invalid JSON"
  assert_not_contains "malformed: no traceback (JSON)" "${OUT}" "Traceback"
fi
if run_bump "${FIX}" "2.1.0"; then
  not_ok "malformed: bump fails on invalid JSON"
else
  assert_not_contains "malformed: bump has no traceback" "${OUT}" "Traceback"
  assert_eq "malformed: no file mutated by failed bump" "${HASHES}" \
    "$(sha "ycc/.claude-plugin/plugin.json");$(sha ".claude-plugin/marketplace.json")"
fi
wf ".agents/plugins/marketplace.json" <<<'{"plugins": [{"name": "ycc", "version": "2.0.0"}]}'
python3 - "${FIX}/.claude-plugin/marketplace.json" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
data["plugins"][2]["version"] = 7
path.write_text(json.dumps(data, indent=2) + "\n")
PY
commit_fix "int version"
if run_pf "${FIX}"; then
  not_ok "malformed: preflight fails on non-string version"
else
  assert_contains "malformed: non-string version named" "${OUT}" "plugins[2].version: expected non-empty string"
fi
if run_bump "${FIX}" "2.1.0"; then
  not_ok "malformed: bump fails on non-string version"
else
  assert_eq "malformed: no mutation after type error" "7" \
    "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["plugins"][2]["version"])' "${FIX}/.claude-plugin/marketplace.json")"
fi
wf ".claude-plugin/marketplace.json" <<<'{"name": "ycc", "plugins": {"ycc": {"version": "2.0.0"}}}'
commit_fix "plugins not a list"
if run_pf "${FIX}"; then
  not_ok "malformed: preflight fails when plugins is not an array"
else
  assert_contains "malformed: shape error named" "${OUT}" ".claude-plugin/marketplace.json: plugins: expected non-empty array"
fi
write_source_fixture "2.0.0"
printf '{"name": "escape", "version": "0.0.1"}\n' >"${SANDBOX_ROOT}/escape-target.json"
rm "${FIX}/.agents/plugins/marketplace.json"
ln -s "${SANDBOX_ROOT}/escape-target.json" "${FIX}/.agents/plugins/marketplace.json"
commit_fix "symlink decoy"
if run_pf "${FIX}"; then
  not_ok "symlink: preflight rejects symlink escaping root"
else
  assert_contains "symlink: escape named" "${OUT}" ".agents/plugins/marketplace.json"
  assert_not_contains "symlink: no traceback" "${OUT}" "Traceback"
fi
SRC_HASHES="$(sha "ycc/.claude-plugin/plugin.json");$(sha ".claude-plugin/marketplace.json")"
if run_bump "${FIX}" "2.1.0"; then
  not_ok "symlink: bump rejected without writes"
else
  assert_eq "symlink: no writes on rejection" "${SRC_HASHES}" "$(sha "ycc/.claude-plugin/plugin.json");$(sha ".claude-plugin/marketplace.json")"
fi
rm "${FIX}/.agents/plugins/marketplace.json"
# === Case 7: wrapper gates ==================================================
new_fixture gates
write_source_fixture "1.0.0"
commit_fix "init"
PLUGIN_HASH="$(sha "ycc/.claude-plugin/plugin.json")"
if run_bump "${FIX}" "2.x"; then
  not_ok "gates: invalid semver rejected"
else
  assert_contains "gates: semver failure explained" "${OUT}" "invalid semver"
  assert_eq "gates: no mutation on invalid semver" "${PLUGIN_HASH}" "$(sha "ycc/.claude-plugin/plugin.json")"
fi
echo "stale" >"${FIX}/README.md"
commit_fix "dirty tree"
echo "dirty" >"${FIX}/README.md"
if run_pf "${FIX}"; then
  not_ok "gates: dirty tree fails preflight"
else
  assert_contains "gates: dirty tree explained" "${OUT}" "git working tree is not clean"
fi
git -C "${FIX}" checkout -- README.md
# === Case 8: emitted staging and rollback commands ==========================
new_fixture staging
write_source_fixture "1.0.0"
wf "ycc/package.json" <<<'{"name": "ycc", "version": "1.0.0"}'
wf "packages/ycc/package.json" <<<'{"name": "@ycc/ycc", "version": "1.0.0"}'
wf ".codex-plugin/ycc/.codex-plugin/plugin.json" <<<'{"name": "ycc", "version": "1.0.0"}'
wf "docs/inventory.json" <<<'{"skills": 1}'
commit_fix "init"
SKILL_DOC="${REPO_ROOT}/ycc/skills/bundle-release/SKILL.md"
CHECKLIST_DOC="${REPO_ROOT}/ycc/skills/bundle-release/references/release-checklist.md"
ROLLBACK_LOOP="$(awk '/^for path in/{flag=1; buf=""} flag{buf=buf $0 "\n"} /^done$/ && flag{print buf; exit}' "${SKILL_DOC}")"
STAGE_LOOP="$(awk '/^for path in/{c++; buf=""} c==2{buf=buf $0 "\n"} /^done$/ && c==2{print buf; exit}' "${SKILL_DOC}" | sed 's/<new-version>/1.1.0/g')"
CL_STAGE_LOOP="$(awk '/^for path in/{flag=1; buf=""} flag{buf=buf $0 "\n"} /^done$/ && flag{print buf; exit}' "${CHECKLIST_DOC}" | sed 's/<new-version>/1.1.0/g')"
assert_eq "docs: SKILL.md and checklist staging loops match" "${STAGE_LOOP}" "${CL_STAGE_LOOP}"
run_bump "${FIX}" "1.1.0"
rm "${FIX}/packages/ycc/package.json"
(cd "${FIX}" && eval "${ROLLBACK_LOOP}")
assert_eq "rollback: restores bumped ycc/package.json" "1.0.0" "$(jexpr "ycc/package.json" 'lambda d: d')"
assert_eq "rollback: restores deleted generated package file" "1.0.0" "$(jexpr "packages/ycc/package.json" 'lambda d: d')"
assert_eq "rollback: leaves clean git status" "" "$(git -C "${FIX}" status --porcelain)"
run_bump "${FIX}" "1.1.0"
jset_all_versions "packages/ycc/package.json" "1.1.0"
jset_all_versions ".codex-plugin/ycc/.codex-plugin/plugin.json" "1.1.0"
wf "docs/releases/1.1.0.md" <<<'# v1.1.0'
(cd "${FIX}" && eval "${STAGE_LOOP}")
assert_eq "staging: leaves zero unstaged changes" "" "$(git -C "${FIX}" diff --name-only)"
assert_contains "staging: stages ycc/package.json" "$(git -C "${FIX}" diff --cached --name-only)" "ycc/package.json"
assert_contains "staging: stages generated packages/" "$(git -C "${FIX}" diff --cached --name-only)" "packages/ycc/package.json"
# Generated runtime copies must keep the source manifest discovery tuple.
for bundle in .opencode-plugin/skills .codex-plugin/ycc/skills packages/cursor/ycc/skills .agents-plugin/skills; do
  assert_contains "generated ${bundle%%/*}: keeps .claude-plugin manifest discovery" \
    "$(grep -F 'MANIFEST_SUBDIRS =' "${REPO_ROOT}/${bundle}/bundle-release/scripts/release_versions.py")" \
    'MANIFEST_SUBDIRS = (".claude-plugin", ".codex-plugin", ".cursor-plugin")'
done
echo
echo "test-release-bundle: ${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
