#!/usr/bin/env python3
"""
Rewrites the CMS-managed content files exactly the way Pages CMS writes them
when the manager opens one and presses Save — driven by .pages.yml.

  python3 tools/cms_normalize.py                 # rewrite every CMS-managed file in content/
  python3 tools/cms_normalize.py --check         # list files not in the CMS's format; change nothing
  python3 tools/cms_normalize.py content/hours.json content/pages/home.json   # only these

Why: a CMS save rewrites the whole file. If the files in the repo are already
in that format, the git history of a CMS edit shows only the manager's change
(and the "Undo my last change" workflow reverts exactly that). The tests use
the same code to simulate a save of every file (tests/test_cms_schema.py).

What a save does in Pages CMS v2.1.8, ported step by step from its source
(lib/schema.ts deepMap / initializeState / sanitizeObject / generateZodSchema,
fields/core/*, lib/serialization.ts, the entries and files API routes):

  1. open    only the fields declared in .pages.yml are read, in .pages.yml
             order; dates are parsed with the field's format (a date in
             another format comes back EMPTY), image paths are normalised.
  2. form    every missing field gets its default: the field's `default`, else
             false for a switch, today for a date (!), "" for everything else.
  3. check   required, maxlength, patterns, choices, number ranges and list
             sizes. A file that fails can't be saved in the CMS at all.
  4. save    dates re-formatted, image paths written with the media `output`
             prefix; then every "" and null is dropped, and so is every list
             or object left empty; JSON.stringify(…, null, 2): 2-space
             indent, no final newline, keys in field order.

It refuses — exit 1, listing every problem, writing nothing — when a file
holds anything a CMS save would lose or refuse: a key that isn't declared in
.pages.yml (with a value), a value of the wrong shape, a date in another
format, or a value the CMS's checks reject. So running it can never silently
drop data; fix .pages.yml (or the file) first.

Only the field types this site uses are ported (string, text, boolean,
number, select, date, image, object, lists of these, and lists of blocks —
the "More sections"). A config using anything else is refused, rather than
normalised wrongly.

Blocks (a `type: block` list): each item is an object whose `blockKey`
("_block" unless the field names another) holds the name of one of the
field's `blocks`; the item's other keys are that block's fields. A save
keeps the key first, then the block's fields in order (deepMap), and the
form's check (a zod discriminated union) refuses an item whose kind isn't one
of the blocks. An item of an unknown kind is reported, never dropped.
"""
import argparse
import copy
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ".pages.yml"

SUPPORTED = {"string", "text", "boolean", "number", "select", "date", "image", "object", "block"}
# fields/core/image: with no media config passed to the schema (as in the
# app's form and API), any path must end in one of the "image" category
# extensions, compared case-sensitively.
IMAGE_EXTENSIONS = ["jpg", "jpeg", "apng", "png", "gif", "svg", "ico", "avif", "bmp", "tif", "tiff", "webp"]


class ConfigError(Exception):
    """.pages.yml can't be used (unreadable, or uses something not ported here)."""


class _Undefined:
    """JavaScript's `undefined`: a key that is absent, as opposed to null."""

    def __repr__(self):
        return "undefined"


UNDEF = _Undefined()


# ---------------------------------------------------------------------------
# .pages.yml
# ---------------------------------------------------------------------------
def _merge(dst, src):
    """lodash.mergewith as lib/config.ts uses it: objects merge deeply, arrays
    (and everything else) from src replace."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst


def _resolve(field, components):
    """lib/config.ts resolveComponent: a field's own keys win over its
    component's; name from the field, type from the component."""
    f = copy.deepcopy(field)
    if isinstance(f.get("component"), str):
        comp = components.get(f["component"])
        if comp is None:
            raise ConfigError(f"Field “{f.get('name')}” uses the component “{f['component']}”, which isn't defined.")
        name = f.get("name")
        del f["component"]
        f = _merge(copy.deepcopy(comp), f)
        f["name"] = name
        f["type"] = comp.get("type")
    if isinstance(f.get("fields"), list) and f["fields"] and f.get("type") is None:
        f["type"] = "object"
    if isinstance(f.get("fields"), list):
        f["fields"] = [_resolve(x, components) for x in f["fields"]]
    if isinstance(f.get("blocks"), list):          # each block resolved too ("Nested blocks")
        f["blocks"] = [_resolve(b, components) for b in f["blocks"]]
    return f


