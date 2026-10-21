# Target Capability Matrix

## Contents

- Parser Grammar
- Capability Matrix
- Native vs install.sh Fallback
- Notes
- How to Update This Document

As of 2026-10-19

This file is the authoritative source for which ycc bundle capabilities are supported on each
deployment target. Downstream scripts parse the table below; read the Parser Grammar section
before editing the table.

---

## Parser Grammar

The first table below (Capability Matrix) is parsed by `ycc/skills/compatibility-audit/scripts/audit-target-features.sh`.
Follow these rules exactly or the parser will misread cells:

- **Column order**: `capability, claude, cursor, codex, opencode, omp` — do not reorder.
- **Cell vocabulary**: exactly one of `supported`, `partial`, or `unsupported` — no other tokens,
  no trailing punctuation, no parenthetical notes inside the cell.
- **Notes** belong in the Notes section below the table, keyed as `capability:target`.
- The Native vs install.sh Fallback table comes after the parsed table and is descriptive only.
  The audit parser stops at the first non-table line after the Capability Matrix, so keep a
  heading or prose line between the two tables. Add a target column only by appending it and
  updating the scripts that parse it.
- Do not change column order or cell vocabulary without updating the parser in
  `ycc/skills/compatibility-audit/scripts/audit-target-features.sh`. Separator cells are dashes
  only (`---`); alignment colons are not allowed. Every header target must be a runtime in
  `ycc/settings/packages.schema.json`, and every `partial` or `unsupported` cell needs a
  `**CAPABILITY:target**` note; `scripts/validate_capability_matrix.py` enforces both.
- **Rows are pinned**: the capability rows and their order are fixed in
  `CANONICAL_CAPABILITIES` in `scripts/validate_capability_matrix.py`. Adding, removing, or
  reordering a capability requires updating that tuple and the capability detection in
  `audit-target-features.sh`.

---

## Capability Matrix

| capability        | claude    | cursor      | codex       | opencode    | omp         |
| ----------------- | --------- | ----------- | ----------- | ----------- | ----------- |
| SKILLS            | supported | supported   | supported   | supported   | partial     |
| COMMANDS          | supported | partial     | unsupported | supported   | partial     |
| AGENTS            | supported | partial     | supported   | supported   | partial     |
| HOOKS.PreToolUse  | supported | partial     | unsupported | partial     | unsupported |
| HOOKS.PostToolUse | supported | partial     | unsupported | partial     | unsupported |
| HOOKS.Stop        | supported | partial     | unsupported | partial     | unsupported |
| MCP               | supported | supported   | partial     | supported   | unsupported |
| INSTALL_PATH      | supported | supported   | supported   | supported   | partial     |
| DANGEROUS_MODE    | supported | unsupported | unsupported | unsupported | unsupported |
| WORKTREE          | supported | partial     | partial     | partial     | partial     |
| MODS              | supported | unsupported | unsupported | unsupported | unsupported |

---

## Native vs install.sh Fallback

Packaging status as of v6.0.0 (2026-10-18). This descriptive companion separates shipping native packages
from installer-managed artifacts and gated work in `ycc/settings/packages.json`.
`listed: false` packages are not published catalog entries; generated trees and successful spikes
alone do not make them shipping user install paths. This does not revise the capability verdicts above.

| target   | native, listed today                                                                                                                          | install.sh fallback today                                                                               | unlisted or gated native packages                                                                                             |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Claude   | `ycc@ycc`, `ycc-mcp@ycc`, `ycc-hooks@ycc` (2.1.300+), `ycc-all@ycc`; `status-bar@ycc-mods`                                                    | Rules, settings, statusline, hooks link, MCP, standalone skills/agents                                  | `ycc-agents@ycc` in v7.0.0                                                                                                    |
| Cursor   | `ycc`, `ycc-rules`, `ycc-mcp`, `ycc-hooks` via the root `.cursor-plugin/marketplace.json` (interactive `/plugins`); hooks `sessionStart` only | Skills, agents, commands, rules, settings under `~/.cursor/`; optional hooks                            | None                                                                                                                          |
| Codex    | `ycc@ycc`, `ycc-mcp@ycc` via the root `.agents/plugins/marketplace.json`                                                                      | Agent TOMLs, `AGENTS.md`, `config.toml`                                                                 | `ycc-hooks` excluded (YAN-1149)                                                                                               |
| opencode | None                                                                                                                                          | Skills, agents, commands, shared, `opencode.json`, `AGENTS.md`                                          | `@yandy-r/ycc-opencode` npm plugin: experimental, opt-in, unpublished                                                         |
| `agents` | None                                                                                                                                          | Skills and `ycc-shared` copied into `~/.agents/`                                                        | None planned                                                                                                                  |
| `omp`    | None                                                                                                                                          | `install.sh --target omp`: local export of `ycc` installed through `omp plugin` (user or project scope) | `ycc` generated, unlisted until v6.1.0; `ycc-mcp`, `ycc-hooks`, `ycc-rules` deferred to v6.1.0 (ADR 0002); `ycc-all` excluded |

