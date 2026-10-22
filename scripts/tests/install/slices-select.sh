#!/usr/bin/env bash
# install.sh tests — --skills / --agents / --commands selection of the
# standalone skills, agents and commands slices on every target: narrowing
# (never pruning), helpers ride along, 'base' stays whole, preflight errors,
# --skills-home agents, paired-skill warnings, remove, --with-deps.
#
# Runs alone (bash scripts/tests/install/slices-select.sh) or from scripts/test-install-sync.sh.
# shellcheck source=scripts/tests/install/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# entries <dir> — the dir's top-level entry names, sorted, space-separated.
entries() {
    find "$1" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null | LC_ALL=C sort | tr '\n' ' ' | sed 's/ $//'
}

# assert_entries <dir> <expected> <name>
assert_entries() {
    local got
    got="$(entries "$1")"
    if [[ "${got}" == "$2" ]]; then ok "$3"; else ko "$3" "got: ${got:-<none>}"; fi
}

# reject <name> <home> <install args...> — an expected rejection: the
# installer must exit nonzero. Leaves its output in REJECT_OUT.
REJECT_OUT=""
reject() {
    local name="$1" rc=0
    shift
    REJECT_OUT="$(run_install "$@")" || rc=$?
    if [[ ${rc} -ne 0 ]]; then ok "${name} (exit ${rc})"; else ko "${name} (exit 0)" "${REJECT_OUT}"; fi
}

echo "== install.sh list skills / agents =="

home="$(new_home)"
install_must_succeed "${home}" list skills --target codex
assert_contains "${INSTALL_OUT}" "go-patterns" "list skills names codex skills"
assert_not_contains "${INSTALL_OUT}" "_shared" "list skills hides the _shared helper"
install_must_succeed "${home}" list skills --target opencode,agents
assert_not_contains "${INSTALL_OUT}" "ycc-shared" "list skills hides ycc-shared"
install_must_succeed "${home}" list agents --target codex
assert_contains "${INSTALL_OUT}" $'\nimplementor\n' "list agents prints stems"
assert_not_contains "${INSTALL_OUT}" ".toml" "list agents drops the codex .toml suffix"
install_must_succeed "${home}" list agents --target agents
if [[ -z "${INSTALL_OUT}" ]]; then ok "agents target lists no agents"; else ko "agents target lists no agents" "${INSTALL_OUT}"; fi

echo
echo "== install.sh --skills: every target =="

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills --skills go-patterns,rust-testing
assert_contains "${INSTALL_OUT}" "Skills: go-patterns, rust-testing" "claude reports the selected skills"
assert_entries "${home}/.claude/skills" "_shared go-patterns rust-testing" "claude installs only the selected skills + _shared"

home="$(new_home)"
install_must_succeed "${home}" sync --target cursor --intent skills --skills go-patterns --skills-home native
assert_entries "${home}/.cursor/skills" "_shared go-patterns" "cursor installs only the selected skill + _shared"

home="$(new_home)"
install_must_succeed "${home}" sync --target codex --intent skills --skills go-patterns --skills-home native
assert_entries "${home}/.codex/skills" "_shared go-patterns" "codex installs only the selected skill + _shared"

home="$(new_home)"
install_must_succeed "${home}" sync --target opencode --intent skills --skills go-patterns --skills-home native
assert_entries "${home}/.config/opencode/skills" "go-patterns" "opencode installs only the selected skill"
if [[ -d "${home}/.config/opencode/shared" ]]; then ok "opencode ships shared/ with a selected skill"; else ko "opencode ships shared/ with a selected skill"; fi

home="$(new_home)"
install_must_succeed "${home}" sync --target agents --intent skills --skills go-patterns
assert_entries "${home}/.agents/skills" "go-patterns" "agents target installs only the selected skill"
if [[ -d "${home}/.agents/ycc-shared" ]]; then ok "agents target ships ycc-shared with a selected skill"; else ko "agents target ships ycc-shared with a selected skill"; fi

echo
echo "== install.sh --agents: every target with an agents slice =="

