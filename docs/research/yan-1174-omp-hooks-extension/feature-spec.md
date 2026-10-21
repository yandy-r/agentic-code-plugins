# Feature Spec: ycc hooks on OMP (herdr session reporting, WorktreeCreate)

Linear YAN-1174 / GitHub #407. Target release: ystack v6.1.0. Runtime: oh-my-pi (`omp`) 18.12.5,
upstream `can1357/oh-my-pi` tag `v18.12.5` (commit `d5cd750e41fede277f9eb933455da92a0738915e`,
2026-10-21; `packages/coding-agent/package.json` `18.12.5`). herdr: installed `herdr 0.8.2`
(API protocol 20, schema 1); herdr docs at `v0.9.5`.

Evidence tags: **[V-live]** observed with the installed binaries in a throwaway HOME
(`/tmp/omp-yan1174.*`, `/tmp/herdr-lab*.*`; never the user's `~/.omp` or herdr socket);
**[V-src]** upstream source or docs at the tags above; **[INFERENCE]** not verified.

## Executive Summary

ADR 0002 planned a ycc-owned OMP extension that reports the session to herdr on `session_start`,
ported from `ycc/settings/cursor/herdr-session-start.sh`. Research shows that adapter must not be
built:

1. **herdr ships its own first-party OMP integration.** `herdr integration install omp` writes
   `<agentDir>/extensions/herdr-omp-agent-state.ts` (`HERDR_INTEGRATION_ID=omp`,
   `HERDR_INTEGRATION_VERSION=8`). It reports the session **and** the working, blocked and idle
   states on `session_start`, `session_switch`, `agent_start`, `agent_end`, tool approvals and
   `ask` [V-live]. This is a superset of the planned shim.
2. **herdr ignores a ycc-sourced session report.** In an isolated herdr server with a real `omp`
   pane, `pane.report_agent_session` from source `ycc:omp` returned `ok` but recorded nothing.
   The same report from `herdr:omp` set `agent_session` [V-live]. herdr's docs also tell
   third parties not to use the `herdr:` prefix.
3. **Impersonation breaks herdr.** Reusing `herdr:omp` with the Cursor script's nanosecond `seq`
   (ycc's shim template) froze herdr's own microsecond-scale state reports: the pane stayed `idle`
   after a `working` report [V-live]. A second reporter for the same source is a correctness
   hazard, not only a duplicate.

Decision: ship **no** ycc OMP hook or extension. Each hook gets a verdict:

- herdr session reporting is **native, owned by herdr** (`herdr integration install omp`),
  documented and covered by an opt-in live harness.
- `WorktreeCreate` is **unsupported**: OMP has no such event.
- The herdr-managed Claude script is **n/a**.

The `ycc-hooks` OMP row becomes `excluded`. The generator keeps failing closed on a hooks row,
with an actionable message that names the herdr integration. The validator rejects any ycc OMP
package that ships `omp.extensions`, hook files or tool modules, and a verdict-table drift check
keeps the hook inventory and docs honest.

## External Dependencies

### APIs and Services

#### OMP ExtensionAPI contract (verified for the record; no ycc code depends on it)

| Fact                                                                                                                                                                                                                                      | Evidence                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `session_start` payload is exactly `{ "type": "session_start" }`; it has no session id field                                                                                                                                              | [V-src] `src/extensibility/shared-events.ts:30-32`; [V-live] probe logged `event: {"type":"session_start"}`                                                                                                                                                    |
| The session id comes from `ctx.sessionManager.getSessionId()`; the file from `getSessionFile()` (`undefined` with `--no-session`)                                                                                                         | [V-src] `session/session-manager.ts:720-745` (`ReadonlySessionManager`); [V-live] `sessionId: "01a15e99-…"`, `sessionFile: null` under `--no-session`                                                                                                          |
| `session_start` fires in TUI, print, json, rpc and ACP sessions **and in every subagent** (`initializeExtensions` in `task/executor.ts:4887`). `ctx.agent.kind` is `"main"` or `"sub"`; `ctx.hasUI` is false in print, json and rpc modes | [V-src] `modes/runtime-init.ts:212`, `controllers/extension-ui-controller.ts:362`, `acp/acp-agent.ts:2664`, `extensions/types.ts:512-537`; [V-live] rpc: `hasUI:true` (rpc-ui frames), `mode:"rpc"`, `agent.kind:"main"`; print: `hasUI:false`, `mode:"print"` |
| `session_switch` is a separate event: `{type, reason: "new" \| "resume" \| "fork", previousSessionFile}`                                                                                                                                  | [V-src] `shared-events.ts:43-50`; [V-live] RPC `new_session` → `reason:"new"`                                                                                                                                                                                  |
| `pi.exec(cmd, args, {signal?, timeout?, cwd?}) → {stdout, stderr, code, killed}`; on timeout or abort, `code: -1, killed: true`                                                                                                           | [V-src] `exec/exec.ts:9-56`, `extensions/types.ts:1875`; [V-live] `timeout:200` → killed after 271 ms; `AbortController` after 100 ms → killed                                                                                                                 |
| A TS module can locate sibling files: `import.meta.url` is `file://<realpath>?mtime=…`, and `import.meta.dir` is set (Bun)                                                                                                                | [V-live] probe logged `url: "file:///tmp/…/probe.ts?mtime=…", dir: "/tmp/…"`; [V-src] `plugins/legacy-pi-compat.ts:2737-2752` (realpath import)                                                                                                                |
| Handler errors are isolated. A throw becomes an `extension_error` (RPC frame, or `Extension error (<path>): <msg>` on stderr in print mode); later handlers still run; the session starts                                                 | [V-src] `extensions/runner.ts:1551-1638`; [V-live] rpc frame `{"type":"extension_error",…,"event":"session_start","error":"probe-throw"}`, `second_handler_ran`, `get_state` answered                                                                          |
| Per-handler budget: 30 s for `session_start` (it is awaited, so a slow handler delays startup); 2 s for `session_shutdown`. The handler `ctx` carries no abort signal for `session_start`                                                 | [V-src] `runner.ts:133` `EXTENSION_HANDLER_TIMEOUT_MS = 30_000`, `:157` `SESSION_SHUTDOWN_HANDLER_TIMEOUT_MS = 2_000`, `:1564-1570` (signals only for `session_stop` and `tool_call`)                                                                          |
| There is no worktree-creation event: the 70-odd `pi.on` overloads include none                                                                                                                                                            | [V-src] `extensions/types.ts:1648-1720`; `docs/extensions.md`; ADR 0002 §3                                                                                                                                                                                     |
| Duplicate loading: discovery dedupes only by resolved path. Two different files with the same body both load and both fire. Plugin `omp.extensions` for one package name is deduped across scopes (project shadows user)                  | [V-src] `extensions/loader.ts:579-591`, `plugins/loader.ts:262-285`; [V-live] `-e copy.ts -e pkg/…/herdr-session.ts` plus a linked package → 3 factory loads, 3 `session_start` calls (2 distinct files)                                                       |
| `package.json#omp.extensions` loads through `omp plugin link` and marketplace installs; it needs a session restart                                                                                                                        | [V-live] `omp plugin link` in a temp HOME → `plugin list --json` `manifest.extensions`, extension fired; [V-src] `docs/marketplace.md:80`                                                                                                                      |
| `pi.pi.getAgentDir()` resolves the profile-aware agent dir                                                                                                                                                                                | [V-live] printed `<tmp>/home/.omp/agent`                                                                                                                                                                                                                       |
| Shell hooks (`*.sh`, `hooks/hooks.json`) never run; `hooks/pre\|post/*.ts` load as extension factories                                                                                                                                    | [V-src] `docs/hooks.md`, `extension-loading.md` §2; spike §2.4                                                                                                                                                                                                 |
| API floor: `ExtensionContext.agent`, `hasUI`, `mode`, `pi.exec` and the 30 s cap all exist at `v18.12.2`                                                                                                                                  | [V-src] `v18.12.2` `extensions/types.ts:653,661,710,1850`, `runner.ts:133`                                                                                                                                                                                     |

#### herdr (`herdr 0.8.2`, protocol 20)

- **Built-in OMP integration.** `herdr integration status` lists `omp: … (~/.omp/agent/extensions/herdr-omp-agent-state.ts)`.
  `herdr integration install omp` refuses when the agent dir is missing
  (`omp extension directory not found … install omp first`) and otherwise writes the file
  [V-live, temp HOME]. Upstream docs: [Integrations § OMP](https://raw.githubusercontent.com/herdrdev/herdr/v0.9.5/docs/next/website/src/content/docs/integrations.mdx).
- **Integration behavior** (file v8) [V-live source read + run]:
  - `enabled()` requires `HERDR_ENV=1` plus `HERDR_SOCKET_PATH` and `HERDR_PANE_ID`. Otherwise
    the factory returns without registering anything.
  - Root-session gate: `activateRootSession` requires `ctx.hasUI === true`, so subagents and
    print-mode sessions never report.
  - Transport: `node:net`; one request per connection; 500 ms then 1500 ms retry; unref'd
    timers; serialized queue; errors are swallowed.
  - `seq` is microsecond-based (`Date.now()*1000`, incremented).
  - Session ref: `agent_session_path` (absolute session file), else `agent_session_id`.
- **Live run against a fake herdr socket** (rpc, `get_state` + `new_session`):
  - Reports: `report_agent_session {source:"herdr:omp", agent:"omp", session_start_source:"startup", agent_session_path:<file>}`,
    then `report_agent {state:"idle"}`, then the same pair with `session_start_source:"new"`.
  - Without `HERDR_*`: 0 connections.
  - Stalled socket (accepts, never replies): the session is ready and the process exits normally
    (3.03 s wall for a 3 s scripted run).
  - Socket missing (refused): no `extension_error`, `get_state` answered.
- **Socket API.** `PaneReportAgentSessionParams` requires `pane_id`, `source` and `agent`.
  Optional: `agent_session_id`, `agent_session_path`, `seq`, `session_start_source`.
  (`herdr api schema --json`.)
- **Source ownership** [V-live, isolated `herdr server`, real `omp` pane]:

  | Report                                                                  | Result                                                    |
  | ----------------------------------------------------------------------- | --------------------------------------------------------- |
  | `report_agent_session` source `ycc:omp`                                 | `ok`, nothing recorded (`agent_session` absent)           |
  | `report_agent` source `ycc:omp` (state + session id)                    | state applied, session id dropped                         |
  | `report_agent_session` source `herdr:omp`                               | `agent_session: {source:"herdr:omp", kind:"id", value:…}` |
  | `herdr:omp` session at ns `seq`, then `herdr:omp` `working` at µs `seq` | pane stays `idle`: the ns `seq` blocks later reports      |

- **Third-party guidance.** "Don't start [source] with `herdr:`, because Herdr's own integrations
  use that prefix." `seq` must increase across sessions and restarts.
  ([Add Herdr support](https://raw.githubusercontent.com/herdrdev/herdr/v0.9.5/docs/next/website/src/content/docs/add-herdr-support.mdx))

### Libraries and SDKs

None added. No JS runtime enters CI:

- `node` 24.15.0 (mise) locally; CI uses `actions/setup-node` 22 for lint only.
- `bun` 1.4.3 locally.
- The opt-in harness needs `omp`, `herdr` and `python3` only.

### External Documentation

- OMP: [`docs/extensions.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/extensions.md),
  [`extension-loading.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/extension-loading.md),
  [`hooks.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/hooks.md),
  [`plugin-manager-installer-plumbing.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/plugin-manager-installer-plumbing.md),
  [`marketplace.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/marketplace.md).
- herdr: [llms.txt](https://herdr.dev/llms.txt), Integrations, Add Herdr support, Socket API (v0.9.5).

## Business Requirements

### User Stories

- As an OMP user inside herdr, I want my pane to show the OMP agent, its state and its session, so
  that herdr can notify me and resume the session after a restart. I get this by running
  `herdr integration install omp`, not from a ycc package.
- As a ycc maintainer, I want every ycc hook to carry a tested OMP verdict, so that no doc or
  package promises parity OMP cannot deliver.
- As a ycc user installing `--target omp`, I want no ycc extension running in-process without a
  verified need. OMP has no trust prompt.

### Business Rules

1. ycc never reports to herdr from OMP: not as `ycc:omp` (ignored), and never as `herdr:omp`
   (impersonation; it breaks herdr's `seq` ordering).
2. No ycc OMP package may ship `omp.extensions`, `pi.extensions`, `hooks`, `tools`, a `hooks/`,
   `extensions/` or `tools/` root, or a `hooks.json`. The validator enforces this.
3. Keep the `ycc` namespace. The `ycc-hooks` key stays in the model, `excluded` on OMP.
4. "Never claim parity without a tested path": the herdr verdict is native through herdr's
   integration. The opt-in live harness proves trigger, payload, fail-closed, timeout and
   duplicate-freedom with the ycc packages installed.

### Hook Inventory and OMP Verdicts

| ycc hook source                                                                                  | Runtime registration                                                                                             | OMP verdict                                              | Evidence and reason                                                                                                                                       |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ycc/settings/hooks/worktree-create.sh` (`WorktreeCreate`)                                       | Claude `ycc/settings/settings.json#hooks.WorktreeCreate`; generated `packages/claude/ycc-hooks/hooks/hooks.json` | **unsupported**                                          | No OMP worktree event; `.sh` and `hooks.json` never run; OMP task isolation owns its workspaces (`~/.omp/wt`); ycc skills use `.omp/worktrees` (YAN-1170) |
| `ycc/settings/cursor/herdr-session-start.sh` + `ycc/settings/cursor/hooks.json` (`sessionStart`) | Cursor `packages/cursor/ycc-hooks`                                                                               | **native (herdr-owned)**                                 | `herdr integration install omp` (v8) reports session plus state; a ycc report is ignored (`ycc:omp`) or harmful (`herdr:omp`)                             |
| `ycc/settings/hooks/herdr-agent-state.sh`                                                        | herdr-managed Claude integration (`HERDR_INTEGRATION_ID=claude`)                                                 | **n/a**                                                  | Not ycc-owned; herdr's OMP counterpart is the row above                                                                                                   |
| `ycc/mods/status-bar/hooks/hooks.json` (mod module registration, not a lifecycle hook)           | `ycc-mods` marketplace                                                                                           | **unsupported** (unchanged)                              | Different module API; spike §3 status-bar row; outside the drift check (not a lifecycle hook)                                                             |
| `ycc/settings/statusline-command.sh`                                                             | Claude `statusLine`                                                                                              | not a hook (unchanged: adapter, YAN-1175 fallback scope) | Spike §3 status-line row; outside the drift check                                                                                                         |
| Claude `PreToolUse` / `PostToolUse` / `Stop`                                                     | none in ycc                                                                                                      | **unsupported** (unchanged)                              | Capability matrix HOOKS.\*:omp                                                                                                                            |

### Edge Cases

- **Profiles.** herdr writes only to `~/.omp/agent/extensions`. Named OMP profiles
  (`~/.omp/profiles/<n>/agent/extensions`) need the user to copy or link the file
  [INFERENCE from herdr docs and `extension-loading.md` §1]. Document it.
- **Double install.** A copy of the herdr file in both `~/.omp/agent/extensions` and
  `<cwd>/.omp/extensions` loads twice (path dedupe only). herdr tolerates it (same source, monotonic
  µs `seq`), but docs say install once.
- **Old Cursor-style manual shim.** A user who hand-adds `herdr-session-start.sh` logic to OMP
  breaks state ordering. Docs warn.
- **Legacy `ycc-hooks@ycc` from the Claude catalog installed in OMP.** `migrate` already refuses
  with "has no native OMP package yet; uninstall it yourself" (`scripts/omp_install.py:1061`);
  unchanged.

### Success Criteria (AC mapping)

| AC dimension             | Verdict and evidence                                                                                                                                        | Test                                               |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Every hook has a verdict | Inventory table above; ADR 0002 and spike rows                                                                                                              | D6 drift check (CI)                                |
| Trigger                  | herdr integration fires on `session_start` (startup) and `session_switch` (new); never on `WorktreeCreate` (no event)                                       | L1 (live); D1, D3, D4 (CI)                         |
| Payload                  | `report_agent_session` carries `pane_id`, `source:"herdr:omp"`, `agent:"omp"`, `seq`, `session_start_source`, `agent_session_path`; matches herdr schema    | L2 (live)                                          |
| Blocking / error         | Missing or refused socket: no `extension_error`, session ready; OMP isolates handler throws                                                                 | L3, L4 (live); OMP contract table [V-live]         |
| Cancellation             | Sends are fire-and-forget with unref'd timers; shutdown is capped at 2 s by OMP; process exits promptly with a stalled socket                               | L6 (live)                                          |
| Timeout                  | Stalled socket: 500 + 1500 ms internal budget, never awaited by the handler; session ready inside the run budget                                            | L5 (live)                                          |
| Duplicate prevention     | ycc ships no extension (CI-enforced); with ycc packages and herdr integration installed, each session event yields exactly one report pair, all `herdr:omp` | D2, D4, D5 (CI); L7 (live); L8 isolated real herdr |

## Technical Specifications

### Architecture Overview

No runtime component is added. The change is confined to the model, the generator, the validator,
tests, the docs and one opt-in harness:

```text
ycc/settings/packages.json   ycc-hooks.runtimes.omp: excluded, gates []
        │
scripts/generate_omp_packages.py   hooks rows fail closed (herdr message); excluded → nothing emitted, root pruned
scripts/validate_omp_native.py     + hook_surface_errors (no extensions/hooks/tools in any OMP root)
                                   + hook_verdict_errors (inventory == HOOK_VERDICTS; doc rows agree)
scripts/test-omp-herdr-hooks.sh + scripts/omp_herdr_smoke.py   opt-in live proof (temp HOME, fake + isolated herdr)
docs: ADR 0002 amendment, spike §1/§3/§5 rows, capability matrix source, docs/install/omp.md, install.sh help
```

### Data Models

`ycc/settings/packages.json` → `packages.ycc-hooks.runtimes.omp`:

```json
{
  "status": "excluded",
  "listed": false,
  "mechanism": "native",
  "components": ["hooks"],
  "requires": [],
  "target_release": "v6.1.0",
  "experimental": false,
  "opt_in": false,
  "evidence": [
    "docs/internal/adr/0002-omp-runtime-contract.md",
    "docs/internal/spikes/omp-runtime-contract.md",
    "docs/research/yan-1174-omp-hooks-extension/feature-spec.md"
  ],
  "gates": [],
  "notes": "Excluded: herdr ships its own OMP integration (herdr integration install omp), which reports the session and agent state; a ycc reporter is ignored by herdr (non-herdr source) or corrupts herdr's ordering (herdr:omp). WorktreeCreate has no OMP event. ycc ships no OMP hooks or extensions (YAN-1174)."
}
```

`ycc-all.runtimes.omp.notes` drops "ycc-hooks" from "the union of …" and says
"install ycc and ycc-mcp separately".

Validator constants (`scripts/validate_omp_native.py`):

```python
# Keys in package.json (top level, and under "omp"/"pi") and plugin manifests that load code in OMP.
CODE_SURFACE_KEYS = frozenset({"extensions", "hooks", "tools"})
CODE_SURFACE_DIRS = frozenset({"hooks", "extensions", "tools"})
CODE_SUFFIXES = (".ts", ".js", ".mjs", ".cjs")
# Every ycc lifecycle-hook registration → (OMP verdict token, row anchor in the spike §3 matrix).
# Keys are "<source file>" or "<registration file>#<event>"; the check derives the live set from
# ycc/settings/hooks/*, ycc/settings/cursor/hooks.json events, ycc/settings/settings.json#hooks
# events and packages/claude/ycc-hooks/hooks/hooks.json events, and requires equality.
HOOK_VERDICTS: dict[str, tuple[str, str]] = {
    "ycc/settings/hooks/worktree-create.sh": ("**unsupported**", "`worktree-create.sh` (`WorktreeCreate`)"),
    "ycc/settings/hooks/herdr-agent-state.sh": ("**n/a**", "`ycc/settings/hooks/herdr-agent-state.sh`"),
    "ycc/settings/cursor/herdr-session-start.sh": ("**native**", "herdr session reporting"),
    "ycc/settings/cursor/hooks.json#sessionStart": ("**native**", "`ycc/settings/cursor/hooks.json`"),
    "ycc/settings/settings.json#WorktreeCreate": ("**unsupported**", "`worktree-create.sh` (`WorktreeCreate`)"),
    "packages/claude/ycc-hooks/hooks/hooks.json#WorktreeCreate": ("**unsupported**", "Package `ycc-hooks`"),
}
```

### API Design

Generator error (`native_packages`), owner map replaced by an actionable reason map:

```python
COMPONENT_REASONS = {
    "hooks": (
        "ycc ships no OMP hooks: herdr session reporting is herdr's own OMP integration "
        "(`herdr integration install omp`) and WorktreeCreate has no OMP event (ADR 0002, YAN-1174); "
        "keep the row excluded and unlisted"
    ),
    "rules": "owned by YAN-1175; keep the row deferred and unlisted until its emitter lands",
}
# message: f"{where}: no OMP emitter for components {sorted(components)}: {reason}"
```

The `listed=true requires status included` check is unchanged and covers excluded rows.

### System Integration

#### Files to Create

- `scripts/test-omp-herdr-hooks.sh`: opt-in live harness (not CI). Mirrors the
  `test-omp-native-packages.sh` sandbox: `mktemp -d /tmp/omp-herdr-hooks.XXXXXX`, refuses a HOME
  under the real HOME, `env -i` with HOME/XDG/TMPDIR inside the sandbox, scrubs every `HERDR_*`
  from the parent env, uses the null model provider, and needs `omp` and `herdr` on PATH.
- `scripts/omp_herdr_smoke.py`: typed driver. Fake herdr unix-socket recorder (modes `ok`,
  `stall`, `refuse`), the RPC session runner, and the isolated `herdr server` probe.

#### Files to Modify

`ycc/settings/packages.json`, `scripts/generate_omp_packages.py`, `scripts/validate_omp_native.py`,
`scripts/test_generate_omp_packages.py`, `scripts/test_package_model.py`,
`scripts/package_install_plan.py` (comment), `scripts/test_package_install_plan.py`,
`scripts/tests/install/omp.sh`, `scripts/test-release-bundle.sh`, `scripts/lib/validate-scope.sh`,
`scripts/test-validate-scope.sh`, `pyproject.toml`, `install.sh` (help text),
`docs/internal/adr/0002-omp-runtime-contract.md`, `docs/internal/spikes/omp-runtime-contract.md`,
`ycc/skills/_shared/references/target-capability-matrix.md` (then regenerate copies),
`docs/install/omp.md`. See the plan for line-level detail.

#### Configuration

None. No new settings, env vars or runtime dependencies.

## UX Considerations

### User Workflows

#### Primary Workflow: OMP inside herdr

1. `./install.sh install --target omp` installs `ycc@ycc` and `ycc-mcp@ycc`; nothing hook-related.
2. `herdr integration install omp` (once per machine, default profile).
3. Restart running omp sessions. The pane shows `omp`, its state, and resume after a herdr restart.

#### Error Recovery Workflow

- `--package ycc-hooks --target omp` → `package 'ycc-hooks' is excluded or opt-in for target 'omp'`.
  `docs/install/omp.md` explains why and points to `herdr integration install omp`.
- Pane shows no agent: check `herdr integration status` (`omp: current (v8)`), the profile path,
  and `HERDR_ENV=1` in the pane.

### UI Patterns

None.

### Accessibility Requirements

N/A (no UI).

### Performance UX

No ycc code runs at OMP session start. Startup cost from herdr's integration is non-blocking
(`void` sends) [V-live].

## Recommendations

### Implementation Approach

1. Model flip and generator message (fail-closed preserved).
2. Validator code-surface check and verdict drift check, with golden tests.
3. Docs: ADR amendment, spike rows, capability matrix, install docs; then `sync.sh` to propagate the
   matrix copies.
4. Opt-in live harness.

### Technology Decisions

| Decision                            | Choice                                           | Rationale                                                                                                                  |
| ----------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| herdr reporting on OMP              | herdr's integration (native, herdr-owned)        | Superset of the shim; only `herdr:` sources are recorded; impersonation corrupts ordering; vendor-owned updates            |
| `ycc-hooks` OMP row                 | `excluded`, `gates: []`                          | Nothing to ship. `deferred` would imply a future emitter. Mirrors `ycc-hooks`/codex and `ycc-all`/omp                      |
| Typed ycc TS extension (`node:net`) | rejected                                         | Ignored by herdr as `ycc:omp`; harmful as `herdr:omp`; in-process full-trust code with no benefit                          |
| `pi.exec` of the ycc shell script   | rejected                                         | Same source problem; adds `python3` and process spawn at startup; a `session_start` handler is awaited (blocks up to 30 s) |
| Duplicate prevention                | Structural (ycc ships nothing) + validator       | Strongest guarantee; tested in CI without a JS runtime                                                                     |
| Live proof                          | Opt-in harness, temp HOME, fake + isolated herdr | Requires `omp` and `herdr` binaries; CI stays Python-only                                                                  |

### Quick Wins

- The `install.sh` help line and the `docs/install/omp.md` herdr section give users the one command
  they need.

### Future Enhancements

- If herdr adds a `pane.report_agent_session` that accepts third-party sources for an
  already-detected agent, revisit. Not planned.
- YAN-1178 may fold `test-omp-herdr-hooks.sh` into the live acceptance matrix.

## Risk Assessment

### Technical Risks

| Risk                                                         | Likelihood | Impact | Mitigation                                                                                 |
| ------------------------------------------------------------ | ---------- | ------ | ------------------------------------------------------------------------------------------ |
| herdr changes or drops its OMP integration                   | Low        | Medium | Harness L1/L2 pin the observed contract; docs cite herdr's version (0.8.2, integration v8) |
| Verdict drift check is too brittle against doc edits         | Medium     | Low    | Anchors are short row prefixes; the error message names the expected anchor and verdict    |
| Release notes or planner tests assert the old `deferred` row | High       | Low    | Enumerated in the plan (release bundle, planner, install `omp.sh`)                         |

### Integration Challenges

- Matrix copies under `packages/*`, `.codex-plugin`, `.agents-plugin` and `.opencode-plugin` are
  generated. Edit only `ycc/skills/_shared/references/target-capability-matrix.md`, then run
  `./scripts/sync.sh`.

### Security Considerations

#### Critical — Hard Stops

- Never emit a source starting with `herdr:` from ycc code (impersonation; ordering corruption
  [V-live]).
- Harness: never touch the real `~/.omp`, the real herdr socket or `HERDR_*` of the parent shell.
  Scrub `HERDR_*`, refuse a HOME under the real HOME, and use `/tmp` sandboxes only.

#### Warnings — Must Address

- Any future OMP code surface in ycc packages is full-trust in-process code with no OMP prompt. The
  validator now rejects it by default; adding one requires changing the validator deliberately.

#### Advisories — Best Practices

- Docs should tell users to install herdr's integration once (user scope) and not also add a
  project copy.

## Task Breakdown Preview

### Phase 1: Model and generator

`packages.json` flip, `COMPONENT_REASONS`, generator, model, planner, install and release tests.

### Phase 2: Validator guards

`hook_surface_errors`, `hook_verdict_errors`, and their golden tests.

### Phase 3: Docs and harness

ADR, spike, matrix, install docs, `install.sh` help; opt-in live harness; validate-scope wiring;
`sync.sh` + `validate.sh`.

## Decisions Needed

None. The direction was approved by Main on 2026-10-21: no ycc OMP extension, `ycc-hooks` OMP
`excluded`, herdr reporting native through herdr's integration, `WorktreeCreate` unsupported.

## Research References

- herdr integration source: `herdr integration install omp` output (`herdr-omp-agent-state.ts`, v8)
  in a temp HOME.
- Probes (reproducible; see the plan's harness): `omp --mode rpc --no-session -e probe.ts`
  (payload, ctx, exec timeout and abort, throw isolation); `omp plugin link` a fixture
  `omp.extensions` package; isolated `herdr server` with `HOME`/`XDG_*` in `/tmp` and
  `herdr pane run <pane> "omp --no-extensions"`.
- Repo: `docs/internal/adr/0002-omp-runtime-contract.md`,
  `docs/internal/spikes/omp-runtime-contract.md` §2.3–2.4, §3, §5;
  `scripts/generate_omp_packages.py`, `scripts/validate_omp_native.py`; YAN-1173 commit `749f155`.
