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
//     tool.hook("execute.before"/"execute.after") for the restricted
//     specialists named in its policy.json (verified on v2.0.32 sources).
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
        if (agent.permissions !== undefined) record.permissions = agent.permissions;
        if (agent.color !== undefined) record.color = agent.color;
        if (agent.steps !== undefined) record.steps = agent.steps;
        if (agent.hidden !== undefined) record.hidden = agent.hidden;
        if (agent.request !== undefined) record.request = agent.request;
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

export default {
  id: "yandy-r.ycc-opencode",
  async setup(ctx) {
    const renderedRoot = renderTree();
    try {
      await registerSkills(ctx, renderedRoot);
      await registerAgents(ctx, renderedRoot);
      await registerCommands(ctx);
      await registerMcp(ctx);
      await registerInstructions(ctx);
      await registerSensitiveGuard(ctx);
    } catch (error) {
      teardown(renderedRoot);
      throw error;
    }
    return () => teardown(renderedRoot);
  },
};
