# YAN-1176 / YAN-1291 live probes (omp 18.12.5)

This is the evidence log for [`feature-spec.md`](feature-spec.md). Every probe ran against the installed
`omp/18.12.5` (`~/.local/bin/omp`, an ELF binary) inside a throwaway sandbox at `/tmp/yan1176-exp`. The
upstream source is at tag `v18.12.5` (commit `d5cd750e41fede277f9eb933455da92a0738915e`, cloned to
`/tmp/omp-src-18125`). Upstream paths are relative to the repo root; `src/` means
`packages/coding-agent/src/`.

## Sandbox

The wrapper (`run.sh`) has the same shape as `scripts/test-omp-native-packages.sh`:

```bash
bwrap --dev-bind / / --tmpfs "$HOME" --ro-bind "$OMP" "$OMP" --unshare-net --chdir "$cwd" -- \
  env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp/yan1176-exp/home XDG_CONFIG_HOME=… XDG_DATA_HOME=… \
  XDG_STATE_HOME=… XDG_CACHE_HOME=… TMPDIR=… GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  timeout -k 5 90 "$OMP" "$@"
```

- **Isolation.** The real home is hidden behind a tmpfs and there is no network. The model is a null
  provider at `127.0.0.1:9`, and no prompt was ever sent. The real `~/.omp` was never read or written.
- **Install.** `generate_omp_packages.py --export /tmp/yan1176-exp/export`, then
  `omp plugin marketplace add <export>`, then `omp plugin install ycc@ycc`, `ycc-mcp@ycc` and
  `ycc-rules@ycc`. All three are user scope at 6.0.0.
- **Probe.** An extension loaded with `-e`. One RPC session sends `get_available_commands` and
  `get_state`. It imports OMP's own loaders:
  - `discovery.loadCapability(id)` for `skills`, `rules`, `mcps`, `slash-commands`, `hooks`,
    `extension-modules`, `tools`, `prompts` and `context-files`;
  - `extensibility/skills.loadSkills` (final names and collision warnings);
  - `task/discovery.discoverAgents`.

  It reports each provider's winners and its `_shadowed` losers.

- **Other targets' files.** These came from the repo's own slice installer, with
  `HOME=/tmp/yan1176-exp/home`:
  - `scripts/install_slices.py install --target <t> --slice skills` for agents, claude, codex,
    cursor and opencode;
  - `--slice agents` for claude, opencode and cursor;
  - `--slice commands` for opencode and cursor;
  - copies of the Claude, Codex and opencode `AGENTS.md`/`CLAUDE.md` rules;
  - `mcp-configs/mcp.json` copied into `~/.claude.json`, `~/.cursor/mcp.json` and
    `~/.codex/config.toml` (URL servers only).

  A Claude marketplace install was simulated as `~/.claude/plugins/installed_plugins.json`
  (`ycc@ycc`, `ycc-mcp@ycc`) pointing at copies of `ycc/` and `packages/claude/ycc-mcp/`.

- **Gotcha.** Symlinks into the real checkout dangle inside bwrap, because the home tmpfs hides
  them. Fixtures must be copies, or the checkout must be `--ro-bind`'d the way
  `test-omp-install-lifecycle.sh` does it.

## Results

Labels match `/tmp/yan1176-exp/out/<label>.json`. Counts are the final loaded set.

