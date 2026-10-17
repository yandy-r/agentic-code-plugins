#!/usr/bin/env bash
# Fixture HOME proof for global migration. No real plugin CLI is contacted.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "== install.sh migrate: parser, preview and ownership =="
# Unlike the shared runner's intentionally non-errexit assertions, fixture
# construction must abort immediately on errors, even when sourced in a loop.
migrate_fixture_must_succeed() {
    "$@" || { ko "migration fixture setup: $*"; exit 1; }
}

# Snapshot includes directory names, file bytes, modes and symlink text. A
# dry-run must not even create a state directory or CLI log.
migrate_snapshot() {
    python3 - "$1" <<'PY'
import hashlib, os, sys
from pathlib import Path
root = Path(sys.argv[1])
items = []
for path in sorted(root.rglob('*')):
    kind = 'link' if path.is_symlink() else 'dir' if path.is_dir() else 'file'
    content = os.readlink(path).encode() if kind == 'link' else path.read_bytes() if kind == 'file' else b''
    items.append((str(path.relative_to(root)), kind, path.lstat().st_mode, hashlib.sha256(content).hexdigest()))
print(repr(items))
PY
}

for target in opencode agents bogus; do
    home="$(new_home)"
    if out="$(run_install "${home}" migrate --target "${target}" --apply)"; then
        ko "migrate rejects unsupported ${target}"
    else
        assert_contains "${out}" "not supported" "migrate rejects unsupported ${target}"
    fi
done
home="$(new_home)"
for flag in --force --mode --only --intent --settings --rules --mcp --hooks --mcps --package --skills-home --project --global; do
    if out="$(run_install "${home}" migrate --target cursor "${flag}")"; then ko "migrate rejects ${flag}"; else ok "migrate rejects ${flag}"; fi
done
if out="$(run_install "${home}" migrate --target cursor --marketplace-source "${REPO_ROOT}")"; then
    ko "marketplace source requires Codex"
else
    assert_contains "${out}" "only supported with the codex" "marketplace source requires Codex"
fi
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target all
assert_contains "${INSTALL_OUT}" "claude,codex,cursor" "all resolves only supported migrations"
if repo_codex_native; then
    assert_contains "${INSTALL_OUT}" "Codex: would add marketplace" "listed Codex preview forecasts the native migration"
else
    assert_contains "${INSTALL_OUT}" "YAN-1140" "unlisted Codex preview explains listing gate"
fi
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "all preview changes no HOME bytes or entries" || ko "all preview changes no HOME bytes or entries"

# v6 deprecation hints: install/sync on a listed native target points at migrate;
# remove and targets without a native listing stay quiet.
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings --global
assert_contains "${INSTALL_OUT}" "migrate --target claude" "claude sync prints the native deprecation hint"
install_must_succeed "${home}" remove --target claude --intent settings --global
assert_not_contains "${INSTALL_OUT}" "deprecated:" "remove prints no deprecation hint"
install_must_succeed "${home}" sync --target agents --intent skills
assert_not_contains "${INSTALL_OUT}" "deprecated:" "agents sync prints no deprecation hint"

