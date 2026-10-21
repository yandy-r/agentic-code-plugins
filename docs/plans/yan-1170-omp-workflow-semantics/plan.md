# YAN-1170 — Adapt OMP workflow semantics: questions, tools, worktrees, background jobs, artifacts

- **Linear:** YAN-1170 (YStack — OMP support, M1). **GitHub:** #399. **Target release:** ystack v6.1.0.
- **Spec:** [feature-spec.md](../../research/yan-1170-omp-workflow-semantics/feature-spec.md) (per-skill audit matrix, evidence, decisions).
- **Contract:** [ADR 0002](../../internal/adr/0002-omp-runtime-contract.md) follow-up row YAN-1170.
- **Base:** `main` (RELEASING.md, trunk-only, tracker `none`). **Mode:** `--parallel --enhanced`, three file-disjoint owners.

## Worktree Setup

- **Parent**: <repo-root>/.claude/worktrees/ystack-feat-yan-1170-omp-workflow-semantics/ (branch: feat/yan-1170-omp-workflow-semantics)

All tasks share this one worktree. No commits or pushes during implementation; `CHANGELOG.md` is not edited.

## Acceptance criteria (from Linear)

1. **AC1 — Matrix covers every skill.** The 50-row audit matrix (spec § Per-skill audit matrix) is the source of truth; every row marked G/T/S/P/F gets its adaptation.
2. **AC2 — Worktree-aware workflows use `.omp/worktrees/`** (or a documented native equivalent).
3. **AC3 — Interactive, print/JSON and RPC/non-interactive behavior is safe and deterministic** (questions, background jobs, dispatch).

Constraints: source changes only in `ycc/` or `scripts/generate_omp_*`; never hand-edit `packages/omp` or other generated bundles; keep the `ycc` namespace; no parity claim without a tested path; `./scripts/sync.sh` and `./scripts/validate.sh` before done.

## Verified runtime facts (omp 18.12.3, upstream `53a0377d`)

| Fact                                                                                                                                        | Evidence                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| OMP bash sets both `OMPCODE=1` and `CLAUDECODE=1`; today `worktree-paths.sh` resolves OMP to `.claude/worktrees`                            | [V-live] `env` probe; `procmgr.ts:44-54`                          |
| `ask` exists only in the TUI and `--mode rpc-ui`; absent in `-p`, `--mode json`, `--mode rpc`, subagents                                    | [V-live] tool probe; `ask.ts:581`, `executor.ts:4615`             |
| `-p`/JSON exits with async `task` jobs pending and drops their results; `wait` collects them                                                | [V-live] `AGENT_END awaitingAsyncWork: true`; `print-mode.ts:299` |
| `task` wire shape is `{context, tasks:[{agent, name, task, solutionSpace, isolated?}]}`; no `subagent_type`/`run_in_background`/`isolation` | `docs/tools/task.md`                                              |
| `task.isolation.enabled` defaults to `false`; isolated copies live in `~/.omp/wt`; `omp worktree list/clear` only touch `~/.omp/wt`         | `task/settings.ts:27-31,198-214`; [V-live]                        |
| Inline task summary capped at 5000 chars; full output at `agent://<id>`                                                                     | `docs/tools/task.md:79,176`                                       |
| Bash auto-backgrounds non-PTY commands after 60 s                                                                                           | `docs/settings.md:684-685`                                        |

## Decisions log

All nine spec "Decisions Needed" take the recommended option.

