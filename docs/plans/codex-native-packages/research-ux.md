# UX Research — Codex Native Package Install (`ycc`, `ycc-mcp`)

## Executive Summary

**Current state (verified on codex-cli 0.161.0, hermetic-local probe).** The repo
already ships the Codex-preferred catalog at `.agents/plugins/marketplace.json`
(name `local-ycc-plugins`, entry `ycc`, local source `./plugins/ycc`). That wins
over `.claude-plugin/marketplace.json` per spike and is **today discoverable**:
`codex plugin marketplace add <repo>` returns
`{"marketplaceName": "local-ycc-plugins", ...}`; `plugin list` and
`plugin list --available --json` show `ycc@local-ycc-plugins`, `installPolicy: AVAILABLE`;
`plugin add ycc@local-ycc-plugins` **fails** with
`plugin source path is not a directory: .../plugins/ycc` (`plugins/` absent; real
payload `.codex-plugin/ycc`). So today’s fork UX is “catalog found, package listed,
install fails with a path message,” while `install.sh` drives a _user-level_ merge
into `~/.agents/plugins/marketplace.json` with `./.agents/plugins/ycc` or git-subdir
and works. Any edit to the committed repo catalog is therefore user-visible now,
before any flip.

**Critical gate finding — `listed: false` does not hide a catalog entry in Codex.**
Verified same harness: `policy.installation: NOT_AVAILABLE` entries **still appear**
in human `plugin list` and in `plugin list --available --json`
(`"installPolicy": "NOT_AVAILABLE"`); only `plugin add` is blocked with
`plugin \`ycc-mcp\` is not available for install in marketplace \`ycc\``(duplicated`Caused by:`). An empty`plugins: []`catalog is accepted (`empty-ycc`add/list OK)
but the marketplace *name/identity* is still discoverable. Consequence: emitting`name: "ycc"`+ new entries (or`NOT_AVAILABLE`placeholders) into`.agents/plugins/marketplace.json`on`main`changes`plugin list`, desktop plugin directory, and
`codex plugin marketplace add yandy-r/claude-plugins` output before v6 — a violation
of RELEASING.md’s unwired-work rule. The supported UX is the separate opt-in
native tree until the flip.

**Migration collision (verified).** With both `local-ycc-plugins` and `ycc`
marketplaces configured, Codex happily installs **both** `ycc@local-ycc-plugins`
and `ycc@ycc` (plus `ycc-mcp@ycc`) as distinct `pluginId`s: distinct caches
`plugins/cache/{local-ycc-plugins,ycc}/ycc/5.3.0`, distinct
`[plugins."ycc@..."] enabled = true` and `[marketplaces.*]` keys in `config.toml`.
No dedupe, no warning. Bare `codex plugin add ycc` → `plugin requires --marketplace unless passed as <plugin>@<marketplace>`.
Caches are snapshots: success text prints “Added plugin `ycc` … Installed plugin root:
…/cache/ycc/ycc/5.3.0”. [INFERENCE: duplicate skill registrations may surface in the
runtime skill inventory; the installer already treats “its skills will appear twice”
as a bug for file slices (`targets/codex.sh:391`).]

**Two must-fix contradictions before any public wording:**

1. The current generated payload **bundles MCP into `ycc`** (`plugin.json`
   `"mcpServers": "./.mcp.json"`; generator copies `mcp-configs/mcp.json` whole).
   The target split is inverted until generation changes: `ycc` must have no MCP
   reference, `ycc-mcp` MCP-only. Docs must never promise “install `ycc` _or_
   `ycc-mcp`” until proven, and the hermetic harness must assert omission, not
   just add-success.
2. The `${XERO_CLIENT_ID}` / `${XERO_CLIENT_SECRET}` passes through unchanged from
   Claude-shaped `mcp-configs/mcp.json:19–20` into plugin `.mcp.json`; the
   **installer** TOML path instead translates `"${X}"` → `env_vars` pass-through.
   In a clean env the live probe showed `codex mcp list` rendering
   `XERO_CLIENT_ID=*****, XERO_CLIENT_SECRET=*****` — a five-star mask **whether**
   the env declares the var; `--json` returns raw literal `"${XERO_CLIENT_ID}"`
   with `env_vars: []`. The human renderer hides “is it set?” from the diagnostic.
   Whether Codex expands `${...}` inside plugin `.mcp.json` `env` at spawn (i.e.
   is it equivalent to `env_vars`?) is unproven — see Open Questions; until proven,
   “missing XERO secret” behavior is unknown and must not be documented.

**Recommendation in one line:** keep the in-repo catalog and legacy `.codex-plugin/ycc`
byte-stable while Codex `ycc`/`ycc-mcp` are `listed: false`; generate the future
`ycc@ycc` / `ycc-mcp@ycc` tree only via an explicit `--native-output <DIR>` into a
non-repo root, from `ycc/` source via the existing `write_all(dest)` machinery,
and prove fork installs + split + dedupe there.

---

## User Workflows

