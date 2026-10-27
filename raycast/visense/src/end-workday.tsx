// End of the day: the end time (now; a draft keeps the text, not the time), a few lines on
// what I focused on and where I stopped, then `workday end`
// stops fleet and tower, prunes, and has Claude add a summary of today's commits, worktrees
// and agents. The note shows here; Start Workday builds tomorrow's plan from it.

import { Action, ActionPanel, Detail, Form, Icon, Toast, showToast, useNavigation } from "@raycast/api";
import { runAppleScript } from "@raycast/utils";
import { join } from "node:path";
import { useState } from "react";
import { DIR, HHMM, LOG, now, read, today, useNote } from "./workday";
import { detach } from "./state";

interface Values {
  fokus: string;
  neste: string;
}

function Note({ since }: { since: number }) {
  const file = join(DIR, `${today()}.md`);
  const { text, failed, loading } = useNote(file, since);
  const markdown =
    text ?? (failed ? `**workday end feilet**\n\n\`\`\`\n${read(LOG) ?? ""}\n\`\`\`` : "_Claude skriver oppsummeringen …_");
  return (
    <Detail
      isLoading={loading}
      markdown={markdown}
      actions={
        <ActionPanel>
          {text && <Action.CopyToClipboard title="Kopier notatet" content={text} />}
          <Action.Open title="Åpne notatet" target={file} shortcut={{ modifiers: ["cmd"], key: "o" }} />
        </ActionPanel>
      }
    />
  );
}

export default function Command() {
  const { push } = useNavigation();
  const [tid, setTid] = useState(now);

  async function submit(v: Values) {
    if (!HHMM.test(tid)) {
      await showToast({ style: Toast.Style.Failure, title: "Sluttid må være HH:MM" });
      return;
    }
    const since = Date.now();
    const args = ["end", "-t", tid];
    if (v.fokus.trim()) args.push("-f", v.fokus.trim());
    if (v.neste.trim()) args.push("-n", v.neste.trim());
    detach("workday", args, LOG);
    push(<Note since={since} />);
    await runAppleScript('quit app "Microsoft Outlook"\nquit app "Microsoft Teams"').catch(() => undefined);
  }

  return (
    <Form
      enableDrafts
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Avslutt dagen" icon={Icon.Moon} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.Description text="Stopper fleet og tower, rydder ferdige agenter og worktrees, lukker Outlook og Teams." />
      <Form.TextField id="tid" title="Sluttid" value={tid} onChange={setTid} info="HH:MM" />
      <Form.TextArea id="fokus" title="Fokus i dag" placeholder="Hva jeg har fokusert på og holdt på med" autoFocus />
      <Form.TextArea id="neste" title="Hvor jeg slapp" placeholder="Halvferdig, neste steg, hva jeg venter på" />
    </Form>
  );
}