def _check_fields(fields, where):
    for f in fields:
        t = f.get("type")
        at = f"{where} › {f.get('name')}"
        if t not in SUPPORTED:
            raise ConfigError(f"{at}: field type “{t}” isn't supported by tools/cms_normalize.py.")
        opts = f.get("options") or {}
        if t in ("select", "image") and opts.get("multiple"):
            raise ConfigError(f"{at}: `multiple` isn't supported by tools/cms_normalize.py.")
        if t == "date" and (opts.get("time") or opts.get("format", "yyyy-MM-dd") != "yyyy-MM-dd"):
            raise ConfigError(f"{at}: only dates stored as yyyy-MM-dd are supported.")
        if t == "object":
            _check_fields(f.get("fields") or [], at)
        if t == "block":
            if not f.get("list"):
                raise ConfigError(f"{at}: only lists of blocks are supported by tools/cms_normalize.py.")
            for b in f.get("blocks") or []:
                if not b.get("name") or b.get("type", "object") != "object":
                    raise ConfigError(f"{at}: every block needs a name and fields.")
                _check_fields(b.get("fields") or [], f"{at} › {b['name']}")


def _block_key(f):
    """The key a block item keeps its kind in (Pages CMS: blockKey, default _block)."""
    return f.get("blockKey") or "_block"


def _block_def(f, item):
    """The block definition an item of a block list is, or None (not an
    object, or a kind the field doesn't have)."""
    name = item.get(_block_key(f)) if isinstance(item, dict) else None
    return next((b for b in f.get("blocks") or [] if b.get("name") == name), None) if isinstance(name, str) else None


class Cms:
    """.pages.yml, normalised the way Pages CMS normalises it (lib/config.ts):
    components resolved, groups flattened."""

    def __init__(self, root=ROOT):
        import yaml   # PyYAML (requirements.txt); imported here so the build never needs it
        self.root = pathlib.Path(root)
        try:
            raw = yaml.safe_load((self.root / CONFIG).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            raise ConfigError(f"{CONFIG} can't be read: {e}") from None
        if not isinstance(raw, dict):
            raise ConfigError(f"{CONFIG} is empty or not a mapping.")
        self.raw = raw
        self.media = raw.get("media") or []
        if isinstance(self.media, str):
            rel = re.sub(r"^/|/$", "", self.media)
            self.media = [{"name": "default", "input": rel, "output": f"/{rel}"}]
        elif isinstance(self.media, dict):
            self.media = [{"name": "default", **self.media}]
        comps = {}
        for k, c in (raw.get("components") or {}).items():
            comps[k] = c
        self.components = {k: _resolve(c, comps) for k, c in comps.items()}
        self.entries = []
        self._flatten(raw.get("content") or [])
        for e in self.entries:
            if e.get("list"):
                raise ConfigError(f"{e['name']}: files that are a list at the top level aren't supported.")
            if (e.get("format") or "json") != "json":
                raise ConfigError(f"{e['name']}: only JSON content is supported.")
            if e["type"] == "collection":
                fn = e.get("filename")
                fn = fn.get("template") if isinstance(fn, dict) else fn
                if not isinstance(fn, str) or not fn.endswith(".json"):
                    raise ConfigError(f"{e['name']}: a JSON collection's filename must end in .json "
                                      "(otherwise its entries vanish from the CMS).")
            _check_fields(e["fields"], e["name"])

    def _flatten(self, items):
        for it in items:
            if it.get("type") == "group":
                self._flatten(it.get("items") or [])
                continue
            e = copy.deepcopy(it)
            e["path"] = str(e.get("path", "")).strip("/")
            e["fields"] = [_resolve(f, self.components) for f in e.get("fields") or []]
            self.entries.append(e)

    def media_config(self, field):
        """The media source an image field uses (fields/core/image)."""
        name = (field.get("options") or {}).get("media")
        if not self.media or name is False:
            return None
        if isinstance(name, str):
            return next((m for m in self.media if m.get("name") == name), None)
        return self.media[0]

    def entry_for(self, rel):
        """The .pages.yml entry that manages a repo-relative path, or None."""
        rel = str(rel).replace("\\", "/")
        for e in self.entries:
            if e["type"] == "file" and e["path"] == rel:
                return e
            if (e["type"] == "collection" and rel.rsplit("/", 1)[0] == e["path"] and rel.endswith(".json")
                    and "/" in rel):
                return e
        return None

    def files(self):
        """Every CMS-managed file that exists: [(repo-relative path, entry)]."""
        out = []
        for e in self.entries:
            if e["type"] == "file":
                if (self.root / e["path"]).is_file():
                    out.append((e["path"], e))
            else:
                d = self.root / e["path"]
                for p in sorted(d.glob("*.json")) if d.is_dir() else []:
                    out.append((f"{e['path']}/{p.name}", e))
        return out


# ---------------------------------------------------------------------------
# JavaScript semantics the CMS code relies on
# ---------------------------------------------------------------------------
def _truthy(v):
    if v is UNDEF or v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v == v and v != 0
    if isinstance(v, str):
        return v != ""
    return True            # lists and objects, even empty ones


def _js_string(v):
    if v is UNDEF:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, list):
        return ",".join("" if x is None or x is UNDEF else _js_string(x) for x in v)
    if isinstance(v, dict):
        return "[object Object]"
    return str(v)


