# Bundle Version Policy

## Version Surfaces

The following files carry version information for the `ycc` bundle. Only hand-edited
files are modified directly; regenerated files are produced by running the listed
generator script.

| File                              | Kind        | Maintained by                      |
| --------------------------------- | ----------- | ---------------------------------- |
| `ycc/.claude-plugin/plugin.json`  | hand-edited | `bundle-release` `bump-version.sh` |
| `.claude-plugin/marketplace.json` | hand-edited | `bundle-release` `bump-version.sh` |
| `.codex-plugin/ycc/**`            | regenerated | `scripts/generate-codex-plugin.sh` |
| `.cursor-plugin/**`               | regenerated | `scripts/sync.sh --only cursor`    |
| `.opencode-plugin/**`             | regenerated | `scripts/sync.sh --only opencode`  |

## Parity Rule

`ycc/.claude-plugin/plugin.json:"version"` and both `"version"` fields inside
`.claude-plugin/marketplace.json` (top-level `metadata.version` and
`plugins[0].version`) MUST be identical at all times. `bundle-release/scripts/preflight.sh`
enforces this check before any release action proceeds. If the values diverge, fix them
manually in both hand-edited files before continuing.

## No Stale Version Literals in Docs

Hand-edited documentation files (`CLAUDE.md`, `AGENTS.md`, `README.md`, `docs/README.md`)
MUST NOT carry example snippets that hard-code a specific semver in a `version` key — they
drift silently as the bundle progresses through releases, leaving behind confusing
references to long-past versions.

When showing an example that would normally include a version, use the placeholder form
instead:

```
# Directory tree
plugin.json      # name: "ycc", version bumped by bundle-release

# JSON example
"version": "<managed by bundle-release>"
```

`bundle-release/scripts/preflight.sh` enforces this: it scans the hand-edited files for
patterns matching `[Vv]ersion[:=]["]?<semver>` and fails if any semver does not equal the
current bundle version. Prose mentions (e.g., "the 2.0.0 breaking change") are not
matched because the pattern requires a `version` key preceding the semver — those are
allowed in historical context.

Generated bundles (`.cursor-plugin/`, `.codex-plugin/`, `.opencode-plugin/`) and
historical dirs (`docs/releases/`, `docs/plans/`, `docs/research/`, `docs/internal/`)
are excluded from the scan.

## Semver Bump Rules

Use standard semver (`MAJOR.MINOR.PATCH`). Apply the first rule that matches:

**Major** — any of the following:

- Rename of a skill, command, or agent (changes the namespaced identifier consumers use)
- Removal of a skill, command, or agent
- Change to the `name` field in `plugin.json`
- Restructure of how the bundle is loaded or distributed

**Minor** — any of the following:

- New skill, command, or agent added
- Additive frontmatter fields on existing surfaces (no removals or renames)
- New shared helpers added under `_shared/` that do not break existing callers

**Patch** — any of the following:

- Bug fix inside an existing skill, command, or agent
- Documentation-only change (SKILL.md prose, reference docs, templates)
- Template refinement or whitespace/linter-only fix

Tie-breaker: when a change could reasonably justify two bump levels, prefer the more
conservative (higher) bump. When in doubt, bump minor rather than patch, and major
rather than minor.

## Never-Edit List

The following paths are fully regenerated. Do not hand-edit them. Make the
corresponding source change and rerun `./scripts/sync.sh` (or the individual generator
scripts) to propagate:

- `.cursor-plugin/**`
- `.codex-plugin/**`
- `.opencode-plugin/**`
- `docs/inventory.json`

## Pre-Bump Checklist

1. Confirm the working tree is clean (`git status` shows no uncommitted changes).
2. Run `bundle-release/scripts/preflight.sh` and verify it exits green.
3. Decide the semver bump level using the rules above.
4. Draft release notes using `release-notes-template.md` before publishing the tag.

See also: release-checklist.md, release-notes-template.md, AGENTS.md (Testing Changes).
