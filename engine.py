"""Pure-Python pricing engine (no network).

Football: a Poisson goals model built from API-Sports team statistics prices Over/Under, BTTS,
1X2 and Double Chance. Basketball: a scoring-average model prices totals and the winner.
Every candidate bet blends the model probability with the bookmaker's no-margin probability and
is only kept when the model agrees with (or is more bullish than) the market.
"""
import math
import re

OU_RE = re.compile(r"(over|under)\s*([0-9]+(?:\.[0-9]+)?)", re.I)


# ---------------------------------------------------------------- helpers
def parse_ou(text):
    m = OU_RE.search(str(text or ""))
    return (m.group(1).lower(), float(m.group(2))) if m else (None, None)


def _f(x):
    try:
        return float(str(x).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _dig(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _mean(vals, weights=None):
    weights = weights or [1] * len(vals)
    pairs = [(v, w) for v, w in zip(vals, weights) if v is not None]
    if not pairs:
        return None
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def _obj(resp):
    if isinstance(resp, list):
        return resp[0] if resp and isinstance(resp[0], dict) else None
    return resp if isinstance(resp, dict) else None


def _devig2(a, b):
    """No-margin probability of side A in a two-way market."""
    pa, pb = 1 / a, 1 / b
    return pa / (pa + pb)


def _norm_cdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def p_total_over(lam, line):
    """P(total goals > line) for a half-line, total goals ~ Poisson(lam)."""
    k = int(math.floor(line))
    return max(0.0, min(1.0, 1 - sum(_pmf(i, lam) for i in range(k + 1))))


def score_grid(lh, la, n=10):
    ph = [_pmf(i, lh) for i in range(n + 1)]
    pa = [_pmf(i, la) for i in range(n + 1)]
    home = draw = away = 0.0
    for i, a in enumerate(ph):
        for j, b in enumerate(pa):
            if i > j:
                home += a * b
            elif i == j:
                draw += a * b
            else:
                away += a * b
    total = home + draw + away
    return home / total, draw / total, away / total


# ---------------------------------------------------------------- football model
def football_model(resp):
    """Build the goals model from one item of the API-Sports /predictions response."""
    resp = _obj(resp)
    if not resp:
        return None
    th, ta = _dig(resp, "teams", "home"), _dig(resp, "teams", "away")
    season_h = _mean([_f(_dig(th, "league", "goals", "for", "average", "home")),
                      _f(_dig(ta, "league", "goals", "against", "average", "away"))])
    season_a = _mean([_f(_dig(ta, "league", "goals", "for", "average", "away")),
                      _f(_dig(th, "league", "goals", "against", "average", "home"))])
    if season_h is None or season_a is None:
        return None
    recent_h = _mean([_f(_dig(th, "last_5", "goals", "for", "average")),
                      _f(_dig(ta, "last_5", "goals", "against", "average"))])
    recent_a = _mean([_f(_dig(ta, "last_5", "goals", "for", "average")),
                      _f(_dig(th, "last_5", "goals", "against", "average"))])
    lam_h = _mean([season_h, recent_h], [0.7, 0.3])
    lam_a = _mean([season_a, recent_a], [0.7, 0.3])

    totals = []
    for m in (resp.get("h2h") or [])[:6]:
        g = (m or {}).get("goals") or {}
        h, a = _f(g.get("home")), _f(g.get("away"))
        if h is not None and a is not None:
            totals.append(h + a)
    h2h_avg = round(sum(totals) / len(totals), 2) if totals else None
    if len(totals) >= 3 and lam_h + lam_a > 0:
        scale = (0.85 * (lam_h + lam_a) + 0.15 * h2h_avg) / (lam_h + lam_a)
        lam_h, lam_a = lam_h * scale, lam_a * scale

    lam_h, lam_a = min(max(lam_h, 0.2), 3.5), min(max(lam_a, 0.2), 3.5)
    ph, pd, pa = score_grid(lam_h, lam_a)
    pred = resp.get("predictions") or {}
    return {"lh": round(lam_h, 2), "la": round(lam_a, 2), "exp": round(lam_h + lam_a, 3),
            "btts": round((1 - math.exp(-lam_h)) * (1 - math.exp(-lam_a)), 4),
            "x12": [round(ph, 4), round(pd, 4), round(pa, 4)],
            "h2h_avg": h2h_avg, "h2h_n": len(totals),
            "api_uo": pred.get("under_over"), "advice": str(pred.get("advice") or "")[:80]}


# ---------------------------------------------------------------- candidate construction
def _mk(cat, key, sel, odds, pm, pk, w, offset, min_p, min_odds, max_odds):
    if not (min_odds <= odds <= max_odds):
        return None
    p = min(0.88, w * pm + (1 - w) * pk)
    if p < min_p or pm < pk:  # model must agree with, or be more bullish than, the market
        return None
    conf = round((p - offset) * 20)
    if pm - pk > 0.15:  # model far above the market: be suspicious
        conf -= 1
    conf = max(1, min(9, conf))
    return {"k": key, "c": cat, "s": sel, "o": round(odds, 2), "p": round(p * 100),
            "pm": round(pm * 100), "pk": round(pk * 100), "n": conf,
            "r": "Low" if p >= 0.75 else "Medium" if p >= 0.62 else "High",
            "ev": round(pm * odds - 1, 3)}


def _keep(best, c):
    if not c:
        return
    cur = best.get(c["c"])
    if cur is None or (c["n"], c["ev"]) > (cur["n"], cur["ev"]):
        best[c["c"]] = c


def _ranked(best):
    return sorted(best.values(), key=lambda c: (c["n"], c["p"]), reverse=True)


def football_candidates(odds, model, home, away, min_odds=1.30, max_odds=3.0, min_p=0.60):
    if not odds or not model:
        return []
    best, lam = {}, model["exp"]

    pairs = {}
    for label, odd in (odds.get("Goals O/U") or {}).items():
        d, line = parse_ou(label)
        if d and line is not None and line % 1 == 0.5:
            pairs.setdefault(line, {})[d] = odd
    for line, v in pairs.items():
        if "over" in v and "under" in v:
            pk_over, po = _devig2(v["over"], v["under"]), p_total_over(lam, line)
            for d, pm, pk in (("over", po, pk_over), ("under", 1 - po, 1 - pk_over)):
                cat = d.upper()
                _keep(best, _mk(cat, f"{cat}:{line:g}", f"{d.title()} {line:g} Goals", v[d], pm, pk,
                                0.6, 0.35, min_p, min_odds, max_odds))

    b = odds.get("BTTS") or {}
    if "Yes" in b and "No" in b:
        pk_yes, pm_yes = _devig2(b["Yes"], b["No"]), model["btts"]
        for lab, pm, pk in (("Yes", pm_yes, pk_yes), ("No", 1 - pm_yes, 1 - pk_yes)):
            _keep(best, _mk("BTTS", f"BTTS:{lab.lower()}", f"BTTS {lab}", b[lab], pm, pk,
                            0.6, 0.35, min_p, min_odds, max_odds))

    m = odds.get("1X2") or {}
    sides = ("Home", "Draw", "Away")
    if all(k in m for k in sides):
        inv = {k: 1 / m[k] for k in sides}
        s = sum(inv.values())
        names = {"Home": f"{home} to win", "Draw": "Draw", "Away": f"{away} to win"}
        for k, pm in zip(sides, model["x12"]):
            _keep(best, _mk("1X2", f"1X2:{k.lower()}", names[k], m[k], pm, inv[k] / s,
                            0.6, 0.35, min_p, min_odds, max_odds))

    d = odds.get("Double Chance") or {}
    dkeys = ("Home/Draw", "Draw/Away", "Home/Away")
    if all(k in d for k in dkeys):
        inv = {k: 1 / d[k] for k in dkeys}
        s = sum(inv.values()) / 2
        ph, pd, pa = model["x12"]
        pm = {"Home/Draw": ph + pd, "Draw/Away": pd + pa, "Home/Away": ph + pa}
        names = {"Home/Draw": f"{home} or Draw", "Draw/Away": f"Draw or {away}", "Home/Away": f"{home} or {away}"}
        for k in dkeys:
            _keep(best, _mk("DOUBLE_CHANCE", f"DC:{k.lower().replace('/', '_')}", names[k], d[k],
                            min(pm[k], 0.97), min(inv[k] / s, 0.97), 0.6, 0.35, min_p,
                            min(min_odds, 1.15), max_odds))
    return _ranked(best)


# ---------------------------------------------------------------- basketball model
def basketball_profile(resp):
    """Scoring averages of one team from the API-Sports basketball team statistics response."""
    r = _obj(resp)
    if not r:
        return {}
    paths = {"for_home": ("points", "for", "average", "home"), "for_away": ("points", "for", "average", "away"),
             "ag_home": ("points", "against", "average", "home"), "ag_away": ("points", "against", "average", "away")}
    out = {}
    for key, path in paths.items():
        v = _f(_dig(r, *path))
        if v is None:
            v = _f(_dig(r, *path[:-1], "all"))
        if v is not None:
            out[key] = v
    return out if len(out) == 4 else {}


def basketball_model(home_profile, away_profile):
    if not home_profile or not away_profile:
        return None
    eh = (home_profile["for_home"] + away_profile["ag_away"]) / 2
    ea = (away_profile["for_away"] + home_profile["ag_home"]) / 2
    total = eh + ea
    if not 90 <= total <= 320:
        return None
    return {"eh": round(eh, 1), "ea": round(ea, 1), "total": round(total, 1),
            "sd_total": round(max(10.0, 0.085 * total), 1), "sd_diff": 12.0}


def basketball_candidates(odds, model, home, away, min_odds=1.30, max_odds=3.0, min_p=0.56, min_gap=4.0):
    if not odds or not model:
        return []
    best = {}
    pairs = {}
    for label, odd in (odds.get("Total O/U") or {}).items():
        d, line = parse_ou(label)
        if d and line is not None:
            pairs.setdefault(line, {})[d] = odd
    for line, v in pairs.items():
        if "over" in v and "under" in v and abs(model["total"] - line) >= min_gap:
            pk_over = _devig2(v["over"], v["under"])
            po = 1 - _norm_cdf((line - model["total"]) / model["sd_total"])
            for d, pm, pk in (("over", po, pk_over), ("under", 1 - po, 1 - pk_over)):
                cat = "BB_" + d.upper()
                _keep(best, _mk(cat, f"{cat}:{line:g}", f"{d.title()} {line:g} Points", v[d], pm, pk,
                                0.5, 0.30, min_p, min_odds, max_odds))
    w = odds.get("Home/Away") or {}
    if "Home" in w and "Away" in w:
        pk_home = _devig2(w["Home"], w["Away"])
        pm_home = _norm_cdf((model["eh"] - model["ea"]) / model["sd_diff"])
        for side, name, pm, pk in (("Home", home, pm_home, pk_home), ("Away", away, 1 - pm_home, 1 - pk_home)):
            _keep(best, _mk("BB_WINNER", f"BB_WINNER:{side.lower()}", f"{name} to win", w[side], pm, pk,
                            0.5, 0.30, min_p, min_odds, max_odds))
    return _ranked(best)