Native dependency resolution is a Claude platform feature, not a cross-runtime guarantee.
The Claude `ycc-all` meta plugin's automatic dependency install was verified on Claude Code 2.1.301 and in the v6.0.0 maintainer clean-host verification; Cursor and Codex have no
dependency field, and the `agents` target is a directory convention, not a package system.
Claude rules, settings, and statusline stay on `install.sh`.

The recommendation in `docs/research/ystack/recommendation.md` is qualified by
`ycc/settings/packages.json` and the later verdicts in `docs/internal/spikes/`:

- `claude-hooks.md`: plugin `WorktreeCreate` was observed on 2.1.300, not 2.1.143. The
  hooks package requires a documented 2.1.300 minimum and tested command-level migration dedupe
  that preserves user-owned hooks. `claude-namespace.md` rejects a shared-name agents split;
  the qualified `ycc-agents:` namespace is deferred to v7.0.0.
- `codex-marketplace.md`: native catalog discovery is verified on 0.161.0, but `WorktreeCreate`
  is dropped and trusted plugin hook dispatch is unverified. Hooks remain excluded.
- `cursor-plugin.md`: user-scope GitHub marketplace registration is verified; interactive
  install was verified in the v6.0.0 maintainer release verification (YAN-1141). YAN-1132
  generates the native packages with a tested Cursor floor of 3.24.12, listed in the root marketplace.
  Native hooks are limited to `sessionStart`; do not infer `WorktreeCreate` or other Claude hook parity.
- `opencode-config-hook.md`: V2 registrations and context-hook instructions were verified on
  v2.0.29, not the V1 config-hook approach. The experimental npm path still needs CI publishing;
  `install.sh` file copy remains primary.
- `omp-runtime-contract.md`: tested on omp 18.12.2 (supported floor `>=18.12.2`). OMP gets a
  dedicated generated `.omp-plugin/` tree; shell hooks, `hooks.json`, and `WorktreeCreate` never
  run, and `ycc-all` is omitted because OMP ignores plugin dependencies. See ADR 0002. The
  opt-in harness installs a generated export of `ycc` (its catalog includes unlisted rows) from
  a local pinned fixture on omp 18.12.3 (YAN-1171). `install.sh install --target omp` installs the
  same export from a checkout through `omp plugin` (YAN-1172); the repository has no published OMP
  catalog until a row is listed (YAN-1180).

---

## Notes

**COMMANDS:claude**
Claude Code has no separate ycc command-wrapper layer. Public skills are native slash
invocations (`/ycc:<name>`); `user-invocable: false` hides a skill from the slash menu.
The standalone installer's Claude `commands` intent aliases `skills`. It retires only
legacy wrappers recorded in installer ownership state, and only after a successful
skills install. Foreign wrappers are never touched.

**INVOCATION POLICY**
`disable-model-invocation: true` is source frontmatter for manual-only skills; it is
distinct from `user-invocable: false`. Claude and Cursor keep the native flag. Codex
emits a skill-local `agents/openai.yaml` with `policy.allow_implicit_invocation: false`.
opencode emits skill metadata `opencode/autoinvoke: 'false'`. The cross-tool `agents`
target has no portable key, so it omits the flag and keeps the description.

**COMMANDS:cursor**
The native `packages/cursor/ycc/commands/` contains thin commands derived from
user-invocable skills in `ycc/skills/`; each loads its package-local skill. This is not
an installed-plugin dispatch proof. The file-copy installer's `commands` intent installs
owned wrappers into `~/.cursor/commands/` that reference the installed skills, and its
`hooks` intent is an optional explicit carrier that registers `sessionStart` only.
Native plugin install is interactive (`/plugins`); the agent CLI has no non-interactive
`plugin install`.

