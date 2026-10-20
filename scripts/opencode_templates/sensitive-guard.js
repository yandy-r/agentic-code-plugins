// ycc sensitive-file guard: OpenCode V2 plugin for restricted ycc specialists.
//
// Copied verbatim as index.js by scripts/opencode_sensitive_policy.py, beside
// policy.json (a copy of ycc/settings/sensitive-files.json), into the bundle's
// own ycc-sensitive-guard unit. The file-copy install loads it through the
// managed `plugins` entry "./ycc-sensitive-guard"; the experimental npm
// package ships the same directory and calls its setup from its own setup.
//
// Only agents in policy.restricted_agents are affected. For them:
//   - execute.before rejects read/edit/write/patch targets, grep/glob search
//     roots, a grep `include` naming a sensitive file, and shell commands or
//     workdirs whose arguments name a sensitive path. Paths are resolved
//     against the session location, `~` expands to the home directory, and
//     existing paths are also checked through realpath so a symlink to a
//     sensitive file is treated as that file.
//   - execute.after removes sensitive files from grep and glob results and
//     rebuilds the model-facing text, so a directory-wide search returns
//     neither their names nor their content.
// Shell checks inspect the command text only. Build, test, and interpreter
// commands execute project code, which this guard does not and cannot bound.
//
// Contract (opencode v2.0.32 tag sources):
//   - Default export { id, setup } (packages/core/src/plugin/module.ts).
//   - ctx.tool.hook("execute.before" | "execute.after", callback): events carry
//     { tool, sessionID, agent, messageID, id, input } and, after a completed
//     call, a mutable `result` { output?, content, metadata? }
//     (packages/plugin/src/effect/tool.ts). Only execute.before may fail; a
//     thrown error rejects that call before it runs
//     (packages/plugin/src/promise/adapter.ts toolHook).
//   - grep/glob output paths are relative to the session location; their
//     model content lists absolute paths (packages/core/src/tool/plugin/grep.ts,
//     glob.ts toModelContent).

import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, resolve, sep } from "node:path";
import { lstatSync, readdirSync, readFileSync, readlinkSync } from "node:fs";

const POLICY = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "policy.json"), "utf8"));
const BLOCKED = "blocked by ycc sensitive-file guard: this specialist may not access secret-bearing files";

