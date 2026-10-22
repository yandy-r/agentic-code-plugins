---
globs:
- '**/*.go'
- '**/go.mod'
- '**/go.sum'
condition: .*
scope:
- tool:edit
- tool:write
interruptMode: never
---

# ycc golang rules

You edited a matching file. Read and apply these ycc rules:

- [ycc-golang-coding-style](rule://ycc-golang-coding-style): When working on Go files, apply formatting, types and idiomatic error handling.
- [ycc-golang-patterns](rule://ycc-golang-patterns): When designing Go interfaces, define small interfaces where they are consumed; use the go-patterns skill for idioms.
- [ycc-golang-security](rule://ycc-golang-security): When working on Go files, apply secret management, input boundaries and security checks.
- [ycc-golang-testing](rule://ycc-golang-testing): When working on Go files, apply test organization, framework usage and failure verification.