def _js_number(v):
    """Number(v), for z.coerce.number(). NaN = None."""
    if isinstance(v, bool):
        return 1 if v else 0
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return 0
        try:
            if re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", s):
                n = float(s)
                return int(n) if n.is_integer() and abs(n) < 2 ** 53 else n
            if re.fullmatch(r"0[xX][0-9a-fA-F]+", s):
                return int(s, 16)
        except ValueError:
            pass
        if s in ("Infinity", "+Infinity"):
            return float("inf")
        if s == "-Infinity":
            return float("-inf")
        return None
    return None


def _utf16_len(s):
    """JavaScript string length (zod's min/max count UTF-16 code units)."""
    return len(s.encode("utf-16-le")) // 2


def _get(obj, name):
    return obj.get(name, UNDEF) if isinstance(obj, dict) else UNDEF


# ---------------------------------------------------------------------------
# lib/schema.ts
# ---------------------------------------------------------------------------
def deep_map(data, fields, apply, path=()):
    """deepMap: a new object with exactly the declared fields, in order.
    apply(value, field, path) maps each leaf; path is for messages only."""
    cur = data if _truthy(data) else {}
    out = {}
    for f in fields:
        name, value = f["name"], _get(cur, f["name"])
        at = path + (name,)
        if f.get("list"):
            if value is UNDEF:
                out[name] = apply(UNDEF, f, at)
            elif isinstance(value, list):
                out[name] = [_map_item(x, f, apply, at + (i,)) for i, x in enumerate(value)]
            else:
                out[name] = []
        elif f.get("type") == "object":
            out[name] = deep_map(value, f.get("fields") or [], apply, at)
        else:
            out[name] = apply(value, f, at)
    return out


def _map_item(x, f, apply, at):
    """One item of a list field, as deepMap maps it: an object's fields; a
    block's kind first and then its fields (an item of an unknown kind
    unchanged); anything else through apply."""
    if f.get("type") == "object":
        return deep_map(x, f.get("fields") or [], apply, at)
    if f.get("type") == "block":
        b = _block_def(f, x)
        if b is None:
            return x
        key = _block_key(f)
        return {key: x[key], **deep_map(x, b.get("fields") or [], apply, at)}
    return apply(x, f, at)


def _empty(v):
    return v is None or v is UNDEF or v == "" and isinstance(v, str)


def sanitize(obj):
    """sanitizeObject: drop "" and null everywhere; drop a key whose list is
    left empty or whose object is left empty. (An empty object INSIDE a list
    stays, as in the CMS.)"""
    if isinstance(obj, list):
        out = [sanitize(v) if isinstance(v, (dict, list)) else v for v in obj]
        return [v for v in out if not _empty(v)]
    if isinstance(obj, dict):
        out = dict(obj)
        for k in list(out):
            v = out[k]
            if isinstance(v, (dict, list)):
                out[k] = v = sanitize(v)
            if ((isinstance(v, list) and all(_empty(x) for x in v)) or (isinstance(v, dict) and not v)
                    or _empty(v)):
                del out[k]
        return out
    return obj


def effectively_empty(v):
    """isEffectivelyEmpty: an optional object whose values are all empty is
    treated as absent. false and 0 count as values."""
    if v is None or v is UNDEF or v == "" and isinstance(v, str):
        return True
    if isinstance(v, list):
        return not v or all(effectively_empty(x) for x in v)
    if isinstance(v, dict):
        return not v or all(effectively_empty(x) for x in v.values())
    return False


