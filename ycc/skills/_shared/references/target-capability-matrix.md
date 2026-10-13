# Target Capability Matrix

As of 2026-10-03

This file is the authoritative source for which ycc bundle capabilities are supported on each
deployment target. Downstream scripts parse the table below; read the Parser Grammar section
before editing the table.

---

## Parser Grammar

The table below is parsed by `ycc/skills/compatibility-audit/scripts/audit-target-features.sh`.
Follow these rules exactly or the parser will misread cells:

- **Column order**: `capability, claude, cursor, codex, opencode` — do not reorder.
- **Cell vocabulary**: exactly one of `supported`, `partial`, or `unsupported` — no other tokens,
  no trailing punctuation, no parenthetical notes inside the cell.
- **Notes** belong in the Notes section below the table, keyed as `capability:target`.
- Do not change column order or cell vocabulary without updating the parser in
  `ycc/skills/compatibility-audit/scripts/audit-target-features.sh`.

---

## Capability Matrix

| capability        | claude    | cursor      | codex       | opencode    |
| ----------------- | --------- | ----------- | ----------- | ----------- |
| SKILLS            | supported | supported   | supported   | supported   |
| COMMANDS          | supported | partial     | unsupported | supported   |
| AGENTS            | supported | partial     | supported   | supported   |
| HOOKS.PreToolUse  | supported | partial     | unsupported | partial     |
| HOOKS.PostToolUse | supported | partial     | unsupported | partial     |
| HOOKS.Stop        | supported | partial     | unsupported | partial     |
| MCP               | supported | supported   | partial     | supported   |
| INSTALL_PATH      | supported | supported   | supported   | supported   |
| DANGEROUS_MODE    | supported | unsupported | unsupported | unsupported |
| WORKTREE          | supported | partial     | partial     | partial     |
| MODS              | supported | unsupported | unsupported | unsupported |

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
Cursor does not natively execute Claude Code slash commands as installable artifacts. The
`ycc` skill guidance is surfaced to Cursor users only through rule-embedded guidance in
`.cursor-plugin/`. Interactive slash-command dispatch is not available.

**COMMANDS:codex**
The Codex customization platform does not support a slash-command layer. Skills are exposed
via the plugin bundle; there is no Codex analog for slash commands.

**AGENTS:cursor**
Cursor supports background agents (`docs.cursor.com/ko/background-agents`) but does not
consume Claude Code agent `.md` definitions directly. Agents are adapted as Cursor rules or
referenced via the generated `.cursor-plugin/` bundle. Full parity is not guaranteed.

**HOOKS.PreToolUse:cursor**
Cursor does not expose a native PreToolUse hook execution surface equivalent to Claude Code's
`~/.claude/settings.json` hooks. Existing repo hook guidance (e.g., `ycc/rules/*/hooks.md`)
is embedded as rule-file notes, not executed by a hook runner.

**HOOKS.PostToolUse:cursor**
Same constraint as HOOKS.PreToolUse:cursor. PostToolUse hook guidance is rule-embedded only.

**HOOKS.Stop:cursor**
Same constraint as HOOKS.PreToolUse:cursor. Stop hook guidance is rule-embedded only.

**HOOKS.PreToolUse:codex**
The Codex config reference documents `features.codex_hooks` as still under development as of
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
Two supported install paths. (1) GitHub marketplace install managed by Claude Code
at `~/.claude/plugins/ycc/`, or the workspace `.claude-plugin/` directory. (2)
`install.sh install --target claude` additionally registers the repo's
`.claude-plugin/marketplace.json` absolute path as a local marketplace
(`local-ycc-plugins`, `source: "file"`) in `~/.claude/settings.local.json`
(user-private, auto-gitignored) — edits in `ycc/` are live on the next plugin
reload with no rsync. The two marketplaces coexist; enable either `ycc@ycc` or
`ycc@local-ycc-plugins` to pick which copy is active.

**INSTALL_PATH:cursor**
Generated bundle lives at `.cursor-plugin/`; consumed by Cursor from the repo root.

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

If the change affects generated bundles, follow the regeneration steps in `CLAUDE.md` under
"Testing Changes".
