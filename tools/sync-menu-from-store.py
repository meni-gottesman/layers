#!/usr/bin/env python3
"""Refresh the menu from Layers' public Square Online store — no credentials.

    python3 tools/sync-menu-from-store.py            # fetch live, write data
    python3 tools/sync-menu-from-store.py --offline  # re-parse the cached JSON

Writes data/menu-fallback.json (and the copy served at
/assets/data/menu-fallback.json). The build renders the static menu from it,
and /api/menu serves it until a Square access token is configured.
tools/build.py runs it with --offline on every build, so edits to
content/menu.json show up without fetching anything.

content/menu.json decides how each Square item is shown: its name and note on
the site (empty = Square's), a photo (empty = Square's), crop focus/zoom, and
whether it is hidden. The order of the list is the order within each category.
A live run appends items Square has added since (with empty fields, so they
show as Square has them) and refreshes the read-only square_name/category,
keeping everything the manager changed. Items Square no longer lists are left
in the file and skipped, with a warning.

What it keeps from Square, verbatim: names, prices, calories, ingredients,
macros and the allergen sentences in each item's description. What it
deliberately drops: Square's dietary-preference tags — several contradict the
item's own allergen line (e.g. "nut-free" on bowls whose crumble contains tree
nuts), and a wrong allergen badge is worse than none.

Photos: each item's photo comes from content/menu.json when one is set there
(e.g. a sharper studio original), otherwise from Square's upload, saved to
src-img/menu/ so build-home-media.py can make the web sizes. A Square photo
stays tied to its item id, so renaming an item on the site keeps its photo.

Each card's photo slot is named after the name shown on the site
("menu/pink-pink-pink"). Two cards never share a slot: when two shown names
give the same slug (a rename that copies another item's name), the item whose
own Square name it is keeps it and the other gets a short id suffix; a name
with no letters or digits ("★★★") gets "item-<id>".

Hidden items are left out of the menu, and their ids are listed under
"hidden" in the output, so the live Square data (/api/menu, main.js) can't
bring them back.
"""
import html
import json
import pathlib
import re
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from content import dump_cms_json  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = "https://layerssuperfoodbar.square.site"
API = (STORE + "/app/store/api/v28/editor/users/152630010/sites/672900839876723331"
       "/products?per_page=200&page=1&include=images,categories")
CACHE = ROOT / "data" / "square-store-products.json"
OUT = [ROOT / "data" / "menu-fallback.json", ROOT / "public" / "assets" / "data" / "menu-fallback.json"]
MENU_CONTENT = ROOT / "content" / "menu.json"
SLOT_SPECS = ROOT / "src-img" / "slot-specs.json"
IMG_DIR = ROOT / "src-img" / "menu"

CATEGORIES = [  # Square category -> (display name, card kind, render style)
    ("Layers Bowls", "Bowls", "Bowl", "cards"),
    ("Layers Smoothies", "Smoothies", "Smoothie", "cards"),
    ("Layers Wellness Market", "Wellness Market", "Market", "list"),
]
UA = {"User-Agent": "Mozilla/5.0 (layers-site menu sync)"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower().replace("’", "").replace("'", "")).strip("-")


def tidy(s):
    s = re.sub(r"\s+", " ", s).strip(" •·:-").rstrip(".")
    s = re.sub(r"\(\s+", "(", s)
    return s.replace(" .", ".").replace("( ", "(")


def split_items(s):
    parts = re.split(r"\s*[•,]\s*", s)
    return [tidy(p) for p in parts if tidy(p)]


def split_name(raw):
    """'Recovery Bowl - 40g Protein (Icy Textures)' -> ('Recovery Bowl', '40g Protein')."""
    raw = re.sub(r"\s+", " ", raw).strip()
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*(?:-\s*(.*))?$", raw)
    if m and not m.group(1).endswith("-"):
        name, paren, tail = m.group(1), m.group(2), m.group(3)
        if " - " in name:
            name, tail2 = name.split(" - ", 1)
            return name.strip(), tidy(tail2)
        note = " · ".join(x for x in (paren, tail) if x)
        return name.strip(), tidy(note)
    if " - " in raw:
        name, note = raw.split(" - ", 1)
        return name.strip(), tidy(note.replace("/", " · "))
    return raw, ""


