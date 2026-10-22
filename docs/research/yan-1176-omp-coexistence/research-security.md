# Security research: OMP coexistence trust boundaries

## Executive Summary

OMP has no trust gate, and project config can override user kill switches. ycc ships no OMP-executable code apart from the existing `ycc-mcp` stdio servers. The only tested boundary is `--no-extensions` plus a user `--config` overlay. The new writes are user-scope, hash-owned and limited to owned entries.

## Trust model (verified)

- **No trust prompt.** OMP has no trust gate: `isProjectTrusted: () => true`
  (`src/extensibility/extensions/runner.ts:1433`, `src/session/agent-session.ts:8562`). Installed
  plugins are trusted code (`docs/plugin-manager-installer-plumbing.md:247-249`).
- **What runs at session start, with no prompt and no tool call** (live, `research-live-probes.md`
  § Project code execution):
  - project `.omp/extensions/*.ts`;
  - project `.claude/hooks/{pre,post}/*.ts`;
  - project `.mcp.json` stdio servers;
  - a project `.omp/plugins/installed_plugins.json` that points at any directory with a `.mcp.json`;
  - project `.omp/config.yml` `extensions: [...]`.
- **Project layer beats user kill switches.** A project `.omp/config.yml` with `disabledProviders: []`
  or `mcp.enableProjectConfig: true` overrides a user value. A user-config safety setting is therefore
  not a boundary against a hostile repository.
- **The only tested boundary that ycc's users control:**
  `omp --no-extensions --config <user-owned overlay with mcp.enableProjectConfig: false>`. The overlay
  outranks project config. Under it nothing from the hostile fixture ran, while ycc's user-scope
  packages still loaded.

## ycc's own surface

| Surface                                           | Executes?                                                                                                    | Guard                                                                                                                                                         |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ycc` package (skills, agents, commands markdown) | No: prompt text                                                                                              | `validate_omp_native.py:220` `hook_surface_errors` rejects `extensions`/`hooks`/`tools` keys or dirs, `hooks.json`, and `.ts/.js/.mjs/.cjs` outside `skills/` |
| `ycc-rules`                                       | No                                                                                                           | Rules closure validator                                                                                                                                       |
| `ycc-mcp`                                         | **Yes**: stdio servers (`github` via `sh -c`, `playwright` via `npx`, …) spawn at session start when enabled | Secret-literal audit; `${VAR}` placeholders only. Users disable through `disabledServers`, or `omp plugin disable ycc-mcp@ycc`. **Unchanged by this work**    |
| Skill helper scripts (`skills/**/scripts/*.sh`)   | Only when the model runs them through bash, which goes through OMP approvals                                 | YAN-1175 `--settings` `tools.approvalMode: write`                                                                                                             |
| New dedupe step                                   | Writes the user `config.yml` (`skills.ignoredSkills` only)                                                   | Hash-owned list-union; symlinked or invalid config refused; never writes project config                                                                       |
| New `ycc-server` query on `linear-personal`       | No code. It changes the OMP token key and the request URL                                                    | Linear ignores the parameter (live); the resource stays canonical                                                                                             |

## Findings by Severity

### CRITICAL (hard stops)

- **C1.** Never write project `.omp/config.yml`, `.omp/mcp.json` or project plugin registries from the
  installer. They are committed, shared and applied without a trust prompt (keeps YAN-1175 D10). The
  dedupe step writes the user scope only, including under `--project`.
- **C2.** Never delete or rewrite another target's files (`~/.agents/skills`, `~/.claude/*`,
  `~/.codex/*`) from the OMP target. Deleting `~/.agents/skills` breaks consolidated Codex, Cursor and
  opencode installs, and a user-authored dir with a ycc name could be lost.
- **C3.** Never hide an unowned skill. Only ledger-recorded ycc entries become ignore entries. A
  user-authored `~/.agents/skills/plan` stays visible (W3).
- **C4.** No secrets in the generated `.mcp.json`. The `ycc-server` value is a constant server name,
  and `audit_no_secret_literals` runs on the transformed bytes.

### Warnings (must address)

- **W-1. Hostile repositories.** Document the tested safe invocation and its limits:
  - project plugin **skills** still load as text;
  - `--no-extensions` also disables the user's own extensions (herdr);
  - `--trusted-extension <abs>` re-allows specific files.

  Never claim OMP has a trust gate.

- **W-2. `enabledProviders` widening.** Opting into `claude`, `*` or `all` imports `~/.claude.json` MCP
  servers. Those outrank and shadow `ycc-mcp:*`, so foreign server commands run instead. W4 names this;
  the docs explain that `disabledServers` with the bare names restores `ycc-mcp:*` (verified live: with
  `disabledServers` listing the Claude names, all 9 `ycc-mcp:*` loaded).
- **W-3. OAuth row sharing.** Until YAN-1291 ships, any two OMP MCP entries with one URL share one
  OAuth credential row, so the second account's login silently replaces the first. The `ycc-server`
  query separates the rows per server name.

### Advisories

- **A-1.** The OMP extension path-only dedupe (YAN-1174 herdr note) is unchanged; no ycc component.
- **A-2.** `skills.ignoredSkills` is a visibility filter, not a security control. A skill hidden in OMP
  still exists on disk for other tools.
- **A-3.** Linear's `/authorize` accepted an unrelated `resource` parameter during the probe
  (HTTP 200 page). This is a server-side observation only. ycc relies on the protected-resource
  document, not on authorize validation.

## Dependency Security

No new dependencies. `urllib.parse` and PyYAML are already used (PyYAML lazily, in the YAML profile
only). The Linear endpoint is unchanged; only a query parameter is added, and only for OMP.
