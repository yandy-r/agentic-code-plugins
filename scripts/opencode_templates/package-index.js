// Experimental opt-in opencode V2 plugin adapter for the ycc bundle.
//
// Copied verbatim into the package as index.js by
// scripts/generate_opencode_package.py; all variable data lives in the
// adjacent registration.json and the package-relative asset tree. This file
// contains no install-root, home-directory, or version literal.
//
// Contract (opencode v2.0.29 tag sources + spike YAN-1125):
//   - The plugin loader requires a default export of { id, setup }; V1 hook
//     plugins are rejected (packages/core/src/plugin/module.ts).
//   - Every ctx.<domain>.transform(...) returns a Promise and is awaited, so
//     setup resolves only after all registrations are attached
//     (packages/plugin/src/promise/adapter.ts).
//   - Skill.Info requires { id, name, path, content } with an absolute
//     SKILL.md path; paths inside a loaded skill are handed to the model as
//     part of content and executed by the shell from the session cwd
//     (packages/core/src/skill.ts, shell.ts, file-access.ts). Packed Markdown
//     therefore carries the package-root anchor only where the package owns
//     the span; the adapter renders the skill tree once at setup (tokens
//     expanded, shell-computable references intact) and registers the
//     rendered tree. Paths are derived from import.meta.url, so the package
//     is relocatable.
//   - Commands mirror packages/core/src/config/plugin/command.ts: execute()
//     expands $ARGUMENTS in the template with the invocation text and forwards
//     it through ctx.session.prompt (the command workflow is a prompt, not an
//     OS process). Every command is namespaced `ycc:<skill>` so the package
//     never shadows a host built-in (e.g. /init) or a user's own /<skill>.
//   - Instructions have no config entry on v2.0.29; the only plugin-side
//     mechanism is session.hook("context") pushing a typed
//     { type: "text", text } SystemPart (packages/plugin/src/promise/session.ts).
//   - The sensitive-file guard (ycc-sensitive-guard/, the same module
//     the file-copy install loads as its own plugin) registers
//     tool.hook("execute.before"/"execute.after"), the guarded ycc_grep/
//     ycc_glob tools, and their context hook for the restricted specialists
//     named in its policy.json (verified on v2.0.32 sources).
//   - Permission floor for those restricted specialists. Agent state is built
//     as built-ins (`pre`) -> package transforms -> opencode.config.agent
//     (`post`; plugin/supervisor.ts, plugin/internal.ts), and config.agent
//     appends the config documents' top-level permissions to every agent
//     already registered (config/plugin/agent.ts). Evaluation is last match
//     wins (permission.ts evaluate), so a host-wide allow would otherwise
//     override a package agent's own rules. Three hooks re-apply the
//     restricted agent's packaged ruleset with the same wildcard and
//     last-match semantics; none of them loosens anything:
//       * ctx.permission.hook("evaluate") runs after the merged rules produce
//         an allow/ask effect (permission.ts evaluateInput; a deny
//         short-circuits before hooks) and its mutated effect/message is
//         final (plugin/src/promise/permission.ts). It turns the effect into
//         deny when the packaged rules deny any resource, and an
//         external_directory allow into ask when the packaged rules ask for a
//         resource no saved approval covers. The event's agent is optional;
//         without it the session's agent is used, as the host does.
//       * ctx.tool.hook("execute.before") rejects a call to a tool whose
//         permission action the packaged rules wholly deny, which also covers
//         tools that never request a permission.
//       * ctx.session.hook("context") removes those tools from the model's
//         view (the host offers what the merged rules allow; tool.ts
//         snapshot/whollyDisabled).
//     registerAgents assigns each record its own copy of the packaged rules
//     and request settings, because config.agent mutates them in place.
//
//     Saved approvals: an "always" reply makes the host save the request's
//     `save` patterns for the project (permission.ts reply, saved.add) and
//     append them as allow rules after every configured rule, so the evaluate
//     event cannot tell a saved approval from a config-level allow, and no
//     plugin API lists saved permissions (v2.0.30-v2.1.1). The host publishes
//     permission.asked (the request, `save` included) and permission.replied
//     on the bus that ctx.event.subscribe streams for this location, so the
//     package records the same patterns in its own storage, one key per
//     pattern under the project (ctx.storage.scan reads them back), and keeps
//     an allow they cover. After saving, the host re-evaluates every other
//     pending request in the same fiber and publishes an "always" reply,
//     without saving anything, for each one that now evaluates to allow. At
//     least one resource of such a request is covered by the patterns just
//     recorded (the rest may be allowed by config), so a reply to a request
//     any recorded pattern already partly covers records nothing. Recording
//     happens in memory before any await, so that same-fiber re-evaluation
//     already sees it.
//
// Coexistence with the primary file-copy install (install.sh --target
// opencode): config agents/skills/commands apply in the `post` plugin group,
// which replays after any user package on every state rebuild
// (plugin/supervisor.ts, internal.ts). For equal ids the file-copy definition
// therefore wins — agents field-blend with config values on top, skills and
// commands are replaced by the config copy — so a stale file-copy bundle
// beats this pinned package instead of the reverse. The adapter's editor.get
// skip only covers same-id registrations loaded before this package (config
// is not one of them). MCP servers genuinely coexist: config MCP merges in a
// `pre` group, so an equal config name wins before this package registers.
// Commands never collide: every package command is `ycc:<skill>` while the
// file-copy commands stay bare, so both remain available side by side. The
// context hook does not push instructions already present on the event, so
// an installed file-copy AGENTS.md is not duplicated. When both channels load
// the sensitive-file guard, both hook sets apply the same policy; a call one
// rejects is rejected, and filtering grep/glob results twice is idempotent.

