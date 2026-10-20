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
//     against the calling session's location (ctx.session.get, falling back
//     to the plugin's setup location; with neither, the call is rejected),
//     `~` expands to the home directory, and
//     existing paths are also checked through realpath so a symlink to a
//     sensitive file is treated as that file.
//   - execute.after removes sensitive files from grep and glob results and
//     rebuilds the model-facing text, so a directory-wide search returns
//     neither their names nor their content.
//   - Search runs only through this plugin. Built-in grep/glob permissions
//     are keyed by the search pattern, so native path rules cannot cover
//     them; the generated restricted agents allow `ycc_grep`/`ycc_glob`
//     instead of `grep`/`glob`. This plugin registers those tools by reusing
//     the built-in definitions, applies the checks above inside them, and
//     runs the built-in implementation as a hidden internal agent that may
//     only search. A context hook shows them to restricted agents under the
//     built-in names. When this plugin is not loaded, restricted agents have
//     no search tool at all (fail closed).
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
//     (packages/plugin/src/promise/adapter.ts toolHook). execute.before sees
//     the name the model called, execute.after the registered tool name
//     (packages/core/src/tool.ts snapshot execute).
//   - grep/glob output paths are relative to the session location; their
//     model content lists absolute paths (packages/core/src/tool/plugin/grep.ts,
//     glob.ts toModelContent). Both assert their own action name against
//     context.agent (grep.ts, glob.ts permission.assert).
//   - ctx.tool.transform editor.get(id) returns a registered tool with a
//     promise-returning execute; editor.add registers a tool whose visibility
//     is gated by the permission action equal to its name
//     (packages/plugin/src/promise/adapter.ts, packages/core/src/tool.ts
//     snapshot/whollyDisabled).
//   - ctx.session.hook("context") may move a tool definition to another key;
//     the core maps it back to the registered tool by object identity
//     (packages/plugin/src/promise/session.ts SessionContext,
//     packages/core/src/session/model-request.ts).
//   - `hidden` keeps an agent out of default selection and the subagent
//     catalog, and the subagent tool refuses a `primary` agent
//     (packages/core/src/agent.ts selectable, tool/plugin/subagent.ts). Such
//     an agent is still listed by /api/agent and a client can select it.
//   - ctx.permission.assert(input) evaluates the given agent's rules, prompts
//     on `ask`, and rejects on deny or a declined prompt
//     (packages/plugin/src/promise/permission.ts). Built-in search asks
//     `external_directory` for a root outside both the session directory and
//     the project worktree (the nearest `.git`/`.hg` ancestor), with resource
//     `<directory>/*`; grep judges a file root by its parent, glob always
//     treats the root as a directory (packages/core/src/file-access.ts
//     resolve/authorizeExternal, project.ts resolve, tool/plugin/grep.ts,
//     glob.ts). ctx.permission.hook("evaluate") may change an allow/ask
//     effect; its event carries the request's `source` { messageID, id }.
//   - ctx.session.get({ sessionID }) resolves { data: Session.Info } whose
//     `location.directory` is the session's absolute directory
//     (packages/protocol/src/groups/session.ts "session.get",
//     packages/plugin/src/promise/adapter.ts); hooks may return promises.

import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { lstatSync, readdirSync, readFileSync, readlinkSync, statSync } from "node:fs";

