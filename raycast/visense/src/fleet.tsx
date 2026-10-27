// fleet's list in Raycast: work items (maps with their open tickets), PRs waiting for my
// review and my own PRs, with the actions the TUI has under m. Every action is a call to
// a bin (fleet, wr); the list reads state.json again afterwards.

import {
  Action,
  ActionPanel,
  Alert,
  Color,
  Icon,
  List,
  Toast,
  confirmAlert,
  showToast,
} from "@raycast/api";
import { ReactNode, useState } from "react";
import {
  AgentState,
  MyPr,
  ReviewPr,
  State,
  WorkItem,
  activate,
  draft,
  draftLine,
  readState,
  run,
  stale,
  when,
} from "./state";

export default function Command() {
  const [s, setS] = useState<State | undefined>(readState);
  const [busy, setBusy] = useState(false);

  /** Runs a bin with a toast, then reads state.json again. */
  async function act(title: string, bin: string, args: string[], confirm?: string) {
    if (confirm && !(await confirmAlert({ title: confirm, primaryAction: { title, style: Alert.ActionStyle.Default } })))
      return;
    const toast = await showToast({ style: Toast.Style.Animated, title: `${title} …` });
    setBusy(true);
    try {
      const out = await run(bin, args);
      toast.style = Toast.Style.Success;
      toast.title = out.split("\n").pop() || title;
    } catch (e) {
      toast.style = Toast.Style.Failure;
      toast.title = `${title} feilet`;
      toast.message = (e as Error).message;
    } finally {
      setBusy(false);
      setS(readState());
    }
  }

  const refresh = (
    <Action
      title="Hent nå (fleet ls)"
      icon={Icon.ArrowClockwise}
      shortcut={{ modifiers: ["cmd"], key: "r" }}
      onAction={() => act("Henter", "fleet", ["ls"])}
    />
  );

  if (!s) {
    return (
      <List isLoading={busy}>
        <List.EmptyView title="fleet har ikke kjørt" actions={<ActionPanel>{refresh}</ActionPanel>} />
      </List>
    );
  }

  const review = s.pullRequests.filter((p) => p.imReviewer && !p.myVote);
  const subtitle = stale(s) ? `fleet kjører ikke (sist ${when(s.updated)})` : `oppdatert ${when(s.updated)}`;

  return (
    <List isLoading={busy} searchBarPlaceholder={`Søk i work items og PRer · ${subtitle}`}>
      {s.error && <List.Item icon={Icon.Warning} title={`FEIL: ${s.error}`} actions={<ActionPanel>{refresh}</ActionPanel>} />}

      <List.Section title="Mine PRer" subtitle={String(s.myPullRequests.length)}>
        {s.myPullRequests
          .filter((m) => !m.group)
          .map((m) => (
            <MyPrItem key={m.id} m={m} act={act} refresh={refresh} />
          ))}
      </List.Section>

      {bundles(s.myPullRequests).map(([g, ms]) => (
        <List.Section key={g.id} title={`Mine PRer · #${g.id} ${g.title}`} subtitle={String(ms.length)}>
          {ms.map((m) => (
            <MyPrItem key={m.id} m={m} act={act} refresh={refresh} />
          ))}
        </List.Section>
      ))}

      <List.Section title="Til review" subtitle={String(review.length)}>
        {review.map((p) => (
          <ReviewItem key={p.id} p={p} act={act} refresh={refresh} />
        ))}
      </List.Section>

      <List.Section title="Work items" subtitle={String(s.workItems.length)}>
        {s.workItems.flatMap((w) => [w, ...(w.tickets ?? [])]).map((w) => (
          <WorkRow key={w.id} w={w} act={act} refresh={refresh} />
        ))}
      </List.Section>
    </List>
  );
}

type Act = (title: string, bin: string, args: string[], confirm?: string) => Promise<void>;

/** My PRs that share a work item, per item, in the order fleet lists them. */
function bundles(mine: MyPr[]): [NonNullable<MyPr["group"]>, MyPr[]][] {
  const by = new Map<number, [NonNullable<MyPr["group"]>, MyPr[]]>();
  for (const m of mine) {
    if (!m.group) continue;
    if (!by.has(m.group.id)) by.set(m.group.id, [m.group, []]);
    by.get(m.group.id)![1].push(m);
  }
  return [...by.values()];
}

function MyPrItem({ m, act, refresh }: { m: MyPr; act: Act; refresh: ReactNode }) {
  return (
    <List.Item
      icon={m.todo.length ? { source: Icon.XMarkCircle, tintColor: Color.Red } : Icon.Circle}
      title={m.title}
      subtitle={`!${m.id} ${m.repo}`}
      keywords={[String(m.id), m.repo, ...(m.group ? [String(m.group.id)] : [])]}
      accessories={[...agentTags(m.agents), ...myPrTags(m)]}
      actions={
        <ActionPanel>
          <Action.OpenInBrowser url={m.url} />
          <Action
            title="Fiks med agent"
            icon={Icon.Hammer}
            onAction={() => act(`Agent på !${m.id}`, "fleet", ["fix", String(m.id)])}
          />
          <Action
            title="Auto-complete"
            icon={Icon.CheckCircle}
            onAction={() => act(`Auto-complete !${m.id}`, "fleet", ["pr", String(m.id), "auto"])}
          />
          {m.group && <Action.OpenInBrowser title={`Åpne work item #${m.group.id}`} url={m.group.url} />}
          <Common url={m.url} refresh={refresh} />
        </ActionPanel>
      }
    />
  );
}

