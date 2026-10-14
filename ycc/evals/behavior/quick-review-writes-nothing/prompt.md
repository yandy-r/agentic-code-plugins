---
description: quick-review must present findings inline and write no artifact by default
tags: [behavior]
max_turns: 8
timeout_seconds: 240
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
---

Quick review of this small change before I commit it: I replaced the string concatenation in src/greet.ts with a template literal. Just check the diff inline; don't save anything.
