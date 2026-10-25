// `wi new` as a form: title, type, parent (my work items and map tickets from fleet's
// state.json), tags and description. The new item's link goes to the clipboard.

import { Action, ActionPanel, Clipboard, Form, Icon, Toast, open, popToRoot, showToast } from "@raycast/api";
import { useState } from "react";
import { readState, run } from "./state";

interface Values {
  title: string;
  type: string;
  parent: string;
  tags: string;
  description: string;
  mine: boolean;
}

export default function Command() {
  const [titleError, setTitleError] = useState<string>();
  const items = (readState()?.workItems ?? []).flatMap((w) => [w, ...(w.tickets ?? [])]);

  async function submit(v: Values) {
    if (!v.title.trim()) return setTitleError("Tittel mangler");
    const args = ["new", v.title.trim(), "-t", v.type];
    if (v.mine) args.push("-a", "@me");
    if (v.parent) args.push("-p", v.parent);
    for (const t of v.tags.split(",").map((t) => t.trim()).filter(Boolean)) args.push("-g", t);
    if (v.description.trim()) args.push("-d", v.description.trim());

    const toast = await showToast({ style: Toast.Style.Animated, title: "Oppretter …" });
    try {
      // «✓ #9400 Issue · tildelt · …  https://dev.azure.com/…»
      const out = await run("wi", args);
      const url = out.split(" ").pop() ?? "";
      await Clipboard.copy(url);
      toast.style = Toast.Style.Success;
      toast.title = out.replace(/\s+https?:\S+$/, "");
      toast.message = "Lenke kopiert";
      toast.primaryAction = { title: "Åpne", onAction: () => open(url) };
      await popToRoot();
    } catch (e) {
      toast.style = Toast.Style.Failure;
      toast.title = "wi new feilet";
      toast.message = (e as Error).message;
    }
  }

  return (
    <Form
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Opprett" icon={Icon.Plus} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.TextField
        id="title"
        title="Tittel"
        error={titleError}
        onChange={() => setTitleError(undefined)}
        autoFocus
      />
      <Form.Dropdown id="type" title="Type" defaultValue="Issue">
        {["Issue", "Bug", "Task"].map((t) => (
          <Form.Dropdown.Item key={t} value={t} title={t} />
        ))}
      </Form.Dropdown>
      <Form.Dropdown id="parent" title="Parent" defaultValue="" filtering>
        <Form.Dropdown.Item value="" title="Ingen" />
        {items.map((w) => (
          <Form.Dropdown.Item key={w.id} value={String(w.id)} title={`#${w.id} ${w.title}`} />
        ))}
      </Form.Dropdown>
      <Form.TextField id="tags" title="Tags" placeholder="komma-separert" />
      <Form.TextArea id="description" title="Beskrivelse" enableMarkdown={false} />
      <Form.Checkbox id="mine" label="Tildel meg" defaultValue />
    </Form>
  );
}
