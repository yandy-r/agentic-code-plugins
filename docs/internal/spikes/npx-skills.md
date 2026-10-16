# `npx skills` Install Spike (YAN-1126)

- **Date:** 2026-10-16
- **Issue:** `YAN-1126` (GitHub #308); target release `v6.0.0`
- **Question:** Can vercel-labs `npx skills add <fork> -g -s plan` install the cross-tool
  `agents` target from `.agents-plugin/skills/`, and do the installed skills resolve the
  shared helpers they reference?
- **Tool under test:** `skills@1.7.2` (npm, `vercel-labs/skills`), Node v24.15.0
- **Source pinned:** `yandy-r/claude-plugins` at `f2f3c8a00d0b05d50c0d0aa5f230828fc37773fb`

## Verdict

**No — `npx skills` cannot replace `install.sh` for the `agents` target as generated
today.**

1. **Subdirectory discovery: yes with the explicit tree URL tested.** Pointing at
   `https://github.com/<owner>/<repo>/tree/<sha>/.agents-plugin/skills` lists all 49 skills
   and installs the generated `plan` byte-for-byte (SHA-256 manifest match).
2. **Bare-repo discovery picks the wrong tree.** `npx skills add yandy-r/claude-plugins`
   also finds 49 skills, but installs the **canonical Claude source** (`ycc/skills/plan`,
   manifest match), with unrewritten `${CLAUDE_PLUGIN_ROOT}/...` paths. Every one of those
   references is unresolvable outside Claude Code.
3. **Shared-file resolution: no.** The CLI copies only the selected skill directory. The
   generated skill references `~/.agents/ycc-shared/...`; that directory is never created,
   so all four direct shared references in `plan` are missing after install. Its five
   direct `references/` files exist, but nested references are not all resolvable.
4. **The literal issue command partially installs, then fails.** In the empty test home,
   `add <repo> -g -s plan -y` targets all agents and returns exit 1 for
   `Eve does not support global skill installation`. It is **not a rollback**: the skill,
   lock entry, and links under dozens of other agent directories remain. Passing an
   explicit agent (`-a codex`) installs successfully without that all-agent fan-out.

Per-skill vendoring is one possible remedy (partial cost below), not a proven requirement.
A separate shared-unit install or different bundle layout was not evaluated. No generator
or installer changes are part of this spike.

## Observed matrix

All runs used `env -i` with a throwaway `HOME`, `XDG_*_HOME` and npm cache under
`/tmp/yan1126`, plus `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_NOSYSTEM=1`. Nothing
was written to the real home directory.

| Command (`npx -y skills@1.7.2 …`)                                      | Exit | Result                                                                    |
| ---------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------- |
| `add yandy-r/claude-plugins -g -s plan -y --json`                      | 1    | `plan` selected; failed: `Eve does not support global skill installation` |
| `add yandy-r/claude-plugins -g -s plan -a codex -y --json`             | 0    | Copied `ycc/skills/plan` to `~/.agents/skills/plan`; `ref: null`          |
| `add …/tree/<sha>/.agents-plugin/skills -g -s plan -a codex -y --json` | 0    | Copied `.agents-plugin/skills/plan`; `ref` = pinned SHA                   |
| `add yandy-r/claude-plugins -l`                                        | 0    | `Found 49 skills`                                                         |
| `add …/tree/<sha>/.agents-plugin/skills -l`                            | 0    | `Found 49 skills`; source shown as `@ <sha> (.agents-plugin/skills)`      |

Post-install layout (both successful installs): `~/.agents/.skill-lock.json` and
`~/.agents/skills/plan/{SKILL.md,references/}` only — no `~/.agents/ycc-shared/`.

Reference resolution for the generated `plan` install:

| Reference                                                                     | Resolved                          |
| ----------------------------------------------------------------------------- | --------------------------------- |
| `~/.agents/skills/plan/references/*.md` (5 files)                             | Yes                               |
| `~/.agents/ycc-shared/references/standalone-dispatch.md`                      | No                                |
| `~/.agents/ycc-shared/references/agent-team-dispatch.md`                      | No                                |
| `~/.agents/ycc-shared/references/visual-mode.md`                              | No                                |
| `~/.agents/ycc-shared/scripts/prepare-feature-branch.sh`                      | No                                |
| Nested `_shared/references/branch-prep.md` in `references/planning-tracks.md` | No (pre-existing stale reference) |

## Per-skill vendoring cost (estimate)

Measured against `.agents-plugin/` at the pinned SHA by scanning each skill for literal
`~/.agents/ycc-shared/<path>` references and following those literals transitively through
shared files. **This is a partial lower bound, not a complete dependency closure.** It
excludes relative paths in skills and shared helpers, dynamically constructed paths,
directory expansion, and cross-skill dependencies. Medians below cover all 49 skills,
including zeros. Three skills counted by the literal scan yield no concrete files;
`research-to-issues` uses relative shared paths and is excluded by this method.

| Metric                                              | Value                                          |
| --------------------------------------------------- | ---------------------------------------------- |
| Skills                                              | 49                                             |
| Skills with literal `~/.agents/ycc-shared` mentions | 32                                             |
| Shared files vendored per skill                     | median 2; max 13 (`releaser`)                  |
| Vendored bytes per skill                            | median 19 KB; max 136 KB (`releaser`)          |
| Total vendored bytes, all skills                    | 1.68 MB (shared tree itself: 40 files, 345 KB) |
| Overhead vs skills' own content (2.14 MB)           | +79%                                           |
| `plan`                                              | 6 shared files, 61 KB (skill itself 37 KB)     |

Vendoring would require rewriting shared references to skill-relative paths and preserving
script-relative dependencies, with duplicated helpers regenerated together. A conservative
alternative estimate is copying the entire 40-file, 345,107-byte shared tree per skill:
16,910,243 extra bytes across 49 skills (about +791% over the skill content), before any
cross-skill dependencies. Neither packaging option was implemented or live-tested.

## Implications

- Keep `install.sh install --target agents` as the supported path for the cross-tool
  target; it installs `~/.agents/ycc-shared/` alongside the skills.
- The explicit `.agents-plugin/skills` tree URL with `-a codex` installs the intended
  skill subtree, but does not deliver shared helpers. The CLI also implements shorthand
  subpath/ref syntax; that spelling was not exercised. Do not advertise the current
  install as self-contained; evaluate a dependency delivery mechanism first.
- Repository-root discovery surfaces the Claude source tree. If `npx skills` support is
  pursued, check whether the CLI honors a manifest or ignore mechanism that hides
  `ycc/skills/`.

## Limits

1. Only `skills@1.7.2` and the `codex` agent target were exercised; other agents and CLI
   versions are unverified.
2. Installs were in copy mode (the CLI's choice for `-a codex`); symlink mode was not
   tested.
3. Installed skills were checked for file presence only; no agent runtime loaded them.
4. Isolation scrubbed the environment; network egress was not sandboxed.
5. The source was the public product repository, not a separately created GitHub fork.
   The command's repository-input path was exercised; fork ownership is not independently
   tested. No fork fixture or production configuration was modified.

## Reproduction

```bash
export LAB=$(mktemp -d)
run() { env -i PATH="$PATH" HOME="$LAB/home" XDG_CACHE_HOME="$LAB/cache" \
  npm_config_cache="$LAB/npm" GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
  npx -y skills@1.7.2 "$@"; }
SHA=f2f3c8a00d0b05d50c0d0aa5f230828fc37773fb
run add yandy-r/claude-plugins -g -s plan -y --json            # exit 1 (Eve)
run add "https://github.com/yandy-r/claude-plugins/tree/$SHA/.agents-plugin/skills" \
  -g -s plan -a codex -y --json                                  # exit 0
ls "$LAB/home/.agents"                                           # no ycc-shared/
```
