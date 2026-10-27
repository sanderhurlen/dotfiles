// The time account, in three views: Oversikt (`workday oversikt`: saldo, ferie used, planned
// and left, workdays left, hours against the norm), Dager (`workday saldo`: each day's hours,
// the days missing a start or end first; ↵ fills in a day's times) and Fri (the year's days
// off; ↵ takes one back). ⌘N adds a day off from anywhere.

import { Action, ActionPanel, Color, Form, Icon, List, Toast, showToast, useNavigation } from "@raycast/api";
import { useEffect, useState } from "react";
import { FriForm } from "./fri";
import { run } from "./state";
import { Day, HHMM, Off, Oversikt, Saldo, hm, oversikt, saldo } from "./workday";

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

const signed = (t: string) => ({
  value: t,
  color: t.startsWith("+") && t !== "+0:00" ? Color.Green : t.startsWith("-") ? Color.Red : Color.SecondaryText,
});

const dager = (n: number) => `${n} ${n === 1 ? "dag" : "dager"}`;

const TYPE_COLOR: Record<string, Color> = { ferie: Color.Blue, syk: Color.Red, avspasering: Color.Purple };

type View = "oversikt" | "dager" | "fri";

export default function Command() {
  const { push, pop } = useNavigation();
  const [view, setView] = useState<View>("oversikt");
  const [data, setData] = useState<Saldo>();
  const [over, setOver] = useState<Oversikt>();
  const [error, setError] = useState<string>();
  const load = () =>
    Promise.all([saldo(), oversikt()])
      .then(([s, o]) => {
        setData(s);
        setOver(o);
      })
      .catch((e) => setError(String(e)));
  useEffect(() => {
    load();
  }, []);
  const done = () => {
    pop();
    load();
  };

  const common = (date?: string) => (
    <>
      <Action
        title="Ny fri"
        icon={Icon.Airplane}
        shortcut={{ modifiers: ["cmd"], key: "n" }}
        onAction={() => push(<FriForm date={date} done={done} />)}
      />
      <Action title="Oppdater" icon={Icon.ArrowClockwise} shortcut={{ modifiers: ["cmd"], key: "r" }} onAction={load} />
    </>
  );

  async function undo(r: Off) {
    try {
      await run("workday", ["fri", r.fra === r.til ? r.fra : `${r.fra}..${r.til}`, "ingen"]);
      await showToast({ title: `Angret ${r.type}: ${r.fra === r.til ? r.fra : `${r.fra} – ${r.til}`}` });
      load();
    } catch (e) {
      await showToast({ style: Toast.Style.Failure, title: "workday fri feilet", message: String(e) });
    }
  }

  const dayRow = (d: Day) => (
    <List.Item
      key={d.date}
      title={`${d.day} ${d.date}`}
      subtitle={d.start ? `${d.start} – ${d.end ?? ""}` : undefined}
      icon={d.status === "mangler" ? { source: Icon.Warning, tintColor: Color.Orange } : Icon.Calendar}
      accessories={accessories(d)}
      actions={
        <ActionPanel>
          <Action title="Rett tider" icon={Icon.Clock} onAction={() => push(<LoggForm d={d} done={done} />)} />
          {common(d.date)}
        </ActionPanel>
      }
    />
  );

  const info = (key: string, title: string, acc: List.Item.Accessory[], icon: Icon, subtitle?: string) => (
    <List.Item
      key={key}
      title={title}
      subtitle={subtitle}
      icon={icon}
      accessories={acc}
      actions={<ActionPanel>{common()}</ActionPanel>}
    />
  );

  const views = () => {
    if (!data || !over) return null;
    if (view === "dager") {
      const missing = data.days.filter((d) => d.status === "mangler");
      const rest = data.days.filter((d) => d.status !== "mangler");
      return (
        <>
          {missing.length > 0 && <List.Section title="Mangler tider">{missing.map(dayRow)}</List.Section>}
          <List.Section title={`Saldo ${data.text}`} subtitle={`fra ${data.fra} · ${hm(data.norm)} per dag · ${data.lunsj} min lunsj`}>
            {rest.map(dayRow)}
          </List.Section>
        </>
      );
    }
    if (view === "fri") {
      const today = over["i dag"];
      const row = (r: Off) => (
        <List.Item
          key={r.fra + r.type}
          title={r.fra === r.til ? r.fra : `${r.fra} – ${r.til}`}
          icon={Icon.Airplane}
          accessories={[{ tag: { value: r.type, color: TYPE_COLOR[r.type] } }, { text: dager(r.dager) }]}
          actions={
            <ActionPanel>
              <Action title="Angre fri" icon={Icon.Undo} style={Action.Style.Destructive} onAction={() => undo(r)} />
              {common(r.fra)}
            </ActionPanel>
          }
        />
      );
      const ahead = over.fri.filter((r) => r.til >= today);
      const past = over.fri.filter((r) => r.til < today).reverse();
      return (
        <>
          {!over.fri.length && <List.EmptyView icon={Icon.Airplane} title="Ingen fri i år" description="⌘N legger til" />}
          {ahead.length > 0 && <List.Section title="Kommende">{ahead.map(row)}</List.Section>}
          {past.length > 0 && <List.Section title="Tatt i år">{past.map(row)}</List.Section>}
        </>
      );
    }
    const { ferie, igjen, timer } = over;
    const h = over["neste helligdag"];
    const year = over["i dag"].slice(0, 4);
    return (
      <>
        <List.Section title="Tidskonto">
          {info("saldo", "Saldo", [{ text: signed(over.saldo) }], Icon.BankNote, `fra ${data.fra}`)}
          {data.days.some((d) => d.status === "mangler") &&
            info("mangler", "Dager mangler tider", [{ tag: { value: "se Dager", color: Color.Orange } }], Icon.Warning)}
        </List.Section>
        <List.Section title={`Ferie ${year}`} subtitle={`${ferie.rett} dager`}>
          {info("f-igjen", "Igjen", [{ text: dager(ferie.igjen) }], Icon.Airplane)}
          {info("f-brukt", "Brukt", [{ text: dager(ferie.brukt) }], Icon.CheckCircle)}
          {info("f-plan", "Planlagt", [{ text: dager(ferie.planlagt) }], Icon.Calendar)}
        </List.Section>
        <List.Section title="Arbeidsdager igjen" subtitle="uten fri">
          {info("i-uke", "Uka", [{ text: `${dager(igjen.uke.dager)} · ${igjen.uke.timer}` }], Icon.Calendar)}
          {info("i-mnd", "Måneden", [{ text: `${dager(igjen.maned.dager)} · ${igjen.maned.timer}` }], Icon.Calendar)}
          {info("i-ar", "Året", [{ text: `${dager(igjen.ar.dager)} · ${igjen.ar.timer}` }], Icon.Calendar)}
        </List.Section>
        <List.Section title="Timer" subtitle="jobbet mot normtid">
          {(["uke", "maned", "ar"] as const).map((k) =>
            info(`t-${k}`, { uke: "Uka", maned: "Måneden", ar: "Året" }[k], [{ text: `${timer[k].jobbet} av ${timer[k].norm}` }, { text: signed(timer[k].diff) }], Icon.Clock),
          )}
        </List.Section>
        <List.Section title="Annet">
          {info("syk", "Syk i år", [{ text: dager(over.syk) }], Icon.Heartbeat)}
          {info("avsp", "Avspasering", [{ text: `${over.avspasering.brukt} brukt · ${over.avspasering.planlagt} planlagt` }], Icon.Clock)}
          {h && info("hd", "Neste helligdag", [{ text: `${h.day} ${h.date}` }], Icon.Star, h.name)}
        </List.Section>
      </>
    );
  };

  return (
    <List
      isLoading={!data && !error}
      navigationTitle={data ? `Tidskonto ${data.text}` : "Tidskonto"}
      searchBarAccessory={
        <List.Dropdown tooltip="Visning" storeValue onChange={(v) => setView(v as View)}>
          <List.Dropdown.Item value="oversikt" title="Oversikt" />
          <List.Dropdown.Item value="dager" title="Dager" />
          <List.Dropdown.Item value="fri" title="Fri" />
        </List.Dropdown>
      }
    >
      {error && <List.EmptyView icon={Icon.Warning} title="workday feilet" description={error} />}
      {views()}
    </List>
  );
}
