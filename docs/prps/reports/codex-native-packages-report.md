# Implementation Report: Codex native packages

## Summary

YAN-1131 / GitHub #300, target v6.0.0. Implemented model-driven dormant MCP metadata and an explicit external native distribution export. Legacy default skills, combined plugin and catalog remain byte-identical. Production listing and migration remain gated under YAN-1140/YAN-1139; hooks remain excluded under YAN-1149.

## Tasks Completed

| Task                   | Result                                                                                                                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Native resource policy | Document-relative resources, SCRIPT_DIR executable fallbacks, forwarded-prompt absolute substitution and scaffold placeholder preservation                                      |
| Native export          | Included package selection, canonical version, translated MCP, listed-aware catalog builder, external destination confinement, model-derived owned cleanup and read-only checks |
| Validation             | Default/dormant and explicit native component/catalog policies; critical unit tests wired into codex group                                                                      |
| Runtime smoke          | Actual full/sparse Git fixture installs plus catalog-only negative; independent cache payloads, credential metadata and cache-relative helper                                   |

## Verification

| Check                                    | Observed result                                                                                                                         |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Modified Python/shell lint               | Passed ruff, black and project shellcheck configuration                                                                                 |
| Scoped codex/packages/release validation | Passed                                                                                                                                  |
| Latest codex validation                  | Passed: 12 plugin generator and 7 native resource tests, existing skill/agent checks                                                    |
| Native structural validator              | Valid export passed; deliberately added MCP declaration in skills-only manifest failed both drift and component checks (exit 1)         |
| Actual Codex smoke                       | codex-cli 0.161.0; full and sparse independent installs passed; catalog-only sparse install failed with no cache, as expected           |
| Helper smoke                             | Installed git-cleanup resource resolved release-state.sh inside cache; `get` returned `present=0` from unchanged clean user-project cwd |
| Legacy stability                         | Skills --check passed; no changes under legacy .codex-plugin/ycc or discovered .agents catalog                                          |

The final harness compares file bytes and executable bits (Git preserves these), not raw checkout permissions. It checks an out-of-sparse sentinel to prove actual filtering. The latest main-agent run used pinned local fixture SHA `0849306e2c59f5ec3fb3998e81a96afe868fd2a9`; its disposable sandbox was removed after success. An earlier revised run retained `/tmp/codex-native-packages.g5f85M/transcript.log`; that ephemeral path is not a permanent artifact.

## Adversarial Review

Three reviewers examined correctness, resources and runtime proof. Fixed: model-derived symlink/prune/check ownership including excluded empty roots; dormant exclusion lifecycle; forwarded agent prompt paths; scaffold placeholder paths; whole-tree bounded resource resolution coverage; sparse sentinel/negative proof; Git executable-bit portability.

## Decisions and Deviations

- Isolated `--native-output DIR` instead of replacing the live catalog: an empty or renamed catalog is already observable before the flip.
- Reuse Codex MCP translation (`env_vars`) rather than copy Claude interpolation literally; no generation-environment credentials materialized.
- Keep the source-derived full distribution out of the checked-in generated tree; only tiny dormant MCP files are added by default.
- Preserve public guides and RELEASING.md. Existing ADR records observed state.
- Enhanced planning helper expected an unavailable portable agents directory; actual seven-role planning agents completed successfully. Feature-spec validator reached its broken Markdown-link regex after structure/content checks; PRP plan validator passed with zero warnings.

## Evidence Boundaries

The fixture uses HTTPS-shaped URLs rewritten to local file-only Git transport. It proves Codex discovery, sparse checkout, independent installs, cache contents, MCP metadata and a harmless installed helper; not public GitHub authentication/transport, actual codex-cli 0.160 execution, credentialed MCP execution, inference, or OS-level network isolation. Existing YAN-1140 clean-machine listing gates and YAN-1149 hooks gate retain those responsibilities.
