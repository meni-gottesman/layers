#!/usr/bin/env python3
"""
Local dev server for the Layers site.

Serves public/ and stubs the two Cloudflare Functions so the full client
behaviour can be exercised without Node or wrangler installed.

  python3 tools/devserver.py [port]

Query flags for testing the resilience paths:
  /?menu=down   -> /api/menu returns 503 (Square unreachable)
  /?menu=square -> /api/menu returns a live-looking Square payload
Default is the fallback payload, matching an unconfigured SQUARE_ACCESS_TOKEN.
"""
import json
import re
import sys
import pathlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
FALLBACK = ROOT / "data" / "menu-fallback.json"

EVENT_TYPES = {
    "Team breakfast", "Wellness event", "Corporate meeting",
    "Private celebration", "Other",
}

# Mirrors functions/api/menu.js output shape for a successful Square sync.
SQUARE_SAMPLE = {
    "source": "square",
    "syncedAt": "2026-07-27T14:00:00.000Z",
    "categories": [
        {"name": "Bowls", "items": [
            {"id": "sq1", "kind": "Bowl", "name": "Berry Much Love U", "note": "Classic Açaí",
             "price": "9.50", "calories": 367, "image": "/assets/img/menu/berry-much-love-u.jpg", "soldOut": False},
            {"id": "sq2", "kind": "Bowl", "name": "Mango Coco", "note": "Inspired by Thai Mango Sticky Rice",
             "price": "9.50", "calories": 280, "image": "/assets/img/menu/mango-coco.jpg", "soldOut": False},
            {"id": "sq3", "kind": "Bowl", "name": "The Balance Bowl", "note": "Yogurt",
             "price": "8.75", "calories": 275, "image": "/assets/img/menu/balance-bowl.jpg", "soldOut": True},
            {"id": "sq4", "kind": "Bowl", "name": "Recovery Bowl", "note": "40g Protein",
             "price": "15.75", "calories": 747, "image": "/assets/img/menu/recovery-bowl.jpg", "soldOut": False},
        ]},
        {"name": "Smoothies", "items": [
            {"id": "sq5", "kind": "Smoothie", "name": "Strawesome", "note": "Skin Health & Antioxidant",
             "price": "10.75", "calories": 255, "image": "/assets/img/menu/strawesome.jpg", "soldOut": False},
            {"id": "sq6", "kind": "Smoothie", "name": "Greenergy", "note": "Daily Greens & Inner Balance",
             "price": "10.75", "calories": 245, "image": "/assets/img/menu/greenergy.jpg", "soldOut": False},
            {"id": "sq7", "kind": "Smoothie", "name": "Summer Special", "note": "New this week",
             "price": "11.25", "calories": 260, "image": "/assets/img/menu/think-well.jpg", "soldOut": False},
        ]},
    ],
}

MODE = {"menu": "fallback"}
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(PUBLIC), **kw)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    # ---------------------------------------------------------------- utils
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        if self.path.startswith("/api/menu"):
            mode = MODE["menu"]
            if mode == "down":
                return self._send_json(
                    {"source": "error", "categories": [],
                     "error": "menu temporarily unavailable"}, 503)
            if mode == "square":
                return self._send_json(SQUARE_SAMPLE)
            data = json.loads(FALLBACK.read_text())
            data["source"] = "fallback"
            return self._send_json(data)

        if self.path.startswith("/api/catering"):
            self.send_response(405)
            self.send_header("allow", "POST")
            self.end_headers()
            return

        # Let ?menu=<mode> on any page switch the stub for the session.
        if "menu=" in self.path:
            m = re.search(r"menu=(\w+)", self.path)
            if m and m.group(1) in ("fallback", "square", "down"):
                MODE["menu"] = m.group(1)
                sys.stderr.write("  [menu stub -> %s]\n" % m.group(1))
            self.path = self.path.split("?")[0] or "/"


        # Clean URLs, mirroring Cloudflare Pages: /menu serves menu.html,
        # and anything unresolved serves 404.html with a 404 status.
        path = self.path.split("?")[0]
        if path not in ("/",) and "." not in path.split("/")[-1]:
            slug = path.strip("/")
            if (PUBLIC / slug / "index.html").is_file():
                self.path = f"/{slug}/index.html"
            elif (PUBLIC / (slug + ".html")).is_file():
                self.path = f"/{slug}.html"
            else:
                self.path = "/404.html"
                body = (PUBLIC / "404.html").read_bytes() if (PUBLIC / "404.html").is_file() else b"Not found"
                self.send_response(404)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        return super().do_GET()

    # ----------------------------------------------------------------- POST
    def do_POST(self):
        if not self.path.startswith("/api/catering"):
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except Exception:
            return self._send_json({"error": "Could not read that submission."}, 400)

        # 1 honeypot -> silent success
        if str(data.get("company", "")).strip():
            sys.stderr.write("  [catering] honeypot tripped -> silent 200\n")
            return self._send_json({"ok": True})

        # 2 validation, mirroring functions/api/catering.js
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip()
        etype = str(data.get("event_type", "")).strip()
        guests = str(data.get("guest_count", "")).strip()
        date = str(data.get("event_date", "")).strip()

        if not name:
            return self._send_json({"error": "Please tell us your name."}, 400)
        if not EMAIL_RE.match(email):
            return self._send_json({"error": "Please enter a valid email address."}, 400)
        if etype not in EVENT_TYPES:
            return self._send_json({"error": "Please choose an event type."}, 400)
        if guests and not re.fullmatch(r"\d{1,5}", guests):
            return self._send_json({"error": "Guest count should be a number."}, 400)
        if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return self._send_json({"error": "Please use the date picker for the event date."}, 400)

        sys.stderr.write("  [catering] accepted from %s <%s> — %s\n" % (name, email, etype))
        return self._send_json({"ok": True})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8931
    print(f"Layers dev server -> http://localhost:{port}  (serving {PUBLIC})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