# Real managed state first, then a user-owned command in the same event group.
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings,hooks,mcp --global
migrate_fixture_must_succeed python3 - "${home}" <<'PY'
import json, sys
from pathlib import Path
home = Path(sys.argv[1])
p = home / '.claude/settings.json'
data = json.loads(p.read_text())
data['enabledPlugins'] = {'ycc-hooks@ycc': True, 'ycc-mcp@ycc': True}
data['hooks']['WorktreeCreate'][0]['hooks'].append({'type': 'command', 'command': 'echo my-hook'})
data['editorMode'] = 'vim'
p.write_text(json.dumps(data, indent=2) + '\n')
p = home / '.claude.json'
data = json.loads(p.read_text())
data['mcpServers']['mine'] = {'url': 'https://mine.example'}
# A changed managed entry must survive removal as well.
first = next(name for name in data['mcpServers'] if name != 'mine')
data['mcpServers'][first] = {'url': 'https://edited.example'}
p.write_text(json.dumps(data, indent=2) + '\n')
PY
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target claude
assert_contains "${INSTALL_OUT}" "would remove" "Claude migration previews command pruning"
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Claude preview preserves config and managed state bytes" || ko "Claude preview preserves config and managed state bytes"
install_must_succeed "${home}" migrate --target claude --apply
assert_contains "$(cat "${home}/.claude/settings.json")" "echo my-hook" "Claude keeps user hook within managed wrapper"
assert_not_contains "$(cat "${home}/.claude/settings.json")" "worktree-create.sh" "Claude prunes only managed hook command"
assert_contains "$(cat "${home}/.claude/settings.json")" '"editorMode": "vim"' "Claude keeps unrelated settings"
assert_contains "$(cat "${home}/.claude.json")" "edited.example" "Claude keeps edited managed MCP"
assert_contains "$(cat "${home}/.claude.json")" "mine.example" "Claude keeps foreign MCP"
[[ ! -L "${home}/.claude/hooks" ]] && ok "Claude removes exactly owned unused hooks link" || ko "Claude removes exactly owned unused hooks link"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target claude --apply
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Claude repeated apply is byte-stable" || ko "Claude repeated apply is byte-stable"

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings,hooks,mcp --global
migrate_fixture_must_succeed python3 - "${home}/.claude/settings.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['enabledPlugins'] = {'ycc-all@ycc': True, 'ycc-hooks@ycc': False, 'ycc-mcp@ycc': False}
p.write_text(json.dumps(data) + '\n')
PY
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target claude --apply
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Claude disabled native plugins and aggregate do not authorize cleanup" || ko "Claude disabled native plugins and aggregate do not authorize cleanup"

