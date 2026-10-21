# Feature Spec: ycc rules, context, settings, model roles and approvals on OMP

Linear YAN-1175 / GitHub #412. Target release: ystack v6.1.0. Runtime: oh-my-pi (`omp`) 18.12.5,
upstream `can1357/oh-my-pi` tag `v18.12.5` (commit `d5cd750e41fede277f9eb933455da92a0738915e`).
Supported floor stays `>=18.12.2` (ADR 0002). The spike already showed marketplace `rules/`
loading at 18.12.2 (`ALWAYSRULEMARK`, spike §2.7).

Evidence tags:

- **[V-live]**: observed with the installed `omp 18.12.5` in a throwaway HOME
  (`/tmp/omp-yan1175.6n5WIi`; null provider `spike-null/null-model` and `null-two` on
  `127.0.0.1:9`; never the user's `~/.omp`).
- **[V-src]**: upstream source or docs at the tag above. Paths are relative to the upstream repo
  root, and `src/` means `packages/coding-agent/src/`.
- **[INFERENCE]**: not verified.

## Executive Summary

YAN-1175 covers five payloads that ADR 0002 left as "adapter" or "fallback". Research decides each one:

1. **Rules: native `ycc-rules` package, adapter for the layout.**
   - **Layout.** OMP loads `<plugin>/rules/*.{md,mdc}` from marketplace and `--plugin-dir` roots. The scan is flat (non-recursive), the rule name is the file stem, and the first name wins by provider priority [V-src] [V-live].
   - **Transform.** ycc flattens the nested tree into 31 files named `ycc-<family>-<stem>.md`. `paths` becomes `globs`; `description` and `alwaysApply` are kept.
   - **No parity claim for `globs`.** On OMP, `globs` only annotate the rulebook listing. They never auto-attach a rule the way Cursor does [V-src docs] [V-live]. Language rules therefore run as on-demand rulebook entries (`rule://ycc-golang-coding-style`), which is **partial** parity.
   - **Package row.** The `ycc-rules` OMP row flips to `included`; `listed` stays false until YAN-1180.
2. **Global instructions (`ycc/settings/rules/AGENTS.md`): installer fallback.** `install.sh --target omp --rules` symlinks the file to `<agentDir>/AGENTS.md`. It refuses to replace a real user file unless `--force` is given. A symlinked `AGENTS.md` and an `@path` import from the user's own file both load [V-live]. OMP gives plugins no context-file channel [V-src].
3. **Settings and model roles: opt-in managed merge into the user `config.yml`.**
   - **Trigger.** Only `install --target omp --settings` writes settings. It merges a few ycc-owned leaves into `<agentDir>/config.yml`, using the existing `merge_managed_config.py` per-leaf SHA-256 ownership (new YAML format).
   - **User edits survive.** An edit by the user wins over the next update.
   - **Project wins.** A project `.omp/config.yml` still beats the user layer [V-live], and the opt-in harness tests this.
   - **No overlay file.** A `--config`/`PI_CONFIG_FILES` overlay is rejected. It outranks project and user config, which inverts precedence, and a missing overlay is a hard startup error [V-live].
4. **`ycc/settings/models.json` gains `targets.omp`.**
   - **Role mapping.** Claude intent maps to the OMP roles `default`, `slow` and `task`. Values are full `provider/model:effort` selectors.
   - **Agent aliases.** The Claude agent-model aliases (`opus` → `@slow`, `sonnet` → `@task`) move from the hard-coded generator constant into this file.
   - **Validation.** `scripts/validate-model-settings.py` validates role names, selector shape, thinking levels, alias closure and the managed snippet.
   - **Per-agent overrides** stay in agent frontmatter, which OMP supports for `.omp-plugin` roots [V-live spike]. ycc never writes `task.agentModelOverrides`.
5. **Approvals: one managed default, `tools.approvalMode: write`, applied only by `--settings`.**
   - **Effect.** Read and write tools are auto-approved; `exec` tools prompt in the main session.
   - **Limits (stated, not hidden).** Subagents are forced to `yolo` [V-src], and a project config can weaken any user value [V-live].
   - **Excluded.** ycc never writes `yolo`, `bash.patterns` or per-tool `deny`.
6. **Status line: unsupported.**
   - OMP has no command-backed renderer. The only code path is an extension, which the YAN-1174 code-surface guard rejects.
   - OMP's built-in `statusLine` already renders path and git [V-live config list].
   - ycc ships no `statusLine.*` keys: they are user taste, not policy.

## External Dependencies

### APIs and Services

#### OMP rules contract

| Fact                                                                                                                                                                                                                                                                            | Evidence                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Marketplace and `--plugin-dir` roots load `rules` through the `claude-plugins` provider (priority 70). The path `path.join(root.path, "rules")` is hard-coded, with extensions `md` and `mdc`                                                                                   | [V-src] `src/discovery/claude-plugins.ts:263-282`, `:715-721`                                                                                                                                      |
| The scan is flat. `loadFilesFromDir` defaults to non-recursive `*.{md,mdc}` and skips hidden and git-ignored files                                                                                                                                                              | [V-src] `src/discovery/helpers.ts:592-632`; [V-live] `rules/nested/deep.md` (`alwaysApply: true`) never appeared in the prompt                                                                     |
| The rule name is the file basename minus `.md`/`.mdc`. Dedupe is first-wins by name in provider-priority order                                                                                                                                                                  | [V-src] `helpers.ts:256-266`, `src/capability/rule.ts:392-396`, `src/capability/index.ts:202-236`                                                                                                  |
| Priorities: native (`<cwd>/.omp/rules`, `<agentDir>/rules`, `RULES.md`) 100 > `omp-plugins` 90 > `agents` 70 = `claude-plugins` 70 > `cursor` 50 > `github` 30 > `builtin-defaults` 1. `.claude/rules` is not read                                                              | [V-src] `docs/rulebook-matching-pipeline.md:35-44`, `src/discovery/builtin.ts:45,402-433`; scout read of `claude.ts` (no rule provider)                                                            |
| A same-named user rule (`<agentDir>/rules/x.md`) or project rule (`<cwd>/.omp/rules/x.md`) silently shadows a plugin rule                                                                                                                                                       | [V-live] user `common-always.md` replaced the plugin body (`USERRULEMARK`); project `python-coding-style.md` replaced the plugin entry; project `ycc-common-security.md` replaced the plugin one   |
| A project `.omp/rules` is read at cwd only, with no ancestor walk                                                                                                                                                                                                               | [V-src] `builtin.ts:61-73`; [V-live] from `proj/pkg/sub` the project shadow was gone and the plugin body (`PLUGSEC`) loaded                                                                        |
| Frontmatter fields: `description`, `globs` (string or list), `alwaysApply` (`=== true`), `enabled`, and TTSR fields (`condition`, `astCondition`, `question`, `scope`, `interruptMode`, `agents`). `paths` is not a field                                                       | [V-src] `helpers.ts:225-254`, `rule.ts:19-50`; [V-live] a `paths:` rule listed with empty globs: `- paths-rule (): …`                                                                              |
| Buckets: TTSR first, then `alwaysApply`, which puts the full body in `<generic-rules>`, then `description`, which puts a one-line `- <name> (<globs>): <description>` entry in `<domain-rules>` with the body on demand via `rule://<name>`. A rule with none of these is inert | [V-src] `src/capability/rule-buckets.ts:49-85`, `src/prompts/system/system-prompt.md:38-65`; [V-live] the `get_state.systemPrompt` excerpt below; a `globs`-only rule (`GLOBSONLYBODY`) was absent |
| `globs` never auto-select a rule. They are advisory text in the listing and a path gate only for TTSR                                                                                                                                                                           | [V-src] `docs/rulebook-matching-pipeline.md:248,321`; `docs/ttsr-injection-lifecycle.md:63`                                                                                                        |
| `ttsr.disabledRules: [name, …]` removes named rules of every bucket                                                                                                                                                                                                             | [V-live] `disabledRules: [common-always, python-coding-style]` removed both from the prompt; [V-src] `rule-buckets.ts:49-85`                                                                       |
| `<agentDir>/RULES.md` is a sticky user rule, always applied, rendered before plugin always-rules                                                                                                                                                                                | [V-live] `STICKYMARK` preceded `ALWAYSMARK` in `<generic-rules>`                                                                                                                                   |
| No plugin manifest key points at rules. `rules/` is a directory convention only                                                                                                                                                                                                 | [V-src] `src/extensibility/plugins/types.ts:27-48`; `docs/skills/authoring-marketplaces.md`                                                                                                        |

Live rules probe [V-live], with `--plugin-dir` pointing at a fixture holding the final naming scheme:

```text
omp --mode rpc --no-session --no-title --model spike-null/null-model --plugin-dir <fixture>  <<< '{"id":"state","type":"get_state"}'
# Skills & Rules
<domain-rules>
- ycc-golang-coding-style (**/*.go, **/go.mod, **/go.sum): When working on Go files, apply formatting.
- ycc-web-performance (): WEBPERF
- ycc-web-testing (): WEBTEST
</domain-rules>
```

An `alwaysApply: true` rule rendered as `<generic-rules>\nALWAYSMARK body.\n</generic-rules>` ahead
of `<domain-rules>`.

#### OMP context files

| Fact                                                                                                                                                                                                                      | Evidence                                                                                                        |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| The user context file is `<agentDir>/AGENTS.md` (native, priority 100; one user file wins). Project: nearest non-empty `.omp/AGENTS.md`, plus standalone `AGENTS.md`/`CLAUDE.md` on a walk to the repo root (priority 10) | [V-src] `src/discovery/builtin.ts:942-974`, `docs/context-files.md:19-25`                                       |
| The user file and a project `AGENTS.md` both load, user first, in one `<repo-rules>` block. A `.omp/AGENTS.md` at the same depth shadows the standalone project file                                                      | [V-live] `USERAGENTSMARK` then `PROJAGENTSMARK`; with `.omp/AGENTS.md` present, `PROJOMPAGENTSMARK` replaced it |
| A symlinked `<agentDir>/AGENTS.md` loads. An `@/abs/path` import inside the user's own `AGENTS.md` is expanded inline                                                                                                     | [V-live] symlink → `YCCGLOBALMARK` present; `MYOWNMARK\n@<file>` → both markers present                         |
| No plugin provider registers context files or `SYSTEM.md`/`APPEND_SYSTEM.md`                                                                                                                                              | [V-src] scout read of `src/capability/context-file.ts` providers; `src/main.ts:1355-1366`                       |
| Task subagents drop inherited `AGENTS.md` and keep `CLAUDE.md`/`GEMINI.md`                                                                                                                                                | [V-src] `docs/system-prompt-customization.md:87-93`                                                             |

#### OMP settings contract (`config.yml`)

| Fact                                                                                                                                                                                  | Evidence                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The user file is `<agentDir>/config.yml`, or an existing `config.yaml`. `<agentDir>` follows `--profile`/`OMP_PROFILE`/`PI_CODING_AGENT_DIR`. `omp config path` prints it             | [V-src] `docs/settings.md:17-26`; [V-live] `omp config path` → `<tmp>/home/.omp/agent`                                                                                                                                                                    |
| The project file is `<cwd>/.omp/config.yml` (plus `.omp/settings.json`), cwd only, with no ancestor walk                                                                              | [V-src] `docs/settings.md:19,30`; [V-live] from a subdir the project `write` vanished and the user `always-ask` applied                                                                                                                                   |
| Precedence, low to high: defaults < user < project < overlays (`PI_CONFIG_FILES`, then `--config`) < runtime flags < setting env vars. Objects deep-merge; scalars and arrays replace | [V-src] `docs/settings.md:112-127,165-169`, `src/config/settings.ts:3935-3954`                                                                                                                                                                            |
| Project beats user for `modelRoles` and for `tools.*`                                                                                                                                 | [V-live] user `default: null-two` + project `default: null-model` → `get_state.model` = `null-model`; user `approvalMode: always-ask` + project `yolo` → effective `yolo`; user `tools.approval.bash: deny` + project `allow` → effective `{bash: allow}` |
| An overlay beats the project file. A missing overlay is a hard error                                                                                                                  | [V-live] `--config` overlay `default: null-two` won over project and user; `PI_CONFIG_FILES=<missing>` → exit 1, `Config overlay not found`                                                                                                               |
| Plugins cannot contribute settings. The manifest `settings` map is per-plugin config stored in `omp-plugins.lock.json`                                                                | [V-src] `src/extensibility/plugins/types.ts:47-48`; `docs/marketplace.md:235,248`; spike §2.6                                                                                                                                                             |
| `omp config set` writes only the user file. It **drops comments**, and setting a record **replaces the whole record**. It preserves symlinked configs                                 | [V-live] `# USER COMMENT keep me` and an inline comment were gone after `config set tools.approvalMode write`; `config set modelRoles '{"smol":…}'` dropped `default` and `slow`; a symlinked `config.yml` stayed a symlink                               |
| Dotted leaves under records are not addressable from the CLI                                                                                                                          | [V-live] `omp config set modelRoles.slow …` → `Unknown setting: modelRoles.slow` (same for `task.agentModelOverrides.architect`, `tools.approval.eval`)                                                                                                   |
| File layers are not validated against known keys: an unknown top-level key is ignored. An invalid enum value is ignored and the default applies                                       | [V-live] `yccUnknownKey: 1` → session started, rc 0; `approvalMode: always_ask` (typo) → effective `yolo`; [V-src] `src/config/registry.ts:645-652`                                                                                                       |
| Invalid YAML in a persistent file is moved to `.broken-*` and startup fails                                                                                                           | [V-src] `docs/settings.md:38`, `docs/config-usage.md:193-198`                                                                                                                                                                                             |

#### Model roles

| Fact                                                                                                                                                                                                                                                                                                    | Evidence                                                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Built-in chat roles: `default, smol, slow, vision, plan, commit, tiny, memory, task, advisor, widget`. Kind roles: `image, web, speech, dictation, judge`. Custom role names are allowed                                                                                                                | [V-src] `src/config/model-roles.ts` (`MODEL_ROLES`); `docs/models.md:686-715`                                                                                                                                    |
| Selector: `provider/modelId[:thinking]`, with thinking ∈ `off, minimal, low, medium, high, xhigh, max, auto, inherit`. A comma-separated list is an ordered model-resolution fallback (first resolvable entry wins); it is not a retry chain for failed requests (`retry.fallbackChains`, out of scope) | [V-src] `docs/settings.md:380`, `docs/models.md:645-652`; [V-live] `default: spike-null/missing, spike-null/null-two` → `null-two`; `:high` suffix accepted                                                      |
| Role alias: canonical `@role`, legacy `pi/role`, and `*` = `@default`. An alias resolves only to a built-in or configured role                                                                                                                                                                          | [V-src] `src/config/model-roles.ts:18-26`, `src/config/model-resolver.ts:1052-1060`; [V-live] `default: "@slow"` and `default: pi/slow` both → `null-two`                                                        |
| Fallbacks: `tiny`→`smol`, `memory`→`tiny`, `widget`→`smol`, and `advisor`→configured `slow` only. Unset `smol`/`slow` inherit an explicit `default`                                                                                                                                                     | [V-src] `model-resolver.ts:1120-1135`; `docs/models.md:~716`; `docs/settings.md:462`                                                                                                                             |
| Subagent model precedence: request override > `task.agentModelOverrides[name]` > agent frontmatter `model` > parent model                                                                                                                                                                               | [V-src] `docs/task-agent-discovery.md:224-230`; `model-resolver.ts:1283-1333`                                                                                                                                    |
| Frontmatter `model` is kept only for `.omp-plugin` roots (dropped for Claude-dialect roots). Generated ycc agents carry `@slow` (23) or `@task` (29); 3 inherit                                                                                                                                         | [V-live] spike (`PROBE model-agent model=@smol`); repo `packages/omp/ycc/agents/*.md` (`grep ^model:`)                                                                                                           |
| An unresolvable role does not fail startup: the main session falls back to an available model. A subagent falls back to the parent when the resolved model has no credentials                                                                                                                           | [V-live] overlay `default: spike-null/does-not-exist` → session ran on `null-model`, no stderr; [V-src] `src/sdk.ts:3232-3277`, `src/task/executor.ts:4448-4460`                                                 |
| The ycc ids exist in OMP's bundled catalog: `anthropic/claude-fable-5-1` and `anthropic/claude-opus-5` (adaptive thinking `low…max`, 1M context), and `openai/gpt-6-astra`, `openai/gpt-5.6-sol`                                                                                                        | [V-src] `packages/catalog/src/models.json`; [V-live] `omp models find <id> --kind all --json` listed each `selector` with dummy `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` (≈1 s; empty `{"models":[]}` without a key) |

#### Approvals

| Fact                                                                                                                                                     | Evidence                                                                                     |
| -------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `tools.approvalMode`: `always-ask` (auto: read), `always-ask-cached`, `write` (auto: read and write; prompts exec), and `yolo`, which is the **default** | [V-src] `docs/approval-mode.md:18-25`; [V-live] `omp config get tools.approvalMode` → `yolo` |
| `tools.approval.<tool>: allow \| prompt \| deny` overrides the mode. `bash.patterns` (ordered `match`/`approval`) governs `bash` only, not `eval`        | [V-src] `docs/approval-mode.md:10,101`; `docs/settings.md:185-216`                           |
| Subagents run headless with `approvalMode: yolo`. A `deny` still applies, and any `prompt` rejects                                                       | [V-src] `src/task/executor.ts:1182`; `docs/approval-mode.md:201`                             |
| A prompt with no UI fails closed                                                                                                                         | [V-src] `docs/approval-mode.md:82`                                                           |
| No trust gate: `isProjectTrusted()` is always `true`, so project config applies unprompted                                                               | [V-src] `docs/extensions.md:362`                                                             |

#### Status line

| Fact                                                                                                                                                                                                                                 | Evidence                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| The built-in `statusLine.*` keys are `preset` (`default\|minimal\|compact\|full\|nerd\|ascii\|custom`), `leftSegments` (default `vim, model, mode, path, git, pr`), `rightSegments`, and others. There is no command-backed renderer | [V-live] `omp config list`; [V-src] `docs/settings.md:844-884`, `packages/tui/src/status-line/schema.ts` |
| Code can only add status text through an extension (`ctx.ui.setStatus`, `setWidget`). `setFooter` is a no-op                                                                                                                         | [V-src] `src/modes/controllers/extension-ui-controller.ts:162,192-193`; `docs/extensions.md:885-886`     |

### Libraries and SDKs

No new dependencies:

- PyYAML is already imported on the OMP install path. `omp_install.py` → `generate_codex_common` imports `yaml` (AST walk of the import graph), and `generate_cursor_rules.py` imports it too.
- The live harness needs only `omp` and `python3`.

### External Documentation

OMP: [`rulebook-matching-pipeline.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/rulebook-matching-pipeline.md),
[`context-files.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/context-files.md),
[`settings.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/settings.md),
[`models.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/models.md),
[`task-agent-discovery.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/task-agent-discovery.md),
[`approval-mode.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/approval-mode.md),
[`system-prompt-customization.md`](https://github.com/can1357/oh-my-pi/blob/v18.12.5/docs/system-prompt-customization.md).

## Repo Current State

- **`ycc/settings/packages.json`.**
  - `ycc-rules.runtimes.omp` is `deferred` and unlisted, with `native` and `["rules"]`. Its gates are `YAN-1175 rules flattener` and `YAN-1178 live acceptance matrix…`.
  - `installer-fallback.runtimes.omp` is `deferred`, with `file-copy` and `["rules","instructions","settings","statusline"]`. Its gate is `YAN-1175 settings, rules, and modelRoles fallback snippets`.
- **`scripts/generate_omp_packages.py:63-70`.** `COMPONENT_REASONS["rules"]` fails closed ("owned by YAN-1175"). `native_packages()` (`:109-132`) accepts only `WORKFLOW_COMPONENTS` or `MCP_COMPONENTS`. The test `scripts/test_generate_omp_packages.py:193-203` asserts the YAN-1175 failure.
- **`scripts/generate_cursor_rules.py`.**
  - It mirrors `ycc/rules` (nested) into `packages/cursor/ycc-rules/rules/**.mdc`.
  - It maps `paths`→`globs`, coerces `alwaysApply`, and drops `globs` when `alwaysApply` is set.
  - It skips `hooks.md`. Lint: at most 2 `alwaysApply` rules with at most 60 body lines (`:95-96`), and no `~/.claude/`.
- **Rules source.** 37 rule files plus `README.md`. Minus the six `hooks.md`, that leaves 31: 9 `common`, 4 each for `golang`, `python`, `rust` and `typescript`, and 6 `web`. `alwaysApply: true` is set only on `common/security.md` (32 body lines) and `common/git-workflow.md` (15). One relative link: `web/testing.md:42` → `performance.md`.
- **`scripts/generate_omp_agents.py:60-65`.** `MODEL_MAP` is hard-coded: `opus`→`@slow`, `sonnet`→`@task`, `inherit`→no key. It does not read `models.json`.
- **`ycc/settings/models.json`.** It has `targets.{claude,codex,opencode,cursor}` and no `omp`. `scripts/validate-model-settings.py` is the cross-target validator and has no OMP checks. The `$comment` names a non-existent `validate-model-settings.sh`.
- **`scripts/merge_managed_config.py`.**
  - It tracks per-leaf ownership, hashes only, in `~/.config/ycc/managed-config-state.json`.
  - Policies: `scalar`, `object`, `map-entries`, `deep`, `list-union`.
  - Formats: JSON/JSONC and TOML; no YAML.
  - It restores the original bytes on failure (`:1376-1392`). It refuses a symlinked Cursor hooks destination (`:1449`). Its `atomic_write` replaces symlinks (`:418-424`).
- **OMP installer.**
  - `scripts/omp_install.py` and `scripts/lib/install/targets/omp.sh` write no config.
  - `omp_valid_steps` returns `base`. `omp_config_groups` is empty.
  - `scripts/tests/install/omp.sh:191-194` asserts that the `settings` intent is unsupported.
  - `CARRIERS["omp"]` (`scripts/package_install_plan.py:56-62`) has no `rules`, `settings` or `instructions`.
  - `select_packages` (`omp_install.py:121-137`) defaults to every included, native, non-opt-in OMP row.
- **Other targets' global instructions.** `link_rules_file` (`scripts/lib/install/core.sh:51-65`) refuses to replace a real file without `--force`. Removal uses `unlink_owned_link` (`:134-144`).
- **Docs.**
  - `docs/install/omp.md:42-43,284-285` says rules, settings and `modelRoles` wait on YAN-1175.
  - The capability matrix packaging row (`target-capability-matrix.md:76`) says "`ycc-rules` deferred to v6.1.0".
  - ADR 0002 rows `:78,82-84` and required adapter 4 cover this issue.

## Business Requirements

### User Stories

- As an OMP user, I want the ycc rule families in my sessions without editing files, so the two always-on policies (security, git workflow) apply and language guidance is one `rule://` read away.
- As an OMP user, I want to keep my own rules, instructions and settings, and have them survive every ycc update.
- As an OMP user, I want ycc's model intent (main, thinking and subagent models) and a safer approval default available as an explicit opt-in, never a silent change.
- As a project maintainer, I want my `.omp/config.yml` and `.omp/rules` to beat anything ycc installs at user scope.
- As a ycc maintainer, I want model ids, role names and the managed snippet validated in CI, so a typo cannot ship a dead role.

### Business Rules

1. **Never clobber.**
   - ycc writes only ycc-owned files (package cache, a `<agentDir>/AGENTS.md` symlink) and ycc-owned leaves in the user `config.yml`, tracked by hash.
   - It never writes a project `.omp/config.yml`, `.omp/rules` or `.omp/AGENTS.md`.
   - It never writes through a symlinked `config.yml`.
2. **Opt-in for settings.** `install --target omp` installs packages only (`ycc`, `ycc-mcp`, `ycc-rules`). Settings need `--settings`; instructions need `--rules`.
3. **Precedence is OMP's, not ycc's.** No overlay file. Project config beats user config, and a user edit to a ycc-managed leaf beats ycc.
4. **Full runtime-valid model references.** Every managed selector is either `provider/model[:thinking]` or `@<role>`, where the role is built-in or declared. Bare ids and legacy `pi/` are rejected.
5. **No parity claims.** Language rules are `partial` on OMP (no glob auto-attach). The status line is `unsupported`. `tools.approvalMode: write` does not gate subagents, and the docs say so.
6. **No OMP code surface.** `ycc-rules` ships only `rules/*.md` plus manifests. The YAN-1174 guard stays.

### Edge Cases

| Case                                               | Behavior                                                                                                                                                                                                                                                                                                                                                                             |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| User has `<agentDir>/rules/ycc-common-security.md` | It shadows the package rule (native priority 100) and survives updates. This is the documented override [V-live]                                                                                                                                                                                                                                                                     |
| User wants a ycc rule off                          | `ttsr.disabledRules: [ycc-web-design-quality]` [V-live]                                                                                                                                                                                                                                                                                                                              |
| Project at a subdirectory cwd                      | Project `.omp/rules`/`config.yml` apply only at the `.omp` dir's cwd [V-live]. Document this                                                                                                                                                                                                                                                                                         |
| User has a real `<agentDir>/AGENTS.md`             | `--rules` refuses. The user can add `@<checkout>/ycc/settings/rules/AGENTS.md` to their own file [V-live], or pass `--force`                                                                                                                                                                                                                                                         |
| `config.yml` is a symlink (dotfiles)               | `--settings` refuses to write and prints the snippet (`atomic_write` would replace the link)                                                                                                                                                                                                                                                                                         |
| `config.yaml` exists instead of `config.yml`       | The merge targets `config.yaml` (OMP loads and updates it in place) [V-src `settings.md:17`]                                                                                                                                                                                                                                                                                         |
| `config.yml` has comments                          | They are dropped on re-serialize, as `omp config set` already does [V-live]. Before any rewrite that would drop content (the file is not exactly ycc's output), save it to `config.yml.ycc-backup` (mode 0600), rotating to `.ycc-backup.N` instead of overwriting, and warn on every such rewrite                                                                                   |
| `config.yml` is invalid YAML                       | Refuse with no write. OMP would otherwise move it to `.broken-*`                                                                                                                                                                                                                                                                                                                     |
| The user later runs `omp config set modelRoles …`  | OMP replaces the whole record [V-live], so ycc leaves the user did not set disappear. The existing helper rule "destination leaf missing → write repo value" (`merge_managed_config.py:17`) re-adds them on the next `--settings` run, and a role the user set is kept. Document this: to keep your own value, set it; to stop ycc managing settings, run `remove --intent settings` |
| No Anthropic credentials                           | Managed roles carry an ordered fallback (`anthropic/…, openai/…`). If nothing resolves, OMP falls back to an available model (no crash) [V-live]                                                                                                                                                                                                                                     |
| Named profiles                                     | All paths come from `omp config path` (profile- and XDG-aware), never a hard-coded `~/.omp` (ADR 0002)                                                                                                                                                                                                                                                                               |
| `--project --settings` or `--project --rules`      | Rejected for OMP: "omp settings and instructions are user-scope; edit `<root>/.omp/config.yml` by hand"                                                                                                                                                                                                                                                                              |

### Success Criteria (AC mapping)

| Acceptance criterion                                  | How it is met                                                                                                                                                                                              | Test                                       |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| Generated context and settings validate               | `validate_omp_native.py` adds `rules_closure_errors`. `validate-model-settings.py` adds OMP checks, and the snippet must be valid YAML whose keys exist in the pinned OMP key list                         | T-G1–G6, T-M1–M7 (CI)                      |
| Model references use full runtime-valid ids and roles | Selector grammar, built-in role list, thinking levels, alias closure (agent `@slow`/`@task` resolve), with catalog presence checked live                                                                   | T-M1–M7 (CI); L5 (live, `omp models find`) |
| User edits survive updates                            | Hash ownership for config leaves (user edit wins). Rules override by name in the native dirs. `AGENTS.md` refuses real files                                                                               | T-S1–S10 (CI); L3, L6 (live)               |
| Project/user precedence is tested                     | Live: project `.omp/config.yml` `modelRoles`/`tools.approvalMode` beat ycc-managed user values, and project `.omp/rules/ycc-*.md` beats the package rule. CI: the installer never writes the project layer | L4, L7 (live); T-I3 (CI)                   |

## Technical Specifications

### Architecture Overview

```text
ycc/rules/**  ──generate_omp_rules.py──▶ packages/omp/ycc-rules/{.omp-plugin,.claude-plugin,package.json,rules/ycc-*.md}
                 (called by generate_omp_packages.py for RULES_COMPONENTS)        └─▶ omp plugin install ycc-rules@ycc (base step)
ycc/settings/models.json targets.omp ──┬─▶ generate_omp_agents.py (agentModels → frontmatter @role)
                                       └─▶ validate-model-settings.py ◀── ycc/settings/omp/config.yml (managed source)
ycc/settings/omp/config.yml ──merge_managed_config.py (profile omp-config, YAML)──▶ <agentDir>/config.yml   (--settings, user scope)
ycc/settings/rules/AGENTS.md ──link_rules_file──▶ <agentDir>/AGENTS.md                                       (--rules, user scope)
<agentDir> = `omp config path` (new `omp_install.py agent-dir` subcommand)
```

### Data Models

#### `ycc-rules` OMP package layout

```text
packages/omp/ycc-rules/
  .omp-plugin/plugin.json        {"name": "ycc-rules", "version": <lockstep>, "description": …}
  .claude-plugin/plugin.json     same name/version (OMP reads install version here; ADR 0002 adapter 1)
  package.json                   {"name": "ycc-rules", "version": <lockstep>, "description": …, "private": true}
  rules/ycc-common-agents.md … rules/ycc-web-testing.md      (31 files, flat)
```

- Naming: `ycc-<family>-<stem>.md`, where `<family>` is the directory under `ycc/rules` and `<stem>` the file stem. The `ycc-` prefix avoids collisions with user, project, cursor and builtin rules, and makes overrides predictable.
- Excluded: `hooks.md` (Claude settings content, the Cursor precedent) and `README.md`.
- Frontmatter transform (keys emitted in this order):
  - `description`: copied from the source. Required and non-empty, as on Cursor.
  - `alwaysApply`: emitted only when `true` (`common/security`, `common/git-workflow`). When true, `globs` is dropped.
  - `globs`: the source `paths` list, verbatim, for language and web rules.
  - No other keys: no `paths`, no TTSR (`condition`, `scope`), no `agents`.
- Body transforms:
  - Rewrite relative Markdown links to rule URLs, for example `[performance.md](performance.md)` → `[performance](rule://ycc-web-performance)`.
  - Fail on any `~/.claude`, `CLAUDE_PLUGIN_ROOT` or `/ycc:` token.
- Policy carried over from Cursor: at most 2 `alwaysApply` rules and at most 60 combined body lines. OMP injects them in full into every main-session prompt.

#### `ycc/settings/models.json` → `targets.omp`

```json
"omp": {
  "config": "ycc/settings/omp/config.yml",
  "placeholder": true,
  "main": { "model": "anthropic/claude-fable-5-1", "effort": "medium" },
  "subagent": { "model": "anthropic/claude-opus-5", "effort": "high" },
  "fallback": { "model": "openai/gpt-5.6-sol", "effort": "high" },
  "roles": { "default": "main", "slow": "subagent", "task": "subagent" },
  "agentModels": { "opus": "@slow", "sonnet": "@task", "inherit": null }
}
```

- `main` and `subagent` mirror `targets.claude`: `claude-fable-5-1`/medium, and `opus[1m]` → `anthropic/claude-opus-5`/high, which has a 1M context window in the catalog [V-src].
- `placeholder: true` follows opencode and cursor: provider availability is machine-dependent.
- `roles` maps each OMP role to `main` or `subagent`. The managed selector is `"<model>:<effort>, <fallback.model>:<fallback.effort>"`, for example `slow: "anthropic/claude-opus-5:high, openai/gpt-5.6-sol:high"`.
- `smol`, `plan`, `advisor` and the other roles are deliberately unmanaged:
  - `smol` inherits `default`.
  - `advisor` falls back to the configured `slow`.
  - `plan` is left to OMP's own fallback [INFERENCE: not traced].
  - ycc has no distinct intent for any of them.
- `agentModels` replaces `MODEL_MAP` in `generate_omp_agents.py`, so frontmatter `model:` is the per-agent override. That channel is supported for `.omp-plugin` roots [V-live spike]. `task.agentModelOverrides` is never written: it is user-config-keyed by agent name, and OMP's `/agents` hub writes it.

#### Managed snippet source `ycc/settings/omp/config.yml`

```yaml
# Managed by ystack install.sh --target omp --settings (ycc-owned leaves only).
modelRoles:
  default: 'anthropic/claude-fable-5-1:medium, openai/gpt-5.6-sol:high'
  slow: 'anthropic/claude-opus-5:high, openai/gpt-5.6-sol:high'
  task: 'anthropic/claude-opus-5:high, openai/gpt-5.6-sol:high'
tools:
  approvalMode: write
```

`merge_managed_config.py` `PROFILES["omp-config"]`, with `format: "yaml"`:

| Group         | Path                        | Policy                                                   |
| ------------- | --------------------------- | -------------------------------------------------------- |
| `models`      | `["modelRoles"]`            | `map-entries` (one leaf per role; other roles untouched) |
| `permissions` | `["tools", "approvalMode"]` | `scalar`                                                 |

State key: `<profile>:<resolved config path>`, unchanged from the current scheme. It stores hashes only.

#### `installer-fallback.runtimes.omp`

- `status`: `included`. `components`: `["instructions", "settings"]`. `gates`: `[]`.
- Notes: rules ship natively in `ycc-rules`; the status line is unsupported.
- Evidence: this spec.

#### `ycc-rules.runtimes.omp`

- `status`: `included`. `listed`: `false`.
- `gates`: `["YAN-1178 live acceptance matrix passes on the real ycc tree"]`.
- Notes say globs are advisory on OMP (partial parity).

### API Design

- **Generator.** `RULES_COMPONENTS = frozenset({"rules"})`. `native_packages()` accepts it, emitting it from `generate_omp_rules.write_tree(root / "rules")`. `COMPONENT_REASONS["rules"]` is removed. Any other component set still fails closed.
- **Installer CLI.** `python3 scripts/omp_install.py agent-dir` prints `omp config path`. It exits non-zero if `omp` is missing or older than the floor.
- **Shell.** `omp_valid_steps` → `base,settings,rules`. `omp_intent_steps`: `settings`→`settings`, `rules`→`rules`. `omp_config_groups` → `settings` (one managed-merge group; `config_groups_for_target` filters groups by intent name). `--project` with `settings` or `rules` → error.
- **Merge helper.** `--format yaml` support:
  - Parse with `yaml.safe_load`, refusing non-mapping roots.
  - Merge, then dump with `yaml.safe_dump(sort_keys=False, allow_unicode=True)`.
  - Re-parse and compare with the merged object.
  - Write atomically. No post-write `omp config get` read-back (adopted simplification, plan Decision Log P3): the YAML 1.2 round-trip and mapping check run before the write, OMP ignores invalid enum values at load, and the opt-in live harness (`scripts/test-omp-rules-settings.sh`) covers the real read-back. If saving ownership state fails after the write, restore the original bytes.
  - Refuse symlinked destinations for this profile.
  - `--remove` deletes only leaves whose value still matches the last-applied hash.

### System Integration

#### Files to Create

- `scripts/generate_omp_rules.py`: flattener with `--check`, `--dry-run` and lint. It reuses the frontmatter parsing from `generate_cursor_rules.py`.
- `scripts/test_generate_omp_rules.py`.
- `ycc/settings/omp/config.yml`: managed source.
- `scripts/test-omp-rules-settings.sh`: opt-in live harness, mirroring the `test-omp-native-packages.sh` sandbox (`mktemp -d /tmp/…`, refuses a HOME under the real HOME, `env -i`, null provider).
- `packages/omp/ycc-rules/**`: generated.

#### Files to Modify

- Package model and data: `ycc/settings/packages.json`, `ycc/settings/models.json` (also fix the stale `.sh` name in `$comment`).
- Generators and validators:
  - `scripts/generate_omp_packages.py`, `scripts/generate_omp_agents.py` (read `agentModels`).
  - `scripts/validate_omp_native.py` (`RULES_ROOT_ENTRIES`, `rules_closure_errors`).
  - `scripts/validate-model-settings.py`.
- Installer:
  - `scripts/merge_managed_config.py` (YAML format, `omp-config` profile).
  - `scripts/omp_install.py` (`agent-dir`), `scripts/lib/install/targets/omp.sh`.
  - `scripts/package_install_plan.py`: `CARRIERS["omp"]` gains `rules: base`, `settings: settings`, `instructions: rules`.
  - `install.sh` help: the `--settings` and `--rules` scope lists gain `omp`.
- Tests:
  - Generator and validator: `scripts/test_generate_omp_packages.py`, `scripts/test_generate_omp_agents.py`, `scripts/test_validate_opencode_config.py` (runs the model validator).
  - Installer: `scripts/test_merge_managed_config.py`, `scripts/test_omp_install.py:903-912`, `scripts/test_package_install_plan.py:67-71`, `scripts/test_package_model.py`, `scripts/tests/install/omp.sh:191-194`.
  - Release: `scripts/test-release-bundle.sh` (new lockstep root).
- Validate scope: `scripts/lib/validate-scope.sh`, `scripts/test-validate-scope.sh`.
- Docs and matrices:
  - Rules and runtime contract: `ycc/rules/README.md` (OMP section), ADR 0002 (amendment, adapter 4 delivered, follow-up row), spike §3 rows `:332-334,340-342,347,352`.
  - Capability matrix: `ycc/skills/_shared/references/target-capability-matrix.md` (packaging row `:76` and `INSTALL_PATH:omp`, then `./scripts/sync.sh`).
  - Install guide: `docs/install/omp.md`, with new sections Rules, Global Instructions, Settings And Model Roles, Approvals and Status Line, plus an `OMP Notes` update.

#### Configuration

- Only `--settings` and `--rules` opt-ins.
- No new env vars.
- `YCC_MANAGED_CONFIG_STATE` keeps working.

## UX Considerations

### User Workflows

#### Primary: install

1. `./install.sh install --target omp` installs `ycc@ycc`, `ycc-mcp@ycc` and `ycc-rules@ycc`. The output names the two always-on rules and `ttsr.disabledRules`.
2. Optionally, `./install.sh install --target omp --settings --rules`:
   - It merges `modelRoles.{default,slow,task}` and `tools.approvalMode: write` into `<agentDir>/config.yml`.
   - It prints each leaf as `wrote`, `updated` or `kept (your edit)`.
   - It links `AGENTS.md`.
3. Restart running sessions. Settings reload live; the rules and `AGENTS.md` load at session start.

#### Override and remove

- **Customize a rule.** Copy it to `<agentDir>/rules/ycc-<name>.md` (user) or `<cwd>/.omp/rules/` (project) and edit the copy, or disable it with `ttsr.disabledRules`.
- **Customize a model or approval leaf.** Edit `config.yml` directly. ycc keeps your value on the next update.
- **Uninstall.** `./install.sh remove --target omp --intent settings,rules` removes only unchanged ycc leaves and the owned symlink.

### Error States

| Condition                                          | Message (shape)                                                                                |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Real `AGENTS.md` present                           | `refusing to replace user-authored rules file: <agentDir>/AGENTS.md` plus an `@import` hint    |
| Symlinked `config.yml`                             | `refusing to write through symlinked <path>; add these keys yourself:` followed by the snippet |
| Invalid YAML, non-mapping root or YAML aliases     | `<path> is not a valid OMP config (…); fix it first. ycc made no changes`                      |
| Ownership state write fails after the config write | Restore the original bytes, then fail (no `omp config get` read-back; plan P3)                 |
| User-edited managed leaf                           | `kept modelRoles.slow (changed locally; --force to replace)`                                   |
| `--project` with settings or rules                 | `omp settings/instructions are user-scope; edit <root>/.omp/config.yml by hand`                |

### Performance UX

- The two `alwaysApply` bodies (47 lines) and 29 one-line rulebook entries go into every main-session prompt.
- Language bodies load only on `rule://` reads.

## Security Considerations

### Critical — Hard Stops

- Never write `tools.approvalMode: yolo`, `--auto-approve`, `bash.patterns` allows, or per-tool `allow`.
- Never write secrets or provider credentials. The snippet holds model selectors and one enum.
- Never write project config. Project files are committed and shared, and OMP applies them without a trust prompt [V-src].
- Never write through a symlink. Never leave invalid YAML: OMP moves it to `.broken-*` and refuses to start.
- The harness never touches the real `~/.omp`. It uses `/tmp` sandboxes and `env -i`.

### Warnings — Must Address

- **`write` mode does not gate subagents.** They are forced to `yolo` [V-src]. The docs must say that ycc's approval default covers main-session `exec` prompts only.
- **A project config can weaken the user value** [V-live]. Document `--approval-mode` (runtime) as the only per-session pin above project config.
- **Headless `omp -p` with `write` mode.** A shell call that needs a prompt fails closed with no UI [V-src]. Document `--approval-mode yolo` for trusted automation. This is the reason approvals are opt-in.

### Advisories

- Rules are prompt text, not code. `ycc-rules` adds no in-process surface, and the YAN-1174 guard is unchanged.
- A same-name rule shadows silently, because OMP does not surface discovery warnings [V-src `rulebook-matching-pipeline.md:353`]. The `ycc-` prefix keeps accidental shadowing to deliberate overrides.

## Risk Assessment

| Risk                                                            | Likelihood | Impact | Mitigation                                                                                                                       |
| --------------------------------------------------------------- | ---------- | ------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Users expect Cursor-style glob auto-attach                      | High       | Medium | Partial verdict in the package notes and docs. Descriptions already start with "When …" triggers. TTSR conversion is a follow-up |
| Comments in `config.yml` are lost on ycc rewrite                | Medium     | Low    | One-time backup plus a warning. OMP's own `config set` drops them too [V-live]. Write only when a leaf changes                   |
| Provider-specific defaults are wrong on a machine               | Medium     | Low    | `placeholder: true`, an ordered fallback, opt-in `--settings`, and OMP's no-crash fallback [V-live]                              |
| `omp config set modelRoles` (record replace) erases ycc leaves  | Medium     | Low    | Missing leaves are re-added on the next `--settings` run (helper rule); roles the user set are kept. Documented                  |
| `claude-plugins` vs `agents` tie at priority 70                 | Low        | Low    | The `ycc-` prefix makes a collision unlikely. Registration order is not verified [INFERENCE]                                     |
| Upstream renames roles or changes globs semantics               | Low        | Medium | The pinned role list is in the validator with an upstream citation. Live harness L1/L5                                           |
| `apply_skills_text_transforms`-style body rewrites miss a token | Low        | Low    | Validator forbid-list and link-resolution check                                                                                  |

## Decisions

| #   | Decision                                    | Options                                                                                                                      | Recommended                                                                                                                                                                                                                                                       |
| --- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Rules naming                                | (a) `<family>-<stem>`; (b) **`ycc-<family>-<stem>`**; (c) keep nesting                                                       | **(b)**: OMP is flat [V-src] [V-live]; the prefix keeps the namespace and makes overrides predictable                                                                                                                                                             |
| D2  | Glob-scoped rules                           | (a) **rulebook entries (`description` + advisory `globs`)**; (b) convert to TTSR `condition: "*.go"`                         | **(a)**: TTSR injects mid-stream on every matching edit. It changes behavior and is not Cursor parity either. Revisit in a follow-up                                                                                                                              |
| D3  | `ycc-rules` OMP row                         | (a) **included, unlisted, installed by default**; (b) `opt_in`                                                               | **(a)**: `opt_in` rows are uninstallable through the planner (`package_install_plan.py:132`). `--package ycc,ycc-mcp` deselects it                                                                                                                                |
| D4  | Settings delivery                           | (a) **opt-in hash-owned merge into user `config.yml`**; (b) overlay via `PI_CONFIG_FILES`/`--config`; (c) print-only snippet | **(a)**: (b) outranks project and user config and hard-fails on a missing file [V-live], which violates both ACs. (c) leaves nothing to keep consistent. Keep the helper's existing decision table unchanged (a missing leaf is re-added; an edited leaf is kept) |
| D5  | Merge granularity                           | (a) **per-role `map-entries` + `scalar` approval**; (b) whole `modelRoles` object                                            | **(a)**: the user's own roles (`smol`, custom) are never touched                                                                                                                                                                                                  |
| D6  | Per-agent overrides                         | (a) **agent frontmatter `@role` via `models.json` `agentModels`**; (b) `task.agentModelOverrides`                            | **(a)**: supported natively for `.omp-plugin` roots; (b) writes user config keyed by name and collides with `/agents`                                                                                                                                             |
| D7  | Approval default                            | (a) **`write`, opt-in via `--settings`**; (b) `always-ask`; (c) manage nothing                                               | **(a)**: the secure middle (exec prompts), matching Codex `on-request` + `workspace-write`. (b) breaks reads-with-files UX; (c) leaves OMP's `yolo`. **Main to confirm** if a lighter touch is preferred                                                          |
| D8  | Global instructions                         | (a) **symlink `<agentDir>/AGENTS.md` via `--rules`**; (b) ship as an `alwaysApply` rule                                      | **(a)**: same channel as Claude, Codex and opencode. Keeps the 2-rule `alwaysApply` budget; refuses real files                                                                                                                                                    |
| D9  | Status line                                 | (a) **unsupported**; (b) extension port; (c) ship `statusLine.*` preset                                                      | **(a)**: no command renderer. (b) needs the YAN-1174 guard lifted. (c) is user taste. The built-in status line already shows path and git                                                                                                                         |
| D10 | Project scope for settings and instructions | (a) **reject**; (b) write `.omp/config.yml`                                                                                  | **(a)**: project files are shared and committed; provider pins do not belong there                                                                                                                                                                                |

## Out of Scope (follow-up issues)

- TTSR glob-triggered variants of language rules (D2b), behind evidence that they help.
- A status-line extension port (D9b). It needs a scoped lift of the YAN-1174 code-surface guard.
- `secrets.enabled` and `secrets.yml` defaults (security hardening; orthogonal to approvals).
- `RULES`, `SETTINGS` and `MODELS` capability-matrix rows. They need a matrix parser and validator change.
- Coexistence with project `.cursor/rules`, `.agents/rules` and Claude opt-in sources (YAN-1176).
- Catalog listing of `ycc-rules` (YAN-1180) and the real-tree live matrix (YAN-1178).
- `smol`, `plan` and `advisor` intent in `models.json`, once ycc defines one.

## Task Breakdown Preview

### Phase 1: Rules package (AC: generated context validates)

| Task                                                                                                                  | Files                                                           | Tests                                                                                                                                                                                                                                                       |
| --------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Flattener: naming, frontmatter transform, link rewrite, forbid-list, `alwaysApply` budget                             | `scripts/generate_omp_rules.py`                                 | T-G1: 31 files and exact names; T-G2: `paths`→`globs`, `alwaysApply` only when true, globs dropped; T-G3: hooks and README skipped; T-G4: link → `rule://ycc-web-performance`; T-G5: budget and forbid-list failures (`scripts/test_generate_omp_rules.py`) |
| Generator wiring: `RULES_COMPONENTS`, `ycc-rules` root and manifests, prune                                           | `scripts/generate_omp_packages.py`, `packages/omp/ycc-rules/**` | Update `test_generate_omp_packages.py:193-203` (rules row emits); T-G6: other mixed sets still fail closed                                                                                                                                                  |
| Validator: `RULES_ROOT_ENTRIES`, `rules_closure_errors` (flat, `ycc-` names, allowed keys, no TTSR, inventory parity) | `scripts/validate_omp_native.py`                                | Golden failures in `test_generate_omp_packages.py`                                                                                                                                                                                                          |
| Model row flip                                                                                                        | `ycc/settings/packages.json`                                    | `test_package_model.py`, `test_package_install_plan.py:67-71`, `test_omp_install.py:903-912`, `test-release-bundle.sh`                                                                                                                                      |

### Phase 2: Model policy (AC: full runtime-valid ids and roles)

| Task                                                                                                                                                                                                                | Files                                                               | Tests                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `targets.omp` data; agent generator reads `agentModels`                                                                                                                                                             | `ycc/settings/models.json`, `scripts/generate_omp_agents.py`        | `test_generate_omp_agents.py` (mapping from data; unknown alias rejected)                          |
| OMP validator: role names ∈ pinned built-ins, selector grammar `provider/model[:thinking]`, thinking enum, `@role` closure, `pi/` and bare ids rejected, snippet == models.json, snippet keys ∈ pinned OMP key list | `scripts/validate-model-settings.py`, `ycc/settings/omp/config.yml` | T-M1–M7 via `test_validate_opencode_config.py` runner (or a new `test_validate_model_settings.py`) |

### Phase 3: Installer (AC: user edits survive; project/user precedence)

| Task                                                                                                                                  | Files                                                                                                           | Tests                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| YAML format in merge helper (round-trip check, symlink refusal, `config.yaml` pick, backup, restore on failure), `omp-config` profile | `scripts/merge_managed_config.py`                                                                               | T-S1–S10 in `test_merge_managed_config.py`: missing → write; unchanged → update; edited → kept; no state and differ → kept; `--force`; `--remove` owned only; unknown keys preserved; symlink refused; invalid YAML untouched; other roles untouched                                                                                                                                                                               |
| `agent-dir`, settings and rules steps, project rejection, carriers                                                                    | `scripts/omp_install.py`, `scripts/lib/install/targets/omp.sh`, `scripts/package_install_plan.py`, `install.sh` | T-I1: fake omp `config path` honored; T-I2: real `AGENTS.md` refused; T-I3: `--project` + settings/rules rejected (no project write); update `scripts/tests/install/omp.sh:191-194`                                                                                                                                                                                                                                                |
| Opt-in live harness                                                                                                                   | `scripts/test-omp-rules-settings.sh`, validate-scope wiring                                                     | L1: package rules in `get_state` (always plus rulebook with globs); L2: `ttsr.disabledRules`; L3: user rule shadows; L4: project rule shadows at cwd only; L5: `omp models find` lists every managed selector (dummy keys); L6: user edit survives re-run of `--settings`; L7: project `.omp/config.yml` `modelRoles` and `approvalMode` beat managed user values (`get_state.model`, `config get`); L8: `AGENTS.md` symlink loads |

### Phase 4: Docs

- ADR 0002 amendment: adapter 4 delivered, installer-fallback, settings and status-line rows, YAN-1175 row.
- Spike §3 rows.
- Capability matrix packaging row and `INSTALL_PATH:omp`, then `./scripts/sync.sh`.
- `docs/install/omp.md` sections; `ycc/rules/README.md` OMP section.
- Then `./scripts/validate.sh`.

## Research References

- Live probe dir `/tmp/omp-yan1175.6n5WIi`: fixture plugin `plugin/`, `models.yml` null provider, and the RPC `get_state` probe above.
- Commands:
  - `omp --mode rpc --no-session --no-title --model spike-null/null-model [--plugin-dir …] [--config …]`
  - `omp config get|set|list|path [--json]`, with `PI_CONFIG_FILES`
  - `omp models find <id> --kind all --json`
- Upstream source: `/tmp/omp-src-1175` (worktree of tag `v18.12.5`).
- Repo:
  - ADR and spike: `docs/internal/adr/0002-omp-runtime-contract.md`, `docs/internal/spikes/omp-runtime-contract.md` §2.6–2.10, §3.
  - Generators and validators: `scripts/generate_cursor_rules.py`, `scripts/generate_omp_packages.py`, `scripts/generate_omp_agents.py`, `scripts/validate_omp_native.py`, `scripts/validate-model-settings.py`.
  - Installer: `scripts/merge_managed_config.py`, `scripts/omp_install.py`, `scripts/lib/install/{core.sh,targets/omp.sh}`.
  - Prior spec: `docs/research/yan-1174-omp-hooks-extension/feature-spec.md`.