home="$(new_home)"
install_must_succeed "${home}" sync --target claude,cursor,codex,opencode --intent agents --agents implementor,code-reviewer
assert_contains "${INSTALL_OUT}" "Agents: implementor, code-reviewer" "agents selection is reported"
assert_entries "${home}/.claude/agents" "code-reviewer.md implementor.md" "claude installs exactly the selected agents"
assert_entries "${home}/.cursor/agents" "code-reviewer.md implementor.md" "cursor installs exactly the selected agents"
assert_entries "${home}/.codex/agents" "code-reviewer.toml implementor.toml" "codex maps agent stems to .toml entries"
assert_entries "${home}/.config/opencode/agents" "code-reviewer.md implementor.md" "opencode installs exactly the selected agents"

home="$(new_home)"
install_must_succeed "${home}" sync --target all --intent agents --agents implementor
assert_contains "${INSTALL_OUT}" "agents target ran no steps" "--target all: the agents target reports a no-op"
if [[ ! -e "${home}/.agents/skills" ]]; then ok "--target all --agents writes nothing to ~/.agents"; else ko "--target all --agents writes nothing to ~/.agents"; fi
assert_entries "${home}/.claude/agents" "implementor.md" "--target all: claude installs exactly implementor"
assert_entries "${home}/.cursor/agents" "implementor.md" "--target all: cursor installs exactly implementor"
assert_entries "${home}/.codex/agents" "implementor.toml" "--target all: codex installs exactly implementor"
assert_entries "${home}/.config/opencode/agents" "implementor.md" "--target all: opencode installs exactly implementor"

echo
echo "== install.sh --skills / --agents: preflight =="

home="$(new_home)"
reject "unknown skill exits nonzero" "${home}" sync --target claude,codex --intent skills --skills go-patterns,no-such-skill --skills-home native
assert_contains "${REJECT_OUT}" "unknown skill 'no-such-skill'" "unknown skill rejected"
assert_contains "${REJECT_OUT}" "list them with: ycc list skills --target <targets>" "unknown skill points at ycc list skills"
if [[ ! -e "${home}/.claude/skills" && ! -e "${home}/.codex/skills" && ! -e "${home}/.config/ycc/installed-units.json" ]]; then
    ok "unknown skill fails before any target writes"
else
    ko "unknown skill fails before any target writes"
fi

home="$(new_home)"
reject "unknown agent exits nonzero" "${home}" sync --target codex --intent agents --agents implementor.toml
assert_contains "${REJECT_OUT}" "unknown agent 'implementor.toml'" "agents are selected by stem, not file name"

home="$(new_home)"
reject "--skills with base only exits nonzero" "${home}" sync --target claude --intent base --skills go-patterns
assert_contains "${REJECT_OUT}" "--skills needs the skills step (it narrows the standalone skills slice; use --intent skills or --only skills)" "--skills with base only is rejected"
reject "agents base + --skills exits nonzero" "${home}" sync --target agents --intent base --skills go-patterns
assert_contains "${REJECT_OUT}" "--skills needs the skills step" "agents base is never filtered: --skills needs its skills step"
reject "--agents on the agents target alone exits nonzero" "${home}" sync --target agents --intent agents --agents implementor
assert_contains "${REJECT_OUT}" "--agents needs the agents step" "--agents on the agents target alone is rejected"

home="$(new_home)"
install_must_succeed "${home}" sync --target agents --intent base,skills --skills go-patterns
assert_contains "${INSTALL_OUT}" "agents base installs every skill into ~/.agents/skills; --skills does not narrow this run" "agents base + skills warns that --skills does not narrow"
if [[ "$(entries "${home}/.agents/skills" | wc -w)" -gt 1 ]]; then ok "agents base still installs every skill under --skills"; else ko "agents base still installs every skill under --skills" "$(entries "${home}/.agents/skills")"; fi

echo
echo "== install.sh --skills: narrowing, re-sync, remove =="

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills --skills go-patterns
install_must_succeed "${home}" sync --target claude --intent skills --skills rust-testing
assert_entries "${home}/.claude/skills" "_shared go-patterns rust-testing" "a second selection keeps the earlier selected skill"
state="$(cat "${home}/.config/ycc/installed-units.json")"
assert_contains "${state}" '"go-patterns"' "state still records the earlier selected skill"
before="$(cksum < "${home}/.config/ycc/installed-units.json")"
install_must_succeed "${home}" sync --target claude --intent skills --skills rust-testing
if [[ "$(cksum < "${home}/.config/ycc/installed-units.json")" == "${before}" ]]; then ok "re-sync of the same selection leaves state unchanged"; else ko "re-sync of the same selection leaves state unchanged"; fi
assert_entries "${home}/.claude/skills" "_shared go-patterns rust-testing" "re-sync of the same selection changes nothing"

