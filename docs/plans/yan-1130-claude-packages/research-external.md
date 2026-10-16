# External contracts: Claude native packages

## Executive Summary

Claude Code supports all three requested package shapes without an SDK: a conventional `.mcp.json` plugin, a `hooks/hooks.json` plugin, and a manifest-only dependency bundle. Generate `packages/claude/ycc-mcp`, `ycc-hooks`, and `ycc-all` from the package model, with the canonical source version currently `5.3.0`; keep them unlisted. Bare dependency names intentionally resolve within the installing marketplace. Native `WorktreeCreate` requires the repository's documented minimum Claude Code `2.1.300`; generation does not authorize public rollout or removal of installer hooks.

## Primary APIs

The integration API is an on-disk plugin format, not a hosted HTTP API. Packaging itself has no authentication, rate limit, or per-request price. Individual MCP services retain their existing authentication and service terms; this task should not change them.

| Contract                  | Official documentation                                                                                    | Required behavior / safe default                                                                                                                                                            |
| ------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Manifest                  | [Manifest reference](https://code.claude.com/docs/en/plugins/manifest-reference#manifest-file)            | Put metadata in `<root>/.claude-plugin/plugin.json`; other payloads belong outside `.claude-plugin/`. Include `name`, canonical `version`, package description, and existing source author. |
| MCP payload               | [MCP components](https://code.claude.com/docs/en/plugins/components#mcp-servers)                          | Put `{ "mcpServers": { ... } }` at `<root>/.mcp.json`. Preserve canonical commands, argv, transport types, URLs, and environment placeholders.                                              |
| Hooks payload             | [Hooks components](https://code.claude.com/docs/en/plugins/components#hooks)                              | Put `{ "hooks": { ...event map... } }` at `<root>/hooks/hooks.json`; copy the referenced scripts inside the package.                                                                        |
| Plugin-relative resources | [Environment variables](https://code.claude.com/docs/en/plugins/manifest-reference#environment-variables) | Keep `${CLAUDE_PLUGIN_ROOT}` literal until runtime and quote paths in shell-form hook commands. Never bake in the checkout path or refer to `~/.claude/hooks`.                              |
| Bundle dependencies       | [Plugin dependencies](https://code.claude.com/docs/en/plugins/dependencies#bundle-plugins-for-a-team)     | A manifest-only plugin is valid; set `dependencies` to `["ycc", "ycc-mcp", "ycc-hooks"]`, derived from model `requires`, with no duplicated payload.                                        |
| Validation                | [Validate the manifest](https://code.claude.com/docs/en/plugins/manifest-reference#validate-the-manifest) | The CLI validates manifest shape and referenced payloads. Its MCP validation requires `2.1.281+`; native worktree behavior needs the stricter repository baseline.                          |

## Libraries and SDKs

No new dependency is needed. Existing Python stdlib JSON, filesystem, and package-model machinery is sufficient. `scripts/package_model.py:23-55` already exposes immutable runtime `components`, `requires`, and `listed` fields. `scripts/generate_codex_plugin.py:113-143,146-188` demonstrates selecting included/native payloads independently from catalog visibility and resolving the version before writing output. Reuse those conventions, not Codex-specific manifest fields such as `interface`.

## Integration Patterns

### Manifest and dependency boundaries

- `ycc/settings/packages.json:65-82,117-138,179-196` declares the three Claude packages as included/native/unlisted; `ycc-all` has no components and requires exactly the three named dependencies.
- `ycc/.claude-plugin/plugin.json:1-8` supplies canonical version `5.3.0` and author. `target_release: v6.0.0` is rollout intent, not the generated version.
- Bare dependencies resolve against the bundle's own marketplace. They do not resolve directly to neighboring filesystem directories. An isolated test marketplace must therefore contain entries for `ycc` and all three generated packages.
- Official docs explicitly state installing a manifest-only bundle installs its dependencies. The coordinator additionally supplied observed evidence on Claude `2.1.301`: a stub `ycc-all` validated and installing only it through an isolated marketplace installed all dependencies. This research did not repeat that experiment.
- Do not add `@ycc` qualification or version-range objects. Those introduce cross-marketplace or git-tag resolution semantics outside the requested bare-name contract. Build-time lockstep versions do not imply runtime version pinning of bare dependencies.

### MCP preservation

`mcp-configs/mcp.json:1-48` is already in Claude's native wrapper shape and defines ten servers, including two separately named Linear endpoints. Preserve it without Codex transport conversion: `github-mcp-server stdio`, `npx` arguments, HTTP endpoints, and `${XERO_CLIENT_ID}` / `${XERO_CLIENT_SECRET}` references remain unchanged. Do not evaluate environment variables during generation or add secret material. Do not infer deduplication merely because two endpoints match.

### Hook registration and relocation

`ycc/settings/settings.json:14-25` registers `WorktreeCreate` as `bash ~/.claude/hooks/worktree-create.sh`. The native equivalent references the packaged copy through `${CLAUDE_PLUGIN_ROOT}`. `ycc/settings/hooks/herdr-agent-state.sh:10-23` accepts only the `session` argument and is gated by `HERDR_ENV`, `HERDR_SOCKET_PATH`, `HERDR_PANE_ID`, and Python availability. A native `SessionStart` registration must preserve the `session` argument; merely copying the file does not register a hook.

The source settings currently do **not** declare a herdr `SessionStart` event. Its intended native registration is supported by the hook spike, not by a generic copy of `settings.json`. Keep this distinction explicit when deriving the hooks payload: settings provide the current worktree registration; the script and documented spike provide the herdr session contract. Do not copy unrelated settings, enabled plugins, environment defaults, or status-line configuration into the package.

## Constraints and Gotchas

1. **Hook JSON wrappers differ from inline manifest hooks.** A hooks file needs top-level `hooks`; an inline manifest hooks object is the event map itself. Prefer the conventional file and omit a redundant manifest `hooks` declaration: docs say both sources load, so redundancy can double-register hooks.
2. **Use conventional MCP auto-discovery.** `.mcp.json` is automatically loaded. A manifest `mcpServers` declaration is unnecessary; declaring it again creates a second merge source. A server declared later wins on equal name.
3. **Relocatable means self-contained.** Manifest component paths must start with `./`, exist, and remain inside the plugin root. Package scripts must not reach into the source checkout. Runtime hook script paths should use quoted `${CLAUDE_PLUGIN_ROOT}` references. The root can change on updates and is not persistent state storage.
4. **Tool names change under native MCP packaging.** Docs name the server `plugin:<plugin>:<server>` and its tools `mcp__plugin_<plugin>_<server>__<tool>`. Existing global MCP entries do not automatically disappear. Migration and permission-name changes remain outside this task.
5. **Generation is not rollout.** `docs/internal/spikes/claude-hooks.md:10-20,38-50,86-92` proves plugin/settings duplicates execute twice, including identical expanded commands; no automatic dedupe exists. Keep public marketplace, settings, and migration unchanged.
6. **Version evidence is bounded.** That spike observed `SessionStart` on `2.1.143` and `2.1.300`, but plugin `WorktreeCreate` only on `2.1.300`. It used a local directory marketplace; remote/cache execution and the actual herdr socket flow were not established. Do not claim broader runtime verification from manifest validation.

## Code Examples

Illustrative generated `ycc-all/.claude-plugin/plugin.json` shape (author/description should come from the existing sources):

```json
{
  "name": "ycc-all",
  "version": "5.3.0",
  "description": "Claude meta plugin that depends on the other native Claude packages.",
  "author": { "name": "yandy-r" },
  "dependencies": ["ycc", "ycc-mcp", "ycc-hooks"]
}
```

Illustrative `hooks/hooks.json` registrations if scripts are copied alongside that JSON file:

```json
{
  "hooks": {
    "WorktreeCreate": [
      { "hooks": [{ "type": "command", "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/worktree-create.sh\"" }] }
    ],
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [{ "type": "command", "command": "sh \"${CLAUDE_PLUGIN_ROOT}/hooks/herdr-agent-state.sh\" session" }]
      }
    ]
  }
}
```

These examples are research contracts, not files produced or executed by this assignment. Preserve the source script bodies and modes; explicit interpreters avoid relying on an executable bit at dispatch time.

## Open Questions

- The package model still labels MCP as unspiked and the meta package as blocked pending dependency-install proof. Update evidence only to the extent the implementation's retained, versioned proof supports it; do not silently clear listing/migration gates.
- The canonical registration source for herdr is not `settings.json`. The narrowly supported default is an explicit native `SessionStart` mapping to the existing `session` script contract, matching the spike, without creating additional lifecycle registrations.
- No need to resolve upstream hosted-service pricing, cross-marketplace policy, or semver tag strategy to implement these unlisted generated artifacts.

## Evidence and Validation Status

Read the official documentation linked above and the local source/evidence paths cited inline. No build, tests, formatter, CLI plugin validation, installation, real hook execution, or remote MCP calls were run in this research assignment.
