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
LOG = ROOT / "workspace" / "console.log"  # what the background processes print, so a crashed run can be explained
DOWNLOADS = {"bill_priced.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "bill_unpriced.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "boq.json": "application/json", "tender_audit.json": "application/json"}


def existing_file(raw: str) -> Path | None:
    f = Path(raw).expanduser()
    return f if f.is_file() else None


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
        elif re.match(r"^/api/runs/\d{8}-\d{6}/files/[\w.\-]+$", self.path):  # the bills and audits a run wrote
            name = self.path.split("/")[5]
            f = view.RUNS_DIR / self.path.split("/")[3] / name
            if name in DOWNLOADS and f.is_file():
                self.send_response(200)
                self.send_header("Content-Type", DOWNLOADS[name])
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                self.wfile.write(f.read_bytes())
            else:
                self._json(404, {"error": "no such file"})
        elif self.path == "/api/log":
            self._json(200, {"tail": "\n".join(LOG.read_text().splitlines()[-25:]) if LOG.exists() else ""})
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
            if body.get("structural"):
                if not existing_file(body["structural"]):
                    return self._json(400, {"error": "structural must be the path of an existing .pdf file"})
                cmd += ["--structural", str(existing_file(body["structural"]))]
            if body.get("quote"):
                if not existing_file(body["quote"]):
                    return self._json(400, {"error": "quote must be the path of an existing file"})
                cmd += ["--quote", str(existing_file(body["quote"]))]
            if body.get("objective"):
                cmd += ["--objective", body["objective"]]
        elif self.path.startswith("/api/runs/") and self.path.endswith("/answer") and view.RUN_ID.match(self.path.split("/")[3]):
            if not body.get("answer"):
                return self._json(400, {"error": "answer is empty"})
            cmd += ["--resume", self.path.split("/")[3], "--answer", body["answer"]]
        elif self.path.startswith("/api/runs/") and self.path.endswith("/bids") and view.RUN_ID.match(self.path.split("/")[3]):
            bids = [b.strip() for b in body.get("bids", []) if b.strip()]
            if not bids or not all(existing_file(b) for b in bids):
                return self._json(400, {"error": "give the path of each returned bill (.xlsx, PDF or image), one per line"})
            cmd = [sys.executable, "-m", "plan2cost.agent.bids", "--run", self.path.split("/")[3], *[str(existing_file(b)) for b in bids]]
        else:
            return self._json(404, {"error": "not found"})
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as log:
            log.write(f"\n$ {' '.join(cmd[2:])}\n")
            subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=log)  # the run saves its own state
        self._json(202, {"started": True})

    def log_message(self, *args) -> None:
        pass


if __name__ == "__main__":
    print(f"Plan2Cost console: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
