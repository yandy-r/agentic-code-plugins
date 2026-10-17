# shellcheck shell=bash
# validate-scope.sh — the validate.sh target list plus the changed-path scoping
# behind `validate.sh --changed`. Sourced by scripts/validate.sh and
# scripts/test-validate-scope.sh (never run directly).
#
# Scoping is deliberately conservative: a path maps to a narrow target set only
# when it is listed here, and every unlisted path selects every target. CI runs
# the unscoped validate.sh, so a rule that is too narrow is caught there.

# shellcheck disable=SC2034  # read by validate.sh and the scope tests.
VALIDATE_TARGETS=(inventory cursor codex opencode agents claude claude-native cursor-native codex-native json config packages release mods practices scope)

# validate_scope_targets_for_path <path> — print the targets a changed
# repo-relative path affects: a space-separated list, `all`, or nothing.
validate_scope_targets_for_path() {
    case "$1" in
        # Generated artifacts and docs owned by a single target.
        docs/inventory.json | README.md) echo "inventory" ;;
        .cursor-plugin/*) echo "cursor cursor-native packages" ;;
        .codex-plugin/*) echo "codex codex-native packages" ;;
        .opencode-plugin/*) echo "opencode" ;;
        .agents-plugin/* | .agents/plugins/marketplace.json) echo "agents codex-native packages" ;;
        .claude-plugin/marketplace.json) echo "claude-native json packages" ;;
        packages/cursor/installer-fallback/*) echo "cursor cursor-native config" ;;
        packages/cursor/*) echo "cursor cursor-native packages" ;;
        packages/claude/*) echo "claude claude-native packages" ;;
        packages/opencode/*) echo "opencode release packages" ;;

        # The package manifest and its model feed the packages validators and
        # per-runtime package generators, so they must match before the
        # catch-all settings rule.
        ycc/settings/packages.json | ycc/settings/packages.schema.json) echo "cursor codex opencode claude claude-native cursor-native codex-native packages" ;;
        scripts/package_model.py | scripts/test_package_model.py) echo "cursor codex opencode claude claude-native cursor-native codex-native packages" ;;
        scripts/build_package_graph.py | scripts/package_graph_extract.py | scripts/test_package_graph.py) echo "packages" ;;
        scripts/validate_packages.py | scripts/test_validate_packages.py) echo "packages" ;;
        scripts/validate_install_doc_ids.py | scripts/test_validate_install_doc_ids.py) echo "packages" ;;
        # Claude package generator, validator and tests.
        scripts/generate_claude_packages.py | scripts/generate-claude-packages.sh | scripts/validate-claude-packages.sh | scripts/validate_claude_native.py | scripts/test_validate_claude_native.py | scripts/test_generate_claude_packages.py | scripts/test-claude-native-packages.sh | scripts/claude_native_smoke.py) echo "claude claude-native" ;;

        # Cursor native package generator, validator and tests. The component
        # generators (skills/agents/rules) stay on the catch-all: install tests
        # and other targets import or regenerate them.
        scripts/generate_cursor_packages.py | scripts/cursor_native_resources.py | scripts/generate-cursor-packages.sh | scripts/validate-cursor-packages.sh | scripts/validate_cursor_native.py | scripts/test_validate_cursor_native.py | scripts/test_generate_cursor_packages.py | scripts/vendor/cursor/*) echo "cursor cursor-native config" ;;
        scripts/cursor_live_smoke.py | scripts/test_cursor_live_smoke.py) echo "cursor-native" ;;

        # Install docs contain model-validated public package identifiers.
        docs/install/*) echo "packages" ;;
        # Experimental OpenCode npm package source and boundary tests.
        scripts/generate_opencode_package.py | scripts/generate-opencode-package.sh | scripts/opencode_package* | scripts/test_generate_opencode_package.py | scripts/test-opencode-npm-package.sh | scripts/opencode_npm_release.py | scripts/test_opencode_npm_release.py) echo "opencode release" ;;

        # Docs and repo meta that no validator reads.
        docs/* | CONTRIBUTING.md | RELEASING.md | LICENSE | .github/*) ;;
        .gitignore | .gitmessage | .graphifyignore | commitlint.config.cjs) ;;
        .markdownlint.json | .markdownlintignore | mise.toml) ;;
        package-lock.json | pnpm-lock.yaml | pnpm-workspace.yaml) ;;


        # Plugin source. Settings and the plugin manifest feed the generators,
        # the install tests and the manifest checks, so they select everything.
        ycc/settings/* | ycc/.claude-plugin/*) echo "all" ;;
        ycc/mods/*) echo "config mods" ;;
        ycc/*) echo "inventory cursor codex opencode agents claude-native cursor-native codex-native packages release practices" ;;

        # install.sh and its tests. The install-coverage validators in the
        # agents and opencode targets parse the per-target install libs.
        scripts/lib/install/*) echo "opencode agents config" ;;
        install.sh | scripts/tests/install/* | scripts/test-install-sync.sh | scripts/completions/*) echo "config" ;;
        scripts/install_slices.py | scripts/test_install_slices_legacy.py) echo "config" ;;
        scripts/install_migrate.py) echo "config" ;;
        scripts/merge_managed_config.py | scripts/managed_config_*.py) echo "config" ;;
        scripts/test_merge_managed_config.py | scripts/test_managed_config_entries.py) echo "config" ;;
        scripts/codex_marketplace.py | scripts/test_codex_marketplace.py) echo "config codex-native" ;;
        scripts/generate_codex_plugin.py | scripts/validate-codex-plugin.sh | scripts/validate_codex_native.py | scripts/test_validate_codex_native.py | scripts/test_generate_codex_plugin.py) echo "codex codex-native config" ;;

        # Single-target tests and validators.
        scripts/test-release-*.sh) echo "release" ;;
        scripts/test-plan-workflow-validators.sh) echo "inventory" ;;
        scripts/test-helper-root-discovery.sh) echo "inventory" ;;
        scripts/rename-repo.sh | scripts/rename_repo.py | scripts/test-rename-repo.sh | scripts/test_rename_repo.py) echo "inventory" ;;
        scripts/validate-mods.sh) echo "mods" ;;
        scripts/validate-practices.sh | scripts/validate_practices.py) echo "practices" ;;
        .claude/rules/*) echo "practices" ;;
        scripts/practices_parse.py | scripts/practices_rules.py | scripts/practices-baseline.json) echo "practices" ;;
        scripts/test_validate_practices.py | scripts/test_standalone_agent_references.py) echo "practices" ;;
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
