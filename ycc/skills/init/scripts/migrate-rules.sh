#!/usr/bin/env bash
# migrate-rules.sh
# Migrate an existing rules layout to the canonical AGENTS.md shape:
# AGENTS.md becomes the tool-neutral canonical file and CLAUDE.md becomes
# `@AGENTS.md` plus any Claude-specific content carried over.
#
# Usage:
#   migrate-rules.sh [--repo <path>] [--dry-run] [--yes]
#
# Options:
#   --repo <path>   Target repository (defaults to $PWD).
#   --dry-run       Print the planned diff and the content-loss list; change nothing.
#   --yes           Apply without prompting (a dry-run preview is always shown first).
#
# Behavior:
#   - No-op when AGENTS.md is already canonical or CLAUDE.md is already a
#     `@AGENTS.md` pointer.
#   - Moves every section of CLAUDE.md that is not Claude-specific into
#     AGENTS.md. Claude-specific sections are those whose heading contains
#     "Claude"; the `@AGENTS.md` import line and a "Precedence" section are
#     dropped (the canonical policy covers them).
#   - An existing pointer-style AGENTS.md (<=40 lines naming CLAUDE.md) is
#     replaced by the moved content and listed in the content-loss list.
#   - The content-loss list names every dropped section; nothing is removed
#     silently. Headings inside fenced code blocks never split sections.
#   - Safeguards: no write without a preview; refuses to apply while CLAUDE.md
#     or AGENTS.md have uncommitted changes in a git repo (so git can restore
#     them); never deletes files; always prints line counts.
#
# Output: human-readable report on stdout; errors on stderr.
# Exit codes: 0 success (or dry-run), 1 usage/precondition error, 2 write failure.
set -euo pipefail

REPO="$PWD"
DRY_RUN=false
ASSUME_YES=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            [[ $# -lt 2 ]] && { echo "migrate-rules: --repo requires a value" >&2; exit 1; }
            REPO="$2"
            shift 2
            ;;
        --dry-run) DRY_RUN=true; shift ;;
        --yes)     ASSUME_YES=true; shift ;;
        -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "migrate-rules: unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ ! -d "$REPO" ]]; then
    echo "migrate-rules: directory not found: $REPO" >&2
    exit 1
fi
REPO="$(cd "$REPO" && pwd)"
CLAUDE="${REPO}/CLAUDE.md"
AGENTS="${REPO}/AGENTS.md"

if [[ ! -f "$CLAUDE" ]]; then
    echo "migrate-rules: no CLAUDE.md at ${REPO} — nothing to migrate." >&2
    exit 1
fi

if [[ -L "$CLAUDE" || -L "$AGENTS" ]]; then
    echo "migrate-rules: refusing symlinked rules files" >&2
    exit 1
fi

if grep -qx '@AGENTS.md' "$CLAUDE"; then
    echo "migrate-rules: CLAUDE.md is already a @AGENTS.md pointer — nothing to do."
    exit 0
fi

if [[ "$DRY_RUN" == false && "$ASSUME_YES" == false ]]; then
    echo "migrate-rules: refusing to write without --dry-run or --yes (dry-run first is required)." >&2
    exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Split CLAUDE.md into sections at level-2 headings. Each section record:
