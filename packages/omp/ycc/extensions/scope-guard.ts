/**
 * ycc agent scope guard for oh-my-pi (YAN-1250).
 *
 * Generated into packages/omp/ycc/extensions/ by scripts/generate_omp_packages.py from
 * scripts/omp_templates/scope-guard.ts; do not edit the generated copy. The scope data sits
 * beside it in agent-scopes.json, rendered from ycc/agents by generate_omp_agents.py (the same
 * data renders each agent's `## Shell scope (OMP)` prompt section).
 *
 * A `tool_call` handler enforces, for ycc subagents only (`ctx.agent.kind === "sub"` and a
 * name listed in agent-scopes.json; the main session and other agents pass through):
 *
 * - bash: every pipeline/chain/group segment must start with one of the agent's prefixes
 *   (`*` matches exactly one argument). Anything the parser cannot prove safe is blocked.
 * - MCP: an `mcp__*` tool call is blocked unless the agent declared that server/tool;
 *   `mcp://` resource reads are blocked for every agent with a declared MCP list.
 *
 * Dependency-free on purpose: OMP loads it with Bun, the tests with Node type stripping.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export interface McpTool {
	server: string;
	tool: string;
}

/** `null` means unrestricted (plain `Bash`, or no `tools` key at all). */
export interface AgentScope {
	bash: string[] | null;
	mcp: McpTool[] | null;
}

export interface ScopeDocument {
	schemaVersion: number;
	/** Plugin packages whose MCP servers OMP names `<namespace>:<server>`. */
	mcpNamespaces: string[];
	agents: Record<string, AgentScope>;
}

export interface Word {
	text: string;
	/** False when an unquoted glob or brace character could expand it into other words. */
	literal: boolean;
}

export type ParseResult = { ok: true; segments: Word[][] } | { ok: false; reason: string };

export interface AgentIdentity {
	kind?: string;
	name?: string;
}

export interface ToolCall {
	toolName: string;
	input?: Record<string, unknown>;
}

export type Decision = { block: true; reason: string } | undefined;

const SCHEMA_VERSION = 1;
const SCOPES_FILE = "agent-scopes.json";
const PREFIX = "ycc scope guard";
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*\+?=/;
const FD = /^[0-9]+$/;
const REDIRECT_TARGET = /^[A-Za-z0-9_./@%+:,-]+$/;
const WORD_BREAK: Record<string, true> = {
	" ": true,
	"\t": true,
	"\n": true,
	";": true,
	"&": true,
	"|": true,
	"(": true,
	")": true,
	"<": true,
	">": true,
};
// Arguments that make `find` run another command the guard never sees.
const FIND_EXEC: Record<string, true> = { "-exec": true, "-execdir": true, "-ok": true, "-okdir": true };
const MCP_PREFIX = "mcp__";
const MCP_NAME_LIMIT = 64;
const MCP_HASH_LENGTH = 8;
const URL_TOOLS: Record<string, true> = { read: true, grep: true, glob: true };

class ParseError extends Error {}

/**
 * Split a bash command into simple-command segments (one word list per pipeline, chain,
 * subshell or brace-group member) after quote removal, or fail closed.
 *
 * Supported: whitespace and newlines; `'…'`, `"…"` and backslash quoting; `|`, `|&`, `||`,
 * `&&`, `;`, `&`, newline; `( … )` and `{ …; }` groups; `#` comments; fd duplication
 * (`2>&1`), input redirection from a plain path and output redirection to `/dev/null`.
 * Rejected: `$` expansions of any kind, backticks, process substitution, here-docs and
 * here-strings, other output redirections, `;;`, unbalanced quotes or groups, and dangling
 * operators.
 */
export function parseShell(command: string): ParseResult {
	try {
		return { ok: true, segments: new ShellParser(command).parse() };
	} catch (error) {
		if (error instanceof ParseError) return { ok: false, reason: error.message };
		throw error;
	}
}