# No ownership proof: preview and apply must both retain the command and link.
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings,hooks --global
migrate_fixture_must_succeed python3 - "${home}/.claude/settings.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['enabledPlugins'] = {'ycc-hooks@ycc': True}
p.write_text(json.dumps(data, indent=2) + '\n')
PY
migrate_fixture_must_succeed rm -f "${home}/.config/ycc/managed-config-state.json"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target claude
assert_not_contains "${INSTALL_OUT}" "would remove ${home}/.claude/hooks" "Claude no-state preview does not forecast hooks link removal"
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Claude no-state preview writes nothing" || ko "Claude no-state preview writes nothing"
install_must_succeed "${home}" migrate --target claude --apply
assert_contains "$(cat "${home}/.claude/settings.json")" "worktree-create.sh" "Claude no-state apply retains unproven hook"
[[ -L "${home}/.claude/hooks" && "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Claude no-state apply is consistent with preview" || ko "Claude no-state apply is consistent with preview"

# Symlinked config leaves are retained with their targets and ownership state.
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings,hooks,mcp --global
migrate_fixture_must_succeed mv "${home}/.claude/settings.json" "${home}/settings-target.json"
migrate_fixture_must_succeed python3 - "${home}/settings-target.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['enabledPlugins'] = {'ycc-hooks@ycc': True, 'ycc-mcp@ycc': True}
p.write_text(json.dumps(data, indent=2) + '\n')
PY
migrate_fixture_must_succeed ln -s "${home}/settings-target.json" "${home}/.claude/settings.json"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target claude --apply
assert_contains "${INSTALL_OUT}" "symlinked config file" "Claude symlinked settings leaf is reported"
[[ "$(migrate_snapshot "${home}")" == "${before}" && -L "${home}/.claude/settings.json" && -L "${home}/.claude/hooks" ]] && ok "Claude symlinked settings leaf, target, state and hooks link retained" || ko "Claude symlinked settings leaf, target, state and hooks link retained"

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent settings,mcp --global
migrate_fixture_must_succeed python3 - "${home}/.claude/settings.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['enabledPlugins'] = {'ycc-mcp@ycc': True}
p.write_text(json.dumps(data, indent=2) + '\n')
PY
migrate_fixture_must_succeed mv "${home}/.claude.json" "${home}/claude-json-target.json"
migrate_fixture_must_succeed ln -s "${home}/claude-json-target.json" "${home}/.claude.json"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target claude --apply
[[ "$(migrate_snapshot "${home}")" == "${before}" && -L "${home}/.claude.json" ]] && ok "Claude symlinked MCP leaf, target and state retained" || ko "Claude symlinked MCP leaf, target and state retained"

# Cursor base copies, projected slice init, helpers, edits, unknown entries,
# and foreign links all coexist in one fixture.
home="$(new_home)"
for unit in skills agents rules; do
    src="${REPO_ROOT}/packages/cursor/ycc/${unit}"
    [[ "${unit}" == rules ]] && src="${REPO_ROOT}/packages/cursor/ycc-rules/rules"
    mkdir -p "${home}/.cursor/${unit}"
    cp -R "${src}/." "${home}/.cursor/${unit}/"
done
# Install the slice from an empty skill destination so projected init is
# genuinely installed rather than a rejected overwrite of raw package bytes.
migrate_fixture_must_succeed rm -rf "${home}/.cursor/skills"
migrate_fixture_must_succeed env HOME="${home}" YCC_MANAGED_CONFIG_STATE="${home}/.config/ycc/managed-config-state.json" \
    python3 "${REPO_ROOT}/scripts/install_slices.py" install --target cursor --slice skills >/dev/null
printf '\nuser edit\n' >> "${home}/.cursor/skills/git-workflow/SKILL.md"
mkdir -p "${home}/.cursor/skills/mine"
printf 'mine\n' > "${home}/.cursor/skills/mine/SKILL.md"
# Use a canonical rule filename but foreign content/link.
rule="$(python3 - "${REPO_ROOT}/packages/cursor/ycc-rules/rules" <<'PY'
from pathlib import Path
import sys
print(next(iter(sorted(Path(sys.argv[1]).iterdir()))).name)
PY
)"
rm -f "${home}/.cursor/rules/${rule}"
ln -s /foreign/rule "${home}/.cursor/rules/${rule}"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target cursor
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Cursor preview preserves files and tracking state" || ko "Cursor preview preserves files and tracking state"
install_must_succeed "${home}" migrate --target cursor --apply
assert_contains "${INSTALL_OUT}" "/add-plugin" "Cursor prints interactive native install step"
[[ -d "${home}/.cursor/skills/_shared" ]] && ok "Cursor retains _shared while any skill remains" || ko "Cursor retains _shared while any skill remains"
assert_contains "$(cat "${home}/.cursor/skills/git-workflow/SKILL.md")" "user edit" "Cursor recorded names never authorize deleting edits"
[[ -d "${home}/.cursor/skills/mine" && -L "${home}/.cursor/rules/${rule}" ]] && ok "Cursor preserves foreign entries and foreign links" || ko "Cursor preserves foreign entries and foreign links"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target cursor --apply
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Cursor repeated apply is byte-stable" || ko "Cursor repeated apply is byte-stable"

# Package carriers must retire before skills: no active wrappers or duplicate
# sessionStart registration may survive a successful migration.
home="$(new_home)"
install_must_succeed "${home}" install --target cursor --only skills,commands,hooks --skills-home native
printf 'my independent command\n' > "${home}/.cursor/commands/mine.md"
migrate_fixture_must_succeed python3 - "${home}/.cursor/hooks.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text())
data['hooks']['sessionStart'].append({'command': 'echo my-session-hook'})
path.write_text(json.dumps(data, indent=2) + '\n')
PY
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target cursor
assert_contains "${INSTALL_OUT}" "would retire" "Cursor preview includes carrier retirement"
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Cursor carrier preview preserves all bytes and state" || ko "Cursor carrier preview preserves all bytes and state"
install_must_succeed "${home}" migrate --target cursor --apply
[[ ! -e "${home}/.cursor/commands/clean.md" && ! -e "${home}/.cursor/skills/clean" ]] && ok "Cursor removes managed wrappers before their skills" || ko "Cursor removes managed wrappers before their skills"
[[ ! -e "${home}/.cursor/hooks/herdr-session-start.sh" ]] && ok "Cursor retires installer hook script" || ko "Cursor retires installer hook script"
assert_not_contains "$(cat "${home}/.cursor/hooks.json")" "herdr-session-start.sh" "Cursor retires installer sessionStart registration"
assert_contains "$(cat "${home}/.cursor/hooks.json")" "echo my-session-hook" "Cursor preserves foreign sessionStart command"
assert_contains "$(cat "${home}/.cursor/commands/mine.md")" "my independent command" "Cursor preserves foreign command file"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target cursor --apply
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Cursor carrier repeated apply is byte-stable" || ko "Cursor carrier repeated apply is byte-stable"

# Every refusal must happen before removing any other carrier or skill.
for conflict in edited-command edited-script lost-hook-state lost-command-state malformed-hooks symlink-hooks; do
    home="$(new_home)"
    install_must_succeed "${home}" install --target cursor --only skills,commands,hooks --skills-home native
    case "${conflict}" in
        edited-command) printf '\nmy edit\n' >> "${home}/.cursor/commands/clean.md" ;;
        edited-script) printf '\n# my edit\n' >> "${home}/.cursor/hooks/herdr-session-start.sh" ;;
        lost-hook-state) migrate_fixture_must_succeed rm "${home}/.config/ycc/managed-config-state.json" ;;
        lost-command-state) migrate_fixture_must_succeed rm "${home}/.config/ycc/installed-units.json" ;;
        malformed-hooks) printf '{\n' > "${home}/.cursor/hooks.json" ;;
        symlink-hooks)
            migrate_fixture_must_succeed mv "${home}/.cursor/hooks.json" "${home}/saved-hooks.json"
            migrate_fixture_must_succeed ln -s "${home}/saved-hooks.json" "${home}/.cursor/hooks.json"
            ;;
    esac
    before="$(migrate_snapshot "${home}")"
    for apply in preview apply; do
        flags=()
        [[ "${apply}" == apply ]] && flags+=(--apply)
        if out="$(run_install "${home}" migrate --target cursor "${flags[@]}")"; then
            ko "Cursor ${conflict} ${apply} fails closed"
        else
            ok "Cursor ${conflict} ${apply} fails closed"
        fi
        assert_contains "${out}" "before applying or activating native packages" "Cursor ${conflict} ${apply} explains resolution"
        [[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Cursor ${conflict} ${apply} leaves every carrier and skill intact" || ko "Cursor ${conflict} ${apply} leaves every carrier and skill intact"
    done
done

# A symlink in the init projection aborts before staging or writes. This case
# runs against an isolated checkout copy because it corrupts one source file.
repo_copy="${SANDBOX_ROOT}/migrate-repo-copy"
migrate_fixture_must_succeed rsync -a --exclude .git --exclude .omp --exclude node_modules "${REPO_ROOT}/" "${repo_copy}/"
migrate_fixture_must_succeed python3 - "${repo_copy}/packages/cursor/ycc/skills/init/scripts/generate-mcp-catalog.sh" "${SANDBOX_ROOT}/projection-target" <<'PY'
import sys
from pathlib import Path
script, target = map(Path, sys.argv[1:])
target.write_text('must stay unchanged\n')
script.unlink()
script.symlink_to(target)
PY
install_repo="${REPO_ROOT}"
install_entrypoint="${INSTALL}"
INSTALL="${repo_copy}/install.sh"
REPO_ROOT="${repo_copy}"
home="$(new_home)"
for unit in skills agents rules; do
    src="${REPO_ROOT}/packages/cursor/ycc/${unit}"
    [[ "${unit}" == rules ]] && src="${REPO_ROOT}/packages/cursor/ycc-rules/rules"
    mkdir -p "${home}/.cursor/${unit}"
    cp -R "${src}/." "${home}/.cursor/${unit}/"
done
before="$(migrate_snapshot "${home}")"
if out="$(run_install "${home}" migrate --target cursor)"; then ko "Cursor symlink projection preview aborts"; else ok "Cursor symlink projection preview aborts"; fi
assert_contains "$(cat "${SANDBOX_ROOT}/projection-target")" "must stay unchanged" "Cursor preview does not write through interior symlinks"
if out="$(run_install "${home}" migrate --target cursor --apply)"; then ko "Cursor symlink projection aborts"; else ok "Cursor symlink projection aborts"; fi
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Cursor symlink projection leaves the fixture unchanged" || ko "Cursor symlink projection leaves the fixture unchanged"
REPO_ROOT="${install_repo}"
INSTALL="${install_entrypoint}"
unset repo_copy install_repo install_entrypoint
home="$(new_home)"
mkdir -p "${home}/foreign-skills/init"
printf 'keep\n' > "${home}/foreign-skills/init/SKILL.md"
ln -s "${home}/foreign-skills" "${home}/.cursor/skills"
before="$(migrate_snapshot "${home}")"
install_must_succeed "${home}" migrate --target cursor --apply
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Cursor never traverses symlinked parents" || ko "Cursor never traverses symlinked parents"

# Full post-listing path uses a generated native export, not changed production
# catalog bytes. The stub implements the observed Codex JSON response schema.
native_source="${SANDBOX_ROOT}/native-marketplace"
migrate_fixture_must_succeed python3 "${REPO_ROOT}/scripts/generate_codex_plugin.py" --native-output "${native_source}" >/dev/null
old_stub_bin="${STUB_BIN}"
STUB_BIN="${SANDBOX_ROOT}/migration-bin"
mkdir -p "${STUB_BIN}"
cat > "${STUB_BIN}/codex" <<'PY'
#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
home = Path.home(); args = sys.argv[1:]
with (home / 'claude-calls.log').open('a') as f: f.write('codex ' + ' '.join(args) + '\n')
fail = home / 'fail-command'
if fail.exists() and fail.read_text().strip() in ' '.join(args):
    print('intentional command failure', file=sys.stderr); sys.exit(9)
version = json.loads((Path(os.environ['MIGRATE_NATIVE_SOURCE']) / '.codex-plugin/ycc/.codex-plugin/plugin.json').read_text())['version']
ids = ['ycc@ycc', 'ycc-mcp@ycc']
installed_marker = home / 'native-installed'
if args[:2] == ['plugin', 'add'] and len(args) > 2 and args[2] in ids:
    installed_marker.touch()
if args[:3] == ['plugin', 'marketplace', 'add']:
    result = {'marketplaceName': 'ycc'}
elif args[:2] == ['plugin', 'list']:
    # Real codex-cli 0.161 shape: installed ids leave `available` entirely.
    row = lambda p, installed: {'pluginId': p, 'installed': installed, 'enabled': installed and not (home / 'native-off').exists(), 'version': version}
    installed = installed_marker.exists()
    result = {'available': [] if installed else [row(p, False) for p in ids],
              'installed': [row(p, True) for p in ids] if installed else []}
else:
    result = {}
print(json.dumps(result))
PY
chmod +x "${STUB_BIN}/codex"
export MIGRATE_NATIVE_SOURCE="${native_source}"

migrate_codex_fixture() {
    local fixture_home="$1"
    mkdir -p "${fixture_home}/.codex/plugins/cache/local-ycc-plugins" "${fixture_home}/.agents/plugins" "${fixture_home}/.codex/agents"
    ln -s "${REPO_ROOT}/.codex-plugin/ycc" "${fixture_home}/.codex/plugins/ycc"
    ln -s "${REPO_ROOT}/.codex-plugin/ycc" "${fixture_home}/.agents/plugins/ycc"
    cp -R "${REPO_ROOT}/.codex-plugin/ycc" "${fixture_home}/.codex/plugins/cache/local-ycc-plugins/ycc"
    cp -R "${REPO_ROOT}/.codex-plugin/agents/." "${fixture_home}/.codex/agents/"
    printf 'name = "mine"\n' > "${fixture_home}/.codex/agents/mine.toml"
    cat > "${fixture_home}/.codex/config.toml" <<'TOML'
# my settings
[plugins."ycc@local-ycc-plugins"]
enabled = true
[plugins."mine@other"]
enabled = true
TOML
    python3 "${REPO_ROOT}/scripts/codex_marketplace.py" merge "${fixture_home}/.agents/plugins/marketplace.json" local ./.agents/plugins/ycc
}

home="$(new_home)"; migrate_codex_fixture "${home}"
before="$(migrate_snapshot "${home}")"
if ! repo_codex_native; then
    if out="$(run_install "${home}" migrate --target codex --apply)"; then ko "Codex production gate fails closed"; else ok "Codex production gate fails closed"; fi
    [[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "Codex gate fails before any CLI or cleanup" || ko "Codex gate fails before any CLI or cleanup"
else
    skip_listed "Codex production gate fails closed"
    skip_listed "Codex gate fails before any CLI or cleanup"
fi
install_must_succeed "${home}" migrate --target codex --marketplace-source "${native_source}"
[[ "$(migrate_snapshot "${home}")" == "${before}" ]] && ok "eligible Codex preview invokes no CLI or cleanup" || ko "eligible Codex preview invokes no CLI or cleanup"
for failure in command native-off; do
    if [[ "${failure}" == command ]]; then printf 'plugin add ycc-mcp@ycc\n' > "${home}/fail-command"; else touch "${home}/native-off"; fi
    legacy_before="$(migrate_snapshot "${home}/.codex")"
    if out="$(run_install "${home}" migrate --target codex --apply --marketplace-source "${native_source}")"; then ko "Codex ${failure} fails migration"; else ok "Codex ${failure} fails migration"; fi
    [[ "$(migrate_snapshot "${home}/.codex")" == "${legacy_before}" && -L "${home}/.agents/plugins/ycc" && ! -e "${home}/.codex/skills" ]] && ok "Codex ${failure} retains all legacy artifacts" || ko "Codex ${failure} retains all legacy artifacts"
    rm -f "${home}/fail-command" "${home}/native-off"
done
agents_before="$(migrate_snapshot "${home}/.codex/agents")"

install_must_succeed "${home}" migrate --target codex --apply --marketplace-source "${native_source}"
[[ "$(migrate_snapshot "${home}/.codex/agents")" == "${agents_before}" ]] && ok "Codex preserves every custom and shipped agent" || ko "Codex preserves every custom and shipped agent"
[[ ! -L "${home}/.codex/plugins/ycc" && ! -L "${home}/.agents/plugins/ycc" && ! -e "${home}/.codex/plugins/cache/local-ycc-plugins/ycc" ]] && ok "Codex retires owned legacy links and exact cache" || ko "Codex retires owned legacy links and exact cache"
assert_contains "$(cat "${home}/.codex/config.toml")" "# my settings" "Codex retains TOML comments"
assert_contains "$(cat "${home}/.codex/config.toml")" "mine@other" "Codex retains foreign plugin tables"
assert_not_contains "$(cat "${home}/.codex/config.toml")" "ycc@local-ycc-plugins" "Codex retires only legacy enablement"
legacy_before="$(migrate_snapshot "${home}/.codex")"
# native-installed marker makes this listing return available=[] and both
# ids under installed, matching the real CLI's already-installed response.
[[ -f "${home}/native-installed" ]] && ok "Codex rerun fixture uses installed-only catalog listing" || ko "Codex rerun fixture uses installed-only catalog listing"
install_must_succeed "${home}" migrate --target codex --apply --marketplace-source "${native_source}"
[[ "$(migrate_snapshot "${home}/.codex")" == "${legacy_before}" ]] && ok "Codex repeated cleanup is byte-stable" || ko "Codex repeated cleanup is byte-stable"
# Standalone Codex skills retire only exact staged copies and preserved links.
home="$(new_home)"; migrate_codex_fixture "${home}"
migrate_fixture_must_succeed env HOME="${home}" YCC_MANAGED_CONFIG_STATE="${home}/.config/ycc/managed-config-state.json" \
    python3 "${REPO_ROOT}/scripts/install_slices.py" install --target codex --slice skills >/dev/null
printf '\nedited\n' >> "${home}/.codex/skills/git-workflow/SKILL.md"
mkdir -p "${home}/.codex/skills/mine"
printf 'mine\n' > "${home}/.codex/skills/mine/SKILL.md"
skills_before="$(migrate_snapshot "${home}/.codex/skills")"
install_must_succeed "${home}" migrate --target codex --marketplace-source "${native_source}"
assert_contains "${INSTALL_OUT}" "would remove" "Codex preview forecasts exact skills retirement"
[[ "$(migrate_snapshot "${home}/.codex/skills")" == "${skills_before}" ]] && ok "Codex preview leaves standalone skills unchanged" || ko "Codex preview leaves standalone skills unchanged"
install_must_succeed "${home}" migrate --target codex --apply --marketplace-source "${native_source}"
assert_contains "$(cat "${home}/.codex/skills/git-workflow/SKILL.md")" "edited" "Codex retains edited standalone skill"
[[ -d "${home}/.codex/skills/mine" && -d "${home}/.codex/skills/_shared" ]] && ok "Codex retains foreign skill and _shared while entries remain" || ko "Codex retains foreign skill and _shared while entries remain"
[[ ! -e "${home}/.codex/skills/init" ]] && ok "Codex retires exact standalone skill copy" || ko "Codex retires exact standalone skill copy"

# An edited catalog entry keeps its referenced local source link.
home="$(new_home)"; migrate_codex_fixture "${home}"
migrate_fixture_must_succeed python3 - "${home}/.agents/plugins/marketplace.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['plugins'][0]['policy']['installation'] = 'ENABLED'
p.write_text(json.dumps(data, indent=2) + '\n')
PY
install_must_succeed "${home}" migrate --target codex --apply --marketplace-source "${native_source}"
[[ -L "${home}/.agents/plugins/ycc" && "$(readlink "${home}/.agents/plugins/ycc")" == "${REPO_REAL}/.codex-plugin/ycc" ]] && ok "Codex retained catalog keeps its referenced local link" || ko "Codex retained catalog keeps its referenced local link"
# An exact pre-rename repo-mode catalog entry retires despite the repository rename.
home="$(new_home)"; migrate_codex_fixture "${home}"
migrate_fixture_must_succeed python3 - "${home}/.agents/plugins/marketplace.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['plugins'][0]['source'] = {
    'source': 'git-subdir',
    'url': 'https://github.com/yandy-r/claude-plugins.git',
    'path': './.codex-plugin/ycc',
    'ref': 'main',
}
p.write_text(json.dumps(data, indent=2) + '\n')
PY
install_must_succeed "${home}" migrate --target codex --apply --marketplace-source "${native_source}"
assert_not_contains "$(cat "${home}/.agents/plugins/marketplace.json")" 'yandy-r/claude-plugins' "Codex retires exact pre-rename repo catalog entry"

# Changing any field makes the pre-rename repo-mode entry foreign and preserves it.
home="$(new_home)"; migrate_codex_fixture "${home}"
migrate_fixture_must_succeed python3 - "${home}/.agents/plugins/marketplace.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['plugins'][0]['source'] = {
    'source': 'git-subdir',
    'url': 'https://github.com/yandy-r/claude-plugins.git',
    'path': './.codex-plugin/ycc',
    'ref': 'v1.0.0',
}
p.write_text(json.dumps(data, indent=2) + '\n')
PY
install_must_succeed "${home}" migrate --target codex --apply --marketplace-source "${native_source}"
assert_contains "$(cat "${home}/.agents/plugins/marketplace.json")" '"ref": "v1.0.0"' "Codex keeps edited pre-rename repo catalog entry"

# Omitting an installer-written field also makes the pre-rename entry user-owned.
home="$(new_home)"; migrate_codex_fixture "${home}"
migrate_fixture_must_succeed python3 - "${home}/.agents/plugins/marketplace.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); data = json.loads(p.read_text())
data['plugins'][0]['source'] = {
    'source': 'git-subdir',
    'url': 'https://github.com/yandy-r/claude-plugins.git',
    'path': './.codex-plugin/ycc',
    'ref': 'main',
}
del data['plugins'][0]['category']
p.write_text(json.dumps(data, indent=2) + '\n')
PY
install_must_succeed "${home}" migrate --target codex --apply --marketplace-source "${native_source}"
assert_contains "$(cat "${home}/.agents/plugins/marketplace.json")" 'yandy-r/claude-plugins' "Codex keeps pre-rename repo catalog entry missing an installer field"

STUB_BIN="${old_stub_bin}"
unset MIGRATE_NATIVE_SOURCE

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
