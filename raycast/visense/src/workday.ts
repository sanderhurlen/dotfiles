// What Start and End Workday share: `workday` (bin/workday) writes its notes whole to
// ~/.local/state/workday, so the views run it detached and wait for the file to change.
// Closing Raycast while Claude writes loses nothing; the command shows the file next time.
// Tidskonto and Fri read and write the time account through `workday saldo|logg|fri`.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { useEffect, useState } from "react";
import { run } from "./state";

export const DIR = join(homedir(), ".local/state/workday");
export const LOG = join(DIR, "raycast.log");
const GIVE_UP_MS = 5 * 60 * 1000;

export const today = () => new Date().toLocaleDateString("sv-SE"); // 2026-10-25
export const now = () => new Date().toTimeString().slice(0, 5); // 08:30
export const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

/** Today's last logged start or end (HH:MM) in times.tsv, the one `workday times` counts. */
export function logged(kind: "start" | "end"): string | undefined {
  const lines = (read(join(DIR, "times.tsv")) ?? "").split("\n");
  const line = lines.filter((l) => l.startsWith(today()) && l.endsWith(`\t${kind}`)).pop();
  return line?.slice(11, 16);
}

export function read(file: string): string | undefined {
  try {
    return readFileSync(file, "utf8");
  } catch {
    return undefined;
  }
}

export interface Day {
  date: string;
  day: string;
  start: string | null;
  end: string | null;
  worked: number | null; // minutes, lunch taken off
  norm: number;
  diff: number | null; // worked − norm; null when it isn't counted (mangler, pågår)
  off: string | null; // ferie | syk | avspasering
  holiday: string | null;
  status: "ok" | "mangler" | "pågår";
}

export interface Saldo {
  saldo: number;
  text: string; // +1:30
  fra: string;
  norm: number;
  lunsj: number;
  days: Day[]; // newest first
}

/** `workday saldo --json`: the time account, per day and in all. */
export async function saldo(): Promise<Saldo> {
  return JSON.parse(await run("workday", ["saldo", "--json"]));
}

/** Minutes as 8:00, or +1:30 / -0:45 with sign. */
export function hm(m: number, sign = false): string {
  const a = Math.abs(m);
  return `${m < 0 ? "-" : sign ? "+" : ""}${Math.floor(a / 60)}:${String(a % 60).padStart(2, "0")}`;
}

/** The newest end note (<date>.md), today's included. */
export function lastNote(): string | undefined {
  try {
    const name = readdirSync(DIR).filter((f) => /^\d{4}-\d\d-\d\d\.md$/.test(f)).sort().pop();
    return name && join(DIR, name);
  } catch {
    return undefined;
  }
}

function mtime(file: string): number {
  try {
    return statSync(file).mtimeMs;
  } catch {
    return 0;
  }
}

/** The file's text once it is written after `since` (or at all, without since); polls each second. */
export function useNote(file: string, since?: number) {
  const fresh = () => (mtime(file) > (since ?? 0) ? read(file) : undefined);
  const [text, setText] = useState(fresh);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const got = fresh();
    setText(got);
    setFailed(false);
    if (got !== undefined) return;
    const start = Date.now();
    const t = setInterval(() => {
      const got = fresh();
      if (got !== undefined) setText(got);
      // workday died (claude missing, ADO down): its log says why
      else if (Date.now() - start > GIVE_UP_MS || /^workday: /m.test(read(LOG) ?? "")) setFailed(true);
      else return;
      clearInterval(t);
    }, 1000);
    return () => clearInterval(t);
  }, [file, since]);
  return { text, failed, loading: text === undefined && !failed };
}