**COMMANDS:codex**
The Codex customization platform does not support a slash-command layer. Skills are exposed
via the plugin bundle; there is no Codex analog for slash commands.

**AGENTS:cursor**
Agents from `ycc/agents/` are adapted into `packages/cursor/ycc/agents/` and copied by
the installer to `~/.cursor/agents/`. The same generated definitions are packaged in the
native `ycc` package.

**HOOKS.PreToolUse:cursor**
Cursor does not expose a native PreToolUse hook execution surface equivalent to Claude Code's
`~/.claude/settings.json` hooks. Existing repo hook guidance (e.g., `ycc/rules/*/hooks.md`)
is embedded as rule-file notes, not executed by a hook runner.

**HOOKS.PostToolUse:cursor**
Same constraint as HOOKS.PreToolUse:cursor. PostToolUse hook guidance is rule-embedded only.

**HOOKS.Stop:cursor**
Same constraint as HOOKS.PreToolUse:cursor. Stop hook guidance is rule-embedded only.

**HOOKS.PreToolUse:codex**
The Codex config reference documents `features.codex_hooks` as under development as of
the April 2026 research audit. No primary source confirms production availability. Marked
`unsupported` pending a verified Codex GA announcement.

**HOOKS.PostToolUse:codex**
Same constraint as HOOKS.PreToolUse:codex.

**HOOKS.Stop:codex**
Same constraint as HOOKS.PreToolUse:codex.

**MCP:codex**
MCP integration is referenced in the Codex customization docs
(`developers.openai.com/codex/concepts/customization`) but is less mature than the Claude Code
or Cursor MCP surfaces. Treat as partial until a verified stable API is documented.

**DANGEROUS_MODE:cursor**
The `--dangerously-skip-permissions` flag is a Claude Code CLI concept with no equivalent in
Cursor.

**DANGEROUS_MODE:codex**
No equivalent to Claude Code's dangerous mode exists in the Codex runtime.

**INSTALL_PATH:claude**
`install.sh install --target claude` registers the `ycc` marketplace through the `claude` CLI, then
runs `claude plugin install ycc@ycc --scope user`. Directory mode (default) runs
`claude plugin marketplace add <absolute-repo-root> --scope user`, so the marketplace
points at the repo checkout (`.claude-plugin/marketplace.json`, name `ycc`) and edits in `ycc/`
apply on `/reload-plugins` with no rsync or cache clear; rerun `--only base` if the repo moves.
Repo mode runs `claude plugin marketplace add yandy-r/ystack --scope user`, a GitHub
source; update with `claude plugin install ycc@ycc --scope user` or the `/plugins` UI. The CLI
writes to `~/.claude/settings.json`. The installer first replaces a symlink there with a real
file so the committed `ycc/settings/settings.json` is not modified, and the `settings` step
later merges repo-managed keys while preserving the CLI-written marketplace entry. It also
removes legacy `local-ycc-plugins` marketplace and `ycc@local-ycc-plugins` entries from
`~/.claude.json` and `~/.claude/settings.local.json`, deleting `settings.local.json` if that
leaves it empty. Other steps: `rules` links `~/.claude/CLAUDE.md`, `hooks` links
`~/.claude/hooks`, `mods` registers the `ycc-mods` directory marketplace, and `skills`/`agents`
install standalone copies into `~/.claude/` (warning about duplicate names if `ycc@ycc` is also
installed). `remove --target claude` uninstalls `ycc@ycc` and the `ycc` marketplace.

**INSTALL_PATH:cursor**
Sources under `ycc/` generate `packages/cursor/ycc/{skills,agents,commands}/`,
`packages/cursor/ycc-rules/rules/`, `packages/cursor/ycc-mcp/mcp.json`, and
`packages/cursor/ycc-hooks/hooks/`. Canonical `ycc/settings/cursor/cli-config.json`
is copied byte-for-byte to `packages/cursor/installer-fallback/config/cli-config.json`.
The file-copy installer copies skills, agents, and rules into `~/.cursor/`, installs
owned `commands` wrappers into `~/.cursor/commands/`, and merges the config there. The
`hooks` step is an optional explicit carrier that installs the `sessionStart` hook only
(no `WorktreeCreate`) and is not inherited by other selections. All four native packages
are listed in the generated root `.cursor-plugin/marketplace.json`; native installation is
interactive (`/plugins`). See `docs/internal/cursor-native-packages.md`.

