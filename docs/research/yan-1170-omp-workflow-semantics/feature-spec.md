# Feature Spec: OMP workflow semantics (questions, tools, worktrees, background jobs, artifacts)

Linear YAN-1170 / GitHub #399. Target runtime: oh-my-pi (`omp`) 18.12.3, upstream
`can1357/oh-my-pi` at `53a0377d` (2026-10-19), with `packages/coding-agent/package.json`
version `18.12.3`. Every fact marked **[V-live]** was observed with the installed binary in a
throwaway `HOME=/tmp/omp-yan1170.*/home`; **[V-src]** cites upstream source or docs at that
commit; **[INFERENCE]** is not verified.

## Executive Summary

The generated OMP skill tree (`packages/omp/ycc/skills`) maps tool _names_ but keeps
Claude workflow _semantics_. It tells the model to call
`task(subagent_type=…, description=…, prompt=…)`, to omit `run_in_background`, to avoid
`isolation: "worktree"` and to "end the turn" while results are pending. It also creates
worktrees under `.claude/worktrees`. Two live findings make this more than cosmetic:

1. OMP sets **both** `OMPCODE=1` and `CLAUDECODE=1` in every bash subprocess, so today's
   `worktree-paths.sh` detection resolves OMP to `.claude/worktrees`.
2. In `-p`/`--mode json`, a turn that ends with a background `task` job still running
   **exits the process and drops the result**.

`ask` is not registered at all in `-p`, `--mode json`, `--mode rpc` or any subagent. It
exists only in the interactive TUI and `--mode rpc-ui`. A deterministic, runtime-neutral
question policy is therefore required.

The design has four parts:

- **Generator-level OMP projection.** Add a `.claude/worktrees` → `.omp/worktrees` rewrite,
  an OMP-native `standalone-dispatch.md` template, dispatch vocabulary rewrites, and a
  validator that forbids Claude-only semantics in `packages/omp`.
- **Runtime-neutral source helpers.** Add `OMPCODE` detection in `worktree-paths.sh` and a new
  shared `question-policy.md`, which each asking skill references with its declared
  non-interactive default.
- **Wait-before-yield rule.** Background jobs must be awaited with `wait` before the turn ends.
- **No per-skill runtime branches.**

## External Dependencies

### APIs and Services

#### OMP `ask` tool: availability per mode

| Mode                                       | `ask` registered?                                | Evidence                                                                                                                                                        |
| ------------------------------------------ | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Interactive TUI (`omp`)                    | yes                                              | [V-live] probe extension `-e probe.ts` (`pi.getActiveTools()` on `session_start`) under `script -qec omp` printed `tools=["ask",…]`                             |
| `-p` / `--mode text -p` / `--mode json -p` | **no**                                           | [V-live] the same probe printed `["ast_edit","bash","debug","edit","eval","glob","grep","lsp","read","task","todo","wait","web_search","write"]`, `hasUI=false` |
| `--mode rpc`                               | **no**                                           | [V-live] probe: same list as above (no `ask`). RPC `get_state.dumpTools` also lacked `ask`                                                                      |
| `--mode rpc-ui`                            | yes                                              | [V-live] probe/`get_state`: `ask` present                                                                                                                       |
| Subagents (any mode)                       | **no**                                           | [V-src] `src/task/executor.ts:4615` creates child sessions with `hasUI: false`                                                                                  |
| ACP                                        | only if the client advertises `elicitation.form` | [V-src] `src/modes/acp/acp-agent.ts:1247` `interactivePrompts: …elicitation?.form != null`                                                                      |

Registration and runtime behavior:

- **Registration.** [V-src] `AskTool.createIf` (`src/tools/ask.ts:581`) registers only when
  `canPromptUser ?? hasUI` is set. `main.ts:2279` sets `hasUI = isInteractive || mode === "rpc-ui"`,
  and `isInteractive = !print && !autoPrint && mode === undefined` (`main.ts:1877`).
- **Absent means not offered.** When `ask` is absent, the model simply does not have the tool;
  it is not an error. [V-live] In `omp -p --model tokenhop/cc/claude-haiku-5-5 "Call the ask tool …"`,
  the model answered `NO_ASK_TOOL`.
- **Forced call.** [V-src] A forced call without UI throws
  `ToolAbortError("Ask tool requires interactive mode")` (`docs/tools/ask.md` § Errors).
- **Cancel.** Throws `Ask tool was cancelled by the user`.
- **Timeout.** [V-src] `ask.timeout` defaults to `0` (disabled); `docs/settings.md:901`. When
  it is set, the fallback picker auto-selects the `recommended` option, or else the first
  option, and tags the answer `(auto-selected after timeout)`. Plan mode disables the timeout.
  The default is **no auto-select**.
- **RPC UI frames.** [V-src] `docs/rpc.md` § Extension UI Sub-Protocol: under `rpc-ui`, `ask`
  sends `select`/`editor` frames, and the `ask` frame is sent only after `set_ask_dialog`.

#### Runtime identity env vars in bash subprocesses

- **Spawn env.** [V-src] `packages/utils/src/procmgr.ts:44-54` `buildSpawnEnv()` sets
  `OMPCODE: "1"`, `CLAUDECODE: "1"`, `GIT_EDITOR: "true"`, `GPG_TTY: "not a tty"` and
  `CI: "true"` (unless `PI_BASH_NO_CI`/`CLAUDE_BASH_NO_CI`).
- **Non-interactive defaults.** [V-src] `src/exec/non-interactive-env.ts` adds `AGENT=1`,
  `TERM=dumb`, `NO_COLOR=1`, `PAGER=cat`/`GIT_PAGER=cat`/`GH_PAGER=cat`,
  `GIT_TERMINAL_PROMPT=0`, `GH_PROMPT_DISABLED=1`, `DEBIAN_FRONTEND=noninteractive`,
  `PIP_NO_INPUT=1` and others (`docs/bash-tool-runtime.md:172-178`).
- **Live check.** [V-live] I ran `env -u CLAUDECODE -u OMPCODE … omp -p … "Run … env | grep -E '^(OMPCODE|CLAUDECODE|OPENCODE|CODEX_THREAD_ID|CI|AGENT|TERM)='"`.
  Output: `AGENT=1 CI=true CLAUDECODE=1 OMPCODE=1 TERM=dumb`. OMP injects these values; they
  are not inherited.
- **Detector impact.** [V-live] In this OMP session's bash,
  `source ycc/skills/_shared/scripts/worktree-paths.sh; ycc_runtime_worktree_root /r` printed
  `/r/.claude/worktrees`. The packaged OMP copy prints the same, because the file is generated
  byte-identically today (`diff` was empty).
- **Distinguishing marker.** `OMPCODE=1` is the only marker unique to OMP. `CLAUDECODE=1`
  alone cannot tell Claude Code and OMP apart.

#### `task` tool: async, background, isolation, artifacts