def parse_description(desc_html):
    """Square's free-text description -> structured fields (all verbatim)."""
    t = html.unescape(re.sub(r"</p>|<br\s*/?>", "\n", desc_html or ""))
    t = re.sub(r"<[^>]+>", "", t)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in t.split("\n")]
    out = {"highlights": [], "base": [], "toppings": [], "ingredients": [], "macros": {}, "allergens": []}
    for ln in lines:
        if not ln:
            continue
        # Macro line: "Protein: 4g Fiber: 13g Sugar: 33g" / "P 17 G"
        mac = re.findall(r"(Protein|Fiber|Sugar)\s*:\s*(\d+)\s*g", ln, re.I)
        if mac:
            for k, v in mac:
                out["macros"][k.lower()] = int(v)
            ln = re.sub(r"(Protein|Fiber|Sugar)\s*:\s*\d+\s*g", "", ln, flags=re.I).strip()
            if not ln:
                continue
        if re.fullmatch(r"P\s*(\d+)\s*G", ln, re.I):
            out["macros"]["protein"] = int(re.findall(r"\d+", ln)[0])
            continue
        # Allergen sentences, kept word for word.
        for sent in re.findall(r"((?:Layers Crumble|Allergens|Oat & Chia Pudding)[^.]*\.(?:\s*Cross-contact[^.]*\.)?)", ln):
            out["allergens"].append(tidy(sent.replace("Allergens: ", "")) + ".")
        ln = re.sub(r"(?:Layers Crumble|Allergens|Oat & Chia Pudding)\s*:[^.]*\.(?:\s*Cross-contact[^.]*\.)?", "", ln).strip()
        nf = re.search(r"Nut-free\s*\|\s*Tree nut-free\s*\(\s*no cross-contact\s*\)", ln, re.I)
        if nf:
            out["allergens"].append("Nut-free and tree-nut-free (no cross-contact).")
            ln = (ln[:nf.start()] + ln[nf.end():]).strip()
        # "NO ADDED SUGAR - Naturally Sweetened with Whole Fruit" can sit anywhere
        # in a line; keep Square's own wording (added vs refined).
        m = re.search(r"No (Added|Refined) Sugar\s*[-•]?\s*Naturally Sweetened with Whole Fruit\s*-?", ln, re.I)
        if m:
            out["highlights"].append(f"No {m.group(1).lower()} sugar — naturally sweetened with whole fruit")
            ln = (ln[:m.start()] + " " + ln[m.end():]).strip(" •-")
            if not ln:
                continue
        mb = re.match(r"^(?:Layers-Made Base|Made A[cç]a[ií] Base|Base)\s*:\s*(.*)$", ln, re.I)
        mt = re.match(r"^Toppings?\s*:\s*(.*)$", ln, re.I)
        if mb:
            out["base"] += split_items(mb.group(1))
        elif mt:
            out["toppings"] += split_items(mt.group(1).replace(":Banana", "Banana"))
        elif "•" in ln and len(ln) < 90 and not re.search(r"organic|banana", ln, re.I):
            out["highlights"] += [tidy(x) for x in ln.split("•") if tidy(x) and not re.search(r"sugar|sweetened", x, re.I)]
        elif re.fullmatch(r"\d+g [A-Za-z ]+", ln):
            out["highlights"].append(ln)
        elif "," in ln or "•" in ln:
            out["ingredients"] += split_items(ln)
        elif re.search(r"\d+g", ln):
            out["highlights"] += [tidy(x) for x in ln.split("•") if tidy(x)]
    # Within-ingredients clean-up: drop dangling parenthetical allergen fragments.
    for k in ("base", "toppings", "ingredients"):
        out[k] = [re.sub(r"\s*\(Contain[s]? Tree Nuts \(Almond Milk\)?\)?", " (contains almond milk)", x) for x in out[k]]
        out[k] = [x for x in out[k] if x]
    out["allergens"] = list(dict.fromkeys(out["allergens"]))
    return {k: v for k, v in out.items() if v}


