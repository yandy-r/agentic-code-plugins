# Cursor and OMP rule sources

This tree supplies Cursor rule content, generated as `.cursor-plugin/rules/**/*.mdc`,
and OMP rule content, generated as flat `packages/omp/ycc-rules/rules/ycc-*.md`.
No Claude, Codex or opencode rules generator/installer loads this tree as rules.
Exception: the `hooks-workflow` skill reads `common/hooks.md` and language `hooks.md`
as hook-configuration inputs across targets. These live inputs are retained for
supported stacks, but **no hooks.md is emitted to Cursor**: the source recommendations
are not native Cursor hooks.

After editing sources, regenerate and validate:

```bash
./scripts/generate-cursor-rules.sh
./scripts/validate-cursor-rules.sh
./scripts/sync.sh --only omp       # regenerates packages/omp/ycc-rules
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
cp -r /path/to/ystack/.cursor-plugin/rules/common .cursor/rules/
cp -r /path/to/ystack/.cursor-plugin/rules/python .cursor/rules/
```

Keep directories intact to avoid colliding filenames. Choose only the stacks you
need. The installer's `--rules` option is separate: it links files from
`ycc/settings/rules/`, not this tree. It does not install these sources as Claude,
Codex or opencode rules.

## OMP

`scripts/generate_omp_rules.py` (called by `scripts/generate_omp_packages.py`)
flattens this tree into the `ycc-rules` OMP package, because OMP scans plugin
`rules/` flat and names a rule after its file stem:

- **Names.** `<family>/<stem>.md` becomes `ycc-<family>-<stem>.md` (for example
  `golang/coding-style.md` → `ycc-golang-coding-style.md`). `hooks.md` and
  `README.md` are skipped, which leaves 31 rules.
- **Frontmatter.** `description` is copied; `alwaysApply` is emitted only when
  true (`common/security.md`, `common/git-workflow.md`), and then `globs` is
  dropped; source `paths` become `globs`. No other keys.
- **Bodies.** Relative rule links become `rule://ycc-<family>-<stem>` URLs.
  Generation fails on `~/.claude` paths, Claude plugin-root variables or
  `/ycc:` command tokens.
- **Advisory globs.** OMP lists `globs` next to each rule but does not select
  rules by glob. Rules marked `alwaysApply: true` (above) are still included
  automatically; language and web rules are on-demand rulebook entries read
  via `rule://<name>`, so parity with Cursor is partial. Write descriptions
  that say when to read the rule.
- **Override and disable.** Users override a rule by copying it under the same
  name to `<agentDir>/rules/` or `<cwd>/.omp/rules/`, or disable it with
  `ttsr.disabledRules`. See
  [`docs/install/omp.md`](https://github.com/yandy-r/ystack/blob/main/docs/install/omp.md#rules).

## Adding guidance

Add source Markdown with a real description and an explicit scope. Prefer existing
project formatters/linters over copying style guides. Retain only constraints that
change agent behavior; reference existing bundled skills for deeper guidance.
Do not add Claude settings paths, Claude tool execution instructions, or generic
always-applied checklists to generated Cursor rules.
