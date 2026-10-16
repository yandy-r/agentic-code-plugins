# Rename Repo: Security Research

## Executive Summary

This is a fixed-file local content writer in a trusted maintainer checkout, not a repository traversal, remote administration tool, or sandbox for hostile concurrent filesystem mutation. Security research inspected generator path guards (`scripts/generate_claude_packages.py:141-165,203-213`), atomic config replacement (`scripts/merge_managed_config.py:362-389`), and symlink regression patterns (`scripts/test_generate_codex_plugin.py:213-240`). Findings below are design risks and required mitigations, not discovered exploitable defects in an implemented rename tool.

## Findings by Severity

The critical, warning, and advisory categories below describe the required containment guarantees and residual limitations. The real preview reported by parent integration has 24 anchored replacements across 12 files, with no protected strings in the diff; the README bare-name rewrite was removed. This narrows the active writer to anchored owner/repo references without claiming a hosting rename or hostile-concurrency guarantee.

### Critical — hard stops

| Risk                                                                              | Required mitigation                                                                                                                                                                  |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Writing outside the intended checkout through an ambient root override or symlink | Derive the physical root from the copied scripts themselves; reject every symlink path component, including leaf/internal/broken links. Do not accept `PROJECT_ROOT` or a root flag. |
| Broad replacement corrupts identities or local state                              | Fixed 12-file allowlist plus exact owner/repository and context boundaries; protect local paths even within managed files.                                                           |
| Partial writes caused by a known invalid later file                               | Complete argument, path, readability, and transformation preflight for all managed files before writing any file.                                                                    |

### Warnings — must address

| Risk                                             | Mitigation                                                                                                                             |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Missing/nonregular leaf hangs or corrupts state  | Fail on missing files, directory leaves, FIFO/socket/device leaves, and non-directory parents.                                         |
| Argument injection / regex replacement semantics | Quoted `"$@"`, strict slug parser, escaped matching, literal replacement; no `eval`, interpolated source, or shell-built substitution. |
| Newline/mode loss                                | Preserve exact unrelated bytes, newline forms, final-newline state, and permission/executable bits.                                    |
| In-place hardlink alias mutation                 | Same-directory temporary file plus atomic replacement, never truncate/write the original inode.                                        |
| Hidden write during preview                      | Share preflight/transformation with apply; render the full diff without temporary or destination writes in dry-run.                    |
| Unallowlisted files touched incidentally         | No recursive discovery, network commands, Git mutation, sync, generators, or execution of transformed content.                         |

### Advisories and limitations

Path checks followed by ordinary pathname opens can have a check/use race. Do not call this race-proof; concurrent hostile checkout mutation is outside this utility's scope. Recheck relevant file state before replacement where appropriate. Same-directory `os.replace` provides per-file atomicity, not a cross-file transaction or guaranteed rollback after an arbitrary mid-apply I/O failure. Temporary files must be cleaned on errors.

## Dependency Security

The runtime uses Bash and Python's standard library only; no new package, SDK, credential, or network endpoint is required. Pass arguments as quoted data and never execute transformed content or invoke sync/remotes/publishing. Existing repository lint and validation supply the dependency/tooling gates; parent integration reports lint plus inventory, scope, and practices validation passed. These results do not constitute an external-service security audit.

## Adversarial fixture matrix

Run both modes where applicable, only in disposable roots containing copies of wrapper and engine and all 12 files:

- Leaf and parent symlinks: relative/absolute, internal/external, and broken; verify external targets and earlier managed files are unchanged.
- Missing file and nonregular leaf late in allowlist; verify preflight no-write behavior.
- Exact slug, HTTPS, `.git`, SCP SSH, `ssh://`, URL path/query/fragment/ref suffixes.
- `claude-plugins-official`, `.fork`, longer repository names, partial owners, unrelated marketplace references, and the full protected identity set.
- `/home/.../yandy-r/claude-plugins` plus worktree paths inside managed files; matching content in generated/historical/unallowlisted files.
- CRLF/mixed newlines, no final newline, executable mode, and hardlink aliases.
- Invocation from an unrelated working directory with misleading environment roots.
- Invalid/unknown/duplicate CLI arguments, same-value/no-match no-op behavior, and repeat apply.

## Decision resolution and evidence status

The security research initially preferred opt-in apply; the agreed CLI instead follows the existing opt-in `--dry-run` convention and must warn plainly in help/docs. Safety comes from reviewable scope, preflight, and fixtures rather than an undocumented mode change. Parent integration reports 20 fixture tests and 50 scope tests passed, alongside lint and inventory/scope/practices validation. This worker has not rerun those tests, and no real-checkout apply, hosting action, or adversarial attack execution is claimed.
