# Codex Native Packages — External Research

## Executive Summary

- Codex CLI **0.161.0 is installed**. Read-only CLI help probes used temporary `CODEX_HOME`; subsequent marketplace/RPC probes also used temporary `HOME` and ran outside the repository. No credentials, login, user config, or inference were used. Marketplace add/install probes wrote only temporary fixtures/config/cache, not the checkout.
- Keep the requested `.codex-plugin/plugin.json` compatibility format for this change. Current official documentation now recommends portable root `plugin.json`, but explicitly supports the compatibility format; changing formats is unnecessary scope.
- `.agents/plugins/marketplace.json` **already exists and is tracked**. It names `local-ycc-plugins`, with `ycc` sourced from `./plugins/ycc`. That directory is absent. A fresh isolated local registration selects this catalog and lists `ycc@local-ycc-plugins`; install fails with `plugin source path is not a directory`. This is the current repository behavior, distinct from the working installer-managed personal catalog.
- Renaming this discovered catalog to `ycc`, including replacing its entries with an empty list, changes externally observable behavior **before** the v6.0.0 flip. `listed: false` is not a Codex runtime field or hiding mechanism. Preserve the existing discovered catalog and legacy bundle while unlisted. Generate a complete future repo-shaped tree only through an explicit opt-in output directory outside the repository; test that tree as a Git fixture. At the release flip, activate native generation based on model listing state.
- Native skills must not depend on the installer's `~/.codex/plugins/ycc` symlink. Codex exposes the installed cache `SKILL.md` path and documents resource paths relative to that file. Generate relocatable references and an explicit instruction to resolve them from the skill/document directory, not the shell working directory.
- Plugin MCP JSON accepts the Claude-compatible `mcpServers` wrapper, but **does not expand arbitrary `${ENV_VAR}` values**. Reuse the existing Codex translation (`env_vars`, `bearer_token_env_var`, etc.) rather than copying the Claude MCP file unchanged. The `ycc` skills-only package must have neither an MCP declaration nor a default `.mcp.json` file.

## Primary APIs

### Versioned source and official documentation

