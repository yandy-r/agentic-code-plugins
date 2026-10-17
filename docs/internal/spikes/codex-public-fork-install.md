# Codex Public Fork Install Spike (YAN-1163)

- **Date:** 2026-10-16
- **Issue:** `YAN-1163` / GitHub #316 (target `v6.0.0`)
- **Target CLI:** `codex-cli 0.160.0` (exact, public profile)
- **Harness:** [`scripts/test-codex-native-packages.sh`](../../../scripts/test-codex-native-packages.sh) `--public` profile with [`scripts/codex_native_smoke.py`](../../../scripts/codex_native_smoke.py)

## Results

1. Anonymous public GitHub HTTPS registration and installation of both independent native packages (`ycc@ycc`, `ycc-mcp@ycc`) succeed on the exact baseline `codex-cli 0.160.0`, from a full checkout and from a sparse checkout, in opposite install orders. This proves public transport for this public fixture only; it does not test authenticated or private transport.
2. Installed payload version is `5.3.0` (the canonical `ycc/.claude-plugin/plugin.json` version at generation time), despite the `v6.0.0` release target. This evidence proves the install mechanics with `5.3.0` payload bytes; it is not evidence about final `v6.0.0`-tagged payload bytes.
3. Production catalogs stay hidden: no checked-in catalog was renamed or listed, and no installer routing changed. Production listing (YAN-1140) and existing-user migration/dedupe (YAN-1139) remain closed gates.

## Fixture and Binary Provenance

- **Public fixture:** `https://github.com/yandy-r/codex-plugin-spike.git` at pinned commit `a0df68c5862180947bd4fb207861f1a87d718a24`, generated from production commit `0dbb571b` (native export). Published only on the topic branch; no trunk push. The fixture is retained for replay until a cleanup decision is made; no deletion is promised.
- **Fixture integrity:** before any Codex install, the harness fetches the pinned SHA, checks out `FETCH_HEAD` detached, asserts `rev-parse HEAD` equals the pinned SHA, and asserts the fixture catalog/payload bytes and executable bits match a fresh native export (`generate_codex_plugin.py --native-output`). After each Codex registration, it also asserts Codex's staged checkout HEAD equals the pinned SHA and checks its Git sparse state: no selection for full, and all three package/catalog selections for sparse.
- **Official binary:** `codex-x86_64-unknown-linux-musl` from the official `0.160.0` release asset, retained at `/tmp/codex-0.160.0-official.tY2gsM/` (ephemeral path). Asset `codex-x86_64-unknown-linux-musl.tar.gz` SHA-256 `306865417d4ee7a927785852910a527f41e1e159add390ac5ae3accb67d44a13` matches the GitHub release metadata; extracted binary SHA-256 `12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad`. `--version` reports `codex-cli 0.160.0`; the public profile enforces this exact version.

## Auth and Isolation Contract

Every harness command runs under `env -i` with fresh `HOME`, `CODEX_HOME`, `XDG_*`, and `TMPDIR` inside the sandbox, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, empty `credential.helper`, `GIT_TERMINAL_PROMPT=0`, and `GIT_ASKPASS`/`SSH_ASKPASS=/bin/false`. The public profile permits only `GIT_ALLOW_PROTOCOL=https` with no URL rewrites and no inherited Git config, credentials, or proxy settings; the public fixture needs no authentication (anonymous HTTPS). No login, model session/inference, hook execution, or MCP server execution was requested: `mcp list` reads metadata only. This is environment/transport isolation, not an OS network sandbox.

## Replay

```bash
# Verify the official 0.160.0 asset and binary, then point CODEX_BIN at it:
sha256sum codex-x86_64-unknown-linux-musl.tar.gz   # 306865417d4ee7a927785852910a527f41e1e159add390ac5ae3accb67d44a13
tar -xzf codex-x86_64-unknown-linux-musl.tar.gz
sha256sum codex-x86_64-unknown-linux-musl          # 12eb3e81114588aca3b7998f4f19e8997b056aca08e57a7ca7c8a3ec8c652aad

CODEX_BIN=/path/to/codex-x86_64-unknown-linux-musl \
  ./scripts/test-codex-native-packages.sh --keep \
  --public https://github.com/yandy-r/codex-plugin-spike.git \
  --ref a0df68c5862180947bd4fb207861f1a87d718a24
```

