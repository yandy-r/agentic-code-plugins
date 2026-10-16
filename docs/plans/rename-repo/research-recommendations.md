# Rename Repo: Recommendations Synthesis

## Executive Summary

Ship one fixed-scope transformer: strict Bash wrapper, Python standard-library engine, exact-slug/context-aware replacements, full dry-run diff, preflight of all 12 source files, and byte/mode-preserving per-file atomic replacement. A standalone isolated fixture suite and explicit inventory/scope wiring are part of the deliverable, not optional follow-up work. Keep preparation behavior completely inactive until an operator invokes it; do not apply the rename in this checkout.

### Recommended Implementation Strategy

Keep wrapper/engine implementation separate from independent copied-fixture tests and validator wiring, so the two slices can run concurrently without shared file ownership. Integrate in the parent, capture the complete dry-run, then review adversarial boundaries before PR/CI/merge. Do not expand the writer to bare README branding or other prose: only anchored owner/repo references belong to this tool.

## Decisions settled across research

| Question                            | Decision                                                   | Why                                                                                 |
| ----------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Dry-run default or apply default?   | `--dry-run` is opt-in; absence applies; no `--apply`       | Established maintainer CLI convention and agreed contract.                          |
| Bash-only / Perl / Python?          | Thin Bash plus stdlib Python                               | Existing wrapper pattern, testability, no new dependency.                           |
| Root override for tests?            | None; physical script-derived root                         | Prevent ambient environment/cwd redirection; copy scripts to fixtures.              |
| Literal substring or word boundary? | Exact owner/repo with explicit context and repo boundaries | Substrings hit local paths; `\b` permits `-official`; dot suffixes need protection. |
| Recursive discovery?                | Fixed 12-file allowlist                                    | Reviewable scope and no generated/history/local-state writes.                       |
| Zero matches?                       | Successful no-op                                           | Safe repeat apply and already-transformed trees.                                    |
| Apply guarantees?                   | All-preflight-before-write, atomic each file               | Honest guarantee without unsupported cross-file rollback claims.                    |
| Regenerate automatically?           | Never                                                      | Generated outputs and hosting/remotes belong to later activation.                   |

## Highest-value evidence

- Adjacent official/plugin identities and legitimate repo source in `ycc/settings/settings.json:30-65` provide a strong positive/negative fixture.
- `.codex-plugin/config/config.toml:60` demonstrates why an owner-qualified substring alone is unsafe: it is inside a local trust path.
- `scripts/generate_codex_plugin.py:31` is the source for generated Codex URLs; generated manifests are not allowlist candidates.
- `scripts/validate.sh` inventory target already contains repo-meta tests; the rename suite requires explicit wiring because its filename is not release-test-discovered.
- `RELEASING.md:83` makes preparation versus owner-led reference flip explicit.

## Avoided scope

Do not rename directories, hosts, remotes, local trusted paths, worktree examples, the `ycc` namespace, or the Codex local catalog identity. Do not rewrite bare prose headings or historical issue links, list packages, publish npm, bump versions, run sync, or invent service verification. The later flip can explicitly review its separate prose and operational responsibilities without weakening this bounded tool.

## Implementation sequence

1. Lock the contract captured by the [spec](feature-spec.md) and [PRP plan](../../prps/plans/rename-repo.plan.md).
2. Concurrently implement wrapper/engine and independent fixture tests/validator wiring, without per-agent worktrees or mid-flight checks. Documentation synthesis is an independent slice.
3. Parent integrates, runs the planned checks once, and captures the complete real-checkout preview without applying it.
4. Conduct adversarial correctness/security review; fix and verify findings as appropriate.
5. Parent opens the PR with the reviewed diff and exercised evidence, handles CI/review, and merges only when required gates pass.

## Risk Assessment

Potential filesystem check/use races and arbitrary mid-apply I/O failures remain documented limits of the trusted-checkout/per-file-atomic design, not invitations to silently add a transactional framework. External APIs are not involved. Parent integration reports 20 fixture tests and 50 scope tests passed, lint and inventory/scope/practices validation passed, and a real preview of 24 replacements in 12 files with no protected strings in the diff. The README bare-name rewrite was removed; only anchored owner/repo references are rewritten. These parent-reported results reduce regression risk without claiming a real apply, full validation, hosting activation, or completed PR/CI/merge.
