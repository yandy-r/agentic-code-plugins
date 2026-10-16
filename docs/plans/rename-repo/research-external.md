# Rename Repo: External Dependencies Research

## Executive Summary

YAN-1134 / [#304](https://github.com/yandy-r/claude-plugins/issues/304) prepares a local reference transformer for v6.0.0. This document synthesizes the external/dependency investigation; no commands, tests, or live service operations were exercised for these findings.

## Primary APIs

No external APIs are involved. The utility must not call GitHub, Forgejo, package registries, Git remotes, sync scripts, or publishing tools. Repository hosting and old-URL redirect preservation belong to the owner-led later reference flip, not preparation. No credentials, network access, endpoint schemas, rate limits, or API SDKs are required.

## Runtime choice

| Choice                       | Evidence                                                                                                                            | Decision                                                                                       |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Strict Bash wrapper          | `scripts/generate-claude-packages.sh:1-7` delegates to Python                                                                       | Use `scripts/rename-repo.sh` with quoted arguments and `exec python3`.                         |
| Python standard library      | `scripts/codex_marketplace.py:10-15`, `scripts/test_codex_marketplace.py:10-16`; CI uses Python in `.github/workflows/validate.yml` | Use `scripts/rename_repo.py`; add no runtime dependencies.                                     |
| Internal unified diff        | Standard-library `difflib`                                                                                                          | Produce the full preview without an external diff subprocess.                                  |
| In-place shell substitutions | No comparable bulk `sed -i` pattern found by dependency researcher                                                                  | Reject: escaping, byte preservation, preview, and failure handling are harder to reason about. |
| Perl, jq, Node               | Not established as runtime requirements for this operation                                                                          | Do not introduce them.                                                                         |

Useful language documentation: [argparse](https://docs.python.org/3/library/argparse.html), [difflib](https://docs.python.org/3/library/difflib.html), [os.replace](https://docs.python.org/3/library/os.html#os.replace), and [tempfile](https://docs.python.org/3/library/tempfile.html). These are reference links, not claims of a live documentation lookup.

## Matching constraints

A literal owner-qualified substring is necessary but insufficient: it also occurs in machine-local filesystem paths and can prefix longer repository names. Use escaped exact-slug matching with explicit repository boundaries and recognized remote/standalone contexts. Preserve `.git` and supported URL suffixes rather than replacing an unqualified `/claude-plugins.git` anywhere. Protect `-official`, `.fork`, partial owners, and local absolute paths even inside allowlisted files.

## Integration Patterns

The allowlist contains source metadata, installer references, current installation documentation, generator constants, and coupled test expectations. Generated manifests are excluded; the later activation explicitly regenerates them. See [technical research](research-technical.md) for the complete list and [feature spec](feature-spec.md) for the settled contract.

## Resolved research differences

Early exploratory suggestions included literal-only replacement and a Git-assisted file enumerator. Neither is adopted: the fixed 12-file allowlist requires no Git enumeration, and context-aware token boundaries are needed for local-path and longer-name safety. No unresolved external dependency remains.