### WF1 — New fork installs native packages (post-flip target)

```bash
codex plugin marketplace add yandy-r/claude-plugins --json   # expect {"marketplaceName": "ycc"}
codex plugin list --available --json                          # expect pluginId "ycc@ycc", "ycc-mcp@ycc"
codex plugin add ycc@ycc                                      # skills + _shared, no MCP
codex plugin add ycc-mcp@ycc                                  # MCP servers only
# restart Codex / new session; composer picks up ycc: namespace skills
```

Branch points where users get lost today and the design must absorb:

- **Marketplace ≠ plugin.** Users conflate “add the repo” with “install ycc”.
  `codex plugin marketplace add owner/repo` clones a snapshot into
  `$CODEX_HOME/.tmp/marketplaces/<name>/`; `plugin add` then copies from that
  snapshot into `plugins/cache/<marketplace>/<plugin>/<version>/`. Two commands
  are required; the first succeeds with nothing user-visible until `plugin list`.
  Docs must show both, with expected JSON fields (`marketplaceName`, `alreadyAdded`).
- **Snapshot semantics.** After `marketplace add`, the package bytes are
  frozen. Upstream skills changes need `codex plugin marketplace upgrade`, not
  `git pull`. Local-directory marketplaces behave differently (resolve from the
  live tree) — docs must not assume contributors’ live-tree mental model.
- **Restart required.** `plugin add` prints the cache path and nothing about
  restart; repo `install.sh` ends with “Restart Codex” (`targets/codex.sh:394/402`).
  Every success block in native docs must end with “start a new Codex session.”
- **Which package(s)?** The split implies three valid profiles: skills-only
  (`ycc`), MCP-only (`ycc-mcp`), both. CLI `plugin list` shows name/version/source
  path — **no descriptions** — so the catalog `plugins[]` ordering and the package
  `interface.shortDescription` (desktop picker) carry the whole “what do I pick?”
  burden. Order `ycc` first; write short descriptions that say “skills only, no
  MCP servers” vs “MCP servers only, no skills”. See naming below.

### WF2 — Existing `install.sh` / `local-ycc-plugins` user migrates (v6 flip)

Today such a user may have any combination of: `ycc@local-ycc-plugins` installed
from `~/.agents/plugins/marketplace.json` (install.sh-merged `local` `./.agents/plugins/ycc`
or repo-mode `git-subdir`); symlinks `~/.codex/plugins/ycc` and `~/.agents/plugins/ycc`
→ repo `.codex-plugin/ycc`; standalone slice copies in `~/.codex/skills/<name>`
(+ `_shared`) or consolidated `~/.agents/skills` copies; TOML MCP servers merged
by the `mcp` installer step; custom agents in `~/.codex/agents/*.toml` (install.sh-only
in v6). The research recommendation (`docs/research/agentic-code-plugins/recommendation.md:120`)
proposes an `install.sh migrate --target codex` command that removes
`ycc@local-ycc-plugins` + symlinks, adds the repo marketplace, and installs
`ycc@ycc` + `ycc-mcp@ycc`. **No `migrate` command exists** (`install.sh:442–447`:
install/sync/remove (+ cli/completion/list-mcps)). Without ordering, the user who
installs native first and never removes legacy gets duplicates for as long as both
are enabled — and there is no warning (verified collision above).

Required migration UX (whether delivered as a script or a doc runbook):

1. **Detect and print a plan before removing anything.** Present state in one
   table: which of `ycc@local-ycc-plugins`, `ycc@ycc`, `ycc-mcp@ycc` are
   installed; slice copies found in `~/.codex/skills` / `~/.agents/skills`;
   standalone user-edited copies that must _not_ be deleted (`install_slices.py`
   ownership model: identical → keep; unowned/foreign → refuse without `--force`;
   owned-but-retired → delete; state in `installed-units.json`). “Detect-and-print”
   mirrors steps.sh’s duplicate prompt (choices 1/2/3) — extend that UX, do not
   invent a second one. Non-interactive runs warn and proceed today
   (`steps.sh:264–368`); that leniency is dangerous for dedupe (see Error Handling).
2. **Remove old before adding new, and prove the gap is closed.** The safe order
   is remove legacy plugin → remove owned slice/consolidated ycc copies → add
   `ycc` marketplace → add packages. Between steps, show `codex plugin list`
   output so the user sees the duplicate resolve.
3. **Preserve what native cannot own.** Agents (`~/.codex/agents/*.toml`),
   `AGENTS.md`, rules/config stay install.sh-managed; migration copy must state
   “your agents and rules stay; only skills/MCP change ownership.” The MCP
   double-registration risk could be similar [INFERENCE; name-collision behavior
   was not probed]: migration must either remove the managed `[mcp_servers.*]`
   entries it wrote (merger state knows them) or warn of a collision. Never
   silently delete user-added servers.
