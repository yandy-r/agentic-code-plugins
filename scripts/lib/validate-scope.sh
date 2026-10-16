# shellcheck shell=bash
# validate-scope.sh — the validate.sh target list plus the changed-path scoping
# behind `validate.sh --changed`. Sourced by scripts/validate.sh and
# scripts/test-validate-scope.sh (never run directly).
#
# Scoping is deliberately conservative: a path maps to a narrow target set only
# when it is listed here, and every unlisted path selects every target. CI runs
# the unscoped validate.sh, so a rule that is too narrow is caught there.

# shellcheck disable=SC2034  # read by validate.sh and the scope tests.
VALIDATE_TARGETS=(inventory cursor codex opencode agents claude json config packages release mods practices scope)

# validate_scope_targets_for_path <path> — print the targets a changed
# repo-relative path affects: a space-separated list, `all`, or nothing.
validate_scope_targets_for_path() {
    case "$1" in
        # Generated artifacts and docs owned by a single target.
        docs/inventory.json | README.md) echo "inventory" ;;
        .cursor-plugin/*) echo "cursor" ;;
        .codex-plugin/*) echo "codex" ;;
        .opencode-plugin/*) echo "opencode" ;;
        .agents-plugin/*) echo "agents" ;;
        packages/claude/*) echo "claude" ;;

        # The package manifest and its model feed both the packages validators
        # and the Claude generator, so they must match before the catch-all
        # settings rule.
        ycc/settings/packages.json | ycc/settings/packages.schema.json) echo "claude packages" ;;
        scripts/package_model.py | scripts/test_package_model.py) echo "claude packages" ;;
        scripts/build_package_graph.py | scripts/package_graph_extract.py | scripts/test_package_graph.py) echo "packages" ;;

        # Claude package generator, validator and tests.
        scripts/generate_claude_packages.py | scripts/generate-claude-packages.sh | scripts/validate-claude-packages.sh | scripts/test_generate_claude_packages.py | scripts/test-claude-native-packages.sh | scripts/claude_native_smoke.py) echo "claude" ;;

        # Docs and repo meta that no validator reads.
        docs/* | CONTRIBUTING.md | RELEASING.md | LICENSE | .github/*) ;;
        .gitignore | .gitmessage | .graphifyignore | commitlint.config.cjs) ;;
        .markdownlint.json | .markdownlintignore | mise.toml) ;;
        package-lock.json | pnpm-lock.yaml | pnpm-workspace.yaml) ;;


        # Plugin source. Settings and the plugin manifest feed the generators,
        # the install tests and the manifest checks, so they select everything.
        ycc/settings/* | ycc/.claude-plugin/*) echo "all" ;;
        ycc/mods/*) echo "config mods" ;;
	ycc/*) echo "inventory cursor codex opencode agents packages release practices" ;;

        # install.sh and its tests. The install-coverage validators in the
        # agents and opencode targets parse the per-target install libs.
        scripts/lib/install/*) echo "opencode agents config" ;;
        install.sh | scripts/tests/install/* | scripts/test-install-sync.sh | scripts/completions/*) echo "config" ;;
        scripts/install_slices.py | scripts/test_install_slices_legacy.py) echo "config" ;;
        scripts/merge_managed_config.py | scripts/managed_config_*.py) echo "config" ;;
        scripts/test_merge_managed_config.py | scripts/test_managed_config_entries.py) echo "config" ;;
        scripts/codex_marketplace.py | scripts/test_codex_marketplace.py) echo "config" ;;
        scripts/validate-model-settings.py) echo "config" ;;

        # Single-target tests and validators.
        scripts/test-release-*.sh) echo "release" ;;
        scripts/test-plan-workflow-validators.sh) echo "inventory" ;;
        scripts/validate-mods.sh) echo "mods" ;;
        scripts/validate-practices.sh | scripts/validate_practices.py) echo "practices" ;;
        .claude/rules/*) echo "practices" ;;
        scripts/practices_parse.py | scripts/practices_rules.py | scripts/practices-baseline.json) echo "practices" ;;
        scripts/test_validate_practices.py) echo "practices" ;;
        scripts/test-validate-scope.sh) echo "scope" ;;

        # Generators, shared libs, validate.sh itself, anything unrecognised.
        *) echo "all" ;;
    esac
}

# validate_scope_select — read changed paths on stdin (one per line) and print
# the affected targets, one per line, in VALIDATE_TARGETS order.
validate_scope_select() {
    local path target affected
    local selected=" "
    while IFS= read -r path; do
        [[ -n "${path}" ]] || continue
        affected="$(validate_scope_targets_for_path "${path}")"
        if [[ "${affected}" == "all" ]]; then
            printf '%s\n' "${VALIDATE_TARGETS[@]}"
            return 0
        fi
        selected+="${affected} "
    done
    for target in "${VALIDATE_TARGETS[@]}"; do
        [[ "${selected}" == *" ${target} "* ]] && printf '%s\n' "${target}"
    done
    return 0
}

# validate_scope_base <repo> — print the commit the current branch was last in
# sync with its push destination (falling back to its upstream, then the
# remote default branch). Returns 1 when none of them resolves.
validate_scope_base() {
    local repo="$1" ref base
    for ref in '@{push}' '@{upstream}' origin/HEAD origin/main; do
        if base="$(git -C "${repo}" merge-base HEAD "${ref}" 2>/dev/null)" && [[ -n "${base}" ]]; then
            printf '%s\n' "${base}"
            return 0
        fi
    done
    return 1
}

# validate_scope_changed_paths <repo> <base> — print the tracked paths that
# differ between <base> and the working tree (validators read the working
# tree, so uncommitted edits count). Renames list both the old and new path.
validate_scope_changed_paths() {
    git -C "$1" diff --name-only --no-renames "$2" --
}