| Label | Setup                                                                                              | Skills                                                                                                                                                                                              | Commands                                                                                        | Agents                                                                                                              | MCP                                                                                                                                                                                       | Other                                                                                                                                                                                  |
| ----- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A     | OMP packages only                                                                                  | 50, all `claude-plugins:user` (the omp registry). 0 collision warnings                                                                                                                              | 49 `ycc:<x>` and 50 `skill:<x>`                                                                 | 55 from the ycc cache                                                                                               | 9 `ycc-mcp:*`. Shadowed: `ycc-mcp:linear-personal`                                                                                                                                        | 31 `ycc-*` rules plus 26 built-in. Prompt is 21 350 chars                                                                                                                              |
| B     | A + every other target's files, default `enabledProviders: []`                                     | **91**: 50 from ycc, plus **41 `agents/<name>` aliases** from `~/.agents/skills`. 8 identical copies are dropped silently (the `*-patterns`/`*-testing` language skills). **41 collision warnings** | `skill:` 50 → **91**                                                                            | 55 (ycc only)                                                                                                       | Same as A. Foreign MCP files are not read                                                                                                                                                 | Prompt is **24 922 chars (+17 %)**. Rules unchanged                                                                                                                                    |
| C     | B + `enabledProviders: ["*"]`                                                                      | **218**. `~/.claude/skills` (Claude, priority 80) takes 49 bare names. ycc becomes `ycc/<name>` (41), plus `codex/` (49), `agents/` (39) and `opencode/` (39). **168 warnings**                     | 98 file commands: 49 `ycc:<x>` **plus 49 bare opencode commands** (`plan`, `implement-plan`, …) | 55 (ycc only). `~/.claude/agents`, `~/.codex/agents`, `~/.cursor/agents` and `~/.config/opencode/agents` never load | Winners are 9 `<name>@claude` from `~/.claude.json`. **All `ycc-mcp:*` are shadowed** as equivalent connections, and so are every Codex and Cursor copy. Each server is still loaded once | Context files: native `<agentDir>/AGENTS.md` wins. `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md` and opencode `AGENTS.md` are shadowed, so there is one copy in the prompt               |
| L/W   | A + Claude plugin registry `ycc@ycc`, with `enabledProviders` `[]` / `["claude"]`                  | ycc 50 from the **omp** cache. The Claude cache `ycc@ycc` is dropped: OMP's registry is authoritative per plugin id (`src/discovery/helpers.ts:1355-1360`)                                          | 49 `ycc:`                                                                                       | 55 from omp                                                                                                         | `ycc-mcp:*` from omp                                                                                                                                                                      | No duplicate from a Claude **plugin** install                                                                                                                                          |
| T     | L with omp `ycc@ycc` uninstalled, `["claude"]`                                                     | Claude plugin ycc (42) + `~/.claude/skills` (49) + agents (39)                                                                                                                                      | 0 `ycc:`                                                                                        | 55 from the **Claude** cache                                                                                        | n/a                                                                                                                                                                                       | The fallback works once the native package is gone                                                                                                                                     |
| D     | B + project `.omp/skills/plan` + project `.claude/skills/clean`                                    | Bare `plan` is native:project; bare `clean` is claude:project. The ycc copies become `ycc/plan` and `ycc/clean`                                                                                     | –                                                                                               | –                                                                                                                   | Project `.mcp.json` `projstub` loaded (`mcp-json` provider)                                                                                                                               | Project resources outrank the user plugin                                                                                                                                              |
| E     | B + `omp plugin install --scope project ycc@ycc`                                                   | 91 (50 `claude-plugins:project` + 41 `agents/`). The user install is `[shadowed]` in `plugin list`                                                                                                  | 49 `ycc:`                                                                                       | 55 **project**                                                                                                      | –                                                                                                                                                                                         | User and project collapse to one copy                                                                                                                                                  |
| F/G   | E, then `plugin disable --scope project`, then `uninstall --scope project`                         | Back to B (the user copy serves)                                                                                                                                                                    | 49                                                                                              | 55 user                                                                                                             | –                                                                                                                                                                                         | The project keeps the omp residue `.omp/plugins/{installed_plugins.json,omp-plugins.lock.json,node_modules/}`, which shows as untracked in `git status`                                |
| H     | G + `uninstall --scope user ycc@ycc`                                                               | 49 `agents:user`, with bare names and 0 aliases                                                                                                                                                     | 0 `ycc:`                                                                                        | 0                                                                                                                   | –                                                                                                                                                                                         | Prior state restored                                                                                                                                                                   |
| I     | A + `install_slices.py remove --target agents --slice skills`                                      | 50 ycc, 0 warnings, 0 shadowed                                                                                                                                                                      | 49                                                                                              | 55                                                                                                                  | –                                                                                                                                                                                         | Removing the agents copies restores single-load                                                                                                                                        |
| J     | B with `--profile work`                                                                            | 49 `agents:user` only                                                                                                                                                                               | 0 `ycc:`                                                                                        | –                                                                                                                   | 0                                                                                                                                                                                         | Plugins are per profile. `~/.agents/skills` is shared by every profile                                                                                                                 |
| —     | `PI_CODING_AGENT_DIR=/tmp/…/altagent`                                                              | –                                                                                                                                                                                                   | –                                                                                               | –                                                                                                                   | –                                                                                                                                                                                         | `omp config path` prints the alt dir, but `omp plugin list` still lists the default ycc installs. The plugins dir follows the config root, not the agent dir (`utils/src/dirs.ts:704`) |
| K     | User `~/.claude/hooks/` (ycc `*.sh` copies) + `~/.claude/settings.json` SessionStart hook, `["*"]` | –                                                                                                                                                                                                   | –                                                                                               | –                                                                                                                   | –                                                                                                                                                                                         | Neither ran. `hooks` capability is empty for user Claude hooks. OMP reads only `hooks/{pre,post}/*.ts`                                                                                 |
| M     | B + `skills.ignoredSkills: ["agents/*"]`                                                           | 50 ycc, 0 `agents/` aliases, **0 warnings**. A foreign `~/.agents/skills/my-own` still loads                                                                                                        | `skill:` 50                                                                                     | 55                                                                                                                  | –                                                                                                                                                                                         | `omp skill list` stderr is empty                                                                                                                                                       |
| M′    | B + `skills.ignoredSkills: ["agents/plan","agents/clean"]`, then `plugin disable ycc@ycc`          | `agents/plan` hidden, bare `plan` from ycc. With ycc disabled, bare `plan` comes from `~/.agents/skills`                                                                                            | –                                                                                               | –                                                                                                                   | –                                                                                                                                                                                         | **Self-heals**: the ignore matches only the namespaced alias                                                                                                                           |
| V     | C + project `.omp/skills/plan` + `ignoredSkills: ["{agents,claude,codex,opencode,ycc}/plan", …]`   | Exactly one `plan` (native:project) and one `clean` (claude:user). No warnings                                                                                                                      | –                                                                                               | –                                                                                                                   | –                                                                                                                                                                                         | Brace globs work (Bun.Glob)                                                                                                                                                            |
| —     | B + project `.omp/config.yml` `skills: {ignoredSkills: [foo]}`                                     | 41 `agents/` aliases return                                                                                                                                                                         | –                                                                                               | –                                                                                                                   | –                                                                                                                                                                                         | **Arrays replace across layers**: a project list drops the user list                                                                                                                   |
| O     | B + `skills.enableAgentsUser: false`                                                               | 50 ycc. `my-own` is also gone                                                                                                                                                                       | –                                                                                               | –                                                                                                                   | –                                                                                                                                                                                         | Too broad: it hides user-authored `~/.agents` skills                                                                                                                                   |
| O′    | B + `disabledExtensions: ["skill:agents/plan"]`                                                    | `agents/plan` hidden, `plan` kept                                                                                                                                                                   | –                                                                                               | –                                                                                                                   | –                                                                                                                                                                                         | Per-name alternative                                                                                                                                                                   |

