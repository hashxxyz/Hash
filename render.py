"""Turns structured picks into a clean Telegram (HTML) message. No markdown tables."""
import html
import re
from datetime import datetime

LINE = "━━━━━━━━━━━━━━"

SECTIONS = [
    ("OVER", "📈 OVER GOALS"),
    ("CORNERS", "🚩 CORNERS"),
    ("1X2", "🏁 1X2 · MATCH RESULT"),
    ("DOUBLE_CHANCE", "🛡 DOUBLE CHANCE"),
    ("UNDER", "📉 UNDER GOALS"),
    ("FIRST_HALF", "⏱ 1ST HALF"),
    ("BTTS", "⚽ BOTH TEAMS TO SCORE"),
    ("BASKETBALL", "🏀 BASKETBALL"),
]
ALL = [k for k, _ in SECTIONS]
FOOTBALL_ONLY = [k for k in ALL if k != "BASKETBALL"]

MODE_SECTIONS = {
    "tips": ALL, "football": FOOTBALL_ONLY, "basketball": ["BASKETBALL"],
    "safe": ALL, "acca": ALL,
    "goals": ["OVER", "UNDER", "FIRST_HALF"], "btts": ["BTTS"],
    "over": ["OVER"], "under": ["UNDER"], "corners": ["CORNERS"],
    "1x2": ["1X2"], "dc": ["DOUBLE_CHANCE"], "firsthalf": ["FIRST_HALF"],
}

MODE_TITLES = {
    "tips": "ALL STRONG PICKS", "football": "FOOTBALL PICKS", "basketball": "BASKETBALL PICKS",
    "safe": "SAFE PICKS", "acca": "ACCUMULATOR (MAX 3 LEGS)", "goals": "GOALS PICKS",
    "btts": "BTTS PICKS", "over": "OVER PICKS", "under": "UNDER PICKS", "corners": "CORNERS PICKS",
    "1x2": "1X2 PICKS", "dc": "DOUBLE CHANCE PICKS", "firsthalf": "1ST HALF PICKS",
}

MAX_PER_SECTION = 8


def esc(x):
    return html.escape(str(x), quote=False)


def pick_block(i, p):
    odds = f"  @ {p['odds']:.2f}" if p.get("odds") else ""
    lines = [f"<b>{i}. {esc(p['match'])}</b>"]
    meta = f"🏆 {esc(p['league'])}" if p.get("league") else ""
    if p.get("kickoff"):
        meta += f"  ·  ⏰ {esc(p['kickoff'])}"
    if meta:
        lines.append(meta)
    lines.append(f"🎯 <b>{esc(p['selection'])}</b>{odds}")
    lines.append(f"📊 {p['probability']}%  ·  ⭐ {p['confidence']}/10  ·  ⚠️ {esc(p['risk'])}")
    return "\n".join(lines)


def _header(mode, date):
    try:
        pretty = datetime.strptime(date, "%Y-%m-%d").strftime("%a %d %b %Y")
    except ValueError:
        pretty = date
    return f"🔥 <b>AI BETTING GURU</b>\n<b>{MODE_TITLES.get(mode, 'PICKS')}</b>\n📅 {pretty}  ·  times in Lagos (WAT)"


FOOTER = "⚠️ <i>Probability-based analysis, not guaranteed results. Bet responsibly.</i>"


def render_report(picks, avoid, mode, date, notes=None):
    out = [_header(mode, date)]

    if mode == "acca":
        legs, used = [], set()
        for p in sorted(picks, key=lambda p: (p["confidence"], p["probability"]), reverse=True):
            if p["risk"] == "High" or p["match_id"] in used:
                continue
            legs.append(p)
            used.add(p["match_id"])
            if len(legs) == 3:
                break
        if not legs:
            out.append("\nNo accumulator is strong enough today. Better to skip than force it.")
        else:
            out.append("\n" + LINE)
            for i, p in enumerate(legs, 1):
                out.append(pick_block(i, p) + "\n")
            known = [p["odds"] for p in legs if p.get("odds")]
            if len(known) == len(legs):
                total = 1.0
                for o in known:
                    total *= o
                out.append(f"💰 Combined odds ≈ <b>{total:.2f}</b>")
            prob = 1.0
            for p in legs:
                prob *= p["probability"] / 100
            out.append(f"📊 Rough combined chance ≈ {round(prob * 100)}% (legs treated as independent)")
    else:
        shown = 0
        for key, title in SECTIONS:
            if key not in MODE_SECTIONS.get(mode, ALL):
                continue
            items = [p for p in picks if p["category"] == key]
            items.sort(key=lambda p: (p["confidence"], p["probability"]), reverse=True)
            items = items[:MAX_PER_SECTION]
            out.append(f"\n<b>{title}</b>  ({len(items)})\n{LINE}")
            if not items:
                out.append("<i>No strong pick today.</i>")
                continue
            for i, p in enumerate(items, 1):
                out.append(pick_block(i, p) + "\n")
                shown += 1
        if avoid and mode in {"tips", "football"}:
            out.append(f"\n🚫 <b>AVOID</b>\n{LINE}")
            for a in avoid[:4]:
                out.append(f"• {esc(a['match'])}")
        if not shown:
            out.append("\nNo pick passed the strength filter today. Try again closer to kick-off.")

    if notes:
        out.append("\nℹ️ " + esc(" ".join(notes)))
    out.append("\n" + FOOTER)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))