| #   | Decision                                 | Chosen                                                                                                                | Owner                                  |
| --- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| D1  | OMP worktree root                        | (a) `<repo-root>/.omp/worktrees/`; `~/.omp/wt` stays OMP-owned and is documented as native placement only             | A (generator), B (docs/tests)          |
| D2  | Detection precedence                     | (a) `OMPCODE=1` wins and consumes `CLAUDECODE`; agents bundle only                                                    | B                                      |
| D3  | Question policy placement                | (a) runtime-neutral `question-policy.md` + declared default per source skill; no generator injection                  | C                                      |
| D4  | Headless `choose-path`                   | (a) take `recommended` only when non-destructive; otherwise `confirm-destructive`                                     | C                                      |
| D5  | Dispatch shape                           | (a) one `task` call with `tasks[]`; documented fallback (b) one call per agent in one message when `task.batch=false` | A                                      |
| D6  | Pending results                          | (a) always `wait` until every owned job settles before yielding                                                       | A (template), C (`ci-monitoring.md`)   |
| D7  | `--team` on OMP                          | (a) fail closed; team advisories name OMP; `agent-team-dispatch.md` stays the unsupported note                        | A (advisory rewrite), C (source prose) |
| D8  | Capitalized `Read/Write/Edit/Bash` prose | (a) leave unchanged                                                                                                   | —                                      |
| D9  | Matrix verdict                           | `WORKTREE:omp` → `partial`, only with `test-worktree-roots.sh` covering omp; no native-parity claim                   | B                                      |

## Batches

| Batch | Tasks                                       | Depends on    | Notes                                                                  |
| ----- | ------------------------------------------- | ------------- | ---------------------------------------------------------------------- |
| 1     | A.1, A.2, A.3, B.1, B.2, B.3, C.1, C.2, C.3 | none          | Three owners run in parallel; files are disjoint (see ownership table) |
| 2     | I.1                                         | A._, B._, C.* | Orchestrator integration: regenerate, validate, tests, live OMP smoke  |

Inside each owner, tasks run in order (A.1 → A.2 → A.3; B.1 → B.2 → B.3; C.1 → C.2 → C.3).

## File ownership (disjoint)

| Owner                        | Files (exclusive)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A — generator + dispatch** | `scripts/generate_omp_skills.py`, `scripts/omp_templates/standalone-dispatch.md` (new), `scripts/test_generate_omp_skills.py`, `scripts/validate-omp-skills.sh`, `ycc/skills/_shared/references/standalone-dispatch.md`, `ycc/skills/_shared/references/review-dispatch.md`, `ycc/skills/orchestrate/references/dispatch-playbook.md` (only if a sentence-table anchor needs a stable source line)                                                                                                                                                                                                                                     |
| **B — worktree root**        | `ycc/skills/_shared/scripts/worktree-paths.sh`, `scripts/test-worktree-roots.sh`, `ycc/skills/_shared/references/worktree-strategy.md`, `ycc/skills/init/templates/git/gitignore.tmpl`, `.gitignore`, `ycc/settings/rules/CLAUDE.md`, `ycc/skills/_shared/references/target-capability-matrix.md`, `docs/internal/adr/0002-omp-runtime-contract.md`, `AGENTS.md`                                                                                                                                                                                                                                                                       |
| **C — question policy**      | `ycc/skills/_shared/references/question-policy.md` (new); the 24 asking skills' `SKILL.md` (backport, blueprint, bundle-release, clean, code-review, feature-research, formatters, git-cleanup, implement-plan, init, plan, plan-workflow, pr-autofix, prp-implement, prp-plan, prp-prd, prp-spec, quick-review, release-model, releaser, research-to-issues, resume-session, review-fix, save-session); `ycc/skills/git-cleanup/references/active-code-rules.md`; `ycc/skills/_shared/references/agent-team-dispatch.md`, `ci-monitoring.md`, `goal-pairing.md`; `ycc/agents/*.md` naming `AskUserQuestion` (today: `git-cleanup.md`) |
| **Orchestrator**             | Generated trees (`packages/**`, `.codex-plugin/**`, `.opencode-plugin/**`, `.agents-plugin/**`, `.cursor-plugin/**`) via `./scripts/sync.sh` only                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

### Cross-slice interfaces

