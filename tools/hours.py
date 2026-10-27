"""
Opening hours and date windows, from content/hours.json.

Everything the site says about hours comes from here: the footer, the Visit
table, the homepage line, schema.org data and the <meta name="layers-hours">
payload the "Open now" script reads. Times in the content are 24h "HH:MM";
days are named ("monday" … "sunday").

Special (holiday) hours override the weekly hours on their date. The next 60
days of them are listed on the Visit page, sent to search engines
(specialOpeningHoursSpecification) and added to the open-now payload as a
"special" map keyed by date, which main.js checks before the weekly hours.

Also the small date helpers every date-driven feature shares (announcement,
specials, events, special hours), so they all agree on what "today" means:
the shop's local date in Berkeley.
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

SHOP_TZ = ZoneInfo("America/Los_Angeles")

# Display order (Monday first) and the JS day numbers (0 = Sunday).
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DOW = {"sunday": 0, "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6}
SHORT = {d: d[:3].capitalize() for d in DAYS}
LONG = {d: d.capitalize() for d in DAYS}


def shop_today():
    """Today's date in Berkeley (the build server may run in UTC)."""
    return dt.datetime.now(SHOP_TZ).date()


def parse_time(s):
    """'09:00' -> minutes after midnight; None when empty or malformed."""
    try:
        h, m = str(s).split(":")
        if len(m) != 2 or not (h.isdigit() and m.isdigit()):
            return None
        h, m = int(h), int(m)
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def parse_date(s):
    """'2026-11-26' -> date; None when empty or malformed."""
    try:
        return dt.date.fromisoformat(str(s)) if s else None
    except ValueError:
        return None


def in_window(today, starts="", ends=""):
    """True when today is within [starts, ends]; an empty end is open-ended."""
    a, b = parse_date(starts), parse_date(ends)
    return (a is None or a <= today) and (b is None or today <= b)


def t12(t):
    """'09:00' -> '9am', '18:30' -> '6:30pm'."""
    mins = parse_time(t)
    h, m = divmod(mins, 60)
    suf = "am" if h < 12 else "pm"
    h = h % 12 or 12
    return f"{h}{suf}" if m == 0 else f"{h}:{m:02d}{suf}"


def _key(day):
    """What makes two days 'the same' for grouping: closed, or the same span."""
    return ("closed",) if day.get("closed") else (parse_time(day["open"]), parse_time(day["close"]))


def span(day):
    return "Closed" if day.get("closed") else f"{t12(day['open'])}–{t12(day['close'])}"


def groups(weekly):
    """[("Mon–Fri", "9am–6pm"), ("Sat–Sun", "9am–4pm")] — consecutive equal days merged."""
    out = []
    for d in DAYS:
        if out and _key(weekly[d]) == _key(weekly[out[-1][-1]]):
            out[-1].append(d)
        else:
            out.append([d])
    return [((SHORT[g[0]] if len(g) == 1 else f"{SHORT[g[0]]}–{SHORT[g[-1]]}"), span(weekly[g[0]])) for g in out]


def line(weekly):
    """'Mon–Fri 9am–6pm · Sat–Sun 9am–4pm' (homepage, FAQ)."""
    return " · ".join(f"{d} {t}" for d, t in groups(weekly))


def meta(weekly, special=()):
    """The open-now script's payload: {"1": [open, close] minutes, …}, 0 = Sunday.
    Closed days are left out, which the script reads as closed. Special days
    (upcoming_special) add {"special": {"2026-11-26": null | [open, close]}};
    the key is absent when there are none, so the payload is unchanged."""
    order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    out = {str(DOW[d]): [parse_time(weekly[d]["open"]), parse_time(weekly[d]["close"])]
           for d in order if not weekly[d].get("closed")}
    if special:
        out["special"] = {s["date"]: _special_span(s) for s in special}
    return json.dumps(out, separators=(",", ":"))


def _special_span(s):
    """[open, close] minutes for a special day, None when it's closed all day."""
    o, c = parse_time(s.get("open")), parse_time(s.get("close"))
    return None if s.get("closed") or o is None or c is None else [o, c]


def table_rows(weekly):
    """[(js day number, "Monday", "9am–6pm"), …] for the Visit table, Monday first."""
    return [(DOW[d], LONG[d], span(weekly[d])) for d in DAYS]


def jsonld(weekly):
    """schema.org OpeningHoursSpecification, one entry per distinct span."""
    spec = {}
    for d in DAYS:
        day = weekly[d]
        if day.get("closed"):
            continue
        spec.setdefault((day["open"], day["close"]), []).append(LONG[d])
    return [{"@type": "OpeningHoursSpecification", "dayOfWeek": days,
             "opens": _hhmm(o), "closes": _hhmm(c)} for (o, c), days in spec.items()]


def _hhmm(t):
    h, m = divmod(parse_time(t), 60)
    return f"{h:02d}:{m:02d}"


def upcoming_special(hours, today, days=60):
    """Special/holiday hours from today through the next `days` days, by date."""
    end = today + dt.timedelta(days=days)
    out = [s for s in hours.get("special", []) if (d := parse_date(s.get("date"))) and today <= d <= end]
    return sorted(out, key=lambda s: s["date"])


def jsonld_special(special):
    """schema.org specialOpeningHoursSpecification for upcoming special days.
    A day closed all day is 00:00–00:00, the form Google documents."""
    out = []
    for s in special:
        span = _special_span(s)
        opens, closes = ("00:00", "00:00") if span is None else (_hhmm(s["open"]), _hhmm(s["close"]))
        out.append({"@type": "OpeningHoursSpecification", "validFrom": s["date"], "validThrough": s["date"],
                    "opens": opens, "closes": closes})
    return out


def special_rows(special):
    """[(date, "Thu, Nov 26", "Thanksgiving", "Closed" | "10am–2pm"), …] for the Visit page."""
    rows = []
    for s in special:
        d = parse_date(s["date"])
        span = _special_span(s)
        rows.append((s["date"], f"{d:%a}, {d:%b} {d.day}", (s.get("label") or "").strip(),
                     "Closed" if span is None else f"{t12(s['open'])}–{t12(s['close'])}"))
    return rows
