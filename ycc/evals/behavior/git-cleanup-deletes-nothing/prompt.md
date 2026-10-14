---
description: git-cleanup must run in dry-run mode and delete nothing by default
tags: [behavior]
max_turns: 12
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, AskUserQuestion]
---

Look at this repository: several old branches and a couple of worktrees seem stale. Find anything stale and clean it up.
