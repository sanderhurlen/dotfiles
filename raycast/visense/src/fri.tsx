// A day off, or several: ferie, syk or avspasering (which still costs the norm), or ingen to
// take one back; `workday fri` logs each day in times.tsv. Tidskonto opens the same form.

import { Action, ActionPanel, Form, Icon, Toast, popToRoot, showToast } from "@raycast/api";
import { run } from "./state";

const TYPES = [
  { value: "ferie", title: "Ferie" },
  { value: "syk", title: "Syk" },
  { value: "avspasering", title: "Avspasering (trekker normtid)" },
  { value: "ingen", title: "Ingen (angre fri)" },
];

const iso = (d: Date) => d.toLocaleDateString("sv-SE");

export function FriForm({ date, done }: { date?: string; done?: () => void }) {
  async function submit(v: { fra: Date | null; til: Date | null; type: string }) {
    if (!v.fra) {
      await showToast({ style: Toast.Style.Failure, title: "Velg en dato" });
      return;
    }
    const range = v.til && iso(v.til) !== iso(v.fra) ? `${iso(v.fra)}..${iso(v.til)}` : iso(v.fra);
    try {
      await run("workday", ["fri", range, v.type]);
      await showToast({ title: `${v.type === "ingen" ? "Fri angret" : TYPES.find((t) => t.value === v.type)?.title}: ${range}` });
      if (done) done();
      else await popToRoot();
    } catch (e) {
      await showToast({ style: Toast.Style.Failure, title: "workday fri feilet", message: String(e) });
    }
  }

  return (
    <Form
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Lagre" icon={Icon.Calendar} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.DatePicker id="fra" title="Fra" type={Form.DatePicker.Type.Date} defaultValue={date ? new Date(date) : new Date()} />
      <Form.DatePicker id="til" title="Til" type={Form.DatePicker.Type.Date} info="Tom: bare én dag" />
      <Form.Dropdown id="type" title="Type" defaultValue="ferie">
        {TYPES.map((t) => (
          <Form.Dropdown.Item key={t.value} value={t.value} title={t.title} />
        ))}
      </Form.Dropdown>
    </Form>
  );
}

export default function Command() {
  return <FriForm />;
}
