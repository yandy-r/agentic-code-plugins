// commitlint.config.cjs — Conventional Commits 1.0.0 for ystack
//
// Types and rules mirror the policy documented in CLAUDE.md. Scope is
// intentionally free-form to support the repo's existing scope taxonomy
// (e.g., `docs(internal):`, `feat(ycc-skill):`, `build(bundles):`).
//
// The config-conventional defaults already cover every type in CLAUDE.md;
// we only override header length and subject casing to match repo style.

/** @type {import('@commitlint/types').UserConfig} */
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'header-max-length': [2, 'always', 100],
    'subject-case': [2, 'never', ['pascal-case', 'upper-case']],
    'body-max-line-length': [0],
    'footer-max-line-length': [0],
  },
};
