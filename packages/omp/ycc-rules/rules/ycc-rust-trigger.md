---
globs:
- '**/*.rs'
condition: .*
scope:
- tool:edit
- tool:write
interruptMode: never
---

# ycc rust rules

You edited a matching file. Read and apply these ycc rules:

- [ycc-rust-coding-style](rule://ycc-rust-coding-style): When working on Rust files, apply formatting, types and idiomatic error handling.
- [ycc-rust-patterns](rule://ycc-rust-patterns): When designing Rust enums, traits or response types, match enums exhaustively and apply sealed traits; use the rust-patterns skill.
- [ycc-rust-security](rule://ycc-rust-security): When working on Rust files, apply secret management, input boundaries and security checks.
- [ycc-rust-testing](rule://ycc-rust-testing): When working on Rust files, apply test organization, framework usage and failure verification.
