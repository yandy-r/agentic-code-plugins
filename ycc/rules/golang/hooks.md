---
paths:
  - '**/*.go'
  - '**/go.mod'
  - '**/go.sum'
description: When working on Go files, apply hook configuration and formatter/linter
  recommendations.
---

# Go Hooks

## PostToolUse Hooks

Configure in `~/.claude/settings.json`:

- **gofmt/goimports**: Auto-format `.go` files after edit
- **go vet**: Run static analysis after editing `.go` files
- **staticcheck**: Run extended static checks on modified packages
