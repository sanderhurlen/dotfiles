// Start of the day, no Claude: fleet is the plan. Shows the time account's balance with the
// days that miss a start or end (⌘T fills in the newest), my launchd jobs that aren't ✓
// (`chores status`) and the last note, where I wrote where I stopped. ↵ starts the day now
// (or keeps today's logged start): `workday start`, then Ghostty with fleet in tab 1 (splits
// `claude agents` to its left by itself) and tower in tab 2, logging in only when the session
// no longer works, then Outlook and Teams. Whatever already runs is left alone. ⌘S starts it
// at another time.

import { Action, ActionPanel, Detail, Form, Icon, Toast, closeMainWindow, open, showToast, useNavigation } from "@raycast/api";
import { runAppleScript } from "@raycast/utils";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { useEffect, useState } from "react";
import { run } from "./state";
import { LoggForm } from "./tidskonto";
import { HHMM, Saldo, lastNote, logged, now, read, saldo } from "./workday";

const HOME = homedir();

function running(bin: string): boolean {
  try {
    execFileSync("pgrep", ["-f", join(HOME, ".dotfiles/bin", bin)]);
    return true;
  } catch {
    return false;
  }
}

const GHOSTTY = `
on run argv
  set cwd to item 1 of argv
  set fresh to not (application "Ghostty" is running)
  tell application "Ghostty"
    activate
    if fresh then
      repeat until (count of windows) > 0
        delay 0.2
      end repeat
      set w to front window
      input text ("cd " & quoted form of cwd & " && " & item 2 of argv & linefeed) to focused terminal of selected tab of w
    else
      set w to new window with configuration {initial working directory:cwd, initial input:item 2 of argv & linefeed}
    end if
    set first_ to selected tab of w
    repeat with i from 3 to count of argv
      new tab in w with configuration {initial working directory:cwd, initial input:item i of argv & linefeed}
    end repeat
    select tab first_
  end tell
end run`;

/** Logs the start at tid (none: keep today's, else now), then opens what the day runs on. */
async function startDay(tid?: string) {
  await closeMainWindow();
  if (tid || !logged("start")) execFileSync(join(HOME, ".dotfiles/bin/workday"), ["start", ...(tid ? [tid] : [])]);
  const cmds: string[] = [];
  if (!running("fleet")) cmds.push("az account get-access-token -o none 2>/dev/null || az login; fleet");
  if (!running("tower")) cmds.push("tower login --ved-behov && tower");
  if (cmds.length) await runAppleScript(GHOSTTY, [join(HOME, "visense"), ...cmds]);
  await open("/Applications/Microsoft Outlook.app");
  await open("/Applications/Microsoft Teams.app");
}

function StartTime() {
  async function submit(v: { tid: string }) {
    if (!HHMM.test(v.tid)) {
      await showToast({ style: Toast.Style.Failure, title: "Starttid må være HH:MM" });
      return;
    }
    await startDay(v.tid);
  }
  return (
    <Form
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Start dagen" icon={Icon.Play} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.TextField id="tid" title="Starttid" defaultValue={logged("start") ?? now()} info="HH:MM" autoFocus />
    </Form>
  );
}

export default function Command() {
  const { push, pop } = useNavigation();
  const note = lastNote();
  const [konto, setKonto] = useState<Saldo>();
  const [jobs, setJobs] = useState<string[]>();
  const load = () =>
    saldo()
      .then(setKonto)
      .catch(() => undefined);
  useEffect(() => {
    load();
    run("chores", ["status"])
      .then((out) => setJobs(out.split("\n").filter((l) => l.trim() && !l.startsWith("✓"))))
      .catch((e) => setJobs([`chores status feilet: ${e.message}`]));
  }, []);

  const missing = konto?.days.filter((d) => d.status === "mangler") ?? [];
  const what = (d: Saldo["days"][number]) => `${d.day} ${d.date} (${d.start ? "slutt" : "start og slutt"})`;
  const head = konto
    ? `_Tidskonto ${konto.text}_${missing.length ? ` · **⚠ mangler tider:** ${missing.map(what).join(", ")} — ⌘T` : ""}\n\n`
    : "";
  const chores = jobs?.length
    ? `**launchd-jobber som trenger noe** (\`chores status <jobb>\`)\n\n\`\`\`\n${jobs.join("\n")}\n\`\`\`\n\n`
    : "";
  const markdown = `# I dag\n\n${head}${chores}---\n\n${note ? read(note) : "_Ingen notat fra forrige arbeidsdag._"}`;
  const started = logged("start");

  return (
    <Detail
      isLoading={!konto || !jobs}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action
            title={started ? `Start dagen (startet ${started})` : "Start dagen nå"}
            icon={Icon.Play}
            onAction={() => startDay()}
          />
          <Action
            title="Start dagen kl. …"
            icon={Icon.Clock}
            shortcut={{ modifiers: ["cmd"], key: "s" }}
            onAction={() => push(<StartTime />)}
          />
          {missing[0] && (
            <Action
              title={`Rett tider for ${missing[0].day} ${missing[0].date}`}
              icon={Icon.Clock}
              shortcut={{ modifiers: ["cmd"], key: "t" }}
              onAction={() =>
                push(
                  <LoggForm
                    d={missing[0]}
                    done={() => {
                      pop();
                      load();
                    }}
                  />,
                )
              }
            />
          )}
          {note && <Action.Open title="Åpne forrige notat" target={note} shortcut={{ modifiers: ["cmd"], key: "o" }} />}
        </ActionPanel>
      }
    />
  );
}