def card_slots(products, entries):
    """{square id: slot name ("menu/<slug>")} for the photo cards. products:
    [(id, raw Square name)] of the visible, not hidden card items, in menu
    order; entries: content/menu.json items by id. Slugs that would collide
    or come out empty get a suffix from the item id, so two cards never share
    a photo (and a stale-file cleanup can always match the file names)."""
    shown = {pid: ((entries.get(pid) or {}).get("display_name") or "").strip() or split_name(raw)[0]
             for pid, raw in products}
    slug = {pid: slugify(name) for pid, name in shown.items()}
    claimed = {}
    for pid, raw in products:                    # the item whose own name it is keeps the slug…
        own = slugify(split_name(raw)[0])
        if own and slug[pid] == own:
            claimed.setdefault(own, pid)
    for pid, _ in products:                      # …otherwise the first in menu order
        if slug[pid]:
            claimed.setdefault(slug[pid], pid)
    out = {}
    for pid, _ in products:
        s = slug[pid]
        tag = re.sub(r"[^a-z0-9]", "", pid.lower())[:6] or "x"
        out[pid] = "menu/" + (s if s and claimed[s] == pid else f"{s}-{tag}" if s else f"item-{tag}")
    return out


def menu_items(root=ROOT):
    """{square id: Square name} for every visible item in the menu's categories,
    from the cached store data (used by the content validator)."""
    data = json.loads((pathlib.Path(root) / "data" / "square-store-products.json").read_text())
    sq_cats = {c[0] for c in CATEGORIES}
    return {p["id"]: p["name"] for p in data["data"] if p.get("visibility") == "visible"
            and any(c["name"] in sq_cats for c in (p.get("categories") or {}).get("data", []))}


def _known_square_photo(sid, previous, specs):
    """The Square photo already downloaded for this item, if any: from the last
    sync's output, else from its tuned slot spec. Keeps photos tied to the id."""
    candidates = [previous.get(sid)]
    candidates += [s.get("tuned", {}).get("image") for s in specs.values()
                   if isinstance(s, dict) and s.get("square_id") == sid]
    for c in candidates:
        if c and c.startswith("src-img/menu/") and (ROOT / c).is_file():
            return c
    return None


def update_content(data, content):
    """Append Square items the manager's list doesn't have yet; refresh the
    read-only square_name/category. Returns (content, added, gone)."""
    by_id = {it.get("square_id"): it for it in content.get("items", [])}
    sq2disp = {sq: disp for sq, disp, _, _ in CATEGORIES}
    live, added = set(), []
    for p in data["data"]:
        if p.get("visibility") != "visible":
            continue
        disp = next((sq2disp[c["name"]] for c in (p.get("categories") or {}).get("data", [])
                     if c["name"] in sq2disp), None)
        if not disp:
            continue
        live.add(p["id"])
        sq_name = re.sub(r"\s+", " ", p["name"]).strip()
        it = by_id.get(p["id"])
        if it is None:
            # keys in the order of the item's fields in .pages.yml, so the file
            # stays in the CMS's own format (tools/cms_normalize.py --check)
            it = {"square_name": sq_name, "display_name": "", "note": "", "photo": "", "hidden": False,
                  "focus": "auto", "zoom": "auto", "category": disp, "square_id": p["id"]}
            content.setdefault("items", []).append(it)
            by_id[p["id"]] = it
            added.append(sq_name)
        else:
            it["square_name"], it["category"] = sq_name, disp
    gone = [it.get("square_name") or it.get("square_id") for it in content.get("items", [])
            if it.get("square_id") not in live]
    return content, added, gone