Retained transcript from the final verified run: `/tmp/codex-native-packages.Wi8D8K/transcript.log` (exit 0, 1078 lines; ephemeral `/tmp` path, retained only because `--keep` was passed). Earlier pre-review runs are retained at `/tmp/codex-native-packages.yX4uwv/transcript.log` and `/tmp/codex-native-packages.W8DmYP/transcript.log`.

## Observed Behavior (sanitized excerpts)

These are selected transcript lines with only disposable path prefixes replaced by `<SANDBOX>` or `<CODEX_BIN>`. Omitted lines (full JSON listings, the repeated `plugin list` output, and the full `mcp list` JSON) are not reproduced. Every command shown exited 0.

Header and fixture proof:

```text
[version] cwd=<SANDBOX>/work argv: <CODEX_BIN> --version
exit=0
codex-cli 0.160.0
YAN-1163 | codex-cli 0.160.0 | public GitHub HTTPS (no URL rewrites)
Public fixture URL: https://github.com/yandy-r/codex-plugin-spike.git
Pinned fixture SHA: a0df68c5862180947bd4fb207861f1a87d718a24
PASS public fixture catalog/payload bytes and executable bits match fresh native export
```

Full profile (fresh `CODEX_HOME`; install order `ycc` then `ycc-mcp`):

```text
[full-register] cwd=<SANDBOX>/work argv: <CODEX_BIN> plugin marketplace add https://github.com/yandy-r/codex-plugin-spike.git --ref a0df68c5862180947bd4fb207861f1a87d718a24 --json
  "marketplaceName": "ycc",
  "alreadyAdded": false
PASS full checkout: HEAD=a0df68c5862180947bd4fb207861f1a87d718a24; sparse selection=none
PASS full staging: full/sparse selection and both payload roots checked
[full-first-install] cwd=<SANDBOX>/work argv: <CODEX_BIN> plugin add ycc@ycc --json
  "pluginId": "ycc@ycc",
  "version": "5.3.0",
  "installedPath": "<SANDBOX>/full/codex/plugins/cache/ycc/ycc/5.3.0",
[full-first-mcp] cwd=<SANDBOX>/work argv: <CODEX_BIN> mcp list --json
[]
[full-second-install] cwd=<SANDBOX>/work argv: <CODEX_BIN> plugin add ycc-mcp@ycc --json
  "pluginId": "ycc-mcp@ycc",
  "version": "5.3.0",
  "installedPath": "<SANDBOX>/full/codex/plugins/cache/ycc/ycc-mcp/5.3.0",
PASS full: independent installs, complete cache bytes/exec bits, enabled IDs, MCP metadata, cache-relative helper
```

Sparse profile (separate fresh `CODEX_HOME`; reversed order `ycc-mcp` then `ycc`, so each package is shown to install without its companion):

```text
[sparse-register] cwd=<SANDBOX>/work argv: <CODEX_BIN> plugin marketplace add https://github.com/yandy-r/codex-plugin-spike.git --ref a0df68c5862180947bd4fb207861f1a87d718a24 --sparse .agents/plugins --sparse .codex-plugin/ycc --sparse .codex-plugin/ycc-mcp --json
  "marketplaceName": "ycc",
  "alreadyAdded": false
PASS sparse checkout: HEAD=a0df68c5862180947bd4fb207861f1a87d718a24; sparse selection=['.agents/plugins', '.codex-plugin/ycc', '.codex-plugin/ycc-mcp']
PASS sparse staging: full/sparse selection and both payload roots checked
[sparse-first-install] cwd=<SANDBOX>/work argv: <CODEX_BIN> plugin add ycc-mcp@ycc --json
  "pluginId": "ycc-mcp@ycc",
  "version": "5.3.0",
  "installedPath": "<SANDBOX>/sparse/codex/plugins/cache/ycc/ycc-mcp/5.3.0",
[sparse-second-install] cwd=<SANDBOX>/work argv: <CODEX_BIN> plugin add ycc@ycc --json
  "pluginId": "ycc@ycc",
  "version": "5.3.0",
  "installedPath": "<SANDBOX>/sparse/codex/plugins/cache/ycc/ycc/5.3.0",
PASS sparse: independent installs, complete cache bytes/exec bits, enabled IDs, MCP metadata, cache-relative helper
PASS native packages: full + sparse catalog/both payloads; no inference, hooks, login, or MCP server execution requested
```

Helper and MCP assertions (both profiles, via `codex_native_smoke.py`):