install_must_succeed "${home}" remove --target claude --intent skills --skills go-patterns
assert_entries "${home}/.claude/skills" "_shared rust-testing" "selective remove takes only the named skill, keeps _shared"
install_must_succeed "${home}" remove --target claude --intent skills --skills rust-testing
if [[ -z "$(entries "${home}/.claude/skills")" ]]; then ok "removing the last selected skill takes _shared too"; else ko "removing the last selected skill takes _shared too" "$(entries "${home}/.claude/skills")"; fi

home="$(new_home)"
install_must_succeed "${home}" sync --target codex,opencode --intent agents --agents implementor,code-reviewer
install_must_succeed "${home}" remove --target codex,opencode --intent agents --agents implementor
assert_entries "${home}/.codex/agents" "code-reviewer.toml" "codex selective agent remove takes only implementor"
assert_entries "${home}/.config/opencode/agents" "code-reviewer.md" "opencode selective agent remove takes only implementor"

home="$(new_home)"
install_must_succeed "${home}" sync --target cursor --intent agents --agents implementor,code-reviewer
install_must_succeed "${home}" remove --target cursor --intent agents --agents implementor
assert_entries "${home}/.cursor/agents" "code-reviewer.md" "cursor selective agent remove takes only implementor"

home="$(new_home)"
install_must_succeed "${home}" sync --target cursor --intent skills --skills go-patterns,rust-testing --skills-home native
install_must_succeed "${home}" remove --target cursor --intent skills --skills go-patterns --skills-home native
assert_entries "${home}/.cursor/skills" "_shared rust-testing" "cursor selective skill remove takes only the named skill, keeps _shared"

home="$(new_home)"
install_must_succeed "${home}" sync --target agents --intent skills --skills go-patterns,rust-testing
install_must_succeed "${home}" remove --target agents --intent skills --skills go-patterns
assert_entries "${home}/.agents/skills" "rust-testing" "agents target selective remove takes only the named skill"
if [[ -d "${home}/.agents/ycc-shared" ]]; then ok "agents target keeps ycc-shared while a ycc skill remains"; else ko "agents target keeps ycc-shared while a ycc skill remains"; fi
install_must_succeed "${home}" remove --target agents --intent skills --skills rust-testing
if [[ -z "$(entries "${home}/.agents/skills")" && ! -e "${home}/.agents/ycc-shared" ]]; then ok "agents target: removing the last selected skill takes ycc-shared too"; else ko "agents target: removing the last selected skill takes ycc-shared too" "$(entries "${home}/.agents/skills")"; fi

echo
echo "== install.sh --skills-home agents: selection follows the skills =="

home="$(new_home)"
install_must_succeed "${home}" sync --target codex,opencode --intent skills --skills go-patterns --skills-home agents
assert_entries "${home}/.agents/skills" "go-patterns" "consolidated skills install only the selection into ~/.agents/skills"
if [[ ! -e "${home}/.codex/skills" && ! -e "${home}/.config/opencode/skills" ]]; then ok "consolidated selection installs no native skills"; else ko "consolidated selection installs no native skills"; fi

echo
echo "== install.sh --agents: codex base stays whole =="

home="$(new_home)"
install_must_succeed "${home}" install --target codex --only base,agents --agents implementor --skills-home native
shipped="$(find "${REPO_ROOT}/.codex-plugin/agents" -maxdepth 1 -name '*.toml' | wc -l)"
got="$(find "${home}/.codex/agents" -maxdepth 1 -name '*.toml' | wc -l)"
if [[ "${got}" -eq "${shipped}" ]]; then ok "codex base still syncs every custom agent under --agents"; else ko "codex base still syncs every custom agent under --agents" "${got} of ${shipped}"; fi
assert_contains "${INSTALL_OUT}" "codex base syncs every custom agent into ~/.codex/agents; --agents does not narrow this run" "codex warns that base ignores --agents"

echo
echo "== install.sh --skills: cursor commands need their skills =="