- **I-1 (A ↔ B), verbatim blocks.** A's `WORKTREE_ROOT_REWRITE` (`/.claude/worktrees` → `/.omp/worktrees`) runs inside `body_rewrite`, which already operates on text returned by `protect_marked_verbatim_blocks`. Content between `<!-- ycc:verbatim-block:begin -->` / `end` is never rewritten. B adds the OMP row **inside** the existing verbatim block in `worktree-strategy.md` (lines ~100-157), so the multi-runtime table survives generation byte-for-byte.
- **I-2 (A ↔ A), sentence table.** `OMP_DISPATCH_SENTENCES` keys must match the final source wording A writes in `standalone-dispatch.md` §3/§7 and `review-dispatch.md`. A edits the source first, then builds the table from it; the drift check fails generation on mismatch.
- **I-3 (A ↔ C), shared reference names.** C creates `question-policy.md` at `ycc/skills/_shared/references/question-policy.md`. A's §9-10 text in `standalone-dispatch.md` may link it by that path; C's skill lines link it via `${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/question-policy.md` (generator rewrites the root per target).
- **I-4 (A ↔ B), validator allowlist.** A's forbidden-semantics scan allowlists `_shared/references/target-capability-matrix.md` and the verbatim runtime table in `_shared/references/worktree-strategy.md` (line-anchored on the B-authored rows). B must keep those rows inside the verbatim block.
- **I-5 (B ↔ C), git-cleanup.** C owns `git-cleanup/SKILL.md` and `active-code-rules.md`, including the "also list `.omp/worktrees/`; `~/.omp/wt` is OMP-managed" note. B does not touch them.

## Patterns to mirror

- `scripts/generate_opencode_dispatch.py:41` `render_standalone_dispatch_reference()` + `_split_numbered_sections()` — template §1-7 + canonical §8-10, fail on missing section.
- `scripts/opencode_templates/standalone-dispatch.md` — template file layout.
- `scripts/generate_omp_skills.py:123` `PATH_TOOL_SENTENCES` and the drift-check helper near line 363 (`table: str = "PATH_TOOL_SENTENCES"`).
- `scripts/generate_omp_skills.py:384-410` `body_rewrite` under `protect_marked_verbatim_blocks`.
- `ycc/skills/_shared/scripts/worktree-paths.sh:24` marker line `# @YCC_DEFAULT_WORKTREE_ROOT@` and `scripts/generate_agents_common.py:85-91` (marker-line swap precedent).
- `scripts/test-worktree-roots.sh:53-63` `BUNDLES` / `EXPECTED` / `CLEAN_ENV` tables.

## Step-by-step tasks

### Owner A — generator + dispatch

#### A.1 Source dispatch wording (runtime-neutral)

- **Files:** `ycc/skills/_shared/references/standalone-dispatch.md`, `ycc/skills/_shared/references/review-dispatch.md`, `ycc/skills/orchestrate/references/dispatch-playbook.md` (only if needed).
- **Depends on:** none.
- **Steps:**
  1. §3: replace the "end the turn to allow completion notifications" sentence with neutral wording: where the runtime offers a wait tool, call it until every spawned job settles; never end the turn while owned jobs run.
  2. §7 Cross-Target Portability: name OMP (dispatch via `task` batch, no team tools, `--team` fails closed).
  3. §9-10 batch-failure asks: point to `question-policy.md` class `failure-recovery` (I-3).
  4. `review-dispatch.md`: same §3-style wait sentence; keep vocabulary that the generator maps.
- **Acceptance:** wording is runtime-neutral (no OMP-only tool names in Claude prose); exact sentences recorded for A.2 (I-2). → AC3.

#### A.2 Generator projection + template

- **Files:** `scripts/generate_omp_skills.py`, `scripts/omp_templates/standalone-dispatch.md` (new).
- **Depends on:** A.1.
- **Steps:**
  1. Add `WORKTREE_ROOT_REWRITE` (`/.claude/worktrees` → `/.omp/worktrees`) inside `body_rewrite` for markdown **and** scripts, so `worktree-paths.sh`'s `@YCC_DEFAULT_WORKTREE_ROOT@` line emits `.omp`; verbatim blocks stay protected (I-1).
  2. Write `scripts/omp_templates/standalone-dispatch.md` §1-7 per spec § OMP dispatch contract: `task({context, tasks:[{agent, name, task, solutionSpace}]})`, never `isolated`; `task.batch=false` fallback; `wait` until all jobs settle (headless exits drop results); 5000-char truncation → `agent://<id>`; `todo` for own steps, `read proc://`, `write proc://<id>/kill`; `--team` abort, `write agent://<id>` is not a team lifecycle; disk-artifact backstop and failure policy unchanged.
  3. Add `render_omp_standalone_dispatch()`: template §1-7 + canonical §8-10 through `body_rewrite`; raise if a section number is missing.
  4. Add `_DISPATCH_WORDING`: `subagent_type` → `agent`; `isolation: "worktree"` / `isolation="worktree"` → `isolated: true` (code-span and roster regexes only).
  5. Add drift-checked `OMP_DISPATCH_SENTENCES` for `run_in_background`, "end the turn", "Monitor progress … `todo`" sentences and `dispatch-playbook.md` example blocks.
  6. Rewrite team advisories ("Cursor and Codex bundles lack team tools" → "Cursor, Codex and OMP bundles …").