4. **Rename the _user-level_ marketplace name carefully.** `codex_marketplace.py`
   preserves any existing marketplace `name` at merge time; `codex.sh` derives the
   selector from it, but the cache path is hard-coded
   `cache/local-ycc-plugins/ycc` (`targets/codex.sh:53`). [INFERENCE] After a
   rename, cleanup/legacy-cache code keyed to the old name can miss snapshots, and
   enabling entries persist in `config.toml` (`[marketplaces.local-ycc-plugins]`,
   `[plugins."ycc@local-ycc-plugins"]`) — migration must verify these keys, not
   just the JSON entry. `codex_marketplace.py:94–106` currently removes only entries
   named `ycc` (not a future `ycc-mcp`), and hard-codes the scaffold name.
   Note a rename of the **repo** catalog from `local-ycc-plugins` → `ycc` does not
   touch the user-level file at all; these are two different catalogs sharing one
   string — say so explicitly in migration docs.

### WF3 — Contributor develops skills in the repo (dominant workflow today)

Local `install.sh` symlinks make generated bundle edits live, but `codex plugin add`
snapshots on top, so contributors refresh by rerunning `install.sh sync --target codex
--intent base` (`targets/codex.sh:402–403`); moving/renaming the repo breaks links
and needs `install --only base` (`:404`). Post-flip, the documented contributor
loop must answer “which of my two installs wins?”: marketplace-added local
directories vs cache snapshots vs slice copies. At minimum keep installer
behaviour byte-identical until the flip (this task’s gate) and, at the flip, have
the installer print which ownership path it left active. The `--native-output`
mode must **not** write into the repo root and must not regenerate the legacy
bundle, or contributor refresh loops will thrash state.

### WF4 — Install MCP-only, or skills-only

Valid and core to the split. UX hazards:

- `ycc-mcp@ycc` with no skills gives the user tool results for workflows that only
  exist as YCC skills pointing at those MCP servers; the user gets servers but no
  recipes. Docs should phrase `ycc-mcp` as _for users of other prompts/agents who
  only want the managed server set_.
- `ycc@ycc` with no MCP: skills that call GitHub/Linear MCP tools fail at runtime
  with missing-tool behaviour. That is a product decision, not an error — but the
  `interface.defaultPrompt` examples on `ycc` must not promise MCP-dependent
  outcomes it does not ship. Today’s `defaultPrompt` items are planning/review/
  orchestration (OK); keep them that way.
- Neither package depends on the other (Codex has no dependency field; ADR: all
  non-Claude runtimes ship self-contained). Docs must not imply “install ycc and
  MCP follows” (that was the monolith behaviour users will expect from the legacy
  bundle, which today bundles `.mcp.json`). The legacy-bundles-MCP fact makes the
  split a **breaking expectation change** for existing users; the migration note
  must headline it: “v6: MCP moved from ycc to ycc-mcp; install both to keep today’s
  behaviour.”

### WF5 — Sparse checkout (power user / org policy)

`marketplace add … --sparse .agents/plugins` alone lets `marketplace add` and
`plugin list --available` succeed but `plugin add` fails `missing plugin.json`
(spike §1.2). Both payload dirs are required:

```bash
codex plugin marketplace add yandy-r/claude-plugins \
  --sparse .agents/plugins --sparse .codex-plugin/ycc --sparse .codex-plugin/ycc-mcp
```

Silent mis-sparse is undetectable until install; the failure names neither the
missing path nor the flag. Include this verbatim block in post-flip docs (never
link users to the sparse form in pre-flip docs).

---

## UI/UX Best Practices

### Naming: `ycc@ycc` vs `ycc-mcp@ycc`

- **Selector math:** `<plugin>@<marketplace>`. `ycc@ycc` reads like a typo to
  newcomers (“ycc at ycc”) but is the documented compat pattern (Claude has the
  same shape: entry `name@marketplace-name`) and is the ADR’s decision. `ycc-mcp@ycc`
  is self-describing. The marketplace segment is not decorative: dropping it
  errors, verified: `plugin requires --marketplace unless passed as <plugin>@<marketplace>`.
- **The three names used for this product** — repository (`claude-plugins` →
  `agentic-code-plugins`), marketplace (`ycc`), package (`ycc`, `ycc-mcp`) — never
  appear in the same CLI output together. At flip docs need exactly one diagram
  line per doc: “`claude-plugins` is the repo; the bundled catalog is `ycc`;
  install commands are `ycc@ycc` and `ycc-mcp@ycc`.” Forbid prose use of `acc`
  (ADR: branding only).
- **Old name `local-ycc-plugins` continues to resolve from the user file** after
  the repo catalog renames; users who autocomplete `ycc@local…` keep installing
  legacy forever unless credentials are migrated. Docs/migration must instruct
  uninstall-first; the product cannot namespace-guard this (Codex treats them as
  separate marketplaces, verified).
