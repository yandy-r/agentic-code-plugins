#!/usr/bin/env bash
set -euo pipefail
# Runs only with --scaffold, inside the empty per-run workspace (never this repo).
[[ ! -e .git ]] || { echo 'Refusing to seed an existing repository' >&2; exit 1; }
git init -q -b main .
git config user.email eval@example.invalid
git config user.name 'Eval Fixture'
printf 'base\n' > seed.txt
git add seed.txt
git commit -qm 'chore: seed'
git checkout -qb stale/old-feature
printf 'old work\n' >> seed.txt
git commit -qam 'feat: old work' --date '2020-01-01T00:00:00'
git checkout -q main
git merge -q --no-ff stale/old-feature -m 'merge: stale/old-feature'
git branch stale/abandoned-spike
git worktree add -q scratch-worktree stale/abandoned-spike
