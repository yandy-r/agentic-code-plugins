# Codex Plugin Hook Trust Spike (YAN-1149)

- **Date:** 2026-10-16
- **Issue:** `YAN-1149` / GitHub #332 (target `v6.0.0`, `main`, no backport)
- **Target CLI:** `codex-cli 0.160.0` (exact), official Linux x86_64 musl binary, SHA-256 `12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad`
- **Harness:** [`scripts/codex_hook_trust_smoke.py`](../../../scripts/codex_hook_trust_smoke.py)
- **Follows:** [`codex-marketplace.md`](codex-marketplace.md) (YAN-1123), which left the trust grant and runtime dispatch unverified; and [`codex-public-fork-install.md`](codex-public-fork-install.md) (YAN-1163) for the pinned binary and public fixture.

## Verdict

1. **Trust transitions: PASS.** On `codex-cli 0.160.0` a plugin hook is discovered as `untrusted` and does not run; after a `trusted_hash` grant through `config/batchWrite` it reports `trusted` and, in a restarted app-server, runs; after the installed hook file is edited it reports `modified` and does not run.
2. **Adapted reporter: GO for a recording-only `SessionStart` / `UserPromptSubmit` hook.** The probe is a generated recording plugin, not the production `ycc` / `herdr` hook. Nothing in this spike integrates with `herdr`, its scripts, or its sockets.
3. **Production hooks remain No-Go** until an adapted reporter (built on `SessionStart` / `UserPromptSubmit`, not `WorktreeCreate`) is implemented and verified. No hook, catalog, listing, or version change ships from this spike.
4. **`WorktreeCreate`: No-Go, unchanged.** The event is absent from the 0.160.0 `HookEventName` schema (the harness fails closed if it appears). `SessionStart` is an adapted reporter probe, not a substitute for `WorktreeCreate` semantics.

## Reproduce

