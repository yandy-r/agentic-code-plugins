# External research: OMP discovery, precedence and MCP identity (omp 18.12.5)

## Executive Summary

OMP dedupes every capability by name in provider-priority order. Skills are additionally deduped by content: identical copies drop and differing copies become `<namespace>/<name>` aliases. MCP also collapses equivalent connections, keyed on exact URL, headers, auth and `requestIdFormat`. MCP OAuth tokens are keyed by profile plus the verbatim URL, so a query string yields a distinct token while Linear ignores it.

Upstream sources:

- `can1357/oh-my-pi` at tag `v18.12.5` (commit `d5cd750e`, cloned to `/tmp/omp-src-18125`). `src/` is
  `packages/coding-agent/src/`.
- Linear MCP: <https://linear.app/docs/mcp.md>.

Live evidence is in [`research-live-probes.md`](research-live-probes.md).

## Integration Patterns

### Capability engine

- **Dedupe.** `loadCapability` (`src/capability/index.ts:142-301`) loads providers by priority,
  highest first. Ties keep registration order (`src/discovery/index.ts:21-40`), so at priority 70
  `claude-plugins` (the OMP marketplace registry) beats `agents`, which beats `codex`. Dedupe is
  first-wins on `capability.key`. Losers stay in `result.all` with `_shadowed: true`, and only the
  Extensions dashboard reads that flag.
- **Foreign gate.** `FOREIGN_USER_PROVIDERS` is cursor, codex, claude, claude-plugins, gemini,
  opencode, windsurf and github (`index.ts:51-60`).
  - Their **user** dirs load only through `enabledProviders` (`isUserSourceEnabled`,
    `index.ts:363-373`).
  - `native`, `agents` (`~/.agents/skills`) and the OMP plugin registry are always on.
  - Project dirs are never gated.
- **Settings layering.** The layers are defaults < user `config.yml` < project `.omp/config.yml` <
  `--config` overlay. Arrays **replace** wholesale (`docs/settings.md:267,1075`).
  - `enabledProviders` and `disabledProviders` accept path-scoped entries (`docs/settings.md:310-340`).
    For example, `{"path": "/x", "providers": ["codex"]}` was verified live with `config get` from
    inside and outside `/x`.

## Primary APIs

### Per-component keys and precedence

| Component          | Key                                                                                                                                                                 | Order (high → low)                                                                                                                                                                                                         | Collision handling                                                                                                                                                                                                                                                                                                                   | Source                                                      |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| Skills             | frontmatter `name`, else the dir                                                                                                                                    | native 100 (`.omp/skills` walked up, then `<agentDir>/skills`) > skillshare 95 > omp-plugins 90 (extension roots only) > claude 80 > agent-plugins 75 > claude-plugins 70 = agents 70 = codex 70 > opencode 55 > github 30 | `loadSkills` dedupes **by content**: an identical body and frontmatter are dropped silently. Differing copies become `<namespace>/<name>` with a `name collision: …` warning. The namespace is the plugin name, else the dir owning `skills/`; a dotted home falls back to the provider id (`agents`, `claude`, `codex`, `opencode`) | `src/extensibility/skills.ts:62-199,289-470`                |
| Skill exclusion    | `skills.ignoredSkills` (glob, matched on the raw **and** final name), `disabledExtensions: ["skill:<name>"]`, `skills.enable{Agents,Claude,Codex,Pi}{User,Project}` | –                                                                                                                                                                                                                          | Applied before admission                                                                                                                                                                                                                                                                                                             | `skills.ts:311-375`; `docs/skills.md:112-135`               |
| Slash commands     | `cmd.name`                                                                                                                                                          | native > omp-plugins > claude 80 (`commands.enableClaudeUser` false) > claude-plugins (`<plugin>:<cmd>`) = agents = codex > opencode 55 (`commands.enableOpencodeUser` false)                                              | First-wins with no warning. `ycc:<cmd>` and the bare opencode `<cmd>` are different names, so both load                                                                                                                                                                                                                              | `docs/slash-command-internals.md:30-110`                    |
| Task agents        | `agent.name`                                                                                                                                                        | project `.omp/agents` > user `.omp/agents` > extension packages > plugin roots (project before user) > bundled                                                                                                             | First-wins with no warning. `.claude/.codex/.cursor/opencode` agent dirs are never read                                                                                                                                                                                                                                              | `src/task/discovery.ts:86-164`                              |
| Rules              | `rule.name`                                                                                                                                                         | native 100 > omp-plugins 90 > claude-plugins 70 = agents 70 > cursor 50 > …                                                                                                                                                | First-wins and silent                                                                                                                                                                                                                                                                                                                | `src/capability/rule.ts:393-397`                            |
| MCP                | `server.name` plus `isSameMCPConnection`                                                                                                                            | native 100 > omp-plugins 90 > claude 80 > agent-plugins 75 > claude-plugins 70 = codex 70 > gemini 60 > opencode 55 > cursor 50 > mcp-json 5 (project root `mcp.json`/`.mcp.json`)                                         | Same name or **equivalent connection** → shadowed. `disabledServers` (user `mcp.json`) suppresses by name but still claims the key                                                                                                                                                                                                   | `src/capability/mcp.ts:77-129`; `src/mcp/config.ts:128-145` |
| Context files      | `level` + basename                                                                                                                                                  | native `<agentDir>/AGENTS.md` > claude `~/.claude/CLAUDE.md` > codex > opencode                                                                                                                                            | One user-level file wins; the rest are shadowed                                                                                                                                                                                                                                                                                      | `src/capability/context-file.ts:41-47`                      |
| Extensions / hooks | **absolute path**                                                                                                                                                   | native `.omp/extensions`, `<agentDir>/extensions`, hook `.ts`/`.js` from **every** enabled provider (`.claude/hooks/{pre,post}`), plugin `omp.extensions`, `extensions:` setting, `-e`                                     | Path dedupe only, so the same file under two paths loads twice                                                                                                                                                                                                                                                                       | `src/extensibility/extensions/loader.ts:572-660`            |

