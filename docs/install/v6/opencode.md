# opencode v6 Install Draft

> **DRAFT — unwired for v6.** The npm package `@yandy-r/ycc-opencode` is
> **unpublished**: no publishing workflow exists, the package is not on the
> registry, and it is **experimental and opt-in — never the default install**.
> The commands shown (`install.sh migrate`, `install.sh --package`) are planned
> v6 commands, not implemented today. The live file-copy installer in
> `docs/install/` is unchanged and stays the primary path.

## Primary path today (unchanged in v6): file copy

```bash
./install.sh install --target opencode
./install.sh sync --target opencode --intent base,settings,mcp,plugins,rules
```

This rsyncs `.opencode-plugin/{skills,agents,commands}/` into
`~/.config/opencode/`, merges managed keys from `.opencode-plugin/opencode.json`
into `~/.config/opencode/opencode.json`, merges MCP servers (project scope by
default; `--global` for user config), and symlinks `.opencode-plugin/AGENTS.md`
to `~/.config/opencode/AGENTS.md`. The file copy is **primary and unchanged** in
v6; it is not a transitional route to be retired.

Current-state steps that keep working unchanged:

- The generated config is **V2-only** (`opencode.ai/v2/docs`). V1 shapes
  (`plugin` singular, `provider`/`agent` top-level, server names directly under
  `mcp`) are rejected by the repo validator.
- The goal plugin is enabled through the live `plugins` array (this is
  current behavior, not the v6 npm package):

  ```json
  {
    "plugins": ["@prevalentware/opencode-goal-plugin"]
  }
  ```

  Install its TUI half with `opencode2 plugin add @prevalentware/opencode-goal-plugin`
  (idempotent; verify with `opencode2 plugin list`). `--settings` installs the
  server-side half.

## Experimental opt-in npm package (planned, unpublished)

`@yandy-r/ycc-opencode` is modeled (in `ycc/settings/packages.json`) as one npm
plugin whose default-exported `{ id, setup }` V2 plugin would register skills,
agents, commands, shared helpers, and MCP, and deliver instructions through a
`session.hook("context", ...)` hook — the mechanism the v2.0.29 spike verified
with a probe plugin. The actual package is not yet generated or published.
Facts that bound every claim below:

- **Unpublished.** No CI publish workflow exists. Publication is owner-decided
  (provenance on a maintainer-pushed product tag) and not implemented.
- **Opt-in and experimental** in the package model (`experimental: true`,
  `opt_in: true`); the file copy never falls back to it or vice versa.
- **Verified only on opencode v2.0.29** (Linux x86_64). Other versions are
  unverified — do not state a minimum older than that.

### Post-publication opt-in shape (future, not current)

After publication, an opt-in would add the package to the V2 `plugins` array.
A directory form is required for `file://` entries (a bare `file://.../index.js`
file entry is ignored with only a server-side warning):

```json
{
  "plugins": ["@yandy-r/ycc-opencode"]
}
```

**No duplication with the file copy.** Because the plugin registers the same
skills, agents, and commands that the file copy installs, choosing the npm
package means removing the file-copy entries first — the two routes are
alternatives, not complements. The planned (future, not implemented)
`install.sh --package @yandy-r/ycc-opencode --target opencode` would install
the npm package and take back only installer-owned file-copy entries, so
user-owned files are preserved. Nothing implementing that planned command
exists today.

**WARNING — name-based deletion hazard in the live installer.** Do NOT treat
`./install.sh remove --target opencode --intent base` (or `--only base`) as a
safe cleanup step: its bundle branch runs `remove_mirrored_entries`
(`scripts/lib/install/bundle.sh`), which deletes every same-named entry from
`~/.config/opencode/{skills,agents,commands,shared}` for each top-level entry
the bundle ships, regardless of ownership. Your own same-named skill, agent,
or command entry would be destroyed; it is name-based, not ownership-aware.

**Manual migration (the safe route today):**

1. Inventory `~/.config/opencode/{skills,agents,commands,shared}` entries,
   checking each same-named entry's contents against the installed bundle
   (for example,
   `diff -r .opencode-plugin/skills/<name> ~/.config/opencode/skills/<name>`,
   plus the matching `agents/`, `commands/`, and `shared/` entries).
2. Back up `~/.config/opencode/{skills,agents,commands,shared}` (or at
   minimum the entries you are about to delete).
3. Remove only entries you confirm are managed/generated copies; keep
   anything user-owned or user-edited.
4. Add `@yandy-r/ycc-opencode` to the V2 `plugins` array above.

## What the spike proved (opencode v2.0.29)

- **Go:** a V2 `{ id, setup }` plugin registered agents, commands, skills
  (inline content + `path` into a fixture directory), and MCP through the V2
  registration APIs; the context hook's pushed system part reached the outgoing
  model request.
- **No-Go:** V1-style `config(cfg)` plugins fail to load (`Plugin must export a
default definition with an id and an effect or setup function.`). The config
  `instructions` array is parsed but **not resolved** on v2.0.29 — a local-file
  entry never reached the model; discovered `AGENTS.md` files did (positive
  control). That is why the file copy ships `~/.config/opencode/AGENTS.md` and
  the npm package uses the context hook instead.
- Skills from config (`skills: ["<dir>"]`, HTTP catalog) listed fine; plugin
  skill bodies arrive as user-role `<skill_content>` blocks with the skill's
  base directory advertised, so generated content references shared helpers
  relatively.

## Migration

**Planned (future, not implemented):** `install.sh migrate --target opencode`
is a planned v6 command; its exact opencode behavior is not designed yet and
it cannot be run today. It must remove only installer-owned copies and
preserve user-owned files; until that ownership-aware migration ships,
migrate by hand using the manual procedure above. For users staying on the
file copy (the default and recommended path), no migration is needed:
re-running the sync commands above keeps the bundle current.

## Evidence

- `docs/internal/spikes/opencode-config-hook.md` (YAN-1125, opencode v2.0.29)
- `docs/internal/adr/0001-package-model-and-versioning.md` (package matrix)
- `ycc/settings/packages.json` (`@yandy-r/ycc-opencode`: experimental, opt-in)
