// What the commands share: fleet's state.json (written by `fleet` every 15 s, or once by
// `fleet ls`), wr's review drafts, and running the dotfiles bins. All logic about ADO stays
// in the bins; this only reads what they write and calls them.

import { execFile, spawn } from "node:child_process";
import { mkdirSync, openSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const HOME = homedir();
const STATE = join(HOME, ".cache/fleet/state.json");
const DRAFTS = join(HOME, ".local/state/wr/review");
const STALE_MS = 10 * 60 * 1000; // fleet rewrites state.json every 15 s while it runs

// Raycast runs with a bare PATH; claude lives in ~/.local/bin, az/uv in Homebrew.
const PATH = [join(HOME, ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", process.env.PATH].join(":");

export type AgentState = "running" | "working" | "blocked" | "done" | string;

export interface WorkItem {
  id: number;
  title: string;
  state: string;
  type: string;
  kind: "item" | "map" | "spec" | string;
  url: string;
  prompt: string;
  agent: string;
  agents: Record<string, AgentState>;
  status?: string; // a map's ticket: ledig | tatt | blokkert
  hitl?: boolean;
  doneTickets?: number;
  tickets?: WorkItem[];
  currentSprint?: boolean; // false: in another iteration, see iterationLabel
  iterationLabel?: string;
  iterationDates?: string | null;
}

export interface ReviewPr {
  id: number;
  title: string;
  repo: string;
  author: string;
  url: string;
  imReviewer: boolean;
  myVote: number;
  agents: Record<string, AgentState>;
}

export interface MyPr {
  id: number;
  title: string;
  repo: string;
  url: string;
  draft: boolean;
  ready: boolean;
  conflicts: boolean;
  autoComplete: boolean;
  policies: { name: string; status: string; blocking: boolean; build?: boolean }[];
  todo: string[];
  group: { id: number; title: string; url: string } | null; // the work item it shares with my other PRs
  agents: Record<string, AgentState>;
}

export interface State {
  updated: string;
  error: string | null;
  workItems: WorkItem[];
  pullRequests: ReviewPr[];
  myPullRequests: MyPr[];
  agents: Record<string, AgentState>;
}

export interface Draft {
  vote?: string;
  comments?: { skip?: boolean }[];
  posted?: string;
}

export function readState(): State | undefined {
  try {
    return JSON.parse(readFileSync(STATE, "utf8"));
  } catch {
    return undefined;
  }
}

export function stale(s: State): boolean {
  return Date.now() - Date.parse(s.updated) > STALE_MS;
}

/** «15:42», or «24.10 15:42» when it isn't today. */
export function when(iso: string): string {
  const d = new Date(iso);
  const hm = d.toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === new Date().toDateString()
    ? hm
    : `${d.toLocaleDateString("nb-NO", { day: "2-digit", month: "2-digit" }).replace(/\.$/, "")} ${hm}`;
}

/** The review agent's draft for a PR, when it is written and not posted yet. */
/** What blocks my PR, without a red build: autopilot's fix agent has that, and fleet shows it as ○ too. */
export function attention(m: MyPr): string[] {
  const builds = new Set(
    (m.policies ?? []).filter((p) => p.blocking && ["rejected", "broken"].includes(p.status)).map((p) => `${p.name} feiler`),
  );
  return m.todo.filter((t) => !builds.has(t));
}

/** A blocking build is queued or running — fleet's ◌. Reviewer policies wait in «queued» too, so only builds count. */
export function building(m: MyPr): boolean {
  return (m.policies ?? []).some((p) => p.build && p.blocking && ["queued", "running"].includes(p.status));
}

/** «Spec: Foo» → «Foo», like fleet: the kind already says it. */
export function bare(title: string): string {
  return title.replace(/^\s*(spec|wayfinder-kart|kart)\s*:\s*/i, "") || title;
}

const TICKETS: [string, string][] = [["ledig", "○"], ["tatt", "▶"], ["blokkert", "⏸"]];

/** A map's/spec's tickets, compact like fleet: «○2 ▶1 ⏸1 ✓4»; a 0 is left out. */
export function ticketCounts(w: WorkItem): string {
  const parts = TICKETS.map(([st, icon]) => [icon, (w.tickets ?? []).filter((t) => t.status === st).length] as const)
    .filter(([, n]) => n)
    .map(([icon, n]) => `${icon}${n}`);
  if (w.doneTickets) parts.push(`✓${w.doneTickets}`);
  return parts.join(" ") || "ingen tickets";
}

export function draft(id: number): Draft | undefined {
  try {
    const d: Draft = JSON.parse(readFileSync(join(DRAFTS, `${id}.json`), "utf8"));
    return d.posted ? undefined : d;
  } catch {
    return undefined;
  }
}

const VOTE: Record<string, string> = {
  approve: "approve",
  suggestions: "approve med forslag",
  wait: "vent på forfatter",
  reject: "reject",
  none: "ingen stemme",
};

export function draftLine(d: Draft): string {
  const n = (d.comments ?? []).filter((c) => !c.skip).length;
  return `${VOTE[d.vote ?? "none"] ?? d.vote} · ${n} kommentar${n === 1 ? "" : "er"}`;
}

/** What needs me, in the order the menu bar shows it. */
export function needs(s: State) {
  const blocked = Object.entries(s.agents ?? {})
    .filter(([, st]) => st === "blocked")
    .map(([name]) => name);
  const fix = s.myPullRequests.filter((m) => attention(m).length);
  const review = s.pullRequests.filter((p) => p.imReviewer && !p.myVote);
  const drafts = review.filter((p) => draft(p.id));
  const running = Object.values(s.agents ?? {}).filter((st) => st === "running" || st === "working").length;
  return { blocked, fix, review, drafts, running, count: blocked.length + fix.length + drafts.length };
}

/** Runs a dotfiles bin; resolves with its stdout, rejects with the last line it wrote to stderr. */
export function run(bin: string, args: string[], timeout = 120_000): Promise<string> {
  return new Promise((resolve, reject) =>
    execFile(
      join(HOME, ".dotfiles/bin", bin),
      args,
      { env: { ...process.env, PATH }, cwd: HOME, timeout },
      (err, stdout, stderr) => {
        if (!err) return resolve(stdout.trim());
        const last = (stderr || stdout).trim().split("\n").pop();
        reject(new Error(last || err.message));
      },
    ),
  );
}

/** Starts a dotfiles bin that outlives the command (Raycast kills what it started when its
 *  window closes); its output goes to log. */
export function detach(bin: string, args: string[], log: string) {
  mkdirSync(join(log, ".."), { recursive: true });
  const fd = openSync(log, "w");
  spawn(join(HOME, ".dotfiles/bin", bin), args, {
    env: { ...process.env, PATH },
    cwd: HOME,
    detached: true,
    stdio: ["ignore", fd, fd],
  }).unref();
}

/** Brings an app to the front (Ghostty, where fleet and the agents run). */
export function activate(app: string) {
  execFile("open", ["-a", app]);
}