home="$(new_home)"
reject "cursor commands + --skills without --commands exits nonzero" "${home}" sync --target cursor --intent skills,commands --skills go-patterns --skills-home native
assert_contains "${REJECT_OUT}" "--skills narrows a run that installs every Cursor command" "--skills with all cursor commands is rejected"
assert_contains "${REJECT_OUT}" "--skills go-patterns --commands go-patterns" "the error suggests selecting the commands too"
if [[ ! -e "${home}/.cursor/skills" && ! -e "${home}/.cursor/commands" && ! -e "${home}/.config/ycc/installed-units.json" ]]; then
    ok "cursor commands + --skills writes nothing"
else
    ko "cursor commands + --skills writes nothing"
fi
home="$(new_home)"
reject "cursor --commands outside --skills exits nonzero" "${home}" sync --target cursor --intent skills,commands --skills go-patterns --commands go-patterns,clean --skills-home native
assert_contains "${REJECT_OUT}" "--skills misses the selected commands clean" "a selected command without its skill is rejected"
assert_contains "${REJECT_OUT}" "--skills go-patterns,clean --commands go-patterns,clean" "the error suggests adding the skill"
if [[ -z "$(entries "${home}/.cursor")" && ! -e "${home}/.config/ycc/installed-units.json" ]]; then ok "cursor subset rejection writes nothing"; else ko "cursor subset rejection writes nothing"; fi
home="$(new_home)"
reject "--target all: cursor commands + --skills exits nonzero" "${home}" sync --target all --intent skills,commands --skills go-patterns --skills-home native
assert_contains "${REJECT_OUT}" "--skills narrows a run that installs every Cursor command" "--target all: cursor commands + --skills is rejected"
if [[ ! -e "${home}/.claude/skills" && ! -e "${home}/.cursor/skills" && ! -e "${home}/.codex/skills" \
    && ! -e "${home}/.config/opencode/skills" && ! -e "${home}/.agents/skills" && ! -e "${home}/.config/ycc/installed-units.json" ]]; then
    ok "--target all: the rejection precedes every target"
else
    ko "--target all: the rejection precedes every target"
fi

echo
echo "== install.sh --commands =="

home="$(new_home)"
install_must_succeed "${home}" list commands --target codex
if [[ -z "${INSTALL_OUT}" ]]; then ok "codex lists no commands"; else ko "codex lists no commands" "${INSTALL_OUT}"; fi
install_must_succeed "${home}" list commands --target opencode
assert_contains "${INSTALL_OUT}" $'\nclean\n' "list commands prints opencode command stems"
assert_not_contains "${INSTALL_OUT}" ".md" "list commands drops the .md suffix"
opencode_list="${INSTALL_OUT}"
install_must_succeed "${home}" list commands --target cursor
if [[ "${INSTALL_OUT}" == "${opencode_list}" ]]; then ok "cursor and opencode list the same commands"; else ko "cursor and opencode list the same commands"; fi
install_must_succeed "${home}" list commands --target claude
assert_contains "${INSTALL_OUT}" "go-patterns" "claude lists its skills as commands"

home="$(new_home)"
reject "--commands on codex alone exits nonzero" "${home}" sync --target codex --intent commands --commands clean
assert_contains "${REJECT_OUT}" "--commands needs the commands step" "codex has no commands step"
if [[ -z "$(entries "${home}/.codex")" ]]; then ok "codex --commands rejection writes nothing"; else ko "codex --commands rejection writes nothing" "$(entries "${home}/.codex")"; fi
reject "unknown command exits nonzero" "${home}" sync --target opencode --intent commands --commands clean,no-such-command
assert_contains "${REJECT_OUT}" "unknown command 'no-such-command'" "unknown command rejected"

home="$(new_home)"
install_must_succeed "${home}" sync --target claude,codex --intent commands --commands clean
assert_entries "${home}/.claude/skills" "_shared clean" "claude --commands narrows its skills slice"
if [[ -z "$(entries "${home}/.codex")" ]]; then ok "codex skips --commands"; else ko "codex skips --commands" "$(entries "${home}/.codex")"; fi

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills,commands --skills go-patterns --commands clean
assert_entries "${home}/.claude/skills" "_shared clean go-patterns" "claude --skills + --commands installs the union once"
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills,commands --skills go-patterns
assert_entries "${home}/.claude/skills" "_shared go-patterns" "claude commands without a selection does not widen --skills"

