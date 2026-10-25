#!/usr/bin/env python3

# @raycast.schemaVersion 1
# @raycast.title Fleet
# @raycast.mode inline
# @raycast.refreshTime 1m
# @raycast.icon 🚢
# @raycast.packageName Visense

# One line in Raycast's root search from fleet's ~/.cache/fleet/state.json: what needs
# me. Agents waiting for me, my PRs with something to fix, PRs waiting for my review
# (how many of them have a review draft ready). Nothing is fetched here; when fleet
# hasn't written for a while the line says so instead.

import datetime
import json
import os

STALE = 10 * 60  # seconds; fleet rewrites state.json on every refresh

try:
    with open(os.path.expanduser("~/.cache/fleet/state.json")) as f:
        s = json.load(f)
except (OSError, ValueError):
    raise SystemExit(print("fleet har ikke kjørt"))

updated = datetime.datetime.fromisoformat(s["updated"])
age = (datetime.datetime.now().astimezone() - updated).total_seconds()

parts = []
blocked = [n for n, st in (s.get("agents") or {}).items() if st == "blocked"]
if blocked:
    parts.append(f"⏸ {len(blocked)} agent{'er' if len(blocked) > 1 else ''} venter")
for m in s.get("myPullRequests", []):
    if m.get("todo"):
        parts.append(f"✗ !{m['id']} {', '.join(m['todo'])}")
review = [p for p in s.get("pullRequests", []) if p.get("imReviewer") and not p.get("myVote")]
if review:
    drafts = sum(1 for p in review if (p.get("agents") or {}).get("review") == "done")
    parts.append(f"{len(review)} til review" + (f" ({drafts} 📝)" if drafts else ""))
running = sum(1 for st in (s.get("agents") or {}).values() if st in ("running", "working"))
if running:
    parts.append(f"▶ {running} kjører")
if s.get("error"):
    parts.insert(0, "FEIL i fleet")

line = " · ".join(parts) or "ingenting venter ✓"
if age > STALE:
    when = f"{updated:%H:%M}" if updated.date() == datetime.date.today() else f"{updated:%d.%m %H:%M}"
    line = f"fleet kjører ikke (sist {when}) · {line}"
print(line)
