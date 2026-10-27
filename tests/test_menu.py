"""Menu presentation (content/menu.json + tools/sync-menu-from-store.py):
ordering, renaming, hiding, and how new Square items are taken in."""
import json

from conftest import edit, load_tool

CATS = ("Bowls", "Smoothies", "Wellness Market")


def sync(repo, name):
    mod = load_tool(repo / "tools" / "sync-menu-from-store.py", name)
    mod.sync(offline=True)
    return json.loads((repo / "data" / "menu-fallback.json").read_text())


def names(menu, cat):
    return [i["name"] for c in menu["categories"] if c["name"] == cat for i in c["items"]]


def test_seed_order_matches_the_site(repo):
    m = sync(repo, "sync_seed")
    assert names(m, "Bowls") == ["Berry Much Love U", "Mango Coco", "Pink Pink Pink", "Recovery Bowl",
                                 "Balance Bowl", "Chia & Oat Pudding", "Build Your Bowl"]
    assert names(m, "Smoothies")[:3] == ["Strawesome", "Blue-Tiful-Day", "Greenergy"]


def test_list_order_is_menu_order(repo):
    def f(d):
        items = d["items"]
        bowls = [i for i in items if i["category"] == "Bowls"]
        rest = [i for i in items if i["category"] != "Bowls"]
        d["items"] = list(reversed(bowls)) + rest
    edit(repo, "menu.json", f)
    m = sync(repo, "sync_order")
    assert names(m, "Bowls")[0] == "Build Your Bowl" and names(m, "Bowls")[-1] == "Berry Much Love U"


def test_rename_note_and_hide(repo):
    def f(d):
        for it in d["items"]:
            if it["square_name"] == "Pink Pink Pink":
                it.update(display_name="Pink³", note="Dragon fruit")
            if it["square_name"].startswith("Greenergy"):
                it["hidden"] = True
    edit(repo, "menu.json", f)
    m = sync(repo, "sync_rename")
    bowls = {i["name"]: i for c in m["categories"] for i in c["items"]}
    assert "Pink³" in bowls and bowls["Pink³"]["note"] == "Dragon fruit"
    assert bowls["Pink³"]["slot"] == "menu/pink"                     # slot follows the shown name
    assert bowls["Pink³"]["image_source"] == "src-img/menu/sq-pink-pink-pink.jpeg"   # photo stays tied to the id
    assert "Greenergy" not in names(m, "Smoothies")


def test_empty_fields_mean_squares_own(repo):
    def f(d):
        for it in d["items"]:
            if it["square_name"] == "Berry Much Love U (Classic Acai)":
                it.update(note="")
    edit(repo, "menu.json", f)
    m = sync(repo, "sync_empty")
    berry = next(i for c in m["categories"] for i in c["items"] if i["id"] == "WCXFIIWG7UHLHK4YSLDSIWNZ")
    assert berry["note"] == "Classic Acai"                           # Square's own wording


def test_items_missing_from_the_list_go_last(repo):
    edit(repo, "menu.json", lambda d: d.update(items=[i for i in d["items"] if i["square_name"] != "Mango Coco"]))
    m = sync(repo, "sync_missing")
    assert names(m, "Bowls")[-1] == "Mango Coco"


def test_live_refresh_appends_new_items_and_keeps_edits(repo):
    mod = load_tool(repo / "tools" / "sync-menu-from-store.py", "sync_live")
    data = json.loads((repo / "data" / "square-store-products.json").read_text())
    content = json.loads((repo / "content" / "menu.json").read_text())
    content["items"][0]["display_name"] = "Kept"
    data["data"].append({"id": "NEWITEM1", "name": "New   Bowl", "visibility": "visible",
                         "categories": {"data": [{"name": "Layers Bowls"}]}})
    gone_id = content["items"][1]["square_id"]
    data["data"] = [p for p in data["data"] if p["id"] != gone_id]
    out, added, gone = mod.update_content(data, content)
    assert out["items"][0]["display_name"] == "Kept"
    assert out["items"][-1] == {"square_id": "NEWITEM1", "square_name": "New Bowl", "category": "Bowls",
                                "display_name": "", "note": "", "photo": "", "focus": "auto", "zoom": "auto",
                                "hidden": False}
    assert added == ["New Bowl"] and len(gone) == 1


def test_cms_pruned_menu_builds_the_same(repo):
    """A CMS save removes empty values; the menu must not change."""
    import content as C
    before = sync(repo, "sync_before")
    p = repo / "content" / "menu.json"
    p.write_text(C.dump_cms_json(json.loads(p.read_text())))
    assert sync(repo, "sync_after") == before


def test_two_items_never_share_a_photo_slot(repo):
    """Renaming Mango Coco to "Pink Pink Pink": Pink Pink Pink keeps its slot
    (it's its own Square name), Mango Coco gets a suffixed one and keeps its photo."""
    def f(d):
        for it in d["items"]:
            if it["square_name"] == "Mango Coco":
                it["display_name"] = "Pink Pink Pink"
    edit(repo, "menu.json", f)
    m = sync(repo, "sync_collide")
    items = {i["id"]: i for c in m["categories"] for i in c["items"]}
    assert items["SE5PJMNKX4A4G7JWWR55MDLC"]["slot"] == "menu/pink-pink-pink"
    assert items["VLK7BDLF3CHWWWUKENU3PK4C"]["slot"] == "menu/pink-pink-pink-vlk7bd"
    assert items["VLK7BDLF3CHWWWUKENU3PK4C"]["image_source"] == "src-img/menu/sq-mango-coco.png"
    slots = [i["slot"] for i in items.values() if i.get("slot")]
    assert len(slots) == len(set(slots))


def test_a_name_without_letters_still_gets_a_slot(repo):
    edit(repo, "menu.json", lambda d: [it.update(display_name="★★★") for it in d["items"]
                                       if it["square_name"] == "Mango Coco"])
    m = sync(repo, "sync_stars")
    mango = next(i for c in m["categories"] for i in c["items"] if i["id"] == "VLK7BDLF3CHWWWUKENU3PK4C")
    assert mango["name"] == "★★★" and mango["slot"] == "menu/item-vlk7bd"


def test_hidden_ids_are_listed_only_when_there_are_any(repo):
    assert "hidden" not in sync(repo, "sync_nohidden")
    edit(repo, "menu.json", lambda d: [it.update(hidden=True) for it in d["items"]
                                       if it["square_name"] in ("Mango Coco", "Pink Pink Pink")])
    m = sync(repo, "sync_hidden")
    assert m["hidden"] == ["SE5PJMNKX4A4G7JWWR55MDLC", "VLK7BDLF3CHWWWUKENU3PK4C"]
