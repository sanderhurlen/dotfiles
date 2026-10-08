#!/usr/bin/env python3
"""PROTOTYPE — throwaway. Triage + utkast via `claude -p`, haiku vs sonnet, side-by-side HTML report.

Run: python3 run.py [--models haiku,sonnet] [--only id1,id2]
Output: results.json, report.html (same dir).
"""
import asyncio, json, os, sys, tempfile, time, html
from pathlib import Path

HER = Path(__file__).parent
TRÅDER = json.loads((HER / "threads.json").read_text())
KB = (HER / "kb.md").read_text()

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "kategori": {"type": "string", "enum": ["svar", "info"]},
        "haster": {"type": "boolean"},
        "sammendrag": {"type": "string"},
        "begrunnelse": {"type": "string"},
    },
    "required": ["kategori", "haster", "sammendrag", "begrunnelse"],
}
UTKAST_SCHEMA = {
    "type": "object",
    "properties": {
        "tekst": {"type": "string"},
        "sjekk": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tekst", "sjekk"],
}


def render(t):
    linjer = [f"Kanal: {t['kanal']}", f"Emne: {t['emne']}", ""]
    for m in t["meldinger"]:
        hvem = "Sander (meg)" if m["fra_meg"] else m["fra"]
        linjer.append(f"--- {m['tid']} fra {hvem}" + (f" til {m['til']}" if m["til"] else "") + (f" cc {m['cc']}" if m["cc"] else ""))
        linjer.append(m["tekst"])
        linjer.append("")
    return f"<kunnskapsbase>\n{KB}\n</kunnskapsbase>\n\n<tråd>\n" + "\n".join(linjer) + "</tråd>"


def ren_env():
    return {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_CODE", "CLAUDECODE"))}


async def kall(sem, modell, systemfil, schema, prompt, nøytral):
    async with sem:
        t0 = time.monotonic()
        p = await asyncio.create_subprocess_exec(
            "claude", "-p", "--model", modell.split(":")[0],
            *(["--effort", modell.split(":")[1]] if ":" in modell else []),
            "--output-format", "json", "--json-schema", json.dumps(schema),
            "--system-prompt-file", str(HER / systemfil),
            "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
            "--permission-prompts", "none", "--no-session-persistence",
            "--max-turns", "3", "--max-budget-usd", "0.25", "--tools", "",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=nøytral, env=ren_env(),
        )
        try:
            out, err = await asyncio.wait_for(p.communicate(prompt.encode()), 180)
        except asyncio.TimeoutError:
            p.kill()
            return {"feil": "timeout", "sek": round(time.monotonic() - t0, 1)}
        sek = round(time.monotonic() - t0, 1)
        try:
            r = json.loads(out)
        except Exception:
            return {"feil": (err or out).decode()[-500:], "sek": sek}
        if r.get("subtype") != "success" or r.get("structured_output") is None:
            return {"feil": r.get("subtype") or r.get("result"), "sek": sek}
        return {"svar": r["structured_output"], "sek": sek, "usd": round(r.get("total_cost_usd", 0), 4),
                "tokens": r.get("usage", {})}


async def main():
    args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    modeller = args.get("--models", "haiku,haiku:low,sonnet").split(",")
    only = set(args["--only"].split(",")) if "--only" in args else None
    tråder = [t for t in TRÅDER if not only or t["id"] in only]
    sem = asyncio.Semaphore(4)
    nøytral = tempfile.mkdtemp(prefix="tower-proto-")
    jobber = {}
    for m in modeller:
        for t in tråder:
            prompt = render(t)
            jobber[(m, "triage", t["id"])] = kall(sem, m, "triage.md", TRIAGE_SCHEMA, prompt, nøytral)
            if t["forventet"]["kategori"] == "svar":
                jobber[(m, "utkast", t["id"])] = kall(sem, m, "utkast.md", UTKAST_SCHEMA, prompt, nøytral)
    svar = await asyncio.gather(*jobber.values())
    res = {}
    for (m, steg, tid), r in zip(jobber, svar):
        res.setdefault(tid, {}).setdefault(steg, {})[m] = r
        print(f"{m:7} {steg:7} {tid:22} {r.get('sek')}s ${r.get('usd')} {r.get('feil') or ''}", flush=True)
    (HER / "results.json").write_text(json.dumps({"modeller": modeller, "res": res}, ensure_ascii=False, indent=1))
    rapport(modeller, tråder, res)


def rapport(modeller, tråder, res):
    e = html.escape
    def celle(r, steg):
        if not r:
            return "<td>–</td>"
        meta = f"<div class=meta>{r.get('sek')}s · ${r.get('usd', '?')}</div>"
        if "feil" in r:
            return f"<td class=feil>FEIL: {e(str(r['feil']))}{meta}</td>"
        s = r["svar"]
        if steg == "triage":
            return f"<td><b>{s['kategori']}</b>{' · <b class=hast>haster</b>' if s['haster'] else ''}<br>{e(s['sammendrag'])}<br><i>{e(s['begrunnelse'])}</i>{meta}</td>"
        sj = "".join(f"<li>{e(x)}</li>" for x in s["sjekk"])
        return f"<td><pre>{e(s['tekst'])}</pre>{'<ul class=sjekk>' + sj + '</ul>' if sj else ''}{meta}</td>"

    total = {m: sum(res[t][s][m].get("usd", 0) or 0 for t in res for s in res[t] if m in res[t][s]) for m in modeller}
    rader = []
    for t in tråder:
        r = res.get(t["id"], {})
        f = t["forventet"]
        tråd = "".join(
            f"<div class='msg{' meg' if m['fra_meg'] else ''}'><div class=meta>{e(m['tid'])} · {e(m['fra'])}</div><pre>{e(m['tekst'])}</pre></div>"
            for m in t["meldinger"])
        hdr = "".join(f"<th>{m}</th>" for m in modeller)
        rader.append(f"""<section><h2>{e(t['emne'])} <small>{t['kanal']} · forventet: {f['kategori']}{' · haster' if f['haster'] else ''}</small></h2>
<details><summary>Tråd ({len(t['meldinger'])} meldinger)</summary>{tråd}</details>
<table><tr><th></th>{hdr}</tr>
<tr><th>Triage</th>{''.join(celle(r.get('triage', {}).get(m), 'triage') for m in modeller)}</tr>
{'<tr><th>Utkast</th>' + ''.join(celle(r.get('utkast', {}).get(m), 'utkast') for m in modeller) + '</tr>' if 'utkast' in r else ''}
</table></section>""")
    (HER / "report.html").write_text(f"""<!doctype html><meta charset=utf-8><title>Utkast-agent prototype</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--card:#f5f5f2;--line:#ddd;--hl:#e8f0ff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16161a;--fg:#e6e6e6;--mut:#999;--card:#222228;--line:#333;--hl:#1e2a40}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui;max-width:1200px;margin:auto;padding:16px}}
h2 small{{color:var(--mut);font-weight:normal;font-size:13px}} table{{width:100%;border-collapse:collapse;table-layout:fixed}}
td,th{{border:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}} th:first-child{{width:70px}}
pre{{white-space:pre-wrap;font:14px/1.45 ui-monospace,monospace;margin:0}} .meta{{color:var(--mut);font-size:12px;margin-top:4px}}
.msg{{background:var(--card);padding:8px;margin:6px 0;border-radius:6px}} .msg.meg{{background:var(--hl)}}
.feil{{color:#c33}} .hast{{color:#d60}} .sjekk{{color:#b70;font-size:13px}} section{{margin-bottom:32px}}
</style>
<h1>PROTOTYPE · triage + utkast</h1><p>Kost (estimat): {' · '.join(f'{m} ${v:.3f}' for m, v in total.items())}</p>
{''.join(rader)}""")
    print("report:", HER / "report.html")


if __name__ == "__main__":
    asyncio.run(main())
