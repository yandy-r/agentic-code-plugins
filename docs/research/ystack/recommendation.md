# Native granular installs and the rename: decision doc

## 0. Owner decisions (2026-10-14)

Recorded on Linear YAN-1127 (ADR). These override the recommendations below where they differ.

1. **Naming:** rename the repo to `agentic-code-plugins`. Keep `ycc` as the namespace and marketplace (`<package>@ycc`). `acc` is a brand name only.
2. **Claude agents split:** ship `ycc-agents` without a break in 6.x if the shared-manifest-name spike (YAN-1121) passes. Otherwise ship it in **v7.0.0** as a breaking change with the `ycc-agents:` prefix (YAN-1142).
3. **Claude rules:** stay on `install.sh`. No passive-skills `ycc-rules` on Claude (YAN-1144 canceled).
4. **opencode:** ship `@yandy-r/ycc-opencode` in **v6.0.0** as an experimental, opt-in npm plugin, published by CI on the maintainer-pushed tag (YAN-1143). Its scope depends on spike YAN-1125.
5. **Cursor:** distribute from the GitHub repo marketplace in 6.0. Submit to the Cursor marketplace after 6.0 (YAN-1145).

## 1. Short answer

**Partly.** The goal makes sense, but the guess behind it is half right, and the example install ids put the parts in the wrong order.

- **Is single-file copying obsolete?** No. It is obsolete only for Claude Code. It is mostly obsolete for Cursor. It is partly obsolete for Codex. It is not obsolete for opencode or for the cross-tool `~/.agents/skills` target.
- **Automatic dependency resolution works natively only on Claude Code.** No other runtime has a dependency field: not Codex, not Cursor, not opencode, not the Agent Plugins spec, and not `npx skills`. Everywhere else, "skills pulls in agents" has to come from how we draw package boundaries (each package ships everything it needs) or from `install.sh`.
- **The id order is reversed.** In `acc@claude-skills`, the part after `@` is the **marketplace**, not the component. The idiomatic form is one marketplace holding several plugins, e.g. `ycc-mcp@ycc`. Names that start with `claude-` or look official are also reserved or flagged by Claude's validator, so `claude-skills` and `claude-agents` should not be used as names.
- **Rename the repo, not the namespace.** `yandy-r/agentic-code-plugins` is free on GitHub and npm. The `ycc:` prefix should stay: Claude takes it from the plugin's manifest name, it appears about 876 times in 159–197 files under `ycc/`, and it is in every user's `enabledPlugins` key. "acc" is not a good identifier either. The unscoped npm name is taken and the acronym is crowded.

**Recommended target: v6.0.0.** Correctness fixes ship first in a 5.2.x patch. Everything else is prepared on `main` without being listed in any marketplace. One rename PR and one package-listing PR then go in just before the 6.0.0 release.

## 2. Critique of the two candidate designs

### Shared problems: unsupported or overstated claims

1. **Existing users will not "auto-install ycc-agents on next update".** Claude turns auto-update off by default for third-party marketplaces. Existing `ycc@ycc` users get new dependencies only after `/plugin marketplace update ycc` or after turning auto-update on. Both designs understate this.
2. **A Claude plugin hook for `WorktreeCreate` is unverified.** Both designs move hooks into a `ycc-hooks` plugin. The dossier shows hooks are a valid plugin component, but it never confirms that the `WorktreeCreate` event (or `statusLine`) works from a plugin. minimal-risk gates this behind a spike; native-first does not.
3. **Codex discovering the marketplace through a relative path is unverified.** We don't know which file `codex plugin marketplace add owner/repo` reads when the repo has both `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`. If it picks the Claude file, it installs the Claude source tree (`./ycc`) into Codex. minimal-risk flags this risk; native-first ignores it.
4. **"Skills degrade gracefully when an agent is missing" is assumed, not shown.** No skill was checked. On Codex, Cursor without bundled agents, and opencode, a missing agent role probably means a failed dispatch, not a fallback.

### native-first

