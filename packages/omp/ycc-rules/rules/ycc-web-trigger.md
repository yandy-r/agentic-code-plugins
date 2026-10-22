---
globs:
- '**/*.html'
- '**/*.css'
- '**/*.scss'
- '**/*.sass'
- '**/*.less'
- '**/*.js'
- '**/*.mjs'
- '**/*.cjs'
- '**/*.ts'
- '**/*.mts'
- '**/*.cts'
- '**/*.jsx'
- '**/*.tsx'
- '**/*.vue'
- '**/*.svelte'
condition: .*
scope:
- tool:edit
- tool:write
interruptMode: never
---

# ycc web rules

You edited a matching file. Read and apply these ycc rules:

- [ycc-web-coding-style](rule://ycc-web-coding-style): When editing web frontend files, apply feature-based file layout, CSS design tokens, compositor-only animation, semantic HTML and naming conventions.
- [ycc-web-design-quality](rule://ycc-web-design-quality): When working on web frontend files, apply anti-template design-quality constraints.
- [ycc-web-patterns](rule://ycc-web-patterns): When building web UI, apply compound components, render-props/slots, container-presentational split, separated state types, URL state and data-fetching patterns.
- [ycc-web-performance](rule://ycc-web-performance): When working on web frontend files, apply loading strategies, asset budgets and Core Web Vitals.
- [ycc-web-security](rule://ycc-web-security): When editing web frontend code or headers, apply CSP, XSS prevention, third-party script, HTTPS header and form-protection checks.
- [ycc-web-testing](rule://ycc-web-testing): When testing web frontends, prioritize visual regression, accessibility, performance, cross-browser and responsive checks, then E2E and unit tests.
