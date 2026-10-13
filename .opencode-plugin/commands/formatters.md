---
description: 'Use this skill when the user asks to "initialize formatters", "bootstrap
  linting", "add lint and format scripts", "set up prettier / biome / ruff / clippy
  / golangci-lint / shellcheck", "add a Makefile lint target", "install a style bundle",
  "wire a pre-commit hook for linting", or any request to stand up a best-practices
  lint/format environment in a project. Profiles the target, installs a self-contained
  `scripts/style.sh` bundle, configures per-language tool files, injects runnable
  aliases (package.json / Makefile / justfile), appends a "Linting & Formatting" section
  to the project docs, and optionally wires CI and pre-commit hooks. Idempotent via
  a managed manifest — safe to re-run with `--sync`. Usage: [--dry-run] [--force]
  [--yes] [--sync] [--copy] [--ci] [--no-autofix] [--hooks] [--no-aliases] [--no-docs]
  [--target=<dir>] [--profile=<lang>] [--rust] [--ts] [--python] [--go] [--docs] [--shell]
  [--all]'
---

Use the skill tool to load the `formatters` skill, then follow its instructions with these arguments:

$ARGUMENTS