def default_value(f, today):
    """getDefaultValue."""
    if "default" in f:
        return copy.deepcopy(f["default"])
    t = f.get("type")
    if t == "object":
        return init_state(f.get("fields") or [], {}, today)
    if t == "boolean":
        return False
    if t == "block":
        return None
    if t == "date":
        return today.isoformat()          # yes: a date field without default "" starts as today
    return ""


def init_state(fields, content, today):
    """initializeState: every missing field filled with its default."""
    def apply(value, f, _path):
        if value is UNDEF:
            if f.get("list"):
                lst = f["list"]
                return copy.deepcopy(lst["default"]) if isinstance(lst, dict) and "default" in lst else []
            return default_value(f, today)
        if value is None and f.get("type") != "object" and not f.get("list"):
            return default_value(f, today)
        return value
    return deep_map(content or {}, fields, apply)


# ---------------------------------------------------------------------------
# fields/core: dates and image paths
# ---------------------------------------------------------------------------
_DATE = re.compile(r"([0-9]{1,4})-([0-9]{1,2})-([0-9]{1,2})(\s*)")


def parse_date(value):
    """date-fns parse(value, "yyyy-MM-dd"): its number parsers take 1–4 /
    1–2 digits and trailing whitespace is allowed. A date or None."""
    if not isinstance(value, str):
        return None
    m = _DATE.fullmatch(value)
    if not m:
        return None
    try:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        return dt.date(y, mo, d) if y > 0 else None
    except ValueError:
        return None


def _normalize_path(path):
    """lib/utils/file.ts normalizePath (note: only the FIRST "//" is collapsed)."""
    segs = path.replace("//", "/", 1).rstrip("/").split("/")
    out = []
    for s in segs:
        if s == "..":
            if not out or out[-1] == "..":
                out.append(s)
            else:
                out.pop()
        elif s not in (".", ""):
            out.append(s)
    return "/".join(out)


def _decode(path):
    cur = path
    for _ in range(2):
        if re.search(r"%(?![0-9a-fA-F]{2})", cur):
            break                                # decodeURIComponent throws: keep it as it is
        try:
            nxt = urllib.parse.unquote(cur, errors="strict")
        except UnicodeDecodeError:
            break
        if nxt == cur:
            break
        cur = nxt
    return cur


def normalize_media_path(path):
    if not path or path.startswith(("http://", "https://", "//", "data:")):
        return path
    parts = path.split("#")                  # JS: const [a, b = ""] = path.split("#")
    without_hash, hsh = parts[0], (parts[1] if len(parts) > 1 else "")
    parts = without_hash.split("?")
    pathname, query = parts[0], (parts[1] if len(parts) > 1 else "")
    decoded = _decode(pathname)
    norm = _normalize_path(decoded)
    out = f"/{norm}" if decoded.startswith("/") else norm
    out = f"{out}?{query}" if query else out
    return f"{out}#{hsh}" if hsh else out


def swap_prefix(path, frm, to, relative=False):
    """lib/github-image.ts swapPrefix."""
    if (path is None or frm is None or to is None or frm == to or path.startswith(("//", "http://", "https://",
                                                                                   "data:image/"))
            or not path.startswith(frm)):
        return path
    if frm == "" and to != "/":
        new = f"{to}/{path}"
    elif frm == "" and to == "/":
        new = f"/{path}"
    else:
        rest = path[len(frm):]
        rest = rest[1:] if rest.startswith("/") else rest
        new = f"/{rest}" if to == "/" else f"{to}/{rest}"
    if new.startswith("/") and relative:
        new = new[1:]
    return new


def _media_io(cms, f):
    m = cms.media_config(f)
    if not m:
        return None
    inp = re.sub(r"^/|/$", "", str(m.get("input", "")))
    out = str(m.get("output", ""))
    out = re.sub(r"/$", "", out) if out != "/" else out
    return inp, out


def _file_extension(path):
    name = _normalize_path(path).split("/")[-1]
    if name.startswith(".") and "." not in name[1:]:
        return ""
    m = re.search(r"(?:\.([^.]+))?$", name)
    return m[1] or ""


