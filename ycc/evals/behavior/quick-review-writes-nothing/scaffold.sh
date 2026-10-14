#!/usr/bin/env bash
set -euo pipefail
# Runs only with --scaffold, inside the empty per-run workspace (never this repo).
[[ ! -e .git ]] || { echo 'Refusing to seed an existing repository' >&2; exit 1; }
git init -q -b main .
git config user.email eval@example.invalid
git config user.name 'Eval Fixture'
mkdir -p src
printf 'export const greet = (name: string) => "Hello " + name;\n' > src/greet.ts
git add .
git commit -qm 'chore: seed'
printf 'export const greet = (name: string) => `Hello ${name}`;\n' > src/greet.ts