- **Acceptance:** `python3 scripts/generate_omp_skills.py --check` style run passes after sync; regenerated `packages/omp/ycc/skills/_shared/references/standalone-dispatch.md` contains `tasks:`, `wait`, `agent://`, and no `isolated: true` recommendation for fan-out. → AC2, AC3.

#### A.3 Tests + validator

- **Files:** `scripts/test_generate_omp_skills.py`, `scripts/validate-omp-skills.sh`.
- **Depends on:** A.2.
- **Steps:**
  1. Tests: worktree-root rewrite (markdown + script), marker-line output `.omp`, verbatim-block preservation, template rendering (all §1-10 present; missing-section error), `_DISPATCH_WORDING` cases, sentence-table drift error, team-advisory rewrite.
  2. Validator: forbidden-semantics scan of `packages/omp` for `subagent_type|run_in_background|isolation: ?"worktree"|AskUserQuestion|TaskOutput|BashOutput|/\.claude/worktrees`; line-anchored allowlist for `_shared/references/target-capability-matrix.md` and the `worktree-strategy.md` runtime table (I-4).
- **Acceptance:** `python3 scripts/test_generate_omp_skills.py` green; `bash scripts/validate-omp-skills.sh` green on the regenerated tree and fails on an injected leak. → AC1, AC2, AC3.

### Owner B — worktree root

#### B.1 Detection + tests

- **Files:** `ycc/skills/_shared/scripts/worktree-paths.sh`, `scripts/test-worktree-roots.sh`.
- **Depends on:** none.
- **Steps:**
  1. In `ycc_runtime_worktree_root`: `OMPCODE=1` → `omp`, consuming the `CLAUDECODE` marker (do not count it twice). Update the comment's evidence list.
  2. Tests: add `[omp]="${REPO_ROOT}/packages/omp/ycc/skills/_shared/scripts"`, `EXPECTED[omp]=.omp`; add `-u OMPCODE` to `CLEAN_ENV`; agents-bundle cases `OMPCODE=1 CLAUDECODE=1` → `.omp` and `OMPCODE=1` → `.omp`; keep claude/codex/cursor/opencode/agents expectations; "ignores runtime markers" case also passes `OMPCODE=1` for non-agents bundles.
- **Acceptance:** after sync, `bash scripts/test-worktree-roots.sh` passes including the omp bundle and agents-bundle OMP cases. → AC2.

#### B.2 Worktree docs + ignore lists