**INSTALL_PATH:codex**
`install.sh install --target codex` symlinks `~/.codex/plugins/ycc/` to the repo's
`.codex-plugin/ycc/`, also symlinks `~/.agents/plugins/ycc` to the same bundle,
rsyncs custom agents to `~/.codex/agents/`, registers `./.agents/plugins/ycc`
(resolved from the marketplace root, `$HOME`) as the local marketplace source in
`~/.agents/plugins/marketplace.json`, and installs + enables the plugin with
`codex plugin add ycc@local-ycc-plugins`, which snapshots it into
`~/.codex/plugins/cache/local-ycc-plugins/ycc/<version>/`. Codex builds without
the plugin CLI get the legacy hand-written flat cache instead. Rerun the base
install step after regenerating the bundle via `./scripts/sync.sh --only codex`
or after clearing `~/.codex/plugins/cache/`.

**INSTALL_PATH:opencode**
Generated bundle lives at `.opencode-plugin/` (skills, agents, commands, AGENTS.md,
opencode.json). Consumed by opencode from `~/.config/opencode/` (global) or `.opencode/`
(project-local) after `install.sh install --target opencode` rsyncs the files.

**SKILLS:opencode**
Native support at `.opencode/skills/<name>/SKILL.md` with strict YAML frontmatter
(`name`, `description` required; `license`, `compatibility`, `metadata` optional). Descriptions
are limited to 1024 chars. opencode also reads `.claude/skills/*/SKILL.md` and
`.agents/skills/*/SKILL.md` as compatibility fallbacks. Source: opencode.ai/docs/skills/.

**COMMANDS:opencode**
Generated thin native commands, one per public skill, sourced from that skill's
`SKILL.md` (frontmatter drives description, argument hint, and model mapping). Each
command body loads the skill through the `skill` tool and forwards `$ARGUMENTS`;
workflow logic stays in the skill. They exist for commands-only compatibility; use
the skill tool rather than chaining commands. Source: opencode.ai/docs/commands/.

**AGENTS:opencode**
Native agent support at `.opencode/agents/<name>.md`. Frontmatter: `description` (required),
`mode` (`primary` | `subagent` | `all`), `model` (`provider/model-id[#variant]`), `system`,
ordered `permissions` rules, `steps`, `hidden`, `color`, `disabled`, and `request`. Legacy
fields such as `prompt`, `tools`, `permission`, `temperature`, `top_p`, and `disable` must not
be generated for V2 agents. Invoke subagents via `@mention` or the native
`subagent(agent, description, prompt, sessionID?, background?)` tool. Sources:
opencode.ai/v2/docs/agents/ and opencode.ai/v2/docs/tools/.

**HOOKS.PreToolUse:opencode**
opencode has a TypeScript plugin system with a `tool.execute.before` event that covers the
same surface area as Claude Code's PreToolUse hook. Marked `partial` because the `ycc` bundle
does not ship a TypeScript plugin in v1 — hook guidance is emitted as rule-embedded notes
only. Upgrading to `supported` requires publishing an `@yandy/opencode-ycc-hooks` npm package.

**HOOKS.PostToolUse:opencode**
Same constraint as HOOKS.PreToolUse:opencode. The underlying opencode event is
`tool.execute.after`.

**HOOKS.Stop:opencode**
Same constraint as HOOKS.PreToolUse:opencode. Closest opencode event is `session.idle`
(fires when a session's agentic loop halts).

**MCP:opencode**
Native MCP support in the top-level `"mcp"` key of `opencode.json`. Server values are either
`{type: "local", command: [argv0, …args], environment, timeout}` or
`{type: "remote", url, headers, oauth, timeout}`. Note the critical shape difference from
Claude Code: opencode's `command` is a single array containing both argv0 and args (no
separate `args` key), and `env` is spelled `environment`. OAuth uses RFC 7591 Dynamic Client
Registration when `clientId` is omitted. Source: opencode.ai/docs/mcp-servers/.

