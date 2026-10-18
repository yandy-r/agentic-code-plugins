# Cursor third-party marketplace spike (YAN-1124)

- **Date:** 2026-10-15
- **Issue:** `YAN-1124` (GitHub #292); target release `v6.0.0`
- **Question:** Can ycc ship Cursor-native packages from a third-party GitHub marketplace, pin them, install them from `agent`, and keep hooks and `~/.cursor/skills` copies from colliding?
- **Harness:** Live CLI against a disposable public fixture, [yandy-r/cursor-plugin-spike](https://github.com/yandy-r/cursor-plugin-spike). Not wired into CI. The fixture is safe to delete after this dossier is merged.

## Executive verdict

1. **User-scope third-party GitHub marketplace: Go.** This spike did not install the Cursor GitHub App.
   `agent plugin marketplace add https://github.com/yandy-r/cursor-plugin-spike` registered marketplace `ycc-cursor-spike` at `scope: user`. The fixture repo was created during this spike, and the spike did not install the Cursor GitHub App. App absence was inferred from the 401 response and the lack of an installation step. `agent plugin marketplace update` then re-indexed that same marketplace from Cursor's servers (public git fetch, not the App's auto-refresh path). The marketplace was removed afterwards. The pre-existing `yci` marketplace was not modified; the before/after `marketplace list` matched.
2. **Pinning: Go for the marketplace ref. Partial for per-plugin `source`.**
   - `agent plugin marketplace add <url> --git-ref <tag|sha>` resolves the ref and stores the **full commit SHA** as `gitRef`. Tag `pin-v1` stored `2d0f5f2722bec9ee0d70ca87cbc4e5c6ea7cfd10`. SHA `13744f2332fab6c47b82bac3c3fedf41a5679496` stored that same SHA. A missing ref fails closed: `git ls-remote did not return a resolvable commit`.
   - A filesystem path is rejected: `Invalid URL format. Expected: github.com/owner/repo or https://github.example.com/owner/repo`.
   - Relative `source` strings (`spike-relative` and `./spike-relative`) are read from the indexed commit and **do** merge `.cursor-plugin/plugin.json` (the CLI printed `MAIN_RELATIVE_DESC`, which exists only on that commit).
   - Object `source` values are real. The CLI schema accepts a string path or `{source:"github", repo, ref?, sha?}`, `{source:"url", url, ref?, sha?}` (`url` must end in `.git`), or `{source:"git-subdir", url, path, ref?, sha?}`. A `git-subdir` entry pinned to the `pin-v1` SHA was cloned into `~/.cursor/plugins/marketplaces/.../<sha>/` and the checkout's skill said `MARKER_PIN_V1`, not the main-branch text. Index output for those entries kept the **marketplace entry description**, not `plugin.json`.
   - The published zod rule "sha must be 40 hex characters" is **not** applied by this CLI indexer. Entry `spike-bad-sha` (`sha: "not-a-sha"`) was registered, not skipped.
   - Server `update` collapses two entries that point at the same relative directory. A marketplace whose only entries were `spike-relative` and `spike-relative-dot` went from 2 (CLI) to 1 (server). Do not emit two marketplace entries for one directory. The 7-entry marketplace also fell by one (7 to 6). The server response does not name plugins, so this run does not prove whether `spike-bad-sha` survived that refresh. The CLI did register it.
3. **Install from `agent`: no non-interactive install. Per-process load works.**
   There is no `plugin install` subcommand (`error: too many arguments for 'plugin'`). `marketplace add` prints `Tip: use /plugins in interactive mode to install plugins from this marketplace.` `agent --plugin-dir <dir>` loaded a local plugin's `sessionStart` hook in that process without an account install. An interactive `/plugins` install was not driven.
4. **Hook parity: `sessionStart` go. `SessionStart` and `WorktreeCreate` no-go.**
   On CLI `2026.10.14-941492e`, `sessionStart` runs from `~/.cursor/hooks.json`, from `<workspace>/.cursor/hooks.json`, and from a plugin `hooks/hooks.json` passed with `--plugin-dir`. The payload field is `hook_event_name: "sessionStart"` and `cursor_version` matches the CLI. The payload also contains `user_email`; hook scripts see the account email.
   `WorktreeCreate` does not occur in the CLI bundle. `SessionStart` occurs only as the unrelated worker flag `onSessionStart`, not as a hook event. A project `hooks.json` that named only `sessionStart` ran. A project file that also named `SessionStart` and `WorktreeCreate` produced no recorder output. In that same session, a plugin file that named only `sessionStart` did run. Unknown event names are not a safe extra key.
   **Release gate:** Cursor `ycc-hooks` may ship `sessionStart` only. Keep `WorktreeCreate` on `install.sh`. Do not copy Claude's `SessionStart` spelling into Cursor `hooks.json`.
5. **`~/.cursor/skills` copies are not collapsed with a plugin skill.**
   Skill dedupe keys off the path after `/.cursor/`, `/.claude/`, `/.codex/`, `/.agents/`, or `/.grok/`. A file under `~/.cursor/skills/<name>/` and a plugin skill under `~/.cursor/plugins/.../skills/<name>/` produce different keys, so both stay. The first discovered item wins on a key collision. A later agent-store item replaces a non-store item with the same key; the reverse does not. In `agent -p`, neither a `~/.cursor/skills/ycc-spike-1124` copy nor the `--plugin-dir` skill was inlined into the prompt (the model reported `NONE`, and the marker text is absent from the session log). Migrate must still delete the `install.sh` copies. The loader will not do it.

## Layout to generate

Repo-root `.cursor-plugin/` is the marketplace manifest directory. It is the wrong place for package contents. The current generated tree has no `plugin.json` and uses that directory as the file-copy root, which collides with the manifest.

```text
.cursor-plugin/marketplace.json          # name: ycc
ycc/.cursor-plugin/plugin.json           # skills, agents, commands
ycc-rules/.cursor-plugin/plugin.json
ycc-mcp/.cursor-plugin/plugin.json
ycc-hooks/.cursor-plugin/plugin.json     # sessionStart only, if shipped
```

Each package is a sibling directory with `.cursor-plugin/plugin.json`. Components use the default folders (`skills/`, `rules/`, `agents/`, `commands/`, `hooks/hooks.json`, `mcp.json`). Marketplace `source` is a relative directory (`"ycc"`, not a git pin). Pin the whole marketplace with `--git-ref` / the stored `gitRef` SHA. One entry per directory. `listed` stays false until the v6 flip.

Tested client: Cursor IDE `3.24.12` (`37b865941ccb31e2fc90c685157534efca87f960`), `agent` `2026.10.14-941492e`. This spike does not establish a minimum older than those versions.

## 1. Environment

- Account: `agent status` reported logged in. Marketplace scope of the fixture was `user`.
- IDE: `cursor --version` → `3.24.12` / `37b865941ccb31e2fc90c685157534efca87f960` / `x64`.
- CLI: `agent --version` and `agent about` → `2026.10.14-941492e` (up to date).
- Fixture commits: `pin-v1` = `2d0f5f2722bec9ee0d70ca87cbc4e5c6ea7cfd10`; description probe = `13744f2332fab6c47b82bac3c3fedf41a5679496`.
- Hook probes used `/tmp/yan-1124-lab` only. `HERDR_ENV` was unset except for one user-hook detection that pointed `HERDR_SOCKET_PATH` at a lab socket. The user's `~/.cursor/hooks.json` was not edited. The lab skill directory `~/.cursor/skills/ycc-spike-1124` and `~/.cursor/plugins/local/ycc-spike-1124` were created for one probe and removed. `agent plugin marketplace list` before and after the fixture matched (`cursor-public`, `yci` at `970c260ae77d98471982660334575aa3a7d01ae2`).

The GitHub App installation endpoint (`repos/yandy-r/cursor-plugin-spike/installation`) returns 401 for this user token, so App absence is inferred from the repo being created in this session with no App install step, plus successful add and server refresh.

## 2. Observed marketplace matrix

CLI `add` prints plugin names and the description it indexed. Server `update` prints only a count.

| Index                                                                                             | CLI `add` count | Server `update` count | What differed                                                 |
| ------------------------------------------------------------------------------------------------- | --------------- | --------------------- | ------------------------------------------------------------- |
| `main` @ `13744f2` (7 entries, including `spike-bad-sha` and two relative paths to one directory) | 7               | 6                     | Count fell by one. Server did not name which entry it dropped |
| `no-bad-sha` (6 entries, still two relative paths, no invalid sha)                                | 6               | 5                     | Count fell by one with the invalid sha already absent         |
| `subset-tests` (`spike-relative` + `spike-relative-dot` only)                                     | 2               | 1                     | Direct evidence that the server collapses those two entries   |
| `--git-ref pin-v1`                                                                                | 2               | not re-run            | Only the two relative entries that exist on that commit       |
| `--git-ref 13744f2`                                                                               | 7               | not re-run            | `gitRef` stored as that SHA                                   |
| `--git-ref does-not-exist-yan1124`                                                                | fail            | n/a                   | `git ls-remote did not return a resolvable commit`            |
| `/tmp/cursor-plugin-spike`                                                                        | fail            | n/a                   | URL parser rejects a filesystem path                          |

Relative entries on `13744f2` displayed `MAIN_RELATIVE_DESC` (from `plugin.json` on that commit). `git-subdir` / `github` entries displayed their marketplace-entry descriptions. The cache directory left behind was the `pin-v1` SHA, and `spike-pinned/skills/ycc-spike-marker/SKILL.md` in that checkout contained `MARKER_PIN_V1`.

`spike-claude-events` (hooks named only `WorktreeCreate` and `SessionStart`) was still indexed. Indexing does not mean those events run.

## 3. Hook probes

Command: `agent -p --trust --sandbox disabled --workspace /tmp/yan-1124-lab/ws`, with a recorder that appends stdin to a lab file.

| Config                                                                   | Result                                                                                                                       |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| User `~/.cursor/hooks.json` `sessionStart` (existing herdr script)       | Fired. A lab unix socket received `pane.report_agent_session` when `HERDR_ENV=1` and `HERDR_SOCKET_PATH` pointed at the lab. |
| Project `.cursor/hooks.json` with only `sessionStart`                    | Fired. `hook_event_name` was `sessionStart`. `cursor_version` was `2026.10.14-941492e`. `workspace_roots` was the lab repo.  |
| Project file that also named `SessionStart` and `WorktreeCreate`         | No recorder output, including from the valid `sessionStart` command in that same file.                                       |
| `--plugin-dir` plugin whose `hooks/hooks.json` named only `sessionStart` | Fired (`label=plugin` in the same session where the mixed project file did not).                                             |
| `~/.cursor/plugins/local/ycc-spike-1124` during one `agent -p`           | No recorder output. Removed immediately. Local-dir discovery for the IDE was not retested.                                   |

`agent -p` did not inline skill bodies. With both `~/.cursor/skills/ycc-spike-1124` (`MARKER=HOME_COPY`) and a `--plugin-dir` skill (`MARKER=PLUGIN_COPY`) present, the model replied `NONE`. Neither marker appears in the session transcript.

## 4. Dedupe rule (from CLI `2026.10.14-941492e`)

The skill identity is the normalized path after the first `/.cursor/`, `/.claude/`, `/.codex/`, `/.grok/`, or `/.agents/` segment. On a collision the first item is kept, unless the later item is in an agent-store skills directory and the current item is not. Plugin cache paths and `~/.cursor/skills/` paths do not share a key. `install.sh migrate` for Cursor has to delete the copied skills, rules, and hooks itself.

## 5. Limitations

1. Interactive `/plugins` user-scope install and uninstall were not driven. Account install remains the documented interactive path.
2. IDE Customize was not exercised. Hook and marketplace results are from `agent` `2026.10.14-941492e`. The IDE version was recorded but not used to click Install.
3. Per-plugin `source.sha` was shown to select the cloned commit. It was not shown to change what an installed plugin executes, because no plugin was installed into the account.
4. No older Cursor than `3.24.12` / CLI `2026.10.14-941492e` was tested.
5. The fixture repo is public and temporary. Delete `yandy-r/cursor-plugin-spike` after this dossier lands.

> **Update (2026-10-18):** limitations 1 and 2 were closed by the v6.0.0 maintainer release verification (YAN-1141): `/plugins` Marketplace installed `ycc`, `ycc-mcp`, `ycc-hooks`, and `ycc-rules` at user scope through both the agent CLI (2026.10.16) and the Cursor IDE. The text above is the original spike record and is otherwise unchanged.

## 6. Reproduction

```bash
agent plugin marketplace add https://github.com/yandy-r/cursor-plugin-spike
agent plugin marketplace list --format json
agent plugin marketplace update ycc-cursor-spike
agent plugin marketplace remove ycc-cursor-spike
```

Pin the marketplace instead of the default branch with `--git-ref pin-v1` or `--git-ref 13744f2332fab6c47b82bac3c3fedf41a5679496`. Remove the marketplace when finished. Do not remove `yci`.
