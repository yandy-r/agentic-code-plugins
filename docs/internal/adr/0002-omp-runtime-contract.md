# ADR 0002: oh-my-pi (OMP) runtime contract

- **Status:** Accepted on authorized PR merge. The PR that adds this file is the
  owner's approval once merged; until then it is proposed.
- **Date:** 2026-10-19
- **Tracking:** Linear YAN-1165; GitHub [#365](https://github.com/yandy-r/ystack/issues/365)
- **Evidence:** [OMP runtime contract spike](../spikes/omp-runtime-contract.md) and its harness
  [`scripts/test-omp-runtime-contract-spike.sh`](../../../scripts/test-omp-runtime-contract-spike.sh)
- **Tested version:** `omp 18.12.2`; upstream `can1357/oh-my-pi` tag `v18.12.2`, commit
  `1d5aff90b057ce7dbfe32ea557a527c1b3144b72`
- **Builds on:** [ADR 0001](0001-package-model-and-versioning.md) (package names, lockstep versioning)

## Context

oh-my-pi (`omp`) installs Claude-compatible marketplaces. It reads
`.omp-plugin/marketplace.json` first, then falls back to `.claude-plugin/marketplace.json`. It loads
skills, commands, agents, rules, TypeScript hook and extension factories, tools, and MCP from each
plugin root. The spike ran every surface on a clean, network-isolated home with no inference.
It found four gaps in the Claude tree:

- A plugin root that has only `.claude-plugin/plugin.json` has its agent `model:` dropped. With
  `.omp-plugin/plugin.json` the model is kept (verified live).
- `${CLAUDE_PLUGIN_ROOT}` is expanded in MCP config only, not in skill bodies.
- Shell hooks and `hooks/hooks.json` are never executed. There is no `WorktreeCreate` event.
- The marketplace does not read plugin `dependencies`. No plugin channel sets settings or model
  roles.

OMP has no trust gate: installed plugin code runs in-process with full user privileges.

## Decision

1. **Dedicated OMP tree.** ycc generates `.omp-plugin/marketplace.json` with relative sources to
   generated OMP package directories. Each directory carries:
   - an `.omp-plugin/plugin.json`;
   - a `package.json` with a unique runtime `name`, the lockstep `version`, and `omp.extensions`
     where adapters ship.

   ycc does not reuse the Claude tree or the root `.claude-plugin/marketplace.json` for OMP. The
   catalog uses no `npm` sources.

2. **Namespace.** Keep `ycc`. Nothing in OMP forces a rename:
   - skills are `/skill:<name>`;
   - commands are `/ycc:<cmd>`;
   - MCP servers are `ycc-mcp:<server>`.
3. **Hooks.**
   - `WorktreeCreate` is **unsupported** on OMP. There is no event to bind, and OMP's task
     isolation manages its own worktrees.
   - herdr session reporting ships as an **extension adapter** bound to `session_start` only. It
     is based on the ycc-owned `ycc/settings/cursor/herdr-session-start.sh`. The Claude-side
     `herdr-agent-state.sh` is herdr-managed and is not ported. A shutdown report is not bound
     ([INFERENCE] about herdr's API).
4. **`ycc-all` is a fallback.** It is omitted from the OMP catalog, and the docs list the
   individual packages to install.
5. **Minimum version.** The supported floor is **`>=18.12.2`**, the tested version. Evidence
   points to a hard floor of 18.2.1 (changelog and tag-bisect) and a recommended 18.11.0. These
   are recorded in the spike but are not claimed until an older binary passes the harness.
6. **Trust.** Every shipped extension, tool, and MCP command is treated as full-trust code. It must
   be side-effect-free at load and fail closed when its dependency is absent. The install docs
   state this, because OMP does not prompt.

### Package matrix (OMP)

| Package                               | OMP mechanism                                                      | Verdict                                        | Notes                                                                                                                                                                         |
| ------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ycc`                                 | Generated package: skills, agents, `_shared`, optional `commands/` | adapter                                        | Rewrite `${CLAUDE_PLUGIN_ROOT}`, `/ycc:` and `_shared` references. Translate agent tools and models to `@role` aliases. The 9 `disable-model-invocation` skills map natively. |
| `ycc-mcp`                             | Generated package with `.mcp.json`                                 | native content, adapter packaging              | Servers become `ycc-mcp:<server>`. `${VAR}` env placeholders expand.                                                                                                          |
| `ycc-hooks`                           | Generated extension package (`omp.extensions`)                     | adapter                                        | herdr `session_start` shim only. `WorktreeCreate` is unsupported. A session restart is needed after install.                                                                  |
| `ycc-rules`                           | Generated package with flat `rules/`                               | adapter                                        | Flatten under unique names. `paths` becomes `globs`. Keep `alwaysApply` and `description`.                                                                                    |
| `ycc-all`                             | none                                                               | fallback                                       | Dependencies are not read. Install the parts separately.                                                                                                                      |
| `ycc-agents`                          | none                                                               | n/a                                            | Deferred to v7 on Claude (ADR 0001). On OMP, agents ship inside `ycc`.                                                                                                        |
| `@yandy-r/ycc-opencode`               | none                                                               | n/a                                            | opencode-specific npm plugin. OMP also rejects `npm` marketplace sources.                                                                                                     |
| `installer-fallback`                  | user and project config layers                                     | fallback                                       | Each payload maps to its component row in the spike matrix: rules and instructions, a settings snippet, a statusline extension.                                               |
| Settings, model pins, `settings.json` | user `config.yml` (`modelRoles`, `task.agentModelOverrides`)       | fallback                                       | No plugin channel. Documented or opt-in snippet.                                                                                                                              |
| Status line, status-bar mod           | `ExtensionAPI` UI (`ctx.ui.setStatus`, `setWidget`)                | adapter (status line); unsupported as is (mod) | `setFooter` is a no-op in OMP. The mod stays in `ycc-mods`. Port only on demand.                                                                                              |

The full per-component matrix, including every skill class, agents, and rules families, is in
the [spike, section 3](../spikes/omp-runtime-contract.md#3-component--verdict-matrix).

### Required adapters

1. OMP catalog and package-tree generator: `.omp-plugin/marketplace.json`, per-package
   `.omp-plugin/plugin.json` and `package.json`, and the lockstep version in the catalog and
   `package.json`.
2. Skill-body rewriter: `${CLAUDE_PLUGIN_ROOT}` paths, `/ycc:<name>` invocations, and `_shared`
   references.
3. Agent translator: tool IDs (`WebSearch` → `web_search`, with `WebFetch` and `NotebookEdit`
   mapped or dropped), Claude `model` to OMP `@role` aliases, and MCP tool names for
   `ycc-mcp:<server>`.
4. Rules flattener: the nested Cursor tree becomes unique flat names, and `paths` becomes `globs`.
5. herdr extension shim: `session_start` only, run through `pi.exec`. It synthesizes the stdin
   payload that `herdr-session-start.sh` reads.
6. Optional: `commands/` wrappers for `/ycc:<name>`, and a status-line extension that renders
   through `ctx.ui.setStatus` or `setWidget`.

## Consequences

- OMP gets its own generated tree, validators, and lockstep surfaces. Release tooling must bump
  and check them.
- Users who already run Claude ycc see no duplicates by default, because foreign user sources are
  opt-in. Copies from the `install.sh` `agents` target in `~/.agents/skills` do load by default and
  can duplicate native skills. Migration must detect them.
- `plugin-overrides.json` does not disable marketplace installs. The per-project switch is
  `omp plugin disable --scope project`.
- Installers resolve paths through omp (`omp plugin list --json`), never a hard-coded `~/.omp`,
  because profiles and XDG relocate state.
- The harness's agent-model probe imports an internal omp module. An upstream move fails the
  harness loudly; it does not silently pass.

## Follow-up mapping

| Issue    | Scope from this ADR                                                                                                     |
| -------- | ----------------------------------------------------------------------------------------------------------------------- |
| YAN-1166 | Add the `omp` target, capability matrix, and package schema and inventory entries; floor `>=18.12.2`                    |
| YAN-1167 | Skill and `_shared` generation, body rewriter, invocation policy (`disable-model-invocation`)                           |
| YAN-1168 | Optional `commands/` wrappers or a documented `/skill:<name>` entrypoint                                                |
| YAN-1169 | Agent translator (tools, `@role` models, MCP names) under `.omp-plugin/plugin.json`                                     |
| YAN-1170 | Workflow semantics: tool-name gaps, OMP task isolation instead of `WorktreeCreate`, background jobs                     |
| YAN-1171 | `.omp-plugin/marketplace.json` and per-package tree generator; `ycc-all` omitted                                        |
| YAN-1172 | `install.sh` OMP lifecycle using `omp plugin` (`--dry-run`, scopes, profile and XDG-aware paths)                        |
| YAN-1173 | `ycc-mcp` OMP package (native `.mcp.json`)                                                                              |
| YAN-1174 | `ycc-hooks` extension package: herdr `session_start` shim; `WorktreeCreate` documented unsupported                      |
| YAN-1175 | `ycc-rules` flattener; `modelRoles` and settings fallback snippets; permission defaults                                 |
| YAN-1176 | Coexistence and dedupe with `~/.agents` and Claude opt-in, profiles, and the trust-model docs                           |
| YAN-1177 | Validators, generator tests, and CI for the OMP tree                                                                    |
| YAN-1178 | Live acceptance matrix extending the spike harness (real ycc tree, network installs, older versions to lower the floor) |
| YAN-1179 | Install, fallback, and migration docs, including the restart-after-install note                                         |
| YAN-1180 | Release gate: list the OMP packages in a maintainer release                                                             |
