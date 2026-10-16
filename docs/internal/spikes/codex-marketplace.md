# Codex Marketplace Discovery, Sparse Checkout, and Hook Parity Spike (YAN-1123)

- **Date:** 2026-10-15
- **Issue:** `YAN-1123`
- **Target CLI:** `codex-cli 0.161.0`
- **Harness:** [`scripts/test-codex-marketplace-spike.sh`](../../../scripts/test-codex-marketplace-spike.sh)

## Executive Decisions

1. **Native repository marketplace catalog location and plugin source form:**
   - A repository configured via `codex plugin marketplace add <git-source>` is discovered through `.agents/plugins/marketplace.json` first, falling back to `.claude-plugin/marketplace.json` only when `.agents/plugins/marketplace.json` is absent.
   - Because this repository already ships `.claude-plugin/marketplace.json` pointing at `./ycc` (Claude Code plugin layout, which lacks `.codex-plugin/plugin.json`), any repo-level Codex catalog **must** live at `.agents/plugins/marketplace.json` with a root-relative `local` plugin source (`{"source": "local", "path": "./.codex-plugin/ycc"}`) or remain in the user-level `~/.agents/plugins/marketplace.json` using `git-subdir` (`{"source": "git-subdir", "url": "https://github.com/yandy-r/claude-plugins.git", "path": "./.codex-plugin/ycc", "ref": "main"}`), as implemented by [`scripts/codex_marketplace.py`](../../../scripts/codex_marketplace.py).
2. **Sparse checkout requirements for `local` plugin sources:**
   - When a Git marketplace catalog uses `"source": "local"` with a root-relative `./...` path and the user passes `--sparse`, the sparse checkout list **must** include **both** the catalog directory (`.agents/plugins`) **and** the plugin payload directory (e.g. `.codex-plugin/ycc`).
   - Passing `--sparse .agents/plugins` alone allows `marketplace add` and `plugin list --available` to succeed, but `codex plugin add` fails (`exit=1`, `Error: missing plugin.json`) because local-source resolution reads directly from the sparse marketplace checkout under `$CODEX_HOME/.tmp/marketplaces/<name>/`.
3. **Codex `ycc` hook parity (`WorktreeCreate` and `herdr` `SessionStart`):** **No-Go.**
   - **`WorktreeCreate`:** **No-Go (unsupported).** `WorktreeCreate` is absent from Codex's `HookEventName` schema and ignored during `hooks/hooks.json` discovery.
   - **Plugin hooks (`SessionStart` / `herdr`):** **No-Go.** Although `hooks/list` discovers `SessionStart` from an installed plugin's `hooks/hooks.json`, this harness observed plugin hooks only as `trustStatus: "untrusted"`, the `plugin_hooks` feature flag is `removed` (`false`), and trust grant plus runtime dispatch were not exercised by this harness (no session, turn, or inference was started). Absent verified trust and dispatch evidence, keep `ycc` / `herdr` hooks out of the Codex plugin bundle.

---

## 1. Live-Verified Facts (`codex-cli 0.161.0`)