- **Wire shape.** [V-src] `docs/tools/task.md` § Inputs. With `task.batch` on (default
  `true`; RPC/ACP pin the default), the shape is
  `{ context, tasks: [{ name?, agent?, task, solutionSpace, isolated?, outputSchema?, … }] }`.
  - `agent` selects the agent type by frontmatter `name`, for example `implementor`.
  - There are no `subagent_type`, `description`, `prompt`, `run_in_background` or
    `isolation` fields.
  - The flat shape is used when `task.batch` is off.
- **Async.** [V-src] `async.enabled` defaults to `true` (`src/tools/settings.ts:929`).
  Non-blocking spawns become background jobs and the call returns
  ``Spawned agent `<id>` (job `<id>`)`` immediately. Results auto-deliver as async-result
  messages; `wait` blocks for the next one.
- **Async in print/JSON mode.** [V-live] In `--mode json -p`, the model called `task`, then
  `wait`. `wait` returned `## Completed (1) … <task-result …>` and the final reply was
  `FINAL: SUBAGENT_DONE_42`.
- **Dropped result (critical).** [V-live] Prompt: spawn one subagent (`sleep 5; echo BG_RESULT_77`),
  end the turn without `wait`, and reply `DELIVERED:` when the result arrives.
  - Event stream: `TOOL task` → `TOOLRESULT Spawned agent StickyOrca` → `ASSISTANT SPAWNED` →
    `AGENT_END {'yielded': True, 'awaitingAsyncWork': True}`.
  - The process then exited (wall 5.96 s) without a `DELIVERED:` turn.
  - Cause: print mode returns after `session.waitForIdle()` (`src/modes/print-mode.ts:299`),
    which does not wait for async jobs (`src/session/agent-session.ts:6497-6517`).
  - So the Claude "end the turn and let notifications arrive" instruction **loses results in
    headless OMP**.
- **Truncation.** [V-src] An inline settled summary is capped at 5000 chars
  (`FULL_OUTPUT_THRESHOLD`). The full output is in `agent://<id>` (`docs/tools/task.md:79,176`).
- **Isolation.** [V-src] `isolated` exists only when `task.isolation.enabled` is set (default
  **`false`**, `src/task/settings.ts:27-31`) and plan mode is off.
  - Isolated workspaces are created by the natives PAL (overlayfs/reflink/btrfs/…/rcopy) under
    the agent-managed worktree base `worktree.base`, default `~/.omp/wt`, overridable with
    `OMP_WORKTREE_DIR` (`src/task/settings.ts:198-214`; `docs/environment-variables.md:571`;
    `src/task/isolation-ownership.ts:2`).
  - Changes merge back as a patch (default) or a branch (`omp/task/<id>`)
    (`task.isolation.merge`, `task.isolation.apply=true`).
- **Concurrency.** [V-src] A session semaphore `task.maxConcurrency` bounds concurrency.
  Parallel fan-out is either one `tasks[]` batch or several `task` calls in one message
  (`docs/tools/task.md:193`).

#### Background jobs, `wait`, `proc://`

- **`wait`.** [V-src] `docs/tools/wait.md`: takes no arguments and returns on the first
  settled caller-owned job or peer message. Jobs can be inspected with `read proc://<id>`
  (non-consuming) and cancelled with `write proc://<id>/kill`.
- **Bash auto-background.** [V-src] `bash.autoBackground.enabled=true` with
  `thresholdMs=60000` (`docs/settings.md:684-685`). A non-PTY command that runs longer than
  60 s becomes a background job (`docs/tools/bash.md:153`). The bash tool also has
  `async: true` and managed services (`name` + `ready`).
- **No Claude equivalents.** There is no `BashOutput`/`TaskOutput`/`Monitor` tool. The
  equivalents are `wait`, `read proc://` and `write proc://<id>/kill`.

#### Tool names (OMP 18.12.3 default surface)

- [V-live] Probe lists:
  - **Print/RPC:** `ast_edit, bash, debug, edit, eval, glob, grep, lsp, read, task, todo, wait, web_search, write`.
  - **Interactive and `rpc-ui`:** the same plus `ask`.
- [V-src] Other tools are conditional or discoverable (`docs/tools/*.md`): `find`, `checkpoint`,
  `rewind`, `browser`, `github`, `recall`/`retain`/`reflect`, `generate_image`, `tts`,
  `computer`, `security_scan`.
- `WebFetch` is `read` with a URL. There is no `NotebookEdit` (use `edit`), no Claude
  `Skill` tool (skills are read as `skill://<name>`), and no team tools
  (`TeamCreate`/`SendMessage`). Peer messaging is `write agent://<id>`.

#### Internal URLs and artifacts

- **`local://`.** [V-src] `docs/tools/read.md:252`, `docs/tools/task.md:159,194`. It is
  session-scoped, writable and shared between the parent and its subagents. Use it for
  scratch and shared context, not for repo deliverables.
- **`artifact://<id>`.** [V-src] `docs/blob-artifact-architecture.md:153-170`: numeric id;
  read-only spill of truncated tool output under the session artifacts dir. Without an
  artifact dir it throws `No session - artifacts unavailable`.
- **`agent://<id>`.** Full subagent output (`<id>.md`). `history://<id>` is the transcript.
- **`skill://`.** [V-src] `docs/bash-tool-runtime.md:34`. External programs see `skill://`
  translated only when it is a whole argument or an `--opt=URL` value. Command text is never
  rewritten, so URLs inside `bash -c '…'` strings or _inside_ child scripts are not resolved.
  The existing generator already rewrites script-internal plugin paths
  (`rewrite_script_plugin_paths`).

#### Skill frontmatter `allowed-tools`

[V-src] `docs/skills.md:50-61` lists the fields that matter for skills: `name`, `description`,
`globs`, `alwaysApply`, `hide`, `disableModelInvocation`/`disable-model-invocation` and
`enabled`. Unknown keys are kept as metadata. `allowed-tools` is only _type-checked as a
string_ by the strict Agent Plugins validator (`src/discovery/agent-plugin-format.ts:94,155-158`)
and grants nothing. The generator already drops it (`KEPT_FRONTMATTER_KEYS`).

#### Worktrees and git in OMP bash

- **Clone rewrite.** [V-src] `worktree.clone` defaults to `true` (`src/task/settings.ts:77-87`).
  The bash tool rewrites a _literal_ `git worktree add …` in the command text to
  `omp worktree add …` (clone-first) (`src/tools/bash-worktree-rewrite.ts`;
  `src/tools/bash.ts:1050`). Commands inside child scripts such as `setup-worktree.sh` are not
  rewritten.
- **In-repo destination.** [V-live] I ran `omp worktree add -b feat/x $T/proj/.omp/worktrees/proj-x`.
  The clone recursed into its own destination, then printed
  `warning: worktree clone fell back to plain checkout` and produced a correct linked worktree.
  `.claude/worktrees/…` behaved the same way. The fallback works, but the clone path is not
  usable for in-repo roots.
