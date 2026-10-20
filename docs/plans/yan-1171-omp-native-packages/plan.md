# YAN-1171 — Generate OMP native component packages and marketplace metadata

- **Linear:** YAN-1171 (P-YAN-21). **GitHub:** #390. **Target release:** v6.1.0.
- **Contract:** [ADR 0002](../../internal/adr/0002-omp-runtime-contract.md), spike §1.1–1.7, §2.1–2.2, §5.
- **Base:** `main` (RELEASING.md, trunk-only, tracker `none`).

## Acceptance criteria (from Linear)

1. Packages validate through native CLI/schema checks.
2. Lockstep versions (source: `ycc/.claude-plugin/plugin.json`).
3. Complete closures: every generated skill, agent, command and shared resource ships in `ycc`.
4. Can be hidden until release (`listed` in `ycc/settings/packages.json`).
5. Install from a clean fork at a pinned ref.

## Verified runtime facts (omp 18.12.3, upstream `v18.12.3`)

| Fact                                                                                                                                                    | Evidence                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| Catalog `.omp-plugin/marketplace.json` wins over `.claude-plugin/marketplace.json`; required `name`, `owner.name`, `plugins`; string sources start `./` | `marketplace/fetcher.ts:108-209`                |
| Names: `^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$`, ≤64; runtime package name = `package.json#name`, else plugin name                                   | `marketplace/types.ts:14-21`, `manager.ts`      |
| Version for relative sources (install and upgrade): `.claude-plugin/plugin.json`, root `plugin.json`, catalog entry `version`, `package.json`           | `manager.ts:555-581` (`#resolveCatalogVersion`) |
| Agent `model:` is dropped only for a root with `.claude-plugin/plugin.json` and no `.omp-plugin/plugin.json`                                            | `agent-plugin-format.ts:566-571`                |
| Marketplace command prefix is the catalog plugin name; `--plugin-dir` uses `.claude-plugin/plugin.json` `name`                                          | YAN-1168 live probe                             |
| `omp plugin marketplace add` takes no ref; a pinned ref is a clone whose HEAD is that commit                                                            | CLI help                                        |

## Design decisions

| #   | Decision                                                                                                                                                                                                                                                                                                             |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Package roots are `packages/omp/<key>/`; `ycc` reuses the existing tree. `scripts/generate_omp_packages.py` owns each emitted root whole: it stages the skills, agents and commands through the existing generators (same bytes) and adds the manifests.                                                             |
| D2  | Every emitted root ships `.omp-plugin/plugin.json` (OMP dialect: agent models kept), `.claude-plugin/plugin.json` (`/ycc:` prefix under `--plugin-dir`; first in OMP's version lookup) and `package.json` (unique runtime name), all named after the package key.                                                    |
| D3  | Catalog sources are relative `./packages/omp/<key>` strings. No git-subdir/url/npm sources.                                                                                                                                                                                                                          |
| D4  | Root `.omp-plugin/marketplace.json` exists only when a row is listed and holds exactly the listed rows; otherwise the generator removes it. `--export DIR` writes a repository-shaped tree whose catalog also includes unlisted included rows (harness/tests only).                                                  |
| D5  | Selection: `runtime == "omp"`, `mechanism == "native"`. Only `included` rows are emitted. Only `{skills, agents, commands, shared}` has an emitter; an included or listed row with another component set fails closed (YAN-1173/1174/1175 own them). Deferred/excluded rows emit nothing and their roots are pruned. |
| D6  | Lockstep: the version source is stamped into the catalog entry, `metadata.version`, both plugin manifests and `package.json`.                                                                                                                                                                                        |
| D7  | The `ycc` omp row flips to `included`, `listed: false` (Codex/Cursor precedent: generated and validated before listing). The YAN-1171 gate is removed from every omp row; YAN-1178 stays. `release_versions.py` maps an included native omp row to its three manifests and checks the OMP catalog when present.      |
| D8  | `scripts/validate_omp_native.py` (stdlib, CI): manifest/catalog schema, name rules, lockstep, unique runtime names, catalog = listed rows, closure. `validate-omp-packages.sh` runs generator `--check` (bytes + modes of every package file) then the policy.                                                       |
| D9  | Opt-in `scripts/test-omp-native-packages.sh` (not CI) installs the export from a pinned local fixture inside bwrap with no network, or a real fork at a full SHA with `--public URL --ref SHA`. It fails closed without isolation.                                                                                   |

## Tasks

1. `scripts/generate_omp_packages.py` + `generate-omp-packages.sh` (D1–D6), typed, `mypy --strict`.
2. `scripts/validate_omp_native.py` + `validate-omp-packages.sh` (D8); `scripts/test_generate_omp_packages.py`.
3. Wiring: `sync.sh`/`validate.sh` `omp`, `validate-scope.sh` + scope tests, `pyproject.toml` mypy files.
4. Model flip and release tooling (D7): `packages.json`, `release_versions.py`, `test-release-bundle.sh`.
5. Live harness + `scripts/omp_native_smoke.py` (D9); docs: capability matrix, spike §1.5/§5, README, CONTRIBUTING.
