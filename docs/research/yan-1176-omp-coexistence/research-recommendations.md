# Recommendations

## Executive Summary

Ship OMP-side alias dedupe (owned only, reversible), one coexistence warning helper, the YAN-1291 generator transform, a mixed-runtime live harness (C1-C8), project-residue cleanup on remove, and a docs section with the precedence table and the untrusted-repo invocation.

## Implementation Recommendations

1. **Dedupe on the OMP side, by alias, with owned entries only.** Add the `dedupe` step, default-on
   with `base`. It merges `skills.ignoredSkills: [agents/<n>, codex/<n>, opencode/<n>]` for
   ledger-owned overlaps into the user `config.yml`. It is hash-owned through `list-union`, and
   `remove --only base|dedupe` takes it back.
   - **Why:** it is the only lever that hides exactly ycc's duplicate and nothing else. It needs no
     change to other targets' files, and it self-heals when the native package goes away (live M′, V).
2. **One coexistence helper for all warnings.** `omp_install.py coexistence` replaces
   `warn_agents_overlap`. It covers the W1–W5 lines. The agents target calls it when OMP ycc is
   recorded.
3. **YAN-1291: ship the fix, OMP-only.** Add a generator transform that appends `?ycc-server=<name>` to
   later equivalent HTTP servers in `packages/omp/ycc-mcp/.mcp.json`. The `mcp-configs/mcp.json` source
   is unchanged, so Claude, Codex and Cursor do not regress.
4. **Mixed-runtime live harness** `scripts/test-omp-coexistence.sh` (opt-in), reusing the
   native-packages sandbox:
   - C1 baseline;
   - C2 the real `install.sh --target agents` then `--target omp` (once-each counts, empty
     `omp skill list` stderr);
   - C3 the Claude plugin registry (no duplicate);
   - C4 `enabledProviders: ["*"]` precedence table (skills, MCP and context file once; W4 printed);
   - C5 project install, project native override and precedence;
   - C6 profile isolation;
   - C7 the hostile project under the documented safe invocation (no marker files);
   - C8 remove / disable restores the pre-install snapshot (config.yml, ledger, project residue).
5. **Project-scope residue.** On `remove --project`, delete the omp-created
   `.omp/plugins/{installed_plugins.json,omp-plugins.lock.json,node_modules/}` only when they are empty
   (`{"plugins": {}}`, an empty dir), then `.omp/plugins` and `.omp` if empty. This brings the project
   back to its pre-install state (live G).
6. **Docs.** Add `docs/install/omp.md` § "Coexistence with other runtimes": the precedence table, what
   loads once, the dedupe step, `enabledProviders` effects, profiles and `PI_CODING_AGENT_DIR`, reload,
   and "Untrusted projects". Amend ADR 0002 (Consequences, YAN-1176 row), spike §1.8 and §5 (close the
   open dedupe question), and the matrix `SKILLS:omp` / `MCP:omp` / `INSTALL_PATH:omp` (remove the
   linear-personal gap).

## Improvement ideas (out of scope)

- Upstream OMP: surface `skillWarnings` in the TUI (today only `omp skill list` prints them), and add
  a project trust gate. File upstream issues; no ycc work.
- A `ycc doctor --target omp` command could print the precedence winners per component using the
  harness probe. Defer: it needs an internal-module import, which is fragile across OMP versions.
- Claude-slice dedupe under `enabledProviders: claude` (ignore `claude/<n>`?). The Claude copy holds the
  **bare** name at priority 80, so only removing the Claude slice or dropping the opt-in fixes it. W4
  covers it.

## Risk Assessment

| Risk                                                                                                   | Likelihood     | Impact | Mitigation                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------ | -------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OMP changes the alias namespace rule (`skillNamespace`)                                                | Low            | Medium | The live harness asserts the alias names. Entries are derived from the provider id, and C2 fails loudly                                                                       |
| Default-on dedupe writes `config.yml` on a plain `install` (a new behavior after YAN-1175 D4's opt-in) | –              | Low    | Hash-owned and reversible; dry-run prints it; `--only base` skips it. **Main to confirm (D3)**                                                                                |
| A project `.omp/config.yml` replaces `skills.ignoredSkills`                                            | Medium         | Low    | Documented, with the fix. The installer never writes project config                                                                                                           |
| Stale owned entries remain after an agents skill is removed                                            | Low            | None   | An alias with no copy behind it matches nothing. `remove` takes them all back                                                                                                 |
| A Linear server change rejects unknown query params                                                    | Low            | Medium | The live harness sends no network traffic. Document a re-check. Fallback: drop the transform and restore the won't-fix note (one function)                                    |
| Claude/Codex/Cursor regression from YAN-1291                                                           | None by design | –      | The source bytes are unchanged; `validate.sh` byte and parity checks                                                                                                          |
| Live OAuth with two accounts is not exercised                                                          | –              | Medium | Proven at the credential-key level (`mcpOAuthCredentialId`) and the server metadata level. Ask the maintainer to run `/mcp reauth` on both once before release (manual check) |