function globRegExp(glob) {
  let source = "";
  for (const character of glob) {
    if (character === "*") source += "[^/]*";
    else if (character === "?") source += "[^/]";
    else source += character.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${source}$`, "i");
}

const RESTRICTED = new Set(POLICY.restricted_agents);
// Allow exceptions (`*.env.example`) only lift the .env-family patterns; a name
// that also matches another basename pattern (`id_rsa.env.example`) stays denied.
const NAME_PATTERNS = POLICY.patterns.filter((pattern) => !pattern.includes("/"));
const ENV_NAMES = NAME_PATTERNS.filter((pattern) => pattern.startsWith(".env")).map(globRegExp);
const OTHER_NAMES = NAME_PATTERNS.filter((pattern) => !pattern.startsWith(".env")).map(globRegExp);
const DIRECTORIES = POLICY.patterns
  .filter((pattern) => pattern.endsWith("/"))
  .map((pattern) => pattern.slice(0, -1).toLowerCase());
const SUFFIXES = POLICY.patterns
  .filter((pattern) => pattern.includes("/") && !pattern.endsWith("/"))
  .map((pattern) => pattern.toLowerCase().split("/"));
const ALLOW = POLICY.allow.map(globRegExp);

function segments(path) {
  return path.split(/[\\/]+/).filter(Boolean);
}

// Lexical policy match on one absolute or relative path.
function matches(path) {
  const parts = segments(path);
  if (parts.length === 0) return false;
  const lower = parts.map((part) => part.toLowerCase());
  if (lower.some((part) => DIRECTORIES.includes(part))) return true;
  if (SUFFIXES.some((suffix) => suffix.every((part, index) => lower.at(index - suffix.length) === part))) return true;
  const name = parts.at(-1);
  if (OTHER_NAMES.some((pattern) => pattern.test(name))) return true;
  return ENV_NAMES.some((pattern) => pattern.test(name)) && !ALLOW.some((pattern) => pattern.test(name));
}

function expandHome(value) {
  if (value === "~") return homedir();
  if (value.startsWith("~/")) return join(homedir(), value.slice(2));
  return value;
}

// Physical path: every existing symlink component is replaced by its target,
// including a dangling link whose target does not exist yet, so a write
// through a link to a sensitive path is judged by that path.
function canonical(absolute) {
  let pending = segments(absolute);
  let current = sep;
  let hops = 0;
  while (pending.length > 0) {
    const part = pending.shift();
    const next = join(current, part);
    let link = null;
    try {
      if (lstatSync(next).isSymbolicLink() && hops < 40) link = readlinkSync(next);
    } catch {
      link = null;
    }
    if (link === null) {
      current = next;
      continue;
    }
    hops += 1;
    if (isAbsolute(link)) current = sep;
    pending = [...segments(link), ...pending];
  }
  return current;
}

function sensitive(value, base) {
  if (typeof value !== "string" || value === "") return false;
  const absolute = resolve(base, expandHome(value));
  return matches(absolute) || matches(canonical(absolute));
}

const GLOB = /[*?[]/;

// Expand one shell glob argument against the filesystem (bash semantics:
// a leading `*`/`?` does not match dotfiles).
function globHits(word, base) {
  const absolute = resolve(base, expandHome(word));
  const parts = segments(absolute);
  let candidates = [isAbsolute(absolute) ? sep : base];
  for (const part of parts) {
    const next = [];
    for (const directory of candidates) {
      if (!GLOB.test(part)) {
        next.push(join(directory, part));
        continue;
      }
      const pattern = globRegExp(part.replace(/\[[^\]]*\]/g, "?"));
      let entries = [];
      try {
        entries = readdirSync(directory);
      } catch {
        continue;
      }
      for (const entry of entries) {
        if (entry.startsWith(".") && !part.startsWith(".")) continue;
        if (pattern.test(entry)) next.push(join(directory, entry));
      }
    }
    candidates = next.slice(0, 2000);
  }
  return candidates;
}

// Every path-like fragment of a command: whole words with quotes removed,
// fragments between shell or language punctuation, option values, and the
// text after each `:` (git object names such as `HEAD:.env` or `:0:.env`).
function shellWords(command) {
  const words = new Set();
  for (const raw of command.split(/[\s;&|()<>`{}]+/)) {
    const word = raw.replace(/["'\\$]/g, "");
    if (word) words.add(word);
    for (const fragment of raw.split(/[^A-Za-z0-9._~/*?[\]@%+:-]+/)) if (fragment) words.add(fragment);
  }
  for (const word of [...words]) {
    const option = word.match(/^-{1,2}[A-Za-z0-9-]+=(.+)$/) ?? word.match(/^[A-Za-z_][A-Za-z0-9_]*=(.+)$/);
    if (option) words.add(option[1]);
  }
  for (const word of [...words]) {
    for (let index = word.indexOf(":"); index !== -1; index = word.indexOf(":", index + 1)) {
      const rest = word.slice(index + 1);
      if (rest) words.add(rest);
    }
  }
  return [...words];
}

// Shell text the word scan cannot resolve to file names: brace lists and
// sequences (`.{e,x}nv`, `{a..z}`) and ANSI-C quoting (`$'\x2e'`). `git diff
// --no-index` compares arbitrary directories (gitignored dotfiles included),
// so it is refused outright.
const AMBIGUOUS_SHELL = [/\{[^{}\s]*(?:,|\.\.)[^{}\s]*\}/, /\$'/, /--no-index\b/];

function shellBlocked(input, root) {
  const workdir = typeof input.workdir === "string" && input.workdir ? resolve(root, expandHome(input.workdir)) : root;
  if (workdir !== root && sensitive(workdir, root)) return true;
  const command = typeof input.command === "string" ? input.command : "";
  if (AMBIGUOUS_SHELL.some((pattern) => pattern.test(command))) return true;
  for (const word of shellWords(command)) {
    if (sensitive(word, workdir)) return true;
    if (GLOB.test(word) && globHits(word, workdir).some((hit) => sensitive(hit, workdir))) return true;
  }
  return false;
}

// The core trims each patch line before matching its file headers.
function patchPaths(text) {
  if (typeof text !== "string") return [];
  return [...text.matchAll(/^\s*\*\*\* (?:Add File|Update File|Delete File|Move to):[ \t]*(.+?)\s*$/gm)].map(
    (match) => match[1],
  );
}

// The read tool falls back to one sibling whose name matches after this
// normalization when the requested path does not exist.
function lookAlike(name) {
  return name.normalize("NFC").replace(/[\u00a0\u202f]/g, " ").replace(/[\u2018\u2019]/g, "'");
}

function readBlocked(path, root) {
  if (sensitive(path, root)) return true;
  if (typeof path !== "string" || path === "") return false;
  const absolute = resolve(root, expandHome(path));
  try {
    lstatSync(absolute);
    return false;
  } catch {
    // Missing: check every sibling the fallback could pick instead.
  }
  const wanted = lookAlike(basename(absolute));
  let entries = [];
  try {
    entries = readdirSync(dirname(absolute));
  } catch {
    return false;
  }
  return entries.some((entry) => lookAlike(entry) === wanted && sensitive(join(dirname(absolute), entry), root));
}

function includeBlocked(include, root) {
  if (typeof include !== "string" || include === "") return false;
  const last = include.split("/").at(-1);
  if (GLOB.test(last) || /[{}!]/.test(last)) return false;
  return sensitive(last, root);
}

function blocked(tool, input, root) {
  const args = input && typeof input === "object" ? input : {};
  switch (tool) {
    case "read":
      return readBlocked(args.path, root);
    case "edit":
    case "write":
      return sensitive(args.path, root);
    case "patch":
      return patchPaths(args.patchText).some((path) => sensitive(path, root));
    case "grep":
      return sensitive(args.path ?? ".", root) || includeBlocked(args.include, root);
    case "glob":
      return sensitive(args.path ?? ".", root);
    case "shell":
      return shellBlocked(args, root);
    default:
      return false;
  }
}

const TRUNCATED = (count) =>
  `(Results are truncated: showing first ${count} results. Consider using a more specific path or pattern.)`;

function grepContent(matches, root, truncated) {
  const lines = matches.length === 0 ? ["No matches found"] : [`Found ${matches.length} matches`];
  let current = "";
  for (const match of matches) {
    const path = resolve(root, match.entry.path);
    if (current !== path) {
      if (current) lines.push("");
      current = path;
      lines.push(`${path}:`);
    }
    lines.push(`  Line ${match.line}: ${match.text}`);
  }
  if (truncated) lines.push("", TRUNCATED(matches.length));
  return lines.join("\n");
}

function globContent(entries, root, truncated) {
  const lines = entries.length === 0 ? ["No files found"] : entries.map((entry) => resolve(root, entry.path));
  if (truncated) lines.push("", TRUNCATED(entries.length));
  return lines.join("\n");
}

function filterResult(tool, result, root) {
  const metadata = result.metadata ?? {};
  const truncated = metadata.truncated === true;
  if (!Array.isArray(result.output)) {
    // Unknown result shape: withhold it rather than pass raw text through.
    result.content = "Search results withheld by ycc sensitive-file guard.";
    return;
  }
  if (tool === "grep") {
    const kept = result.output.filter((match) => !sensitive(match?.entry?.path, root));
    result.output = kept;
    result.content = grepContent(kept, root, truncated);
    result.metadata = { ...metadata, matches: kept.length };
  } else {
    const kept = result.output.filter((entry) => !sensitive(entry?.path, root));
    result.output = kept;
    result.content = globContent(kept, root, truncated);
    result.metadata = { ...metadata, count: kept.length };
  }
}

export async function registerSensitiveGuard(ctx) {
  const root = ctx.location.directory;
  await ctx.tool.hook("execute.before", (event) => {
    if (!RESTRICTED.has(event.agent)) return;
    if (blocked(event.tool, event.input, root)) throw new Error(BLOCKED);
  });
  await ctx.tool.hook("execute.after", (event) => {
    if (!RESTRICTED.has(event.agent) || event.status !== "completed") return;
    if (event.tool !== "grep" && event.tool !== "glob") return;
    filterResult(event.tool, event.result, root);
  });
}

export default {
  id: "yandy-r.ycc-sensitive-guard",
  setup: registerSensitiveGuard,
};