- **`omp worktree list|clear`.** Manages only `~/.omp/wt` ([V-live]
  `No agent-managed worktrees found under …/home/.omp/wt`), so it never touches repo-local
  ycc worktrees.
- **Isolation snapshot.** [V-src] CHANGELOG 18.12.3: isolated tasks no longer snapshot linked
  worktrees under a gitignored in-repo root (#16068). A repo-local `.omp/worktrees/` is safe
  for isolation.
- **`.omp/` discovery.** [V-src] `src/discovery/builtin.ts:111-122` treats the nearest
  non-empty `.omp/` between cwd and the repo root as project config. A `.omp/worktrees/`
  directory makes `<repo>/.omp/` exist but adds no config files. Inside a linked worktree the
  walk stops at the worktree's own git root.
- **Approvals.** [V-src] `tools.approvalMode` defaults to `yolo`, and subagents are forced to
  `yolo` (`docs/tools/task.md` step 12). Under `--mode rpc --no-ui`, tools that need approval
  fail closed (`docs/rpc.md:1210`).

### Libraries and SDKs

None new. Python 3.11 generators (`scripts/generate_omp_*.py`, reusing
`generate_codex_common.protect_marked_verbatim_blocks`) and bash helpers under
`ycc/skills/_shared/scripts/`.

### External Documentation

- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/tools/ask.md>
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/tools/task.md>
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/tools/wait.md>
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/tools/bash.md>
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/bash-tool-runtime.md>
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/rpc.md> (Extension UI Sub-Protocol)
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/skills.md> (`SKILL.md` frontmatter)
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/blob-artifact-architecture.md>
- <https://github.com/can1357/oh-my-pi/blob/53a0377d/docs/settings.md>, `docs/environment-variables.md`

## Business Requirements

### User Stories

- As an OMP user running `/ycc:implement-plan`, I want the feature worktree created under
  `<repo>/.omp/worktrees/<repo>-<feature>/`, so OMP work never lands in Claude's root.
- As an OMP user running a fan-out skill headless (`omp -p "/ycc:plan-workflow …"`), I want
  every subagent result collected before the run exits.
- As an RPC/CI host, I want skills that normally ask questions to take a documented,
  non-destructive default or stop with an exact rerun hint, never hang or guess.
- As a maintainer, I want the OMP projection done once in the generator and shared references,
  with tests that fail when Claude-only semantics leak into `packages/omp`.

### Business Rules

1. **Single-worktree contract stays.** ycc pre-creates one feature worktree with
   `setup-worktree.sh` and dispatches agents with `Working directory:`. On OMP, never set
   `isolated: true` for that fan-out; isolation would create one `~/.omp/wt` copy per agent
   and merge patches back.
2. **Worktree root.** On OMP the root is `<repo-root>/.omp/worktrees/`.
   `YCC_WORKTREE_ROOT` still overrides it everywhere.
3. **Questions.** If the question tool (`ask` or `AskUserQuestion`) is available, ask. If it
   is not, apply the skill's declared non-interactive default (see the Question policy
   below). Never call a question tool that is not in the tool list.
4. **Destructive or publishing gates** never auto-approve without an explicit flag (`--yes`,
   `--apply`, `--ci-yes`, …). Headless runs stop and print the exact rerun command.
5. **Background results.** Never end a turn while spawned jobs you own are running. Call
   `wait` until every job has settled, and validate each report, reading `agent://<id>` when
   the inline summary is truncated.
6. **No parity claims.** A capability-matrix cell moves from `unsupported` only with a tested
   path (unit test plus `test-worktree-roots.sh`, and the live `-p` probe where noted).
7. **Namespace and source.** Keep the `ycc` namespace. Edit `ycc/` or `scripts/generate_omp_*`
   only; never hand-edit `packages/omp/`.

### Edge Cases

- **Nested runtimes.** Claude Code launched from an OMP bash inherits `OMPCODE=1` and gets
  `CLAUDECODE=1`, so it would be detected as OMP [INFERENCE: rare]. OMP launched from Claude
  Code sets both markers and is correctly OMP. Detection only matters for the portable
  `agents` bundle; the OMP package hard-codes `.omp`.
- **Async off.** `async.enabled=false`, or RPC with that setting pinned: `task` runs inline,
  `wait` may be absent, and the policy "call `wait` only if jobs are pending and `wait` exists"
  still holds.
- **Batch off.** `task.batch=false`: one `task` call per agent in a single message, with shared
  context written to `local://ctx.md`.
- **Plan mode.** `isolated` is removed and only read-only tools remain. Skills that write
  artifacts must not be run in plan mode [INFERENCE: behavior is unchanged from today].
- **`ask.timeout > 0`.** In interactive mode an unanswered `ask` auto-selects `recommended`.
  Every ycc question therefore needs a `recommended` option that matches the declared
  non-interactive default.

### Success Criteria

- [ ] `packages/omp` contains no `subagent_type`, `run_in_background`, `isolation: "worktree"`,
      `AskUserQuestion`, `TaskOutput`/`BashOutput` or `/.claude/worktrees` outside the
      allowlisted multi-runtime files. The validator enforces this.
- [ ] `test-worktree-roots.sh` asserts `omp` → `.omp/worktrees`, and asserts that the agents
      bundle with `OMPCODE=1 CLAUDECODE=1` → `.omp/worktrees`.
- [ ] The OMP `standalone-dispatch.md` describes the `task {context, tasks[]}` shape, `wait`,
      `agent://` and the no-`isolated` rule. Generator tests cover it.
- [ ] Every skill in the matrix below with a question gate has a declared non-interactive
      default linked to `question-policy.md`.
- [ ] `target-capability-matrix.md` `WORKTREE:omp` and `SKILLS:omp` notes are updated with
      the evidence.

## Technical Specifications

### Architecture Overview

```
ycc/skills (canonical, runtime-neutral)
  _shared/references/question-policy.md   NEW: gate classes + headless defaults
  _shared/references/standalone-dispatch.md   §1-7 Claude-facing, §8-10 neutral
  _shared/scripts/worktree-paths.sh       + OMPCODE marker (agents bundle)
        │
        ▼ scripts/generate_omp_skills.py
  1. path / namespace / tool-name rewrites (existing)
  2. NEW worktree root: "/.claude/worktrees" -> "/.omp/worktrees" (verbatim blocks protected)
  3. NEW dispatch projection:
       standalone-dispatch.md = scripts/omp_templates/standalone-dispatch.md (§1-7)
                              + canonical §8-10 run through the OMP rewrite
       vocabulary: subagent_type -> agent; isolation:"worktree" -> isolated: true;
       OMP_DISPATCH_SENTENCES table (drift-checked, like PATH_TOOL_SENTENCES)
  4. team advisories name OMP; agent-team-dispatch.md stays the "unsupported" note
        │
        ▼
  packages/omp/ycc/skills  --(validate-omp-skills.sh: forbidden-semantics scan)--> OK
```

