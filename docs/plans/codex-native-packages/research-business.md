# Codex Native Packages — Business Research

## Executive Summary

YAN-1131 / GitHub #300 prepares the v6.0.0 Codex package split without activating it for current users. Generate two self-contained native packages from `ycc/settings/packages.json`: `ycc` (skills and shared helpers, no MCP) and `ycc-mcp` (MCP only). Prepare a future marketplace named `ycc` using repository-root-relative local sources. Do not generate Codex hooks or change current installer behavior.

The key release risk is that **the preferred marketplace path is already live**, not an unused hidden directory. `.agents/plugins/marketplace.json:1–20` currently names `local-ycc-plugins` and lists `ycc` at `./plugins/ycc`. The Codex spike documents that this path wins over the Claude catalog (`docs/internal/spikes/codex-marketplace.md:10–18`). Replacing it with a catalog named `ycc`, even with an empty `plugins` array, changes discovery today and removes the shipping entry. A dot-directory and `listed: false` do not themselves hide such a change.

Recommended business boundary: keep the shipping catalog and installer payload behavior unchanged before the flip; generate the future catalog and package split through an explicit maintainer-only staging/fixture path, then materialize `.agents/plugins/marketplace.json` in the authorized listing PR. This is a recommendation, not an implemented mechanism. If the issue requires overwriting the production catalog now, its scope conflicts with the release gates and needs resolution rather than a silent policy exception.

Sources: supplied Linear specification; ADR 0001 (`docs/internal/adr/0001-package-model-and-versioning.md:42–81,92–139`); `RELEASING.md:55–95`; package manifest (`ycc/settings/packages.json:1–42,65–98,117–156`). No implementation, CLI checks, or tests were run for this research.

## User Stories

| Actor                          | Story                                                                                                                                                                            | Acceptance                                                                                                                                                         |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Maintainer generating packages | As a maintainer, I generate Codex packages from the canonical package model so package identity, eligibility, content, and visibility do not drift across hand-maintained lists. | Included/native Codex entries produce the two specified artifacts; excluded hooks produce none; repeated generation is deterministic; check mode identifies drift. |
| Maintainer preparing v6        | As a maintainer, I exercise the future catalog on a generated-tree Git fixture before exposing it to users.                                                                      | The fixture installs both `ycc@ycc` and `ycc-mcp@ycc`; production discovery, installer registration, and public guides remain unchanged.                           |
| Future v6 skills user          | As a Codex user, I install `ycc@ycc` to get skills and their shared helpers without also enabling MCP servers.                                                                   | Installed skills and helper references resolve inside the package; no MCP declaration, agents, configuration, or hooks accompany it.                               |
| Future v6 MCP user             | As a Codex user, I install `ycc-mcp@ycc` to obtain MCP configuration independently of workflow skills.                                                                           | Package contains MCP configuration and necessary native metadata only; environment references remain symbolic and no build-machine credentials are captured.       |
| Current `install.sh` user      | As an existing user, I update or reinstall without being opted into the unfinished package model.                                                                                | Existing `local-ycc-plugins` registration, selected marketplace name preservation, existing installation modes, and scope-aware MCP behavior continue to work.     |
| Release owner                  | As the release owner, I activate the new catalog only when all required release evidence exists.                                                                                 | Rename precedes the listing flip; validators, lockstep preflight, migration/dedupe, and clean-machine fork installs pass for every newly listed package.           |

## Business Rules