def sync(offline=False):
    if offline:
        data = json.loads(CACHE.read_text())
    else:
        data = json.loads(fetch(API))
        CACHE.write_text(json.dumps(data, indent=1))
    content = json.loads(MENU_CONTENT.read_text(encoding="utf-8")) if MENU_CONTENT.exists() else {"items": []}
    if not offline:
        before = json.dumps(content, ensure_ascii=False)
        content, added, gone = update_content(data, content)
        if json.dumps(content, ensure_ascii=False) != before:
            MENU_CONTENT.write_text(dump_cms_json(content), encoding="utf-8")
        for name in added:
            print(f"  + new on Square, added to content/menu.json: {name}")
        for name in gone:
            print(f"  ! no longer on Square (skipped; can be removed from content/menu.json): {name}")
    entries = {it.get("square_id"): it for it in content.get("items", []) if isinstance(it, dict)}
    order = {sid: i for i, sid in enumerate(entries)}
    specs = json.loads(SLOT_SPECS.read_text()) if SLOT_SPECS.exists() else {}
    previous = {}
    for path in OUT[:1]:
        if path.exists():
            for c in json.loads(path.read_text()).get("categories", []):
                for it in c["items"]:
                    if it.get("image_source"):
                        previous[it["id"]] = it["image_source"]
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    cats = {disp: {"name": disp, "style": style, "items": []} for _, disp, _, style in CATEGORIES}
    sq2disp = {sq: (disp, kind) for sq, disp, kind, _ in CATEGORIES}
    card_cats = {sq for sq, _, _, style in CATEGORIES if style == "cards"}
    shown_cards = sorted(((p["id"], p["name"]) for p in data["data"] if p.get("visibility") == "visible"
                          and (entries.get(p["id"]) or {}).get("hidden") is not True
                          and any(c["name"] in card_cats for c in (p.get("categories") or {}).get("data", []))),
                         key=lambda x: order.get(x[0], len(order)))
    slots = card_slots(shown_cards, entries)
    hidden = []
    for p in data["data"]:
        if p.get("visibility") != "visible":
            continue
        pdata = (p.get("categories") or {}).get("data", [])
        pcats = [c["name"] for c in pdata]
        hit = next((c for c in pcats if c in sq2disp), None)
        cat_id = next((c.get("site_category_id") for c in pdata if c["name"] == hit), None)
        if not hit:
            continue
        disp, kind = sq2disp[hit]
        ov = entries.get(p["id"], {})
        if ov.get("hidden") is True:
            hidden.append(p["id"])
            continue
        name, note = split_name(p["name"])
        name = (ov.get("display_name") or "").strip() or name
        note = (ov.get("note") or "").strip() or note
        # The store lists each item at its lowest price including required
        # options (every item carries a +$0.25 one), so show that same number.
        pr = p.get("price", {})
        price = pr.get("low_with_modifiers", pr.get("low", pr.get("high")))
        cal = ((p.get("product_type_details") or {}).get("calorie_count"))
        item = {
            "id": p["id"], "kind": kind, "name": name, "note": note,
            "price": f"{price:.2f}" if isinstance(price, (int, float)) else None,
            "calories": cal if isinstance(cal, int) else None,
            # The store has no per-item pages (its product links 404); orders
            # open the store at the item's category, embedded on /order.
            "category_id": cat_id,
        }
        if CATEGORIES[[c[1] for c in CATEGORIES].index(disp)][3] == "cards":
            item.update(parse_description(p.get("short_description")))
            item["slot"] = slots[p["id"]]
            slug = item["slot"].split("/", 1)[1]
            src = (ov.get("photo") or "").strip().replace("\\", "/").lstrip("/") or None
            if not src:
                src = _known_square_photo(p["id"], previous, specs)
            if not src:
                imgs = (p.get("images") or {}).get("data", [])
                if imgs:
                    url = imgs[0].get("absolute_url") or imgs[0].get("url")
                    ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
                    dest = IMG_DIR / f"sq-{slug}.{ext}"
                    if not dest.exists() and not offline:
                        dest.write_bytes(fetch(url))
                    src = str(dest.relative_to(ROOT)) if dest.exists() else None
            item["image_source"] = src
            if not src:
                item.pop("slot")
        # list order in content/menu.json; items not listed yet go last, by name
        item["_rank"] = order.get(p["id"], len(order))
        cats[disp]["items"].append(item)

    out = {
        "_comment": "Generated by tools/sync-menu-from-store.py from the public Square Online store. "
                    "Served by /api/menu until a Square token is configured; the build renders the static menu from it.",
        "source": "fallback",
        "store": STORE,
        "categories": [],
    }
    if hidden:              # only when there are any, so the file is unchanged otherwise
        out["hidden"] = sorted(hidden)
    for _, disp, _, _ in CATEGORIES:
        c = cats[disp]
        c["items"].sort(key=lambda i: (i["_rank"], i["name"].lower()))
        for i in c["items"]:
            i.pop("_rank")
        if c["items"]:
            out["categories"].append(c)
    for path in OUT:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return {c["name"]: len(c["items"]) for c in out["categories"]}


def main():
    n = sync(offline="--offline" in sys.argv)
    print("menu:", n, "->", ", ".join(str(p.relative_to(ROOT)) for p in OUT))


if __name__ == "__main__":
    main()