home="$(new_home)"
install_must_succeed "${home}" sync --target opencode --intent commands --commands clean,plan
assert_entries "${home}/.config/opencode/commands" "clean.md plan.md" "opencode --commands installs only the selected commands"
assert_contains "${INSTALL_OUT}" "opencode: command 'clean' needs skill 'clean', not installed" "opencode warns about the missing paired skill"
if [[ ! -e "${home}/.config/opencode/skills" ]]; then ok "the paired-skill warning installs nothing"; else ko "the paired-skill warning installs nothing"; fi
install_must_succeed "${home}" sync --target opencode --intent commands --commands go-patterns
assert_entries "${home}/.config/opencode/commands" "clean.md go-patterns.md plan.md" "a second --commands selection keeps the earlier ones"
install_must_succeed "${home}" remove --target opencode --intent commands --commands plan
assert_entries "${home}/.config/opencode/commands" "clean.md go-patterns.md" "opencode selective command remove takes only plan"

home="$(new_home)"
install_must_succeed "${home}" sync --target opencode --intent skills,commands --skills clean --commands clean --skills-home native
assert_not_contains "${INSTALL_OUT}" "needs skill" "a skill the same run installs counts as installed"
home="$(new_home)"
install_must_succeed "${home}" sync --target opencode --intent skills --skills clean --skills-home native
install_must_succeed "${home}" sync --target opencode --intent commands --commands clean
assert_not_contains "${INSTALL_OUT}" "needs skill" "a standalone skill counts as installed"

home="$(new_home)"
install_must_succeed "${home}" sync --target cursor --intent skills,commands --skills clean,go-patterns --commands clean --skills-home native
assert_entries "${home}/.cursor/commands" "clean.md" "cursor --commands installs only the selected command"
assert_entries "${home}/.cursor/skills" "_shared clean go-patterns" "cursor installs the selected skills"
install_must_succeed "${home}" sync --target cursor --intent commands --commands go-patterns
assert_entries "${home}/.cursor/commands" "clean.md go-patterns.md" "cursor merges a second command selection"
reject "cursor command without its skill fails closed" "${home}" sync --target cursor --intent commands --commands plan
assert_contains "${REJECT_OUT}" "Cursor commands require installed skills" "cursor refuses a command whose skill is missing"
assert_entries "${home}/.cursor/commands" "clean.md go-patterns.md" "the fail-closed preflight writes nothing"
install_must_succeed "${home}" remove --target cursor --intent commands --commands clean
assert_entries "${home}/.cursor/commands" "go-patterns.md" "cursor selective command remove takes only clean"

home="$(new_home)"
mkdir -p "${home}/.claude/commands" "${home}/.config/ycc"
echo wrapper > "${home}/.claude/commands/clean.md"
echo wrapper > "${home}/.claude/commands/plan.md"
printf '{"version": 1, "units": {"%s/.claude/commands": ["clean.md", "plan.md"]}}\n' "${home}" > "${home}/.config/ycc/installed-units.json"
install_must_succeed "${home}" remove --target claude --intent commands --commands clean
assert_entries "${home}/.claude/commands" "plan.md" "claude --commands remove retires only the named legacy wrapper"

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills --skills clean,plan
mkdir -p "${home}/.claude/commands"
echo wrapper > "${home}/.claude/commands/clean.md"
python3 - "${home}" <<'PY'
import json, sys
home = sys.argv[1]
path = f"{home}/.config/ycc/installed-units.json"
state = json.load(open(path))
state["units"][f"{home}/.claude/commands"] = ["clean.md"]
json.dump(state, open(path, "w"))
PY
install_must_succeed "${home}" remove --target claude --intent skills,commands --commands clean
assert_entries "${home}/.claude/skills" "_shared clean plan" "claude --commands remove never removes skills"
assert_contains "${INSTALL_OUT}" "pass --skills to remove skills" "claude --commands remove explains the skipped skills slice"
if [[ ! -e "${home}/.claude/commands/clean.md" ]]; then ok "claude --commands remove retires the clean.md wrapper"; else ko "claude --commands remove retires the clean.md wrapper"; fi
install_must_succeed "${home}" remove --target claude --intent skills,commands --skills plan --commands clean
assert_entries "${home}/.claude/skills" "_shared clean" "claude --skills + --commands remove takes only the --skills selection"

