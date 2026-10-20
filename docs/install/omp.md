# OMP Install Guide

This guide covers installing `ycc` into OMP (oh-my-pi) with `install.sh`.

> **Pre-release:** the OMP package is generated but unlisted. This repository
> publishes no OMP catalog until the release gate lists it (YAN-1180), so the
> only install path today is `install.sh` from a checkout. `--mode repo` and
> `--target all` do not include OMP yet.

## Prerequisites

- `omp` 18.12.2 or newer on `PATH` (`omp --version`). The installer stops
  with `omp >= 18.12.2 is required for --target omp` otherwise.
- `python3` on `PATH`.
- A checkout of this repository.

OMP has no trust prompt: installed plugin code runs with your user privileges.
Install only from a checkout you trust.

## Quick Start

```bash
./install.sh install --target omp
```

The `base` step generates and validates the OMP package, then:

1. exports it to `${XDG_DATA_HOME:-~/.local/share}/ycc/omp-marketplace`;
2. registers that export as the OMP marketplace `ycc`
   (`omp plugin marketplace add`);
3. installs `ycc@ycc` with `omp plugin install --scope user ycc@ycc`.

What ycc installed is recorded in `~/.config/ycc/omp-native-install.json`.
`update`, `remove` and `migrate` act only on what that file records; an
install or marketplace you created yourself is reported and left untouched.

`ycc@ycc` carries the skills, agents and commands (`/ycc:<skill>`) plus the
shared helpers. It is the only OMP package today: `ycc-mcp`, `ycc-hooks` and
`ycc-rules` are deferred (YAN-1173 to YAN-1175), and `ycc-all` is excluded
because OMP does not read plugin dependencies. `--package ycc` selects it
explicitly; any other package is rejected with the package model's reason.

## Update

Re-run the same command after pulling or regenerating:

```bash
./install.sh install --target omp
./install.sh sync --target omp --intent base   # equivalent
```

A re-run refreshes the export and runs `omp plugin marketplace update ycc`,
then `omp plugin upgrade --scope <scope> ycc@ycc` only when the exported
version differs from the installed one. When nothing changed, omp is not
touched and the installer prints `ycc@ycc <version> up to date`.

The `plugins` intent maps to the same `base` step
(`./install.sh sync --target omp --intent plugins`). Every other intent is
skipped with a notice.

## Reload Or Restart

After an install or update, run `/reload-plugins` in running omp sessions to
pick up skills, commands, agents and MCP servers. A package that ships hooks
or extensions needs a session restart; the installer says so when it applies.

## Project Scope

```bash
cd ~/code/my-project && ycc install --target omp --project
```

`--project` installs with `--scope project` in the git root of the current
directory. It is refused at `$HOME`; `cd` into a project or use the default
user scope (`--global`).

A project install shadows your user install inside that project. To return to
the user copy there, disable the project install:

```bash
omp plugin disable --scope project ycc@ycc
```

ycc never enables or disables plugins: a disabled install stays disabled
across updates and reinstalls.

A user-scope upgrade can make omp garbage-collect the cache a project install
still points at. The installer detects this and prints the repair command:

```bash
cd <project-root> && ./install.sh install --target omp --project
```

## Preview With `--dry-run`

```bash
./install.sh install --target omp --dry-run
./install.sh remove --target omp --only base --dry-run
```

`--dry-run` builds nothing and changes nothing. It prints each mutation as
`[dry-run] would run: omp …` and runs omp's own `--dry-run` check where omp
has one. It works with `install`, `sync` and `remove`, and only when every
`--target` is `omp`.

## Force Reinstall

```bash
./install.sh install --target omp --force
./install.sh install --target omp --project --force
```

`--force` reinstalls the ycc-owned installs (`omp plugin install --force`)
and replaces an export directory that ycc did not record or that was edited.
It never takes over an install ycc did not create.

## Remove

```bash
./install.sh remove --target omp --only base             # user scope
./install.sh remove --target omp --only base --project   # this project
```

`remove` uninstalls only the installs ycc recorded for that scope. The `ycc`
marketplace and the export are removed only when nothing else still uses
them; otherwise the installer prints `kept marketplace ycc: <reason>`.

## Migrate From Older Installs

```bash
./install.sh migrate --target omp           # dry-run
./install.sh migrate --target omp --apply
```

Migration retires two older setups without leaving duplicates:

- `omp plugin link` installs that point at this checkout's `packages/omp/`
  tree (foreign links are kept and reported);
- a `ycc` marketplace registered at the checkout root, where OMP falls back to
  the Claude catalog. Its installs are uninstalled, the marketplace is removed,
  and the native package is installed in the same scopes.

ycc skills in `~/.agents/skills` are also loaded by OMP. Migration and install
report them but never delete them; remove them with
`./install.sh remove --target agents --only base` (YAN-1176).

`migrate --target all` does not include OMP; run `migrate --target omp`
separately.

## Profiles And XDG

The installer resolves every path through omp, so OMP profiles
(`OMP_PROFILE` or `omp --profile`) and the `$XDG_DATA_HOME/omp` data root
work unchanged. Ownership state is keyed per profile: run the installer once
per profile you want `ycc` in.

## Source Modes And `--target all`

Only `--mode local` (the default) works today. `--mode repo` needs a listed
OMP package and is refused until YAN-1180.

`--target all` includes OMP only once an OMP package is listed and
`omp >= 18.12.2` is on `PATH`. Until then it prints
`--target all: skipping omp (...)` and runs the other targets.

## OMP Notes

- Skills run as `/skill:<name>` and commands as `/ycc:<skill>`; agents are
  OMP task agents with `@role` models.
- OMP never runs shell hooks or `WorktreeCreate`. Rules, settings and
  `modelRoles` have no OMP plugin channel yet (YAN-1175).
- Details: [ADR 0002](../internal/adr/0002-omp-runtime-contract.md) and the
  [capability matrix](../../ycc/skills/_shared/references/target-capability-matrix.md).
