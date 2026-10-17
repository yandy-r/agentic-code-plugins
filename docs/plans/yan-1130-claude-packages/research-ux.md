# UX Research: YAN-1130 Claude Add-on Packages

## Executive Summary

This is a maintainer-facing hidden packaging change, not a new public installation journey. Generate unlisted `ycc-mcp`, `ycc-hooks`, and dependency-only `ycc-all` while preserving the shipping `ycc` plugin, public marketplace, settings, and installer behavior. Native hooks require Claude Code **2.1.300 or later**; plugin hooks do not deduplicate against legacy settings hooks, so installing these packages into a maintainer's normal profile is unsafe. A disposable local marketplace is the appropriate acceptance journey, with installation of only `ycc-all` proving automatic dependency installation.

## User Workflows

### Primary: maintainer changes a canonical source

1. Edit the canonical input, not generated package files: `ycc/settings/packages.json`, `mcp-configs/mcp.json`, `ycc/settings/hooks/`, or source plugin version metadata as appropriate.
2. Regenerate Claude package output through the repository's generation workflow. Follow the existing `sync.sh`/`validate.sh` convention rather than creating a second maintainer process. At research time `scripts/sync.sh:4-15` has no Claude target yet; adding this integration is implementation work, not an existing command to advertise.
3. Review generated manifests and payloads. All three add-ons remain unlisted, versioned in lockstep with source **5.3.0** for this change; `ycc-all` has bare dependencies exactly `["ycc", "ycc-mcp", "ycc-hooks"]`, not duplicate component payloads.
4. Use a non-writing drift check, then native `claude plugin validate` for each generated plugin. Existing Codex generator patterns provide a precedent for check/dry-run behavior; avoid requiring maintainers to install a plugin to detect stale files.
5. Run the isolated acceptance flow below. Report generation, manifest validation, dependency installation, and actual hook execution as distinct outcomes; passing one does not establish the others.

Evidence: `AGENTS.md:50-66`; `scripts/generate_codex_plugin.py:101-125`; `scripts/validate.sh:261-268`; `docs/research/ystack/roadmap.json:149-159`; `ycc/settings/packages.json:117-196`. Current `validate.sh --only packages` validates the model/graph, not future generated Claude payload freshness.

### Acceptance: isolated local marketplace

- Use a fresh temporary lab with isolated `HOME` and `CLAUDE_CONFIG_DIR`, an `env -i` allowlist, no inherited credentials, plugins, settings, `HERDR_*`, or production socket configuration. Existing spike scripts establish this pattern.
- Create a **temporary** marketplace containing the existing `ycc` and all three generated add-ons. Do not edit `.claude-plugin/marketplace.json` to expose hidden packages.
- Add that marketplace with `claude plugin marketplace add <lab-marketplace> --scope user`; install **only** `claude plugin install ycc-all@<lab-marketplace> --scope user`. Pre-installing dependencies would invalidate the acceptance proof.
- Inspect `claude plugin list --json` and assert all four names are installed/enabled in the isolated scope, with expected lockstep versions. Preserve sanitized command/result evidence, including the client version. Validate every generated plugin independently as well.
- Do not run real hooks merely to prove dependency installation. If runtime hooks are exercised, use the established stub/fake-API fixture pattern and a disposable Git repository, never real worktree/herdr resources.
- Remove disposable lab state; do not alter the maintainer's actual Claude profile.

**Evidence status:** the coordinator reports a successful isolated dependency-only installation on **Claude 2.1.301** using a validated stub `ycc-all`. This is supplied evidence, not a run performed for this research. It proves the client's dependency-install behavior, not the final generated payloads or older-client coverage. The older repository ADR/model still calls dependency installation unproved; the final acceptance evidence should distinguish this newer observation from historical gates.

