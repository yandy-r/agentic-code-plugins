---
description: explicit /ycc:git-cleanup invocation defaults to audit-only and deletes nothing
tags: [behavior]
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, AskUserQuestion]
---

/ycc:git-cleanup --branches --worktrees Audit this repository for stale branches and worktrees and report what would be cleaned.