- **Files:** `ycc/skills/_shared/references/worktree-strategy.md`, `ycc/skills/init/templates/git/gitignore.tmpl`, `.gitignore`, `ycc/settings/rules/CLAUDE.md`, `AGENTS.md`.
- **Depends on:** B.1.
- **Steps:**
  1. `worktree-strategy.md`, **inside** the verbatim block: OMP row `<repo-root>/.omp/worktrees/` — `generator rewrite (.omp)`; agents-bundle detection note (`OMPCODE`); native-placement evidence (task isolation and `omp worktree` use `~/.omp/wt`, `OMP_WORKTREE_DIR`; clone-first rewrite of literal `git worktree add` falls back to plain checkout for in-repo roots; isolation skips gitignored in-repo roots, #16068).
  2. Add `.omp/worktrees/` to `gitignore.tmpl`, root `.gitignore` (YAN-1111 block), and `ycc/settings/rules/CLAUDE.md` root list.
  3. `AGENTS.md` worktree table: add `| OMP | <repo-root>/.omp/worktrees/ |`; keep the file ≤150 lines (today 125).
- **Acceptance:** OMP row present in source and byte-identical in `packages/omp` after sync (verbatim); `wc -l AGENTS.md` ≤ 150. → AC2.

#### B.3 Capability matrix + ADR

- **Files:** `ycc/skills/_shared/references/target-capability-matrix.md`, `docs/internal/adr/0002-omp-runtime-contract.md`.
- **Depends on:** B.1.
- **Steps:**
  1. `WORKTREE:omp` → `partial` (tested `.omp/worktrees` via scripts + `test-worktree-roots.sh`; no native `WorktreeCreate` hook). Update `SKILLS:omp` and `AGENTS:omp` notes: `task` batch dispatch, `wait`-before-yield, `ask` availability per mode, `--team` unsupported.
  2. ADR 0002 follow-up row YAN-1170: state delivered scope (`.omp/worktrees` root, `OMPCODE` detection, OMP dispatch template, question policy); isolation stays off for ycc fan-out.
- **Acceptance:** `compatibility-audit --target=omp` (or `./scripts/validate.sh`) reports no matrix errors. → AC1, AC2.

### Owner C — question policy

#### C.1 `question-policy.md`

- **Files:** `ycc/skills/_shared/references/question-policy.md` (new).
- **Depends on:** none.
- **Steps:** Write the runtime-neutral reference: detection rule (question tool "available" only if `ask` or `AskUserQuestion` is in the tool list; never call an absent one); subagents never ask, return choices to parent; the six gate classes (`clarify`, `confirm-destructive`, `confirm-publish`, `choose-path`, `checkpoint`, `failure-recovery`) with interactive and non-interactive defaults per spec § Data Models; destructive/publishing gates never auto-approve without an explicit flag; one-line plain-text `rerun with <flag>` output; every question carries a `recommended` option equal to the declared default (covers `ask.timeout > 0`); text-mode fallback (moved from quick-review) for chat runtimes without a question tool; OMP mode table (TUI/rpc-ui ask; `-p`/json/rpc/subagents declared default).
- **Acceptance:** file exists; all six classes and the detection rule present. → AC3.

#### C.2 Per-skill declared defaults

- **Files:** the 24 asking skills' `SKILL.md`; `ycc/skills/git-cleanup/references/active-code-rules.md`.
- **Depends on:** C.1.
- **Steps:**
  1. Add one line per skill: `**Questions:** class \`<class>\`; without a question tool: <default>. See \`${CLAUDE_PLUGIN_ROOT}/skills/_shared/references/question-policy.md\`.`Classes and defaults per the spec matrix rows marked **P** (e.g. backport`confirm-destructive`, blueprint `clarify`, clean `confirm-destructive`→ report-only, code-review`confirm-publish`→`--save`, feature-research `choose-path`→ enhance, git-cleanup`confirm-destructive`→ dry-run report, implement-plan`failure-recovery`, plan `checkpoint`, plan-workflow `checkpoint`→`--no-checkpoint`, prp-implement `choose-path`→ sequential +`failure-recovery`, quick-review `choose-path`→ Save to file, releaser/bundle-release/release-model`confirm-publish`, resume-session/save-session `checkpoint`).
  2. quick-review: replace the local text-mode fallback with the policy reference.
  3. git-cleanup `SKILL.md` + `active-code-rules.md`: also list `<repo-root>/.omp/worktrees/` as a managed root; note `~/.omp/wt` is OMP-managed (`omp worktree clear`), never deleted by ycc.
- **Acceptance:** `grep -l 'question-policy.md' ycc/skills/*/SKILL.md | wc -l` = 24. → AC1, AC3.

#### C.3 Shared refs + agents

- **Files:** `ycc/skills/_shared/references/agent-team-dispatch.md`, `ci-monitoring.md`, `goal-pairing.md`, `ycc/agents/*.md` naming `AskUserQuestion` (today `git-cleanup.md`).
- **Depends on:** C.1.
- **Steps:**
  1. `agent-team-dispatch.md` §8 failure ask → `failure-recovery` class reference (keep it the "unsupported on OMP" note).
  2. `ci-monitoring.md`: long monitors may auto-background (OMP >60 s); pass a sufficient `timeout` or `wait` for the job; never yield while it runs.
  3. `goal-pairing.md` caveat 2 → `question-policy.md`.
  4. Agents: subagents cannot ask; return choices to the parent caller (replace "present via AskUserQuestion").
- **Acceptance:** `grep -rn AskUserQuestion ycc/agents` empty, or only "the parent asks" phrasing; regenerated `packages/omp` passes A.3's scan. → AC3.

### Integration (orchestrator)

#### I.1 Regenerate, validate, smoke

- **Depends on:** A.3, B.3, C.3.
- **Steps:**
  1. `./scripts/sync.sh` (all targets; shared refs and `worktree-paths.sh` feed every bundle).
  2. `./scripts/validate.sh`.
  3. `npm run lint:modified`.
  4. `python3 scripts/test_generate_omp_skills.py` and `bash scripts/test-worktree-roots.sh`.
  5. Leak scan: `grep -rEn 'subagent_type|run_in_background|isolation: ?"worktree"|AskUserQuestion|TaskOutput|BashOutput|/\.claude/worktrees' packages/omp` → only allowlisted lines.
  6. Live OMP smoke: temp `HOME=$(mktemp -d)`, install/load the generated `packages/omp/ycc` (`--plugin-dir`), run headless `omp -p --no-session "Run: source <pkg>/skills/_shared/scripts/worktree-paths.sh; ycc_worktree_root"` in a temp git repo and confirm `<repo>/.omp/worktrees`, and `echo $OMPCODE` = `1`. Also run the agents bundle helper under `omp -p` and confirm `.omp/worktrees`.
- **Acceptance:** all commands exit 0; smoke output shows `.omp/worktrees` under `OMPCODE`. → AC2, AC3.

## Acceptance mapping

| Linear AC                     | Satisfied by                                                                                                                   | Check                                                                            |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| AC1 matrix covers every skill | Spec matrix (50 rows) + A.2/A.3 (G, T), B.2/B.3 (S, matrix), C.2/C.3 (P, S)                                                    | Leak scan in I.1 step 5; `grep -l question-policy.md` = 24; matrix cells updated |
| AC2 `.omp/worktrees/`         | A.2 rewrite + marker line; B.1 detection; B.2 docs/ignores; B.3 `WORKTREE:omp` partial                                         | `test-worktree-roots.sh` omp + agents cases; live `omp -p` smoke                 |
| AC3 safe, deterministic modes | A.2 template (`task` batch, `wait`-before-yield, `agent://`, no `isolated`); C.1 policy + C.2 defaults; C.3 ci-monitoring wait | `test_generate_omp_skills.py`; validator scan; `validate.sh`                     |

## Validation commands

```bash
./scripts/sync.sh
./scripts/validate.sh
npm run lint:modified
python3 scripts/test_generate_omp_skills.py
bash scripts/test-worktree-roots.sh
bash scripts/validate-omp-skills.sh
wc -l AGENTS.md   # <= 150
```

## NOT building

- OMP-native `--team` via `write agent://` peers; opt-in `isolated: true` batches (spec § Future Enhancements).
- Mapping capitalized `Read/Write/Edit/Bash` prose (D8).
- `CHANGELOG.md` edits (out of scope for this run).
- Hand edits to any generated bundle.

## Risks

| Risk                                              | Mitigation                                                   |
| ------------------------------------------------- | ------------------------------------------------------------ |
| Global root rewrite corrupts multi-runtime tables | Verbatim blocks (I-1), validator allowlist (I-4), unit test  |
| `subagent_type` → `agent` hits non-dispatch prose | Code-span/roster regexes only; review regenerated diff       |
| Sentence-table drift on later source edits        | Generation fails loudly (I-2)                                |
| Model ignores `wait` rule in `-p`                 | Rule in §2/§3 of template; disk-artifact backstop remains    |
| `OMPCODE` misdetects Claude nested in OMP         | Agents bundle only; `YCC_WORKTREE_ROOT` override; documented |