# ---------------------------------------------------------------------------
# One save
# ---------------------------------------------------------------------------
class _Save:
    def __init__(self, cms, today):
        self.cms, self.today, self.problems = cms, today, []

    def problem(self, kind, path, message):
        self.problems.append({"kind": kind, "field": ".".join(str(p) for p in path), "message": message})

    # 0 · what the CMS would throw away without a word -----------------------
    def undeclared(self, data, fields, path):
        if not isinstance(data, dict):
            return
        names = {f["name"]: f for f in fields}
        for k, v in data.items():
            f = names.get(k)
            if f is None:
                if sanitize({k: v}):
                    self.problem("undeclared", path + [k], "not declared in .pages.yml — a CMS save deletes it")
                continue
            if f.get("list"):
                if v is not None and not isinstance(v, list):
                    self.problem("lost", path + [k], "should be a list — a CMS save replaces it with nothing")
                elif f.get("type") == "block":
                    for i, item in enumerate(v or []):
                        b = _block_def(f, item)
                        if b is not None:
                            rest = {x: y for x, y in item.items() if x != _block_key(f)}
                            self.undeclared(rest, b.get("fields") or [], path + [k, i])
                        elif sanitize([item]):
                            kinds = ", ".join(str(x.get("name")) for x in f.get("blocks") or [])
                            self.problem("invalid", path + [k, i], f"isn't one of the kinds of {f.get('label') or k} "
                                                                   f"({kinds}) — the CMS can't save the file")
                elif f.get("type") == "object":
                    for i, item in enumerate(v or []):
                        if isinstance(item, dict):
                            self.undeclared(item, f.get("fields") or [], path + [k, i])
                        elif sanitize([item]):
                            self.problem("lost", path + [k, i], "should be a group of fields — a CMS save "
                                                                "replaces it with an empty one")
            elif f.get("type") == "object":
                if isinstance(v, dict):
                    self.undeclared(v, f.get("fields") or [], path + [k])
                elif v is not None and sanitize({k: v}):
                    self.problem("lost", path + [k], "should be a group of fields — a CMS save drops it")

    # 1 · open the entry ------------------------------------------------------
    def read(self, data, fields):
        def apply(value, f, path):
            t = f.get("type")
            if t == "date":
                if not _truthy(value):
                    return ""
                if not isinstance(value, str):
                    self.problem("invalid", path, f"“{_js_string(value)}” can't be opened as a date")
                    return ""
                d = parse_date(value)
                if d is None:
                    self.problem("lost", path, f"“{value}” isn't a yyyy-MM-dd date — the CMS shows it empty "
                                               "and a save blanks it")
                    return ""
                return d.isoformat()
            if t == "image":
                if not _truthy(value) or (isinstance(value, list) and not value):
                    return None
                io = _media_io(self.cms, f)
                if not io:
                    return value
                return swap_prefix(normalize_media_path(_js_string(value)), io[1], io[0], relative=True)
            return value
        return deep_map(data, fields, apply)

    # 3 · the form's and the server's checks (generateZodSchema) --------------
    def check_object(self, value, fields, path):
        if not isinstance(value, dict):
            self.problem("invalid", path, "should be a group of fields")
            return UNDEF
        return {f["name"]: self.check_field(_get(value, f["name"]), f, path + [f["name"]]) for f in fields}

    def check_field(self, v, f, path):
        t, req = f.get("type"), bool(f.get("required"))
        if f.get("list"):
            if v is UNDEF:
                if req:
                    self.problem("invalid", path, "is required")
                return UNDEF
            if not isinstance(v, list):
                self.problem("invalid", path, "should be a list")
                return UNDEF
            lst = f["list"] if isinstance(f["list"], dict) else {}
            lo = lst.get("min") if isinstance(lst.get("min"), (int, float)) and lst.get("min", 0) > 0 else None
            hi = lst.get("max") if isinstance(lst.get("max"), (int, float)) and lst.get("max", 0) > 0 else None
            if lo is not None and len(v) < lo:
                self.problem("invalid", path, f"needs at least {lo} item(s); it has {len(v)}")
            if hi is not None and len(v) > hi:
                self.problem("invalid", path, f"can have at most {hi} item(s); it has {len(v)}")
            if req and not v:
                self.problem("invalid", path, "needs at least one item")
            return [self.check_single(x, f, path + [i]) for i, x in enumerate(v)]
        out = self.check_single(v, f, path)
        return out

    def check_single(self, v, f, path):
        t, req, opts = f.get("type"), bool(f.get("required")), f.get("options") or {}
        if t == "block":
            # z.discriminatedUnion(blockKey, [one object per block]).optional().nullable()
            if v is None or v is UNDEF:
                return v
            b = _block_def(f, v)
            if b is None:
                self.problem("invalid", path, "isn't one of the kinds of section the field allows")
                return v
            key = _block_key(f)
            return {key: v[key], **self.check_object(v, b.get("fields") or [], path)}
        if t == "object":
            if req:
                if v is UNDEF:
                    self.problem("invalid", path, "is required")
                    return UNDEF
                return self.check_object(v, f.get("fields") or [], path)
            if effectively_empty(v):
                return UNDEF
            return self.check_object(v, f.get("fields") or [], path)
        if v is UNDEF:             # .optional() lets undefined through untouched
            if t == "boolean" and req:
                return False       # z.coerce.boolean(): Boolean(undefined)
            if req:
                self.problem("invalid", path, "is required")
            return UNDEF
        if t in ("string", "text"):
            if not isinstance(v, str):
                self.problem("invalid", path, f"should be text, not {type(v).__name__}")
                return v
            n = _utf16_len(v)
            if req and n < 1:
                self.problem("invalid", path, "is required")
            pat = f.get("pattern")
            if pat:
                regex = pat if isinstance(pat, str) else pat.get("regex", "")
                if not re.search(regex, v):
                    self.problem("invalid", path, f"“{v}” doesn't match the pattern {regex}")
            if opts.get("minlength") and n < opts["minlength"]:
                self.problem("invalid", path, f"is shorter than {opts['minlength']} characters")
            if opts.get("maxlength") and n > opts["maxlength"]:
                self.problem("invalid", path, f"is {n} characters long; the limit is {opts['maxlength']}")
            return v
        if t == "boolean":
            return _truthy(v)
        if t == "number":
            if v == "" and isinstance(v, str):
                if req:
                    self.problem("invalid", path, "is required")
                return ""
            n = _js_number(v)
            if n is None:
                self.problem("invalid", path, f"“{_js_string(v)}” isn't a number")
                return v
            if opts.get("min") is not None and n < opts["min"]:
                self.problem("invalid", path, f"{n} is below the minimum {opts['min']}")
            if opts.get("max") is not None and n > opts["max"]:
                self.problem("invalid", path, f"{n} is above the maximum {opts['max']}")
            return n
        if t == "select":
            v = "" if v is None else v
            values = [_js_string(x.get("value", x.get("name", "")) if x.get("value", x.get("name")) is not None
                                 else "") if isinstance(x, dict) else _js_string(x)
                      for x in opts.get("values") or []]
            if not isinstance(v, str) or (v not in values and (req or v != "")):
                self.problem("invalid", path, f"“{_js_string(v)}” isn't one of the choices ({', '.join(values)})")
            return v
        if t == "date":
            if not isinstance(v, str):
                self.problem("invalid", path, "should be a date")
                return v
            if not v:
                if req:
                    self.problem("invalid", path, "needs a date")
                return v
            if parse_date(v) is None:
                self.problem("invalid", path, f"“{v}” isn't a date")
            return v
        if t == "image":
            if v is UNDEF or v is None:
                if req:
                    self.problem("invalid", path, "needs a photo")
                return v
            if not isinstance(v, str):
                self.problem("invalid", path, "should be a photo path")
                return v
            if v == "":
                if req:
                    self.problem("invalid", path, "needs a photo")
                return v
            if _file_extension(v) not in IMAGE_EXTENSIONS:
                self.problem("invalid", path, f"“{v}”: the CMS only accepts these photo extensions: "
                                              + ", ".join(IMAGE_EXTENSIONS) + " (lower case)")
            return v
        raise ConfigError(f"field type {t} isn't supported")

    # 4 · write -------------------------------------------------------------
    def write(self, data, fields):
        def apply(value, f, path):
            t = f.get("type")
            if t == "date":
                if value is UNDEF:     # date-fns throws on undefined: the CMS's save fails
                    self.problem("invalid", path, "the CMS can't save an entirely empty group holding a date")
                    return ""
                d = parse_date(value)
                return d.isoformat() if d else ""
            if t == "image":
                if not _truthy(value) or (isinstance(value, list) and not value):
                    return None
                io = _media_io(self.cms, f)
                if not io:
                    return value
                return swap_prefix(normalize_media_path(_js_string(value)), io[0], io[1])
            return value
        return deep_map(data, fields, apply)