`omp skill list` (B) prints the 91 final names on stdout and the 41 warnings on stderr, for example:
`warning: name collision: "backport" from …/.agents/skills/backport/SKILL.md differs from …/plugins/cache/plugins/ycc___ycc___6.0.0/skills/backport/SKILL.md; available as "agents/backport"`.
No TUI or UI surface shows these warnings (`grep skillWarnings src/modes` returns nothing).

## Project code execution (trust)

The fixture project held:

- `.claude/hooks/pre/bash.ts`;
- `.omp/extensions/x.ts`;
- `.mcp.json` with a stdio `projstub`;
- `.omp/plugins/installed_plugins.json` pointing at an in-project plugin whose `.mcp.json` has a stdio
  server;
- `.omp/config.yml` with `extensions: [<in-project .ts>]`.

Each one writes a marker file. One RPC session ran with no prompt and no tool call.

| Run                                                                       | Markers written                                                                                     |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| default                                                                   | hook, extension, MCP, plugin MCP, `extensions:`                                                     |
| `--no-extensions`                                                         | MCP and plugin MCP                                                                                  |
| `--config overlay.yml` with `mcp: {enableProjectConfig: false}`           | hook, extension                                                                                     |
| user `disabledProviders: [claude, mcp-json]`                              | none                                                                                                |
| …plus project `.omp/config.yml` `disabledProviders: []`                   | **all** (the project layer overrides the user kill switch)                                          |
| user `mcp.enableProjectConfig: false` plus project `true`                 | MCP ran (the project wins)                                                                          |
| **`--no-extensions --config overlay.yml`** (`enableProjectConfig: false`) | **none**. ycc user skills (50 + aliases), 49 `ycc:` commands and the `ycc-mcp:*` servers still load |

