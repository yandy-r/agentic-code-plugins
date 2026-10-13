---
description: 'Interactive, whole-project source-of-truth spec generator. Takes a raw
  software idea, interrogates it through a multi-gate process (Foundation → Grounding
  → Scope → Tech Stack → Architecture → Generate), and writes a durable project charter
  at docs/blueprint.md — vision, users, scope, tech-stack decision, architecture,
  modules, NFRs, milestones, risks. Its machine-readable Bootstrap section then drives
  project bootstrap (code init, CI, formatters) by orchestrating /init and /formatters.
  Use when the user asks to "create a project spec", "write a software spec", "whole-project
  spec", "source of truth spec", "scaffold/bootstrap a new software project from an
  idea", "project charter/blueprint", or says "/blueprint". Sits UPSTREAM of prp-prd/prp-spec
  — those are per-feature; this is the whole software. Usage: [project idea] (blank
  = start with questions) [--update] [--dry-run]'
---

Use the skill tool to load the `blueprint` skill, then follow its instructions with these arguments:

$ARGUMENTS