import { fileURLToPath } from "node:url";
import { dirname, isAbsolute, join, relative as relativePath } from "node:path";
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

import { registerSensitiveGuard } from "./ycc-sensitive-guard/index.js";

const PACKAGE_ROOT = dirname(fileURLToPath(import.meta.url));
const REGISTRATION = JSON.parse(readFileSync(join(PACKAGE_ROOT, "registration.json"), "utf8"));
// Restricted specialists come from the guard policy the package ships (one
// source of truth with the file-copy guard). Their packaged rules are
// snapshotted at load, before any host transform can touch them.
const GUARD_POLICY = JSON.parse(readFileSync(join(PACKAGE_ROOT, "ycc-sensitive-guard", "policy.json"), "utf8"));
const RESTRICTED_RULES = new Map(
  (REGISTRATION.agents ?? [])
    .filter((agent) => GUARD_POLICY.restricted_agents.includes(agent.id) && Array.isArray(agent.permissions))
    .map((agent) => [agent.id, structuredClone(agent.permissions)]),
);
const FLOOR_DENIED = "Permission denied by ycc restricted-agent rules: ";
// The only action the floor raises from allow to ask.
const EXTERNAL = "external_directory";

// Token the generator writes where a package asset path is needed; it points
// at the *rendered* tree created below, which sits beside the package root.
const PACKAGE_ROOT_TOKEN = "{{package-root}}";

// Absolute path under the package root for one registration-relative POSIX
// path (e.g. "skills/<id>/SKILL.md"); anything escaping the root is rejected.
function packageAsset(relative) {
  if (typeof relative !== "string" || relative === "" || relative.startsWith("/")) {
    throw new Error(`invalid package asset path: ${String(relative)}`);
  }
  const path = join(PACKAGE_ROOT, ...relative.split("/"));
  const fromRoot = relativePath(PACKAGE_ROOT, path);
  if (fromRoot.startsWith("..") || isAbsolute(fromRoot)) {
    throw new Error(`package asset escapes the package root: ${relative}`);
  }
  return path;
}

// Render tokens into a disposable tree instead of mutating a read-only npm
// installation. References and scripts remain adjacent, including Markdown
// reached later through the read tool. Unloading disposes this tree.
function renderTree() {
  const root = mkdtempSync(join(tmpdir(), "ycc-opencode-"));
  try {
    for (const unit of REGISTRATION.assets) {
      cpSync(packageAsset(unit), join(root, unit), { recursive: true });
    }
    function render(directory) {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) render(path);
        else if (entry.isFile() && entry.name.endsWith(".md")) {
          const text = readFileSync(path, "utf8");
          if (text.includes(PACKAGE_ROOT_TOKEN)) {
            writeFileSync(path, text.replaceAll(PACKAGE_ROOT_TOKEN, root));
          }
        }
      }
    }
    render(root);
    return root;
  } catch (error) {
    teardown(root);
    throw error;
  }
}

function teardown(root) {
  rmSync(root, { recursive: true, force: true });
}