**DANGEROUS_MODE:opencode**
No equivalent to Claude Code's `--dangerously-skip-permissions` flag exists in opencode. The
OpenCode V2 permission model uses ordered `{action, resource, effect}` rules. Native actions
include `edit`, `shell`, `subagent`, `read`, `glob`, `grep`, `webfetch`, and `websearch`; the
last matching rule wins. Source: opencode.ai/v2/docs/permissions/.

**WORKTREE:claude**
Full support. Worktree isolation is **on by default** for the 9 worktree-aware skills; pass
`--no-worktree` to opt out. The legacy `--worktree` flag is accepted as a silent no-op.
Harness-managed worktrees exist (`Agent(isolation: "worktree")`, `EnterWorktree`, plus the
`WorktreeCreate` hook registered in `ycc/settings/settings.json`), but the current ycc
single-worktree contract should not use per-agent tool-side isolation for parallel task fan-out.
Instead, pre-create one feature worktree and point every agent at it via `Working directory:`.
A Bash fallback (`git worktree add`) is always available. See
`ycc/skills/_shared/references/worktree-strategy.md` for the single-worktree naming scheme.

**WORKTREE:cursor**
Partial. Worktree mode is on by default for the 9 worktree-aware skills; pass `--no-worktree`
to opt out. The legacy `--worktree` flag is a silent no-op. Skills emit `git worktree add`
instructions for the user; no auto-creation from the skill layer. Worktree support is
editor-side in Cursor and is not skill-programmable. See
`ycc/skills/_shared/references/worktree-strategy.md` for Cursor-specific guidance.

**WORKTREE:codex**
Partial. Worktree mode is on by default for the 9 worktree-aware skills; pass `--no-worktree`
to opt out. The legacy `--worktree` flag is a silent no-op. No tool-side isolation equivalent.
Skills instruct the agent to run `git worktree add` via Bash; auto-creation happens when the
instruction is embedded in the agent prompt. See
`ycc/skills/_shared/references/worktree-strategy.md` for the Bash-fallback protocol.

**WORKTREE:opencode**
Partial. Worktree mode is on by default for the 9 worktree-aware skills; pass `--no-worktree`
to opt out. The legacy `--worktree` flag is a silent no-op. Same as Codex — Bash via prompt,
no tool-side isolation. Skills embed `git worktree add` commands in agent prompts. See
`ycc/skills/_shared/references/worktree-strategy.md` for the Bash-fallback protocol.

**MODS:claude**
Supported from Claude Code 2.1.287 (CLI and desktop app). Mods live under `ycc/mods/` with their
own `ycc-mods` marketplace and install via `ycc sync --target claude --intent mods`.

**MODS:cursor**
Unsupported. `--intent mods` is reported and skipped; a translator step would map a mod's hooks
module onto Cursor's extension surface.

**MODS:codex**
Unsupported. Codex has no in-process hook module API; the intent is reported and skipped.

**MODS:opencode**
Unsupported. opencode plugins are the closest analogue, but no translator exists yet; the intent
is reported and skipped.

**SKILLS:omp**
Partial: `scripts/generate_omp_skills.py` generates every skill under `packages/omp/ycc/skills/`,
and it loads via `omp --plugin-dir`. Skills run as `/skill:<name>`, and `disable-model-invocation`
maps natively. `${CLAUDE_PLUGIN_ROOT}` and `_shared` paths become `skill://` URLs, and `_shared`
ships once as the hidden `ycc-shared` skill. `/ycc:<name>` becomes `/skill:<name>`. The tree ships
in the generated `ycc` package (YAN-1171), which is unlisted until release; `install.sh install
--target omp` installs it from a checkout (see INSTALL_PATH:omp). Workflow semantics (YAN-1170):
repo-local worktrees under `.omp/worktrees` (see WORKTREE:omp); fan-out uses one `task` batch and
calls `wait` until every owned job settles, because `-p`/JSON runs exit and drop pending async
results; `ask` exists only in the TUI and `--mode rpc-ui`, so `-p`, `--mode json`, `--mode rpc`
and subagents take each skill's declared default from `question-policy.md`; `--team` is
unsupported and fails closed. Per-skill status: `docs/internal/omp-workflow-semantics.md`.
Source: ADR 0002; spike §3.