A project `.claude/hooks/pre/bash.sh` shell hook did not run at session start; it is a tool hook.
`isProjectTrusted: () => true` is hard-coded (`src/extensibility/extensions/runner.ts:1433`,
`src/session/agent-session.ts:8562`).

## MCP equivalence and OAuth keys (YAN-1291)

A probe extension (`mcpprobe.ts`) reads `loadCapability("mcps")` and
`mcp/oauth-flow.mcpOAuthCredentialId(url)`. The installed `ycc-mcp` cache `.mcp.json` was mutated per
variant (sandbox only):

| `linear-personal` variant                                                      | Survives dedupe                                                       | OAuth credential id                                                                        |
| ------------------------------------------------------------------------------ | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| shipped: `https://mcp.linear.app/mcp`                                          | **no**, shadowed by `ycc-mcp:linear`                                  | `mcp_oauth:profile:default:https://mcp.linear.app/mcp` (same as linear)                    |
| `url: …/mcp?ycc-profile=personal`                                              | **yes**, and nothing shadowed                                         | `mcp_oauth:profile:default:https://mcp.linear.app/mcp?ycc-profile=personal` (**distinct**) |
| `url: …/mcp/`                                                                  | yes                                                                   | `…:https://mcp.linear.app/mcp/` (distinct)                                                 |
| `headers: {X-Ycc-Profile: personal}`                                           | yes                                                                   | **same as linear**: shared token, wrong account                                            |
| `requestIdFormat: "string"`                                                    | **no**: plugin `.mcp.json` drops the field (`docs/mcp-config.md:111`) | same                                                                                       |
| user `mcp.json` `ycc-mcp:linear-personal` with the `?ycc-profile=personal` URL | yes (native wins by name)                                             | distinct                                                                                   |

Why each variant behaves this way, from source:

- **Equivalence.** `src/capability/mcp.ts:77-106` (`isSameMCPConnection`) compares `auth`, `oauth`,
  `requestIdFormat`, the transport, the exact `url` string and `headers`.
- **Token key.** The OAuth credential id is profile plus the **verbatim URL**, query included
  (`src/mcp/oauth-flow.ts:16-34`). It lives in `<agentDir>/agent.db` `auth_credentials`.
- **Discovery.** RFC 9728 discovery drops the query (`src/mcp/oauth-discovery.ts:358-372`).

Linear's side (`curl`, 2026-10-21):

- `POST https://mcp.linear.app/mcp?ycc-profile=personal` (MCP `initialize`) returns `401` with
  `resource_metadata="…/.well-known/oauth-protected-resource/mcp"`. This is byte-identical to the
  bare URL: the query is accepted and ignored.
- The protected-resource document for the bare and query paths is identical:
  `{"resource":"https://mcp.linear.app/mcp","authorization_servers":["https://mcp.linear.app"],…}`.
  The token audience stays the canonical resource.
- `/mcp/` advertises a **different** resource, `https://mcp.linear.app/mcp/`. `/mcp/foo` also answers
  401 (a prefix route). A trailing slash changes the RFC 8707 resource, so it was rejected.
- Dynamic client registration (`POST /register`, `token_endpoint_auth_method: none`) succeeds.
  `/authorize` returns 200 for the bare and query resources, and also for an unrelated resource. The
  authorize page is therefore no proof of resource validation. A real two-account login needs a human
  and was **not** run.
- Linear documents `https://mcp.linear.app/mcp` (OAuth 2.1 + DCR) and `/mcp/readonly`
  (<https://linear.app/docs/mcp.md>). Query parameters are undocumented.