def _json_roundtrip(v):
    """JSON.parse(JSON.stringify(v)): undefined keys vanish, undefined list
    items become null, NaN becomes null."""
    if isinstance(v, dict):
        return {k: _json_roundtrip(x) for k, x in v.items() if x is not UNDEF}
    if isinstance(v, list):
        return [None if x is UNDEF else _json_roundtrip(x) for x in v]
    if isinstance(v, float) and v != v:
        return None
    return v


def _js_key_order(v):
    """JavaScript objects list integer-like keys first, in numeric order."""
    if isinstance(v, dict):
        idx = sorted((k for k in v if re.fullmatch(r"0|[1-9][0-9]*", k) and int(k) < 2 ** 32 - 1), key=int)
        rest = [k for k in v if k not in set(idx)]
        return {k: _js_key_order(v[k]) for k in idx + rest}
    if isinstance(v, list):
        return [_js_key_order(x) for x in v]
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e21:
        return int(v)
    return v


def dump(data):
    """lib/serialization.ts for JSON: JSON.stringify(data, null, 2), no final
    newline; an empty object is written as an empty file."""
    if not data:
        return ""
    return json.dumps(_js_key_order(data), indent=2, ensure_ascii=False)


def save(data, entry, cms, today=None):
    """The file Pages CMS writes when this content is opened and saved
    unchanged: (text, problems). Problems are dicts {kind, field, message};
    kind is "undeclared" / "lost" (a save would drop data) or "invalid" (the
    CMS would refuse to save)."""
    today = today or dt.date.today()
    s = _Save(cms, today)
    fields = entry["fields"]
    if not isinstance(data, dict):
        s.problem("lost", [], "the file should hold a group of fields ({ … })")
        return "", s.problems
    s.undeclared(data, fields, [])
    opened = s.read(data, fields)                             # GET entries/[path]
    state = init_state(fields, sanitize(opened), today)       # the entry form
    sent = _json_roundtrip(state)                             # POST body: JSON of the form's values
    parsed = s.check_object(sent, fields, [])                 # zod (the form runs the same checks first)
    written = s.write(parsed, fields)                         # deepMap with the writeFns
    return dump(sanitize(_json_roundtrip(written))), s.problems