**COMMANDS:omp**
Partial: `scripts/generate_omp_commands.py` writes one thin command per public skill to
`packages/omp/ycc/commands/<skill>.md`. Public means the directory is not `_`-prefixed and
`user-invocable` is not `false`; manual-only skills (`disable-model-invocation: true`) still get
one. Each command keeps the skill's `description` and `argument-hint`, reads `skill://<skill>`,
and passes `$ARGUMENTS`. OMP registers plugin commands as `<plugin>:<stem>`; the prefix is the catalog plugin name
for marketplace installs, else the `name` in `.claude-plugin/plugin.json` (or root
`plugin.json`), else the `--plugin-dir` basename. `.omp-plugin/plugin.json` does not set it, but
OMP keeps agent `model:` only with it, so the package root ships both manifests, named `ycc`,
for `/ycc:<skill>` (verified live on omp 18.12.3).
`omp plugin link` registers bare names, and OMP's built-ins (such as `/plan`) and bundled file
commands (such as `/init`) shadow them. Generation fails on names OMP cannot dispatch, duplicate
names, a `ycc` namespace or `ycc:<name>` equal to an OMP built-in name or alias (the set is pinned
from omp 18.12.3), empty descriptions, non-string hints and a non-boolean `user-invocable`.
`/skill:<name>` is an alternative when `skills.enableSkillCommands` is on (the default). The
generated root carries both manifests (YAN-1171); a checkout installs it with `install.sh install
--target omp`, and the repository publishes no OMP catalog until the package is listed (see
INSTALL_PATH:omp).
Source: spike §3.

**AGENTS:omp**
Partial: `scripts/generate_omp_agents.py` generates every agent as an OMP task agent under
`packages/omp/ycc/agents/`, and it loads via `omp --plugin-dir`. `name` and `description` are kept.
Tools map to OMP IDs (`WebSearch` → `web_search`, `WebFetch` → `read`, `NotebookEdit` → `edit`).
Claude tool names in agent prose are rewritten the same way, but only in tool contexts; fenced
code and other code spans stay verbatim. An `mcp__<server>__*` entry is dropped only when
`<server>` is configured in `mcp-configs/mcp.json`; an unknown server fails generation. OMP
mounts every MCP tool in every agent, including agents that listed none (such as the read-only
auditors), and cannot restrict MCP tools per agent. Models map to roles: `opus` → `@slow`,
`sonnet` → `@task`, and `inherit` emits no `model:`. `color` is dropped. Generation fails on any
other key, tool or model. It also fails on OMP's reserved session names (`main`, `sub`) and on
names that would shadow OMP's bundled agents (`task`, `sonic`, `scout`, `reviewer`,
`security-reviewer`, `seance`). OMP has no command-scoped shell permission, so `Bash(<cmd>:*)`
becomes `bash` plus a `## Shell scope (OMP)` prompt section.
Subagents run with `approvalMode: yolo`, so that scope is a prompt rule, not enforced. OMP drops
agent `model:` only for Claude-dialect roots (a `.claude-plugin/plugin.json` without an
`.omp-plugin/plugin.json`). The generated `packages/omp/ycc` root ships `.omp-plugin/plugin.json`,
so it keeps agent `model:` both under `--plugin-dir` and as a marketplace install (YAN-1171).
Delegation: OMP `task` runs agents in the background
when `async.enabled` is set and inline otherwise; worktree isolation is the per-call `isolated`
flag (`task.isolation.enabled`, default off). Since YAN-1170 the generated dispatch reference
uses the `task({context, tasks: [...]})` batch shape (`agent`, not `subagent_type`), never sets
`isolated` for ycc fan-out, calls `wait` before yielding, and reads `agent://<id>` when an inline
summary is truncated at 5000 chars. Subagents have no `ask` tool and return choices to the
parent. OMP has no team tools; `--team` aborts, and `write agent://<id>` peer messaging is not a
team lifecycle.
Source: ADR 0002.

**HOOKS.PreToolUse:omp**
Unsupported. OMP never runs shell hooks or `hooks/hooks.json`; hooks load only as TypeScript
`ExtensionAPI` factories (`pi.on` events such as `tool_call`, `tool_result`, `session_stop`).
ycc ships no adapter for these events; the only planned OMP hook is a herdr `session_start`
extension shim (YAN-1174). Source: ADR 0002; spike §2.4.