function stripFrontmatter(text) {
  if (!text.startsWith("---\n")) return text;
  const end = text.indexOf("\n---\n", 4);
  return end === -1 ? text : text.slice(end + 5);
}

function expandArguments(template, args) {
  if (template.includes("$ARGUMENTS")) {
    return template.replaceAll("$ARGUMENTS", args).trim();
  }
  return [template.trim(), args.trim()].filter(Boolean).join("\n\n");
}

// registration.json carries opencode "provider/model" strings, validated at
// generation time; split once into a Model.Ref.
function parseModelRef(value) {
  const separator = value.indexOf("/");
  if (separator <= 0) throw new Error(`invalid model reference: ${value}`);
  return { id: value.slice(separator + 1), providerID: value.slice(0, separator) };
}

// The package stores the config-file placeholder syntax; the adapter resolves
// it from process.env at setup time so no credential is stored in the package.
function resolveEnvironment(value) {
  if (typeof value === "string") {
    return value.replace(/\{env:([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, name) => process.env[name] ?? "");
  }
  if (Array.isArray(value)) return value.map(resolveEnvironment);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, resolveEnvironment(item)]));
  }
  return value;
}

async function registerSkills(ctx, renderedRoot) {
  const skills = REGISTRATION.skills ?? [];
  if (skills.length === 0) return;
  await ctx.skill.transform((editor) => {
    for (const skill of skills) {
      if (editor.get(skill.id)) continue;
      packageAsset(skill.path);
      const path = join(renderedRoot, skill.path);
      editor.add({
        id: skill.id,
        name: skill.name,
        description: skill.description,
        ...(skill.autoinvoke === undefined ? {} : { autoinvoke: skill.autoinvoke }),
        path,
        content: stripFrontmatter(readFileSync(path, "utf8")),
      });
    }
  });
}

async function registerAgents(ctx, renderedRoot) {
  const agents = REGISTRATION.agents ?? [];
  const overrides = REGISTRATION.agentModels ?? {};
  if (agents.length === 0 && Object.keys(overrides).length === 0) return;
  await ctx.agent.transform((editor) => {
    for (const agent of agents) {
      if (editor.get(agent.id)) continue;
      packageAsset(agent.prompt);
      const prompt = stripFrontmatter(readFileSync(join(renderedRoot, agent.prompt), "utf8")).trim();
      editor.update(agent.id, (record) => {
        record.name = agent.name;
        record.description = agent.description;
        record.mode = agent.mode;
        record.system = prompt;
        // A copy: the host appends its own rules to this array in place.
        if (agent.permissions) record.permissions = structuredClone(agent.permissions);
        if (agent.color !== undefined) record.color = agent.color;
        if (agent.steps !== undefined) record.steps = agent.steps;
        if (agent.hidden !== undefined) record.hidden = agent.hidden;
        if (agent.request !== undefined) record.request = structuredClone(agent.request);
        if (agent.model !== undefined) record.model = parseModelRef(agent.model);
      });
    }
    // Built-in agents keep a user's own pin; the bundle default only fills a gap.
    for (const [id, model] of Object.entries(overrides)) {
      if (!editor.get(id)) continue;
      editor.update(id, (record) => {
        if (!record.model) record.model = parseModelRef(model);
      });
    }
  });
}

async function registerCommands(ctx) {
  const commands = REGISTRATION.commands ?? [];
  if (commands.length === 0) return;
  await ctx.command.transform((editor) => {
    for (const command of commands) {
      editor.add({
        name: command.name,
        description: command.description,
        execute: async (input) => {
          const text = expandArguments(command.template, input.prompt.text);
          if (command.agent) {
            const session = await ctx.session.get({ sessionID: input.sessionID });
            if (session.agent !== command.agent) {
              await ctx.session.switchAgent({ sessionID: input.sessionID, agent: command.agent });
            }
          }
          if (command.model) {
            await ctx.session.switchModel({ sessionID: input.sessionID, model: parseModelRef(command.model) });
          }
          await ctx.session.prompt({
            ...input.prompt,
            sessionID: input.sessionID,
            text,
            delivery: input.delivery,
          });
        },
      });
    }
  });
}

async function registerMcp(ctx) {
  const servers = REGISTRATION.mcp ?? {};
  const names = Object.keys(servers);
  if (names.length === 0) return;
  await ctx.mcp.transform((editor) => {
    for (const name of names) {
      if (editor.get(name)) continue;
      editor.set(name, resolveEnvironment(servers[name]));
    }
  });
}