echo
echo "== install.sh --skills: dependency warning =="

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills --skills clean
assert_contains "${INSTALL_OUT}" "is referenced by clean but not installed" "a missing ycc: dependency is reported"
assert_contains "${INSTALL_OUT}" "ycc sync --target claude --intent" "the warning names the command that adds it"
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills --skills go-patterns
assert_not_contains "${INSTALL_OUT}" "is referenced by" "a self-contained skill warns about nothing"
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills,agents --skills plan --agents planner
assert_not_contains "${INSTALL_OUT}" "'planner'" "an agent selected in the same run counts as installed"
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills,agents --skills plan
assert_not_contains "${INSTALL_OUT}" "'planner'" "the same run's full agents slice counts as installed"
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent agents,commands --agents review-fixer
assert_not_contains "${INSTALL_OUT}" "is dispatched only by" "claude commands (the skills alias): no dispatched-only warning"
assert_not_contains "${INSTALL_OUT}" "but not installed" "claude commands (the skills alias) count as the same run's full skills slice"
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent agents,commands --agents review-fixer --commands clean
assert_contains "${INSTALL_OUT}" "'review-fixer' is dispatched only by" "claude --commands narrows the same run's skills for agent warnings"

echo
echo "== install.sh --with-deps =="

home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills,agents --skills code-review --agents implementor --with-deps
if [[ -d "${home}/.claude/skills/code-review" && -d "${home}/.claude/skills/review-fix" ]]; then ok "--with-deps installs the selected skill and its skill dependencies"; else ko "--with-deps installs the selected skill and its skill dependencies" "$(entries "${home}/.claude/skills")"; fi
if [[ -f "${home}/.claude/agents/code-reviewer.md" && -f "${home}/.claude/agents/implementor.md" ]]; then ok "--with-deps installs the selected agent and the referenced agents"; else ko "--with-deps installs the selected agent and the referenced agents" "$(entries "${home}/.claude/agents")"; fi
assert_contains "${INSTALL_OUT}" "claude: --with-deps adds" "--with-deps reports what it adds"
# Only the claude deprecation notice may warn; no dependency warning remains.
warnings="$(grep -F '[!!]' <<< "${INSTALL_OUT}" | grep -vF 'deprecated: claude native packages' || true)"
if [[ -z "${warnings}" ]]; then ok "--with-deps leaves no dependency warning"; else ko "--with-deps leaves no dependency warning" "${warnings}"; fi
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills,agents --skills code-review --with-deps
assert_not_contains "${INSTALL_OUT}" "is referenced by" "--with-deps with the whole agents slice warns about nothing"
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent skills,commands --skills go-patterns --commands code-review --with-deps
assert_contains "${INSTALL_OUT}" "claude: --with-deps adds skills:" "--with-deps follows claude --commands (its skills)"
assert_not_contains "${INSTALL_OUT}" "skill 'review-fix' is referenced by" "--with-deps resolves the --commands skill's skill references"
# Commands step only: the added skills still install (they go to --commands).
home="$(new_home)"
install_must_succeed "${home}" sync --target claude --intent commands --commands code-review --with-deps
if [[ -d "${home}/.claude/skills/review-fix" ]]; then ok "--with-deps installs claude --commands dependencies without the skills step"; else ko "--with-deps installs claude --commands dependencies without the skills step" "$(entries "${home}/.claude/skills")"; fi
# Consolidated skills (~/.agents/skills) are not cursor's to install: they keep warning.
home="$(new_home)"
install_must_succeed "${home}" sync --target cursor --skills-home agents --intent skills,agents --skills go-patterns --agents review-fixer --with-deps
assert_not_contains "${INSTALL_OUT}" "cursor: --with-deps adds skills" "--with-deps does not claim consolidated skills"
assert_contains "${INSTALL_OUT}" "is dispatched only by" "consolidated skill dependencies still warn"
home="$(new_home)"
reject "remove --with-deps exits nonzero" "${home}" remove --target claude --intent skills --skills code-review --with-deps
assert_contains "${REJECT_OUT}" "--with-deps is only valid with install or sync" "remove --with-deps is rejected"
reject "--with-deps without a selection exits nonzero" "${home}" sync --target claude --intent skills --with-deps
assert_contains "${REJECT_OUT}" "--with-deps needs --skills or --agents" "--with-deps without --skills / --agents is rejected"

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then install_tests_finish; fi