1. **Generation is not publication.** `status: included` permits artifact preparation; `listed: false` forbids adding the new native package to a production catalog. `listed` is generator input and must not become a field emitted for Codex to interpret (`RELEASING.md:78–84`; ADR:134–139).
2. **No pre-flip reachability change.** Preserve the current shipping `ycc` catalog entry and marketplace identity throughout preparation. Changing a discovered catalog to an empty `ycc` marketplace is not equivalent to hiding new entries. New package-install guides stay unwired until the separate v6 docs flip.
3. **Native package boundaries are explicit.** Codex `ycc` has components `["skills", "shared"]`; `ycc-mcp` has `["mcp"]`; both have `requires: []`, `mechanism: "native"`, and target `v6.0.0`. They do not imply installation of one another (`packages.json:26–42,84–98`).
4. **Hooks are excluded, not merely unlisted.** Codex `ycc-hooks` has `status: "excluded"` and `listed: false`. No hooks artifact, manifest hook field, catalog listing, or bundled hook payload is permitted. Reconsideration requires YAN-1149 or superseding verified evidence; YAN-1131 cannot waive this (`packages.json:140–156`).
5. **Lockstep versioning.** Read the product version from `ycc/.claude-plugin/plugin.json`, as declared by `version_source`. Both package manifests and any versioned catalog metadata must agree. No new independent version, per-package tag, release-tag prerequisite, or timestamp-derived version (`packages.json:4,8,67`; ADR:109–123).
6. **Secrets remain references.** Copy/transform canonical MCP configuration without expanding `${ENV}` against the maintainer's environment. Native MCP configuration must preserve symbolic references; installer-specific `env_vars` translations remain separate. Do not copy auth state or user configuration into generated artifacts or fixtures.
7. **Future catalog contract.** Its identity is `ycc`; future entries use `{ "name": "ycc", "source": { "source": "local", "path": "./.codex-plugin/ycc" } }` and the analogous `ycc-mcp` path. Paths resolve from repository root, not the catalog's directory. Do not replace these with tag-pinned `git-subdir` sources.
8. **Installer marketplace is a separate concern.** `scripts/codex_marketplace.py` owns the user-level `local-ycc-plugins` registration and preserves an existing nonempty marketplace name. Do not repurpose its constant to rename user installations during generation (`codex_marketplace.py:21–24,55–91`).
9. **Other Codex surfaces remain installer-owned.** Agents (`*.toml`), `AGENTS.md`, and configuration do not become native package components (ADR:72–75). Existing installer compatibility handling is not removed as incidental cleanup.

## Workflows

### Maintainer preparation before the flip

1. Load and validate the existing immutable package model; select Codex entries by runtime, status, and native mechanism.
2. Generate the future skills/shared and MCP-only artifacts from canonical sources in an explicit preparation destination. Preserve the production artifact behavior consumed by `install.sh` until migration is authorized.
3. Build the future `ycc` catalog in that staging destination; normal production generation continues to preserve the current shipping catalog. Production listing filters apply `listed`; fixture-only activation must be explicit and must not edit the tracked manifest to make packages public.
4. Run the package validator and hermetic generated-tree fork-install evidence workflow during implementation verification. Check both installed package contents, not merely catalog availability.
5. Merge preparation without publishing the new entries, renaming marketplaces, or linking new user installation instructions.

### Hermetic future install proof

1. Construct a Git fixture from the generated future tree, including preferred `.agents/plugins/marketplace.json` and both payload directories.
2. Start with fresh `HOME`, `CODEX_HOME`, XDG paths, and isolated Git configuration; reuse the spike's HTTPS-shaped source rewritten to local Git transport rather than a direct `file://` marketplace argument.
3. Add the fixture marketplace and install `ycc@ycc` and `ycc-mcp@ycc` independently. Verify versions, skills/shared closure, MCP-only separation, symbolic secrets, and absence of hooks in installed cache content.
4. For sparse installation, include `.agents/plugins`, `.codex-plugin/ycc`, and `.codex-plugin/ycc-mcp`. Catalog-only sparse checkout is a documented negative case, not successful install proof.
5. Record the actual CLI version and evidence boundary. A local Git rewrite proves discovery and installation semantics, not public GitHub transport or authenticated server runtime operation.

### Authorized v6 activation

After repository rename and all release gates pass, the listing PR changes visibility, emits the prepared `ycc` marketplace at the production discovery path, and coordinates installer migration/dedupe. Public instructions are linked only in the docs flip. This ticket prepares that transition; it does not authorize it.

### Existing installation