function ReviewItem({ p, act, refresh }: { p: ReviewPr; act: Act; refresh: ReactNode }) {
  const d = draft(p.id);
  return (
    <List.Item
      icon={d ? { source: Icon.Pencil, tintColor: Color.Yellow } : Icon.Eye}
      title={p.title}
      subtitle={`!${p.id} ${p.repo}`}
      keywords={[String(p.id), p.repo, p.author]}
      accessories={[
        ...(d ? [{ tag: { value: `📝 ${draftLine(d)}`, color: Color.Yellow } }] : []),
        ...agentTags(p.agents),
        { text: `@${p.author.split("@")[0]}` },
      ]}
      actions={
        <ActionPanel>
          {d ? (
            <Action
              title="Post review-utkastet"
              icon={Icon.Upload}
              onAction={() => act(`Poster på !${p.id}`, "wr", ["post", String(p.id)], `Post på !${p.id}: ${draftLine(d)}?`)}
            />
          ) : (
            <Action.OpenInBrowser url={p.url} />
          )}
          {d && <Action.OpenInBrowser url={p.url} />}
          <Action
            title="Review med agent"
            icon={Icon.Eye}
            onAction={() => act(`Review-agent på !${p.id}`, "fleet", ["review", String(p.id)])}
          />
          <Action
            title="Approve"
            icon={Icon.CheckCircle}
            onAction={() => act(`Approve !${p.id}`, "fleet", ["pr", String(p.id), "approve"], `Approve !${p.id}?`)}
          />
          <Common url={p.url} refresh={refresh} />
        </ActionPanel>
      }
    />
  );
}

const STATES = ["To Do", "Doing", "Done"];

function WorkRow({ w, act, refresh }: { w: WorkItem; act: Act; refresh: ReactNode }) {
  const ticket = !!w.status;
  return (
    <List.Item
      icon={ticket ? Icon.Dot : w.state === "Doing" ? Icon.Play : w.kind === "map" ? Icon.Map : Icon.Circle}
      title={w.title}
      subtitle={`#${w.id} ${ticket ? w.status : w.type}`}
      keywords={[String(w.id), w.type]}
      accessories={[
        ...agentTags(w.agents),
        ...(w.hitl ? [{ tag: { value: "HITL", color: Color.Purple } }] : []),
        ...(w.tickets ? [{ text: `${w.tickets.length} åpne, ${w.doneTickets ?? 0} done` }] : []),
        { tag: { value: w.state, color: w.state === "Doing" ? Color.Blue : Color.SecondaryText } },
      ]}
      actions={
        <ActionPanel>
          <Action.OpenInBrowser url={w.url} />
          <Action
            title={`Start agent (${w.prompt.split(" ")[0]})`}
            icon={Icon.Play}
            onAction={() => act(`Agent på #${w.id}`, "fleet", ["go", String(w.id)])}
          />
          <Action
            title="Åpne i VS Code"
            icon={Icon.Code}
            onAction={() => act(`VS Code for #${w.id}`, "fleet", ["code", String(w.id)])}
          />
          <ActionPanel.Submenu title="Sett state" icon={Icon.Pencil} shortcut={{ modifiers: ["cmd"], key: "s" }}>
            {STATES.filter((st) => st !== w.state).map((st) => (
              <Action key={st} title={st} onAction={() => act(`#${w.id} → ${st}`, "fleet", ["wi", String(w.id), "state", st])} />
            ))}
          </ActionPanel.Submenu>
          <Action.CopyToClipboard title="Kopier prompt" content={w.prompt} shortcut={{ modifiers: ["cmd", "shift"], key: "c" }} />
          <Common url={w.url} refresh={refresh} />
        </ActionPanel>
      }
    />
  );
}

function Common({ url, refresh }: { url: string; refresh: ReactNode }) {
  return (
    <ActionPanel.Section>
      <Action.CopyToClipboard title="Kopier lenke" content={url} shortcut={{ modifiers: ["cmd"], key: "." }} />
      <Action
        title="Åpne Ghostty (fleet og agentene)"
        icon={Icon.Terminal}
        shortcut={{ modifiers: ["cmd"], key: "g" }}
        onAction={() => activate("Ghostty")}
      />
      {refresh}
    </ActionPanel.Section>
  );
}

const AGENT: Record<string, [string, Color]> = {
  blocked: ["⏸ venter", Color.Orange],
  running: ["▶ kjører", Color.Green],
  working: ["▶ kjører", Color.Green],
  done: ["✓", Color.SecondaryText],
};

function agentTags(agents: Record<string, AgentState>) {
  return Object.entries(agents ?? {}).map(([role, st]) => {
    const [label, color] = AGENT[st] ?? [st, Color.SecondaryText];
    return { tag: { value: `${role} ${label}`, color } };
  });
}

function myPrTags(m: MyPr) {
  if (m.todo.length) return [{ tag: { value: m.todo.join(", "), color: Color.Red } }];
  if (m.draft) return [{ tag: { value: "draft", color: Color.SecondaryText } }];
  if (m.ready) return [{ tag: { value: "klar", color: Color.Green } }];
  return m.autoComplete ? [{ tag: { value: "auto", color: Color.Blue } }] : [];
}
