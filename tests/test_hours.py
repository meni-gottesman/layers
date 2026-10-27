"""Opening hours and date windows (tools/hours.py)."""
import datetime as dt

import hours
from conftest import seed_content

WEEKLY = seed_content("hours.json")["weekly"]          # the frozen seed, never the live hours


def week(**over):
    w = {d: {"closed": False, "open": "09:00", "close": "18:00"} for d in hours.DAYS}
    w.update(over)
    return w


def test_today_seed_renders_like_the_old_site():
    assert hours.line(WEEKLY) == "Mon–Fri 9am–6pm · Sat–Sun 9am–4pm"
    assert hours.groups(WEEKLY) == [("Mon–Fri", "9am–6pm"), ("Sat–Sun", "9am–4pm")]
    # same payload, same key order as before (main.js reads it)
    assert hours.meta(WEEKLY) == '{"1":[540,1080],"2":[540,1080],"3":[540,1080],"4":[540,1080],"5":[540,1080],"6":[540,960],"0":[540,960]}'
    assert hours.jsonld(WEEKLY) == [
        {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
         "opens": "09:00", "closes": "18:00"},
        {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Saturday", "Sunday"], "opens": "09:00", "closes": "16:00"}]


def test_t12():
    assert hours.t12("09:00") == "9am"
    assert hours.t12("12:00") == "12pm"
    assert hours.t12("00:30") == "12:30am"
    assert hours.t12("18:30") == "6:30pm"


def test_closed_day():
    w = week(sunday={"closed": True, "open": "", "close": ""})
    assert hours.line(w) == "Mon–Sat 9am–6pm · Sun Closed"
    assert '"0"' not in hours.meta(w)                 # the open-now script reads "missing" as closed
    assert hours.table_rows(w)[-1] == (0, "Sunday", "Closed")
    assert all("Sunday" not in s["dayOfWeek"] for s in hours.jsonld(w))


def test_only_consecutive_days_merge():
    w = week(wednesday={"closed": False, "open": "10:00", "close": "18:00"})
    assert hours.line(w) == "Mon–Tue 9am–6pm · Wed 10am–6pm · Thu–Sun 9am–6pm"


def test_parse_time_and_date():
    assert hours.parse_time("09:05") == 545
    for bad in ("9am", "24:00", "12:60", "", None, "9:5"):
        assert hours.parse_time(bad) is None, bad
    assert hours.parse_date("2026-11-26") == dt.date(2026, 11, 26)
    assert hours.parse_date("2026-02-30") is None
    assert hours.parse_date("") is None


def test_date_window_is_inclusive_and_open_ended():
    d = dt.date(2026, 11, 1)
    assert hours.in_window(d, "", "")
    assert hours.in_window(d, "2026-11-01", "2026-11-01")
    assert hours.in_window(d, "2026-10-01", "")
    assert hours.in_window(d, "", "2026-12-01")
    assert not hours.in_window(d, "2026-11-02", "")
    assert not hours.in_window(d, "", "2026-10-31")


def test_upcoming_special_hours_next_60_days():
    h = {"special": [
        {"date": "2026-12-25", "label": "Christmas", "closed": True},
        {"date": "2026-11-26", "label": "Thanksgiving", "closed": True},
        {"date": "2026-10-01", "label": "Past", "closed": True},
        {"date": "2027-03-01", "label": "Too far", "closed": True},
        {"date": "not a date", "label": "Broken", "closed": True},
    ]}
    got = hours.upcoming_special(h, dt.date(2026, 10, 27))
    assert [s["label"] for s in got] == ["Thanksgiving", "Christmas"]
    assert [s["label"] for s in hours.upcoming_special(h, dt.date(2026, 11, 26), days=0)] == ["Thanksgiving"]
