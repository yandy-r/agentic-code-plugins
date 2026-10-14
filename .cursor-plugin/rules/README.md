# Cursor rule sources

This tree supplies Cursor rule content, generated as `.cursor-plugin/rules/**/*.mdc`.
No Claude, Codex or opencode rules generator/installer loads this tree as rules.
Exception: the `hooks-workflow` skill reads `common/hooks.md` and language `hooks.md`
as hook-configuration inputs across targets. These live inputs are retained for
supported stacks, but **no hooks.md is emitted to Cursor**: the source recommendations
are not native Cursor hooks.

After editing sources, regenerate and validate:

```bash
./scripts/generate-cursor-rules.sh
./scripts/validate-cursor-rules.sh
```

## Scope and descriptions

- Every rule has a source `description:` explaining **when** to apply it and **what**
  it covers (nonempty, at most 200 characters, not its H1). The generator uses this
  description; there is no title fallback.
- Only `common/security.md` and `common/git-workflow.md` are `alwaysApply: true`.
  The validator caps the global set at **2 rules / 60 combined body lines**, counting
  headings and blank lines, excluding YAML frontmatter.
- Other `common/` rules are **Apply Intelligently**: description, no globs, not always
  applied. Language and web rules use explicit source `paths:` (converted to Cursor
  `globs:`) or `globs:`. Nothing silently falls back to an all-files glob.
- Rules do not inherit or inline other rules. Keep necessary constraints in the
  selected rule itself, not in "This file extends" link chains.

## Supported stacks

`common/`, `golang/`, `python/`, `rust/`, `typescript/`, and `web/` are retained.
Languages without a corresponding ycc skill/agent (C++, C#, Dart, Java, Kotlin,
Perl, PHP, Swift) have been removed; add focused rules only when actual usage
justifies them. The hooks-workflow language list is derived from retained hooks.md
inputs and will reject a removed language rather than emitting an empty config.

Language `patterns.md` and `testing.md` bodies are three-line entry points to the
corresponding `go-patterns` / `go-testing`, `python-patterns` / `python-testing`,
`rust-patterns` / `rust-testing`, and `ts-patterns` / `ts-testing` skills, with one
nonobvious constraint. Detailed guidance belongs in skills, not duplicate rules.

## Installation and loading

`./install.sh install --target cursor` generates and mirrors the bundle, including
rules, to `~/.cursor/rules/`. That is the installer's destination, **not a verified
native user-global rule-loading surface**. Cursor user-global rules are configured
in Cursor Settings. For file-based project rules, copy the desired generated
folders to the project's `.cursor/rules/`:

```bash
mkdir -p .cursor/rules
cp -r /path/to/claude-plugins/.cursor-plugin/rules/common .cursor/rules/
cp -r /path/to/claude-plugins/.cursor-plugin/rules/python .cursor/rules/
```

Keep directories intact to avoid colliding filenames. Choose only the stacks you
need. The installer's `--rules` option is separate: it links files from
`ycc/settings/rules/`, not this tree. It does not install these sources as Claude,
Codex or opencode rules.

## Adding guidance

Add source Markdown with a real description and an explicit scope. Prefer existing
project formatters/linters over copying style guides. Retain only constraints that
change agent behavior; reference existing bundled skills for deeper guidance.
Do not add Claude settings paths, Claude tool execution instructions, or generic
always-applied checklists to generated Cursor rules.
