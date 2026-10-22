# Business analysis: OMP coexistence (YAN-1176) and linear-personal (YAN-1291)

## Executive Summary

Only `~/.agents/skills` duplicates ycc on OMP by default: 41 aliases, +17 % prompt. Claude plugin installs never duplicate. Opt-in imports add more. The business rules are: native wins, never touch another target's files, hide only ycc-owned copies, keep it reversible, and keep YAN-1291 OMP-only.

## Who is affected

| Persona                     | Install state                                                                                                                                                               | Outcome on OMP today (live, 18.12.5)                                                                                                                                                         |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1, multi-tool user         | `install.sh install --target all`, or OMP plus Codex/Cursor/opencode with skills consolidated into `~/.agents/skills` (the default recommendation in `resolve_skills_home`) | **41 `agents/<skill>` duplicates** and 41 collision warnings. Prompt grows 17 %. Two copies of `plan`, `clean`, … are offered to the model (probe B)                                         |
| P2, Claude plugin user      | `ycc@ycc` through `claude plugin`, then OMP                                                                                                                                 | No duplicates, even with `enabledProviders: ["claude"]`, because the OMP registry wins per plugin id (probes L and W)                                                                        |
| P3, Claude slice user       | `--target claude --intent skills,agents`, plus OMP, plus `enabledProviders` including `claude`                                                                              | Claude copies take the bare names and ycc becomes `ycc/<skill>`, which inverts precedence (probe C). `~/.claude/agents` never loads                                                          |
| P4, opt-in importer         | `enabledProviders: ["*"]`                                                                                                                                                   | Up to 218 skill entries, with `codex/` and `opencode/` aliases, plus 49 bare opencode commands. MCP stays single-copy, but the Claude `~/.claude.json` servers replace `ycc-mcp:*` (probe C) |
| P5, project installer       | `install --target omp --project` in a repo                                                                                                                                  | User and project copies collapse to one. Uninstalling leaves untracked omp residue in `.omp/plugins/` (probes E–G)                                                                           |
| P6, profile user            | `OMP_PROFILE=work`                                                                                                                                                          | Plugins are per profile, but `~/.agents/skills` is shared, so P1's duplicates appear in every profile where ycc is installed (probe J)                                                       |
| P7, Linear two-account user | Relies on `linear-personal` for a second Linear account                                                                                                                     | On OMP, `ycc-mcp:linear-personal` is shadowed and never connects. Both names would share one OAuth row anyway (same URL)                                                                     |

## User Stories

- **US1.** As P1, I want each ycc skill offered once in OMP, from the OMP package, so the model is not
  choosing between drifting copies and I don't pay prompt tokens twice.
- **US2.** As P1, P3 or P4, when the installer sees an overlap I want one warning that names the exact
  source and the exact command or setting that removes it.
- **US3.** As any user, I want removing or disabling ycc on OMP to return OMP to the state it had before
  ycc touched it: the other tools' copies are visible again and no ycc-written keys or files are left.
- **US4.** As a user opening an untrusted repository, I want a documented, tested way to run OMP with
  ycc loaded and none of the repository's hooks, extensions or MCP servers executing.
- **US5.** As P7, I want `ycc-mcp:linear` and `ycc-mcp:linear-personal` both to load on OMP with separate
  logins, without changing Claude, Codex or Cursor.

## Business Rules

- **BR1. Native beats fallback.** When the OMP package is installed, it is the ycc source on OMP. Other
  targets' copies are never the winner by ycc's own action.
- **BR2. Never edit another target's files from the OMP target.** `~/.agents/skills` also feeds Codex,
  Cursor and opencode (consolidation). Deleting it would break them. ycc may change OMP's own config
  only, and only for keys it owns by hash.
- **BR3. Consent for config writes.** YAN-1175 D4 made OMP config writes opt-in. A dedupe write needs
  either explicit consent (a TTY prompt or a flag) or must be skipped with a warning.
- **BR4. Deterministic precedence.** The order is documented and proven: project native > user native >
  OMP plugin (project > user) > foreign imports by OMP provider priority. Identical copies collapse;
  differing copies are aliased.
- **BR5. No parity claim without a test.** Each coexistence statement in the docs or the matrix maps to
  a live probe or a hermetic test.
- **BR6. Reversible.** Every write is recorded (hash ownership, ledger) and taken back by
  `remove --target omp`.
- **BR7. The YAN-1291 change is OMP-only.** `mcp-configs/mcp.json` and the Claude, Codex and Cursor
  packages stay byte-identical.

## Edge cases

- A user-authored `~/.agents/skills/<name>` that collides with a ycc skill must not be hidden. Hide only
  the names the agents target recorded as ycc-owned (`installed-units.json`).
- After ycc on OMP is disabled or uninstalled, the agents copies must come back under their bare names.
  An `agents/<name>` ignore entry matches only the alias, which exists only on a collision (probe M′).
- A project `.omp/config.yml` that sets its own `skills.ignoredSkills` replaces the user list, because
  arrays replace across layers. The duplicates then reappear inside that project. Document this; do not
  write project config (YAN-1175 D10).
- Two profiles: dedupe entries live in each profile's `config.yml`, so run the installer per profile.
- `PI_CODING_AGENT_DIR` moves `config.yml` but not the plugins dir. Entries still follow `omp config path`.
- `--target all` runs `agents` before `omp` (`ALL_TARGETS`), so overlap detection must run after the
  agents step in the same run. It does, inside the omp base step.
- A legacy `~/.agents/skills` from before the ledger has no ownership record. Warn only; never hide.

## Success criteria (acceptance mapping)

| AC (YAN-1176 / YAN-1291)                                                                | Evidence                                                                                                                       |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| A mixed-runtime fixture shows each component loaded once, with deterministic precedence | Live harness `test-omp-coexistence.sh` cases C1–C6 plus hermetic `test_omp_install.py`                                         |
| Actionable warnings                                                                     | Installer lines naming the source and the fix (hermetic tests assert the exact text)                                           |
| Untrusted project resources do not execute                                              | ycc ships no OMP code (existing guard). Harness case C7: the hostile fixture runs nothing under the documented safe invocation |
| Uninstall or disable restores prior state                                               | Harness C8 plus hermetic remove tests: config keys taken back, project residue removed, other tools' copies visible again      |
| YAN-1291: both servers load, linear not shadowed, OAuth tokens separate                 | `test-omp-native-packages.sh` mcp-listed with an empty shadowed set, plus a credential-id check. Generator and validator tests |
| No regression for Claude, Codex or Cursor                                               | `mcp-configs/mcp.json` unchanged. `./scripts/validate.sh` (Claude, Codex and Cursor parity and byte checks)                    |
