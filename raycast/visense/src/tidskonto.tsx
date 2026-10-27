// The time account (`workday saldo`): the balance, and each day's hours against the norm.
// Days missing a start or end come first; ↵ fills in a day's times, ⌘F marks it off.

import { Action, ActionPanel, Color, Form, Icon, List, Toast, showToast, useNavigation } from "@raycast/api";
import { useEffect, useState } from "react";
import { FriForm } from "./fri";
import { run } from "./state";
import { Day, HHMM, Saldo, hm, saldo } from "./workday";

export function LoggForm({ d, done }: { d: Day; done: () => void }) {
  async function submit(v: { start: string; end: string }) {
    if (!HHMM.test(v.start) || (v.end && !HHMM.test(v.end))) {
      await showToast({ style: Toast.Style.Failure, title: "Tidene må være HH:MM" });
      return;
    }
    try {
      await run("workday", ["logg", d.date, v.start, ...(v.end ? [v.end] : [])]);
      done();
    } catch (e) {
      await showToast({ style: Toast.Style.Failure, title: "workday logg feilet", message: String(e) });
    }
  }
  return (
    <Form
      navigationTitle={`${d.day} ${d.date}`}
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Lagre" icon={Icon.Clock} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.TextField id="start" title="Start" defaultValue={d.start ?? "08:00"} info="HH:MM" autoFocus />
      <Form.TextField id="end" title="Slutt" defaultValue={d.end ?? "16:00"} info="HH:MM, tom: dagen pågår" />
    </Form>
  );
}

function accessories(d: Day): List.Item.Accessory[] {
  const out: List.Item.Accessory[] = [];
  const tag = d.holiday ?? d.off;
  if (tag) out.push({ tag: { value: tag, color: Color.Blue } });
  if (d.status === "mangler") out.push({ tag: { value: "mangler start/slutt", color: Color.Orange } });
  if (d.status === "pågår") out.push({ tag: { value: "pågår", color: Color.SecondaryText } });
  if (d.worked !== null) out.push({ text: hm(d.worked), tooltip: `normtid ${hm(d.norm)}` });
  if (d.diff !== null)
    out.push({
      text: { value: hm(d.diff, true), color: d.diff > 0 ? Color.Green : d.diff < 0 ? Color.Red : Color.SecondaryText },
    });
  return out;
}

export default function Command() {
  const { push, pop } = useNavigation();
  const [data, setData] = useState<Saldo>();
  const [error, setError] = useState<string>();
  const load = () =>
    saldo()
      .then(setData)
      .catch((e) => setError(String(e)));
  useEffect(() => {
    load();
  }, []);
  const done = () => {
    pop();
    load();
  };

  const row = (d: Day) => (
    <List.Item
      key={d.date}
      title={`${d.day} ${d.date}`}
      subtitle={d.start ? `${d.start} – ${d.end ?? ""}` : undefined}
      icon={d.status === "mangler" ? { source: Icon.Warning, tintColor: Color.Orange } : Icon.Calendar}
      accessories={accessories(d)}
      actions={
        <ActionPanel>
          <Action title="Rett tider" icon={Icon.Clock} onAction={() => push(<LoggForm d={d} done={done} />)} />
          <Action
            title="Fri"
            icon={Icon.Airplane}
            shortcut={{ modifiers: ["cmd"], key: "f" }}
            onAction={() => push(<FriForm date={d.date} done={done} />)}
          />
          <Action title="Oppdater" icon={Icon.ArrowClockwise} shortcut={{ modifiers: ["cmd"], key: "r" }} onAction={load} />
        </ActionPanel>
      }
    />
  );

  const missing = data?.days.filter((d) => d.status === "mangler") ?? [];
  const rest = data?.days.filter((d) => d.status !== "mangler") ?? [];
  return (
    <List isLoading={!data && !error} navigationTitle={data ? `Tidskonto ${data.text}` : "Tidskonto"}>
      {error && <List.EmptyView icon={Icon.Warning} title="workday saldo feilet" description={error} />}
      {data && !data.days.length && <List.EmptyView title={`Saldo ${data.text}`} description={`Ingen dager siden ${data.fra} ennå`} />}
      {missing.length > 0 && <List.Section title="Mangler tider">{missing.map(row)}</List.Section>}
      {data && rest.length > 0 && (
        <List.Section title={`Saldo ${data.text}`} subtitle={`fra ${data.fra} · ${hm(data.norm)} per dag · ${data.lunsj} min lunsj`}>
          {rest.map(row)}
        </List.Section>
      )}
    </List>
  );
}
