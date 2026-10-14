# ycc plugin evals

Eval suites for `claude plugin eval` (Claude Code ≥ 2.1.269; authored and baselined
on 2.1.299). Run them with `./scripts/eval.sh` — see
[CONTRIBUTING.md](../../CONTRIBUTING.md#plugin-evals). They make real model calls,
so they are not part of CI.

## Layout

```text
ycc/evals/
├── trigger/<case>/        # tags: [trigger]
│   ├── prompt.md          # frontmatter: limits + allowed_tools; body: the prompt
│   └── graders/*.md       # one grader per file
├── behavior/<case>/       # tags: [behavior]
│   ├── prompt.md
│   ├── case.yaml          # context.scaffold_script (seeds a scratch git repo)
│   ├── scaffold.sh        # runs only with --scaffold, in an empty workspace
│   └── graders/*.md
└── results/               # gitignored run output
```

The plugin manifest needs no `experimental.evals` key: `evals/` is the default
directory and `claude plugin validate ycc` accepts it.

## Trigger suite (36 cases)

Twelve skills × 3 cases: `plan`, `plan-workflow`, `prp-plan`, `code-review`,
`quick-review`, `review-fix`, `git-workflow`, `prp-commit`, `prp-pr`, `clean`,
`git-cleanup`, `go-patterns`.

- Two should-trigger cases per skill: grader `tool_used: Skill` with
  `input_match` on the skill name (namespaced `ycc:` form accepted).
- One near-miss per skill, named `<skill>-near-miss-<sibling>`: the prompt belongs
  to a sibling skill, so the grader asserts the target skill is **not** loaded
  (`min: 0`, `max: 0`). Loading the sibling or nothing both pass.

`clean` and `git-cleanup` carry `disable-model-invocation: true`, so the model
cannot select them on its own. Their should-trigger cases are expected to fail
until that policy changes; they record that a user must invoke them explicitly.

## Behavior suite (3 cases)

All graders are deterministic and cost nothing (no `llm`/`baseline`).

| Case                          | Gate                                  | Observable evidence                                                          |
| ----------------------------- | ------------------------------------- | ---------------------------------------------------------------------------- |
| `plan-waits-for-confirmation` | no edits before the user confirms     | no `Write`/`Edit`, no files created, `src/cli.ts` unchanged, asks to proceed |
| `git-cleanup-deletes-nothing` | dry-run by default                    | branch refs and worktree metadata still present, no `Write`/`Edit`           |
| `quick-review-writes-nothing` | inline review, no artifact by default | no `Write`/`Edit`, no files created, `src/greet.ts` unchanged                |

`Bash` is deliberately not granted: it needs a bubblewrap + `socat` sandbox, and
file/ref state is enough to prove the gates. Behavior cases therefore prove "no
file edits and refs intact", not "the command was never attempted".

## Writing a case

1. Phrase the prompt as a user would type it; do not name the skill.
2. Prefer `tool_used`, `file_exists`, and `regex` graders. Use `llm` only when no
   deterministic signal exists.
3. Near-miss cases need `min: 0` / `max: 0`; add `arm: both` if you run with
   baseline ablation.
4. Run it alone first: `./scripts/eval.sh --case <name>`.

## Follow-ups (out of scope for the first suite)

- Cross-model matrix (Haiku / Sonnet / Opus) once the suite is stable.
- A manually dispatched workflow once a CI credential and budget are agreed.
