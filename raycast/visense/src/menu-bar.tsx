// The menu bar item: a count of what needs me (agents waiting, my PRs with something to
// fix, review drafts to post), and a menu with every row. Reads state.json every minute;
// nothing is fetched here. When fleet hasn't written for a while the menu says so and
// offers `fleet ls`.

import { Color, Icon, LaunchType, MenuBarExtra, launchCommand, open, showHUD } from "@raycast/api";
import { activate, draft, draftLine, needs, readState, run, stale, when } from "./state";

const agentRow = (name: string) => name.match(/^fleet-(pr|wi)-(\d+)-(\w+)$/);

export default function Command() {
  const s = readState();
  if (!s) {
    return (
      <MenuBarExtra icon={Icon.Boat} tooltip="fleet har ikke kjørt">
        <MenuBarExtra.Item title="fleet har ikke kjørt" />
        <Refresh />
      </MenuBarExtra>
    );
  }
  const n = needs(s);
  const old = stale(s);
  const attention = n.count > 0 || !!s.error;

  return (
    <MenuBarExtra
      icon={{ source: Icon.Boat, tintColor: attention ? Color.Orange : undefined }}
      title={n.count ? String(n.count) : undefined}
      tooltip={old ? `fleet kjører ikke (sist ${when(s.updated)})` : "fleet"}
    >
      {(old || s.error) && (
        <MenuBarExtra.Section>
          {s.error && <MenuBarExtra.Item icon={Icon.Warning} title={`FEIL: ${s.error}`} />}
          {old && <MenuBarExtra.Item icon={Icon.Warning} title={`fleet kjører ikke (sist ${when(s.updated)})`} />}
          {old && <Refresh />}
        </MenuBarExtra.Section>
      )}

      {n.blocked.length > 0 && (
        <MenuBarExtra.Section title="Agenter som venter på meg">
          {n.blocked.map((name) => {
            const m = agentRow(name);
            return (
              <MenuBarExtra.Item
                key={name}
                icon={Icon.Pause}
                title={m ? `${m[1] === "pr" ? "!" : "#"}${m[2]} ${m[3]}` : name}
                tooltip="Åpner Ghostty, der fleet og agentene er"
                onAction={() => activate("Ghostty")}
              />
            );
          })}
        </MenuBarExtra.Section>
      )}

      {s.myPullRequests.length > 0 && (
        <MenuBarExtra.Section title="Mine PRer">
          {s.myPullRequests.map((m) => (
            <MenuBarExtra.Item
              key={m.id}
              icon={m.todo.length ? { source: Icon.XMarkCircle, tintColor: Color.Red } : Icon.Circle}
              title={`!${m.id} ${m.title}`}
              subtitle={m.todo.length ? m.todo.join(", ") : m.draft ? "draft" : m.ready ? "klar" : ""}
              onAction={() => open(m.url)}
            />
          ))}
        </MenuBarExtra.Section>
      )}

      {n.review.length > 0 && (
        <MenuBarExtra.Section title="Til review">
          {n.review.map((p) => {
            const d = draft(p.id);
            return (
              <MenuBarExtra.Item
                key={p.id}
                icon={d ? { source: Icon.Pencil, tintColor: Color.Yellow } : Icon.Eye}
                title={`!${p.id} ${p.title}`}
                subtitle={d ? `📝 ${draftLine(d)}` : `@${p.author.split("@")[0]}`}
                onAction={() => open(p.url)}
              />
            );
          })}
        </MenuBarExtra.Section>
      )}

      {s.workItems.length > 0 && (
        <MenuBarExtra.Section title="Work items">
          {s.workItems.map((w) => (
            <MenuBarExtra.Item
              key={w.id}
              icon={w.state === "Doing" ? Icon.Play : w.kind === "map" ? Icon.Map : Icon.Circle}
              title={`#${w.id} ${w.title}`}
              subtitle={w.state}
              onAction={() => open(w.url)}
            />
          ))}
        </MenuBarExtra.Section>
      )}

      <MenuBarExtra.Section>
        {n.running > 0 && <MenuBarExtra.Item icon={Icon.Play} title={`${n.running} agenter kjører`} />}
        <MenuBarExtra.Item
          icon={Icon.List}
          title="Åpne fleet-lista"
          shortcut={{ modifiers: ["cmd"], key: "l" }}
          onAction={() => launchCommand({ name: "fleet", type: LaunchType.UserInitiated })}
        />
        <MenuBarExtra.Item
          icon={Icon.Plus}
          title="Nytt work item"
          shortcut={{ modifiers: ["cmd"], key: "n" }}
          onAction={() => launchCommand({ name: "wi-new", type: LaunchType.UserInitiated })}
        />
      </MenuBarExtra.Section>
    </MenuBarExtra>
  );
}

function Refresh() {
  return (
    <MenuBarExtra.Item
      icon={Icon.ArrowClockwise}
      title="Hent nå (fleet ls)"
      onAction={async () => {
        await showHUD("Henter fleet …");
        try {
          await run("fleet", ["ls"]);
          await launchCommand({ name: "menu-bar", type: LaunchType.Background });
        } catch (e) {
          await showHUD(`fleet ls feilet: ${(e as Error).message}`);
        }
      }}
    />
  );
}
