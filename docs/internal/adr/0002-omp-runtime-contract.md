# ADR 0002: oh-my-pi (OMP) runtime contract

- **Status:** Accepted on authorized PR merge. The PR that adds this file is the
  owner's approval once merged; until then it is proposed.
- **Amendment (2026-10-21, YAN-1174):** herdr session reporting on OMP is **native and
  herdr-owned**. herdr's own `herdr integration install omp` extension reports the session and
  agent state, so ycc ships no OMP hook or extension and `ycc-hooks` is **excluded** on OMP.
  Live probes showed that herdr ignores a ycc-sourced session report (`ycc:omp`) and that a ycc report
  under `herdr:omp` corrupts herdr's `seq` ordering. Decision 3, the `ycc-hooks` package row,
  required adapter 5 and the YAN-1174 follow-up row below record this; the evidence is in the
  [YAN-1174 feature spec](../../research/yan-1174-omp-hooks-extension/feature-spec.md).
- **Amendment (2026-10-21, YAN-1175):** rules, global instructions, settings, model roles and
  approvals on OMP. `ycc-rules` ships natively as 31 flat `ycc-<family>-<stem>.md` rules; OMP
  `globs` are advisory, so language rules are on-demand rulebook entries (**partial** parity).
  `installer-fallback` delivers `AGENTS.md` (`install.sh --rules`) and an opt-in hash-owned merge of
  `modelRoles.{default,slow,task}` and `tools.approvalMode: write` into the user `config.yml`
  (`install.sh --settings`). Both are user scope only; project config and rules always win. The
  status line is **unsupported**. The package rows, required adapters 4 and 6 and the YAN-1175
  follow-up row record this; the evidence is in the
  [YAN-1175 feature spec](../../research/yan-1175-omp-rules-settings/feature-spec.md).
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
plugin root. The spike exercised these surfaces live on a clean, network-isolated home with no
inference; [§5 of the spike](../spikes/omp-runtime-contract.md#5-open-questions-and-gaps) lists
what was not run (network installs, TUI, LSP/DAP startup, hot reload). It found four gaps in the
Claude tree:

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
   - a `package.json` with a unique runtime `name` and the lockstep `version`. ycc ships no
     `omp.extensions` (YAN-1174).

   ycc does not reuse the Claude tree or the root `.claude-plugin/marketplace.json` for OMP. The
   catalog uses no `npm` sources.

2. **Namespace.** Keep `ycc`. Nothing in OMP forces a rename:
   - skills are `/skill:<name>`;
   - commands are `/ycc:<cmd>`;
   - MCP servers are `ycc-mcp:<server>`.
3. **Hooks.**
   - `WorktreeCreate` is **unsupported** on OMP. There is no event to bind, and OMP's task
     isolation manages its own worktrees.
   - herdr session reporting is **native and herdr-owned**: herdr's
     `herdr integration install omp` extension (v8) reports session and state. ycc ships no OMP
     reporter. herdr records only `herdr:`-sourced session reports, and a ycc copy under
     `herdr:omp` corrupts its `seq` ordering (verified live, YAN-1174). The Claude-side
     `herdr-agent-state.sh` is herdr-managed and is not ported.
4. **`ycc-all` is a fallback.** It is omitted from the OMP catalog, and the docs list the
   individual packages to install.
5. **Minimum version.** The supported floor is **`>=18.12.2`**, the tested version. Evidence
   points to a hard floor of 18.2.1 (changelog and tag-bisect) and a recommended 18.11.0. These
   are recorded in the spike but are not claimed until an older binary passes the harness.
6. **Trust.** Every shipped extension, tool, and MCP command is treated as full-trust code. It must
   be side-effect-free at load and fail closed when its dependency is absent. The install docs
   state this, because OMP does not prompt.

### Package matrix (OMP)

| Package                               | OMP mechanism                                                      | Verdict                           | Notes                                                                                                                                                                                                                                                           |
| ------------------------------------- | ------------------------------------------------------------------ | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ycc`                                 | Generated package: skills, agents, `_shared`, optional `commands/` | adapter                           | Rewrite `${CLAUDE_PLUGIN_ROOT}`, `/ycc:` and `_shared` references. Translate agent tools and models to `@role` aliases. The 9 `disable-model-invocation` skills map natively.                                                                                   |
| `ycc-mcp`                             | Generated package with `.mcp.json`                                 | native content, adapter packaging | Servers become `ycc-mcp:<server>`. `${VAR}` env placeholders expand.                                                                                                                                                                                            |
| `ycc-hooks`                           | none                                                               | excluded                          | herdr reporting: `herdr integration install omp`; `WorktreeCreate` unsupported. ycc ships no OMP hooks or extensions.                                                                                                                                           |
| `ycc-rules`                           | Generated package with flat `rules/`                               | adapter                           | Included, unlisted until YAN-1180. 31 rules named `ycc-<family>-<stem>.md`; `paths` becomes `globs`; `description` kept; `alwaysApply` only when true. `globs` are advisory on OMP, so language rules are rulebook entries read via `rule://` (partial parity). |
| `ycc-all`                             | none                                                               | fallback                          | Dependencies are not read. Install the parts separately.                                                                                                                                                                                                        |
| `ycc-agents`                          | none                                                               | n/a                               | Deferred to v7 on Claude (ADR 0001). On OMP, agents ship inside `ycc`.                                                                                                                                                                                          |
| `@yandy-r/ycc-opencode`               | none                                                               | n/a                               | opencode-specific npm plugin. OMP also rejects `npm` marketplace sources.                                                                                                                                                                                       |
| `installer-fallback`                  | user config layer (`<agentDir>`)                                   | fallback                          | Included with `instructions` (`AGENTS.md` symlink, `--rules`) and `settings` (opt-in merge, `--settings`). Rules ship natively in `ycc-rules`. Status line unsupported.                                                                                         |
| Settings, model pins, `settings.json` | user `config.yml` (`modelRoles`, `tools.approvalMode`)             | fallback                          | Opt-in `--settings` merge of `modelRoles.{default,slow,task}` and `tools.approvalMode: write` into the user `config.yml`, owned per leaf by hash. Project config wins. Never `task.agentModelOverrides`.                                                        |
| Status line, status-bar mod           | none (status line); `ExtensionAPI` UI (mod)                        | unsupported                       | No command-backed renderer; an extension is blocked by the YAN-1174 code-surface guard. Use OMP's built-in `statusLine.*`. The mod stays in `ycc-mods`.                                                                                                         |

The full per-component matrix, including every skill class, agents, and rules families, is in
the [spike, section 3](../spikes/omp-runtime-contract.md#3-component--verdict-matrix).

### Required adapters

1. OMP catalog and package-tree generator: `.omp-plugin/marketplace.json`, per-package
   `.omp-plugin/plugin.json` and `package.json`, and the lockstep version in the catalog and
   `package.json`. Implemented by `scripts/generate_omp_packages.py` (YAN-1171). The root also
   ships `.claude-plugin/plugin.json` named after the package: it sets the `/ycc:` command prefix
   under `--plugin-dir`, and OMP reads the install and upgrade version from it, never from
   `.omp-plugin/plugin.json` (an `.omp-plugin`-only bump was ignored live on omp 18.12.3).
2. Skill-body rewriter: `${CLAUDE_PLUGIN_ROOT}` paths, `/ycc:<name>` invocations, and `_shared`
   references.
3. Agent translator: tool IDs (`WebSearch` → `web_search`, with `WebFetch` and `NotebookEdit`
   mapped or dropped), Claude `model` to OMP `@role` aliases, and MCP tool names for
   `ycc-mcp:<server>`.
4. Rules flattener: the nested Cursor tree becomes unique flat names, and `paths` becomes `globs`.
   Delivered (YAN-1175): `scripts/generate_omp_rules.py`.
5. ~~herdr session reporter.~~ Dropped (YAN-1174): herdr ships the integration
   (`herdr integration install omp`), so ycc generates no OMP reporter.
6. Optional: `commands/` wrappers for `/ycc:<name>`. The status-line extension is dropped
   (YAN-1175: unsupported); a port is a follow-up in the
   [YAN-1175 spec](../../research/yan-1175-omp-rules-settings/feature-spec.md#out-of-scope-follow-up-issues)
   and needs a scoped lift of the YAN-1174 code-surface guard.

## Consequences

- OMP gets its own generated tree, validators, and lockstep surfaces. Release tooling must bump
  and check them.
- Users who already run Claude ycc see no duplicates by default, because foreign user sources are
  opt-in. Copies from the `install.sh` `agents` target in `~/.agents/skills` do load by default and
  can duplicate native skills. Delivered (YAN-1176): `install --target omp` runs a default-on
  `dedupe` step that adds hash-owned `agents/<name>`, `codex/<name>` and `opencode/<name>` entries
  to the user `<agentDir>/config.yml` `skills.ignoredSkills`, only for skills ycc installed. The
  entries hide OMP's alias alone, so other tools keep their copies, and `remove --target omp`
  takes them back. Project config is never written.
- `plugin-overrides.json` does not hide a marketplace install's skills, rules, agents, commands,
  or MCP, but it does filter the package's `omp.extensions` (verified live). The full per-project
  switch is `omp plugin disable --scope project`; installer docs must not offer overrides as a
  ycc kill switch.
- Installers resolve paths through omp (`omp plugin list --json`), never a hard-coded `~/.omp`,
  because profiles and XDG relocate state.
- The harness's agent-model probe imports an internal omp module. An upstream move fails the
  harness loudly; it does not silently pass.

## Follow-up mapping

| Issue    | Scope from this ADR                                                                                                                                                                                                                                                     |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| YAN-1166 | Add the `omp` target, capability matrix, and package schema and inventory entries; floor `>=18.12.2`                                                                                                                                                                    |
| YAN-1167 | Skill and `_shared` generation, body rewriter, invocation policy (`disable-model-invocation`)                                                                                                                                                                           |
| YAN-1168 | Optional `commands/` wrappers or a documented `/skill:<name>` entrypoint                                                                                                                                                                                                |
| YAN-1169 | Agent translator (tools, `@role` models, MCP names) under `.omp-plugin/plugin.json`                                                                                                                                                                                     |
| YAN-1170 | Delivered: `.omp/worktrees` root (`OMPCODE`), `task` batch + `wait` dispatch, `question-policy.md`; never `isolated`                                                                                                                                                    |
| YAN-1171 | `.omp-plugin/marketplace.json` and per-package tree generator; `ycc-all` omitted                                                                                                                                                                                        |
| YAN-1172 | Delivered: `install.sh --target omp` lifecycle using `omp plugin` (`--dry-run`, scopes, profile and XDG-aware paths)                                                                                                                                                    |
| YAN-1173 | Delivered: `ycc-mcp` OMP package (native `.mcp.json`, secret-literal audit), installed by `install.sh --target omp`                                                                                                                                                     |
| YAN-1174 | Delivered: hook verdicts (herdr native via herdr's integration, `WorktreeCreate` unsupported), `ycc-hooks` excluded on OMP, validator guards, opt-in herdr harness                                                                                                      |
| YAN-1175 | Delivered: `ycc-rules` OMP package (flat `ycc-*` rules), `--rules` `AGENTS.md` link, opt-in `--settings` merge (`modelRoles`, `tools.approvalMode: write`), `models.json` `targets.omp`; status line unsupported                                                        |
| YAN-1176 | Delivered: default-on `dedupe` step (owned `skills.ignoredSkills` aliases), W1–W5 coexistence warnings, precedence and untrusted-project docs, `--project` residue cleanup; with YAN-1291 (`?ycc-server=<name>` on `linear-personal` in the OMP `ycc-mcp` package only) |
| YAN-1177 | Validators, generator tests, and CI for the OMP tree                                                                                                                                                                                                                    |
| YAN-1178 | Live acceptance matrix extending the spike harness (real ycc tree, network installs, older versions to lower the floor)                                                                                                                                                 |
| YAN-1179 | Install, fallback, and migration docs, including the restart-after-install note                                                                                                                                                                                         |
| YAN-1180 | Release gate: list the OMP packages in a maintainer release                                                                                                                                                                                                             |