Current installer continues using `.codex-plugin/ycc`, `scripts/codex_marketplace.py`, and its existing user-level marketplace registration. The `base`, standalone skills/agents, settings, rules, and MCP steps keep their current meanings. Generating staged native packages must not implicitly change what this workflow installs.

## Domain Model

| Entity                 | Relevant fields / relationship                                                                                                                                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Product version        | Canonical `version_source: "ycc/.claude-plugin/plugin.json"`; shared by workflow packages.                                                                                     |
| Package                | Key (`ycc`, `ycc-mcp`, `ycc-hooks`), description, `version_policy: "lockstep"`, runtime entries.                                                                               |
| Runtime package policy | `runtime`, `status`, `listed`, `mechanism`, `components`, `requires`, target release, gates/evidence; existing `RuntimePackage` dataclass in `scripts/package_model.py:23–36`. |
| Native artifact        | Package-specific manifest and component payload; generated eligibility is distinct from public catalog visibility.                                                             |
| Repository marketplace | Codex discovery document at `.agents/plugins/marketplace.json`; current identity `local-ycc-plugins`, future identity `ycc`.                                                   |
| Marketplace entry      | Native package name plus root-relative `local` source and supported Codex metadata; no runtime `listed` flag.                                                                  |
| User marketplace       | `$HOME/.agents/plugins/marketplace.json`, merged by installer independently of repository catalog generation.                                                                  |
| Release gate           | Policy evidence that authorizes listing; generated artifacts alone do not satisfy it.                                                                                          |
| Git fixture            | Disposable representation of the future generated tree, used to prove installability without activating public distribution.                                                   |

## Existing Codebase Integration

- `scripts/generate_codex_plugin.py:29–67` currently generates one `ycc` manifest with both `skills` and `mcpServers`; `write_all():103–125` copies canonical MCP into the shipping package. Simply removing those fields/files now changes the installer payload, even if new catalog entries remain unlisted. The preparation design must account for this second pre-flip compatibility boundary.
- `build_repo_marketplace():70–90` currently generates the exact shipping `local-ycc-plugins` catalog with `./plugins/ycc`. `.agents/plugins/marketplace.json:1–20` confirms this file already exists. Replacing it is an observable marketplace rename, not harmless new scaffolding.
- `scripts/generate_codex_common.py:20–30` centralizes current payload, catalog, and source paths; native package preparation should reuse the existing transformation helpers and source-of-truth conventions instead of introducing a second content pipeline.
- `scripts/generate_codex_mcp.py:1–18,80–98` translates canonical `mcp-configs/mcp.json` plus Codex overrides into installer-managed `mcp_servers`. This does not establish the native plugin MCP schema; preserve the installer output while testing native MCP packaging independently.
- `scripts/package_model.py:23–55` already models runtime policy and exposes `PackageModel.lookup(package, runtime)`; consume this existing model rather than parsing a competing policy format.
- `scripts/validate-codex-plugin.sh:7–29` currently checks generator drift and JSON for only the combined package/catalog and enforces local-files MCP exclusions. Extend coverage to the actual future artifacts while retaining applicable existing policy assertions.
- `scripts/lib/install/targets/codex.sh:47–58,130–153,170–187,193–223` owns CLI compatibility, selector construction, user catalog merging, and scoped installation. Its comments identify 0.160+ support, but version-specific future package acceptance still needs direct evidence.
- `scripts/test-codex-marketplace-spike.sh` is the existing fixture-harness precedent. Its documented evidence applies to synthetic marker plugins on 0.161.0, not yet the generated YCC split (`docs/internal/spikes/codex-marketplace.md:24–55,108–118`).

## Success Criteria