All live observations below were produced by running `./scripts/test-codex-marketplace-spike.sh --keep` in an `env -i` sandbox (`HOME`, `CODEX_HOME`, `XDG_*`, and `TMPDIR` under `/tmp/opencode`; `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `credential.helper=`, `GIT_ALLOW_PROTOCOL=file`, working directory outside the repository, no auth or user config copied).

### 1.1 Marketplace Source URL Acceptance & Offline Git Transport

- `codex plugin marketplace add file://<bare-repo>` fails immediately with `exit=1` and stderr:

  ```text
  Error: invalid marketplace source format; expected owner/repo, a git URL, or a local marketplace path
  ```

- `codex plugin marketplace add https://codex-spike.invalid/fixture.git --ref <sha> --json` is accepted by Codex's URL parser as an HTTPS Git marketplace source and cloned into `$CODEX_HOME/.tmp/marketplaces/<marketplace-name>` via `git` using an isolated `url.file://<bare>.insteadOf=https://codex-spike.invalid/...` rewrite with `GIT_ALLOW_PROTOCOL=file` (Git transport restricted to `file://`; this exercised path requires no network).

### 1.2 Observed Discovery & Install Matrix

> **Historical per-run values:** Fixture commit SHAs, hook `currentHash` values, SHA-256 digests, and `/tmp/opencode/codex-marketplace-spike.*` sandbox/transcript paths in this document are records from the verified run in `codex-marketplace-spike.u9S6zp` on `codex-cli 0.161.0`. They are not stable identifiers: commit SHAs change with each run's commit timestamps, sandbox paths come from `mktemp -d`, and the hook hash is computed by Codex and may depend on inputs beyond the fixture bytes. Compare behavior (exit codes, selected marketplace, marker content), not these literal values.

Fixtures built by the harness:

- **Dual-catalog bare repo (`fixture.git`, historical per-run commit `dca13c0a134c9bc93a5dc9d5e1e08825fe958fbd`):**
  - `.agents/plugins/marketplace.json`: marketplace `spike-native`, plugin `native-plugin`, source `{"source": "local", "path": "./.codex-plugin/native"}`, marker `NATIVE-MARKER` (`sha256=28ae6dfdfa16f596de8d1c0c6d7910c50368b048b3eb00d42c187cfd8a1dfcaa`).
  - `.claude-plugin/marketplace.json`: marketplace `spike-claude`, plugin `claude-plugin`, source `"./claude-plugin-payload"`, marker `CLAUDE-MARKER` (`sha256=a395f3be97249ac236dafa1513d196fa1c8b5208a32f7c9e8c092df112dfdac6`).
- **Claude-only bare repo (`claude.git`, historical per-run commit `20c09c2b037109126fc461a2e9d53fee7ff0ea2b`):**
  - Contains only `.claude-plugin/marketplace.json` and `claude-plugin-payload/`.

| Case                                        | Source & Flags                                                                                                                                       | `marketplace add`                              | Selected Marketplace                                        | `plugin list --available`                                  | `plugin add`                            | Installed Cache & Marker Verification                                                                                                                                                   |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------------------------- | ---------------------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `file-url` (negative control)               | `file://<SANDBOX>/fixture.git`                                                                                                                       | `exit=1` (`invalid marketplace source format`) | n/a                                                         | n/a                                                        | n/a                                     | Rejected before Git clone                                                                                                                                                               |
| `full` (both catalogs present)              | `https://codex-spike.invalid/fixture.git --ref <commit>`                                                                                             | `exit=0`                                       | `spike-native` (`.agents/plugins/marketplace.json` wins)    | `native-plugin@spike-native` (`version: "0.0.1"`)          | `exit=0`                                | `$CODEX_HOME/plugins/cache/spike-native/native-plugin/0.0.1/skills/marker/SKILL.md` matches `NATIVE-MARKER` (`sha256=28ae6dfdfa16f596de8d1c0c6d7910c50368b048b3eb00d42c187cfd8a1dfcaa`) |
| `sparse-catalog` (catalog-only sparse)      | `https://codex-spike.invalid/fixture.git --ref <commit> --sparse .agents/plugins`                                                                    | `exit=0`                                       | `spike-native`                                              | `native-plugin@spike-native`                               | `exit=1` (`Error: missing plugin.json`) | Cache directory absent; checkout under `.tmp/marketplaces/spike-native` contains only `.agents/plugins/marketplace.json`                                                                |
| `sparse-payload` (catalog + payload sparse) | `https://codex-spike.invalid/fixture.git --ref <commit> --sparse .agents/plugins --sparse .codex-plugin/native`                                      | `exit=0`                                       | `spike-native`                                              | `native-plugin@spike-native` (`version: "0.0.1"`)          | `exit=0`                                | `$CODEX_HOME/plugins/cache/spike-native/native-plugin/0.0.1/skills/marker/SKILL.md` matches `NATIVE-MARKER` (`sha256=28ae6dfdfa16f596de8d1c0c6d7910c50368b048b3eb00d42c187cfd8a1dfcaa`) |
| `claude-only` (fallback control)            | `https://codex-spike.invalid/claude.git --ref <commit2>`                                                                                             | `exit=0`                                       | `spike-claude` (`.claude-plugin/marketplace.json` fallback) | `claude-plugin@spike-claude` (`version: "0.0.1"`)          | `exit=0`                                | `$CODEX_HOME/plugins/cache/spike-claude/claude-plugin/0.0.1/skills/marker/SKILL.md` matches `CLAUDE-MARKER` (`sha256=a395f3be97249ac236dafa1513d196fa1c8b5208a32f7c9e8c092df112dfdac6`) |
| `git-subdir` (catalog entry control)        | Local catalog with `{"source": "git-subdir", "url": "https://codex-spike.invalid/fixture.git", "path": "./.codex-plugin/native", "ref": "<commit>"}` | `exit=0`                                       | `spike-subdir`                                              | `native-plugin@spike-subdir` (`version: null` pre-install) | `exit=0`                                | `$CODEX_HOME/plugins/cache/spike-subdir/native-plugin/0.0.1/skills/marker/SKILL.md` matches `NATIVE-MARKER` (`sha256=28ae6dfdfa16f596de8d1c0c6d7910c50368b048b3eb00d42c187cfd8a1dfcaa`) |

### 1.3 Live Hook Schema & Discovery Evidence

1. **Protocol schema (`codex app-server generate-json-schema --experimental --out <dir>`):**
   - `v2/HooksListResponse.json` defines `HookEventName` as:

     ```json
     [
       "preToolUse",
       "permissionRequest",
       "postToolUse",
       "preCompact",
       "postCompact",
       "sessionStart",
       "sessionEnd",
       "userPromptSubmit",
       "subagentStart",
       "subagentStop",
       "stop",
       "interrupt"
     ]
     ```

   - `worktreeCreate` / `WorktreeCreate` is **not** in `HookEventName`.
   - `HookTrustStatus` is `["managed", "untrusted", "trusted", "modified"]`.
   - `HookSource` includes `"plugin"`.
2. **Feature flags (`codex features list`):**
   - `hooks` is `stable` (`true`), `plugins` is `stable` (`true`), and `plugin_hooks` is `removed` (`false`).
3. **JSON-RPC metadata probe (`codex app-server --stdio` -> `initialize` + `hooks/list`):**
   - With `native-plugin@spike-native` installed in `$CODEX_HOME/plugins/cache/spike-native/native-plugin/0.0.1` and containing `hooks/hooks.json` with both `SessionStart` and `WorktreeCreate` no-op recording entries, `hooks/list` returned:
     - Exactly 1 hook entry: `key: "native-plugin@spike-native:hooks/hooks.json:session_start:0:0"`, `eventName: "sessionStart"`, `source: "plugin"`, `pluginId: "native-plugin@spike-native"`, `enabled: true`, `trustStatus: "untrusted"`, `currentHash: "sha256:3d2bb4fc82ef0f87f9e869381667b6869fb887257c2caceb118885d54477c4be"` (verified sample from the historical `u9S6zp` run; recomputed per run).
     - `WorktreeCreate` was silently dropped (`warnings: []`, `errors: []`).

---

## 2. Upstream Source Evidence (`openai/codex` `rust-v0.161.0`)

> **Source-review caveat:** The line ranges below were supplied by the task scope for `openai/codex` tag `rust-v0.161.0`. This spike did not fetch or read those files (network access was out of scope), so the bullet descriptions are the expected role of each range, consistent with the live observations in section 1, and have **not** been verified line-by-line against upstream. Treat them as pointers for a follow-up source read, not as confirmed source evidence.

Pointers for the `rust-v0.161.0` source ranges:

- **Catalog relative paths & discovery precedence** — [`codex-rs/core-plugins/src/marketplace.rs` lines 20-25](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L20-L25) and [lines 328-337](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L328-L337):
  - Defines the native catalog relative path (`.agents/plugins/marketplace.json`) ahead of the Claude compatibility fallback (`.claude-plugin/marketplace.json`), and resolves the first existing catalog under the marketplace root.
- **Plugin source schema (`local`, `url`, `git-subdir`, `npm`, and Claude string shorthand) & root-relative `./` validation** — [`codex-rs/core-plugins/src/marketplace.rs` lines 677-718](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L677-L718):
  - Parses tagged plugin source objects (`local`, `url`, `git-subdir`, `npm`) alongside bare relative string paths (used by `.claude-plugin/marketplace.json`) and enforces that local plugin paths remain relative to the marketplace root (`./...`).
- **Git marketplace staging, sparse checkout application, and local-path resolution** — [`codex-rs/core-plugins/src/marketplace.rs` lines 980-992](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L980-L992):
  - Clones/Stages Git marketplaces into `$CODEX_HOME/.tmp/marketplaces/<name>` and applies `--sparse` paths via `git sparse-checkout`; when a catalog entry uses a local relative path, `plugin add` copies from that checkout directory and requires `.codex-plugin/plugin.json` to exist on disk.
- **Supported hook event surface** — [`codex-rs/hooks/src/lib.rs` lines 22-36](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/hooks/src/lib.rs#L22-L36):
  - Exports the hook event types (`PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `SubagentStart`, `SubagentStop`, `Stop`, `Interrupt`) without `WorktreeCreate`.

---

## 3. Limitations & Unverified Boundaries

1. **Hook trust transition & runtime command dispatch are unverified offline:**
   - This harness uses `hooks/list` only for read-only metadata inspection. It does not exercise any CLI or JSON-RPC mechanism to mark an `"untrusted"` plugin hook as `"trusted"`, trigger `SessionStart`, or compare trusted vs. untrusted dispatch. This is a boundary of the harness, not evidence that no such mechanism exists.
   - Because live inference, login, and real `ycc` / `herdr` socket execution are out of bounds for this hermetic harness, runtime dispatch of trusted vs. untrusted plugin hooks remains unverified and is treated as a **No-Go** for shipping `ycc` hooks in Codex.
   - **Follow-up (YAN-1149):** the trust grant and trusted/untrusted/modified dispatch gap above was exercised separately with a recording-only plugin and a loopback no-inference stub; see [`codex-hook-trust.md`](codex-hook-trust.md). The conclusions here for shipping `ycc` / `herdr` hooks and `WorktreeCreate` are unchanged.
2. **Direct `file://` marketplace URLs are rejected by CLI parsing:**
   - The installed CLI's help advertises local paths, `owner/repo[@ref]`, HTTPS Git URLs, and SSH Git URLs. The live negative control verifies rejection of a direct `file://` marketplace argument; the successful Git marketplace cases use an `.invalid` HTTPS URL rewritten to `file://` via isolated `GIT_CONFIG_*` environment variables with `GIT_ALLOW_PROTOCOL=file`.
3. **Public GitHub transport was not tested:**
   - No public GitHub `owner/repo` source, public HTTPS/SSH transport, authentication, or real remote repository was exercised. The local Git rewrite verifies catalog discovery, sparse checkout, relative sources, and cache installation after CLI URL parsing; it is **not proof** of the public GitHub transport boundary.
4. **Network isolation scope:**
   - Isolation is enforced only for Git transport (`GIT_ALLOW_PROTOCOL=file` with `url.<base>.insteadOf` rewrites, no system/global git config, empty credential helper, `GIT_TERMINAL_PROMPT=0`) and for authentication/config (fresh `HOME`, `CODEX_HOME`, `XDG_*`; no credentials copied). The exercised CLI/RPC code paths require no network, but non-Git process egress is **not OS-sandboxed**; nothing in the harness would block an unexpected outbound connection.

---

## 4. Reproduction Command & Transcript Summary

Run the hermetic harness from the repository root:

```bash
./scripts/test-codex-marketplace-spike.sh --keep
```

Historical summary from the independently verified run on `codex-cli 0.161.0` (`/tmp/opencode/codex-marketplace-spike.u9S6zp/transcript.log`, exit 0) — an ephemeral example transcript, retained only by `--keep` and subject to `/tmp` cleanup. Commit SHAs and transcript paths below identify that run only, not stable reproduction inputs:

```text
YAN-1123 | codex-cli 0.161.0 | offline Git fixture | 2026-10-15
Immutable fixture commits: dual=dca13c0a134c9bc93a5dc9d5e1e08825fe958fbd claude-only=20c09c2b037109126fc461a2e9d53fee7ff0ea2b
PASS file:// marketplace URL rejected; HTTPS-shaped alias uses file-only Git transport
PASS full | selected=spike-native | available=native-plugin | install=0 | cache marker/hash verified
PASS sparse-catalog | selected=spike-native | available=native-plugin | install=1 (expected missing sparse payload) | marker=absent
PASS sparse-payload | selected=spike-native | available=native-plugin | install=0 | cache marker/hash verified
PASS claude-only | selected=spike-claude | available=claude-plugin | install=0 | cache marker/hash verified
PASS git-subdir | selected=spike-subdir | available=native-plugin | install=0 | cache marker/hash verified
PASS hooks metadata | SessionStart discovered untrusted + sha256 | WorktreeCreate absent
NO-GO hooks runtime: trust grant and trusted/untrusted dispatch unverified; no inference/session started
PASS: 5 marketplace matrix cases + file:// rejection + installed hook schema/discovery
Transcript: /tmp/opencode/codex-marketplace-spike.u9S6zp/transcript.log
Retained transcript: /tmp/opencode/codex-marketplace-spike.u9S6zp/transcript.log (exit=0)
```