# ---------------------------------------------------------------------------
def normalise(rel, cms, today=None):
    """(current text, normalised text, problems) for one repo-relative file."""
    path = cms.root / rel
    text = path.read_text(encoding="utf-8")
    entry = cms.entry_for(rel)
    if entry is None:
        return text, text, [{"kind": "lost", "field": "", "message": "not managed by .pages.yml"}]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return text, text, [{"kind": "invalid", "field": "", "message": f"isn't valid JSON ({e})"}]
    new, problems = save(data, entry, cms, today)
    return text, new, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="Rewrite CMS-managed content files in Pages CMS's own format.")
    ap.add_argument("files", nargs="*", help="repo-relative content files (default: every CMS-managed file)")
    ap.add_argument("--check", action="store_true", help="report files that would change; write nothing")
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    try:
        cms = Cms(args.root)
    except ConfigError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    root = pathlib.Path(args.root).resolve()
    if args.files:
        rels = []
        for f in args.files:
            p = pathlib.Path(f)
            p = (p if p.is_absolute() else pathlib.Path.cwd() / p).resolve()
            try:
                rels.append(p.relative_to(root).as_posix())
            except ValueError:
                rels.append(f)
    else:
        rels = [rel for rel, _ in cms.files()]

    results, bad = [], False
    for rel in rels:
        if not (cms.root / rel).is_file():
            print(f"✗ {rel}: no such file", file=sys.stderr)
            bad = True
            continue
        old, new, problems = normalise(rel, cms)
        results.append((rel, old, new))
        for p in problems:
            bad = True
            where = f" › {p['field']}" if p["field"] else ""
            print(f"✗ {rel}{where}: {p['message']}", file=sys.stderr)
    if bad:
        print("\nNothing was written. Declare the missing fields in .pages.yml (or fix the file), then run "
              "this again.", file=sys.stderr)
        return 1
    changed = [(rel, new) for rel, old, new in results if old != new]
    if args.check:
        for rel, _ in changed:
            print(f"would rewrite {rel}")
        print(f"{len(changed)} of {len(results)} file(s) not in the CMS's format.")
        return 1 if changed else 0
    for rel, new in changed:
        (cms.root / rel).write_text(new, encoding="utf-8")
        print(f"rewrote {rel}")
    print(f"{len(changed)} of {len(results)} file(s) rewritten.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
