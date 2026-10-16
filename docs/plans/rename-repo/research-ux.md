# Rename Repo: Maintainer UX Research

## Executive Summary

Provide a predictable noninteractive maintenance CLI: preview the complete bounded change, review it, and explicitly rerun without `--dry-run` only during the later approved flip. No browser, interactive confirmation, service login, or external API is involved.

## Existing conventions

The UX researcher inspected `scripts/sync.sh:1-63` for help/options, `scripts/eval.sh:1-40` for validation/errors, `scripts/style.sh` for opt-in dry-run output, and Python generators for stdout summaries and stderr diagnostics. Those conventions support a strict wrapper with a Python parser, not a second shell argument parser.

### Core User Workflows

```bash
scripts/rename-repo.sh --from yandy-r/claude-plugins --to yandy-r/agentic-code-plugins --dry-run
```

This previews only. The same invocation without `--dry-run` applies changes; do not execute that form against the preparation checkout. `--help` / `-h` succeeds and documents required slugs, apply-by-default semantics, fixed source scope, and the absence of host rename, remote updates, or sync. Do not add `--apply`, root overrides, or prompts.

### Feedback and State Design

| State                            | Feedback                                                                            | Recovery                                                                   |
| -------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Dry-run with changes             | Complete unified diff with stable repository-relative labels and a no-write summary | Review every hunk; preserve the diff in the PR.                            |
| Apply with changes               | Plain per-file/summary feedback                                                     | Inspect the changed sources before later explicit regeneration.            |
| Already transformed / no matches | Successful no-op message                                                            | No repair required.                                                        |
| Invalid CLI                      | Diagnostic and useful usage on stderr; nonzero status                               | Correct the slug/argument, then preview again.                             |
| Missing/unsafe managed path      | Name the offending relative path; nonzero status before any writes                  | Restore the required source or remove the unsafe link, then preview again. |

Keep machine-readable diff output uncolored and avoid exposing absolute checkout paths in labels. Results go to stdout, errors to stderr. Do not truncate hunks, silently skip required files, or imply that the utility renamed a remote repository.

## Documentation location

Add a short usage/scope paragraph to `CONTRIBUTING.md` near maintainer-only workflows. Link the detailed spec or plan rather than changing release policy. `RELEASING.md` and the changelog are outside this documentation slice.

## Evidence and limits

Early UX suggestions included exact wording, protected-target bans, and verbose counters. These are not required interfaces; correctness and a full reviewable diff take precedence. The settled contract requires argument safety and preservation of protected content, not a new policy banning arbitrary destination names. Parent integration reports the real preview contains 24 anchored replacements in 12 files, with no protected strings in the diff. The README bare-name rewrite was removed. This worker has not rerun that preview; no apply or hosting operation is implied.
