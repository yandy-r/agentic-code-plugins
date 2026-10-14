# Project Profile Heuristics

## Contents

- Detection Signal Table
- Mixed Stack Handling
- Existing-Artifact Detection Keys
- Command detection notes
- Empty Repo Fallback

How `profile-project.sh` maps repository signals to a language/ecosystem profile.

---

## Detection Signal Table

Commands are listed for the case where their signal exists (see _Command detection notes_);
without the signal the key is `unknown` and templates render `# not detected`.

| Detected file/pattern             | `primary_language` | `package_manager` | `test_cmd`           | `lint_cmd`                | `build_cmd`       |
| --------------------------------- | ------------------ | ----------------- | -------------------- | ------------------------- | ----------------- |
| `Cargo.toml`                      | `rust`             | `cargo`           | `cargo test`         | `cargo clippy`            | `cargo build`     |
| `go.mod`                          | `go`               | `go`              | `go test ./...`      | `go vet ./...`            | `go build ./...`  |
| `pyproject.toml` + `uv.lock`      | `python`           | `uv`              | `uv run pytest`      | `uv run ruff check .`     | `uv build`        |
| `pyproject.toml` + `poetry.lock`  | `python`           | `poetry`          | `poetry run pytest`  | `poetry run ruff check .` | `poetry build`    |
| `pyproject.toml` + `hatch.toml`   | `python`           | `hatch`           | `hatch run test`     | `hatch run lint`          | `hatch build`     |
| `pyproject.toml` (no lock)        | `python`           | `pip`             | `pytest`             | `ruff check .`            | _(none detected)_ |
| `requirements.txt`                | `python`           | `pip`             | `pytest`             | `ruff check .`            | _(none detected)_ |
| `package.json` + `pnpm-lock.yaml` | `typescript`       | `pnpm`            | `pnpm test`          | `pnpm lint`               | `pnpm build`      |
| `package.json` + `yarn.lock`      | `typescript`       | `yarn`            | `yarn test`          | `yarn lint`               | `yarn build`      |
| `package.json` + `bun.lock`       | `typescript`       | `bun`             | `bun test`           | `bun lint`                | `bun build`       |
| `package.json` (npm fallback)     | `typescript`       | `npm`             | `npm test`           | `npm run lint`            | `npm run build`   |
| `tsconfig.json` (no package.json) | `typescript`       | `unknown`         | _(unknown)_          | _(unknown)_               | _(unknown)_       |
| `*.tf` files present              | `terraform`        | `terraform`       | `terraform validate` | `tflint`                  | `terraform plan`  |

`typescript` covers both plain JS and TS projects; the script checks for `tsconfig.json`
to set `secondary_languages=typescript` when `package.json` is the primary signal.

---

## Mixed Stack Handling

When multiple language manifests coexist, the script ranks by file precedence:

1. `Cargo.toml` (Rust beats all others)
2. `go.mod`
3. `pyproject.toml` / `requirements.txt`
4. `package.json`
5. `*.tf`

The highest-ranking manifest sets `primary_language`. All others populate
`secondary_languages` as a comma-separated list. Example:

```
primary_language=rust
secondary_languages=typescript
```

The profile key emitted is the `primary_language` value. Templates and commit-lint
configuration use `primary_language` to pick language-specific blocks.

---

## Existing-Artifact Detection Keys

These keys let the skill trigger update/merge semantics per artifact:

| Key                       | Meaning                                                                                                                      |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `has_claude_md`           | `CLAUDE.md` exists at the project root                                                                                       |
| `has_agents_md`           | `AGENTS.md` exists at the project root                                                                                       |
| `agents_md_is_pointer`    | True if the existing `AGENTS.md` is ≤40 lines and references `CLAUDE.md` (legacy inverted pointer — offer `--migrate-rules`) |
| `has_cursor_rules`        | Either `.cursor/rules/` or legacy `.cursorrules` exists                                                                      |
| `has_legacy_cursorrules`  | `.cursorrules` (legacy single-file) exists — triggers migration under `--update`                                             |
| `has_modern_cursor_rules` | `.cursor/rules/` directory exists                                                                                            |
| `has_issue_templates`     | `.github/ISSUE_TEMPLATE/` contains at least one `.yml`/`.yaml`/`.md` file                                                    |
| `has_pr_template`         | `pull_request_template.md` exists at a standard path                                                                         |
| `has_gitmessage`          | `.gitmessage` file exists at the project root                                                                                |
| `has_gitignore`           | `.gitignore` file exists at the project root                                                                                 |
| `has_commitlint_config`   | Any `commitlint.config.*` or `.commitlintrc*` exists                                                                         |
| `has_lefthook_config`     | `lefthook.yml`, `lefthook.yaml`, `.lefthook.yml`, `.lefthook.yaml`, or `.lefthook/` exists                                   |
| `has_releasing_md`        | `RELEASING.md` exists at the project root — the project already has a release model                                          |

When `--update` is not passed but two or more of these are true, the skill prints a
suggestion to re-run with `--update`. See `flag-reference.md` for update semantics per
artifact.

`has_releasing_md` is not part of that count. It drives the release-model phase: when it
is `false`, the skill offers `ycc:release-model` (unless `--no-release-model`); when it
is `true`, the offer is skipped and the `AGENTS.md` "Branching & releases" section is
rendered. The skill checks only that the file exists; `ycc:release-model --audit` validates
its content.

---

## Empty Repo Fallback

When `is_empty=true` (no manifest files found, fewer than 3 source files total):

- All detection keys are set to `unknown`.
- The skill enters an interactive prompt sequence asking the user for:
  1. Project name (`PROJECT_NAME`)
  2. One-sentence purpose (`PROJECT_PURPOSE`)
  3. Primary language (`PRIMARY_LANG`) — free-form, then normalised to a known profile
- The normalised value is used to hydrate templates exactly as if detection had succeeded.
- `--profile=empty` forces this path even in a non-empty repo (useful for greenfield
  bootstrapping from a pre-seeded directory).

---

---

## Command detection notes

- JS/TS: `test`, `build` need the matching `package.json` script; `lint` needs `lint` or
  `lint:check`. Detection uses `jq`; if `jq` is missing the script warns on stderr and
  reports `unknown` rather than guessing.
- Python: `pytest` needs the dependency, a `[tool.pytest]` table, or a pytest config /
  `conftest.py`; `ruff` needs the dependency, a `[tool.ruff]` table or `ruff.toml`; a build
  command needs `[build-system]`. Comments in manifests are ignored.
- Go: `go vet ./...`, or `golangci-lint run` when a `.golangci.*` config exists.
- Mixed repos: commands come from the first detected stack; `secondary_languages` lists the
  rest, and the renderer keeps every component language's block.
