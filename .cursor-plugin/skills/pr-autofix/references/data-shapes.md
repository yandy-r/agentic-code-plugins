# Data Shapes

Structures passed between `pr-autofix` phases: fetcher JSONL record, in-memory plan, and fixer agent inputs.

## JSONL record (Phase 1 output)

`scripts/fetch-pr-comments.sh` emits one record per comment of interest:

```json
{
  "source": "review_thread | review_comment | issue_comment",
  "thread_id": "PRRT_kw...", // null for issue_comment
  "comment_id": 12345,
  "comment_node_id": "PRRC_kw...", // null for issue_comment
  "author_login": "coderabbitai[bot]",
  "is_bot": true,
  "is_resolved": false,
  "is_outdated": false,
  "path": "src/auth.ts",
  "line": 42,
  "start_line": 40,
  "body": "..."
}
```

Materialize with `cat "$JSONL_FILE" | jq -s '.'`.

## In-memory plan (Phase 3 output)

```
plan = [
  { idx: 1, decision: "Apply",  thread_id, comment_id, path, line, body, author_login },
  { idx: 2, decision: "Skip",   reason: "Not in scope for this PR", thread_id, ... },
  { idx: 3, decision: "Defer",  thread_id: null, ... },
  ...
]
```

## Fixer agent input, Shape A (single comment)

```
COMMENT:
  Author:        <author_login>
  Severity:      <severity>
  Path:          <path>
  Line:          <line>
  Source:        review_thread | review_comment | issue_comment
  Thread ID:     <thread_id or "(top-level, no thread)">
  Sanitized body: |
    <sanitized body text — multi-line>

PROJECT TYPE-CHECK COMMAND: <detected typecheck cmd | SKIP (none detected)>
```

## Fixer agent input, Shape B (same-file group)

```
COMMENTS (same file `<path>`, sorted by line DESCENDING):
  1. Author=<a1> Severity=<s1> Line=<L1>
     Sanitized body: <multi-line>
  2. Author=<a2> Severity=<s2> Line=<L2>
     Sanitized body: <multi-line>
  ...

PROJECT TYPE-CHECK COMMAND: <...>
```

## Fixer agent output

Per comment: `STATUS: Fixed` or `STATUS: Failed`, with `CHANGES:` and, on failure, `BLOCKER` + `RECOMMENDATION`. Contract: `ycc/agents/pr-comment-fixer.md`.