## Plugins, scopes, profiles, reload

- **Plugin roots** (`listClaudePluginRoots`, `src/discovery/helpers.ts:1222-1450`). The Claude registry
  `~/.claude/plugins/installed_plugins.json` is read first. The OMP registry is then **authoritative per
  plugin id** and drops the Claude entries for that id (`:1355-1360`). Project registry entries shadow
  user entries (`:1436-1442`), and `--plugin-dir` beats both.
- **Scope collisions.** A project install shadows a user install of the same id. A disabled project
  entry is skipped, so the user copy serves. `uninstall`, `enable` and `disable` need `--scope` when
  both exist.
- **Profiles.**
  - `--profile` / `OMP_PROFILE` move the whole config root to `~/.omp/profiles/<n>`, which covers
    plugins, `agent.db`, `mcp.json` and `config.yml`.
  - `PI_CODING_AGENT_DIR` moves only the default profile's agent dir. The plugins dir stays at the
    config root (`packages/utils/src/dirs.ts:495-504,700-705`).
  - `~/.agents`, `~/.claude`, `~/.codex` and project dirs are shared by every profile.
- **Reload.**
  - Discovery runs at session start, and nothing watches files.
  - `/reload-plugins` refreshes plugin roots, agents, skills, commands, capabilities and MCP.
  - `/plugins enable|disable` refreshes immediately.
  - A live `enabledProviders` or `disabledProviders` change refreshes skills and commands
    (`sdk.ts:5042`). `mcp.enableProjectConfig` is live.
  - Hooks, tools and extension modules need a restart (`docs/marketplace.md`,
    `docs/extension-loading.md`).
- **Trust.**
  - `isProjectTrusted: () => true` (`src/extensibility/extensions/runner.ts:1433`).
  - Project `.omp/extensions`, project hooks, project MCP (`.mcp.json`, `.omp/mcp.json`), project
    plugin registries and project `extensions:` settings all execute at session start.
  - Controls: `--no-extensions`; `--trusted-extension <abs>`; `disabledProviders`;
    `mcp.enableProjectConfig`; `disabledServers`.

## MCP connection identity and OAuth (YAN-1291)

- **Equivalence.** `isSameMCPConnection` (`src/capability/mcp.ts:77-106`) returns false when any of
  `auth`, `oauth` or `requestIdFormat` (unset = `number`) differ, or the transport differs. For HTTP it
  then compares `url === url` (exact string, no normalization) and deep-equal `headers`.
- **`requestIdFormat`.** It is read only from OMP-native files, root `mcp.json` and extension packages.
  It is **ignored** for configs translated from other tools (`docs/mcp-config.md:111`). It was dropped
  live from the plugin `.mcp.json`.
- **Plugin `.mcp.json` schema.** Each transport is `additionalProperties: false`. Claude-format keys
  survive translation.
- **OAuth credential id.** The id is `mcp_oauth:profile:<profile>:<serverUrl>`, with the URL **verbatim,
  query included** (`src/mcp/oauth-flow.ts:16-34`). It is stored in `<agentDir>/agent.db`
  (`auth_credentials`), or in the auth broker.
  - Same URL → one row. `/mcp reauth <either>` overwrites it.
  - A different URL string → a separate row and a separate login.
  - Headers never separate tokens, except an explicit `Authorization` header, which disables the
    URL-keyed lookup (`src/mcp/oauth-credentials.ts:34-37`).
- **Discovery.** RFC 9728 discovery strips the query and probes
  `/.well-known/oauth-protected-resource/<path>` (`src/mcp/oauth-discovery.ts:358-372`). The advertised
  `resource` drives RFC 8707 (`oauth-flow.ts:249-300`).
- **Linear.**
  - It documents `https://mcp.linear.app/mcp` (OAuth 2.1 + DCR; Streamable HTTP) and `/mcp/readonly`.
    Query strings are not documented.
  - Live: the `?ycc-server=linear-personal` query is ignored by the server, and the protected-resource
    document is byte-identical with `resource` = `https://mcp.linear.app/mcp`.
  - `/mcp/` changes the advertised resource to `…/mcp/`, so it was rejected.
  - DCR works with `token_endpoint_auth_method: none`.
- **Other clients** (from the repo; the code was not re-run):
  - Claude Code, Cursor and Codex key MCP auth by server name. Claude's own docs show
    `claude mcp add … linear-server https://mcp.linear.app/mcp`.
  - In this repo, `linear` and `linear-personal` are already two named servers on Codex
    (`docs/internal/spikes/codex-public-fork-install.md:104`).
  - The query string also reaches those clients if it is added to the shared `mcp-configs/mcp.json`.
    It is not proven harmless there: the server-side behavior is identical, but client token keying
    may move. That is the YAN-1291 regression boundary.

## Gaps

- Two real Linear accounts (OAuth through a browser) were not exercised, so "OAuth tokens separate per
  server" is proven at the OMP credential-key level only.
- Hot-reload of a removed `~/.agents/skills` dir mid-session was not exercised; restart is documented.