### Data Models

#### Question gate classes (`question-policy.md`)

| Class                 | Examples                                                                                 | Interactive | Non-interactive default (no question tool)                                                                                               |
| --------------------- | ---------------------------------------------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `clarify`             | blueprint/prp-prd/prp-spec interviews, prp-plan "STOP and ask"                           | ask         | Print the open questions, write nothing, stop.                                                                                           |
| `confirm-destructive` | clean delete, git-cleanup apply, formatters install, pr-autofix apply, backport continue | ask         | Do not act. Fall back to the read-only path (report/dry-run/save) and print `rerun with <flag>`.                                         |
| `confirm-publish`     | releaser tag/publish, code-review publish, bundle-release, release-model write           | ask         | Stop before the side effect and print `rerun with <flag>`.                                                                               |
| `choose-path`         | quick-review action, prp-implement parallel?, feature-research regenerate                | ask         | Take the option marked `recommended` only if it is non-destructive (Save / sequential / enhance). Otherwise apply `confirm-destructive`. |
| `checkpoint`          | plan-workflow research review, save-session review                                       | ask         | Continue (artifacts are docs only) and report the checkpoint in the summary.                                                             |
| `failure-recovery`    | batch validation failure (implement-plan, prp-implement, review-fix, team dispatch)      | ask         | Stop, preserve completed work, and report the failing batch plus resume command. Never auto-retry or skip.                               |

Detection rule: the question tool is "available" only if `ask` (OMP) or `AskUserQuestion`
(Claude) appears in the current tool list. Subagents never ask; they return choices to the
parent. The existing quick-review text-mode fallback (print the choices, wait for a reply)
becomes the shared interactive fallback for runtimes that have no question tool but do have a
chat turn (Cursor/Codex).

### API Design

#### OMP dispatch contract (template `scripts/omp_templates/standalone-dispatch.md`, §1-7)

```
task({
  context: "<shared background: goal, plan path, worktree line, artifact contract>",
  tasks: [
    { agent: "<ycc agent name, e.g. implementor>", name: "<CamelCase role>",
      task: "<full self-contained prompt incl. Working directory:>",
      solutionSpace: "<how open-ended>" },
    …
  ]
})
```

1. **One batch.** Use one `task` call with one item per independent agent, and never set
   `isolated`. If `task.batch` is off, issue one `task` call per agent in a single message.
2. **Collecting results.** If the call returns background job ids, call `wait` repeatedly until
   every job has settled. Never end the turn with jobs pending: headless runs exit and drop
   them.
3. **Validating reports.** A summary longer than 5000 chars is truncated; read `agent://<id>`
   for the full report. The disk-artifact backstop and failure policy (§5-6) are unchanged.
4. **Progress.** `todo` tracks only the orchestrator's own steps. Use `read proc://` to inspect
   jobs and `write proc://<id>/kill` to cancel one.
5. **Teams.** `--team` is unsupported, so abort (see `agent-team-dispatch.md`). Peer messaging
   is `write agent://<id>`, but it is not a team lifecycle.

### Per-skill audit matrix (all 50 skill directories)

The OMP column reports the current generated output in `packages/omp/ycc/skills/<skill>/`.
Leak counts come from a regex scan over every file in the skill dir.

Adaptation legend:

- **G** — generator rewrite
- **T** — OMP dispatch template / sentence table
- **S** — shared-reference or source change (runtime-neutral)
- **P** — declared question-policy default in the skill source
- **F** — documented fallback
- **—** — none