Primary documentation: [Package your plugin](https://developers.openai.com/plugins/build/plugins), including [marketplace metadata](https://developers.openai.com/plugins/build/plugins#marketplace-metadata), [CLI registration](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli), [path rules](https://developers.openai.com/plugins/build/plugins#path-rules), and [bundled MCP](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks). The document was retrieved through OpenAI's developer-docs search/fetch tools. It is moving documentation; use tagged source for this version requirement. For example, its general cache description says local versions use `local`, whereas the observed 0.161.0 CLI installed the manifest version `5.3.0`.

Fetched and byte-compared these files from `rust-v0.160.0` and `rust-v0.161.0`: `core-plugins/src/manifest.rs`, `core-plugins/src/marketplace.rs`, `codex-mcp/src/plugin_config.rs`, `ext/skills/src/catalog_prompt.rs`, `ext/skills/src/fragments.rs`, and `rmcp-client/src/utils.rs`. **All six files were identical across those tags.** This supports the format conclusions for both releases; only 0.161.0 was executed.

### Plugin manifest

Source: [`RawPluginManifest`, `resolve_raw_plugin_manifest`, and path resolvers](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/manifest.rs#L46-L153), [resolution](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/manifest.rs#L279-L476), [path validation](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/manifest.rs#L582-L671).

| Field                     | Accepted shape / behavior                                                                                                                                                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`                    | String; omitted/blank legacy name falls back to plugin root basename. Supply explicitly.                                                                                                                                                                                                        |
| `version`                 | Optional string, trimmed; supply lockstep package version.                                                                                                                                                                                                                                      |
| `description`, `keywords` | Optional string and string array.                                                                                                                                                                                                                                                               |
| `skills`                  | String or string array of plugin-root-relative paths, e.g. `"./skills/"`.                                                                                                                                                                                                                       |
| `mcpServers`              | String path (`"./.mcp.json"`) or inline server map.                                                                                                                                                                                                                                             |
| `apps`                    | Optional `./` path; unrelated to ordinary bundled MCP declarations.                                                                                                                                                                                                                             |
| `hooks`                   | Path, paths, inline hooks object, or array; keep absent and omit hook files for this issue.                                                                                                                                                                                                     |
| `interface`               | `displayName`, `shortDescription`, `longDescription`, `developerName`, `category`, `capabilities`, `websiteUrl`/`websiteURL`, `privacyPolicyUrl`/`privacyPolicyURL`, `termsOfServiceUrl`/`termsOfServiceURL`, `defaultPrompt`, `brandColor`, `composerIcon`, `logo`, `logoDark`, `screenshots`. |
| `extensions`              | Parsed JSON; includes optional `com.openai.onboardingSkill`. Not needed here.                                                                                                                                                                                                                   |

Paths start with `./`, resolve against the **plugin root**, and cannot traverse `..` or escape that root. Invalid declarations can be warned about and ignored rather than aborting parse. `defaultPrompt` permits a string or list; at most three valid prompts, each at most 128 characters after whitespace normalization. Author/repository/homepage/license are conventional distributable metadata but not fields consumed by this legacy raw manifest parser; its unknown-field behavior does not reject them.

Crucially, omission of `skills` or `mcpServers` is not a deny rule. [`loader.rs`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/loader.rs) discovers defaults (`skills/`, `.mcp.json`) when no override is present. MCP-only must have no `skills/`; skills-only must have no `.mcp.json` or hooks payload.

### Marketplace schema

Source: [`RawMarketplaceManifest` and tagged sources](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L1019-L1110), [policies](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L155-L199), [source resolution](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L612-L760).

Top-level required fields: `name: string`, `plugins: array`. Optional `interface.displayName`. Each entry requires `name` and `source`; optional `policy`, `category`, and flattened plugin metadata for listing/fallback.

| Source           | JSON shape                                                                                                                                                            |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Local            | `{"source":"local","path":"./.codex-plugin/ycc"}`; string shorthand `"./.codex-plugin/ycc"` also accepted.                                                            |
| Git root         | `{"source":"url","url":"https://github.com/owner/repo.git","ref":"main"}`; optional `path`, `ref`, `sha`. `url` here means a Git source, **not an archive download**. |
| Git subdirectory | `{"source":"git-subdir","url":"https://github.com/owner/repo.git","path":"./.codex-plugin/ycc","ref":"main"}`; required `path`, optional `ref`/`sha`.                 |
| NPM              | `{"source":"npm","package":"@owner/plugin","version":"^1.0.0","registry":"https://registry.npmjs.org"}`; not required by YAN-1131.                                    |

`policy.installation` is `AVAILABLE` (default), `INSTALLED_BY_DEFAULT`, or `NOT_AVAILABLE`. `policy.authentication` is `ON_INSTALL` (default) or `ON_USE`. Optional `policy.products` exists but source explicitly notes consumer enforcement remains incomplete; do not use it as a release visibility gate. Marketplace `category` overrides manifest `interface.category`. Unsupported or invalid entry sources may be skipped, so valid catalog JSON alone does not prove both packages are available/installable. There is no `listed` visibility field consumed by this schema.

### Discovery, registration, and sparse checkout

[`marketplace.rs:20-25`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L20-L25) defines this exact first-existing-file order:

1. `.agents/plugins/marketplace.json`
2. `.agents/plugins/api_marketplace.json`
3. `.claude-plugin/marketplace.json`
4. `.cursor-plugin/marketplace.json`

[`find_marketplace_manifest_path`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs#L339-L349) selects the first existing file, not the first catalog with installable entries. `plugins: []` at the preferred path suppresses fallback and still changes marketplace identity/discovery.

[`parse_marketplace_source`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace_add/source.rs#L18-L65) maps `owner/repo[@ref]` to `https://github.com/owner/repo.git`. `--ref` overrides an embedded ref; HTTPS/HTTP and SSH Git URLs or local directories are supported. Marketplace registration requires a directory, not a catalog file. Direct `file://` marketplace URLs are rejected by this CLI parser, though Git plugin entry URL normalization supports file URLs.

Registration stages Git sources, discovers/validates the catalog name, and persists `[marketplaces.<name>]` configuration. Local roots are referenced directly, not copied. Git snapshots live under `$CODEX_HOME/.tmp/marketplaces/<name>` (also confirmed by the existing spike). A conflicting source under the same marketplace name must first be removed.

[`clone_git_source`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace_add/install.rs#L6-L41) uses full `git clone` without sparse flags; with sparse paths it runs `clone --filter=blob:none --no-checkout`, `sparse-checkout set <paths...>`, then `checkout <ref-or-HEAD>`. Include **catalog and both local payload roots** in sparse paths. Local sources resolve against marketplace root, not `.agents/plugins/`. A catalog-only checkout can list entries successfully while install later fails. Existing repo spike evidence: `docs/internal/spikes/codex-marketplace.md:48-55`; that harness exercised full, catalog-only sparse negative control, complete sparse, Claude fallback, and git-subdir installs on 0.161.0.

### Observed CLI contract

`codex --version` returned `codex-cli 0.161.0`. Help commands exited successfully, with a nonfatal warning that Codex refused to create PATH helper aliases under `/tmp`.

```text
codex plugin --help
  add | list | marketplace | remove
codex plugin marketplace --help
  add | list | upgrade | remove
codex plugin marketplace add [OPTIONS] <SOURCE>
  SOURCE: local path, owner/repo[@ref], HTTPS Git URL, or SSH Git URL
  --ref <REF>  --sparse <PATH> (repeatable)  --json
codex plugin add [OPTIONS] <PLUGIN[@MARKETPLACE]>
  --marketplace <MARKETPLACE>  --json
codex plugin list
  --marketplace <MARKETPLACE>  --json  --available
codex plugin marketplace upgrade [MARKETPLACE_NAME]
  --json
```

`codex features list` showed `plugins stable true`, `remote_plugin stable true`, `hooks stable true`, and `plugin_hooks removed false`. Do not infer runtime hook parity from that flags output; YAN-1123 remains no-go.

## Libraries and SDKs

No new SDK/library is necessary. Generation remains Python stdlib; native install/discovery is performed by Codex CLI plus Git. The authoritative Rust integration boundary is `codex-core-plugins`, with `codex-mcp::parse_plugin_mcp_config`, `codex-config::McpServerConfig`, and `codex-rmcp-client` for process environment setup. The public Agent Plugins format is a different supported branch, not a reason to add another manifest dialect for this issue.

Useful internal APIs to reuse: `generate_codex_plugin.write_all`, `generate_codex_skills.write_tree`/`write_all`, and `generate_codex_mcp.build_codex_mcp_servers`/`translate_env`. Keep installer personal-catalog merge/remove in `scripts/codex_marketplace.py`; do not rename that marketplace or conflate it with repository catalog identity.

## Integration Patterns

### Off-by-default generation and release gate

Recommended interface: `--native-output <DEST>`, explicitly documenting that DEST is a separate staging root, not the current repository. This is clearer than generic `--output-dir`, which suggests ordinary default output relocation and can obscure the behavioral mode change. `--preview-native` alone does not communicate where a complete tree is emitted.

Before listing: default metadata, legacy payload, installer, and discovered catalog remain unchanged. Opt-in native output regenerates from `ycc/` source into `.codex-plugin/ycc` and `.codex-plugin/ycc-mcp` plus `.agents/plugins/marketplace.json`, rather than copying checked-in generated skills (which contain legacy absolute paths). This tree can be committed into a temporary Git fixture for fork-install proof. A separate default-generated unlisted `ycc-mcp` payload is not necessary for discovery and should only be added if required by the internal spec; it must not be catalog-wired.

At listing: model `listed` state selects the native route. Do not require a second hard-coded release switch. Reject incoherent states that would remove legacy bundled MCP without making the native MCP package available. Lifecycle/check tests should cover legacy byte-stability, native deterministic output, orphan removal only within owned paths, forbidden in-repo output roots, absent hook package, and stale MCP/skills defaults during cutover. These are implementation recommendations, not checks executed here.

### Installed skill resources and relocation

Primary evidence:

- [`catalog_prompt.rs`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/ext/skills/src/catalog_prompt.rs#L1-L48) instructs the model to open listed/expanded host `SKILL.md` paths and explicitly resolve relative resources against the directory containing that expanded `SKILL.md` first.
- [`fragments.rs`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/ext/skills/src/fragments.rs#L56-L112) emits `<name>`, `<path>`, resource metadata, and unmodified skill contents; it does not replace a `CODEX_PLUGIN_ROOT` variable.
- [`tools/read.rs`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/ext/skills/src/tools/read.rs#L44-L69) describes `skill_root` for executor skills; implementation derives it from `SKILL.md.parent()`.
- Live isolated install of a temporary local catalog `ycc` pointing at a copied current plugin succeeded. `skills/list` returned **54 skills**, including `ycc:backport` at `$CODEX_HOME/plugins/cache/ycc/ycc/5.3.0/skills/backport/SKILL.md`, enabled with `pluginId: "ycc@ycc"`. This proves the runtime exposes the cache path; it does not prove every current skill helper invocation works.

Native generation should calculate relative references using the generated document's location: e.g. from `skills/backport/SKILL.md`, `_shared/scripts/release-state.sh` relocated to `shared/` becomes `../../shared/scripts/release-state.sh`; from `shared/references/ci-monitoring.md` it becomes `../scripts/...`. Add an explicit instruction to resolve bundled resources against the containing installed document path and use the resolved absolute helper path while retaining the user's repository cwd. This matters because helpers operate on the user's repo. Merely running `../../shared/scripts/...` from the repo cwd is wrong. Apply path transformation to reference documents too, not only SKILL.md.

Do not emit `${CODEX_PLUGIN_ROOT}` or assume `${PLUGIN_ROOT}` exists in ordinary skill shell commands: no such substitution was found in the examined skill rendering/resource paths. `${PLUGIN_ROOT}` support in portable MCP and hooks is a separate subsystem and not evidence for skills.

### Installed MCP loading

[`loader.rs:900-946`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/loader.rs#L900-L946) resolves configured enabled plugins to installed roots, then reads MCP declarations from the manifest/default file. [`load_plugin_mcp_servers_from_manifest_with_format`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/loader.rs#L1534-L1589) handles inline maps or file paths and applies per-plugin policy. The default `.mcp.json` is read even if the manifest omits `mcpServers`.

[`plugin_config.rs:44-72`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/codex-mcp/src/plugin_config.rs#L44-L72) accepts `{"mcpServers": {...}}` **or a bare server map**. It does **not** recognize the top-level `{"mcp_servers": {...}}` shape emitted for config merging by `generate_codex_mcp.build_codex_mcp_config`; wrap that function's inner server map under `mcpServers` for plugin payloads.

[`normalize_plugin_mcp_server_value`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/codex-mcp/src/plugin_config.rs#L243-L305) removes compatible transport `type` values (`http`, `streamable_http`, `streamable-http`, `stdio`), normalizes OAuth camelCase aliases, roots explicit relative `cwd` under the plugin, and deserializes Codex server fields. Invalid individual servers are skipped without discarding siblings. It does not translate Claude `env` interpolation or arbitrary header fields.

[`create_env_for_mcp_server`](https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/rmcp-client/src/utils.rs#L16-L58) collects allowed/pass-through names from host environment and overlays explicit env strings unchanged. Thus `"env":{"XERO_CLIENT_ID":"${XERO_CLIENT_ID}"}` passes that literal string; instead generate `"env_vars":["XERO_CLIENT_ID"]`. Use existing server overrides and translation so HTTP auth policy (`bearer_token_env_var`, `env_http_headers`, tool approvals) remains intact.

Live app-server metadata after the isolated current-plugin install: `plugin/list` reported `ycc@ycc` installed/enabled, localVersion `5.3.0`; `mcpServerStatus/list` returned a `context7` entry with `pluginId: "ycc@ycc"` and HTTP origin `https://mcp.context7.com`. This confirms current wrapper parsing and plugin MCP association, **not successful authentication/execution of all servers or placeholder expansion**. The metadata response included cached server information; no live MCP tool invocation or inference was performed. This probe was not OS-egress-sandboxed and should not be represented as a hermetic network test.

## Constraints and Gotchas

1. `listed` belongs only to this repository's package model; Codex neither filters nor hides packages based on it.
2. Preferred catalog presence/name is visible independently of plugin listing. Empty entries and `NOT_AVAILABLE` are not equivalent to preserving the existing catalog surface.
3. Preserve `local-ycc-plugins` personal marketplace and its cache identity. Existing installer local mode uses `./.agents/plugins/ycc` relative to HOME; repo mode uses git-subdir `./.codex-plugin/ycc`. Neither should silently switch to the future repo identity.
4. Avoid stale default `.mcp.json`, `skills/`, or `hooks/hooks.json` when pruning native outputs. Omitting manifest fields alone does not exclude capability discovery.
5. Cache paths must not be hard-coded: marketplace/name/version are variable, and skill listing exposes the installed path.
6. Relative manifest paths cannot traverse parents; relative **skill document resource references** are different and may intentionally reach plugin `shared/`.
7. CLI help with only `CODEX_HOME` isolation is insufficient to isolate marketplace discovery: HOME's `.agents/plugins/marketplace.json` remains discoverable. Confirmed initial probe saw `/home/yandy` personal marketplace; a fresh HOME removed it. Hermetic tests must isolate both and run outside any source repo.
8. Public docs have moved toward portable Agent Plugins; do not silently import `mcp.json` schema or `${PLUGIN_ROOT}` expansion semantics into legacy `.mcp.json` behavior.
9. 0.160 source parity is established for six key files; execution on an actual 0.160 binary and public GitHub transport remain unverified.

## Code Examples

### Native staging tree (not default pre-flip output)

```text
<DEST>/
  .agents/plugins/marketplace.json
  .codex-plugin/ycc/.codex-plugin/plugin.json
  .codex-plugin/ycc/skills/<name>/SKILL.md
  .codex-plugin/ycc/shared/{scripts,references}/...
  .codex-plugin/ycc-mcp/.codex-plugin/plugin.json
  .codex-plugin/ycc-mcp/.mcp.json
```

`ycc` manifest (illustrative v6 target; actual generated version comes from source):

```json
{ "name": "ycc", "version": "6.0.0", "skills": "./skills/", "description": "YCC workflow skills" }
```

`ycc-mcp` manifest:

```json
{ "name": "ycc-mcp", "version": "6.0.0", "mcpServers": "./.mcp.json", "description": "YCC MCP connections" }
```

Native catalog:

```json
{
  "name": "ycc",
  "interface": { "displayName": "YCC" },
  "plugins": [
    {
      "name": "ycc",
      "source": { "source": "local", "path": "./.codex-plugin/ycc" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    },
    {
      "name": "ycc-mcp",
      "source": { "source": "local", "path": "./.codex-plugin/ycc-mcp" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Productivity"
    }
  ]
}
```

Plugin MCP wrapper around translated Codex server map:

```json
{
  "mcpServers": {
    "xero": {
      "command": "npx",
      "args": ["-y", "@xeroapi/xero-mcp-server@latest"],
      "env_vars": ["XERO_CLIENT_ID", "XERO_CLIENT_SECRET"]
    },
    "context7": { "url": "https://mcp.context7.com/mcp" }
  }
}
```

Post-flip/fork fixture install command shape:

```bash
codex plugin marketplace add owner/fork --ref fixture-sha \
  --sparse .agents/plugins \
  --sparse .codex-plugin/ycc \
  --sparse .codex-plugin/ycc-mcp
codex plugin add ycc@ycc --json
codex plugin add ycc-mcp@ycc --json
codex plugin list --available --json
```

For a network-free Git fixture, follow `scripts/test-codex-marketplace-spike.sh`: HTTPS-shaped `.invalid` URL rewritten to a local bare Git fixture via isolated `GIT_CONFIG_*`, `GIT_ALLOW_PROTOCOL=file`, `GIT_CONFIG_NOSYSTEM=1`, no global config/credential helper. Do not pass a direct `file://` marketplace URL. These example future-native fork installs were **not executed in this research**; the implementation acceptance harness must exercise both generated packages, sparse paths, cache contents, capability boundaries, and resource relocation.

## Open Questions

- Adopt the proposed opt-in native staging interface in the implementation spec, explicitly distinguishing pre-flip staging from discovered repository output. Leaving the original requirement as “hidden catalog at discovered path” is internally contradictory when any catalog identity or entry changes.
- Final native shared-directory spelling: current generator maps `_shared` to `shared`; acceptance says “skills + _shared”. Determine whether that means logical component ownership or exact directory spelling. Whichever is chosen, native resource links and lifecycle tests must match it consistently; this is not a Codex format restriction.
- Native helper correctness needs a cache-based smoke assertion under a clean HOME with no installer symlink, preserving repository cwd. Source-backed relative resource semantics and `skills/list` cache path evidence are established; no model-driven helper execution was attempted.
- Actual `rust-v0.160.0` CLI execution and public GitHub authentication/transport were not tested. The existing hermetic Git rewrite can prove parsing, discovery, sparse checkout, package installation and cache shape without claiming remote transport proof.
- Hook trust/runtime parity remains YAN-1149, not YAN-1131. Do not emit or install `ycc-hooks` based on newly expanded general docs.
