<!-- Template used by bundle-release/scripts/draft-notes.sh. Placeholders ({{...}}) are replaced at generation time. Do not remove or rename them. -->

# Release {{VERSION}} — {{DATE}}

## Summary

TODO: 1–2 sentence release summary.

## Added

{{COMMITS_ADDED}}

## Changed

{{COMMITS_CHANGED}}

## Removed

{{COMMITS_REMOVED}}

## Fixed

{{COMMITS_FIXED}}

## Validation

- `./scripts/sync.sh` — OK
- `./scripts/validate.sh` — OK
- `python3 -m json.tool .claude-plugin/marketplace.json` — OK
- `python3 -m json.tool ycc/.claude-plugin/plugin.json` — OK

## Upgrade Notes

TODO: breaking changes, migration steps, or "no action required".

## Commit Log

{{COMMITS}}

---

Previous release: {{PREV_TAG}}