Prerequisite: the official `0.160.0` binary (obtain and verify as in [`codex-public-fork-install.md`](codex-public-fork-install.md#replay); the harness itself rejects any binary whose SHA-256 differs from the value above or whose `--version` is not `codex-cli 0.160.0`). From the repository root:

```bash
CODEX_BIN=/path/to/codex-x86_64-unknown-linux-musl python3 scripts/codex_hook_trust_smoke.py
```

`CODEX_BIN` is mandatory: there is no `PATH` fallback and no auto-download. The sandbox and `evidence.json` are always retained under `/tmp/opencode` (including on failure), and the script prints `PASS: <sandbox>/evidence.json` (exit 0) or `FAIL: …` (exit 1). Final verified run after review and formatting: `PASS: /tmp/opencode/codex-hook-trust.qa4a_bb5/evidence.json`, 3.12 s. It records `systemConfigAbsent: true`; the initial run also had empty app-server stderr in all three phases. The sandbox path is ephemeral; compare the values below, not the path.

## Observed Trust Transitions

Fixture: a generated local marketplace `hook-trust-spike` (`codex plugin marketplace add <SANDBOX>/fixture --json`, then `codex plugin add recording@hook-trust-spike --json`, both exit 0, plugin version `0.0.1`) with one plugin `recording` whose `hooks/hooks.json` declares two command hooks (timeout 5 s) that run `/usr/bin/python3 hooks/record.py <Event> <revision>`. `record.py` appends `{event, revision, plugin_root, payload_keys}` to a JSONL file outside the plugin.

Hook identities (stable across all phases):

| Key                                                                  | Event              | Matcher   |
| -------------------------------------------------------------------- | ------------------ | --------- |
| `recording@hook-trust-spike:hooks/hooks.json:session_start:0:0`      | `sessionStart`     | `startup` |
| `recording@hook-trust-spike:hooks/hooks.json:user_prompt_submit:0:0` | `userPromptSubmit` | none      |

Both hooks: `source: "plugin"`, `pluginId: "recording@hook-trust-spike"`, `handlerType: "command"`, `enabled: true`, `isManaged: false`, `sourcePath` inside `<CODEX_HOME>/plugins/cache/`.

| Phase (app-server)                    | `hooks/list` trust status | Hook `currentHash` (`sha256:`…)                                                                                    | Record lines before → after | Turn                                 |
| ------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------- | ------------------------------------ |
| 1. `untrusted-and-grant` (initial)    | `untrusted` ×2            | session_start `0e458a24…f997f`; user_prompt_submit `bec2484f…1b74`                                                 | 0 → 0                       | completed, no `hook/*` notifications |
| 1b. same process after grant + reload | `trusted` ×2              | unchanged hashes (identities asserted equal)                                                                       | n/a (no turn run)           | not run                              |
| 2. `trusted-restarted` (new process)  | `trusted` ×2              | unchanged hashes                                                                                                   | 0 → 2                       | completed; 4 `hook/*` notifications  |
| 3. `modified-restarted` (new process) | `modified` ×2             | session_start `661c3181…9892`; user_prompt_submit `7146b640…37a1` (both differ from the originals; keys unchanged) | 2 → 2                       | completed, no `hook/*` notifications |

Full hashes: original `sha256:0e458a24f9f74a246f42206b68ccbc8247d6eafca62fc2c052ce3270642f997f` (session_start), `sha256:bec2484ffd2868467af2b2bd15f7df43ddd2618e961a5b527c3a11bd091f1b74` (user_prompt_submit); modified `sha256:661c31817ee5e1bf7bb85ad22bfb8996ebfca7f62d314bd90d4d9c1f137b9892`, `sha256:7146b64060e3ed81ebf25055d77317493a595837890d9ace954c54acdef037a1`. Hashes are computed by Codex and may depend on inputs beyond the hook text (see the historical note in `codex-marketplace.md`); compare the status transitions, not the literals.

### Trust grant

- Granted over JSON-RPC (`initialize` with `capabilities.experimentalApi: true`, then `initialized`) with one request:

  ```json
  {
    "method": "config/batchWrite",
    "params": {
      "reloadUserConfig": true,
      "edits": [
        {
          "keyPath": "hooks.state",
          "mergeStrategy": "upsert",
          "value": { "<hook key>": { "trusted_hash": "<currentHash>" } }
        }
      ]
    }
  }
  ```

  `value` held both hook keys, each mapped to its observed `currentHash`.

- Persistence: after the first app-server exited, the isolated `config.toml` parsed with `hooks.state.<key>.trusted_hash == currentHash` for both keys (`trustPersisted: true`).
- In-session reload: the immediate `hooks/list` in the same process reported `trusted` for both keys with identical hashes (`inSessionReloadTrusted: true`). This spike did **not** run a turn in that same process after the grant, so in-session dispatch after a grant is unobserved; execution was observed only after a restart.
- Modification: the harness rewrote only the installed cache `hooks/hooks.json` (revision argument `original` → `modified`) between phases 2 and 3. A trusted hook whose hash no longer matches reports `modified` and is not executed.

### Event order (phase 2, `trusted-restarted`)

Client requests: `initialize`, `initialized`, `hooks/list`, `thread/start` (`cwd`, `model: "mock-model"`, `modelProvider: "hook_stub"`, `approvalPolicy: "never"`, `sandbox: "read-only"`, `sessionStartSource: "startup"`), `turn/start` (text `"Record hook trust only. Do not call tools."`).

Server notifications after `turn/start`, in order:

```text
remoteControl/status/changed, thread/started, warning (mock-model metadata fallback), thread/status/changed,
turn/started,
hook/started   session-start:0:<…>/hooks.json      eventName=sessionStart      executionMode=sync scope=thread
hook/completed session-start:0:…                   status=completed durationMs=46
hook/started   user-prompt-submit:1:<…>/hooks.json eventName=userPromptSubmit  executionMode=sync scope=turn
hook/completed user-prompt-submit:1:…              status=completed durationMs=57
item/started userMessage, item/completed userMessage,
item/started agentMessage, item/completed agentMessage ("YAN-1149 deterministic loopback response; no inference."),
thread/tokenUsage/updated, account/rateLimits/updated, thread/status/changed, turn/completed
```

Both `hook/*` pairs occur after `turn/started` and before the user message item; the `sessionStart` hook ran at the first turn (not at `thread/start`) and before the `userPromptSubmit` hook. Phases 1 and 3 show the same sequence minus the four `hook/*` notifications. The `warning` appears in every phase and concerns missing model metadata for the stub's `mock-model` only.

### Recorded hook payloads (phase 2)

| Order | `event`            | `revision` | `plugin_root` (`PLUGIN_ROOT` env in hook process)                            | stdin JSON keys                                                                                            |
| ----- | ------------------ | ---------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| 1     | `SessionStart`     | `original` | `<SANDBOX>/codex/plugins/cache/hook-trust-spike/recording/0.0.1` (non-empty) | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `source`, `transcript_path`            |
| 2     | `UserPromptSubmit` | `original` | same                                                                         | `cwd`, `hook_event_name`, `model`, `permission_mode`, `prompt`, `session_id`, `transcript_path`, `turn_id` |

Exactly 2 records after the whole run; none in phases 1 and 3. Only payload key names were recorded, not values.

### Schema contract checked

`codex app-server generate-json-schema --experimental` output was inspected before use; the harness fails if the fields it uses disappear: `v1/InitializeParams` (`capabilities`, `clientInfo`), `v2/HooksListParams` (`cwds`), `v2/ConfigBatchWriteParams` (`edits`, `reloadUserConfig`; `ConfigEdit` has `keyPath`/`mergeStrategy`/`value`; `upsert` exists), `v2/ThreadStartParams`, `v2/TurnStartParams`, plus trust statuses `untrusted`/`trusted`/`modified`. `HookEventName` was exactly: `preToolUse`, `permissionRequest`, `postToolUse`, `preCompact`, `postCompact`, `sessionStart`, `sessionEnd`, `userPromptSubmit`, `subagentStart`, `subagentStop`, `stop`, `interrupt` — no `worktreeCreate`. Schema SHA-256s are in `evidence.json` and are per-binary, not stable identifiers.

## No-Inference Proof

Turns ran against a loopback Python stub, not a model service. The isolated `config.toml` defines provider `hook_stub` (`base_url = http://127.0.0.1:<ephemeral port>/v1`, `wire_api = "responses"`, `requires_openai_auth = false`, websockets off, zero request/stream retries) with analytics disabled.

- The stub answers only `POST /v1/responses`, with one fixed SSE sequence (`response.created`, one assistant message item, `response.completed` with zero token usage). Any other method/path, any `Authorization` header, or a fourth request is recorded as a failure and answered 400.
- Observed: exactly 3 requests (one per turn), all `POST /v1/responses`, `authorizationPresent: false`, body 39 259 bytes each with distinct SHA-256s (`2f70d615…`, `5689cbdb…`, `7ac29e22…`), `failures: []`. Each phase asserted the cumulative request count (1, 2, 3).
- Every turn's `agentMessage` equalled the fixed stub text; every `turn/completed` had status `completed` with no error; `thread/start` resolved `modelProvider == "hook_stub"`. No server-initiated request (tool call or approval) was received (the harness fails on one), and `<CODEX_HOME>/auth.json` did not exist at the end.

This shows no real inference and no credentials were used. It does not show the absence of any other outbound traffic (see below).

## Isolation and Limits

Recorded in `evidence.json` `isolation`: fresh `HOME` and `CODEX_HOME`, no inherited environment, no copied credentials or hooks, loopback provider, production scripts and sockets not configured or referenced, generated fixture.

- The child environment is built from scratch (not inherited): fixed `PATH=/usr/local/bin:/usr/bin:/bin`, `HOME`, `CODEX_HOME`, `XDG_*`, `TMPDIR` under the sandbox, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `GIT_ALLOW_PROTOCOL=file`, and empty `credential.helper`. The harness fails closed before invoking Codex if `/etc/codex` exists (including a symlink): official release builds still load host system/managed configuration, and debug override environment variables do not disable it.
- **Not an OS network sandbox** (`osNetworkIsolation: false`): only the model provider URL is constrained to loopback by configuration. The harness cannot block an unexpected outbound connection by the Codex binary itself.
- The hook command is `/usr/bin/python3` from the host and runs unconfined as the invoking user; it writes only to a path in the sandbox by construction of the generated script.
- The marketplace fixture is a **local path** marketplace, so this run says nothing about transport; transport is covered separately below.
- Scope is one platform and one binary: Linux x86_64, `codex-cli 0.160.0`. Not exercised: other versions (including the `0.161.0` used by YAN-1123), other OSes, `PreToolUse`/`Stop` or any other event, hooks that return output or block, async hooks, multiple plugins, project-scope hooks, and managed (`isManaged`) hooks.
- The `plugin_hooks` feature flag (`removed` on 0.161.0 per `codex-marketplace.md`) was not re-queried in this run; the config enabled `plugins` and `hooks` and hooks were discovered and ran, regardless of that flag's reported state.
- Sandbox and `evidence.json` live under `/tmp/opencode` and are ephemeral; evidence has `<SANDBOX>`/`<CODEX_BIN>` substituted for paths.

## Public Transport (shorthand `owner/repo`)

Separately from the hook probe, `codex plugin marketplace add yandy-r/codex-plugin-spike --ref a0df68c5862180947bd4fb207861f1a87d718a24 --json` (shorthand `owner/repo`, no full URL) succeeded on `codex-cli 0.160.0` (exit 0, anonymous HTTPS, 2026-10-16):

- **Fixture immutable ref:** `yandy-r/codex-plugin-spike` at commit `a0df68c5862180947bd4fb207861f1a87d718a24` (remote ref `refs/heads/test/yan-1163-native-fixture`; the fixture repo's `main` / `HEAD` at observation time, `d2e2e5c448ac97c14224ac5b15c18eb8b2c96ec4`, is unrelated, so always pass the SHA via `--ref`). Same fixture as [`codex-public-fork-install.md`](codex-public-fork-install.md).
- Codex resolved the shorthand to `https://github.com/yandy-r/codex-plugin-spike.git` (staged `.git/config` and `config.toml`); the staged checkout `HEAD` equalled the SHA. Marketplace `ycc`; `ycc@ycc` and `ycc-mcp@ycc` both installed (version `5.3.0`) and listed enabled.
- Two runs, identical `mcp list --json` bytes (SHA-256 `0ee4e41b9aff97080d570fda0918b05c619656425d832b0ad81e3338e6229c26`) and identical installed tree digests: official binary with a full checkout, and the equivalent installed native binary (same bytes, same SHA-256 as above) with `--sparse .agents/plugins --sparse .codex-plugin/ycc --sparse .codex-plugin/ycc-mcp` (HEAD = SHA, sparse cone mode, partial clone). `ycc` 357 files `a24176ff…2c27`; `ycc-mcp` 2 files `1b135525…0403`.
- No URL rewrites and no inherited Git config (`git config --get-regexp '^url\..*\.insteadof$'` exit 1; only `credential.helper=` on the command line). Same isolation caveat: environment isolation, not an OS network sandbox; no login, model, hook, or MCP server execution (`mcp list` is metadata only).
- Neither installed manifest declares `hooks`, and the installed fixture contains no Codex hook declaration. The fixture is the pre-fix `5.3.0` payload and differs from the current native export (nine `ycc` files and the `ycc-mcp` `.mcp.json`; catalog bytes equal), so it proves transport and install mechanics, not current payload bytes.
- The replay script for this run (`/tmp/yan1149-public.sh`) was an ephemeral non-repository file and is not part of this change; the command above is the reproducible core. This closes the "public GitHub transport was not tested" boundary in `codex-marketplace.md` §3 for the shorthand source on this fixture only; private/authenticated transport and the SSH form remain untested.

## Decision Record

| Item                                                           | Decision                                                                                              |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Plugin hook trust model (`untrusted` → `trusted` → `modified`) | Verified on `0.160.0` as above.                                                                       |
| Adapted reporter using `SessionStart` / `UserPromptSubmit`     | **GO** for a recording-only probe.                                                                    |
| Shipping `ycc` / `herdr` hooks in the Codex plugin bundle      | **No-Go** until the adapted reporter is implemented and verified; this spike changes no shipped file. |
| `WorktreeCreate`                                               | **No-Go**: absent from `HookEventName`; `SessionStart` does not substitute for it.                    |
| Real `herdr` integration                                       | **Not tested**: no `herdr` script, socket, or payload consumer was involved.                          |
