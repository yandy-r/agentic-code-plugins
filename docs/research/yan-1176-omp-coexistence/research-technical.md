# Technical design: OMP coexistence and linear-personal

## Executive Summary

Add a default-on `dedupe` step that merges ledger-owned `agents/`, `codex/` and `opencode/` alias names into the user `config.yml` `skills.ignoredSkills`, using the existing hash-owned `list-union` merge. Add one `coexistence` helper for warnings, and an OMP-only generator transform that gives `linear-personal` a distinct `?ycc-server=` URL.

## Current state (repo)

| Surface                                                                                                                                | Where it lands                                                                                                                                                                                                                                  | OMP reads it?                                                         | Duplicate today                                                              |
| -------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| OMP `ycc` package (skills, agents, `commands/`)                                                                                        | `~/.omp/plugins/cache/plugins/ycc___ycc___<v>/` through `omp plugin install` (`scripts/omp_install.py:521-690`)                                                                                                                                 | yes, provider `claude-plugins` (OMP registry origin)                  | –                                                                            |
| `agents` target skills                                                                                                                 | `~/.agents/skills/<name>`, copied flat and recorded in `~/.config/ycc/installed-units.json` (`scripts/install_slices.py:58-85,136-160`)                                                                                                         | **yes, by default** (provider `agents`, priority 70)                  | **41 aliases** `agents/<name>` + 8 identical copies dropped (probe B)        |
| Codex, Cursor and opencode skills consolidated into `~/.agents/skills` (`resolve_skills_home`, `scripts/lib/install/steps.sh:369-429`) | same dir                                                                                                                                                                                                                                        | yes                                                                   | same as above                                                                |
| Codex skills                                                                                                                           | `~/.codex/skills/<name>`                                                                                                                                                                                                                        | only with `enabledProviders` ∋ codex                                  | `codex/<name>` aliases                                                       |
| opencode skills and commands                                                                                                           | `~/.config/opencode/{skills,commands}`                                                                                                                                                                                                          | only with opt-in                                                      | `opencode/<name>` skill aliases and **bare** `<name>` commands               |
| Cursor skills, agents, commands                                                                                                        | `~/.cursor/*`                                                                                                                                                                                                                                   | skills never; MCP only with opt-in                                    | MCP equivalence-shadowed                                                     |
| Claude slices                                                                                                                          | `~/.claude/{skills,agents}`                                                                                                                                                                                                                     | skills only with opt-in, at **priority 80 > plugin 70**; agents never | Claude copy takes the bare name; ycc becomes `ycc/<name>`                    |
| Claude marketplace `ycc@ycc`                                                                                                           | `~/.claude/plugins/…`                                                                                                                                                                                                                           | **no**: the OMP registry is authoritative per id (`helpers.ts:1355`)  | none                                                                         |
| Claude, Codex and Cursor MCP                                                                                                           | `~/.claude.json`, `~/.codex/config.toml`, `~/.cursor/mcp.json`                                                                                                                                                                                  | only with opt-in                                                      | Claude names win, and `ycc-mcp:*` is shadowed (still one copy)               |
| Global instructions                                                                                                                    | `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, opencode `AGENTS.md`, `<agentDir>/AGENTS.md` (`--rules`)                                                                                                                                           | one context file wins (native, else Claude)                           | none                                                                         |
| Rules                                                                                                                                  | `ycc-rules` package; Cursor rules are not written to `~/.cursor/rules`                                                                                                                                                                          | yes                                                                   | none                                                                         |
| Hooks                                                                                                                                  | ycc ships none to OMP (`validate_omp_native.py:220` `hook_surface_errors`). Claude hooks are `*.sh` with `settings.json` activation                                                                                                             | OMP reads only `hooks/{pre,post}/*.ts`                                | none                                                                         |
| Existing detection                                                                                                                     | `omp_install.agents_overlap` / `warn_agents_overlap` (`omp_install.py:167-187`) counts `~/.agents/skills` dirs named like a package skill. Called by install, dry-run and migrate. `omp_reads_agents_skills` returns 1 (`targets/omp.sh:47-49`) | –                                                                     | warn only; no fix; Claude, Codex and opencode opt-in sources are not counted |

## Architecture Design

```text
install.sh install --target omp
  └─ omp.sh sync_omp_target
       ├─ base    → omp_install.py install           (unchanged)
       ├─ dedupe  → omp_install.py coexistence --emit <tmp.yml>   (NEW)
       │            └─ merge_settings_config omp-config <tmp.yml> <agentDir>/config.yml dedupe
       ├─ settings / rules                          (unchanged, opt-in)
       └─ omp_install.py coexistence --warn          (NEW; replaces warn_agents_overlap)
install.sh remove --target omp --only base|dedupe
  └─ merge_settings_config omp-config … dedupe --remove   (takes back owned list items)
install.sh install --target agents
  └─ agents_duplicate_hint → omp_install.py coexistence --warn --if-installed   (NEW)
generate_omp_packages.py
  └─ mcp_payloads → omp_mcp_bytes(source)   (NEW: disambiguate equivalent connections)
```

### Dedupe mechanism: hash-owned `skills.ignoredSkills` aliases

- OMP turns a differing same-name skill into `<namespace>/<name>`. `skills.ignoredSkills` globs match
  the raw **and** final names (`docs/skills.md:135`).
  - An entry `agents/<name>` therefore hides only the alias, and only while the alias exists.
  - When ycc on OMP is disabled or uninstalled, the `~/.agents` copy keeps its bare name and loads again.
    It self-heals, as verified live in probe M′.
- **Entries.** For each (dir, namespace) in `(~/.agents/skills, agents)`, `(~/.codex/skills, codex)` and
  `(~/.config/opencode/skills, opencode)`, take
  `ledger_owned(dir) ∩ omp_package_skill_names(selected packages)` and emit `<namespace>/<name>`.
  - `ledger_owned(dir)` is `install_slices.load_state(install_slices.state_path())[str(dir)]`, minus
    `ycc-shared`.
  - Entries are sorted and deduplicated.
- **Namespaces** follow `skillNamespace` (`skills.ts:74-93`):
  - the dir owning `skills/` when it is not dotted, otherwise the provider id;
  - `~/.agents` → `agents`, `~/.codex` → `codex`, `~/.config/opencode` → `opencode`.
- **Excluded.** Entries are never added for unowned dirs (user-authored or pre-ledger), for Claude
  (`~/.claude/skills` holds the bare name at priority 80, and ignoring `ycc/<name>` would hide the native
  package), or for opencode commands (`disabledExtensions: slash-command:<n>` would also hide the user's
  own `<agentDir>/commands/<n>.md`).
- **Storage.**
  - New group `dedupe` in the `omp-config` profile (`merge_managed_config.py:200-210`):
    `{"path": ["skills", "ignoredSkills"], "policy": "list-union"}`.
  - The source is a temp YAML `skills: {ignoredSkills: [...]}` that `omp_install.py` writes. The
    destination is `omp_config_dest "$(omp_agent_dir)"`.
  - `list-union` keeps user items and records appended item hashes (`ADDED_ITEMS_KEY`). `--remove`
    takes back only owned items and deletes the key or file when this tool emptied it
    (`plan_list_removals`, `:1052-1097`).
- **Empty set.** When there is no overlap, nothing is written and `config.yml` is not created.

### Warnings (one helper: `omp_install.py coexistence`)

Inputs:

- the selected packages' skill names;
- the ledger;
- the dirs on disk;
- `omp config get enabledProviders --json` (user-level effective value, run from `$HOME`).

Each warning line below is final text and is tested.

| Id  | Condition                                                                                                           | Line                                                                                                                                                                                                                                   |
| --- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| W1  | Owned overlap hidden (the dedupe step ran)                                                                          | `[ok] OMP: hid N ycc duplicate skills (agents/…, codex/…) via skills.ignoredSkills in <config>; ./install.sh remove --target omp --only dedupe restores them`                                                                          |
| W2  | Owned overlap and the dedupe step skipped (`--only base`, migrate)                                                  | `[!!] OMP also loads N ycc skills from ~/.agents/skills as agents/<name>; run ./install.sh install --target omp --only dedupe to hide them in OMP`                                                                                     |
| W3  | Unowned dir in a scanned dir with a ycc skill name                                                                  | `[!!] ~/.agents/skills/<a>[, …] share ycc skill names but were not installed by ycc; OMP lists them as agents/<name> (left as is)`                                                                                                     |
| W4  | `enabledProviders` ∋ `claude`, `*` or `all`, and owned `~/.claude/skills` overlap                                   | `[!!] enabledProviders includes claude: N ycc skills in ~/.claude/skills outrank the OMP package (it shows as ycc/<name>); remove them with ./install.sh remove --target claude --intent skills, or drop claude from enabledProviders` |
| W5  | Agents target run while OMP ycc is recorded installed (`omp-native-install.json`) and the overlap is not yet hidden | `[!!] OMP also loads these skills; run ./install.sh install --target omp --only dedupe to hide the ~/.agents copies in OMP`                                                                                                            |

`omp skill list` stderr prints OMP's own `name collision` lines. The docs name it as the verification
command.

### YAN-1291: OMP-only connection disambiguation in the generator

- **Function.** `omp_mcp_bytes(source: bytes) -> bytes` in `generate_omp_packages.py`:
  1. Parse `mcpServers` in order. Key each server with the same tuple OMP uses (mirroring
     `isSameMCPConnection` and `omp_native_smoke.connection`).
  2. For a later **http/sse** server equivalent to an earlier one, append the query parameter
     `ycc-server=<name>` to its `url`, using `?` or `&` with `urllib.parse`.
  3. A later **stdio** duplicate raises `ValueError("<name>: same stdio connection as <first>; OMP would shadow it")`.
  4. Re-serialize with `json.dumps(indent=2, ensure_ascii=False) + "\n"`.
  5. With no equivalence, return the source bytes unchanged.
- **Wiring.** `mcp_payloads` writes `omp_mcp_bytes(mcp_source())`.
- **Validator.** `mcp_closure_errors` compares the package bytes to `omp_mcp_bytes(source)` instead of
  the raw source. The secret audit runs on the output too.
- **Effect.** Only `packages/omp/ycc-mcp/.mcp.json` changes:
  `"linear-personal": {"type": "http", "url": "https://mcp.linear.app/mcp?ycc-server=linear-personal"}`.
  `mcp-configs/mcp.json` and the Claude, Codex and Cursor packages stay byte-identical, so their
  generators and parity checks are untouched.
- **Proof (live).**
  - The variant survives dedupe and nothing is shadowed.
  - Credential ids differ: `mcp_oauth:profile:default:https://mcp.linear.app/mcp` vs
    `…?ycc-server=linear-personal`.
  - Linear returns the same 401 challenge and protected-resource doc (`resource` = canonical `/mcp`).
- **Harness.**
  - `test-omp-native-packages.sh` `mcp-listed`: `shadowed` becomes empty, because `connection()` is
    computed on the shipped (transformed) file.
  - The probe also reports `credentialIds` through `@oh-my-pi/pi-coding-agent/mcp/oauth-flow`.
    `check_mcp_listed` asserts that distinct http URLs give distinct ids.

## Data Models

```yaml
# Generated temp source (never committed): input to merge_managed_config --groups dedupe
skills:
  ignoredSkills:
    - agents/backport
    - agents/blueprint
    # … sorted; one per owned overlapping ~/.agents|~/.codex|~/.config/opencode skill
```

```python
# merge_managed_config.py PROFILES["omp-config"]["groups"]
"dedupe": [{"path": ["skills", "ignoredSkills"], "policy": "list-union"}],
```

```jsonc
// packages/omp/ycc-mcp/.mcp.json (generated) — only change vs mcp-configs/mcp.json
"linear-personal": { "type": "http", "url": "https://mcp.linear.app/mcp?ycc-server=linear-personal" }
```

## Step contract (`scripts/lib/install/targets/omp.sh`)

- `omp_valid_steps` becomes `base,dedupe,settings,rules`.
- `omp_intent_steps base|plugins` becomes `base dedupe`.
- `omp_project_steps` becomes `base dedupe`. Dedupe writes the user `config.yml` only; the
  `~/.agents` duplicate is user-level, and a project install sees it too.
- `step_enabled dedupe` defaults on, like `base` (`steps.sh:44`). `--only base` skips it.
- **Remove.** When `base` or `dedupe` is selected, `merge_settings_config … dedupe --remove` runs
  before the package uninstall, so `remove --target omp --only base` restores the prior state.
- **Dry-run.** The emitted entries and the planned merge are printed. Nothing is written, and
  `omp config path` is not run (existing rule).

## Precedence contract (documented and proven)

1. Project native (`<cwd>/.omp/skills|commands|rules|agents`, `.omp/mcp.json`).
2. User native (`<agentDir>/…`, user `mcp.json`, with `disabledServers` above every source).
3. OMP plugin: project install > user install. The OMP registry replaces a Claude-registry entry with
   the same plugin id.
4. Claude user imports (opt-in, priority 80). Skills and MCP outrank the plugin, so W4 applies.
5. `~/.agents/skills` (always on, priority 70, below the plugin by registration order): aliased, and
   hidden by dedupe.
6. Codex 70 (opt-in), opencode 55 (opt-in) and Cursor 50 (MCP only, opt-in): aliased or shadowed.
7. Built-in and bundled.

Within MCP, equivalent connections collapse onto the highest-priority one. Within skills, identical
content collapses silently.

## Files

- **Create:** `scripts/test-omp-coexistence.sh`.
- **Modify:**
  - `scripts/omp_install.py`, `scripts/test_omp_install.py`, `scripts/tests/install/fake_omp.py`
    (`config get`);
  - `scripts/merge_managed_config.py`, `scripts/test_merge_managed_config.py`;
  - `scripts/generate_omp_packages.py`, `scripts/validate_omp_native.py`,
    `scripts/test_generate_omp_packages.py`;
  - `scripts/omp_native_smoke.py`, `scripts/test-omp-native-packages.sh`;
  - `scripts/lib/install/targets/omp.sh`, `scripts/lib/install/targets/agents.sh`,
    `scripts/lib/install/steps.sh`, `install.sh` (help);
  - `scripts/tests/install/omp.sh`, `scripts/tests/install/agents.sh`;
  - `scripts/lib/validate-scope.sh`, `scripts/test-validate-scope.sh`;
  - docs: `docs/install/omp.md`, ADR 0002, spike, `ycc/skills/_shared/references/target-capability-matrix.md`.
- **Regenerated:** `packages/omp/ycc-mcp/.mcp.json`, plus the matrix copies, through `./scripts/sync.sh`.
