# oh-my-pi (`omp`) Runtime Contract Spike (YAN-1165)

- **Date:** 2026-10-19
- **Issue:** `YAN-1165`; GitHub [#365](https://github.com/yandy-r/ystack/issues/365)
- **Target CLI:** `omp 18.12.2` (`omp --version` prints `omp/18.12.2`)
- **Upstream:** [`can1357/oh-my-pi`](https://github.com/can1357/oh-my-pi) tag `v18.12.2`, commit `1d5aff90b057ce7dbfe32ea557a527c1b3144b72` (2026-10-18)
- **Harness:** [`scripts/test-omp-runtime-contract-spike.sh`](../../../scripts/test-omp-runtime-contract-spike.sh)
- **Decision record:** [ADR 0002](../adr/0002-omp-runtime-contract.md)
- **ycc inventory:** worktree at `228ac6b9`: 49 skills plus `skills/_shared/{references,scripts}`, 55 agents, `ycc/rules/{common,golang,python,rust,typescript,web}`, and the packages in `ycc/settings/packages.json`.

Citation format: `path:line` is relative to the oh-my-pi repo at the pinned tag, and `src/` means `packages/coding-agent/src/`. `packages/coding-agent/CHANGELOG.md` is rotated (at `v18.12.2` it starts at 18.3.2), so older entries are cited as `CHANGELOG.md@<tag>:<line>`. Landing versions that the CHANGELOG does not state come from a binary search over release tags with `git grep` and are labeled **[tag-bisect]**. Claims that were neither run live nor read in upstream docs or source are labeled **[INFERENCE]**.

Verdict key: **native** (works as shipped for Claude Code), **adapter** (works once ycc generates an OMP-specific form), **fallback** (no OMP plugin mechanism; document a user-config or manual path), **unsupported** (no way to reach parity).

## Executive Decisions

1. **Catalog: generate a dedicated OMP tree.**
   - omp reads `.omp-plugin/marketplace.json` first and falls back to `.claude-plugin/marketplace.json` (live §1.1; `src/extensibility/plugins/marketplace/fetcher.ts:209`). Today's root Claude catalog installs as is.
   - Reusing the Claude tree still loses two things. Plugin roots with `.claude-plugin/plugin.json` and no `.omp-plugin/plugin.json` have their agent `model:` discarded (live §1.4). `${CLAUDE_PLUGIN_ROOT}` is not expanded in skill bodies (upstream §2.8).
   - ycc therefore ships `.omp-plugin/marketplace.json` pointing at generated OMP package directories. Each has `.omp-plugin/plugin.json` and a `package.json` with a unique `name`. Claude Code keeps reading `.claude-plugin/`.
2. **Hooks.** OMP never executes shell hooks and never reads `hooks/hooks.json`. Hooks run only as TypeScript/JavaScript `ExtensionAPI` factories.
   - `WorktreeCreate` (`worktree-create.sh`) is **unsupported**. OMP has no worktree-creation event.
   - herdr session reporting is an **adapter**: an extension bound to `session_start` that runs the ycc-owned `herdr-session-start.sh` logic. (The Claude-side `ycc/settings/hooks/herdr-agent-state.sh` is installed and managed by herdr itself and is not registered by ycc.)
3. **Packages.**
   - `ycc`, `ycc-mcp`, `ycc-hooks`, and `ycc-rules` become OMP packages.
   - `ycc-all` is a **fallback**: the marketplace does not resolve dependencies, so users install the parts separately.
4. **Agents, skills, rules.** These are **adapter** surfaces.
   - Discovery is native.
   - Agent tool names and models, skill-body placeholders and `/ycc:` references, `_shared` paths, and the nested Cursor rules tree with `paths:` frontmatter all need generated OMP forms.
5. **Trust.** OMP has no trust gate. Installed plugin code runs in-process with full user privileges from install onward, and MCP servers start at session start without a prompt.
6. **Minimum version.**
   - The supported floor is the tested **18.12.2**.
   - Evidence puts the hard floor at 18.2.1 (changelog and tag-bisect) and recommends 18.11.0 or later. Neither older version was run.
7. **Namespace.** Keep `ycc`. Nothing in OMP forces a rename:
   - skills are unprefixed (`/skill:<name>`);
   - commands become `ycc:<cmd>` under a plugin named `ycc`;
   - MCP servers become `<plugin>:<server>`.

---

## 1. Live-Verified Facts (`omp/18.12.2`)

All observations come from `bash scripts/test-omp-runtime-contract-spike.sh` (pass `--keep` to retain `<sandbox>/transcript.log` and `<sandbox>/logs/<label>.{stdout,stderr}`).

**Sandbox:**

- Every `omp` call runs as `env -i PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 TERM=dumb NO_COLOR=1`.
- `HOME`, `XDG_{CONFIG,DATA,STATE,CACHE}_HOME`, `XDG_RUNTIME_DIR`, and `TMPDIR` point into a per-case tree under `mktemp -d /tmp/omp-runtime-contract-spike.XXXXXX`.
- A guard aborts if `HOME` would resolve outside the sandbox or under the real home.
- Each call also runs as `bwrap --dev-bind / / --tmpfs $REAL_HOME --ro-bind <omp> <omp> --unshare-net --`. That gives a private network namespace and hides the real home, so the real `~/.omp` is unreachable. The harness fails closed if bwrap cannot create the network namespace, unless `--allow-env-i` is passed. The verified run used `sandbox=bwrap-netns`.
- Git is file-only:
  - `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_ALLOW_PROTOCOL=file`, and an empty credential helper;
  - `url.file://<bare>.insteadOf` rewrites of `https://omp-spike.invalid/{omp,claude}.git`.
- **No inference:**
  - The only model is a null `openai-completions` provider on `127.0.0.1:9`.
  - RPC sessions send only `get_available_commands`, `get_state`, and the builtin `/reload-plugins`, which answers `"agentInvoked":false`.

**Introspection surfaces that need no model:**

- `omp --mode rpc` with `get_available_commands`: skills, file commands, and extension commands, each with its `source`.
- `get_state`: the rendered system prompt with agents, rules, MCP routes, and tool devices.
- `omp ttsr list|test`, `omp plugin list --json`, `omp plugin doctor`, `omp config list|get|set|path`, and `omp agents unpack`.
- There is no `omp mcp list`; `/mcp` exists only as a slash command.

> **Per-run values:** Fixture SHAs, `<SANDBOX>` paths, and timestamps change on every run. Compare exit codes, messages, and layouts, not those literal values.

### 1.1 Marketplace and catalog

| Command                                                                                         | Exit | Key output                                                                                                                        |
| ----------------------------------------------------------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------- |
| `omp plugin marketplace add https://omp-spike.invalid/omp.git` (both catalogs, different names) | 0    | `marketplace list` shows `spike-omp`, not `spike-claude-shadow`                                                                   |
| `omp plugin marketplace add https://omp-spike.invalid/claude.git` (Claude catalog only)         | 0    | `spike-claude` added                                                                                                              |
| `omp plugin marketplace add <dir without catalog>`                                              | 1    | `Marketplace catalog not found at "<…>/.omp-plugin/marketplace.json" or "<…>/.claude-plugin/marketplace.json"`                    |
| `omp plugin discover spike-claude`                                                              | 0    | `rel-spike sub-spike npm-spike`                                                                                                   |
| `omp plugin install npm-spike@spike-claude`                                                     | 1    | `npm plugin sources are not yet supported. Use git-based sources instead.`                                                        |
| `omp plugin install sub-spike@spike-claude` (`git-subdir`)                                      | 0    | cache `spike-claude___sub-spike___0.0.2` (version from the plugin.json at the ref tip)                                            |
| `omp plugin marketplace remove spike-claude` (with `sub-spike@spike-claude` installed)          | 0    | catalog removed; `plugin list --json` still has `sub-spike@spike-claude`; registry entry, cache dir, and `node_modules` link stay |

`metadata.pluginRoot: "plugins"` combined with source `./ycc-spike` resolved to `plugins/ycc-spike`. The catalog clone lands at `~/.omp/plugins/cache/marketplaces/<name>/`.

### 1.2 Install, dry-run, layout, and package name

| Command                                                                | Exit | Key output                                                                                                          |
| ---------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------- |
| `omp plugin install --dry-run ycc-spike@spike-omp`                     | 0    | `[dry-run] Would install ycc-spike@spike-omp`; no registry, no `node_modules` link                                  |
| `omp plugin install ycc-spike@spike-omp`                               | 0    | `✔ Installed ycc-spike from spike-omp (0.0.1)`                                                                      |
| `omp plugin list --json`                                               | 0    | `"id": "ycc-spike@spike-omp"`, `"scope": "user"`, `installPath` under `cache/plugins/spike-omp___ycc-spike___0.0.1` |
| `omp plugin doctor`                                                    | 0    | `plugins_directory`, `node_modules` checks pass                                                                     |
| `omp plugin install rel-spike@spike-claude` (same `package.json#name`) | 1    | `Runtime package name "ycc-spike" conflicts with installed plugin "ycc-spike@spike-omp"`                            |
| `omp plugin install nopkg@spike-local` (no `package.json`)             | 0    | `✔ Installed nopkg from spike-local (0.0.1)`; `node_modules/nopkg` links to the cache; its skill and agent load     |

User-scope layout:

```text
~/.omp/marketplaces.json
~/.omp/plugins/cache/marketplaces/<mkt>/                         # catalog clone
~/.omp/plugins/cache/plugins/<mkt>___<plugin>___<version>/        # plugin copy (+ generated .lsp.json)
~/.omp/plugins/installed_plugins.json                            # {"version":2,"plugins":{"<id>":[…]}}
~/.omp/plugins/omp-plugins.lock.json                             # keyed by runtime package name
~/.omp/plugins/node_modules/<runtime package name> -> <cache dir>
```

- **Runtime package name:** the runtime key is `package.json#name` when it exists, else the catalog plugin name (`src/extensibility/plugins/marketplace/manager.ts:941-950`, `#resolvePluginPackageName`).
- **Settled live:** a plugin without `package.json` registers under its plugin name, and its skills and agents load.
- **Requirement:** each OMP package needs a unique runtime name. Ship a `package.json` with a distinct `name` (for example `ycc`, `ycc-mcp`, `ycc-hooks`, `ycc-rules`), or rely on distinct plugin names.

### 1.3 Component discovery (installed marketplace plugin)

| Surface                                                           | Observed                                                                                                  | Upstream                                                                       | Verdict                      |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------- |
| `skills/<n>/SKILL.md`                                             | `{"name":"skill:spike-skill","source":"skill"}`; listed in the system prompt                              | `src/discovery/claude-plugins.ts:215-257`                                      | native                       |
| `commands/*.md`                                                   | `ycc-spike:spike-cmd` for a marketplace install; unprefixed `spike-cmd` for `link`                        | `claude-plugins.ts:288-356`                                                    | native                       |
| `agents/*.md`                                                     | listed under "Available Agents" with the `(READ-ONLY; …)` label, which `tools: read, grep` produces       | `src/task/discovery.ts:122-155`                                                | native (frontmatter: §1.4)   |
| `rules/*.md` `alwaysApply: true`                                  | body injected into the system prompt                                                                      | `claude-plugins.ts:263-282`                                                    | native                       |
| `rules/*.md` `condition:` (TTSR)                                  | `ttsr list` shows `spike-ttsr [claude-plugins]`; `ttsr test 'x SPIKEFORBIDDEN y'` gives `Triggered (1)`   | `docs/rulebook-matching-pipeline.md:215-250`                                   | native                       |
| `hooks/pre/*.ts` factory                                          | its `registerCommand` command appears (`source: "extension"`)                                             | `src/extensibility/extensions/loader.ts:621-629`                               | native, TS/JS factories only |
| `hooks/pre/*.sh`                                                  | discovered as metadata; the fixture script would `touch` a marker file, and the marker stays absent       | `claude-plugins.ts:384`; `docs/hooks.md:7-12`                                  | **unsupported**              |
| `tools/*.ts`                                                      | custom tool in the system prompt                                                                          | `claude-plugins.ts:410-443`                                                    | native                       |
| `.mcp.json` with `${OMP_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_ROOT}` | both stub servers start; tools `mcp__ycc_spike_spikemcp_spikemcp_ping` and `mcp__ycc_spike_spikeclaude_…` | `claude-plugins.ts:449-536`, `:645`; `src/discovery/substitute-plugin-root.ts` | native                       |
| `package.json#omp.extensions`                                     | `/spike-ext` registered (marketplace and `link`)                                                          | `docs/extension-loading.md:55-65`                                              | native                       |
| catalog `lspServers`                                              | written to `<cache>/.lsp.json`; LSP runtime not started                                                   | `docs/marketplace.md:159-160`                                                  | native on disk               |

### 1.4 Agent `model:` dialect

The harness loads a probe extension with `-e probe.ts`. The probe calls omp's own `discoverAgents()` (internal module `@oh-my-pi/pi-coding-agent/task/discovery`) and publishes the resolved `model` as a command description, so no inference runs. The fixture agent declares `model: "@smol"`.

| Plugin root                                                         | Observed                                 |
| ------------------------------------------------------------------- | ---------------------------------------- |
| `--plugin-dir` root with `.claude-plugin/plugin.json` only          | `PROBE model-agent model=none` (dropped) |
| `--plugin-dir` root with `.omp-plugin/plugin.json`                  | `PROBE model-agent model=@smol` (kept)   |
| marketplace install of an `.omp-plugin` root without `package.json` | `PROBE model-agent model=@smol`          |

This matches `src/discovery/agent-plugin-format.ts:566-571` (`pluginUsesClaudeModelDialect`) and `src/task/discovery.ts:138-155` (`ignoreModel`). The dialect follows the plugin's manifest, not the registry that supplied the root.

Not tested live: how Claude-cased `tools:` names are normalized. Per upstream (`src/tools/builtin-names.ts:1-63`; `src/sdk.ts:4129-4130`), `Read` maps to `read`, while unknown names such as `WebFetch` and `NotebookEdit` are silently dropped. That claim is **doc-sourced**.

### 1.5 Enable, disable, reload, upgrade, uninstall

| Command                                                                                              | Exit | Key output                                                                                           |
| ---------------------------------------------------------------------------------------------------- | ---- | ---------------------------------------------------------------------------------------------------- |
| `omp plugin disable ycc-spike@spike-omp`                                                             | 0    | lock `"enabled": false`; RPC loses the skill, agent, and MCP; `ttsr list` loses the rule             |
| `omp plugin enable …` then RPC `/reload-plugins`                                                     | 0    | `Plugins reloaded.`, `"agentInvoked":false`; skill restored                                          |
| catalog-only `version` bump, `marketplace update`, `plugin upgrade`                                  | 0    | `All marketplace plugins are up to date.`                                                            |
| `.claude-plugin/plugin.json` + `package.json` bump, `marketplace update spike-omp`, `plugin upgrade` | 0    | `0.0.1 -> 0.0.2`; new cache dir `…___0.0.2`                                                          |
| `omp plugin uninstall --scope user …`                                                                | 0    | `node_modules` link removed; `installed_plugins.json` no longer lists the id; marketplace clone kept |

- **Upgrade rule:** for relative string sources, `#resolveCatalogVersion` reads `.claude-plugin/plugin.json`, then root `plugin.json`, **before** the catalog `version`. Object sources use the catalog version first (`manager.ts:555-580`). A catalog-only bump is therefore invisible to `omp plugin upgrade`.
- **Generator consequence:** an OMP package whose only manifest is `.omp-plugin/plugin.json` has no plugin-manifest version for this lookup, so the catalog `version` and then `package.json#version` decide. The generator must stamp the lockstep version into the catalog entry and `package.json` [INFERENCE from the source order; not run with an `.omp-plugin`-only fixture].
- **Restart:** per `docs/marketplace.md:80`, newly installed non-MCP tools, hooks, and extension modules need a session restart. `/reload-plugins` refreshes agents, skills, commands, and MCP. Live: `/reload-plugins` is a builtin; hot-loading of new extensions was not exercised.

### 1.6 Scopes, shadowing, overrides

| Command (cwd = git repo `proj/`)                                                     | Exit | Key output                                                                                                                    |
| ------------------------------------------------------------------------------------ | ---- | ----------------------------------------------------------------------------------------------------------------------------- |
| `omp plugin install --scope project …`                                               | 0    | `proj/.omp/plugins/{installed_plugins.json,omp-plugins.lock.json,node_modules/…}`; cache shared under `~/.omp/plugins/cache/` |
| `omp plugin list --json`                                                             | 0    | project entry `"scope": "project"`; user entry `"shadowedBy": "project"`                                                      |
| `omp plugin uninstall …` (in both scopes, no `--scope`)                              | 1    | `installed in both user and project scope. Use --scope user or --scope project`                                               |
| `omp plugin disable --scope project …`                                               | 0    | `shadowedBy` disappears; the user copy serves                                                                                 |
| `proj/.omp/plugin-overrides.json` `{"disabled":["ycc-spike"]}` + marketplace install | n/a  | rule still loaded (**no effect**)                                                                                             |
| same overrides file + `omp plugin link` install                                      | n/a  | skill and extension command disappear                                                                                         |

`plugin-overrides.json` applies only to npm/link packages (`src/extensibility/plugins/loader.ts:69-85`). The per-project kill switch for marketplace installs is `omp plugin disable --scope project`.

### 1.7 `link`, `--plugin-dir`, profiles, XDG

- **`omp plugin link <dir>`:** symlinks `~/.omp/plugins/node_modules/<name>` to the source dir, and `plugin list --json` reports it under `"npm"` with `manifest.extensions`. `link --dry-run` writes nothing.
- **`omp --plugin-dir <dir> --mode rpc`:** loads a tree with no install, so it is the developer loop. It is a root-command flag: `omp ttsr list --plugin-dir` fails with `Unknown option`.
- **Profiles:** `--profile work` or `OMP_PROFILE=work` relocates state to `~/.omp/profiles/work/{marketplaces.json,plugins/…}`. The default profile then reports `No plugins installed`.
- **XDG:** after `omp config init-xdg`, marketplace and plugin state live under `$XDG_DATA_HOME/omp/`, and `~/.omp/marketplaces.json` is absent. The agent dir stays at `~/.omp/agent`.
- **Agent dir override:** `PI_CODING_AGENT_DIR=<dir> omp config path` prints `<dir>`.
- Installers must resolve paths through omp (for example, `installPath` from `omp plugin list --json`), never hard-code `~/.omp/plugins`.

### 1.8 Cross-harness auto-import

Seeded: skills under `~/.claude`, `~/.codex`, `~/.cursor`, `~/.agents`, and `~/.config/opencode`; MCP in `~/.claude.json`, `~/.codex/config.toml`, `~/.cursor/mcp.json`, and `opencode.json`; plus native `~/.omp/agent/{skills,mcp.json}` entries that reuse a foreign name.

| `enabledProviders` | Skills                                             | MCP                                                                                           |
| ------------------ | -------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| default `[]`       | `~/.agents` + native; same-named native skill wins | native only; native `claudejson` loaded                                                       |
| `["*"]`            | + Claude, Codex, opencode skills                   | + Codex, Cursor, opencode; Claude `claudejson` shadowed by the native server of the same name |
| `["claude"]`       | + Claude only                                      | + Claude only                                                                                 |
| any                | `~/.cursor/skills` never loaded                    | n/a                                                                                           |

Foreign user-level sources are opt-in (`src/capability/index.ts:51-60`, `:356-373`; since 18.1.5, `CHANGELOG.md@v18.3.0:1200`). A Claude ycc install is therefore invisible to OMP by default. `~/.agents/skills` is on by default at priority 70, so `install.sh`'s `agents` target copies can duplicate a native OMP ycc install (§2.10).

---

## 2. Upstream Contract (`v18.12.2`)

### 2.1 Catalog

- **Location:** `.omp-plugin/marketplace.json` is preferred and `.claude-plugin/marketplace.json` is the fallback; a repo may ship both (`docs/marketplace.md:16`, `:96-98`; `fetcher.ts:209`).
- **Schema:**
  - Required: `name`, `owner.name`, `plugins`. Optional: `metadata.pluginRoot`.
  - Catalog `commands`, `agents`, `hooks`, `mcpServers`, and `strict` are metadata only (`docs/marketplace.md:127-160`).
- **Sources:**
  - `./` relative, `url`, `github`, and `git-subdir` install.
  - `npm` is parsed but rejected at install (`docs/marketplace.md:112-217`).
  - A direct `.json` catalog URL cannot use relative sources (`:96`).
- **Names:** ASCII letters, digits, `-`, and `.`; start and end alphanumeric; at most 64 characters; case-insensitive collisions rejected. Plugin IDs are `name@marketplace` (`docs/marketplace.md:18`, `:250-259`).

### 2.2 Plugin roots

The `claude-plugins` provider (priority 70, `claude-plugins.ts:32-34`) reads each installed root:

- `.claude-plugin/plugin.json` for component paths;
- `skills/`, `commands/`, `rules/*.{md,mdc}` (non-recursive, `src/discovery/helpers.ts:611-618`), `hooks/pre|post/`, `tools/`, and `.mcp.json`.

Also:

- **MCP manifest:** `.omp-plugin/plugin.json` takes precedence over `.claude-plugin/plugin.json` (`claude-plugins.ts:465-473`).
- **Agents:** loaded by task discovery (`src/task/discovery.ts:138-155`).
- **Extension packages:** marketplace roots are symlinked into `<scope>/plugins/node_modules/` and load `package.json#omp.extensions` (`docs/plugin-manager-installer-plumbing.md:20-26`, `:92-104`).
- **Dependencies:** no marketplace code reads a plugin-manifest `dependencies` field. The only `dependencies` reads, in `marketplace/manager.ts:1022-1045`, concern npm `package.json`.

### 2.3 Extensions (`ExtensionAPI`)

- **Factory:** a module default-exports `(pi: ExtensionAPI) => void | Promise<void>` (`docs/extensions.md:17-36`).
- **API** (`docs/extensions.md:114-131`, `:457-600`, `:885-894`):
  - registration: `on`, `registerTool`, `registerCommand`, `registerShortcut`, `registerFlag`, `registerProvider`;
  - actions: `sendMessage`, `exec`, `setModel`;
  - events: `session_start`, `session_shutdown`, `session_stop`, `tool_call` (pre, may block or rewrite), `tool_result` (post), `before_subagent_spawn`;
  - UI: `ctx.ui.setStatus` and `setWidget` render. `setFooter` and `setHeader` are currently no-ops in the UI controller (`docs/extensions.md:883-886`).
- **Install validation:** each declared extension must import and initialize, or the install rolls back (`docs/plugin-manager-installer-plumbing.md:119`).

### 2.4 Hooks

- Hook files under `hooks/pre|post/` load only as `.ts`/`.js` extension factories that call `pi.on(...)`. The directory and basename are metadata (`docs/hooks.md:10`, `:35-93`; `extensions/loader.ts:621-629`).
- `git grep -F hooks.json -- packages/ docs/` and `git grep -F WorktreeCreate -- packages/ docs/` both return no match (exit 1).
- The extension event list (`docs/extensions.md:451-605`) has no worktree-creation event. Task isolation creates its own workspaces internally (`docs/tools/task.md:136-137`).

### 2.5 MCP

- **Names:** marketplace servers are named `<plugin>:<server>` (`claude-plugins.ts:645`). Tool names are `mcp__<server>_<tool>`, and Claude's `mcp__a__b` spelling is mapped back (`src/mcp/tool-bridge.ts:469-483`).
- **Placeholders:** `${CLAUDE_PLUGIN_ROOT}` and `${OMP_PLUGIN_ROOT}` are substituted in `command`, `args`, and `cwd`. `${VAR}` and `${VAR:-default}` in `env` expand at discovery (`claude-plugins.ts:550-571`, `:646-690`).
- **Timeouts:** `timeout` values below 1000 ms are ignored with a warning (`docs/mcp-config.md:116`).
- **Precedence:** the first definition of a server name wins: native, then extension packages, then Claude, then Agent Plugins, then marketplace plugins and Codex, and so on. User `disabledServers` and `enabledServers` override every source (`docs/mcp-config.md:450-514`).

### 2.6 Task agents and model roles

- **Frontmatter:**
  - Required: `name`, `description`, and a body.
  - Optional: `tools`, `spawns`, `model` (list; `@role` aliases), `thinking-level`, `output`, `blocking`, `structured`, `autoload-skills`, `read-summarize`, `prewalk`, `advisor`.
  - Unknown keys such as `color` are ignored (`docs/task-agent-discovery.md:25-49`; `helpers.ts:315-380`).
- **Discovery order:** project `.omp/agents`, user `.omp/agents`, extension-package `agents/`, marketplace `agents/` (project scope first), then bundled agents; the first name wins. `.claude/agents` is never loaded (`docs/task-agent-discovery.md:148-164`).
- **Model precedence:** `task.agentModelOverrides[name]`, then frontmatter `model`, then the parent model; role aliases expand through `modelRoles` (`docs/task-agent-discovery.md:224-230`).
- **Roles:** `default`, `smol`, `slow`, `vision`, `plan`, `commit`, `tiny`, `memory`, `task`, and `advisor`, plus custom names (`docs/models.md:681-704`).
- **No plugin channel for settings:** no plugin surface sets `modelRoles` or other settings, which come only from the user, project, and `--config` layers (`docs/config-usage.md:154-196`; `claude-plugins.ts:707-753`).
- **Approval:** subagents run with `tools.approvalMode = yolo` (`docs/approval-mode.md:176`).

### 2.7 Rules

- **Fields:** `name` (file stem; first wins), `globs`, `alwaysApply`, `description`, `condition` (TTSR regex), `astCondition`, `scope`, `agents`, `enabled`. There is no `paths` key (`helpers.ts:210-245`; `docs/rulebook-matching-pipeline.md:33-88`).
- **Buckets:**
  - a rule with a TTSR condition goes to TTSR;
  - else an `alwaysApply` rule is injected in full;
  - else a rule with a `description` goes to the rulebook (`rule://`).
- **`globs`:** advisory for the rulebook and a path gate for TTSR (`:215-250`).

### 2.8 Skills

- **Layout:** `<root>/<name>/SKILL.md`, one level deep (`docs/skills.md:31`).
- **Frontmatter:**
  - `disable-model-invocation` normalizes to `disableModelInvocation`. Together with `hide`, it keeps a skill out of the prompt listing while `/skill:<name>` and `skill://` still work (`src/extensibility/skills.ts:265`; `src/system-prompt.ts:938`; since 15.9.0).
  - `allowed-tools` and `argument-hint` carry no semantics (`docs/skills.md:50-61`).
- **Names:** plugin skills are not namespaced; the command form is `/skill:<name>` (`claude-plugins.ts:246-250`).
- **Paths:** `skill://<name>/<rel>` rejects `..` (`docs/skills.md:180-217`).
- **Placeholders:** `${CLAUDE_PLUGIN_ROOT}` is **not** expanded in skill bodies. `substitutePluginRoot` is called only by the MCP loaders (`git grep -c CLAUDE_PLUGIN_ROOT packages/coding-agent/src` matches only `discovery/{claude-plugins,omp-plugins,substitute-plugin-root}.ts`).
- **Precedence:** native 100 > omp-plugins 90 > claude 80 > agent-plugins 75 > claude-plugins/agents/codex 70 > opencode 55. Identical copies collapse, and differing copies are namespaced `<plugin>/<name>` (`docs/skills.md:91-135`).

### 2.9 Settings, status line

- **Settings:** OMP settings live in `~/.omp/agent/config.yml` and project layers. Claude `settings.json` is read only as a foreign settings source (`src/discovery/claude.ts:530-560`).
- **Status line:** a built-in `statusLine.*` preset and segment configuration with no command-backed renderer (`docs/settings.md:864-884`). Extensions can render through `ctx.ui.setStatus` and `setWidget`; `setFooter` is a no-op (`docs/extensions.md:883-894`).

### 2.10 Security and trust model

- **No sandbox:** plugin and extension code runs in-process, unsandboxed, as trusted code (`docs/plugin-manager-installer-plumbing.md:245-249`; `docs/extension-loading.md:330-333`).
- **No trust prompt:** `isProjectTrusted()` always returns `true` (`docs/extensions.md:362`). There is no per-plugin trust prompt or hash pinning (unlike Codex `trustStatus`).
- **Controls:**
  - `--trusted-extension <abs-file>` (since 17.2.10);
  - `--no-extensions`;
  - `disabledExtensions`;
  - `enabledProviders`/`disabledProviders`;
  - MCP `disabledServers` (`docs/extension-loading.md:110-165`; `docs/mcp-config.md:450-465`).
- **Approval:** the default `tools.approvalMode` is `yolo`. Undeclared tools default to the `exec` tier and MCP tools to `write`; subagents are forced to yolo (`docs/approval-mode.md:12`, `:24`, `:176`).
- **Input hygiene:**
  - npm and git specs are checked for shell metacharacters;
  - source and component paths are containment-checked;
  - inline git credentials are stripped (`docs/plugin-manager-installer-plumbing.md:235-243`; `claude-plugins.ts:196-201`; `CHANGELOG.md@v18.12.2:514`).
- **No lock:** there is no cross-process lock on `omp-plugins.lock.json` (`docs/plugin-manager-installer-plumbing.md:231`).
- **Live:**
  - Project-scope installs, project overrides, and project-level foreign configs load without a prompt.
  - Plugin MCP stdio servers were spawned at `--mode rpc` session start with no confirmation.

**Trust model for ycc:** installing or enabling an OMP ycc package grants full user privileges to every extension, tool, and MCP command it ships. Each of those must therefore be side-effect-free at load, must not read secrets beyond its declared `env` placeholders, and must fail closed when its external dependency (herdr, a token) is absent. Install docs must say so, because no OMP prompt will.

### 2.11 Landing versions

| Needed feature                                                                                    | Landed              | Evidence                                                |
| ------------------------------------------------------------------------------------------------- | ------------------- | ------------------------------------------------------- |
| Marketplace system, `git-subdir`, `/reload-plugins`, marketplace MCP with `${CLAUDE_PLUGIN_ROOT}` | 13.17.0             | `CHANGELOG.md@v18.0.0:7805`, `:7813`, `:7815`, `:7834`  |
| Project scope                                                                                     | 13.17.2             | `CHANGELOG.md@v18.0.0:7754`                             |
| `disable-model-invocation` hides skills                                                           | 15.9.0              | `CHANGELOG.md@v18.0.0:5045`                             |
| Named profiles                                                                                    | 15.13.1             | `CHANGELOG.md@v18.0.0:3788`                             |
| `.omp-plugin/marketplace.json` preferred                                                          | 16.0.1 [tag-bisect] | commit `587f68a899`; `fetcher.ts` at v16.0.1 vs v16.0.0 |
| Hook factories run                                                                                | 16.0.3              | `CHANGELOG.md@v18.0.0:3555`                             |
| Marketplace installs register `node_modules` + `omp.extensions`                                   | 16.1.17             | `CHANGELOG.md@v18.0.0:2955`                             |
| Marketplace `rules/` discovered                                                                   | 18.0.5              | `CHANGELOG.md@v18.3.0:1587`                             |
| Foreign user sources opt-in                                                                       | 18.1.5              | `CHANGELOG.md@v18.3.0:1200`                             |
| omp-installed skills and agents bypass the Claude opt-in gate                                     | 18.1.9 / 18.1.14    | `CHANGELOG.md@v18.3.0:1077`, `:987`                     |
| OMP-native plugin agents keep `model:`; manifest `mcpServers`; install `--dry-run`                | 18.2.1              | `CHANGELOG.md@v18.3.0:447`, `:652`, `:522`              |
| `link --dry-run` stops writing                                                                    | 18.4.1              | `CHANGELOG.md@v18.12.2:1462`                            |
| TUI `/plugins` live refresh; Bun-less installs; plugin.json version precedence                    | 18.11.0             | `CHANGELOG.md@v18.12.2:347-350`                         |

---

## 3. Component → Verdict Matrix

| ycc component                                                                                                                                                                                                                        | Claude form today                                                                                 | OMP surface                                                   | Verdict                                           | Required work                                                                                                                                                                                                                                                                                                   | Evidence         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| Catalog                                                                                                                                                                                                                              | root `.claude-plugin/marketplace.json` (`./ycc`, `./packages/claude/{ycc-mcp,ycc-hooks,ycc-all}`) | `.omp-plugin/marketplace.json`                                | **adapter**                                       | Generate an OMP catalog with relative sources to generated OMP packages; no `npm` sources; set the lockstep `version` per entry.                                                                                                                                                                                | §1.1, §1.4, §2.1 |
| Plugin manifest                                                                                                                                                                                                                      | `ycc/.claude-plugin/plugin.json`                                                                  | `.omp-plugin/plugin.json` + `package.json`                    | **adapter**                                       | `.omp-plugin/plugin.json` keeps agent models and wins the MCP lookup. `package.json` gives a unique runtime name and the lockstep version, and carries `omp.extensions` where adapters ship.                                                                                                                    | §1.2, §1.4, §1.5 |
| Skills, auto-invocable (40 of 49)                                                                                                                                                                                                    | `skills/<n>/SKILL.md`                                                                             | plugin skill scan                                             | **native** discovery / **adapter** bodies         | Rewrite `${CLAUDE_PLUGIN_ROOT}` references (96 files) and `/ycc:<name>` references (65 files under `ycc/skills`: 26 `SKILL.md` plus references, templates, and scripts).                                                                                                                                        | §1.3, §2.8       |
| Skills, hidden/manual (9 with `disable-model-invocation: true`: backport, blueprint, bundle-author, bundle-release, clean, compatibility-audit, git-cleanup, hooks-workflow, releaser; `bundle-author` also `user-invocable: false`) | hidden from the model                                                                             | `disableModelInvocation` / `hide`                             | **native**                                        | Keep the key. OMP has no `user-invocable: false` equivalent, so `bundle-author` stays reachable via `/skill:` [INFERENCE from the recognized-key list].                                                                                                                                                         | §2.8             |
| Skill `allowed-tools`, `argument-hint`                                                                                                                                                                                               | Claude permission and UX hints                                                                    | none                                                          | **unsupported** (ignored, harmless)               | None; approval comes from `tools.approvalMode`.                                                                                                                                                                                                                                                                 | §2.8, §2.10      |
| `skills/_shared/` (`references/`, `scripts/`)                                                                                                                                                                                        | reached via `${CLAUDE_PLUGIN_ROOT}/skills/_shared/…`                                              | not a skill; `skill://` rejects `..`                          | **adapter**                                       | Rewrite paths to the package root the generator controls, or vendor into each skill.                                                                                                                                                                                                                            | §2.8             |
| Commands                                                                                                                                                                                                                             | none for Claude (Cursor generates thin wrappers)                                                  | `commands/*.md` → `/ycc:<cmd>`                                | **adapter** (optional)                            | Thin wrappers restore `/ycc:<name>`; otherwise users run `/skill:<name>`.                                                                                                                                                                                                                                       | §1.3             |
| Agents (55)                                                                                                                                                                                                                          | `agents/*.md`: Claude `tools`; `model` of `opus`, `sonnet`, or `inherit`; `color`                 | plugin `agents/` → task agents                                | **adapter**                                       | Ship under `.omp-plugin/plugin.json`; map `model` to `@role` aliases; map tool names to OMP IDs (`WebSearch` → `web_search`; `WebFetch` and `NotebookEdit` → `read` and `edit`, or drop); re-mint MCP tool names for `ycc-mcp:<server>`. `color` is ignored.                                                    | §1.4, §2.6       |
| Rules `common/`                                                                                                                                                                                                                      | Cursor source tree, `paths:` frontmatter                                                          | flat `rules/*.{md,mdc}`, `globs:`                             | **adapter**                                       | Flatten under unique names; `paths` → `globs`; keep `alwaysApply` (only `common/security.md`, `common/git-workflow.md`) and `description`; drop `README.md`.                                                                                                                                                    | §1.3, §2.7       |
| Rules `golang/`, `python/`, `rust/`, `typescript/`, `web/`                                                                                                                                                                           | same                                                                                              | same                                                          | **adapter**                                       | Same as `common/`; prefix names (for example `golang-coding-style`), because `coding-style.md` appears six times and names dedupe first-wins.                                                                                                                                                                   | §2.7             |
| `ycc/settings/rules/{CLAUDE,AGENTS}.md`                                                                                                                                                                                              | `install.sh` instructions                                                                         | `AGENTS.md` discovery via the `.agents` and native providers  | **fallback**                                      | Not plugin-shippable as context; keep on the installer, or convert key guidance to `alwaysApply` rules [INFERENCE].                                                                                                                                                                                             | §2.9             |
| `ycc/settings/rules/README.md`                                                                                                                                                                                                       | maintainer doc for the instruction files                                                          | none                                                          | **n/a**                                           | Not a runtime payload.                                                                                                                                                                                                                                                                                          | —                |
| herdr session reporting (ycc-owned `ycc/settings/cursor/herdr-session-start.sh`, Cursor `sessionStart`)                                                                                                                              | not registered on Claude: Claude ycc hooks register only `WorktreeCreate`                         | extension `session_start` + `pi.exec`                         | **adapter**                                       | TS extension shim on `session_start` only. It must synthesize the stdin payload the script reads (`hook_event_name`, `session_id`). No shutdown binding: the ycc script has no end-of-session action, and a shutdown report is [INFERENCE] about herdr's API. herdr acceptance of an OMP source is [INFERENCE]. | §1.3, §2.3, §2.4 |
| `ycc/settings/hooks/herdr-agent-state.sh`                                                                                                                                                                                            | herdr-managed Claude integration (`# installed by herdr`, `HERDR_INTEGRATION_ID=claude`)          | none                                                          | **n/a** (not ycc-owned)                           | herdr ships its own integrations; ycc does not port it.                                                                                                                                                                                                                                                         | —                |
| `worktree-create.sh` (`WorktreeCreate`)                                                                                                                                                                                              | `hooks/hooks.json`                                                                                | none                                                          | **unsupported**                                   | No `hooks.json` reader, no worktree event, and `.sh` hooks never run. OMP's task isolation creates its own workspaces.                                                                                                                                                                                          | §1.3, §2.4       |
| `ycc-mcp` `.mcp.json`                                                                                                                                                                                                                | nested `mcpServers`; stdio + http; `${XERO_*}` env                                                | plugin MCP loader                                             | **native**                                        | Servers become `ycc-mcp:<server>`; first name wins against the user's own configs; agent allowlists need the new names.                                                                                                                                                                                         | §1.3, §2.5       |
| `ycc/settings/models.json`, model roles                                                                                                                                                                                              | `settings.json` `model` / `CLAUDE_CODE_SUBAGENT_MODEL`                                            | `modelRoles`, `task.agentModelOverrides` in user `config.yml` | **fallback** (pins) / **adapter** (agent `@role`) | No plugin channel sets roles. Document the user config; generated agents carry role aliases.                                                                                                                                                                                                                    | §1.4, §2.6       |
| `ycc/settings/settings.json` (env, permissions, hooks, `enabledPlugins`, statusLine)                                                                                                                                                 | Claude user settings                                                                              | OMP `config.yml`                                              | **fallback**                                      | Not plugin-shippable. Document or generate an opt-in `config.yml` snippet.                                                                                                                                                                                                                                      | §2.9             |
| Status line (`statusline-command.sh`)                                                                                                                                                                                                | `statusLine: {type:"command"}`                                                                    | `statusLine.*` presets; extension UI                          | **adapter**                                       | Port as an extension rendering via `ctx.ui.setStatus` or `setWidget`. `setFooter` is a no-op. There is no command-backed status line.                                                                                                                                                                           | §2.3, §2.9       |
| Status-bar mod (`ycc/mods/status-bar`, `register.tsx`, `ycc-mods`)                                                                                                                                                                   | Claude Code mod API                                                                               | `ExtensionAPI` (`setStatus`, `setWidget`)                     | **unsupported** as is / **adapter** (rewrite)     | A different module API. Out of the `ycc` lockstep; port only if wanted, rendering via `setStatus` or `setWidget`.                                                                                                                                                                                               | §2.3             |
| Package `ycc`                                                                                                                                                                                                                        | `./ycc`                                                                                           | generated OMP package                                         | **adapter**                                       | Skills, agents, `_shared`, optional commands.                                                                                                                                                                                                                                                                   | rows above       |
| Package `ycc-mcp`                                                                                                                                                                                                                    | `./packages/claude/ycc-mcp`                                                                       | generated OMP package                                         | **native** content / **adapter** packaging        | Copy `.mcp.json`; add `.omp-plugin/plugin.json` and `package.json`.                                                                                                                                                                                                                                             | §1.3, §2.5       |
| Package `ycc-hooks`                                                                                                                                                                                                                  | `./packages/claude/ycc-hooks` (`WorktreeCreate` only)                                             | generated OMP extension package                               | **adapter**                                       | `package.json#omp.extensions` carrying the herdr `session_start` shim only; `WorktreeCreate` dropped. Needs a restart after install.                                                                                                                                                                            | §1.5, §2.3       |
| Package `ycc-rules`                                                                                                                                                                                                                  | Cursor only                                                                                       | generated OMP package with flat `rules/`                      | **adapter**                                       | See the rules rows.                                                                                                                                                                                                                                                                                             | §2.7             |
| Package `ycc-all`                                                                                                                                                                                                                    | Claude meta plugin with `dependencies`                                                            | none                                                          | **fallback**                                      | OMP does not read dependencies. Omit it from the OMP catalog and document installing `ycc`, `ycc-mcp`, `ycc-hooks`, and `ycc-rules` separately.                                                                                                                                                                 | §2.2             |
| LSP / DAP                                                                                                                                                                                                                            | none                                                                                              | catalog `lspServers` / `dapAdapters`                          | n/a                                               | ycc ships none.                                                                                                                                                                                                                                                                                                 | §1.3             |
| Package `ycc-agents`                                                                                                                                                                                                                 | deferred to v7 on Claude (ADR 0001)                                                               | none                                                          | **n/a**                                           | Not built for any runtime yet; agents ship inside `ycc` on OMP. Revisit with the v7 split.                                                                                                                                                                                                                      | ADR 0001         |
| Package `@yandy-r/ycc-opencode`                                                                                                                                                                                                      | opencode npm plugin (V2 `setup`)                                                                  | marketplace `npm` source                                      | **n/a**                                           | opencode-specific API, and OMP rejects `npm` marketplace sources at install.                                                                                                                                                                                                                                    | §1.1, §2.1       |
| Package `installer-fallback`                                                                                                                                                                                                         | `install.sh` file copy per runtime                                                                | user and project config layers                                | **fallback**                                      | Map each payload to its row above: rules and instructions → the rules and `AGENTS.md` rows; settings → a `config.yml` snippet; statusline → the extension adapter. No OMP plugin form.                                                                                                                          | rows above       |
| `ycc/settings/cursor/hooks.json`, `herdr-session-start.sh`                                                                                                                                                                           | Cursor `sessionStart` package source                                                              | extension `session_start`                                     | **adapter** (source of the herdr shim)            | See the herdr row; OMP does not read `hooks.json`.                                                                                                                                                                                                                                                              | §2.4             |
| `ycc/settings/cursor/cli-config.json`                                                                                                                                                                                                | Cursor CLI settings                                                                               | none                                                          | **n/a**                                           | Cursor-only settings.                                                                                                                                                                                                                                                                                           | —                |
| `ycc/settings/cursor/select-mcp.py`                                                                                                                                                                                                  | Cursor helper that merges bundled MCP servers into a project `mcp.json`                           | plugin MCP loader                                             | **n/a**                                           | OMP loads the package `.mcp.json` directly; users turn servers off with `disabledServers`.                                                                                                                                                                                                                      | §2.5             |
| `mcp-configs/mcp.json`                                                                                                                                                                                                               | source of the `ycc-mcp` server set                                                                | plugin `.mcp.json`                                            | **native** (input to `ycc-mcp`)                   | The generator copies it into the OMP `ycc-mcp` package.                                                                                                                                                                                                                                                         | §1.3, §2.5       |
| `ycc/evals/` (`behavior`, `policy`, `trigger`)                                                                                                                                                                                       | maintainer eval suites                                                                            | none                                                          | **n/a**                                           | Not a runtime payload; never shipped in a package.                                                                                                                                                                                                                                                              | —                |

---

## 4. Minimum Supported Version

- **Tested:** `omp 18.12.2` only. The harness rejects older versions.
- **Hard floor (evidence only): 18.2.1.** It is the first release with all of:
  - marketplace rules (18.0.5);
  - omp-installed skills and agents without the Claude opt-in (18.1.9 / 18.1.14);
  - OMP-native agents keeping `model:` and manifest `mcpServers` (18.2.1);
  - the install `--dry-run` preview (18.2.1).
- **Recommended: 18.11.0 or later.** It adds TUI `/plugins` live refresh, Bun-less installs, and plugin.json version precedence for upgrades. 18.4.1 fixes `link --dry-run` writes.
- **Decision (ADR 0002):** support **`>=18.12.2`** until an older binary passes this harness. 18.2.1 and 18.11.0 are recorded as evidence, not as a claim.

## 5. Open Questions and Gaps

- **Not exercised live:**
  - real network installs (GitHub `owner/repo`, direct-catalog URLs, `omp install <npm-spec>`);
  - `marketplace.autoUpdate`;
  - the TUI `/marketplace` and `/plugins`;
  - DAP and LSP runtime startup;
  - hot-reload of newly installed extensions.
- Normalization of Claude-cased agent `tools:` names is doc-sourced (§1.4).
- herdr acceptance of an OMP-originated `session_start` report, and whether herdr's API has a shutdown report [INFERENCE]; needs herdr-side confirmation.
- Whether to generate `commands/` wrappers for `/ycc:<name>` parity, or document `/skill:<name>`.
- Dedupe policy when both `install.sh`'s `agents` target (`~/.agents/skills`) and the OMP ycc package are present (§1.8, §2.8).
- Upgrade detection for `.omp-plugin`-only packages relies on the catalog `version` (§1.5) [INFERENCE]; verify in the generator's live smoke.
- The probe in §1.4 imports an internal omp module (`task/discovery`). If that path moves, the harness case fails loudly instead of passing silently.

## 6. Reproduction

```bash
bash scripts/test-omp-runtime-contract-spike.sh          # sandbox removed on exit
bash scripts/test-omp-runtime-contract-spike.sh --keep   # retain transcript.log and logs/
OMP_BIN=/abs/path/to/omp bash scripts/test-omp-runtime-contract-spike.sh
bash scripts/test-omp-runtime-contract-spike.sh --allow-env-i   # weaker sandbox when bwrap netns is unavailable
```

Requirements: `omp >= 18.12.2`, `git`, `python3`, `timeout`, and `bwrap` with a working `--unshare-net`. Without it the harness exits 1 (`refusing to run without network/home isolation`). `--allow-env-i` overrides that and runs with `sandbox=env-i`, which has no network namespace and does not hide the real home; only the `env -i` HOME guard remains.
