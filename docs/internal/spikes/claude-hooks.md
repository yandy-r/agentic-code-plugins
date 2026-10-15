# Claude Code Plugin `hooks/hooks.json` Spike (YAN-1122)

- **Date:** 2026-10-15
- **Issue:** `YAN-1122` (GitHub #288); target release `v6.0.0` (`ycc-hooks@ycc` gate S2)
- **Question:** Do `WorktreeCreate` and a herdr-like `SessionStart` command hook work when shipped as a plugin `hooks/hooks.json`, with `${CLAUDE_PLUGIN_ROOT}` resolved, alongside legacy `settings.json` hooks — and what must migration dedupe?
- **Harness:** [`scripts/test-claude-hooks-spike.sh`](../../../scripts/test-claude-hooks-spike.sh) + [`scripts/claude_hooks_spike.py`](../../../scripts/claude_hooks_spike.py) + typed assertions in [`scripts/claude_hooks_checks.py`](../../../scripts/claude_hooks_checks.py) (opt-in, not wired into CI)

## Executive verdict

1. **Plugin `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}`: Go on `2.1.300` for both events; No-Go on the `2.1.143` floor for `WorktreeCreate`.**
   - `SessionStart` (matcher `"*"`, argument style like the real herdr registration) fires from a plugin on **both** `2.1.143` and `2.1.300`. `${CLAUDE_PLUGIN_ROOT}` expands to the local directory marketplace's source directory (`<LAB>/market-<scenario>/plugin`) on both, not the cache copy. Execution from cache or a remote-source installation is not established.
   - `WorktreeCreate` fires from a plugin **only on `2.1.300`**. On `2.1.143` the plugin's `WorktreeCreate` handler is silently absent during `--worktree` startup (0 executions), while a settings-registered handler works. This matches the CHANGELOG trail: hooks-in-plugins shipped 2.1.50, silent-ignore fix 2.1.69, and the `--worktree` startup plugin-loading fix 2.1.300. It is captured by the harness as an **explicit expected no-go**, not a missing execution.
   - **Release gate:** `ycc-hooks@ycc` may ship `hooks/hooks.json` only with a documented minimum Claude Code version of **2.1.300** (or keep `WorktreeCreate` in `install.sh` settings for the floor). Below that, plugin `WorktreeCreate` hooks silently do nothing — a user on the floor would get Git-default worktrees with no warning.
2. **Coexistence settings + plugin (semantically same hook, distinct command strings):** both run on both versions (verified counts 1 + 1). Shipping the plugin hook does **not** suppress a legacy settings hook: migration must remove installer-owned settings entries or users get duplicate `WorktreeCreate` executions (on `2.1.300`) and duplicate `SessionStart` reports.
3. **Coexistence with the exact same expanded command (plugin var vs legacy absolute path string):** both run — **2 `SessionStart` executions on both versions** and **2 `WorktreeCreate` executions on `2.1.300`** (floor: 1, because its plugin `WorktreeCreate` is absent), distinguished only by exported `CLAUDE_PLUGIN_ROOT`. The documented settings-only identical-handler dedupe does **not** merge a plugin copy against a settings copy. Leaving duplicate `WorktreeCreate` handlers in place is unsafe (multi-handler selection is undocumented), though **winner identity is not observable in this run** because both stubs return the same `HOOKS_TARGET` path; the harness asserts execution counts only, and a distinct-target probe would be required to observe selection.
4. **Post-migration (settings hooks removed, plugin enabled):** plugin alone drives both events on `2.1.300`; on the floor `SessionStart` remains plugin-driven while `WorktreeCreate` falls back to Git's default worktree path (observed `<repo>/.claude/worktrees/<name>`).
5. **Disabled plugin = negative control:** zero executions of either event on both versions.
6. **Migration dedupe target and merge-engine constraint (recorded, not implemented):**
   - **Desired migration rule:** when the native plugin is enabled, remove **only installer-owned settings `hooks` command entries whose expanded command matches what the plugin ships** (e.g. `bash ~/.claude/hooks/worktree-create.sh` / the herdr `session` registration), and **preserve any independent user-owned hooks in the same event array**. Because plugin and settings copies never dedupe at runtime, anything left in place executes a second time.
   - **Current merge-engine constraint:** [`scripts/merge_managed_config.py`](../../../scripts/merge_managed_config.py) currently models `hooks` with `policy: "map-entries"` (`flatten_leaves` treats each `/hooks/<Event>` array as one atomic leaf, not `list-union`). It **cannot** honor selective command-level removal today. `plan_remove` deletes the whole event array when it equals the source array or matches the last-applied hash; otherwise it preserves the whole array and reports a conflict, unless `--force` requests whole-array deletion. Thus adding an independent user command to a previously managed event prevents normal removal of the installer command too, while forced removal would delete both. For a still-present source event, `plan_merge` likewise preserves a locally changed array with a conflict, or replaces the whole array with the source under `--force`; when an event disappears from the source, stale pruning deletes it only if its whole-array hash still matches, otherwise leaving it untouched. Implementing `install.sh migrate` therefore requires **extending the merge engine** (for example, item-level or command-aware pruning inside `/hooks/<Event>` matcher groups) rather than calling the existing `map-entries` removal as-is.

## 1. Environment & isolation proof

Run: `./scripts/test-claude-hooks-spike.sh --keep` — exit 0, retained at `/tmp/opencode/claude-hooks-spike.bzourQ` (may be deleted later; the committed evidence is this dossier plus hashes).

- Fresh `mktemp -d /tmp/opencode/claude-hooks-spike.XXXXXX` lab (`umask 077`); **no real hooks, no herdr script, no production socket, no real worktree helper, no `HERDR_*` variables** ever executed or inherited (the stub hard-fails if any `HERDR_*` variable reaches it; the driver asserts the lab env carries none).
- `env -i` allowlist: isolated `HOME`, `CLAUDE_CONFIG_DIR`, `XDG_*`, `TMPDIR`, npm cache/config, updater/telemetry disabled, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`. No user plugins, settings, proxies, or credentials copied; no `~/.claude` or `~/.claude.json` is read, so this harness creates no credential fingerprints (unlike YAN-1121); the caller owns any before/after config comparison if desired.
- Lab-local pinned installs only; inference routed to a loopback fake Messages API with a dummy key (headers never logged; HTTP handler reused from the YAN-1121 harness, not its namespace assertions). Egress limitation is **best-effort environment scrubbing, not an OS sandbox/firewall**.
- The recording stub (`record.py`) is a **new safe fixture**: validates the hook JSON event, refuses non-lab paths, rejects a `CLAUDE_PLUGIN_ROOT` that does not identify the executed script's own directory, records event/cwd/session_id/plugin_root/script/sha256 via atomic append, and for `WorktreeCreate` prints a **pre-created fixture worktree path** (created by `git worktree add --detach` in the disposable fixture repo only). No main-repo files, worktrees, or branches touched; stub immutability is hash-asserted after every probe.

| Pinned version | Resolved `--version`    | Lab binary `sha256`                                                |
| -------------- | ----------------------- | ------------------------------------------------------------------ |
| `2.1.143`      | `2.1.143 (Claude Code)` | `f75fdc3ff9d9cd494b86192f9e349b5c5c6d3970ed4d5cd5c7b330c5a2b1dcc4` |
| `2.1.300`      | `2.1.300 (Claude Code)` | `674deba0bba9aee479f4503c438b49303b6fdd304b9a471b14977aaec5215453` |

## 2. Observed matrix

Plugin installed through a **local directory marketplace** (`plugin marketplace add <dir> --scope user` → `plugin install hooks-probe@hooks-spike-<scenario> --scope user`), verified present in `plugin list --json` (`scope: user`, enabled). Although Claude Code also writes a cache copy under `plugins/cache/<market>/<plugin>/0.0.1` (`installPath`), for this directory-source local marketplace `readFromFolder` and the observed runtime `CLAUDE_PLUGIN_ROOT` both resolved to the marketplace source directory (`<LAB>/market-<scenario>/plugin`); execution from `plugins/cache` (or from a remote-source marketplace) was **not** observed or proved here. Not `--plugin-dir`. Each scenario gets a fresh config; `ss` = plain `-p` session, `wt` = `-p --worktree <label>` startup.

| Scenario           | Settings hooks                         | Plugin hooks                   | `2.1.143` ss / wt  | `2.1.300` ss / wt  | Selected path (wt)                                               |
| ------------------ | -------------------------------------- | ------------------------------ | ------------------ | ------------------ | ---------------------------------------------------------------- |
| `baseline`         | none                                   | none                           | 0 / 0              | 0 / 0              | Git default                                                      |
| `settings-only`    | both events                            | none                           | SS 1 / WC 1 + SS 1 | SS 1 / WC 1 + SS 1 | **stub path**                                                    |
| `plugin-only`      | none                                   | both events                    | SS 1 / WC 0 + SS 1 | SS 1 / WC 1 + SS 1 | floor: Git default; 300: **stub path**                           |
| `coexist-distinct` | both (absolute legacy command)         | both (`${CLAUDE_PLUGIN_ROOT}`) | SS 2 / WC 1 + SS 2 | SS 2 / WC 2 + SS 2 | stub path (both return same `HOOKS_TARGET`; winner unobservable) |
| `coexist-exact`    | both (literal expanded plugin command) | both                           | SS 2 / WC 1 + SS 2 | SS 2 / WC 2 + SS 2 | stub path (both return same `HOOKS_TARGET` on 2.1.300)           |
| `post-migration`   | removed                                | both                           | SS 1 / WC 0 + SS 1 | SS 1 / WC 1 + SS 1 | floor: Git default; 300: **stub path**                           |
| `disabled-plugin`  | none                                   | both, `plugin disable`         | 0 / 0              | 0 / 0              | Git default                                                      |

Counts are per-event marker/origin counts from actual recorded executions; SessionStart counts in `wt` rows are those observed inside the worktree session (cwd = the selected path). Origin attribution uses the presence of exported `CLAUDE_PLUGIN_ROOT` (plugin copy) vs its absence (settings copy); in `coexist-exact` both copies execute the same marketplace-source script file (`<LAB>/market-coexist-exact/plugin/record.py`), so totals — not markers — carry the dedupe finding.

### Key sanitized excerpts

`2.1.300` `coexist-exact-wt` records (exact order appended in `run-2.1.300/logs/coexist-exact-wt.records.jsonl`: for `WorktreeCreate`, the plugin-origin copy with `plugin_root` set appended first and the settings-origin copy with `plugin_root: ""` appended second; for `SessionStart`, the settings-origin copy with `plugin_root: ""` appended first and the plugin-origin copy with `plugin_root` set appended second):

```json
{"event":"WorktreeCreate","marker":"plugin","plugin_root":"<LAB>/market-coexist-exact/plugin","cwd":"<LAB>/work","input_cwd":"<LAB>/work"}
{"event":"WorktreeCreate","marker":"plugin","plugin_root":"","cwd":"<LAB>/work","input_cwd":"<LAB>/work"}
{"event":"SessionStart","marker":"plugin","plugin_root":"","cwd":"<LAB>/target-coexist-exact"}
{"event":"SessionStart","marker":"plugin","plugin_root":"<LAB>/market-coexist-exact/plugin","cwd":"<LAB>/target-coexist-exact"}
```

`2.1.143` `coexist-distinct-wt` (settings copy present, plugin `WorktreeCreate` absent on the floor):

```json
{"event":"WorktreeCreate","marker":"settings","plugin_root":"","cwd":"<LAB>/work","input_cwd":"<LAB>/work"}
{"event":"SessionStart","marker":"settings","cwd":"<LAB>/target-coexist-distinct"}
{"event":"SessionStart","marker":"plugin","plugin_root":"<LAB>/market-coexist-distinct/plugin","cwd":"<LAB>/target-coexist-distinct"}
```

Per-probe checks beyond counts: stub `sha256` immutability, `input.cwd` == executed `os.getcwd()`, `WorktreeCreate` executes in the fixture repo while `SessionStart` executes in the **selected** worktree, init `cwd` equals the selected path (stub path, or Git default `.claude/worktrees/<label>` when no plugin hook supplied one), fixture plugin files unchanged after probes, and every CLI run reached the loopback fake API (egress to anywhere else is not blocked or asserted).

## 3. Sanitized evidence SHA-256 (retained run)

| File                                              | SHA-256                                                            |
| ------------------------------------------------- | ------------------------------------------------------------------ |
| `transcript.log`                                  | `44d9bbdc2e9eeb45139e53469797ca93a27b66363f5149cb458f842836922ffc` |
| `run-2.1.143/results.json`                        | `60c7a88963c4010a9b51232b73455b486354f76aeab8ee75a35c9fb83b86ec1a` |
| `run-2.1.300/results.json`                        | `219199da0e4e9cf261b916bf996792bd11d7a7a281fcaf76bb8b639fb33f5312` |
| `run-2.1.143/logs/coexist-exact-wt.records.jsonl` | `e25c5866f2fcfcf9bf4cce56c9f5279aff6c08f5c978f9444a04a0d1d212a885` |
| `run-2.1.300/logs/coexist-exact-wt.records.jsonl` | `e9e768aea37f7fb6a03fbb61e778c2add187b44d96237be9eb40411a8db4d9fc` |
| `run-2.1.300/logs/plugin-only-wt.records.jsonl`   | `950c8ecb336620848144fde7093c008a771be9e0729dfda187ab5d5e42cc6833` |

Retained-lab scan: `grep -rl 'sk-ant-'` matched only the upstream npm vendor binaries (opaque upstream constants); the dummy key appears nowhere in captured evidence; `grep -rIl '/home/yandy'` found no real-home paths in the retained lab after npm cache removal (the harness deletes its own `npm-cache` on exit because npm debug logs name host paths).

## 4. Limitations

1. **Execution-count evidence (not winner selection):** with 2+ `WorktreeCreate` executions, this matrix proves both handlers ran, not which path won: both plugin and settings stubs returned the same pre-created `HOOKS_TARGET`, so winner identity is structurally unobservable and is not asserted. A coexist migration that leaves duplicate `WorktreeCreate` handlers is still unsafe (multi-handler selection is undocumented); a distinct-target probe would be required to observe any selection behavior.
2. **No failure/no-path negative control** (nonzero exit / no path → abort): out of scope to keep the matrix narrow; the docs claim was not re-verified here.
3. **Argument-passing fidelity:** the plugin `SessionStart` command uses the herdr-style `... session` argv suffix; settings-vs-plugin parity for stdin JSON and argv was observed but the real herdr socket flow was intentionally never exercised. Only the loopback fake API and fixture Git were "external" systems touched.
4. **Version coverage:** exactly 2.1.143 and 2.1.300; the harness fail-closes (`choices`) on other versions. The floor no-go is inferred for any version between 2.1.143 and 2.1.300 only via the recorded CHANGELOG trail, not per-version testing.
5. **Migration dedupe is recorded, not implemented;** the managed-entries constraint in the verdict must be handled by the install.sh merge engine work (separate issue).
6. No OS-level sandbox; timeouts are 75s per CLI invocation, 180s per install, 800s per version matrix, 1800s total, with process-group kills of CLI, driver, and npm groups on failure/signals.

## 5. Reproduction

```bash
./scripts/test-claude-hooks-spike.sh --keep          # both pinned versions
./scripts/test-claude-hooks-spike.sh --output-dir /tmp/opencode
```

Fail-closed: exit 0 requires both versions to print `<version> assert_matrix: all expectations verified`; missing markers, unexpected counts, non-lab paths, or unsupported versions exit nonzero. The floor's plugin `WorktreeCreate` absence is asserted as expected evidence (0 plugin-origin executions), so a future floor regression that fires it fails the matrix loudly.

Authoring checks: `bash -n`, `shellcheck` 0.10.0 (repo pin) on the shell script; `ruff check` + `py_compile` on both Python modules. Full sync/validate deliberately not run: no skills, agents, or generated sources were modified.
