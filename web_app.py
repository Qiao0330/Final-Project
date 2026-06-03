from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from study_adapter import get_study_view_data
from strategy_profile import load_strategy_profile, save_strategy_profile
from trainer_adapter import get_trainer_question, grade_trainer_answer


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "web_static"


class PokerUiHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_file(STATIC_ROOT / "index.html", "text/html")
            return
        if path == "/app.js":
            self._send_file(STATIC_ROOT / "app.js", "application/javascript")
            return
        if path == "/style.css":
            self._send_file(STATIC_ROOT / "style.css", "text/css")
            return
        if path == "/api/strategy-profiles":
            self._send_json(load_strategy_profile())
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/study":
                self._send_json(get_study_view_data(payload))
                return
            if path == "/api/trainer/question":
                self._send_json(get_trainer_question(payload))
                return
            if path == "/api/trainer/grade":
                self._send_json(
                    grade_trainer_answer(
                        str(payload.get("question_id", "")),
                        str(payload.get("user_action", "")),
                    )
                )
                return
            if path == "/api/strategy-profiles":
                self._send_json(save_strategy_profile(payload))
                return
            self._send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        data = self.rfile.read(length).decode("utf-8")
        return json.loads(data)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"error": "not found"}, status=404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), PokerUiHandler)
    print(f"Poker UI running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
