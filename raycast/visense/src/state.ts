// What the commands share: fleet's state.json (written by `fleet` every 15 s, or once by
// `fleet ls`) and running the dotfiles bins. All logic stays in the bins: every row carries
// `view` — icon, chips and whether it needs me, worked out by fleet as its own list shows
// them — so this only maps fleet's tones to Raycast's colours and calls the bins.

import { Color, Icon, Image, List } from "@raycast/api";
import { execFile, spawn } from "node:child_process";
import { mkdirSync, openSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const HOME = homedir();
const STATE = join(HOME, ".cache/fleet/state.json");
const STALE_MS = 10 * 60 * 1000; // fleet rewrites state.json every 15 s while it runs

// Raycast runs with a bare PATH; claude lives in ~/.local/bin, az/uv in Homebrew.
const PATH = [join(HOME, ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin", process.env.PATH].join(":");

export type AgentState = "running" | "working" | "blocked" | "done" | string;

/** A row as fleet's list shows it. Tones are fleet's: red, yellow, green, cyan, dim, b-bad, b-ok, … */
export interface View {
  icon: string; // ✗ ⏸ ✓ ○ ● ▶ …
  tone: string;
  chips: { text: string; tone: string }[];
  needsMe: boolean;
  title?: string; // work items: without «Spec:»/«Kart:»
  label?: string; // work items: Spec, Kart, Bug, Task …
  labelTone?: string;
  status?: string; // tickets: ledig | tatt | blokkert
  titleDim?: boolean; // my PRs: draft
  myTurn?: boolean; // reviews: ○
  postDraft?: string | null; // reviews: the draft waiting to be posted, as wr draft_line says it
}

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
  view: View;
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
  view: View;
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
  policies: { name: string; status: string; blocking: boolean }[];
  todo: string[];
  group: { id: number; title: string; url: string } | null; // the work item it shares with my other PRs
  agents: Record<string, AgentState>;
  view: View;
}

/** What needs me, counted by fleet: agents waiting on me, my PRs that are ✗/⏸, drafts to post. */
export interface NeedsMe {
  count: number;
  blockedAgents: string[];
  myPrs: number[];
  drafts: number[];
  review: number[]; // reviews where it's my turn (○)
  runningAgents: number;
}

export interface State {
  updated: string;
  error: string | null;
  workItems: WorkItem[];
  pullRequests: ReviewPr[];
  myPullRequests: MyPr[];
  agents: Record<string, AgentState>;
  needsMe?: NeedsMe; // missing until the fleet that writes it has run
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

const NO_NEEDS: NeedsMe = { count: 0, blockedAgents: [], myPrs: [], drafts: [], review: [], runningAgents: 0 };

/** What needs me, as fleet counted it, with the rows it points at. */
export function needs(s: State) {
  const n = s.needsMe ?? NO_NEEDS;
  return {
    ...n,
    fix: s.myPullRequests.filter((m) => n.myPrs.includes(m.id)),
    review: s.pullRequests.filter((p) => n.review.includes(p.id)),
  };
}

/** fleet's tone as a Raycast colour; undefined for plain text. */
export function color(tone: string): Color | undefined {
  const t = tone.replace(/^[bt]-/, "");
  return (
    {
      red: Color.Red,
      bad: Color.Red,
      bug: Color.Red,
      yellow: Color.Yellow,
      warn: Color.Orange,
      green: Color.Green,
      ok: Color.Green,
      spec: Color.Green,
      cyan: Color.Blue,
      run: Color.Blue,
      map: Color.Blue,
      task: Color.Blue,
      blue: Color.Blue,
      magenta: Color.Magenta,
      issue: Color.Magenta,
      skill: Color.Purple,
      dim: Color.SecondaryText,
      item: Color.SecondaryText,
    } as Record<string, Color>
  )[t];
}

const ICON: Record<string, Icon> = {
  "✗": Icon.XMarkCircle,
  "⏸": Icon.Pause,
  "✓": Icon.CheckCircle,
  "○": Icon.Circle,
  "●": Icon.CircleFilled,
  "▶": Icon.Play,
};

/** The row's icon in its tone. */
export function viewIcon(v: View): Image.ImageLike {
  return { source: ICON[v.icon] ?? Icon.Dot, tintColor: color(v.tone) };
}

/** The row's chips as accessories: fleet's boxes (b-…) as tags, the rest as coloured text. */
export function chips(v: View): List.Item.Accessory[] {
  return v.chips.map((c) =>
    c.tone.startsWith("b-") ? { tag: { value: c.text, color: color(c.tone) } } : { text: { value: c.text, color: color(c.tone) } },
  );
}

/** The chips as one line, for a menu bar subtitle. */
export function chipLine(v: View): string {
  return v.chips.map((c) => c.text).join("  ");
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
