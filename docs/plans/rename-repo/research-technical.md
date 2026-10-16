# Rename Repo: Technical Research

## Executive Summary

The implementation is a fixed-scope source transformer, not a repository rename operation. A strict Bash wrapper delegates to a standard-library Python engine; all path and content preflight precedes either full dry-run output or per-file atomic replacement. Only anchored owner/repo references are rewritten: the proposed README bare-name rewrite was removed. Parent integration reports 24 replacements across the 12 managed files, with no protected strings appearing in the real preview diff.

## Architecture Approach

```text
rename-repo.sh → rename_repo.py → validate arguments and every managed path
                               → compute all byte-preserving transformations
                               → full diff (dry-run) OR atomic per-file replacements
```

The wrapper is strict Bash and forwards quoted `"$@"` to the standard-library Python engine. `main(argv: list[str] | None = None) -> int` is the Python API. Resolve the physical repository root from the scripts' own location and Python `__file__`, never the caller's directory, `PROJECT_ROOT`, Git environment, or a user-provided root. Tests copy both scripts into disposable fixture roots rather than adding a production override.

CLI: `scripts/rename-repo.sh --from owner/repo --to owner/repo [--dry-run]`. Both slugs are required; no `--apply` flag. Without `--dry-run`, apply is selected. Help states that the utility does not rename hosts, update remotes, or sync/regenerate targets. Invalid/unknown/duplicate arguments fail before writes; no-op succeeds.

## Fixed source allowlist

| Path                                       | Reason                                   |
| ------------------------------------------ | ---------------------------------------- |
| `README.md`                                | Claude marketplace-add instruction       |
| `.claude-plugin/marketplace.json`          | Main marketplace repository metadata     |
| `.github/ISSUE_TEMPLATE/config.yml`        | Discussions destination                  |
| `docs/install/codex.md`                    | Current repo-mode installation guide     |
| `install.sh`                               | Repo-mode help/examples                  |
| `scripts/codex_marketplace.py`             | Runtime `git-subdir` URL                 |
| `scripts/generate_codex_plugin.py`         | Canonical generated Codex URL source     |
| `scripts/test_codex_marketplace.py`        | Coupled URL fixtures/expectations        |
| `scripts/lib/install/targets/claude.sh`    | Claude marketplace source/messages       |
| `scripts/lib/install/targets/codex.sh`     | Codex repo-mode references/messages      |
| `ycc/mods/.claude-plugin/marketplace.json` | Mods repository URL/prose, not identity  |
| `ycc/settings/settings.json`               | Marketplace source repo, not plugin keys |

Evidence: business/inventory researchers inspected these current anchors, including `README.md:118`, `scripts/codex_marketplace.py:40`, `scripts/generate_codex_plugin.py:31`, and `ycc/settings/settings.json:58-65`. Historical documents, local trust settings, generated bundles, and all worktrees are excluded.

## Transformation semantics

- Validate canonical owner/repository shape; reject traversal, additional segments, whitespace/control characters, schemes, and shell syntax.
- Support exact standalone marketplace slugs, HTTPS URLs, SCP-style SSH and `ssh://` URLs. Preserve `.git`, URL path, query, fragment, and supported ref suffix delimiters.
- Match the complete source owner and repository. A word boundary alone is wrong because `-official` can satisfy `\b`; `.fork`, longer repos, and partial owners also must not match.
- Do not treat an arbitrary slash-prefixed path as a repository URL. `/home/.../yandy-r/claude-plugins` and worktree paths stay untouched even in an allowlisted file.
- Protect `ycc:`, `ycc@ycc`, `ycc-mods`, `CLAUDE_PLUGIN_ROOT`, `claude-plugins-official`; unrelated marketplace names remain unchanged.
- Escape any source used in a regex and use a literal/callback replacement. Never interpolate arguments into executable shell/Python source.

### Data Model Implications

No persistent database, API schema, or config serialization is introduced. The transformation model is the fixed tuple of 12 repository-relative source paths plus each file's original bytes, proposed bytes, and permission mode. Repository identity is the exact owner/repo pair; marketplace/plugin identity remains separate and unchanged. Reading and writing raw bytes avoids JSON, YAML, shell, or Markdown reserialization and preserves unrelated content and newline conventions.

## File safety and state

Before any write, check every allowlist parent and leaf using non-following metadata. Parents must be directories; leaves must exist and be regular files. Reject symlink components, broken links, directories, FIFOs, sockets, and devices. Compute transformations for all files before apply; dry-run performs the same preflight.

Read/write bytes without newline normalization or reserialization. Unchanged bytes, CRLF/mixed newlines, missing final newlines, and permission/executable bits must survive. Replace changed files with same-directory temporary files and atomic `os.replace`; clean temporary files on failure. This avoids in-place hardlink alias mutation. It is per-file atomicity, not a rollback-capable multi-file transaction.

## Reusable patterns

- Wrapper/module: `scripts/generate-claude-packages.sh:1-7`.
- Preflight: `scripts/generate_claude_packages.py:141-165,203-213`.
- Same-directory replacement and modes: `scripts/merge_managed_config.py:362-389`.
- Fixture tests: `scripts/test_codex_marketplace.py:10-33` and symlink cases in `scripts/test_generate_codex_plugin.py:213-240`.
- Validator integration: `scripts/validate.sh` inventory target and `scripts/lib/validate-scope.sh` single-target mappings.

## Resolved exploratory conflicts

The settled contract overrides proposals for default dry-run, `--apply`, `PROJECT_ROOT`, Perl, permissive substring replacement, or failure on zero matches. Legacy-fixture semantics in `test_codex_marketplace.py` are not special-cased: approved repository references in that allowlisted source follow the same boundary rules. No generated file is directly edited or implicitly regenerated.

## Verification status

Parent integration reports 20 fixture tests and 50 scope tests passed; lint and validation for inventory, scope, and practices passed. The real dry-run shows 24 anchored replacements in 12 files and no protected strings in its diff. These results are supplied by the parent, not rerun by this documentation worker; apply against the preparation checkout is not claimed.
