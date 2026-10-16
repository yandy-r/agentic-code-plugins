# Hidden Claude native add-ons (YAN-1130)

Target: v6.0.0. These generated packages remain unlisted; the public marketplace and installer are unchanged.

| Package                     | Generated payload                                                          |
| --------------------------- | -------------------------------------------------------------------------- |
| `packages/claude/ycc-mcp`   | Manifest and literal Claude-shaped `.mcp.json` from `mcp-configs/mcp.json` |
| `packages/claude/ycc-hooks` | Manifest, `hooks/hooks.json`, copied executable `worktree-create.sh`       |
| `packages/claude/ycc-all`   | Versioned dependency-only manifest requiring `ycc`, `ycc-mcp`, `ycc-hooks` |

`ycc/settings/packages.json` owns selection and dependency order; `version_source` owns lockstep versions. `listed: false` does not suppress generation. Canonical `ycc/` is not duplicated. Only the committed WorktreeCreate registration is relocated; the unregistered herdr script is not activated.

## Maintainer checks

```bash
./scripts/sync.sh --only claude
./scripts/validate.sh --only claude
./scripts/test-claude-native-packages.sh
```

The generator also supports `--check` (read-only missing/content/extra/executable drift check) and `--dry-run`. It owns modeled Claude add-on roots only and rejects managed symlinks before writing. Edit source configuration or generator, never generated files.

The opt-in smoke harness isolates HOME/config/XDG/temp paths, builds a directory-source marketplace from actual packages, installs only ycc-all, checks all four plugins enabled at the product version, and exercises the copied WorktreeCreate script in a disposable Git repository. No Claude session, inference or MCP-server execution is requested. `CLAUDE_BIN` selects a CLI; `VERIFY_TEMP_DIR` selects an existing temporary parent; `--keep` retains evidence.

## Observed acceptance evidence

On Claude Code **2.1.301**, each actual generated package passed `claude plugin validate`. Installing only ycc-all automatically installed ycc, ycc-mcp and ycc-hooks. The contained copied-script worktree smoke passed. The harness also passed with relative `VERIFY_TEMP_DIR=.` after review corrected temporary-path normalization.

Sixteen generator boundary tests and 46 changed-path scoping checks passed. The generator/MCP sentinel checks preserve literal `${ENV}` references. Modified-source Markdown/Prettier, Ruff/Black and ShellCheck checks passed.

## Compatibility and rollout limits

Native WorktreeCreate requires Claude Code **2.1.300 or later** per the [hook spike](spikes/claude-hooks.md). Settings and plugin copies both run: do not enable both before installer-owned command-level migration/dedupe exists. User-owned hooks must survive that migration.

This local directory-source install proof does not establish dependency support on candidate baseline 2.1.143, a minimum dependency-capable version, remote/public-fork installation, cache hook dispatch or authenticated MCP behavior. Existing package-model listing gates remain closed. YAN-1139 owns migration; YAN-1140 owns listing; this change does not authorize either.