async function registerInstructions(ctx) {
  if (!REGISTRATION.context) return;
  const text = readFileSync(packageAsset(REGISTRATION.context), "utf8");
  await ctx.session.hook("context", (event) => {
    if (event.system.some((part) => part.type === "text" && part.text.includes(text.trim()))) return;
    event.system.push({ type: "text", text });
  });
}

// Exact port of opencode v2.0.32 core/src/util/wildcard.ts match().
function wildcardMatch(input, pattern) {
  let escaped = pattern
    .replaceAll("\\", "/")
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*")
    .replace(/\?/g, ".");
  if (escaped.endsWith(" .*")) escaped = escaped.slice(0, -3) + "( .*)?";
  return new RegExp("^" + escaped + "$", process.platform === "win32" ? "si" : "s").test(
    String(input).replaceAll("\\", "/"),
  );
}

// Last matching rule wins (core/src/permission.ts evaluate).
function packagedEffect(rules, action, resource) {
  return rules.findLast((rule) => wildcardMatch(action, rule.action) && wildcardMatch(resource, rule.resource))
    ?.effect;
}

// core/src/tool.ts whollyDisabled: the last rule for the action denies `*`.
function whollyDenied(rules, action) {
  const rule = rules.findLast((item) => wildcardMatch(action, item.action));
  return rule?.resource === "*" && rule.effect === "deny";
}

// Registered tool id -> the permission action that gates it (`options.permission`,
// e.g. write/patch -> edit; otherwise the id, namespaced like
// core/src/tool/runtime.ts effectiveName). Unknown tools are gated by their own
// name, which every restricted ruleset's `* * deny` covers.
async function toolPermissions(ctx) {
  const permissions = new Map();
  try {
    for (const tool of (await ctx.tool.list?.()) ?? []) {
      const name = String(tool.name).replace(/[^a-zA-Z0-9_-]/g, "_");
      const namespace = tool.options?.namespace;
      const id = namespace === undefined ? name : `${namespace.replaceAll(".", "_")}_${name}`;
      permissions.set(id, tool.options?.permission ?? id);
    }
  } catch {
    // Fall back to tool names.
  }
  return permissions;
}

// The guard shows ycc_grep/ycc_glob to restricted agents as grep/glob. A call
// under the built-in name is judged as the guarded tool by execute.before; a
// call that reaches the unguarded built-in still asks for `grep`/`glob`, which
// the evaluate hook denies. In the context hook a `grep`/`glob` key is the
// guarded tool only once the guard has renamed it (a guard loaded before this
// package), i.e. when the guarded key itself is no longer offered.
const GUARDED_ALIASES = { grep: "ycc_grep", glob: "ycc_glob" };

async function sessionAgent(ctx, sessionID) {
  const session = await ctx.session.get({ sessionID });
  return (session?.data ?? session)?.agent;
}

// Saved external_directory approvals of one project, mirrored from the host:
// one storage key per pattern, so instances sharing a project never
// overwrite each other's records.
function savedPrefix(ctx) {
  return `saved/${EXTERNAL}/${encodeURIComponent(ctx.location.project.id)}/`;
}

async function storedPatterns(ctx) {
  const patterns = [];
  const prefix = savedPrefix(ctx);
  let after;
  do {
    const page = await ctx.storage.scan({ prefix, after });
    for (const entry of page.entries) if (typeof entry.value === "string") patterns.push(entry.value);
    after = page.next;
  } while (after !== undefined);
  return patterns;
}

// Recorded patterns: this instance's in-memory records (loaded at setup, then
// set as soon as a reply arrives) plus those other locations of the project
// stored since.
async function savedPatterns(ctx, recorded) {
  try {
    return [...recorded, ...(await storedPatterns(ctx))];
  } catch {
    return [...recorded];
  }
}

function matches(resource, patterns) {
  return patterns.some((pattern) => wildcardMatch(resource, pattern));
}

