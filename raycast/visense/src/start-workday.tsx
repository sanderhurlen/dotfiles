// Start of the day: how to attack it (`workday plan`: yesterday's note, fleet's list and the
// standup, through Claude; written once a day) above yesterday's note. ↵ asks for the start
// time (today's logged start, else now) and starts the day:
// Ghostty with fleet in tab 1 (splits `claude agents` to its left by itself) and tower in
// tab 2, logging in only when the session no longer works, then Outlook and Teams. Whatever
// already runs is left alone. `workday start` logs the time and starts a background agent
// that sums up my launchd jobs; End Workday logs the end. The time account's balance shows on top,
// with the days that miss a start or end (⌘T fills in the newest).

import { Action, ActionPanel, Detail, Form, Icon, Toast, closeMainWindow, open, showToast, useNavigation } from "@raycast/api";
import { runAppleScript } from "@raycast/utils";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { useEffect, useState } from "react";
import { detach } from "./state";
import { LoggForm } from "./tidskonto";
import { DIR, HHMM, LOG, Saldo, lastNote, logged, now, read, saldo, today, useNote } from "./workday";

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

async function startDay(tid: string) {
  await closeMainWindow();
  execFileSync(join(HOME, ".dotfiles/bin/workday"), ["start", tid]);
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
  const file = join(DIR, `plan-${today()}.md`);
  // Written once a day; started here when missing, so it is under way while I read yesterday.
  const [since, setSince] = useState(() => {
    if (read(file) !== undefined) return undefined;
    detach("workday", ["plan"], LOG);
    return Date.now();
  });
  const { text, failed, loading } = useNote(file, since);
  const note = lastNote();

  const plan =
    text ??
    (failed ? `**workday plan feilet**\n\n\`\`\`\n${read(LOG) ?? ""}\n\`\`\`` : "_Claude leser fleet, standup og gårsdagens notat …_");
  const [konto, setKonto] = useState<Saldo>();
  const load = () =>
    saldo()
      .then(setKonto)
      .catch(() => undefined);
  useEffect(() => {
    load();
  }, []);
  const missing = konto?.days.filter((d) => d.status === "mangler") ?? [];
  const what = (d: Saldo["days"][number]) => `${d.day} ${d.date} (${d.start ? "slutt" : "start og slutt"})`;
  const head = konto
    ? `_Tidskonto ${konto.text}_${missing.length ? ` · **⚠ mangler tider:** ${missing.map(what).join(", ")} — ⌘T` : ""}\n\n`
    : "";
  const markdown = `# Forslag til i dag\n\n${head}${plan}\n\n---\n\n${note ? read(note) : "_Ingen notat fra forrige arbeidsdag._"}`;

  return (
    <Detail
      isLoading={loading}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action title="Start dagen" icon={Icon.Play} onAction={() => push(<StartTime />)} />
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
          {text && <Action.CopyToClipboard title="Kopier forslaget" content={text} />}
          <Action
            title="Lag forslaget på nytt"
            icon={Icon.ArrowClockwise}
            shortcut={{ modifiers: ["cmd"], key: "r" }}
            onAction={() => {
              detach("workday", ["plan", "--fresh"], LOG);
              setSince(Date.now());
            }}
          />
          {note && <Action.Open title="Åpne gårsdagens notat" target={note} shortcut={{ modifiers: ["cmd"], key: "o" }} />}
        </ActionPanel>
      }
    />
  );
}
