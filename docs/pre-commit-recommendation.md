# Pre-commit Hooks — Recommendation for ystack

Pre-commit hooks catch formatting errors, lint violations, and broken tests before they reach CI, shortening the feedback loop for every contributor.

---

## TypeScript / Node — lefthook or husky + lint-staged (recommended)

**Option A — lefthook** (`npm install -D lefthook`):

```yaml
pre-commit:
  commands:
    lint:
      glob: '*.{ts,tsx,js,jsx}'
      run: npm run lint {staged_files}
pre-push:
  commands:
    test:
      run: npm test
```

**Option B — husky + lint-staged** (`npm add -D husky lint-staged`):

`.lintstagedrc.json`: `{ "*.{ts,tsx,js,jsx}": ["npm run lint"] }`

`.husky/pre-push`: `npm test`

## Python — pre-commit.com (recommended)

Install: `pip install pre-commit` then `pre-commit install`.

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: []
```

Pre-push: add a `.git/hooks/pre-push` that runs `npm test`, or manage via lefthook alongside pre-commit.com.

---

Install manually — the init workflow deliberately does NOT install hooks automatically. Review the snippet for your ecosystem above, adapt paths and commands to your project layout, then commit the hook config alongside your code. Refer to `CLAUDE.md` for this project's commit message rules and branching conventions.
