"""Plan2Cost console: watch a run, answer its questions, start new ones. Local only (127.0.0.1), standard library only.

    python ui/server.py            then open http://127.0.0.1:8765
"""
import json
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plan2cost.agent import view  # noqa: E402
from plan2cost.kit.progress import Run  # noqa: E402

PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, default=str).encode())

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "ui" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/runs":
            self._json(200, view.list_runs())
        elif re.match(r"^/api/runs/\d{8}-\d{6}/models/[\w.\-]+\.(jpg|json)$", self.path):  # the annotated plans and drawing models of a run
            f = view.RUNS_DIR / self.path.split("/")[3] / "models" / self.path.split("/")[5]
            if f.is_file():
                self._send(200, f.read_bytes(), "image/jpeg" if f.suffix == ".jpg" else "application/json")
            else:
                self._json(404, {"error": "no such file"})
        elif self.path.startswith("/api/runs/") and view.RUN_ID.match(self.path.split("/")[3]):
            try:
                self._json(200, view.summary(Run.load(self.path.split("/")[3])))
            except OSError:
                self._json(404, {"error": "no such run"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        cmd = [sys.executable, "-m", "plan2cost.agent"]
        if self.path == "/api/start":
            pdf = Path(body.get("pdf", "")).expanduser()
            if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
                return self._json(400, {"error": "pdf must be the path of an existing .pdf file"})
            cmd += ["--pdf", str(pdf), "--turns", str(int(body.get("turns", 30)))]
            if body.get("quote"):
                quote = Path(body["quote"]).expanduser()
                if not quote.is_file():
                    return self._json(400, {"error": "quote must be the path of an existing file"})
                cmd += ["--quote", str(quote)]
            if body.get("objective"):
                cmd += ["--objective", body["objective"]]
        elif self.path.startswith("/api/runs/") and self.path.endswith("/answer") and view.RUN_ID.match(self.path.split("/")[3]):
            if not body.get("answer"):
                return self._json(400, {"error": "answer is empty"})
            cmd += ["--resume", self.path.split("/")[3], "--answer", body["answer"]]
        else:
            return self._json(404, {"error": "not found"})
        subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # the run saves its own state
        self._json(202, {"started": True})

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print(f"Plan2Cost console: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