| Skill                 | Asks questions?                                                                                                                                     | Agent fan-out                                 | Background jobs                                                               | Worktree use                                                                  | Git / PR                                                 | Non-interactive flags                                                 | Current OMP output                                                                                                                                                  | Required adaptation                                                                                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_shared`             | yes: team-failure `AskUserQuestion` (agent-team-dispatch §8), batch-failure ask (standalone §9-10), branch-prep "stop and ask", goal-pairing caveat | defines standalone/review/agent-team dispatch | `run_in_background` prose; `ci-monitor.sh`/`release-ci-monitor.sh` long polls | defines contract: worktree-strategy, `setup-worktree.sh`, `worktree-paths.sh` | pr-guard, forge, ci-monitor, release-state, backport-lib | n/a                                                                   | leaks: `task(subagent_type=…)` ×2, `subagent_type` ×3, `run_in_background` ×5, `isolation:"worktree"` ×4, `.claude/worktrees` ×13, CLAUDECODE detection → `.claude` | G (root), T (standalone-dispatch, review-dispatch vocab), S (new question-policy.md, worktree-strategy OMP row + evidence, ci-monitoring wait note, OMPCODE detection, goal-pairing caveat) |
| `backport`            | yes: "Continue the cherry-pick and push?" (`--resolve`)                                                                                             | 1 × `backport-conflict-resolver`              | no                                                                            | yes: worktree per backport via `setup-worktree.sh`                            | cherry-pick, push, PR, labels                            | `--dry-run`, `--ci`, `--audit`, `--resolve`                           | `.claude/worktrees` ×1                                                                                                                                              | G; P (`confirm-destructive`: leave worktree, report, stop)                                                                                                                                  |
| `blueprint`           | yes: 5 GATEs + `AskUserQuestion`                                                                                                                    | refers to standalone-dispatch                 | no                                                                            | no                                                                            | no (hands off to init)                                   | `--dry-run`, `--update`                                               | `ask` mapped; no other leak                                                                                                                                         | P (`clarify`: print questions, stop)                                                                                                                                                        |
| `bundle-author`       | prose only                                                                                                                                          | no (names agents it scaffolds)                | no                                                                            | no                                                                            | no                                                       | `--dry-run`                                                           | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `bundle-release`      | yes: version-policy concern, notes review                                                                                                           | no                                            | no                                                                            | no                                                                            | version bump, publish                                    | `--dry-run`, `--no-publish`, `--skip-notes`                           | OK                                                                                                                                                                  | P (`confirm-publish`)                                                                                                                                                                       |
| `clean`               | yes: 2 × `AskUserQuestion` before delete                                                                                                            | 6 parallel cleanup agents                     | no                                                                            | no                                                                            | no                                                       | `--dry-run`, `--report-only`, `--safe-mode`                           | `ask` ×2; "MULTIPLE `task` calls"                                                                                                                                   | T (batch phrasing); P (`confirm-destructive` → report-only)                                                                                                                                 |
| `code-report`         | prose only                                                                                                                                          | no                                            | no                                                                            | no                                                                            | reads git                                                | `--dry-run`                                                           | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `code-review`         | yes: publish decision unless `--yes`                                                                                                                | parallel/team reviewers (review-dispatch)     | no                                                                            | yes: PR worktree on by default                                                | `gh pr review`, checkout                                 | `--yes`, `--save`, `--no-worktree`, `--parallel`, `--team`            | `.claude/worktrees` ×2; `--team` ×10                                                                                                                                | G; T (review-dispatch); P (`confirm-publish` → `--save` artifact only)                                                                                                                      |
| `compatibility-audit` | prose only                                                                                                                                          | no                                            | no                                                                            | no                                                                            | no                                                       | `--json`, `--dry-run`, `--fail-fast`, `--target=omp`                  | OK (target already includes omp)                                                                                                                                    | — (re-run after the matrix update)                                                                                                                                                          |
| `deep-research`       | prose only                                                                                                                                          | 4+ agents; `--team`                           | no                                                                            | no                                                                            | no                                                       | `--team`, `--dry-run`                                                 | `subagent_type` ×1; SendMessage ×3; `--team` ×13                                                                                                                    | T; F (`--team` fail-closed advisory names OMP)                                                                                                                                              |
| `feature-research`    | yes: "regenerate or enhance" existing spec                                                                                                          | 7 researchers; `--team`                       | "Monitor progress … `todo`"                                                   | no                                                                            | no                                                       | `--team`, `--dry-run`                                                 | `subagent_type` ×9; SendMessage ×27; `--team` ×22; "Monitor" via `todo`                                                                                             | T (`subagent_type=` → `agent=`, monitor → `wait`); P (`choose-path` → enhance); F (`--team`)                                                                                                |
| `formatters`          | yes: "Proceed with install?" when not `--yes`                                                                                                       | no                                            | no                                                                            | mentions only                                                                 | lefthook install, `git ls-files`                         | `--yes`, `--force`, `--ci`, `--dry-run`                               | `ask` mapped                                                                                                                                                        | P (`confirm-destructive` → abort install, print `--yes`)                                                                                                                                    |
| `frontend-design`     | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `frontend-patterns`   | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `git-cleanup`         | yes: `AskUserQuestion` summary; `--apply` still confirms                                                                                            | 1 × `git-cleanup` agent                       | no                                                                            | audits worktrees (`.claude/worktrees` managed root)                           | deletes branches/tags/PRs                                | `--dry-run` (default), `--apply`, `--report-only`                     | `.claude/worktrees` ×3                                                                                                                                              | G; P (`confirm-destructive`: headless `--apply` → dry-run report); S (also list `.omp/worktrees` and note `~/.omp/wt` is OMP-managed)                                                       |
| `git-workflow`        | prose ("ask the user" troubleshooting)                                                                                                              | parallel doc/commit agents                    | CI monitor (`--ci`)                                                           | no                                                                            | commit, push, PR                                         | `--commit`, `--push`, `--pr`, `--dry-run`, `--ci`, `--ci-yes`         | `subagent_type` ×1                                                                                                                                                  | T; S (ci-monitoring wait note)                                                                                                                                                              |
| `go-patterns`         | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK (4 "tool" hits are Go `Read(`/`Write(` code)                                                                                                                     | — (do not rewrite code)                                                                                                                                                                     |
| `go-testing`          | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `hooks-workflow`      | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | `--dry-run`, `--force`, `--target`                                    | OK (Claude matcher names are legitimate content)                                                                                                                    | —                                                                                                                                                                                           |
| `implement-plan`      | yes: team failure ask                                                                                                                               | implementor batches; `--team`                 | no                                                                            | yes: `setup-worktree.sh parent`, `move-plan-to-worktree.sh`                   | minimal                                                  | `--team`, `--dry-run`, `--no-worktree`                                | `subagent_type` ×4; `isolation` ×2; `.claude/worktrees` ×4; SendMessage ×5                                                                                          | G; T; P (`failure-recovery`)                                                                                                                                                                |
| `init`                | yes: confirm profile before writing; overwrite/merge prompt; migrate-rules "Apply?"                                                                 | 1 × `codebase-research-analyst` (>50 files)   | no                                                                            | `gitignore.tmpl` lists worktree roots                                         | optional `git init`                                      | `--dry-run`, `--force`, `--update`, …                                 | `.claude/worktrees` ×1; `subagent_type` ×1                                                                                                                          | G; T; S (`gitignore.tmpl` add `.omp/worktrees/`); P (`confirm-destructive`: skip existing files, print diff, stop)                                                                          |
| `orchestrate`         | prose                                                                                                                                               | heavy fan-out; `--team`                       | `run_in_background` ×1                                                        | yes: parallel tasks share one worktree                                        | minimal                                                  | `--team`, `--dry-run`, `--plan-only`, `--sequential`, `--no-worktree` | `subagent_type` ×8; `task(` ×7; `isolation` ×3; `.claude/worktrees` ×9; SendMessage ×19                                                                             | G; T (dispatch-playbook example blocks via sentence table); F (`--team`)                                                                                                                    |
| `parallel-plan`       | no                                                                                                                                                  | none standalone (`--team` only)               | no                                                                            | emits worktree annotations                                                    | no                                                       | `--team`, `--no-worktree`                                             | `--team` ×7                                                                                                                                                         | G (annotation root via §8.4); F (`--team`)                                                                                                                                                  |
| `plan`                | `AskUserQuestion` allowed (confirm plan)                                                                                                            | 3 personas (+2 enhanced); `--team`            | no                                                                            | annotations                                                                   | no                                                       | `--parallel`, `--team`, `--enhanced`, `--no-worktree`                 | `subagent_type` ×17; `.claude/worktrees` ×1                                                                                                                         | G; T; P (`checkpoint`: emit plan, stop before executing)                                                                                                                                    |
| `plan-workflow`       | yes: research checkpoint `AskUserQuestion`                                                                                                          | research/analysis/validation agents; `--team` | "Monitor progress … `todo`"                                                   | annotations                                                                   | no                                                       | `--no-checkpoint`, `--research-only`, `--plan-only`, `--team`         | `subagent_type` ×3; `task(` ×2; SendMessage ×47; `--team` ×66                                                                                                       | G; T; P (`checkpoint` → behave as `--no-checkpoint`)                                                                                                                                        |
| `pr-autofix`          | yes: per-comment apply/skip, dirty tree, branch switch                                                                                              | `--parallel` fixers                           | CI monitor                                                                    | no                                                                            | push, thread replies                                     | `--yes`, `--ci`, `--ci-confirm`, `--dry-run`, `--parallel`            | `ask` ×7                                                                                                                                                            | T; S (ci wait); P (`confirm-destructive` without `--yes` → dry-run table)                                                                                                                   |
| `prp-commit`          | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | commit                                                   | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `prp-implement`       | yes: batch failure; "parallel-capable, run parallel?"                                                                                               | implementor batches; `--team`                 | dev server `cmd &` in validation ref                                          | yes                                                                           | minimal                                                  | `--parallel`, `--team`, `--no-worktree`, `--dry-run`                  | `subagent_type` ×4; `.claude/worktrees` ×1                                                                                                                          | G; T; P (`choose-path` → sequential; `failure-recovery`); F (dev server: OMP `bash` `async: true` or a service `name`/`ready` [INFERENCE: trailing `&` behavior untested])                  |
| `prp-plan`            | yes: "STOP and ask" when vague; retry `--parallel`                                                                                                  | parallel researchers; `--team`                | "end the turn while results are pending"                                      | annotations                                                                   | no                                                       | `--parallel`, `--team`, `--enhanced`, `--no-worktree`                 | `subagent_type` ×15; `run_in_background` ×1; `task(` ×1                                                                                                             | G; T (sentence: "end the turn" → `wait`); P (`clarify`)                                                                                                                                     |
| `prp-pr`              | no                                                                                                                                                  | no                                            | CI monitor                                                                    | no                                                                            | PR create                                                | `--draft`, `--ci`, `--ci-yes`                                         | OK                                                                                                                                                                  | S (ci wait)                                                                                                                                                                                 |
| `prp-prd`             | yes: interview (`AskUserQuestion`)                                                                                                                  | refers to standalone-dispatch                 | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK (`ask`)                                                                                                                                                          | P (`clarify`)                                                                                                                                                                               |
| `prp-spec`            | yes: Phase 1 GATE                                                                                                                                   | refers to standalone-dispatch                 | no                                                                            | no                                                                            | no                                                       | `--ground`                                                            | OK (`ask`)                                                                                                                                                          | P (`clarify`)                                                                                                                                                                               |
| `python-patterns`     | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `python-testing`      | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `quick-fix`           | no                                                                                                                                                  | `--parallel` review-fixers                    | no                                                                            | no                                                                            | no                                                       | `--parallel`                                                          | `subagent_type` ×1                                                                                                                                                  | T                                                                                                                                                                                           |
| `quick-review`        | yes: review action (has text-mode fallback)                                                                                                         | `--parallel`/`--team` (review-dispatch)       | no                                                                            | passes `--no-worktree`                                                        | no                                                       | `--yes`, `--save`, `--write-and-apply`                                | `ask` ×2                                                                                                                                                            | T; P (`choose-path` → Save to file); S (fallback moves to question-policy)                                                                                                                  |
| `release-model`       | yes: up to 3 `AskUserQuestion`                                                                                                                      | no                                            | no                                                                            | no                                                                            | writes RELEASING.md, labels                              | `--yes`, `--model`, `--upgrade`, `--audit`                            | `ask` ×2                                                                                                                                                            | P (`confirm-publish` without `--yes` → proposal only)                                                                                                                                       |
| `releaser`            | yes: dirty tree STOP, unlabelled rows, notes review, CI auth                                                                                        | 1 × `release-fix-applier`                     | release CI monitor                                                            | no                                                                            | tags, releases, publish                                  | `--dry-run`, `--ci`, `--ci-yes`, `--publish`                          | `ask` ×1; `subagent_type` ×1                                                                                                                                        | T; S (ci wait); P (`confirm-publish`)                                                                                                                                                       |
| `research-to-issues`  | yes: ask path if not found                                                                                                                          | no                                            | no                                                                            | no                                                                            | creates issues                                           | `--dry-run`                                                           | `ask` ×1                                                                                                                                                            | P (`clarify` → stop)                                                                                                                                                                        |
| `resume-session`      | yes: wait for user (by design)                                                                                                                      | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | `ask` ×1                                                                                                                                                            | P (`checkpoint`: print brief and stop, which is already deterministic)                                                                                                                      |
| `review-fix`          | yes: batch validation failure                                                                                                                       | fixers parallel/`--team`                      | no                                                                            | yes                                                                           | commits                                                  | `--parallel`, `--team`, `--no-worktree`, `--dry-run`                  | `subagent_type` ×4; `isolation` ×4                                                                                                                                  | G; T; P (`failure-recovery`)                                                                                                                                                                |
| `rust-patterns`       | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `rust-testing`        | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `save-session`        | yes: "wait for confirmation" after writing                                                                                                          | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | P (`checkpoint`: file written, report the path)                                                                                                                                             |
| `shared-context`      | no                                                                                                                                                  | parallel analyzers; `--team`                  | no                                                                            | mentions                                                                      | no                                                       | `--team`, `--dry-run`                                                 | `--team` ×8                                                                                                                                                         | T; F (`--team`)                                                                                                                                                                             |
| `ts-patterns`         | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `ts-testing`          | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | no                                                       | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `visual-plan`         | prose: plan is the approval gate                                                                                                                    | no                                            | no ("background" hits are CSS)                                                | no                                                                            | no                                                       | `--share`                                                             | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `visual-recap`        | no                                                                                                                                                  | no                                            | no                                                                            | no                                                                            | reads diffs                                              | —                                                                     | OK                                                                                                                                                                  | —                                                                                                                                                                                           |
| `write-docs`          | prose                                                                                                                                               | 5 documentation agents                        | no                                                                            | no                                                                            | no                                                       | `--update`, `--fresh`, `--dry-run`                                    | "MULTIPLE `task` calls"                                                                                                                                             | T (batch phrasing)                                                                                                                                                                          |

Totals over `packages/omp/ycc/skills`:

| Leak                    | Count |
| ----------------------- | ----- |
| `subagent_type`         | 72    |
| `run_in_background`     | 7     |
| `isolation: "worktree"` | 13    |
| `task(` call syntax     | 13    |
| `/.claude/worktrees`    | 37    |
| `SendMessage`           | 127   |
| `--team`                | 287   |
| `CLAUDECODE`            | 2     |

### System Integration

#### Files to Create

- `ycc/skills/_shared/references/question-policy.md`: gate classes, detection rule, headless
  defaults and the text-mode fallback. Runtime-neutral, so every target ships it.
- `scripts/omp_templates/standalone-dispatch.md`: OMP-native §1-7 (task batch shape, `wait`,
  `agent://`, `proc://`, no `isolated`, `--team` abort).

#### Files to Modify

- `scripts/generate_omp_skills.py`:
  - `WORKTREE_ROOT_REWRITE` (`/.claude/worktrees` → `/.omp/worktrees`), applied in
    `body_rewrite` for markdown and scripts, with verbatim blocks protected. This also turns
    the `@YCC_DEFAULT_WORKTREE_ROOT@` marker line into `.omp`.
  - `render_omp_standalone_dispatch()`: template §1-7 + canonical §8-10 run through
    `body_rewrite`, failing if a section number is missing. Mirrors
    `generate_opencode_dispatch.render_standalone_dispatch_reference`.
  - `_DISPATCH_WORDING`: `subagent_type` → `agent`, `isolation: "worktree"` /
    `isolation="worktree"` → `isolated: true`.
  - `OMP_DISPATCH_SENTENCES`, a drift-checked table like `PATH_TOOL_SENTENCES`, for the
    `run_in_background` / "end the turn" / "Monitor progress … `todo`" sentences and the
    `dispatch-playbook.md` example blocks.
  - Team advisories ("Cursor and Codex bundles lack team tools" → "Cursor, Codex and OMP …").
- `scripts/test_generate_omp_skills.py`: cases for each rewrite, template rendering, sentence
  drift errors, verbatim-block preservation and the marker-line output.
- `scripts/validate-omp-skills.sh`: add a forbidden-semantics scan of `packages/omp` for
  `subagent_type|run_in_background|isolation: ?"worktree"|AskUserQuestion|TaskOutput|BashOutput|/\.claude/worktrees`.
  Allowlist `_shared/references/target-capability-matrix.md` (verbatim) and the
  `worktree-strategy.md` runtime table, with line-anchored entries.
- `scripts/test-worktree-roots.sh`: add `[omp]="${REPO_ROOT}/packages/omp/ycc/skills/_shared/scripts"`
  and `EXPECTED[omp]=.omp`. Agents-bundle cases: `OMPCODE=1 CLAUDECODE=1` → `.omp`, and
  `OMPCODE=1` alone → `.omp`. Add `-u OMPCODE` to `CLEAN_ENV`.
- `ycc/skills/_shared/scripts/worktree-paths.sh`, in `ycc_runtime_worktree_root`:
  `OMPCODE=1` → `omp`, consuming the `CLAUDECODE` marker it also sets. This affects the
  agents bundle only, because OMP loads `.agents/skills` (`src/discovery/agents.ts:30,177`).
- `ycc/skills/_shared/references/worktree-strategy.md`, inside the verbatim block: add the OMP
  row (`<repo-root>/.omp/worktrees/`, generator rewrite) and native-placement evidence (task
  isolation and `omp worktree` use `~/.omp/wt`; clone-first rewrite of literal
  `git worktree add`; `OMPCODE` marker).
- `ycc/skills/_shared/references/standalone-dispatch.md` §3: a neutral sentence saying that
  where the runtime offers a wait tool, use it rather than ending the turn. §7 names OMP.
- `ycc/skills/_shared/references/ci-monitoring.md`: long monitors may auto-background on OMP
  (>60 s); pass a sufficient `timeout`, or `wait` for the job, and never yield while it runs.
- `ycc/skills/_shared/references/goal-pairing.md`: caveat 2 points to `question-policy.md`.
- Asking skills, one "Questions" line each linking `question-policy.md` with the declared class
  and default (rows marked P): backport, blueprint, bundle-release, clean, code-review,
  feature-research, formatters, git-cleanup, implement-plan, init, plan, plan-workflow,
  pr-autofix, prp-implement, prp-plan, prp-prd, prp-spec, quick-review, release-model,
  releaser, research-to-issues, resume-session, review-fix, save-session. Shared:
  agent-team-dispatch, standalone-dispatch.
- `ycc/skills/init/templates/git/gitignore.tmpl` and `ycc/settings/rules/CLAUDE.md` worktree
  roots: add `.omp/worktrees/`.
- `ycc/skills/_shared/references/target-capability-matrix.md`: `WORKTREE:omp` → `partial`
  (tested `.omp/worktrees` via scripts, no native hook); update the `SKILLS:omp` and
  `AGENTS:omp` delegation notes. Re-run `compatibility-audit`.
- `ycc/agents/git-cleanup.md` (and any agent naming `AskUserQuestion`): subagents cannot ask,
  so return choices to the parent. This is source prose and benefits every target.
- `docs/internal/adr/0002-omp-runtime-contract.md` follow-up row and `CHANGELOG.md`.
- Regenerate all bundles (`./scripts/sync.sh`), because `worktree-paths.sh` and the shared
  references feed every target.

#### Configuration

None required from users. OMP defaults that the design relies on: `async.enabled=true`,
`task.batch=true`, `task.isolation.enabled=false`, `ask.timeout=0`, `worktree.clone=true`.

## UX Considerations

### User Workflows

#### Primary Workflow: headless fan-out

1. `omp -p "/ycc:plan-workflow my-feature"`.
2. Research agents are spawned in one `task` batch; the orchestrator calls `wait` until all
   jobs settle.
3. The checkpoint class has no `ask`, so the run continues as `--no-checkpoint` and the summary
   says so.
4. Planning output is written; the process exits only after every job is consumed.

#### Error Recovery Workflow

A batch fails in `-p`: the run stops (`failure-recovery`), leaves the feature worktree under
`.omp/worktrees/`, and prints the failing batch plus the resume command. In interactive mode
the same gate uses `ask`, with `recommended` = "fix manually and resume".

### UI Patterns

| Mode                                             | Question surface                   | Behavior                                |
| ------------------------------------------------ | ---------------------------------- | --------------------------------------- |
| OMP TUI                                          | `ask` (rich dialog)                | ask; `recommended` = declared default   |
| OMP `rpc-ui`                                     | `ask` via `select`/`editor` frames | ask                                     |
| OMP `-p`, `--mode json`, `--mode rpc`, subagents | none                               | declared default / stop with rerun hint |
| Cursor/Codex (no question tool, chat turn)       | text-mode fallback                 | print choices, wait for reply           |

### Accessibility Requirements

Non-interactive outputs must be plain text with the exact rerun command on one line, so that
CI logs and RPC hosts can parse them.

### Performance UX

One batched `task` call starts every agent at once (speculative launch,
`docs/tools/task.md:135`). `wait` adds no polling cost.

## Recommendations

### Implementation Approach

Implement in three slices:

1. **Worktree root and detection.** Generator rewrite, `worktree-paths.sh`, tests, gitignore
   template, worktree-strategy row and matrix cell.
2. **Dispatch projection.** Template, vocabulary and sentence table, validator scan.
3. **Question policy.** New shared reference plus per-skill declared defaults.

Slices 1 and 2 touch only the generator and `_shared`. Slice 3 is source prose. All three ship
in one PR with one regeneration.

### Technology Decisions

| Decision            | Recommendation                          | Rationale                                                                                                                |
| ------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Worktree root       | `<repo-root>/.omp/worktrees/`           | Matches the YAN-1111 per-runtime convention; `omp worktree clear` never touches it; isolation snapshots skip it (#16068) |
| Dispatch projection | Template + drift-checked sentence table | The opencode precedent; avoids per-skill branches; generation fails on source drift                                      |
| Question policy     | Runtime-neutral shared reference        | Fixes headless Claude/Cursor/Codex too; deterministic                                                                    |

### Quick Wins

- The worktree root rewrite and the OMPCODE marker: a few lines each, with an immediate,
  testable effect.
- The validator forbidden-semantics scan.

### Future Enhancements

- An OMP-native `--team` via `write agent://` peers (out of scope; it needs a tested
  lifecycle).
- Optionally honoring `isolated: true` for embarrassingly parallel, file-disjoint batches
  behind a flag.

## Risk Assessment

### Technical Risks

| Risk                                                                | Likelihood | Impact              | Mitigation                                                                                                                                                                       |
| ------------------------------------------------------------------- | ---------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A global `/.claude/worktrees` rewrite corrupts multi-runtime tables | Med        | Med                 | Verbatim-block markers (existing), validator allowlist, unit test                                                                                                                |
| `OMPCODE` precedence misdetects Claude nested inside OMP            | Low        | Low                 | Agents bundle only; `YCC_WORKTREE_ROOT` override; documented                                                                                                                     |
| The model ignores "call `wait`" and yields in `-p`                  | Med        | High (lost results) | Rule placed in §2/§3 of the dispatch reference; disk-artifact backstop still applies; a live smoke with a probe would need a model [INFERENCE: cannot be tested without a model] |
| Sentence-table drift on source edits                                | Med        | Low                 | Generation fails loudly (existing pattern)                                                                                                                                       |
| `subagent_type` → `agent` hits non-dispatch prose                   | Low        | Low                 | Code-span and roster regexes only; review the diff of the regenerated tree                                                                                                       |
| `render-template.py` reads stdin when not a TTY under OMP bash      | Low        | Med                 | [INFERENCE] OMP non-PTY stdin is empty or closed; verify during implementation                                                                                                   |
| A trailing `&` dev server in OMP bash                               | Med        | Low                 | Document `async: true` / service `name`; [INFERENCE] untested                                                                                                                    |

### Integration Challenges

- `worktree-paths.sh` is shared by every bundle; the agents-bundle tests must keep the
  existing claude/codex/opencode expectations.
- The capability-matrix cell change feeds `compatibility-audit`.

### Security Considerations

#### Critical — Hard Stops

- Never auto-approve destructive or publishing gates headless; require explicit flags
  (Business Rule 4). OMP's default `approvalMode: yolo` provides no backstop.

#### Warnings — Must Address

- OMP bash forces `GIT_TERMINAL_PROMPT=0`, `GIT_EDITOR=true`, `GH_PROMPT_DISABLED=1` and
  `CI=true`, so git and gh prompts fail closed. Skills must not rely on interactive git.
  `cherry-pick --continue` already uses `GIT_EDITOR=true`.

#### Advisories — Best Practices

- Keep deliverables in repo paths; `local://` is session-scoped and is lost on new sessions.

## Task Breakdown Preview

### Phase 1: Worktree root

- **Tasks:** generator rewrite + tests; `worktree-paths.sh` OMPCODE + `test-worktree-roots.sh`;
  worktree-strategy OMP row; gitignore template and rules; `WORKTREE:omp` cell.
- **Parallel:** generator and script work are independent.

### Phase 2: Dispatch projection

- **Tasks:** `omp_templates/standalone-dispatch.md` + renderer; vocabulary + sentence table;
  review-dispatch; validator scan; tests.
- **Dependencies:** Phase 1 for the §8 rewrite.

### Phase 3: Question policy

- **Tasks:** `question-policy.md`; 24 skill lines + 2 shared refs; quick-review fallback move;
  agent prose; ci-monitoring and goal-pairing notes; CHANGELOG/ADR; `sync.sh` regeneration.

## Decisions Needed

1. **OMP worktree root.** Options: (a) `<repo>/.omp/worktrees/`; (b) OMP native `~/.omp/wt`.
   **Recommend (a).** It is consistent with every other runtime, survives `omp worktree clear`,
   and is git-ignored by the template. (b) mixes ycc worktrees with OMP-owned sandboxes that
   `omp worktree clear` deletes.
2. **Detection precedence.** Options: (a) `OMPCODE=1` wins and consumes `CLAUDECODE`;
   (b) treat both as ambiguous → `.agents`. **Recommend (a).** OMP always sets both markers,
   so (b) would never detect OMP.
3. **Question policy placement.** Options: (a) runtime-neutral shared reference plus declared
   defaults in each source skill; (b) OMP-only generator injection. **Recommend (a).** It is
   deterministic on every target and has no per-runtime branches.
4. **Headless default for `choose-path`.** Options: (a) take `recommended` only when it is
   non-destructive; (b) always stop. **Recommend (a).** It keeps quick-review and
   feature-research useful in CI.
5. **Dispatch shape.** Options: (a) one `task` call with `tasks[]`; (b) many `task` calls in
   one message. **Recommend (a)**, with (b) as the documented fallback when `task.batch=false`.
6. **Pending results.** Options: (a) always `wait` before yielding; (b) end the turn as on
   Claude. **Recommend (a).** (b) was shown live to drop results in `-p`/JSON.
7. **`--team` on OMP.** Options: (a) fail closed, with advisories naming OMP; (b) strip team
   sections the way opencode does. **Recommend (a).** It is a small, tested change; (b) is a
   large projection with no OMP equivalent.
8. **Capitalized `Read/Write/Edit/Bash` in prose.** Options: (a) leave them; (b) map them in
   backticked spans only. **Recommend (a).** The names are understandable, and go-patterns and
   hooks-workflow hits are legitimate code or Claude content.
9. **Matrix verdict.** **Recommend** `WORKTREE:omp` → `partial`, only after
   `test-worktree-roots.sh` covers omp. Do not claim native parity.

## Research References

Evidence commands, run in a throwaway `HOME=/tmp/omp-yan1170.C9o7/home`:

- **RPC state.** `printf '{"id":"q1","type":"get_state"}\n' | omp --mode rpc|rpc-ui --no-session`
  shows the `dumpTools` lists.
- **Tool probe.** `omp [-p|--mode json -p|--mode rpc|--mode rpc-ui] --no-session -e probe.ts`,
  where `probe.ts` logs `pi.getActiveTools()` and `ctx.hasUI` on `session_start`.
- **`ask` in print mode.** `omp -p --model tokenhop/cc/claude-haiku-5-5 "Call the ask tool …"`
  → `NO_ASK_TOOL`.
- **Async `task` in JSON mode.** `omp --mode json -p … "spawn sonic … then wait"` →
  `wait` returns the result → `FINAL: SUBAGENT_DONE_42`.
- **Dropped result.** `omp --mode json -p … "spawn … never call wait"` →
  `AGENT_END {'yielded': True, 'awaitingAsyncWork': True}`, then exit without delivery.
- **Env markers.** `env -u CLAUDECODE -u OMPCODE … omp -p … "env | grep …"` →
  `AGENT=1 CI=true CLAUDECODE=1 OMPCODE=1 TERM=dumb`.
- **Worktree placement.** `omp worktree add -b feat/x <repo>/.omp/worktrees/proj-x` → clone
  falls back to a plain checkout, and the worktree is created. `omp worktree list` sees only
  `~/.omp/wt`.

Repo:

- `docs/internal/adr/0002-omp-runtime-contract.md`
- `docs/internal/spikes/omp-runtime-contract.md` §2.4, §2.8
- `ycc/skills/_shared/references/{standalone-dispatch,worktree-strategy,target-capability-matrix}.md`
- `scripts/generate_omp_skills.py`
- `scripts/generate_opencode_dispatch.py` (template precedent)
- `scripts/generate_agents_common.py:85-91` (marker-line precedent)
- `scripts/test-worktree-roots.sh`
