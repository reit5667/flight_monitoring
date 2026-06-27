"""
Minimal HTTP server for the Telegram Mini App dashboard.

Endpoints:
  GET /              → miniapp.html
  GET /api/history   → JSON price history for a route (?origin=HAN&dest=BKK&days=30)
  GET /api/routes    → JSON list of monitored routes

Run:
  python3 -m dashboard.server
  (set MINIAPP_URL=https://<your-ngrok>.ngrok.io in .env)
"""
import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

from db import get_conn

load_dotenv()

_HTML_PATH = Path(__file__).parent / "miniapp.html"
_PORT = int(os.getenv("MINIAPP_PORT", "8080"))


def _load_history(origin: str, dest: str, days: int = 30) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DATE(valid_from) AS day, MIN(price::numeric) AS min_price
                FROM flights_history fh
                JOIN routes r ON r.route_id = fh.route_id
                WHERE r.origin = %s AND r.destination = %s
                  AND fh.valid_from >= %s
                GROUP BY DATE(valid_from)
                ORDER BY day
                """,
                (origin.upper(), dest.upper(), since),
            )
            rows = cur.fetchall()
    return [{"date": str(r[0]), "price": float(r[1])} for r in rows]


def _load_routes() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT origin, destination, notes FROM routes WHERE enabled ORDER BY priority DESC"
            )
            rows = cur.fetchall()
    return [{"origin": r[0], "dest": r[1], "label": r[2] or f"{r[0]} → {r[1]}"} for r in rows]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence default access log

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path == "/":
            html = _HTML_PATH.read_bytes()
            self._send(200, "text/html; charset=utf-8", html)

        elif path == "/api/history":
            origin = (qs.get("origin", [""])[0]).upper()
            dest = (qs.get("dest", [""])[0]).upper()
            days = int(qs.get("days", ["30"])[0])
            if not origin or not dest:
                self._send(400, "application/json", b'{"error":"origin and dest required"}')
                return
            try:
                data = _load_history(origin, dest, days)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self._send(500, "application/json", body)
                return
            self._send(200, "application/json", json.dumps(data).encode())

        elif path == "/api/routes":
            try:
                data = _load_routes()
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self._send(500, "application/json", body)
                return
            self._send(200, "application/json", json.dumps(data, ensure_ascii=False).encode())

        else:
            self._send(404, "text/plain", b"Not found")


def main():
    server = HTTPServer(("0.0.0.0", _PORT), _Handler)
    print(f"Mini App server running on http://0.0.0.0:{_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
