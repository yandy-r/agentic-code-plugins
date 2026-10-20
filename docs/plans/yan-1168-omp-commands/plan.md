# YAN-1168 — OMP native command entrypoints

Linear YAN-1168 · GitHub #385 · Target release: ystack v6.1.0 (next minor).

## Acceptance criteria (from the issue)

1. Every public skill is invokable explicitly with arguments.
2. Hidden/manual policies are respected.
3. Collisions and unsupported names fail during generation.

## Contract (omp 18.12.3 live probes; upstream `src/discovery/claude-plugins.ts`, `docs/slash-command-internals.md`, `docs/skills.md`)

- `claude-plugins` provider scans `<root>/commands/*.md` and registers each as
  `<root.plugin>:<file stem>`. Marketplace installs take `root.plugin` from the catalog plugin
  name. `--plugin-dir` takes it from `.claude-plugin/plugin.json` or `plugin.json` `name`, otherwise
  the directory basename. `.omp-plugin/plugin.json` is **not** read for this name (live probe:
  `.omp-plugin` only → `p:demo`; `.claude-plugin` → `ycc:demo`). `omp plugin link` registers
  bare names (spike §1.3).
- Command frontmatter: `description` (else first body line), `argument-hint`/`argumentHint`.
  The body is the template. `$ARGUMENTS`/`$@`/`$1…` are substituted once. When no placeholder
  is used, the args are appended.
- Built-ins dispatch first and split the name at the first whitespace **or colon**, so `/ycc:plan`
  is tried as built-in `ycc` before the file command. The namespace must not be a built-in name or
  alias. Extension/file parsing splits only at the first space, so `ycc:<skill>` is preserved.
- `/skill:<name>` exists only when `skills.enableSkillCommands` is on (default `true`). `skill://<name>`
  `read` works for every discovered skill, including `hide`/`disableModelInvocation` ones.

## Decisions

| ID  | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                | Why                                                                                                                                                                               |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | New `scripts/generate_omp_commands.py` writes `packages/omp/ycc/commands/<skill>.md`. `--check` byte-compares and prunes orphans (same convention as the skills/agents generators).                                                                                                                                                                                                                                                     | One package tree, one convention.                                                                                                                                                 |
| D2  | A thin wrapper per command: frontmatter `description` + `argument-hint` (when the source has one). Body: read `skill://<name>` and follow it with `$ARGUMENTS`. The body is not embedded.                                                                                                                                                                                                                                               | One source of truth (the generated skill). It works without `skills.enableSkillCommands`, and `skill://` resolves the skill's relative paths. Matches the Cursor wrapper pattern. |
| D3  | Public = directory not `_`-prefixed and `user-invocable` not `false`. Manual-only skills (`disable-model-invocation: true`) **get** a command: commands are user-only, and the skill stays out of model listing through the skills generator. `user-invocable: false` gets **no** command.                                                                                                                                              | Criterion 2; same policy as Cursor/opencode commands.                                                                                                                             |
| D4  | Fail generation on: a name not matching `^[a-z0-9][a-z0-9-]*$`; duplicate names; a `ycc:<name>` that equals a reserved OMP built-in name/alias; a namespace `ycc` that is a built-in name/alias; a missing/empty description; a non-string `argument-hint`; a `user-invocable` that is not a boolean. The reserved built-in set is pinned in the generator from omp 18.12.3 `slash-commands/*.ts`.                                      | Criterion 3; built-ins win dispatch and parse up to `:`.                                                                                                                          |
| D5  | Descriptions reuse the skills generator's namespace rewrite (`/ycc:x` → `/skill:x`), so command and skill text agree and the content policy (`/ycc:` forbidden in bodies) holds.                                                                                                                                                                                                                                                        | Single transform.                                                                                                                                                                 |
| D6  | Bare-name shadowing under `omp plugin link` (`/plan`, `/init` lose to OMP's built-in/bundled commands) is documented in `COMMANDS:omp`, not failed. Skill names stay source-stable.                                                                                                                                                                                                                                                     | Renaming public skills is an API break; marketplace installs are always namespaced.                                                                                               |
| D7  | Wiring: `generate-omp-commands.sh`, `validate-omp-commands.sh` (drift + inventory parity + content policy), `sync.sh omp`, `validate.sh omp`, `lib/validate-scope.sh` + `test-validate-scope.sh`, `pyproject.toml` mypy list, CONTRIBUTING/README/AGENTS.md wording. `packages.json` omp `ycc` components gain `commands`; the note drops the YAN-1168 deferral. Matrix `COMMANDS:omp` → `partial` with a note.                         | Same pattern as YAN-1167/YAN-1169.                                                                                                                                                |
| D8  | Handoff to YAN-1171: the OMP root needs both `.omp-plugin/plugin.json` (OMP keeps agent `model:` only with it) and `.claude-plugin/plugin.json` (or root `plugin.json`) with `name: ycc`, which sets the command prefix. A manifest-less `--plugin-dir` root uses its directory basename; a marketplace install uses the catalog plugin name, which must be `ycc`. Verified live: with both manifests, commands register as `ycc:demo`. | Live-probed naming rule.                                                                                                                                                          |

## Tests

`scripts/test_generate_omp_commands.py` (golden): wrapper shape + `$ARGUMENTS`; `argument-hint`
kept and omitted; manual-only skill gets a command; `user-invocable: false` skipped; `_shared`
skipped; bad name, duplicate, reserved collision, empty description, non-string hint fail;
description namespace rewrite; inventory parity (each public skill exactly once); `--check` detects
drift and orphans.

## Live verification

Throwaway root with `.claude-plugin/plugin.json` (`name: ycc`) + copies of
`packages/omp/ycc/{skills,agents,commands}`:

1. RPC `get_available_commands` lists `ycc:<skill>` for every public skill with descriptions and hints.
2. A real `omp -p "/ycc:<skill> <args>"` run loads the skill and receives the arguments.