1. The implementation derives package generation and listing eligibility from `packages.json`; no handwritten policy list replaces the existing model.
2. Future generated `ycc` contains working skills and shared-helper closure without MCP; `ycc-mcp` contains MCP only. Codex hooks are absent everywhere in these outputs.
3. Future native manifests use distinct package names and the canonical lockstep version. `${ENV}` references survive generation without environment substitution.
4. The future `ycc` marketplace uses the specified root-relative local sources; unlisted packages do not appear in the production catalog before the flip.
5. Current repository catalog discovery and current installer behavior remain unchanged before v6 activation, including preservation of user-owned marketplace entries/names and installer-managed MCP behavior.
6. `scripts/validate-codex-plugin.sh` passes against its updated complete contract, including reproducibility checks for every generated artifact.
7. A hermetic Git fixture of the generated tree proves successful installation of both exact selectors on codex-cli >=0.160, with actual tested version recorded (locally supplied version: 0.161.0). Verify installed payloads, not only command exit or marketplace enumeration. Testing 0.161.0 alone is not proof of 0.160.0 compatibility.
8. The evidence explicitly distinguishes local fixture proof from public fork transport, authentication, and live MCP operation. Required clean-machine release gates remain separate until exercised.

## Open Questions

1. **Scope conflict requiring an explicit design decision:** Does “hidden repository marketplace at `.agents/plugins/marketplace.json`” mean prepared output or immediate replacement? Existing discovery makes immediate replacement user-visible. Recommend staged generation now and production-path emission only at the flip; an empty replacement catalog also violates shipping-entry continuity.
2. **Shipping payload compatibility:** How will preparation preserve today's combined `.codex-plugin/ycc` consumed by `install.sh` while the future package at that same logical path becomes MCP-free? Recommend a separate preparation destination, not an unrequested installer migration. Whether installer-managed MCP fully compensates for removing bundled MCP is unverified and must not be assumed.
3. **Minimum support evidence:** The spec says >=0.160, whereas the spike explicitly establishes no minimum (ADR:36–38). Is direct 0.160 testing required to claim that floor, or should evidence/reporting be scoped to tested 0.161.0 until baseline testing is available?
4. **Fork acceptance boundary:** The supplied criterion permits a hermetic Git fixture like the spike; release gates also require clean-machine fork installs. Confirm evidence is labeled accurately and does not promote local rewrite proof into a public GitHub transport claim.
5. **Native MCP runtime boundary:** Actual parsing/installation must establish the supported native MCP shape and symbolic secret behavior; the existing installer translation does not by itself prove these. Server authentication or successful live tool calls are outside the supplied installation acceptance unless separately requested.

### Assessment of explicit native output

The proposed `--native-output <DEST>` direction satisfies the business boundary: keep default `.codex-plugin/ycc` and the discovered catalog unchanged while Codex entries remain unlisted, and generate the complete future repository-shaped tree only in an explicit external destination. Generate skills from `ycc` through existing generation helpers rather than copying the shipping generated bundle. This proves the intended package split without maintaining another committed full skills tree.

- Prefer `--native-output` over generic `--output-dir`: it makes clear that this selects future package semantics as well as a destination. `--preview-native` risks implying a dry run, whereas this mode must create installable files.
- Require a separate destination outside the repository to prevent accidental production-path activation or recursive fixture inclusion. Test rejected repository-root and repository-descendant destinations explicitly.
- Optional default generation of unlisted `ycc-mcp` metadata/payload is acceptable only if it cannot alter the shipping catalog, legacy `ycc` payload, installer inputs, or public guides; it is not required to satisfy hidden future-install proof.
- After the authorized manifest flip, default output should route to native semantics from model policy, not require an undocumented permanent CLI flag. Mixed listing states must preserve the shipping `ycc` entry and list only eligible packages; the release transition needs explicit coverage rather than assuming both flags always change together.
- Repeated native output must remove only generator-owned obsolete files, preserve unrelated destination files, and never leave stale MCP in skills-only `ycc` or stale hooks anywhere. Cleanup should follow an explicit generated-file inventory rather than deleting the destination wholesale.
- Check mode must compare future manifests, catalog, skills/shared closure, and MCP payload without mutating repository or destination. Tests should cover deterministic regeneration, stale owned-file pruning, excluded hooks, symbolic secrets, destination safety, and default pre-flip byte stability. These are proposed implementation acceptance checks, not checks exercised in this research.
