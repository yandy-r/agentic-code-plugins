# @yandy-r/ycc-opencode

Experimental, opt-in [OpenCode](https://opencode.ai) V2 plugin carrying the ycc bundle
(version 6.0.0). It is unlisted and never the default install: the
`install.sh --target opencode` file copy remains the primary path.

Requires OpenCode `>=2.0.30` (V2 plugin API; V1 hook plugins are not supported).

## Enable

Add the package to the V2 `plugins` array in your own `opencode.json`:

```json
{ "plugins": ["@yandy-r/ycc-opencode"] }
```

A local checkout loads with a directory entry (`"file:///abs/path/to/packages/opencode/ycc-opencode"`),
not the `index.js` file.

## What it registers

`setup()` awaits one registration per component class, all from package-local assets:

- **Skills** (`skills/<id>/SKILL.md`): at setup the Markdown, scripts, and shared helpers are copied to a
  temporary rendered tree whose absolute root replaces `{{package-root}}` in shell snippets, so a snippet
  runs from any working directory; the tree is removed when the plugin unloads.
- **Agents** (`agents/<id>.md` prompts, permissions, color, model pins from `ycc/settings/models.json`).
- **Commands**: each public skill becomes `/ycc:<id>`; `$ARGUMENTS` is expanded and the result is forwarded
  as a prompt (a workflow command, not an OS process).
- **MCP servers**: plain data from `mcp-configs/mcp.json`; `{env:VAR}` placeholders resolve from the
  environment at setup time.
- **Instructions**: `AGENTS.md` pushed through the session `context` hook.

## Coexistence with the file-copy install

Skills, agents, and MCP servers are registered under their source ids. OpenCode applies file-copy config
(`~/.config/opencode`) after user plugins, so a same-id file-copy skill, agent, or command replaces (agents:
field-blends over) the package definition; the package's `editor.get` skip only sees registrations loaded
before it, and MCP config servers genuinely win. Package commands are always `ycc:<skill>` and never collide
with the bare file-copy `/<skill>` commands or host built-ins such as `/init`. The context hook does not push
instructions already present in the request.
Provider and variant settings (`providers`) are user configuration and are not carried by this package.