- **Namespace unaffected:** skills remain `ycc:` in v6 (ADR). Set explicit
  expectation: “installing `ycc-mcp` does not change skill names; installing
  `ycc` keeps `ycc:skill-name`.” Manifest `name` == catalog `name` for both
  packages (`ycc` / `ycc-mcp`) to avoid manifest-vs-entry confusion (Claude’s
  documented #1 marketplace footgun, and Codex list renders entry names).

### Display metadata is the description channel (CLI shows none)

CLI `plugin list` shows only name/status/version/source path. So:

- Set per-package `interface.displayName`/`shortDescription` that make the split
  legible in Codex Desktop picker: e.g. `YCC` — “Planning, implementation, and
  review skills for Codex. No MCP servers.” and `YCC MCP` — “Managed MCP servers
  (GitHub, Linear, …). No skills.” Today’s `ycc` shortDescription (“Planning,
  implementation, review, and workflow skills for Codex.”) is fine but add the
  “No MCP” clause post-split — users of the legacy bundle expect servers inside.
- Order catalog entries `ycc` then `ycc-mcp`; catalog order is listing order.
- Keep `interface.displayName` = “YCC” on the marketplace; the marketplace-picker
  label comes from top-level `interface.displayName` (docs). Today the user-level
  file says “Local YCC Plugins” — the flip also renames the picker label; mention
  in migration notes (“the picker now shows YCC, not Local YCC Plugins”).

### `--native-output` flag naming (the pre-flip generation switch)

Recommend **`--native-output <DIR>`** over `--output-dir` and `--preview-native`:

- It is a _write_, not a preview: `--dry-run` (existing, prints “Would write …”)
  is the preview verb. A `--preview-native` write flag invites the misread that
  nothing lands on disk. Keep one read-only affordance: `--native-output` +
  `--dry-run` composes naturally.
- `--output-dir` is generic (and file-grained `--output` already means “write
  JSON to PATH” in `build_package_graph.py:152`), inviting scripts to point it at
  the repo root. The flag there is not “choose a directory” but “emit the
  _native_ model elsewhere” — name it after the model.
- Contract wording (help text and errors): “Write the unlisted native-package
  tree (`ycc@ycc`, `ycc-mcp@ycc`) under DIR, which must be outside this repository.
  Does not modify `.codex-plugin/` or `.agents/`.” Error messages from the guard
  must name both paths and why (a repo-root output would be discovered by Codex).
- `--check` must compare the _same profile it would write_ (`run_check()` currently
  temp-writes and diffs against the repo, lines 141–155) — running `--check` with
  a native output must not compare a native tree byte-wise to the legacy tree and
  report eternal “drift”; define check-per-profile. [INFERENCE: drift UX today
  prints `missing in repo:` / `drift:` per path and points at
  `generate-codex-plugin.sh` — keep that actionable template per profile.]
- **Do not mint a second skill-copy pipeline.** `--native-output` re-generates
  skills from `ycc/` into `<DIR>/.codex-plugin/ycc/skills` through the existing
  skills `write_all(dest)`; copying the checked-in `.codex-plugin/ycc` tree would
  ship whatever stale tree is on disk (including its `.mcp.json`) and defeat the
  split — regenerate, then assert `ycc` manifest has no `mcpServers` key and no
  `.mcp.json` file exists under `ycc/`, while `ycc-mcp/` has manifest + `.mcp.json`.

### Pre-flip default output may grow `ycc-mcp` bytes — is that hidden enough?

Generating an unlisted `.codex-plugin/ycc-mcp/` payload _in-repo_ by default does
not consult any catalog: Codex discovers only cataloged entries, and
`validate-codex-plugin.sh` hardcodes the one payload today. From a _runtime_
standpoint it is invisible. From a UX standpoint it is semi-visible: contributors
browsing the repo will find a package that installs nothing; keep its README-less
manifests accurate and do not reference it from docs. It also risks the legacy
validator passing while the new payload rots — the validator scope question
(extend JSON-lint to `ycc-mcp` files as soon as they generate by default) belongs
to the implementer; the acceptance criterion “validator passes” should cover
every generated JSON file.

### `listed` flag routing (what flips automatically)

Today both Codex `ycc` and `ycc-mcp` are `listed: false` (`ycc/settings/packages.json:28,86`);
RELEASING says `listed` is generator input only, yet generator consumption is
explicitly “pending” (ADR:137–138). UX requirements on the _eventual_ routing:

- Flip **atomically per runtime-catalog**, never piecemeal: default generation
  switches to the native profile only when the complete Codex catalog set is
  `listed: true`. If `ycc@codex` flipped alone, one sync would rename the
  marketplace to `ycc` while `ycc-mcp` stayed unlisted — a marketplace called
  `ycc` shipping only skills, breaking every line of migration copy. Partial
  state should fail generation with a message naming the inconsistent flags,
  not emit a half-native catalog.
- `ycc-hooks` is `status: "excluded"` (line 141): the routing must treat excluded
  ≠ unlisted-included. Generating a `ycc-hooks` catalog entry even as
  `NOT_AVAILABLE` would _display_ it (verified) — must not happen until YAN-1149.
- The flip must be observable: after the listing PR, `marketplace add` returns
  `"marketplaceName": "ycc"`; before, `"local-ycc-plugins"`. The fork-install
  harness should assert the name string, not just exit 0.

### Success, progress, and undo affordances

- Every installer doc block should pair install with undo: `codex plugin remove
ycc-mcp@ycc` (observed: “Removed plugin `ycc-mcp` from marketplace `ycc`.”) and
  `codex plugin marketplace remove ycc`. Verified sharp edge: removing a
  marketplace leaves installed packages installed and enabled (`ycc@local-ycc-plugins`
  still `installed, enabled` after marketplace removal; orphaned cache dirs
  remain). Docs must sequence: remove plugins, then remove marketplace; never
  present marketplace-remove as an uninstall.
- Native `plugin add` has no `--force`/undo of enablement; disabling without
  removing is `[plugins."ycc@ycc"] enabled = false` in user `~/.codex/config.toml`
  (docs: project-level `.codex/config.toml` on trusted projects only). Worth one
  “temporarily disable” recipe in post-flip docs; pre-flip, saying nothing is
  correct.

---

## Error Handling

Errors observed on codex-cli 0.161.0 (harness transcripts + spike §1) and what the
user needs beside them. Docs should include a “you saw X → do Y” table post-flip;
none of these strings can be changed by this repo (they are Codex’s).

| Observed condition                        | Literal message (verbatim)                                                                                                              | What user needs                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Catalog path wrong (today’s repo catalog) | `Error: plugin source path is not a directory: <abs>/plugins/ycc` + identical `Caused by:`                                              | Names a path that exists nowhere in current docs; user assumes checkout corruption. Interim: (a) make sure `--native-output` never emits `./plugins/ycc` (generate `.codex-plugin/ycc`); (b) while unlisted, do not “fix” the committed catalog path in isolation — fixing it makes a broken-but-harmless entry _installable_ pre-flip (user-visible). Decision belongs to the flip PR.                                                                       |
| Missing selector                          | `plugin requires --marketplace unless passed as <plugin>@<marketplace>`                                                                 | Actionable already. Docs always show fully qualified `ycc@ycc` / `ycc-mcp@ycc`, never bare names.                                                                                                                                                                                                                                                                                                                                                             |
| Wrong plugin in right marketplace         | `Error: plugin \`nope\` was not found in marketplace \`local-ycc-plugins\``                                                             | No list of available names. Doc recovery: run `codex plugin list --available --json` and copy `pluginId`.                                                                                                                                                                                                                                                                                                                                                     |
| Right plugin, wrong marketplace           | `Error: plugin \`ycc\` was not found in marketplace \`ycc\``(before`ycc` added)                                                         | Indistinguishable from “marketplace never added.” Doc recovery: `codex plugin marketplace list` first; if `ycc` absent, add it. Note message says “was not found in marketplace `ycc`” even when no such marketplace exists.                                                                                                                                                                                                                                  |
| Install against `NOT_AVAILABLE`           | `plugin \`ycc-mcp\` is not available for install in marketplace \`ycc\``×2 (`Caused by:`)                                               | Proof `NOT_AVAILABLE` is a display-not-hide state. Never rely on it pre-flip.                                                                                                                                                                                                                                                                                                                                                                                 |
| Sparse missing payload                    | `Error: missing plugin.json` (spike)                                                                                                    | Fixed by adding payload `--sparse` paths; doc verbatim block (WF5).                                                                                                                                                                                                                                                                                                                                                                                           |
| Bad marketplace source                    | `Error: invalid marketplace source format; expected owner/repo, a git URL, or a local marketplace path` (spike file-url case)           | Fine as-is; docs use `owner/repo` form only.                                                                                                                                                                                                                                                                                                                                                                                                                  |
| installer plugin-add failure              | installer warns: `codex plugin add ycc@<name> returned non-zero — check 'codex plugin list'` and **continues** (`targets/codex.sh:142`) | A “sync complete” followed by a stale/missing plugin. Native migration UX must make this a hard stop before deleting legacy state, else migration strands the user with neither plugin. Minimal rule: never remove legacy until `codex plugin list` shows the native IDs `installed`.                                                                                                                                                                         |
| Old Codex, no plugin CLI                  | installer warns and writes legacy flat cache (`targets/codex.sh:134`, documented in install/codex.md:87–91)                             | Silent downgrade class: user believes native installed. Keep the loud warning; post-flip docs state the `codex-cli >= 0.160` floor up front (matches `test-codex-marketplace-spike.sh:11–12`).                                                                                                                                                                                                                                                                |
| Stale real dirs at link targets           | `Stale Codex plugin copy at … Remove it with: rm -rf …` exits 1 (`targets/codex.sh:307–317`)                                            | Good pattern (names path + exact fix). `--native-output` guard + future native validation should match this tone.                                                                                                                                                                                                                                                                                                                                             |
| Duplicate slices + plugin                 | end-of-run warning only, after mutation (`targets/codex.sh:391`)                                                                        | The safe default for native migration should be detect-before-write: if plugin and standalone ycc skills will coexist, stop (interactive prompt exists for `~/.agents/skills` in steps.sh; the non-TTY “warn and proceed” branch must not be inherited by an irreversible dedupe/migration step). [INFERENCE]                                                                                                                                                 |
| Missing MCP credentials                   | **No message at install.** `codex mcp list` masks as `*****` regardless of env presence; `--json` echoes raw `${XERO_CLIENT_ID}`.       | Negative-space failure: users cannot tell “unset” from “set,” nor whether `${…}` even expands for plugin-delivered stdio servers. Until proven, `ycc-mcp` listing gate should include a live-harness case: env unset → what happens when Codex spawns `xero` (session-block? degraded? literal string to server?). Document only that result. Note other servers’ auth state _is_ surfaced (`Not logged in` for http OAuth servers; `unsupported` for stdio). |

**Split-validation failure is the subtle one.** `scripts/validate-codex-plugin.sh`
validates exactly one payload’s two JSON files and the catalog, and `plugin list`
does not print whether a package carries MCP. So a regression that re-bundles MCP
into `ycc` — or drops skills from `ycc` — sails through today’s gate while `plugin add`
still “succeeds.” The native profile needs _negative_ assertions: `ycc` manifest has
no `mcpServers`; no `ycc/.mcp.json`; `ycc-mcp` manifest references `.mcp.json` and
declares no `skills:` path; installed cache for `ycc-mcp` contains no `skills/`
tree. Re-running `--native-output <DIR>` into a populated directory must also
**prune** any pre-existing `ycc/.mcp.json` (and `--check` must detect unexpected
extra files, not only missing/drifted ones — `compare_files()` at
`generate_codex_plugin.py:128–138` only iterates `files` today, so a leftover
`.mcp.json` in `ycc/` would pass `--check` silently).

---

## Performance UX

- **Install latency [INFERENCE from probe + sizes]:** a local probe sequence
  including three `plugin add` calls (two 3.7 MB payloads with 49 `SKILL.md` +
  40 `shared/` files each and one `.mcp.json`-only add) completed in 1.29 s wall.
  `marketplace add` on a Git source clones the snapshot (dominant cost; sparse
  shrinks it). Per-command UX needs no spinner work; the long pole is Git clone
  into `.tmp/marketplaces/`. `--json` outputs are small and script-checkable.
- **Duplicate installs can waste model context, not just disk [INFERENCE].** If
  Codex offers both enabled skill trees, two enabled copies of 49 skills would
  produce duplicate descriptions every session. User-visible symptoms could be
  repeated entries and unpredictable agent skill choice, same class as Claude’s
  no-dedupe hook finding for duplicate `WorktreeCreate` («settings + plugin
  copies both run»). This repo already treats “appears twice” as a bug for slices
  (`targets/codex.sh:391`). Dedupe is
  therefore a _performance_ gate, not cosmetic: RELEASING’s flip criteria already
  require “per-target migration/dedupe tests.”
- **Discovery cost:** `codex plugin list` (default) already printed “not
  installed” rows for configured marketplaces in the probe; `--available` only
  affects _JSON_ (`available[]`) — help says “Include uninstalled marketplace
  plugins in the JSON output.” Human-friendly docs: plain `codex plugin list`
  to browse; `--available --json` to script/verify. Machine-verify harnesses
  should assert on the JSON (spike harness does exactly this,
  `test-codex-marketplace-spike.sh:194–202`).
- **Cache snapshots vs live trees:** fork installs copy to
  `plugins/cache/<market>/<name>/<version>/` once; re-adding the same plugin
  refreshes it (installer comment, `targets/codex.sh:130–131`). Docs should tell
  users updating after a new release is `codex plugin marketplace upgrade ycc`
  then re-`plugin add` — not `install.sh sync`. [INFERENCE that re-add is the
  refresh verb for native; it is observed for `local-ycc-plugins`.]
- **Server set size:** the proposed `ycc-mcp` ships 10 servers if it reuses
  `mcp-configs/mcp.json` (`github`, `context7`, `stripe`, `xero`, `linear`,
  `linear-personal`, `vercel`, `railway`, `playwright`, `openaiDeveloperDocs`).
  Seven are remote HTTP; the probe showed `Not logged in` auth state for six of
  seven (`openaiDeveloperDocs` was `unsupported`). [INFERENCE: auth is lazy /
  on first use; exact timing was not probed.] `codex mcp list` is the visible
  inventory check; TOML/plugin same-name collision behavior remains an Open
  Question — see WF2.3.

---

## Competitive Analysis

- **Claude Code (this repo’s primary surface).** Same selector grammar
  `<entry>@<marketplace>`; official docs say “most failed installs come from a
  relative path written from the wrong directory, or an entry name that differs
  from `plugin.json` name,” and warn that a missing-dir path passes `validate`
  but fails at `install` with `Source path does not exist`. The Codex analog is
  exact (verified above). Adopt these two doc rules verbatim: paths from
  marketplace root; entry name == manifest name. Claude gets an in-session
  `/plugin` panel with descriptions and a component inventory (`Skills (1)
hello`); Codex CLI gets none — which is _why_ `interface.*` metadata matters
  more here. Claude marketplaces can embed dependency meta (planned `ycc-all`);
  Codex cannot — the “install both” burden is Codex-only friction this split owns.
- **Codex Desktop / ChatGPT plugin directory.** Reads repo (`.agents/...`), legacy
  (`.claude-plugin/...`), and personal (`~/.agents/...`) marketplaces as picker
  sources; installs to `~/.codex/plugins/cache/$MARKETPLACE_NAME/$PLUGIN_NAME/$VERSION/`
  (local plugins: version `local` in desktop docs; CLI probe stamped `5.3.0` —
  local-marketplace behaviour differs per surface/profile [INFERENCE]). A committed
  repo catalog therefore could also surface for desktop users who merely open
  the repo [INFERENCE; desktop behavior was not probed], which strengthens the
  case against emitting native to the repo root pre-flip.
- **Cursor.** Marketplace registration is interactive-only (no non-interactive
  install, ADR table) — Codex’s pure-CLI flow is strictly better for forks;
  matching Cursor’s copy (“install through the UI”) would waste that. Keep the
  Codex flow script-first, with JSON assertions.
- **Current `install.sh` (the bar to meet).** One command syncs skills+agents+
  rules+MCP with ownership tracking, interactive dedupe prompts, and restart
  notices. Native fork install deliberately covers _less_ (no agents, no rules).
  Public docs must state the delta in the same table as the install commands, or
  users will read “native install available” as “full YCC,” then file “agents
  missing” issues. AGENTS.md/config parity stays installer-only in v6 (ADR).

---

## Recommendations

1. **(Gate) Do not emit the native catalog into the repo tree while
   `listed: false`.** Keep `.agents/plugins/marketplace.json` and default
   generation byte-stable until the flip PR. `NOT_AVAILABLE` still displays;
   zero-entry changes marketplace identity; both are user-visible (verified).
   Emit native only via `--native-output <DIR>` (name over `--output-dir`/
   `--preview-native`), guard `DIR` outside the repo root, and refuse if `DIR`
   is `$CODEX_HOME` or an existing user marketplace root — those are discovery
   surfaces too. [INFERENCE: presence of a ycc catalog at a user root via the
   generator would be a shadow-install; the generator is a build tool, fork
   installs are the proof.]
2. **(Correctness-before-copy) Fix the split at generation:** `ycc` manifest with
   no `mcpServers`, no copied `.mcp.json`, skills generated **from `ycc/` source**
   into the native tree using existing `write_all(dest)`; `ycc-mcp` manifest +
   `.mcp.json` only. Then extend `validate-codex-plugin.sh`’s _profile-aware_
   negative assertions (§ Error Handling) to the native tree. Before v6 public
   wording, decide: `.mcp.json` for `ycc-mcp` ships Claude-shaped `type`/`${…}`
   placeholders (`mcp-configs/mcp.json`) — the exact bytes accepted by Codex
   0.161 in this probe — while the TOML install path uses translated
   `env_vars`/Codex overrides (incl. `bearer_token_env_var`, per-tool
   `approval_mode`, `generate_codex_mcp.py:5–15`). Choosing which bytes the
   native plugin ships is a functional divergence, not UX sugar: whichever is
   chosen, `codex mcp get xero` must be shown in the harness transcript.
3. **(Naming) Ship exactly:** marketplace `ycc` (displayName “YCC”), entries
   `ycc` → `./.codex-plugin/ycc`, `ycc-mcp` → `./.codex-plugin/ycc-mcp`;
   manifests `name` identical to entries; split-disclosing shortDescriptions;
   `ycc`’s `defaultPrompt` stays skill-only. Never document a bare
   `plugin add ycc` form; always qualified.
4. **(Migration) Do not publish flip docs before a tested dedupe path exists**
   (RELEASING already gates on “migration/dedupe tests”). Whether it ships as
   `install.sh migrate --target codex` (recommendation.md proposal; does not
   exist today) or an ordered doc runbook, it must: print detected state first;
   remove `ycc@local-ycc-plugins` and owned slice/consolidated skill copies
   _before_ enabling native; keep agents/`AGENTS.md`/rules untouched; resolve
   TOML-vs-plugin MCP duplicates; verify with `codex plugin list --available --json`
   that exactly one skills owner and one MCP owner are enabled; hard-fail (not
   warn) if a `plugin add` in the sequence fails, before removing legacy.
5. **(Docs, pre-flip) Write nothing user-facing** linking `ycc@ycc` /
   `ycc-mcp@ycc`, `--native-output` fork instructions, or migration steps —
   `docs/install/*` stays unwired until the flip (RELEASING:84). The existing
   codex guide stays public and installer-first. (Existing contradiction in
   `docs/install/codex.md:21–26` vs `:48` — `./.agents/plugins/ycc` vs
   “registers … `./plugins/ycc`” and stale cache wording — is pre-existing rot;
   fixing the _doc_ wording is safe but out of scope for the native packages
   feature; flag, don’t bundle.)
6. **(Docs, flip PR) Replacement wording for `docs/install/codex.md`:**
   lead with the breaking-expectation line (“v6: MCP moved from `ycc` to
   `ycc-mcp`”), then fork-install block, sparse block (both payload paths),
   profile table (skills-only / mcp-only / both / full `install.sh` incl. agents),
   restart line, error table (six rows above), remove/disable recipes,
   “`codex mcp list` to check connections” line — and replace every
   `ycc@local-ycc-plugins` reference (currently also `install.sh:328–332` help
   text and `targets/codex.sh:394/402` restart notices; those strings are
   installer UX that must flip in lockstep, per ADR roadmap: keep
   `local-ycc-plugins` working until then).
7. **(Harness / acceptance UX) Extend the spike harness pattern to the native
   tree and capture receipts a user would send in a bug report:**
   `marketplace add --json` (assert `marketplaceName == "ycc"`), `plugin list
--available --json` (assert pluginIds exactly `{ycc@ycc, ycc-mcp@ycc}`, both
   `installPolicy: "AVAILABLE"`), both `plugin add`s, cache-marker byte checks
   (a skill marker present under `ycc` cache; absent under `ycc-mcp`;
   `.mcp.json` present under `ycc-mcp`, absent under `ycc`), plus negative cases:
   current-repo-catalog control (pre-flip outputs unchanged — catches accidental
   leakage of native into repo root), bare-selector error, wrong-marketplace
   error, sparse-missing-payload error. Keep the harness git-fixture hermetic;
   treat public GitHub `owner/repo` transport as [INFERENCE] until proven (spike
   explicitly did not test it).

---

## Open Questions

1. **Does Codex expand `${VAR}` inside plugin `.mcp.json` `env` values at spawn
   time?** Probe shows the value is stored and masked (`*****`) while JSON
   round-trips it literally; only a live session probe spawning the `xero`
   stdio server (with vars set vs. unset) distinguishes (a) env replaced by
   value, (b) literal `${XERO_CLIENT_ID}` passed to the server, (c) empty
   string. If not (a), `ycc-mcp` needs Codex-shaped bytes (`env_vars` equivalent)
   — decide before listing; this blocks honest wording about “missing XERO vars.”
   Related: do unset-env stdio servers block session start or degrade silently?
2. **Desktop picker behaviour with an unchosen repo catalog.** When a user opens
   this repo in Codex Desktop today, does the plugins directory show
   `local-ycc-plugins`/`ycc` (and its broken path) by default? Docs say repo
   marketplaces are picker sources; not probed headlessly. The answer affects
   whether today’s committed catalog is already a desktop bug report generator.
3. **What does Codex do when repo and user marketplaces end up with the same
   `name`** (post-flip repo `ycc` + a user file someone edited to `ycc`)? Probe
   showed two `local-ycc-plugins` rows allowed simultaneously (path-keyed). Does
   `plugin add ycc@ycc` pick first/last/ambiguous-error? Worth a harness case
   (dup-name, different sources) since `codex_marketplace.py` preserves arbitrary
   existing names.
4. **Version stamping for local-directory marketplaces:** desktop docs say local
   plugins cache under version `local`; CLI probe used manifest version `5.3.0`.
   Which applies to a Git-snapshot marketplace with `local` _plugin sources_?
   Affects cache-invalidation wording in migration/update docs.
5. **Should `ycc-mcp`’s manifest declare `skills` at all** (e.g. an
   `onboardingSkill` setup workflow per docs)? UX benefit: a setup skill could
   walk users through per-server OAuth + env vars post-install. But that makes
   “MCP-only” inaccurate (one skill rides along). Decide explicitly; if adopted,
   qualify copy (“MCP servers + one setup skill”). No such flow exists today.
6. **Does JSON-marketplace renaming orphan user `config.toml` keys?** Verified
   marketplace-remove leaves installed+enabled plugins. [INFERENCE] The inverse
   (rename in `~/.agents/plugins/marketplace.json`) leaves stale
   `[marketplaces.local-ycc-plugins]` snapshots plus `plugins."ycc@local-ycc-plugins"`
   enabled rows that keep serving the legacy cache after the file says `ycc`.
   Needs the migration harness to answer; until then migration copy cannot
   promise “rename is enough.”

---

_Evidence: codex-cli 0.161.0 hermetic probes in fresh `HOME`/`CODEX_HOME` (deleted
after use) against this worktree and a native-shaped fixture; `docs/internal/spikes/codex-marketplace.md`;
`docs/internal/adr/0001-package-model-and-versioning.md`; RELEASING.md v6 gates;
repo sources cited inline. Upstream: <https://developers.openai.com/plugins/build/plugins>,
<https://learn.chatgpt.com/docs/extend/mcp?surface=cli>,
<https://code.claude.com/docs/en/plugins/create-marketplace>. Unverified claims are
marked [INFERENCE]. No skills invoked; no implementation changes made._
