#!/usr/bin/env python3
"""AQ History — serves Home Assistant recorder (MariaDB) history as JSON.

Endpoints:
  GET /health  -> {"ok": true}
  GET /history?entity_id=sensor.x&hours=168[&max_points=300]
      -> {"entity": "sensor.x", "points": [[ms_ts, value], ...]}
"""
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import pymysql

def _option(key, default=None):
    """Read an option: options.json first, then env vars, then default."""
    for p in ("/data/options.json", "/config/options.json", "/options.json"):
        try:
            with open(p) as f:
                v = json.load(f).get(key)
            if v not in (None, ""):
                return v
        except Exception:
            pass
    for prefix in ("ADDON_", "APP_"):
        v = os.environ.get(prefix + key.upper())
        if v not in (None, ""):
            return v
    return default


DB_HOST = str(_option("db_host", "mariadb"))
DB_PORT = int(_option("db_port", 3306))
DB_USER = str(_option("db_user", "recorder"))
DB_PASS = str(_option("db_password", ""))
DB_NAME = str(_option("db_name", "homeassistant"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8799"))
ALLOWED_DOMAINS = {d.strip() for d in str(_option("allowed_domains", "sensor")).split(",") if d.strip()}

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def get_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=DB_NAME, connect_timeout=5, read_timeout=30,
        cursorclass=pymysql.cursors.Cursor,
    )


def fetch_points(entity_id, hours, max_points):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_updated, state FROM states "
                "WHERE entity_id = %s AND last_updated >= %s "
                "ORDER BY last_updated",
                (entity_id, since),
            )
            rows = cur.fetchall()
    pts = []
    for ts, state in rows:
        try:
            v = float(state)
        except (TypeError, ValueError):
            continue
        pts.append([int(ts.timestamp() * 1000), v])
    if len(pts) > max_points:
        step = len(pts) / max_points
        pts = [pts[int(i * step)] for i in range(max_points)]
    return pts


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/health":
            try:
                get_conn().close()
                self._json(200, {"ok": True})
            except Exception as e:
                self._json(200, {"ok": False, "error": str(e)})
            return
        if u.path == "/history":
            entity = (q.get("entity_id") or [""])[0]
            try:
                hours = min(float((q.get("hours") or ["24"])[0]), 24 * 365)
                max_points = min(int((q.get("max_points") or ["300"])[0]), 5000)
            except ValueError:
                self._json(400, {"error": "bad hours/max_points"})
                return
            if not ENTITY_RE.match(entity):
                self._json(400, {"error": "bad entity_id"})
                return
            domain = entity.split(".", 1)[0]
            if ALLOWED_DOMAINS and domain not in ALLOWED_DOMAINS:
                self._json(403, {"error": f"domain {domain} not allowed"})
                return
            try:
                t0 = time.time()
                pts = fetch_points(entity, hours, max_points)
                self._json(200, {"entity": entity, "points": pts, "ms": int((time.time() - t0) * 1000)})
            except Exception as e:
                self._json(500, {"error": str(e)})
            return
        if u.path == "/debug":
            def s(x):
                if x is None:
                    return None
                if isinstance(x, (datetime,)):
                    return x.isoformat()
                return str(x)
            out = {}
            try:
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT NOW(), @@global.time_zone, @@session.time_zone")
                        out["time"] = [s(v) for v in cur.fetchone()]
                        cur.execute("SELECT COUNT(*), MAX(last_updated) FROM states")
                        out["states_total"] = [s(v) for v in cur.fetchone()]
                        cur.execute(
                            "SELECT entity_id, COUNT(*), MAX(last_updated) FROM states "
                            "WHERE entity_id LIKE 'sensor.air%' GROUP BY entity_id "
                            "ORDER BY MAX(last_updated) DESC LIMIT 15")
                        out["air_sensors"] = [[s(v) for v in r] for r in cur.fetchall()]
                        cur.execute(
                            "SELECT entity_id, state, last_updated FROM states "
                            "ORDER BY last_updated DESC LIMIT 5")
                        out["newest_rows"] = [[s(v) for v in r] for r in cur.fetchall()]
                self._json(200, out)
            except Exception as e:
                self._json(500, {"error": str(e)})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"aq-history listening on :{LISTEN_PORT} db={DB_HOST}:{DB_PORT}/{DB_NAME} user={DB_USER} domains={ALLOWED_DOMAINS}")
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