const POLICY = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "policy.json"), "utf8"));
const BLOCKED = "blocked by ycc sensitive-file guard: this specialist may not access secret-bearing files";
// Built-in search tool -> guarded tool restricted agents are granted
// (mirrors GUARDED_SEARCH_TOOLS in scripts/opencode_sensitive_policy.py).
const GUARDED_SEARCH = { grep: "ycc_grep", glob: "ycc_glob" };
const SEARCH_BASE = Object.fromEntries(Object.entries(GUARDED_SEARCH).map(([base, name]) => [name, base]));
// Internal agent the guarded tools run the built-in implementation as. It may
// only search. Every check that depends on the caller (its own search and
// external-directory rules) is made as the calling agent before delegating,
// so the helper allows external directories; host-wide rules appended after
// its own can still deny them. execute.before rejects any tool call made by
// it directly; the delegated call does not pass through tool hooks.
const SEARCH_AGENT = "ycc-sensitive-search";
const SEARCH_AGENT_RULES = [
  { action: "*", resource: "*", effect: "deny" },
  { action: "grep", resource: "*", effect: "allow" },
  { action: "glob", resource: "*", effect: "allow" },
  { action: "external_directory", resource: "*", effect: "allow" },
];

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
// Allow exceptions (`*.env.example`) only lift the .env-family patterns (every
// basename pattern containing `.env`); a name that also matches another
// basename pattern (`id_rsa.env.example`) stays denied.
const NAME_PATTERNS = POLICY.patterns.filter((pattern) => !pattern.includes("/"));
const ENV_NAMES = NAME_PATTERNS.filter((pattern) => pattern.includes(".env")).map(globRegExp);
const OTHER_NAMES = NAME_PATTERNS.filter((pattern) => !pattern.includes(".env")).map(globRegExp);
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
// sequences (`.{e,x}nv`, `{a..z}`, quoted elements included), every `$` form
// (parameter expansion such as `$HOME`/`${PWD}`, `$(…)`, ANSI-C `$'\x2e'`),
// backtick substitution, and tilde prefixes other than `~` and `~/`
// (`~user`, `~+`, `~-`, also after `=` or `:`). `git diff --no-index`
// compares arbitrary directories (gitignored dotfiles included), so it is
// refused outright.
const AMBIGUOUS_SHELL = [
  /\{[^{}]*(?:,|\.\.)[^{}]*\}/,
  /[$`]/,
  /(?:^|[\s=:;&|()<>"'])~(?![/\s;&|()<>"']|$)/,
  /--no-index\b/,
];

function outside(path, root) {
  const fromRoot = relative(root, path);
  return fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || isAbsolute(fromRoot);
}

// git switches to no-index mode on its own when a path argument lies outside
// the worktree or it runs outside a repository, and -C/-c/--git-dir/
// --work-tree (or GIT_DIR/GIT_WORK_TREE) retarget it. A restricted agent's git
// commands therefore stay inside the session root: no retargeting, no
// directory (workdir or an earlier `cd`) outside it, and no argument that
// resolves outside it. Shell expansions are already refused (AMBIGUOUS_SHELL).
function gitEscapes(command, workdir, root) {
  let cwd = workdir;
  for (const simple of command.split(/[;&|()\n`]+/)) {
    const words = simple
      .trim()
      .split(/\s+/)
      .map((word) => word.replace(/["'\\]/g, ""))
      .filter(Boolean);
    let retargeted = false;
    while (words.length > 0 && /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[0])) {
      if (/^GIT_/.test(words.shift())) retargeted = true;
    }
    if (words.length === 0) continue;
    const program = basename(words[0]);
    if (program === "cd" || program === "pushd") {
      const target = words.slice(1).find((word) => !word.startsWith("-"));
      cwd = resolve(cwd, expandHome(target ?? "~"));
      continue;
    }
    if (program !== "git") continue;
    if (retargeted || outside(cwd, root) || outside(canonical(cwd), canonical(root))) return true;
    let subcommand = false;
    for (const word of words.slice(1)) {
      if (word.startsWith("-")) {
        // Options before the subcommand are git's own; after it, `-C`/`-c`
        // mean copy detection / combined diffs.
        if (!subcommand && /^(?:-C|-c|--git-dir|--work-tree)/.test(word)) return true;
        continue;
      }
      subcommand = true;
      const path = resolve(cwd, expandHome(word));
      if (outside(path, root) || outside(canonical(path), canonical(root))) return true;
    }
  }
  return false;
}

function shellBlocked(input, root) {
  const workdir = typeof input.workdir === "string" && input.workdir ? resolve(root, expandHome(input.workdir)) : root;
  if (workdir !== root && sensitive(workdir, root)) return true;
  const command = typeof input.command === "string" ? input.command : "";
  if (AMBIGUOUS_SHELL.some((pattern) => pattern.test(command))) return true;
  if (gitEscapes(command, workdir, root)) return true;
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
  switch (SEARCH_BASE[tool] ?? tool) {
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

function absoluteDirectory(value) {
  return typeof value === "string" && isAbsolute(value) ? value : undefined;
}

// The session's own location, not the server's: a session created or moved
// to another directory resolves tool paths there. Order: a location carried on
// the event, then session.get(sessionID), then the plugin's setup location.
// Undefined when none is usable.
async function sessionRoot(ctx, event) {
  const carried = absoluteDirectory(event.location?.directory);
  if (carried) return carried;
  try {
    const session = await ctx.session?.get?.({ sessionID: event.sessionID });
    const directory = absoluteDirectory((session?.data ?? session)?.location?.directory);
    if (directory) return directory;
  } catch {
    // Fall through to the setup location.
  }
  return absoluteDirectory(ctx.location?.directory);
}

// Nearest ancestor holding `.git` or `.hg`: the project worktree the host
// treats as internal (core/src/project.ts resolve). The filesystem root never
// counts, as in core/src/file-access.ts resolve.
function projectDirectory(start) {
  let current = start;
  while (true) {
    for (const marker of [".git", ".hg"]) {
      try {
        lstatSync(join(current, marker));
        return dirname(current) === current ? undefined : current;
      } catch {
        // Not here; keep walking up.
      }
    }
    const parent = dirname(current);
    if (parent === current) return undefined;
    current = parent;
  }
}

// The `external_directory` request the built-in makes for this search root
// (`<directory>/*`), or undefined when the root is inside the session
// directory or its project. Made for the calling agent instead of the helper;
// an "always" reply saves only that directory.
function externalDirectory(base, path, root) {
  const target = resolve(root, expandHome(typeof path === "string" ? path : "."));
  if (!outside(target, root)) return undefined;
  const project = projectDirectory(root);
  if (project && !outside(target, project)) return undefined;
  let directory = target;
  if (base === "grep") {
    directory = dirname(target);
    try {
      if (statSync(target).isDirectory()) directory = target;
    } catch {
      // A missing root is judged by its parent, as the built-in does.
    }
  }
  return join(directory, "*").replaceAll("\\", "/");
}

// The metadata the built-in attaches to its own search permission request.
function searchMetadata(base, input) {
  const args = input && typeof input === "object" ? input : {};
  if (base === "grep") {
    return {
      root: ".",
      path: args.path,
      include: args.include,
      literal: args.literal,
      caseSensitive: args.caseSensitive,
      limit: args.limit,
    };
  }
  return { root: args.path ?? ".", path: args.path, hidden: args.hidden, limit: args.limit };
}

// Guarded calls in flight whose caller approved an external directory:
// `${sessionID}\0${callID}` -> approved resource. The built-in then asks the
// helper for the same directory, which would prompt the user a second time.
const APPROVED = new Map();

function approvalKey(sessionID, id) {
  return `${sessionID}\u0000${id}`;
}

// Guarded search for restricted agents: the built-in grep/glob definition and
// implementation, run as SEARCH_AGENT after the caller's own permission
// checks, the same root checks the hooks apply, and with the same result
// filtering. A host without the built-in gets no guarded tool, so the
// restricted agent simply has no search (fail closed).
async function registerSearchTools(ctx) {
  await ctx.agent.transform((editor) => {
    editor.update(SEARCH_AGENT, (agent) => {
      agent.name = SEARCH_AGENT;
      agent.description = "Internal: runs guarded searches for restricted ycc specialists.";
      // Checked on an isolated v2.0.32 host: as a hidden `subagent` it could
      // still be started by name through the subagent tool; as `primary` the
      // tool rejects it ("cannot run as a subagent"). Explicit client
      // selection remains possible, so execute.before also rejects its calls.
      agent.mode = "primary";
      agent.hidden = true;
      agent.permissions = structuredClone(SEARCH_AGENT_RULES);
    });
  });
  await ctx.tool.transform((editor) => {
    for (const [base, name] of Object.entries(GUARDED_SEARCH)) {
      const builtin = editor.get(base);
      if (!builtin || typeof builtin.execute !== "function") continue;
      editor.add({
        name,
        description: builtin.description,
        input: builtin.input,
        output: builtin.output,
        options: { codemode: false },
        execute: async (input, context) => {
          if (!RESTRICTED.has(context.agent)) throw new Error(`${name} is reserved for restricted ycc specialists`);
          const root = await sessionRoot(ctx, { sessionID: context.sessionID });
          if (!root || blocked(base, input, root)) throw new Error(BLOCKED);
          const caller = {
            sessionID: context.sessionID,
            agent: context.agent,
            source: { type: "tool", messageID: context.messageID, id: context.id },
          };
          const external = externalDirectory(base, input?.path, root);
          if (external) {
            await ctx.permission.assert({ action: "external_directory", resources: [external], save: [external], ...caller });
          }
          await ctx.permission.assert({
            action: name,
            resources: [String(input?.pattern)],
            save: ["*"],
            metadata: searchMetadata(base, input),
            ...caller,
          });
          const key = approvalKey(context.sessionID, context.id);
          if (external) APPROVED.set(key, external);
          try {
            const result = await builtin.execute(input, { ...context, agent: SEARCH_AGENT });
            filterResult(base, result, root);
            return result;
          } finally {
            APPROVED.delete(key);
          }
        },
      });
    }
  });
  // The caller already approved this directory for this call: the helper's
  // identical request is not asked again. Only an `ask` for exactly that
  // resource, from the in-flight call, is changed; a deny never is.
  await ctx.permission.hook("evaluate", (event) => {
    if (event.agent !== SEARCH_AGENT || event.action !== "external_directory" || event.effect !== "ask") return;
    const approved = APPROVED.get(approvalKey(event.sessionID, event.source?.id));
    if (approved && event.resources.length > 0 && event.resources.every((resource) => resource === approved)) {
      event.effect = "allow";
    }
  });
  // Model-facing names stay grep/glob for restricted agents; a built-in the
  // host still offers under that name is never shadowed. Other agents are
  // never offered the guarded tools, which reject them anyway.
  await ctx.session.hook("context", (event) => {
    if (!RESTRICTED.has(event.agent)) {
      for (const name of Object.values(GUARDED_SEARCH)) delete event.tools[name];
      return;
    }
    for (const [base, name] of Object.entries(GUARDED_SEARCH)) {
      const definition = event.tools[name];
      if (!definition || event.tools[base]) continue;
      event.tools[base] = definition;
      delete event.tools[name];
    }
  });
}

export async function registerSensitiveGuard(ctx) {
  await ctx.tool.hook("execute.before", async (event) => {
    // The internal search agent only runs inside the guarded tools, which
    // call the built-in directly; a session running as it gets no tools.
    if (event.agent === SEARCH_AGENT) throw new Error(BLOCKED);
    if (!RESTRICTED.has(event.agent)) return;
    const root = await sessionRoot(ctx, event);
    if (!root || blocked(event.tool, event.input, root)) throw new Error(BLOCKED);
  });
  await ctx.tool.hook("execute.after", async (event) => {
    if (!RESTRICTED.has(event.agent) || event.status !== "completed") return;
    const base = SEARCH_BASE[event.tool] ?? event.tool;
    if (base !== "grep" && base !== "glob") return;
    const root = await sessionRoot(ctx, event);
    if (!root) {
      event.result.output = [];
      event.result.content = "Search results withheld by ycc sensitive-file guard.";
      return;
    }
    filterResult(base, event.result, root);
  });
  await registerSearchTools(ctx);
}

export default {
  id: "yandy-r.ycc-sensitive-guard",
  setup: registerSensitiveGuard,
};
