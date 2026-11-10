// End of the day: the end time (now) and one line on where I stopped (a draft keeps it), then
// `workday end` stops fleet and tower, prunes, and writes today's note: hours, saldo and my
// line. The note shows here; Start Workday shows it tomorrow.

import { Action, ActionPanel, Detail, Form, Icon, Toast, showToast, useNavigation } from "@raycast/api";
import { runAppleScript } from "@raycast/utils";
import { join } from "node:path";
import { useState } from "react";
import { DIR, HHMM, LOG, now, read, today, useNote } from "./workday";
import { detach } from "./state";

function Note({ since }: { since: number }) {
  const file = join(DIR, `${today()}.md`);
  const { text, failed, loading } = useNote(file, since);
  const markdown =
    text ?? (failed ? `**workday end feilet**\n\n\`\`\`\n${read(LOG) ?? ""}\n\`\`\`` : "_Stopper fleet og rydder …_");
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

  async function submit(v: { neste: string }) {
    if (!HHMM.test(tid)) {
      await showToast({ style: Toast.Style.Failure, title: "Sluttid må være HH:MM" });
      return;
    }
    const since = Date.now();
    const args = ["end", "-t", tid];
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
      <Form.TextArea id="neste" title="Hvor jeg slapp" placeholder="Halvferdig, neste steg, hva jeg venter på" autoFocus />
      <Form.TextField id="tid" title="Sluttid" value={tid} onChange={setTid} info="HH:MM" />
    </Form>
  );
}