// Record the `save` patterns of every external_directory request the user
// answers "always", as the host saves them (any agent and session of the
// project). A reply this package never saw asked, any other reply, and a reply
// to a request a recorded pattern already partly covers (the host's
// re-evaluation of other pending requests, which saves nothing) record
// nothing; the cost is one more prompt when a genuine "always" overlaps an
// earlier record. Events are handled one at a time; a failed write loses only
// that record, until this instance is rebuilt.
function trackSavedApprovals(ctx, signal, recorded) {
  const asked = new Map();
  void (async () => {
    for await (const event of ctx.event.subscribe({ signal })) {
      try {
        if (event.type === "permission.asked") {
          const { id, action, resources, save } = event.data;
          if (action === EXTERNAL && save?.length) asked.set(id, { resources, save });
        } else if (event.type === "permission.replied") {
          const request = asked.get(event.data.requestID);
          asked.delete(event.data.requestID);
          if (!request || event.data.reply !== "always") continue;
          const known = [...recorded];
          if (request.resources.some((resource) => matches(resource, known))) continue;
          for (const pattern of request.save) recorded.add(pattern);
          for (const pattern of request.save) {
            await ctx.storage.set(savedPrefix(ctx) + encodeURIComponent(pattern), pattern);
          }
        }
      } catch {
        // Unrecorded patterns prompt again once this instance is rebuilt.
      }
    }
  })().catch(() => {
    // Without the event stream nothing is recorded: saved approvals prompt.
  });
}

// A packaged deny is enforced on top of the host's effect for every action.
// Every restricted ruleset starts with `* * deny`, so any action or resource
// outside the agent's own allowlist is denied here. The packaged `ask` a
// restricted agent ships is external_directory: a host allow is raised back
// to ask unless a recorded saved approval covers every resource it asks for,
// so a config-level allow cannot skip the prompt and an "always" answer is not
// prompted again. Every other action keeps the host's allow or ask.
async function registerPermissionFloor(ctx, signal) {
  if (RESTRICTED_RULES.size === 0) return;
  const recorded = new Set();
  trackSavedApprovals(ctx, signal, recorded);
  try {
    for (const pattern of await storedPatterns(ctx)) recorded.add(pattern);
  } catch {
    // Unloaded records are still read by the evaluate hook's own scan.
  }
  await ctx.permission.hook("evaluate", async (event) => {
    if (event.effect === "deny") return;
    let agent = event.agent;
    if (agent === undefined) {
      try {
        agent = await sessionAgent(ctx, event.sessionID);
      } catch {
        // The session's agent is unknown, so it may be restricted.
        event.effect = "deny";
        event.message = FLOOR_DENIED + event.action;
        return;
      }
    }
    const rules = RESTRICTED_RULES.get(agent);
    if (!rules) return;
    const effects = event.resources.map((resource) => packagedEffect(rules, event.action, resource));
    if (effects.includes("deny")) {
      event.effect = "deny";
      event.message = FLOOR_DENIED + event.action;
      return;
    }
    if (event.effect !== "allow" || event.action !== EXTERNAL) return;
    const asked = event.resources.filter((_, index) => effects[index] === "ask");
    if (asked.length === 0) return;
    if (asked.every((resource) => matches(resource, [...recorded]))) return;
    const saved = await savedPatterns(ctx, recorded);
    if (!asked.every((resource) => matches(resource, saved))) event.effect = "ask";
  });
  await ctx.tool.hook("execute.before", async (event) => {
    const rules = RESTRICTED_RULES.get(event.agent);
    if (!rules) return;
    const permissions = await toolPermissions(ctx);
    const name = GUARDED_ALIASES[event.tool] ?? event.tool;
    const action = permissions.get(name) ?? name;
    if (whollyDenied(rules, action)) throw new Error(FLOOR_DENIED + action);
  });
  await ctx.session.hook("context", async (event) => {
    const rules = RESTRICTED_RULES.get(event.agent);
    if (!rules) return;
    const permissions = await toolPermissions(ctx);
    for (const name of Object.keys(event.tools)) {
      const alias = GUARDED_ALIASES[name];
      const tool = alias && !(alias in event.tools) ? alias : name;
      if (whollyDenied(rules, permissions.get(tool) ?? tool)) delete event.tools[name];
    }
  });
}

export default {
  id: "yandy-r.ycc-opencode",
  async setup(ctx) {
    const renderedRoot = renderTree();
    const events = new AbortController();
    const dispose = () => {
      events.abort();
      teardown(renderedRoot);
    };
    try {
      await registerSkills(ctx, renderedRoot);
      await registerAgents(ctx, renderedRoot);
      await registerCommands(ctx);
      await registerMcp(ctx);
      await registerInstructions(ctx);
      await registerPermissionFloor(ctx, events.signal);
      await registerSensitiveGuard(ctx);
    } catch (error) {
      dispose();
      throw error;
    }
    return dispose;
  },
};