- **It breaks the namespace.** Moving agents into a `ycc-agents` plugin renames every `ycc:<agent>` reference to `ycc-agents:<agent>`. That includes 44 `subagent_type` references in skills, agent-to-agent references in 14 agents, and anything users wrote themselves. The design admits this, but it plans the break before the "same manifest name" spike has run.
- **It creates a dependency cycle that only vendoring can break.** Four agents read skill paths: implementor, planner, pr-comment-fixer, releaser. Skills dispatch agents. Splitting them makes `ycc → ycc-agents → ycc` paths. Vendoring the skill files into the agents package breaks the cycle, but it duplicates content that will drift.
- **Its release process conflicts with RELEASING.md.** It needs version ranges, which need per-plugin `<plugin>--v6.0.0` tags (7+ per release). "Agents never tag" and maintainers cut releases. So every release gains a list of tags a human must push. Codex `git-subdir` sources pinned to `ref: v6.0.0` also point at a tag that does not exist yet when the release PR merges, so the Codex install is broken on `main` until the tag lands.
- **Its speculative mechanisms are presented as the plan.** These include the Codex SessionStart hook that would sync agent TOMLs, the opencode cross-package `register()` calls, Claude rules shipped as passive skills, and moving `status-bar@ycc-mods` to `ycc-mod-status-bar@ycc` with no automatic cross-marketplace rename.
- **The release surface is very large.** It means 7 Claude plugins, 4–5 Codex plugins, 6 Cursor plugins, 6 npm packages and an Agent Plugins root, all in lockstep. A publish that half-succeeds leaves runtimes out of sync.

### minimal-risk

- **It doesn't give the owner granular skills and agents on Claude or Cursor.** It is honest about that, though.
- **The Codex `ycc` plugin loses `.mcp.json`.** That is a breaking change for users who installed only through the marketplace. It is acceptable in a major release, but it needs a migration note.
- **Its claim that Cursor already emits `${CURSOR_PLUGIN_ROOT}` paths is only half true.** The generator emits the variable, but the content assumes the file-copy layout under `~/.cursor`. Moving to a real plugin layout needs a generator audit.
- **Coverage gaps:** Cursor hooks are deferred, opencode is file-copy only, and Claude rules and settings stay on install.sh. All of that is correct, but it should be said plainly to the owner.
- **What it gets right:** it avoids version ranges (bare-name dependencies inside one relative-path marketplace mean no per-plugin tags), keeps one `v<semver>` tag, and gates unverified features behind spikes. This is the right default for a trunk-only repo.

### What both designs leave uncovered

Neither design has a plan for commands on Cursor and Codex, beyond Codex turning legacy `commands/` into skills. Neither defines how users avoid duplicate loading when a native plugin and the `~/.agents/skills` copies are both present. Neither decides which agents the `orchestrate` and `init` skills can count on, given that they choose from about 20 agents at run time.

## 3. Merged recommendation

The base is **minimal-risk**, plus three things from native-first: the build-time dependency graph and closure validator, an `install.sh migrate` command, and clear per-runtime native-vs-fallback docs. Any split of agents from skills on Claude waits for the namespace spike.

### Names

| Item                                | Value                                                                                                            |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Repo                                | `yandy-r/agentic-code-plugins` (GitHub and Forgejo). Never recreate the old name, so the redirect keeps working. |
| Marketplace (Claude, Codex, Cursor) | `ycc`                                                                                                            |
| Claude mods marketplace             | `ycc-mods` (unchanged)                                                                                           |
| Namespace                           | `ycc:` (unchanged)                                                                                               |
| Package names                       | `ycc`, `ycc-mcp`, `ycc-hooks`, `ycc-rules` (Cursor only), `ycc-all` (Claude meta), and later `ycc-agents`        |
| npm scope (opencode, experimental)  | `@yandy-r/ycc-opencode`                                                                                          |
| "acc"                               | Prose and branding only, if wanted. Never an id.                                                                 |

### Package matrix

