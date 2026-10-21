# OpenCode Plugin Native Registration Spike (YAN-1125)

- **Date:** 2026-10-15
- **Issue:** `YAN-1125` (GitHub #290); target release `v6.0.0`
- **Question:** Can an OpenCode plugin natively register skills, agents, commands, MCP and instructions on the installed **opencode v2.0.29**? The original issue assumed a V1 `config` hook on opencode 1.19, but V1 support was dropped (Linear YAN-1118 canceled; the generated config is V2-only), so the decision is made against the installed V2 binary and V1 is only a negative control.
- **Harness:** [`scripts/test-opencode-config-hook-spike.sh`](../../../scripts/test-opencode-config-hook-spike.sh) + [`scripts/opencode_config_hook_spike.py`](../../../scripts/opencode_config_hook_spike.py) + fixtures/checks in [`scripts/opencode_config_hook_checks.py`](../../../scripts/opencode_config_hook_checks.py) (opt-in, not wired into CI)

## Executive verdict

1. **Plugin registrations: Go for agents, commands, skills and MCP.** A local V2 plugin (`{ id, setup }` default export) registered one agent, one command, one skill (inline content + `path` into a fixture directory holding a relative support file) and one local MCP server, all observable through the location-scoped read-only APIs with per-run random markers. Plugin state was `active` and the MCP stdio stub was `connected` in some runs and `pending` at read time in others (registration is asserted; connection status is recorded as observed, not asserted).
2. **Instructions from a plugin `session.hook("context", ...)`: Go.** The hook's pushed system part reached the outgoing model request on the loopback fake provider. This is the only plugin-side instruction mechanism: **there is no instructions transform** in the V2 plugin API.
3. **Config `instructions` array: No-Go on v2.0.29.** The key is accepted by config schema and the v2 docs, but [`packages/core/src/config/plugin/instruction.ts` at tag v2.0.29](https://github.com/anomalyco/opencode/blob/v2.0.29/packages/core/src/config/plugin/instruction.ts) (raw source read during this spike) reads only the global `~/.config/opencode/AGENTS.md` and ancestor `AGENTS.md` files. A config `instructions: ["<file>"]` entry did **not** reach the model request, while a discovered `AGENTS.md` in the same run did (positive control). At the time, this matched the generator comment's claim that V2 "accepts the field but does not resolve its entries". Superseded on v2.1.1: a config `instructions` entry reaches the model (YAN-1241), and the bundle still omits the key for the reason given in `scripts/generate_opencode_plugin.py`.
4. **Skills from config: Go.** Both `skills: ["<dir>"]` and a loopback HTTP catalog (`index.json` + files) listed with markers. The catalog cache lives at `<XDG_CACHE_HOME>/opencode/skills/<sha1-of-source>/<skill>/<file>` (hashed per source URL), with a `.opencode-version` marker beside the files. Refresh/version-change semantics were not tested.
5. **V1 hook-style plugin: No-Go (expected negative control).** A `export const P = async () => ({ config(cfg) {...} })` module configured via `plugins` failed to load with state `failed` and error `"Plugin must export a default definition with an id and an effect or setup function."` ([`packages/core/src/plugin/module.ts` at tag v2.0.29](https://github.com/anomalyco/opencode/blob/v2.0.29/packages/core/src/plugin/module.ts), read during this spike, accepts only `{ id, setup }` / `{ id, effect }` default exports). Nothing registered.
6. **Configured local plugin must be a directory: bare `file://` file entries are ignored.** `plugins: ["file://…/index.js"]` produced no plugin inventory entry, no API error and no registrations; the server log does carry a WARN `configured plugin path must be a directory` (retained `server-configured-file-negative.log:3`). The directory form (`file://…/v2-plugin`) loads. Recorded because the v2 plugin docs show `.ts` file entries and auto-discovery of direct files under `.opencode/plugins/`, while configured entries in v2.0.29 resolve directories only (`config/plugin/source.ts` logs _"configured plugin path must be a directory"_ — warning observed in source and server log; no API inventory entry or API error). Auto-discovery of `.opencode/plugins/*.ts` was observed live in an earlier scratch run (plugin loaded and registered) but is **not** part of the committed matrix.

### V2 API timing/stability notes

- The v2 plugin API is the current documented API (opencode.ai/v2/docs/build/plugins documents `Plugin.define`, transforms and hooks). The spike pinned exactly **v2.0.29** (`--version` asserted; binary sha256 `7e23471f4ebe2313d78baacc9ac96fe9e197ce26d808de4b0fcc37efbe473dad`); behavior of other builds is unverified.
- **Deferred plugin activation:** `/api/plugin` (and siblings) initially return empty arrays right after the HTTP listener is up; the registries populate asynchronously. Read-only polls immediately after readiness can see empty inventories that are not failures. The harness waits for the built-in `opencode.config.skill` plugin to appear before asserting.
- **Transforms return Promises** in the promise-shape plugin; the probe awaits each `ctx.*.transform(...)` before `setup` resolves.
- `session.hook("context")` mutates a single event object: `event.system.push({ type: "text", text })` (typed `SystemPart`; a bare string push fails schema validation and the session errors out — observed while bringing the probe up).
- Command registration requires `{ name, description?, execute }` (async function); the V1-era `template`-style config command belongs in config `commands`, not the plugin transform.
- Skill guidance is injected per model call; the loaded skill body arrives as a user-role `<skill_content>` block, not in the system prompt.

### Source provenance (independent tag reads)

The local `/tmp/opencode/opencode-src` checkout is **v2.0.26**, not the runtime under test; it is not the basis for the exact-tag claims above. The implementation session read the following v2.0.29 raw GitHub tag sources directly (the first three were re-fetched during review correction):

- [Instruction loader](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/core/src/config/plugin/instruction.ts): global/ancestor `AGENTS.md` discovery, no config `instructions` entry resolver.
- [Plugin source scanner](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/core/src/config/plugin/source.ts): configured file-path warning and omission.
- [Module loader](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/core/src/plugin/module.ts): default-export `id` + `setup`/`effect` schema.
- [Promise context](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/plugin/src/promise/plugin.ts), [adapter](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/plugin/src/promise/adapter.ts), and [session event types](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/plugin/src/promise/session.ts): registration promises, exposed domains and system-part event shape.
- [Agent](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/core/src/agent.ts), [command](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/core/src/command.ts), and [skill](https://raw.githubusercontent.com/anomalyco/opencode/v2.0.29/packages/core/src/skill.ts) registries: update/add/execute contracts and skill base-directory output. These corroborate, rather than substitute for, the live v2.0.29 observations.

## 1. Environment & isolation proof

Run: `./scripts/test-opencode-config-hook-spike.sh --keep` — exit 0, retained at `/tmp/opencode/opencode-config-hook-spike.DSLLtL` (may be deleted later; committed evidence is this dossier plus hashes).

- Fresh `mktemp -d /tmp/opencode/opencode-config-hook-spike.XXXXXX` lab (`umask 077`); **no real service, config, DB or home writes**. The user's `~/.config/opencode/opencode.json`, top-level `~/.config/opencode/` entries (files, dirs, symlinks; mode/size/mtime/inode) and `~/.local/state/opencode/service.json` are fingerprinted before/after (metadata plus sha256 of those two files only; contents never copied) and the harness fails if anything differs. No bare `opencode`/`opencode api` ever runs: every child server is `opencode serve --hostname 127.0.0.1 --port <free>` under the lab env, and all API access is direct HTTP to that private port with the lab-set `OPENCODE_SERVER_PASSWORD` (Basic auth), equivalent to `opencode api --server http://127.0.0.1:<port>` — confirmed against the server's own `/openapi.json` (routes `/api/{plugin,skill,agent,command,mcp}`, deepObject `location[directory]` query parameter on each).
- `env -i` allowlist: lab `HOME`, `XDG_{CONFIG,DATA,STATE,CACHE,RUNTIME}_HOME`, `TMPDIR`, `OPENCODE_DB`, `OPENCODE_SERVER_PASSWORD`, models-fetch/FFF/filewatcher disabled, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`. No user plugins, auth, proxies, `NODE_OPTIONS` or service discovery inherited. Each server runs in its own process group under `timeout -k 3 120`; the driver is bounded by `timeout -k 10 480`; groups are killed on exit/signal.
- Network is loopback only: the HTTP skills catalog and the fake OpenAI-compatible provider both bind `127.0.0.1` ephemeral ports (stdlib `http.server`). The provider uses a dummy key; headers are never logged. Egress elsewhere is **not blocked** — isolation is best-effort environment scrubbing, not an OS sandbox/firewall.
- Config per scenario is written to `<lab>/config/opencode/opencode.json` with `update: "disable"`; scenario project dirs under `<lab>/work/<scenario>` are fresh; fixtures (plugin dirs, skills, catalog, MCP stub) are plain files generated per run with a unique marker `yan1125-<12 hex>`.

## 2. Observed matrix

Read-only evidence via `GET /api/{plugin,agent,command,skill,mcp}?location[directory]=<lab>/work/<scenario>`; instruction evidence via captured request bodies on the loopback fake provider. "marker" = the run's unique random marker string present in the JSON payload.

| Scenario                   | Config                                                          | Evidence                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `baseline`                 | none                                                            | 0 custom plugins; marker absent in all five inventories                                                                                                                                                                                                                                                                                                                                                   |
| `configured-file-negative` | `plugins: ["file://…/index.js"]` (bare file)                    | 0 custom plugins, marker absent everywhere (no API inventory entry/API error; server WARN `configured plugin path must be a directory`)                                                                                                                                                                                                                                                                   |
| `v2-plugin`                | `plugins: ["file://…/v2-plugin"]` (directory)                   | plugin `yan1125.probe` **active** (`source: local`); agent `yan1125-agent` (update transform), command `yan1125-cmd` (add + async `execute`), skill `yan1125-skill` (add with `path` into fixture dir + inline `content`), MCP `<marker>-mcp` registered, status **connected** in the retained run (earlier runs: `pending` at read time)                                                                 |
| `config-skills-dir`        | `skills: ["<fixtures/skills>"]`                                 | skill `dir-skill` listed once, marker in description; path is the fixture `SKILL.md`                                                                                                                                                                                                                                                                                                                      |
| `config-skills-url`        | `skills: ["http://127.0.0.1:<p>/"]`                             | skill `yan1125-url` listed, marker present; served from loopback `index.json` catalog; cached under `cache/opencode/skills/<40-hex>/<name>/` incl. `support.md` + `.opencode-version`                                                                                                                                                                                                                     |
| `v1-negative`              | `plugins: [{package: "file://…/v1-plugin"}]`                    | plugin state **failed**: `"Plugin must export a default definition with an id and an effect or setup function."` (ref `err_<run-specific>`); no agents/commands/skills/MCP registered                                                                                                                                                                                                                     |
| `instructions`             | `instructions: ["<file>"]` + v2-plugin + discovered `AGENTS.md` | 1 captured model request on fake provider: config marker absence checked over all captured bodies; hook + discovered-AGENTS positives required together in a single request system message; hook marker **in system**, discovered-`AGENTS.md` marker **present**, config-`instructions` marker **absent**, skill block present as user-role `<skill_content>` with `Base directory for this skill: <dir>` |

### Key sanitized excerpts

From the retained run (`work/instructions`, system prompt of the single captured request; `<LAB>` = retained lab root):

```text
…Instructions from: <LAB>/work/instructions/AGENTS.md
yan1125-<marker> discovered-agents
…call `tools.opencode.session_move` and make the worktree the session's working directory.
yan1125-<marker> hook-instruction
```

`yan1125-<marker> config-instruction` appears nowhere in the request (find index −1), although the same config carried `instructions: ["<LAB>/fixtures/instructions.md"]` containing exactly that marker — the positive controls in the same request prove the pipeline was live.

User-role skill block (abridged):

```text
<skill_content name="Yan1125 Skill">
# Skill: Yan1125 Skill

yan1125-<marker> inline; Read support.md relative to the skill base.

Base directory for this skill: <LAB>/fixtures/skills/dir-skill
Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.
Note: file list is sampled.

<skill_files>
<file>…support.md</file>
</skill_files>
</skill_content>
```

V1 negative plugin state (`/api/plugin`):

```json
{
  "status": "failed",
  "error": "Plugin must export a default definition with an id and an effect or setup function.",
  "ref": "err_<run-specific>"
}
```

## 3. Sanitized evidence SHA-256 (retained run)

| File                   | SHA-256                                                            |
| ---------------------- | ------------------------------------------------------------------ |
| `transcript.log`       | `ce61cc7d64672eed926d749c4e72c4f65431d44a5a81b36d62231d1148b1a604` |
| `results.json`         | `eb525ccf7f244b6ee8aee5c6b6378d7a50f7c5456c5a9d008d5d6dec2c8e7b3e` |
| `provider-bodies.json` | `b29213722993cb8b8202404a3d1cd79f2223d0a6c6ff968722f79fb480904281` |

## 4. Guidance for generated skill content (shared files)

The V2 skill loader tells the model that relative paths resolve against the skill's base directory (`Base directory for this skill: <dir>` + `Relative paths … are relative to this base directory`), and the observed skill block advertised the base and support-file path from a fixture directory without any absolute paths baked into the markdown. Therefore generated skill content should reference shared helpers **relatively**, not via baked absolute paths. For a skill at `<root>/skills/<skill>/SKILL.md` the exact layout examples are: shared helpers at `<root>/shared/` → reference as `../../shared/scripts/x.sh`; shared helpers at `<root>/skills/_shared/` → reference as `../_shared/scripts/x.sh`.

This contrasts with the current generator: `scripts/generate_opencode_common.py:283-297` rewrites `${CLAUDE_PLUGIN_ROOT}/skills/_shared/...` to absolute `~/.config/opencode/shared/...` paths at generation time because opencode has no plugin-root variable. Under V2 the cleaner shape is to ship `_shared/` as siblings under the installed skills root and keep references relative, relying on the base-directory contract observed here; absolute rewrites remain a valid fallback but couple generated content to one install path (and to home-dir layout). Note this spike only proved the base-directory contract and the adjacent `support.md` presence and listing; a `../_shared/` or `../../shared/` traversal was not executed live — the relative shared layout above is the inferred recommendation, and skill `path` values would point at the on-disk `SKILL.md` under the shared skills root. A production migration decision is out of scope for this spike.

## 5. Limitations

1. Exactly opencode v2.0.29 on Linux x86_64; other versions/architectures unverified. The harness asserts the version and fails otherwise.
2. `--keep` was passed by the final run; earlier scratch runs against the same binary (auto-discovery of `.opencode/plugins/*.ts`, MCP failure states with a malformed stub) informed the dossier but are not part of the committed matrix.
3. MCP connection status is recorded as observed (`connected` in the retained run; `pending` at read time in earlier runs); long-lived reconnect/reconciliation semantics, remote MCP, and OAuth are untested. The stdio stub is a minimal JSON-RPC echo, not a real MCP server.
4. Command/skill/agent registration is asserted through the read-only listing APIs; command **execution** is unverified: the registered definition has a no-op `execute`, but invocation flows were not driven.
5. Instruction conclusion for config `instructions` is backed by (a) live negative observation with same-request positive controls and (b) immutable v2.0.29 source read from GitHub tag raw URLs (module.ts, config/plugin/instruction.ts, config/plugin/source.ts, plugin/promise/plugin.ts, plugin/promise/session.ts, plugin/promise/adapter.ts, core/src/command.ts, core/src/agent.ts, core/src/skill.ts); a glob/URL `instructions` entry was not separately probed (the file form failing is sufficient for the no-go).
6. The `transform-failure` probe (a throwing transform disabling only its plugin) was not implemented; per-plugin failure isolation is unverified.
7. Skill catalog version-refresh behavior (bumping `version`) and cache eviction were not tested.
8. No OS-level sandbox; timeouts bound every subprocess (120 s per server, 480 s driver) and process groups are killed on failure, but network egress outside loopback is not blocked.

## 6. Reproduction

```bash
opencode --version                       # must print: opencode v2.0.29
./scripts/test-opencode-config-hook-spike.sh --keep
./scripts/test-opencode-config-hook-spike.sh --output-dir /tmp/opencode
```

Fail-closed: exit 0 requires the transcript to contain `assert_matrix: all expectations verified`; any mismatched `check()`, unexpected location envelope, missing provider capture, or real-config metadata change exits nonzero. `check()` raises `SystemExit` (no bare asserts, valid under `-O`) and the driver opens with a negative self-test that it must fail closed. Opt-in only: the script is not referenced by `scripts/validate.sh` or CI.

Authoring checks: `bash -n`, `shellcheck` 0.10.0 (repo pin) on the shell script; `ruff check` + `black` (via `npm run format:modified`) + `python3 -m py_compile` on both Python modules. Full sync/validate deliberately not run: no skills, agents, or generated sources were modified.
