---
globs:
- '**/*.py'
- '**/*.pyi'
condition: .*
scope:
- tool:edit
- tool:write
interruptMode: never
---

# ycc python rules

You edited a matching file. Read and apply these ycc rules:

- [ycc-python-coding-style](rule://ycc-python-coding-style): When working on Python files, apply formatting, types and idiomatic error handling.
- [ycc-python-patterns](rule://ycc-python-patterns): When managing Python resources or iteration, use context managers and generators; use the python-patterns skill for idioms.
- [ycc-python-security](rule://ycc-python-security): When working on Python files, apply secret management, input boundaries and security checks.
- [ycc-python-testing](rule://ycc-python-testing): When working on Python files, apply test organization, framework usage and failure verification.