class ShellParser {
	readonly #src: string;
	#i = 0;
	readonly #segments: Word[][] = [];
	#current: Word[] = [];
	#word: string | null = null;
	#literal = true;
	#quoted = false;
	/** A `|`, `||`, `&&` or `|&` still needs a command after it. */
	#pendingOperator = false;
	/** The last thing seen closed a group, which may be followed by an operator or redirection only. */
	#afterGroup = false;
	/** Open groups: their closing character and the segment count when they opened. */
	readonly #groups: Array<{ close: ")" | "}"; start: number }> = [];

	constructor(src: string) {
		this.#src = src;
	}

	parse(): Word[][] {
		const src = this.#src;
		while (this.#i < src.length) {
			const c = src[this.#i];
			const next = src[this.#i + 1];
			if (c === " " || c === "\t") {
				this.#finishWord();
				this.#i++;
			} else if (c === "\n") {
				// A newline right after `|`, `||` or `&&` continues the command, as in bash.
				if (!(this.#pendingOperator && this.#word === null)) this.#terminator();
				this.#i++;
			} else if (c === "#" && this.#word === null) {
				while (this.#i < src.length && src[this.#i] !== "\n") this.#i++;
			} else if (c === "\\") {
				if (next === undefined) throw new ParseError("trailing backslash");
				if (next !== "\n") this.#append(next, true);
				this.#i += 2;
			} else if (c === "'") {
				const end = src.indexOf("'", this.#i + 1);
				if (end < 0) throw new ParseError("unbalanced single quote");
				this.#append(src.slice(this.#i + 1, end), true);
				this.#i = end + 1;
			} else if (c === '"') {
				this.#doubleQuoted();
			} else if (c === "`") {
				throw new ParseError("command substitution (backticks) is not allowed");
			} else if (c === "$") {
				this.#checkDollar(next, false);
				this.#append("$", false);
				this.#i++;
			} else if (c === "|") {
				this.#i += next === "|" || next === "&" ? 2 : 1;
				this.#binary();
			} else if (c === "&") {
				if (next === "&") {
					this.#i += 2;
					this.#binary();
				} else if (next === ">") {
					this.#redirect();
				} else {
					this.#i++;
					this.#terminator();
				}
			} else if (c === ";") {
				if (next === ";") throw new ParseError("';;' is not allowed");
				this.#i++;
				this.#terminator();
			} else if (c === "(") {
				this.#open(")");
				this.#i++;
			} else if (c === ")") {
				this.#close(")");
				this.#i++;
			} else if (c === "<" || c === ">") {
				this.#redirect();
			} else if ((c === "{" || c === "}") && this.#word === null && (next === undefined || WORD_BREAK[next] === true)) {
				this.#braceWord(c);
				this.#i++;
			} else {
				this.#append(c, false);
				if (c === "*" || c === "?" || c === "[" || c === "{" || c === "}") this.#literal = false;
				this.#i++;
			}
		}
		this.#finishWord();
		if (this.#pendingOperator) throw new ParseError("command ends with an operator");
		if (this.#groups.length > 0) throw new ParseError(`unbalanced group: missing '${this.#groups.at(-1)?.close}'`);
		this.#endSegment();
		return this.#segments;
	}

	#append(text: string, quoted: boolean): void {
		if (this.#word === null) {
			this.#word = "";
			this.#literal = true;
			this.#quoted = false;
		}
		this.#word += text;
		if (quoted) this.#quoted = true;
	}

	#finishWord(): void {
		if (this.#word === null) return;
		if (this.#afterGroup) throw new ParseError("a word cannot follow a closed group");
		this.#current.push({ text: this.#word, literal: this.#literal });
		this.#word = null;
		this.#pendingOperator = false;
	}

	#endSegment(): void {
		if (this.#current.length > 0) this.#segments.push(this.#current);
		this.#current = [];
	}

	#terminator(): void {
		this.#finishWord();
		if (this.#pendingOperator) throw new ParseError("missing command after an operator");
		this.#endSegment();
		this.#afterGroup = false;
	}

	#binary(): void {
		this.#finishWord();
		if (this.#current.length === 0 && !this.#afterGroup) throw new ParseError("operator without a command before it");
		this.#endSegment();
		this.#pendingOperator = true;
		this.#afterGroup = false;
	}

	#open(close: ")" | "}"): void {
		if (this.#word !== null || this.#current.length > 0 || this.#afterGroup) {
			throw new ParseError(`unexpected '${close === ")" ? "(" : "{"}' inside a command`);
		}
		this.#groups.push({ close, start: this.#segments.length });
		this.#pendingOperator = false;
	}

	#close(close: ")" | "}"): void {
		this.#finishWord();
		if (this.#pendingOperator) throw new ParseError("missing command after an operator");
		const group = this.#groups.pop();
		if (group === undefined || group.close !== close) throw new ParseError(`unbalanced '${close}'`);
		this.#endSegment();
		if (this.#segments.length === group.start) throw new ParseError("empty group");
		this.#afterGroup = true;
	}

	/** A bare `{` opens a group at command position; a bare `}` closes one there, else it is an argument. */
	#braceWord(c: string): void {
		const atCommandStart = this.#current.length === 0;
		if (c === "{" && atCommandStart) {
			this.#open("}");
		} else if (c === "}" && atCommandStart && this.#groups.at(-1)?.close === "}") {
			this.#close("}");
		} else {
			this.#append(c, false);
			this.#literal = false;
			this.#finishWord();
		}
	}

	#doubleQuoted(): void {
		const src = this.#src;
		let text = "";
		let j = this.#i + 1;
		for (;;) {
			const c = src[j];
			if (c === undefined) throw new ParseError("unbalanced double quote");
			if (c === '"') break;
			if (c === "`") throw new ParseError("command substitution (backticks) is not allowed");
			if (c === "$") this.#checkDollar(src[j + 1], true);
			if (c === "\\" && src[j + 1] !== undefined && '$`"\\\n'.includes(src[j + 1])) {
				if (src[j + 1] !== "\n") text += src[j + 1];
				j += 2;
				continue;
			}
			text += c;
			j++;
		}
		this.#append(text, true);
		this.#i = j + 1;
	}

	/**
	 * A `$` is literal only before a word break or the end (or a closing quote inside double
	 * quotes); anything else starts an expansion, `$'…'` or `$"…"` and fails closed.
	 */
	#checkDollar(next: string | undefined, inDoubleQuotes: boolean): void {
		if (next === "(") throw new ParseError("command substitution $(…) is not allowed");
		if (next === undefined || WORD_BREAK[next] === true || (inDoubleQuotes && next === '"')) return;
		throw new ParseError("$ expansions are not allowed");
	}

	/** `[n]>&m`, `[n]<&m`, `[n]>/dev/null`, `&>/dev/null` and `[n]<path`; everything else fails closed. */
	#redirect(): void {
		const src = this.#src;
		if (this.#word !== null && !this.#quoted && FD.test(this.#word)) {
			this.#word = null; // the fd number belongs to the redirection
		} else {
			this.#finishWord();
		}
		let op = "";
		if (src[this.#i] === "&") {
			op = "&";
			this.#i++;
		}
		const c = src[this.#i];
		const next = src[this.#i + 1];
		if (next === "(") throw new ParseError("process substitution is not allowed");
		if (c === "<" && (next === "<" || next === ">")) throw new ParseError("here-documents and '<>' are not allowed");
		op += c;
		this.#i++;
		if (c === ">" && (next === ">" || next === "|")) {
			op += next;
			this.#i++;
		}
		const dup = src[this.#i] === "&" && op !== "&>" && op !== "&>>";
		if (dup) this.#i++;
		while (src[this.#i] === " " || src[this.#i] === "\t") this.#i++;
		let target = "";
		while (this.#i < src.length && WORD_BREAK[src[this.#i]] !== true) target += src[this.#i++];
		if (!REDIRECT_TARGET.test(target)) throw new ParseError(`unsupported redirection target '${target}'`);
		if (dup) {
			if (!FD.test(target) && target !== "-") throw new ParseError(`unsupported fd duplication '${op}&${target}'`);
		} else if (op !== "<" && target !== "/dev/null") {
			throw new ParseError(`output redirection to '${target}' is not allowed (only /dev/null)`);
		}
	}
}

/** Token-wise prefix match; `*` matches exactly one argument. Matched words must be literal. */
export function matchesPrefix(words: Word[], prefix: string): boolean {
	const tokens = prefix.trim().split(/\s+/);
	if (words.length < tokens.length) return false;
	return tokens.every((token, k) => words[k].literal && (token === "*" || words[k].text === token));
}

/** Why `command` is outside `prefixes`, or undefined when every segment is allowed. */
export function checkCommand(command: string, prefixes: string[]): string | undefined {
	const parsed = parseShell(command);
	if (!parsed.ok) return `cannot verify the command (${parsed.reason})`;
	for (const words of parsed.segments) {
		const shown = words.map(word => word.text).join(" ");
		if (ASSIGNMENT.test(words[0].text)) return `leading variable assignment in "${shown}" is not allowed`;
		if (!prefixes.some(prefix => matchesPrefix(words, prefix))) return `"${shown}" is outside the allowed prefixes`;
		if (words[0].text === "find" && words.some(word => FIND_EXEC[word.text] === true)) {
			return `"${shown}" runs another command through find`;
		}
	}
	return undefined;
}

function sanitizeMcpPart(value: string, fallback: string): string {
	const sanitized = value
		.toLowerCase()
		.replace(/[^a-z0-9_]+/g, "_")
		.replace(/_+/g, "_")
		.replace(/^_+|_+$/g, "");
	return sanitized.length > 0 ? sanitized : fallback;
}

/** OMP's createMCPToolName (mcp/tool-bridge.ts); undefined when a capped name needs Bun.hash and it is absent. */
export function mcpToolName(server: string, tool: string): string | undefined {
	const serverPart = sanitizeMcpPart(server, "server");
	let toolPart = sanitizeMcpPart(tool, "tool");
	if (toolPart.startsWith(`${serverPart}_`)) toolPart = toolPart.slice(serverPart.length + 1);
	const name = `${MCP_PREFIX}${serverPart}_${toolPart}`;
	if (name.length <= MCP_NAME_LIMIT) return name;
	// OMP caps with Bun.hash; Node (the unit tests) has none, so a capped name is never allowed there.
	const bun: unknown = Reflect.get(globalThis, "Bun");
	const hasher = typeof bun === "object" && bun !== null ? Reflect.get(bun, "hash") : undefined;
	if (typeof hasher !== "function") return undefined;
	const hash = String(hasher(name).toString(36)).slice(0, MCP_HASH_LENGTH);
	return `${name.slice(0, MCP_NAME_LIMIT - hash.length - 1)}_${hash}`;
}

function allowedMcpNames(scope: McpTool[], namespaces: string[]): Set<string> {
	const names = new Set<string>();
	for (const { server, tool } of scope) {
		for (const qualified of [server, ...namespaces.map(namespace => `${namespace}:${server}`)]) {
			const name = mcpToolName(qualified, tool);
			if (name !== undefined) names.add(name);
		}
	}
	return names;
}

function mcpUrl(input: Record<string, unknown> | undefined): string | undefined {
	const path = input?.path;
	if (typeof path !== "string") return undefined;
	return path
		.split(";")
		.map(part => part.trim())
		.find(part => part.toLowerCase().startsWith("mcp://"));
}

function block(agent: string, detail: string): Decision {
	return { block: true, reason: `${PREFIX}: ${detail} (ycc agent "${agent}")` };
}

/** The guard's verdict for one tool call; `doc` null means the scope data failed to load. */
export function decide(
	doc: ScopeDocument | null,
	event: ToolCall,
	agent: AgentIdentity | undefined,
	loadError = "unknown error",
): Decision {
	if (agent?.kind !== "sub" || typeof agent.name !== "string") return undefined;
	const name = agent.name.trim().toLowerCase();
	const guarded = event.toolName === "bash" || event.toolName.startsWith(MCP_PREFIX);
	if (doc === null) {
		return guarded ? block(name, `scope data ${SCOPES_FILE} failed to load (${loadError}); bash and MCP are blocked`) : undefined;
	}
	const scope = Object.hasOwn(doc.agents, name) ? doc.agents[name] : undefined;
	if (scope === undefined) return undefined;

	if (event.toolName === "bash") {
		if (scope.bash === null) return undefined;
		if (scope.bash.length === 0) return block(name, "this agent declares no shell access");
		const command = event.input?.command;
		if (typeof command !== "string") return block(name, "bash call without a command string");
		const problem = checkCommand(command, scope.bash);
		if (problem === undefined) return undefined;
		return block(name, `${problem}; allowed prefixes: ${scope.bash.map(prefix => `\`${prefix}\``).join(", ")}`);
	}
	if (scope.mcp === null) return undefined;
	if (event.toolName.startsWith(MCP_PREFIX)) {
		if (scope.mcp.length === 0) return block(name, `this agent declares no MCP tools; blocked ${event.toolName}`);
		if (allowedMcpNames(scope.mcp, doc.mcpNamespaces).has(event.toolName)) return undefined;
		return block(name, `${event.toolName} is not a declared MCP tool; allowed: ${scope.mcp.map(({ server, tool }) => `${server}/${tool}`).join(", ")}`);
	}
	if (URL_TOOLS[event.toolName] === true) {
		const url = mcpUrl(event.input);
		if (url !== undefined) return block(name, `MCP resource reads (${url}) are not declared by this agent`);
	}
	return undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
	return Array.isArray(value) && value.every(item => typeof item === "string");
}

function isMcpList(value: unknown): value is McpTool[] {
	return (
		Array.isArray(value) &&
		value.every(item => isRecord(item) && typeof item.server === "string" && typeof item.tool === "string")
	);
}

/** Parse and validate agent-scopes.json; throws on any shape it does not expect. */
export function parseScopes(text: string): ScopeDocument {
	const raw: unknown = JSON.parse(text);
	if (!isRecord(raw)) throw new Error("not a JSON object");
	if (raw.schemaVersion !== SCHEMA_VERSION) throw new Error(`unsupported schemaVersion ${String(raw.schemaVersion)}`);
	if (!isStringArray(raw.mcpNamespaces)) throw new Error("mcpNamespaces must be a string array");
	if (!isRecord(raw.agents)) throw new Error("agents must be an object");
	const agents: Record<string, AgentScope> = {};
	for (const [name, scope] of Object.entries(raw.agents)) {
		if (!isRecord(scope)) throw new Error(`agents.${name} must be an object`);
		const { bash, mcp } = scope;
		if (bash !== null && !isStringArray(bash)) throw new Error(`agents.${name}.bash is malformed`);
		if (mcp !== null && !isMcpList(mcp)) throw new Error(`agents.${name}.mcp is malformed`);
		agents[name] = { bash, mcp };
	}
	return { schemaVersion: SCHEMA_VERSION, mcpNamespaces: raw.mcpNamespaces, agents };
}

interface GuardApi {
	on(event: "tool_call", handler: (event: ToolCall, ctx: { agent?: AgentIdentity }) => Decision): void;
	setLabel?(label: string): void;
}

export default function yccScopeGuard(pi: GuardApi): void {
	let doc: ScopeDocument | null = null;
	let loadError = "unknown error";
	try {
		doc = parseScopes(readFileSync(fileURLToPath(new URL(SCOPES_FILE, import.meta.url)), "utf8"));
	} catch (error) {
		loadError = error instanceof Error ? error.message : String(error);
	}
	pi.setLabel?.("ycc scope guard");
	pi.on("tool_call", (event, ctx) => decide(doc, event, ctx?.agent, loadError));
}
