// Start of the day: how to attack it (`workday plan`: yesterday's note, fleet's list and the
// standup, through Claude; written once a day) above yesterday's note. ↵ starts the day:
// Ghostty with fleet in tab 1 (splits `claude agents` to its left by itself) and tower in
// tab 2, logging in only when the session no longer works, then Outlook and Teams. Whatever
// already runs is left alone. `workday start` logs the time; End Workday logs the end.

import { Action, ActionPanel, Detail, Icon, closeMainWindow, open } from "@raycast/api";
import { runAppleScript } from "@raycast/utils";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import { join } from "node:path";
import { useState } from "react";
import { detach } from "./state";
import { DIR, LOG, lastNote, read, today, useNote } from "./workday";

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

async function startDay() {
  await closeMainWindow();
  execFileSync(join(HOME, ".dotfiles/bin/workday"), ["start"]);
  const cmds: string[] = [];
  if (!running("fleet")) cmds.push("az account get-access-token -o none 2>/dev/null || az login; fleet");
  if (!running("tower")) cmds.push("tower login --ved-behov && tower");
  if (cmds.length) await runAppleScript(GHOSTTY, [join(HOME, "visense"), ...cmds]);
  await open("/Applications/Microsoft Outlook.app");
  await open("/Applications/Microsoft Teams.app");
}

export default function Command() {
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
  const markdown = `# Forslag til i dag\n\n${plan}\n\n---\n\n${note ? read(note) : "_Ingen notat fra forrige arbeidsdag._"}`;

  return (
    <Detail
      isLoading={loading}
      markdown={markdown}
      actions={
        <ActionPanel>
          <Action title="Start dagen" icon={Icon.Play} onAction={startDay} />
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