# "start_line:end_line". Section text outside any heading (the preamble)
# becomes section 0.
awk '
    BEGIN { start = 1; fence = 0 }
    /^(```|~~~)/ { fence = !fence }
    /^## / && !fence {
        if (NR > start) { print start ":" NR - 1 }
        start = NR
    }
    END { print start ":" NR }
' "$CLAUDE" >"${work}/sections.txt"

mapfile -t ranges <"${work}/sections.txt"
total_lines=$(wc -l <"$CLAUDE" | tr -d ' ')

moved_lines=0
dropped_lines=0
kept_lines=0
: >"${work}/moved.md"
: >"${work}/claude-only.md"
: >"${work}/loss.txt"

for range in "${ranges[@]}"; do
    start="${range%%:*}"
    end="${range##*:}"
    sed -n "${start},${end}p" "$CLAUDE" >"${work}/section.md"
    heading="$(head -n 1 "${work}/section.md")"
    if [[ "$start" -eq 1 && "$heading" != "## "* ]]; then
        # Preamble: title + intro. The title moves; intro moves with it.
        cat "${work}/section.md" >>"${work}/moved.md"
        moved_lines=$((moved_lines + end - start + 1))
        continue
    fi
    if echo "$heading" | grep -qi 'claude'; then
        cat "${work}/section.md" >>"${work}/claude-only.md"
        kept_lines=$((kept_lines + end - start + 1))
        continue
    fi
    if echo "$heading" | grep -qi '^## Precedence'; then
        echo "- ${heading} (CLAUDE.md lines ${start}-${end}) — covered by the canonical policy" >>"${work}/loss.txt"
        dropped_lines=$((dropped_lines + end - start + 1))
        continue
    fi
    cat "${work}/section.md" >>"${work}/moved.md"
    moved_lines=$((moved_lines + end - start + 1))
done

# Existing AGENTS.md: a short pointer to CLAUDE.md is replaced (and listed as
# lost); anything else is kept and the moved sections are appended.
agents_is_pointer=false
if [[ -f "$AGENTS" ]]; then
    agents_lines=$(wc -l <"$AGENTS" | tr -d ' ')
    if [[ "$agents_lines" -le 40 ]] && grep -qi 'CLAUDE.md' "$AGENTS"; then
        agents_is_pointer=true
        echo "- AGENTS.md pointer boilerplate (${agents_lines} lines) — replaced by the canonical content" >>"${work}/loss.txt"
    fi
fi

# Build the new AGENTS.md.
{
    if [[ -f "$AGENTS" && "$agents_is_pointer" == false ]]; then
        cat "$AGENTS"
        echo
    fi
    cat "${work}/moved.md"
} >"${work}/AGENTS.md.new"

# Build the new CLAUDE.md: @AGENTS.md plus Claude-only sections.
{
    echo "@AGENTS.md"
    if [[ -s "${work}/claude-only.md" ]]; then
        echo
        cat "${work}/claude-only.md"
    fi
} >"${work}/CLAUDE.md.new"

new_agents_lines=$(wc -l <"${work}/AGENTS.md.new" | tr -d ' ')
new_claude_lines=$(wc -l <"${work}/CLAUDE.md.new" | tr -d ' ')

echo "Migration plan for ${REPO}"
echo "  CLAUDE.md (current, ${total_lines} lines) -> AGENTS.md canonical"
echo "  content moved: ${moved_lines} lines; Claude-only kept: ${kept_lines} lines"
echo "  dropped: ${dropped_lines} lines"
echo
echo "New line counts: AGENTS.md=${new_agents_lines}, CLAUDE.md=${new_claude_lines}"
echo
if [[ -s "${work}/loss.txt" ]]; then
    echo "Content-loss list (sections dropped, not moved):"
    cat "${work}/loss.txt"
else
    echo "Content-loss list: none."
fi
echo
echo "----- diff: AGENTS.md -----"
if [[ -f "$AGENTS" ]]; then
    diff -u "$AGENTS" "${work}/AGENTS.md.new" || true
else
    diff -u /dev/null "${work}/AGENTS.md.new" || true
fi
echo "----- diff: CLAUDE.md -----"
diff -u "$CLAUDE" "${work}/CLAUDE.md.new" || true

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run: no files changed."
    exit 0
fi

if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
    dirty="$(git -C "$REPO" status --porcelain -- CLAUDE.md AGENTS.md 2>/dev/null || true)"
    if [[ -n "$dirty" ]]; then
        echo "migrate-rules: CLAUDE.md/AGENTS.md have uncommitted changes — commit or stash first so git can restore them:" >&2
        echo "$dirty" >&2
        exit 1
    fi
fi

if [[ "$ASSUME_YES" == false ]]; then
    printf 'Apply this migration? [y/N] '
    read -r answer
    [[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "Aborted; nothing changed."; exit 0; }
fi

cp "${work}/AGENTS.md.new" "$AGENTS" || { echo "migrate-rules: failed writing AGENTS.md" >&2; exit 2; }
cp "${work}/CLAUDE.md.new" "$CLAUDE" || { echo "migrate-rules: failed writing CLAUDE.md" >&2; exit 2; }
echo "Applied: AGENTS.md (${new_agents_lines} lines) + CLAUDE.md (${new_claude_lines} lines)."