- After `ycc` alone, `mcp list --json` is `[]`; after `ycc-mcp`, the enabled server set matches the canonical Codex MCP config exactly (`context7`, `github`, `linear`, `linear-personal`, `openaiDeveloperDocs`, `playwright`, `railway`, `stripe`, `vercel`, `xero`), transports (URL or stdio command/args) match, Xero carries `env_vars: ["XERO_CLIENT_ID", "XERO_CLIENT_SECRET"]` with `env: null`, and no `${...}` literal survives. Servers were never executed.
- Cache inventories match the fixture payload byte-for-byte including executable bits; the `ycc` cache is skills-only (no `mcpServers`, no `.mcp.json`), the `ycc-mcp` cache is MCP-only (`mcpServers: ./.mcp.json`, no `skills`/`shared`), and neither cache contains hook declarations or files.
- The bundled helper is resolved from the installed cache document's relative reference (`shared/scripts/release-state.sh` under `.../cache/ycc/ycc/5.3.0/`), is executable, and runs as `release-state.sh get` from a separate user-project cwd (full profile excerpt; the sparse profile output is identical in shape):

```text
helper exit=0 cwd_before=<SANDBOX>/full/user-project cwd_after=<SANDBOX>/full/user-project
helper stdout='present=0\n' stderr=''
PASS helper output present=0; user repository remains clean; no legacy symlink
```

## Limits and Still-Closed Gates

- Only exact `codex-cli 0.160.0` was executed in the public profile. No claim is made about any later/current runtime; the earlier `0.161.0` evidence (YAN-1131) used a local file-transport fixture only.
- Public anonymous HTTPS only: authenticated, private-repo, SSH, and `owner/repo` shorthand transports are untested.
- Metadata only for MCP: no server startup, tool call, login/auth flow, model session, or hook trust/dispatch was exercised; hooks remain excluded.
- Payload bytes are version `5.3.0`, not the final `v6.0.0` payload.
- Production listing/routing flip remains YAN-1140; existing `local-ycc-plugins` migration/dedupe remains YAN-1139. Both gates stay closed; catalogs stay hidden.
- The public fixture is retained for replay until a cleanup decision; sandbox and transcript paths under `/tmp` are ephemeral per-run values, not stable identifiers.

## 2026-10-17 Follow-up: Staged Checkout Proof (YAN-1200 / #337)

The results and sanitized public-install excerpts above remain historical evidence from **2026-10-16**, not a claim that the current public replay passes. The checkout checker now verifies Codex's staged checkout HEAD against the pinned fixture SHA and its exact sparse selection in both the default local-fixture and public profiles: full must have no sparse selection; sparse must select exactly `.agents/plugins`, `.codex-plugin/ycc`, and `.codex-plugin/ycc-mcp`.

- Default harness runs with `--keep` passed on `codex-cli 0.161.0` and official `codex-cli 0.160.0`, using pinned local fixture `dc4cc59449ff6bc77a0da6342009051b5217256d`. Retained transcripts are `/tmp/codex-native-packages.FJ51SQ/transcript.log` and `/tmp/codex-native-packages.xPZx4a/transcript.log`, respectively. Both record `PASS full checkout` with HEAD equal to the pin and `sparse selection=none`, and `PASS sparse checkout` with HEAD equal to the pin and `sparse selection=['.agents/plugins', '.codex-plugin/ycc', '.codex-plugin/ycc-mcp']`. Independent payload installs, cache bytes/executable bits, cache-relative helper, MCP metadata, and catalog-only rejection checks passed.
- A current public replay on official `0.160.0` successfully fetched the documented immutable `a0df68c5862180947bd4fb207861f1a87d718a24` SHA, then exited 1 at fixture proof: its payload bytes/executable bits no longer match the current native export, including changed MCP configuration. Transcript: `/tmp/codex-native-packages.GDfRzT/transcript.log`. It did not reach current public staged-checkout/install proof. This is a stale immutable-fixture limitation, not a successful current public replay or evidence of a transport failure.
- No fixture-proof bypass or refresh of the separate public fixture repository was made. No production catalogs or installer routing changed; the closed gates above remain closed. All retained `/tmp` paths are ephemeral.

Default local-fixture replay and checkout-checker unit tests (commands for replay; the evidence above is from the retained harness runs):

```bash
./scripts/test-codex-native-packages.sh --keep
python3 -m unittest discover -s scripts -p 'test_codex_native_smoke.py'
```
