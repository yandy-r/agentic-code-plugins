# Question Policy — Shared Contract

## Contents

- Detection rule
- Gate classes
- Hard rules
- Declared defaults
- Text-mode fallback
- Runtime modes

Reference for every ycc skill that asks the user a question. Each asking skill declares
its gate class(es) and its default without a question tool in one **Questions** line that
links here. Fix the shared behavior here, not per skill.

## Detection rule

- The question tool is **available** only when `ask the user` (or the runtime's
  equivalent question tool) appears in your current tool list. Never call a question tool
  that is not in the list, and never treat its absence as an error.
- **Subagents never ask.** A subagent returns the open choices, the evidence and its
  recommended option to the parent, and the parent applies this policy.
- No question tool, but a chat turn exists (the user can reply): use the text-mode fallback
  below.
- No question tool and no chat turn (print, JSON, RPC, CI, or any headless run): apply the
  skill's declared default for the gate class. Never wait for input that cannot arrive.

## Gate classes

| Class                 | Typical gate                                                     | Interactive | Without a question tool                                                                                          |
| --------------------- | ---------------------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------- |
| `clarify`             | interviews, "STOP and ask" ambiguity gates, missing input path   | ask         | Print the open questions, write nothing, stop.                                                                   |
| `confirm-destructive` | delete, apply, install, overwrite, continue a cherry-pick + push | ask         | Do not act. Take the read-only path (report, dry-run, save) and print `rerun with <flag>`.                       |
| `confirm-publish`     | tag, release, publish, post a review, write release policy       | ask         | Stop before the side effect and print `rerun with <flag>`.                                                       |
| `choose-path`         | pick an action or execution mode                                 | ask         | Take the declared non-destructive option (save, sequential, enhance). If none exists, use `confirm-destructive`. |
| `checkpoint`          | review artifacts before continuing                               | ask         | Continue (artifacts are docs only) and report the checkpoint in the final summary.                               |
| `failure-recovery`    | batch or validation failure mid-run                              | ask         | Stop, preserve completed work, and print the failing batch plus the resume command. Never auto-retry or skip.    |

## Hard rules

1. Destructive and publishing gates never auto-approve without an explicit flag the skill
   documents (`--yes`, `--apply`, `--ci-yes`, `--publish`, …). Absence of a question tool is
   not consent.
2. The headless stop message is one plain-text line naming the exact rerun, for example:
   `Stopped before publish: no question tool. Rerun with --publish --confirm.`
3. The declared default, not the `recommended` marker, governs when no question tool
   exists. `recommended` is an interactive hint only and may differ from the declared
   default.
4. Never mark a destructive or publishing choice `recommended` in a `confirm-destructive` or
   `confirm-publish` question.
5. Auto-select on timeout is a user opt-in interactive behavior (for example OMP
   `ask.timeout > 0`, off by default). It picks the `recommended` option, which in a
   `choose-path` question may edit files (quick-review recommends "Apply fixes" or "Write
   file and apply fixes"). Rule 4 guarantees only that a timeout never confirms a
   destructive or publishing gate; it does not make a timed-out `choose-path` read-only.
6. A declared default never widens scope: it may only skip, stop, report, or take a
   non-destructive path.

## Declared defaults

Each asking skill carries one line near its arguments:

```
**Questions:** class `<class>`; without a question tool: <default>. See `.../question-policy.md`.
```

A skill with several gates lists each class with its default. A skill-specific default
overrides the class default above only by being narrower.

## Text-mode fallback

For chat runtimes without a question tool:

1. Print the question and the numbered choices, mark the `recommended` one, and end the turn.
2. Parse the next reply case-insensitively against the choice labels and the skill's
   documented synonyms.
3. Ambiguous reply: re-prompt once. Still ambiguous: take the least destructive choice
   (discard, cancel, or the read-only path).

## Runtime modes

| Mode                                                              | Question surface   | Behavior                               |
| ----------------------------------------------------------------- | ------------------ | -------------------------------------- |
| opencode interactive; OMP TUI and `--mode rpc-ui`              | question tool      | ask; mark one `recommended` hint       |
| OMP `-p`, `--mode json`, `--mode rpc`; any subagent; headless     | none               | declared default, or stop + rerun hint |
| Chat runtimes without a question tool (for example Cursor, Codex) | text-mode fallback | print choices, wait for the reply      |

OMP registers its question tool only when a UI is attached, so the same skill can see it in
the TUI and not in `-p`. Detect per run; never assume from the runtime name.
