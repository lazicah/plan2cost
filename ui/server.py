"""Plan2Cost console: watch a run, answer its questions, start new ones. Local only (127.0.0.1), standard library only.

    python ui/server.py            then open http://127.0.0.1:8765
"""
import json
import re
import subprocess
import sys
import time
from urllib.parse import unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plan2cost.agent import view  # noqa: E402
from plan2cost.kit import progress  # noqa: E402
from plan2cost.kit.progress import Run  # noqa: E402

PORT = 8765
LOG = ROOT / "workspace" / "console.log"  # what the background processes print, so a crashed run can be explained
UPLOADS = ROOT / "workspace" / "uploads"  # files picked in the console are copied here, then handed to the agent by path
UPLOAD_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx"}
DOWNLOADS = {"bill_materials_labour.pdf": "application/pdf", "bill_materials_labour.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "bill_priced.pdf": "application/pdf", "bill_unpriced.pdf": "application/pdf", "bill_priced.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "bill_unpriced.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
        self.path = self.path.split("?")[0]  # the page adds ?v=... to images so a redrawn plan is fetched again; routes ignore it
        if self.path in ("/", "/index.html"):
            self._send(200, (ROOT / "ui" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/runs":
            self._json(200, view.list_runs())
        elif re.match(r"^/api/runs/\d{8}-\d{6}/models/[\w.\-]+\.(jpg|json)$", self.path):  # the annotated plans and drawing models of a run
            f = progress.RUNS_DIR / self.path.split("/")[3] / "models" / self.path.split("/")[5]
            if f.is_file():
                self._send(200, f.read_bytes(), "image/jpeg" if f.suffix == ".jpg" else "application/json")
            else:
                self._json(404, {"error": "no such file"})
        elif re.match(r"^/api/runs/\d{8}-\d{6}/files/[\w.\-]+$", self.path):  # the bills and audits a run wrote
            name = self.path.split("/")[5]
            f = progress.RUNS_DIR / self.path.split("/")[3] / name
            if name in DOWNLOADS and f.is_file():
                self.send_response(200)
                self.send_header("Content-Type", DOWNLOADS[name])
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.end_headers()
                self.wfile.write(f.read_bytes())
            else:
                self._json(404, {"error": "no such file"})
        elif re.match(r"^/api/runs/\d{8}-\d{6}/pages/p\d+\.jpg$", self.path):  # page thumbnails
            f = progress.RUNS_DIR / self.path.split("/")[3] / "pages" / self.path.split("/")[5]
            self._send(200, f.read_bytes(), "image/jpeg") if f.is_file() else self._json(404, {"error": "no such file"})
        elif self.path == "/api/log":
            self._json(200, {"tail": "\n".join(LOG.read_text().splitlines()[-25:]) if LOG.exists() else ""})
        elif self.path.startswith("/api/runs/") and self.path.endswith("/massing") and view.RUN_ID.match(self.path.split("/")[3]):
            try:
                from plan2cost.agent.massing import massing

                self._json(200, massing(Run.load(self.path.split("/")[3])))
            except OSError:
                self._json(404, {"error": "no such run"})
        elif self.path.startswith("/api/runs/") and view.RUN_ID.match(self.path.split("/")[3]):
            try:
                self._json(200, view.summary(Run.load(self.path.split("/")[3])))
            except OSError:
                self._json(404, {"error": "no such run"})
        else:
            self._json(404, {"error": "not found"})

    def _upload(self) -> None:
        name = re.sub(r"[^\w.\- ]", "_", Path(unquote(self.path.split("name=", 1)[-1])).name)
        if Path(name).suffix.lower() not in UPLOAD_TYPES:
            return self._json(400, {"error": f"{Path(name).suffix or 'that file'} is not supported; use PDF, image or Excel"})
        UPLOADS.mkdir(parents=True, exist_ok=True)
        dest = UPLOADS / f"{time.strftime('%Y%m%d-%H%M%S')}-{name}"
        dest.write_bytes(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        self._json(200, {"path": str(dest)})

    def _voice(self) -> None:
        """A WAV recording in; what was heard and the estimate inputs read from it out. The form is filled from it, and the person checks it before starting."""
        from plan2cost.facts.spoken_inputs import read_spoken_inputs
        from plan2cost.kit.voice import transcribe

        wav = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            heard = transcribe(wav)
            self._json(200, {"transcript": heard.get("transcript", ""), "inputs": read_spoken_inputs(heard.get("transcript", ""))})
        except (ValueError, RuntimeError, KeyError) as e:
            self._json(400, {"error": str(e)})

    def do_POST(self) -> None:
        if self.path.startswith("/api/upload?name="):
            return self._upload()
        if self.path == "/api/voice":
            return self._voice()
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        cmd = [sys.executable, "-m", "plan2cost.agent"]
        if self.path == "/api/start":
            floors = body.get("floors") or []
            names = [f.get("name") for f in floors]
            if not floors or any(not existing_file(f.get("file", "")) for f in floors) or len(set(names)) != len(names) or any(n not in progress.FLOOR_NAMES for n in names):
                return self._json(400, {"error": "give at least one floor plan, each with a floor name (ground, first, ...) used once"})
            try:
                height = float(body.get("storey_height_m"))
            except (TypeError, ValueError):
                height = 0.0
            if not 2.0 <= height <= 6.0:
                return self._json(400, {"error": "the storey height must be between 2 and 6 metres (floor to floor)"})
            if body.get("roof_type") not in progress.ROOF_TYPES:
                return self._json(400, {"error": f"choose a roof type: {', '.join(progress.ROOF_TYPES)}"})
            cmd += ["--storey-height", str(height), "--roof", body["roof_type"], "--turns", str(int(body.get("turns", 20)))]
            for f in floors:
                page = f":{int(f['page'])}" if f.get("page") and str(f["file"]).lower().endswith(".pdf") and int(f["page"]) > 1 else ""
                cmd += ["--floor", f"{f['name']}={existing_file(f['file'])}{page}"]
            if body.get("finish_level") in ("standard", "premium"):
                cmd += ["--finish", body["finish_level"]]
            for flag, key in (("--pitch", "pitch_deg"), ("--overhang", "overhang_m")):
                if body.get(key) not in (None, ""):
                    cmd += [flag, str(float(body[key]))]
            if body.get("quote"):
                if not existing_file(body["quote"]):
                    return self._json(400, {"error": "quote must be the path of an existing file"})
                cmd += ["--quote", str(existing_file(body["quote"]))]
        elif self.path.startswith("/api/runs/") and self.path.endswith("/answer") and view.RUN_ID.match(self.path.split("/")[3]):
            if not body.get("answer"):
                return self._json(400, {"error": "answer is empty"})
            cmd += ["--resume", self.path.split("/")[3], "--answer", body["answer"]]
        elif self.path.startswith("/api/runs/") and self.path.endswith("/resume") and view.RUN_ID.match(self.path.split("/")[3]):
            cmd += ["--resume", self.path.split("/")[3]]
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
