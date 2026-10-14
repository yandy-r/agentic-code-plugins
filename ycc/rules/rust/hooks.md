---
paths:
  - '**/*.rs'
  - '**/Cargo.toml'
description: When working on Rust files, apply hook configuration and formatter/linter
  recommendations.
---

# Rust Hooks

## PostToolUse Hooks

Configure in `~/.claude/settings.json`:

- **cargo fmt**: Auto-format `.rs` files after edit
- **cargo clippy**: Run lint checks after editing Rust files
- **cargo check**: Verify compilation after changes (faster than `cargo build`)
