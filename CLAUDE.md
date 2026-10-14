@AGENTS.md

# Claude-specific repository notes

- Invoke public skills as `/ycc:{skill}` and agents as
  `subagent_type: "ycc:{agent}"`. `user-invocable: false` hides passive skills from
  the slash menu.
- This repo's marketplace is a `directory` source: Claude loads `ycc` in place,
  not from `~/.claude/plugins/cache/`. A missing cache directory is expected;
  `installed_plugins.json`'s `installPath` is nominal. Check install health by
  whether `ycc:` skills and agents are available in-session. Read plugin content
  from `ycc/`, not a cache or generated mirror.
- `${CLAUDE_PLUGIN_ROOT}` resolves to this repo's `ycc/` directory at runtime.
  Source skill paths use `${CLAUDE_PLUGIN_ROOT}/skills/{skill}/…`; shared helpers
  use `${CLAUDE_PLUGIN_ROOT}/skills/_shared/scripts/{name}.sh`.
- Claude mods live at `ycc/mods/<name>/`, each a complete plugin with a
  `hooks/hooks.json` `modules` entry. Their separate marketplace is
  `ycc/mods/.claude-plugin/marketplace.json` (`ycc-mods`), the deliberate exception
  to the single workflow-plugin rule. Generators do not read mods.
  `ycc sync --target claude --intent mods` installs them; other targets report
  the intent unsupported until translated. Validate with
  `./scripts/validate.sh --only mods`; see `ycc/mods/README.md`.

<!-- Maintainer marker for release-model's heading check; not a second policy.
## Branching & releases
The canonical pointer is in AGENTS.md (imported above). Update that pointer,
not this file; do not append a duplicate policy here. -->