**HOOKS.PostToolUse:omp**
Same constraint as HOOKS.PreToolUse:omp. The closest OMP event is `tool_result`.

**HOOKS.Stop:omp**
Same constraint as HOOKS.PreToolUse:omp. The closest OMP event is `session_stop`.

**MCP:omp**
Unsupported today: ycc ships no OMP MCP package yet. OMP's plugin MCP loader reads a package
`.mcp.json` natively, names servers `ycc-mcp:<server>`, and expands `${VAR}` env placeholders.
Owner: YAN-1173. Source: spike §2.5, §3.

**INSTALL_PATH:omp**
Partial: `install.sh install --target omp` (omp `>=18.12.2` on PATH) is the only install path, and
only from a checkout. `scripts/generate_omp_packages.py` builds `packages/omp/ycc/` with
`.omp-plugin/plugin.json`, `.claude-plugin/plugin.json` and `package.json` at the lockstep version.
`scripts/omp_install.py` exports it to `${XDG_DATA_HOME:-~/.local/share}/ycc/omp-marketplace`,
registers that as the `ycc` marketplace, and runs `omp plugin install --scope user ycc@ycc`
(`--project`: `--scope project` in the git root). Ownership is recorded per omp profile in
`~/.config/ycc/omp-native-install.json`; a re-run updates the marketplace and upgrades only on a
version change, and `remove` uninstalls only recorded installs. `--dry-run` previews every `omp`
call. Gaps: the root `.omp-plugin/marketplace.json` (relative `./packages/omp/<package>` sources)
is written only once a package is `listed` in `ycc/settings/packages.json`; none is, so there is
no published OMP catalog, `--mode repo` is refused, and `--target all` skips omp until YAN-1180.
`ycc-mcp`, `ycc-hooks` and `ycc-rules` are YAN-1173 to YAN-1175. OMP has no trust prompt:
installed plugin code runs in-process with full user privileges. Source: ADR 0002.

**DANGEROUS_MODE:omp**
Unsupported. ycc ships no mapping for `--dangerously-skip-permissions`. OMP's default
`tools.approvalMode` is already `yolo` and subagents are forced to yolo, so there is no Claude
flag analogue to emit. Source: spike §2.10.

**WORKTREE:omp**
Partial: skill-managed worktrees use `<repo-root>/.omp/worktrees/`. The OMP generator rewrites the
`worktree-paths.sh` default to `.omp`, and the portable `agents` bundle resolves `.omp` from
`OMPCODE=1` (OMP bash also sets `CLAUDECODE=1`, which `OMPCODE` consumes). Tested by
`scripts/test-worktree-roots.sh` (omp bundle and agents-bundle OMP cases). Gaps: OMP has no
`WorktreeCreate` event, so there is no native hook. OMP's own task isolation and
`omp worktree` place workspaces under `~/.omp/wt` (`OMP_WORKTREE_DIR`); ycc never sets
`isolated` and never deletes `~/.omp/wt`. The bash tool rewrites a literal `git worktree add`
to clone-first `omp worktree add`, which falls back to a plain checkout for in-repo roots.
No native-parity claim. Source: ADR 0002; `worktree-strategy.md` §1.

**MODS:omp**
Unsupported. The Claude Code mod API differs from OMP's `ExtensionAPI`; the status-bar mod is
not ported. Source: ADR 0002.

---

## How to Update This Document

Before changing any cell value, consult the three primary research artifacts that produced the
current verdicts:

1. `research/plugin-additions/report.md` — executive synthesis with platform source citations.
2. `research/plugin-additions/synthesis/innovation.md` — prioritized recommendations and
   rejected ideas, including the explicit warning against claiming cross-platform hook parity.
3. `research/plugin-additions/evidence/verification-log.md` — contradiction log and confidence
   ratings; specifically the Codex hook contradiction entry which drives the `unsupported`
   verdict for all HOOKS.\*:codex cells.

After updating a cell value, also update the corresponding note in the Notes section (or add
one if absent), and re-run the compatibility audit:

```
ycc:compatibility-audit
```

If the change affects generated bundles, follow the regeneration steps in `AGENTS.md` under
"Testing Changes".