Sources: `docs/internal/spikes/claude-hooks.md:22-38`; `scripts/test-claude-hooks-spike.sh`; `scripts/claude_hooks_spike.py`; `ycc/settings/packages.json:179-196`. Official [plugin dependency documentation](https://code.claude.com/docs/en/plugins/dependencies) explicitly supports dependency-only bundles and same-marketplace bare names. Loading siblings with `--plugin-dir` satisfies local dependencies but does **not** prove marketplace auto-installation.

### Alternative: ordinary user or older Claude client

No change. Keep current public install guides, shipping `ycc` listing, installer settings, and enabled plugins intact. Older clients keep installer-managed hooks. Do not recommend enabling `ycc-hooks` or `ycc-all` in an existing profile until the separate migration/dedupe rollout gate passes.

Evidence: `RELEASING.md:76-85`; `ycc/settings/settings.json:14-24,30-31`.

## UI/UX Best Practices

- **CLI feedback is the interface:** identify the package/path and actionable recovery when generation or validation fails. Keep drift checks read-only and return nonzero instead of silently refreshing output.
- **Explicit hidden status:** internal maintainer docs should say generated does not mean listed or safe to activate in an existing profile. Do not add public guide links or installation defaults in this change.
- **Source-of-truth clarity:** make maintainers edit source hooks/MCP configuration, not generated copies. Hook paths must resolve relative to `${CLAUDE_PLUGIN_ROOT}`, not a developer's home or repository checkout.
- **Minimum-version wording:** state “Claude Code 2.1.300+ required for native WorktreeCreate hooks,” not merely “plugins supported.” On 2.1.143 the plugin's SessionStart works while WorktreeCreate silently does not, producing a misleading partially-working installation.
- No graphical interface, responsive layout, loading animation, or accessibility widget is introduced. Plain-text commands and diagnostics should not depend on color alone.

Evidence: `docs/internal/spikes/claude-hooks.md:10-16`; `ycc/settings/hooks/worktree-create.sh:4-23`; [official hook path variables](https://code.claude.com/docs/en/hooks#reference-scripts-by-path).

## Error Handling

| State                                           | User-visible consequence                                     | Safe response                                                                                    |
| ----------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| Generated output stale                          | Maintainer may commit inconsistent packages                  | Fail drift check with affected paths and regeneration command; do not mutate on check            |
| Invalid manifest or missing dependency          | Bundle fails installation/loading                            | Name the package and validator/dependency error; do not convert it into success                  |
| Claude below 2.1.300                            | Plugin WorktreeCreate can silently fall back to Git defaults | Document minimum; retain legacy installer route, no automatic enablement                         |
| Legacy settings hook plus native plugin         | Both execute; duplicate reports or worktree operations       | Keep add-ons unlisted and test in isolation; do not rely on runtime deduplication                |
| User-owned command shares a managed event array | Whole-array removal can delete user customization            | No migration here; future dedupe must remove only positively identified installer-owned commands |
| Client unavailable for live acceptance          | Generated files alone cannot establish installation behavior | Report exact skipped proof; never label static validation as runtime success                     |

The duplicate-hook risk is observed, not speculative: both distinct commands and exactly identical expanded commands execute twice across settings/plugin origins. Multi-handler WorktreeCreate winner selection was **not** established because spike fixtures returned the same path. The current merge engine treats each event array atomically and cannot safely implement selective command removal.

Evidence: `docs/internal/spikes/claude-hooks.md:14-20,40-50,86-92`; `scripts/merge_managed_config.py` (constraint documented by the spike). Current official [hook reference](https://code.claude.com/docs/en/hooks#hook-handler-fields) agrees: matching handlers run in parallel, settings-file identical handlers run once, and plugin/skill copies remain separate.

## Performance UX

Generation/checking is synchronous local maintainer work: concise start/result output and exit status are sufficient. Do not add optimistic success, background installation, telemetry, or network requirements to generation. Live marketplace proof is a separate explicitly invoked operation; existing isolation harnesses use bounded CLI/install timeouts. No latency measurements were performed in this research. Duplicate SessionStart execution is also needless runtime overhead, but correctness and side-effect safety—not speed—are the reason to prevent coexistence.

## Competitive Analysis

The best comparison is Claude Code's own dependency-only “standard plugin set” pattern: one bundle install resolves multiple same-marketplace plugins without copying their contents. Its `--plugin-dir` development workflow is useful for component iteration but deliberately weaker than the requested installation proof. Within this repository, the existing Codex generator and Claude hooks spike are stronger precedents than introducing a new package manager or setup wizard.

References: [Claude plugin dependencies](https://code.claude.com/docs/en/plugins/dependencies); `scripts/generate_codex_plugin.py`; `docs/internal/spikes/claude-hooks.md`.

## Recommendations

### Must have

- Preserve unlisted/public-settings/no-migration scope and lockstep 5.3.0 output.
- Document the 2.1.300 hook minimum and duplicate-hook activation warning in internal maintainer-facing material.
- Prove final generated `ycc-all` installs its three dependencies through a fresh local marketplace, installing only the meta-plugin.
- Keep native manifest validation, dependency install proof, and hook execution evidence separate.

### Should have

- Reuse repository sync/check conventions and disposable marketplace fixture patterns.
- Record exact Claude version and sanitized installed-plugin evidence so future listing decisions can cite reproducible results.
- Explain that listing remains blocked on separate command-level migration/dedupe work preserving user hooks.

### Nice to have

No additional UX features are needed for this hidden generator change; defer public installation/migration walkthroughs to their already-planned rollout.

## Open Questions

- The 2.1.301 stub observation does not establish dependency-install behavior on candidate baseline 2.1.143. This remains a **future listing gate**, not a reason to lower the 2.1.300 native-hook minimum or expand this issue into migration work (`RELEASING.md:78-80`; `ycc/settings/packages.json:193-196`).
- Local-directory marketplace hook execution in the existing spike resolved `${CLAUDE_PLUGIN_ROOT}` to the marketplace source directory, not the cache. Remote/cache execution was not established by that spike; avoid claiming those paths were exercised (`docs/internal/spikes/claude-hooks.md:11,38,86-92`).
- The exact internal acceptance-evidence destination should follow the implementation's existing test/documentation conventions; no new public guide or permanent fake implementation is needed.
