# UX research: OMP coexistence

## Executive Summary

Users get one line per finding, each naming a concrete command. The install hides the duplicates and prints the undo command. Users verify with `omp skill list`. Untrusted repos use one documented, tested invocation.

## User Workflows

### Install (P1: `--target all`, or `agents` then `omp`)

```text
$ ./install.sh install --target all
…agents complete.
omp: install ycc@ycc, ycc-mcp@ycc, ycc-rules@ycc (user scope)
omp: hide ycc duplicates in /home/u/.omp/agent/config.yml (dedupe)
  [ok] wrote /skills/ignoredSkills (+41 items)
[ok] OMP: hid 41 ycc duplicate skills (agents/…) via skills.ignoredSkills in /home/u/.omp/agent/config.yml; ./install.sh remove --target omp --only dedupe restores them
[ok] new sessions pick this up (/reload-plugins or restart)
```

- **Before.** Today the same run prints one line: `[!!] ~/.agents/skills holds 41 ycc skills that OMP
also loads; remove them with ./install.sh remove --target agents --only base`. That remedy breaks
  Codex, Cursor and opencode when their skills were consolidated there.
- **After.** OMP hides its own view of the duplicates. The other tools keep their copies.

### Install order reversed (`omp` first, then `agents`)

The agents target prints W5 and points at `install --target omp --only dedupe`. It never writes OMP
config itself (BR2): the agents target owns `~/.agents` only.

### Verify

- `omp skill list` (stderr is empty once deduped).
- In a session, `/skill:plan` resolves to the OMP package path.
- `/mcp list` shows `ycc-mcp:linear` and `ycc-mcp:linear-personal`.

### Opt out or restore

| Goal                                     | Command                                                                                                                        |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Show the `~/.agents` copies again in OMP | `./install.sh remove --target omp --only dedupe` (owned list items only; user items kept)                                      |
| Remove ycc from OMP entirely             | `./install.sh remove --target omp --only base`. It removes the packages and dedupe entries, and project residue at `--project` |
| Keep duplicates (never write)            | `./install.sh install --target omp --only base` (W2 still prints)                                                              |

### Untrusted repository

Documented in `docs/install/omp.md` § Coexistence → Untrusted projects, and backed by a live test:

```bash
printf 'mcp:\n  enableProjectConfig: false\n' > ~/.omp/agent/untrusted.yml
omp --no-extensions --config ~/.omp/agent/untrusted.yml
```

- **Effect.** ycc skills, commands, agents, rules and `ycc-mcp:*` still load. Project hooks,
  extensions, `.mcp.json` and the project `extensions:` setting do not run.
- **Why an overlay.** It must come from `--config`: a project `.omp/config.yml` overrides user
  settings, so a kill switch set in the user config is beaten by the repository (verified live).
- **Plugins.** A project plugin registry's MCP server is blocked by the same pair. A project plugin's
  skills still load as text.

## Error states

| Situation                                               | Behavior                                                                                                                                                         |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.yml` is a symlink, or invalid YAML              | The merge refuses and changes nothing (existing `omp-config` `refuse_symlink` and parse). The dedupe step prints the merge error, and the install exits non-zero |
| User edited `skills.ignoredSkills`                      | `list-union` keeps the user's items. Only items ycc appended are ever removed                                                                                    |
| A project `.omp/config.yml` sets `skills.ignoredSkills` | The duplicates reappear in that project (arrays replace). Documented, with the fix "add `agents/*` to the project list or remove it"                             |
| No ledger (pre-ledger `~/.agents` install)              | W3 only. The fix: `./install.sh install --target agents` once (re-records ownership), then `install --target omp`                                                |
| `--project`                                             | Dedupe still writes the **user** `config.yml`. The line says `user scope`                                                                                        |
| `--dry-run`                                             | Prints `would add N items to /skills/ignoredSkills` and writes nothing                                                                                           |
| Second profile                                          | Dedupe is per `omp config path`. The profile note already says to run the installer per profile                                                                  |

## Performance UX

Hiding the 41 aliases removes about 3.6 k characters from every main-session prompt (probe A vs B).

## Messaging rules

- One line per finding, with the count, the source dir, the visible OMP name pattern and one exact
  command.
- `[ok]` for actions taken, `[!!]` for anything left for the user.
- Never say "harmless" for OMP. Each alias adds a prompt line (+17 % prompt, probe B).
- Point at `omp skill list` for verification. It prints OMP's own collision warnings.

## Accessibility

CLI text only. Messages are plain ASCII prefixes (`[ok]`, `[!!]`) and already pass through
`NO_COLOR`/`TERM=dumb`. No new color-only signals.
