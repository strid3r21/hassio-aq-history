# hassio-aq-history

Tiny Home Assistant OS add-on that exposes recorder history (from MariaDB)
as a read-only JSON API for custom Lovelace cards.

## Why
Some HA builds ship without the history API (`/api/history`, `history/*`
websocket commands, History panel). The recorder still writes to MariaDB;
this add-on reads it directly.

## Install
1. HA UI → Add-ons → ⚙️ (top-right) → Add-on Store → Manage repositories →
   add `https://github.com/strid3r21/hassio-aq-history`
2. Add-ons → AQ History → Options → set the MariaDB connection
   (from your `secrets.yaml` `mariadb_url`), then **Start**.
3. It listens on port **8799** of the HA host.

## API
```
GET /health
GET /history?entity_id=sensor.foo&hours=168&max_points=300
→ {"entity": "sensor.foo", "points": [[1699999999000, 42.0], ...]}
```
Only entities in `allowed_domains` (default: `sensor`) can be queried.
Endpoints send `Access-Control-Allow-Origin: *` for browser cards.

## Notes
- Read-only access; uses whatever DB user you configure (a read-only user
  is recommended).
- The port is exposed on the LAN; keep the HA instance LAN-only or put a
  reverse proxy in front if you expose it wider.