| Runtime                              | Package id                     | Contents                                                   | Mechanism                                                          | Depends on                                                         |
| ------------------------------------ | ------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| Claude                               | `ycc@ycc`                      | 49 skills, 55 agents, `_shared`                            | native (same as today)                                             | none                                                               |
| Claude                               | `ycc-mcp@ycc`                  | `.mcp.json` (10 servers, secrets as `${ENV}`)              | native, MCP-only                                                   | none                                                               |
| Claude                               | `ycc-hooks@ycc`                | WorktreeCreate and herdr hooks                             | native, only if spike S2 passes; otherwise install.sh              | none                                                               |
| Claude                               | `ycc-all@ycc`                  | meta: name + dependencies                                  | native meta-plugin                                                 | ycc, ycc-mcp, (ycc-hooks)                                          |
| Claude                               | `status-bar@ycc-mods`          | status-bar mod                                             | native (unchanged)                                                 | none                                                               |
| Claude                               | rules, settings, statusLine    | CLAUDE.md, AGENTS.md, settings merge                       | **install.sh fallback** (Claude has no plugin component for these) | none                                                               |
| Claude (post-6.0, gated by S1)       | `ycc-agents@ycc`               | 55 agents                                                  | native, agents-only                                                | none (`ycc` would then depend on it)                               |
| Codex                                | `ycc@ycc`                      | 49 skills and `shared/`                                    | native (repo `.agents/plugins/marketplace.json`, relative source)  | agents through install.sh (**cannot be declared**)                 |
| Codex                                | `ycc-mcp@ycc`                  | `.mcp.json`                                                | native                                                             | none                                                               |
| Codex                                | `ycc-hooks@ycc`                | `hooks/hooks.json`                                         | native if spike S3 passes; the user must trust the hooks           | none                                                               |
| Codex                                | agents, AGENTS.md, config.toml | 55 `*.toml` roles, rules, profiles                         | **install.sh fallback** (Codex plugins cannot carry these)         | none                                                               |
| Cursor                               | `ycc@ycc`                      | skills, agents, commands, shared                           | native plugin (Cursor 2.5 or later), self-contained                | none (no dependency field)                                         |
| Cursor                               | `ycc-rules@ycc`                | 38 `.mdc` rules                                            | native                                                             | none                                                               |
| Cursor                               | `ycc-mcp@ycc`                  | `mcp.json`                                                 | native                                                             | none                                                               |
| Cursor                               | `ycc-hooks@ycc`                | hooks                                                      | native if spike S4 passes                                          | none                                                               |
| Cursor                               | `cli-config.json`              | user CLI config                                            | **install.sh fallback**                                            | none                                                               |
| opencode                             | file copy                      | skills, agents, commands, shared, opencode.json, AGENTS.md | **install.sh (primary)**                                           | none                                                               |
| opencode (experimental, gated by S5) | `@yandy-r/ycc-opencode`        | one npm package; its `config` hook registers everything    | npm plugin in the `plugin` key                                     | none (one package, because npm dependencies don't load as plugins) |
| agents (`~/.agents/skills`)          | file copy                      | 49 skills and `ycc-shared`                                 | **install.sh**; `npx skills` only if spike S6 passes               | none                                                               |

### Native vs fallback, per runtime

- **Claude: TRUE.** Native plugins and native dependencies, which is real automatic resolution. The gaps are user-global rules (CLAUDE.md and `~/.claude/rules`) and settings beyond `agent`/`subagentStatusLine`. Agent frontmatter `hooks`, `mcpServers`, `permissionMode` and `initialPrompt` are ignored inside plugins.
- **Cursor: TRUE for packaging, FALSE for dependencies.** All six component types can be packaged. There is no dependency field, the marketplace entry has `additionalProperties:false`, and the docs describe no way for users to pin a version. Today's `.cursor-plugin/` is not a real plugin: it has no `plugin.json`, and its directory name collides with Cursor's manifest directory.
- **Codex: PARTIAL.** Skills, MCP, apps and hooks are plugin components. Agent roles, rules and config are not. There are no dependencies.
- **opencode: mostly FALSE.** Plugins are npm code modules. Skills, agents, commands and rules can only arrive through a `config` hook at run time, which is not documented. The V2 plugin API is unreleased.
- **`~/.agents/skills`: FALSE.** It is a directory convention with no package system.

### How dependencies are resolved

1. **A build-time graph** (`scripts/build_package_graph.py`). It records skill→agent edges (resolved by frontmatter name, so `codebase-research-analyst` maps to `code-researcher.md`), skill→`_shared`, skill→skill script paths, agent→skill paths and agent→agent edges. `validate.sh --only packages` fails when a package's closure is not satisfied, or when packages that can be installed together define the same component.
2. **Claude:** bare-name dependencies in one relative-path marketplace. No version ranges, so no per-plugin tags. `ycc-all` is the meta-plugin.
3. **Codex, Cursor, opencode, agents:** packages are self-contained by construction. Skills and agents stay together wherever the runtime allows. The edges a runtime cannot express (Codex agents) are filled by `install.sh install --package ycc --target codex`, which expands the closure from `ycc/settings/packages.json`.
4. **`_shared` and cross-skill script reach-ins** stay inside the `ycc` package, so nothing is vendored in 6.0.
5. **Catalog skills (`orchestrate`, `init`, `write-docs`)** always ship alongside every agent.

### Releasing (trunk-only, RELEASING.md)

- **Lockstep versions.** Every workflow package uses the product version. `status-bar` keeps its own version in `ycc-mods`, as today.
- **One `v<semver>` tag per release**, pushed by a maintainer. Agents never tag. No per-plugin tags unless a later release adopts version ranges.
- **One source of package definitions:** `ycc/settings/packages.json`. Generators emit all three `marketplace.json` files from it. `bump-version.sh` and `preflight.sh` iterate every `plugins[]` entry and every package manifest. Today both are hard-coded to `plugins[0]`, which I verified at lines 97/101 and 105.
- **Hidden until flipped.** Generated package trees land on `main` but are **not listed** in any marketplace until the flip PR, because listing a package makes it installable. The repo rename is prepared as a dry-run script with an allowlist, then applied in one PR after the owner renames the repo on GitHub and Forgejo.
- **CI** keeps `validate.yml` as the single gate, with new groups `packages`, `claude-native` (`claude plugin validate`), `cursor-native` (vendored schema) and `codex-native` (source-tag allowlist).

### Migration

- **Claude users:** nothing breaks. `ycc@ycc` keys survive the repo rename, and git fetches follow the redirect. Users who turn on `ycc-hooks` or `ycc-mcp` should run `install.sh migrate --target claude`, which removes the hooks and MCP entries install.sh merged earlier so nothing runs twice.
- **Codex users:** run `install.sh migrate --target codex`. It removes `ycc@local-ycc-plugins` and its symlinks, adds the repo marketplace, runs `codex plugin add ycc@ycc ycc-mcp@ycc`, and leaves `~/.codex/agents` in place. Or keep the local install.sh mode, which stays supported.
- **Cursor users:** run `install.sh remove --target cursor --intent skills,agents,rules` before `/add-plugin`. `migrate` prints this step.
- **opencode and agents users:** no change after the Phase 0 key fix. Re-run `install.sh sync --target opencode --settings` so the goal plugin actually loads.

## 4. Risks

- If spike S1 fails, Claude users never get a non-breaking agents/skills split. The owner then chooses between a 7.0 namespace break and no split.
- Codex marketplace precedence (S3) could send the Claude tree to Codex. The Codex marketplace must not be listed publicly until S3 passes.
- Duplicate skills when a native plugin and the `~/.agents/skills` or `~/.cursor` copies are both installed. Detecting this in `install.sh` and documenting it are required.
- Lockstep releases bump add-on packages even when their content did not change. This is accepted.
- The minimum Claude Code version for `dependencies` is not documented. Document 2.1.143 or later and test against that floor.

## 5. Decisions the owner must make

1. Confirm the repo name `agentic-code-plugins`, and confirm keeping `ycc` as the namespace and marketplace (recommended), rather than switching to `acc`.
2. After S1: is a Claude `ycc-agents` split worth a namespace break in 7.0 if the shared-manifest-name approach fails?
3. Should `ycc-rules` exist on Claude as passive skills (an approximation), or should rules stay on install.sh only (recommended)?
4. Should 6.0 publish anything to npm, or does opencode stay file-copy until the V2 plugin API ships (recommended)?
5. Should the Cursor plugin go to cursor.com/marketplace/publish for review, or be distributed only as a GitHub marketplace?
