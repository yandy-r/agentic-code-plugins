---
globs:
- '**/*.ts'
- '**/*.tsx'
- '**/*.js'
- '**/*.jsx'
condition: .*
scope:
- tool:edit
- tool:write
interruptMode: never
---

# ycc typescript rules

You edited a matching file. Read and apply these ycc rules:

- [ycc-typescript-coding-style](rule://ycc-typescript-coding-style): When working on TypeScript/JavaScript files, apply formatting, types and idiomatic error handling.
- [ycc-typescript-patterns](rule://ycc-typescript-patterns): When handling external TypeScript/JavaScript input, validate at runtime boundaries; use the ts-patterns skill for idioms.
- [ycc-typescript-security](rule://ycc-typescript-security): When working on TypeScript/JavaScript files, apply secret management, input boundaries and security checks.
- [ycc-typescript-testing](rule://ycc-typescript-testing): When working on TypeScript/JavaScript files, apply test organization, framework usage and failure verification.
