"""Render PDF pages to images with poppler (pdftoppm). Rendered pages are scratch files, never committed."""
import re
import shutil
import subprocess
from pathlib import Path

POPPLER_FALLBACKS = ("/opt/local/bin", "/opt/homebrew/bin", "/usr/local/bin")  # MacPorts, Homebrew (arm, intel)


def pdftoppm() -> str:
    exe = shutil.which("pdftoppm") or next((str(Path(d) / "pdftoppm") for d in POPPLER_FALLBACKS if (Path(d) / "pdftoppm").exists()), None)
    if not exe:
        raise RuntimeError("pdftoppm not found; install poppler (brew install poppler or port install poppler)")
    return exe


def render_pages(pdf: str, pages: list[int], out_dir: str, dpi: int = 130) -> list[str]:
    """Render 1-based pages to JPEG; returns the image paths in page order."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths = []
    for p in pages:
        prefix = Path(out_dir) / f"p{p:02d}"
        subprocess.run([pdftoppm(), "-r", str(dpi), "-f", str(p), "-l", str(p), "-jpeg", "-singlefile", pdf, str(prefix)], check=True)
        paths.append(f"{prefix}.jpg")
    return paths


def page_count(pdf: str) -> int:
    exe = pdftoppm().replace("pdftoppm", "pdfinfo")
    out = subprocess.run([exe, pdf], capture_output=True, text=True, check=True).stdout
    return int(next(l.split()[-1] for l in out.splitlines() if l.startswith("Pages:")))


def page_text(pdf: str, page: int) -> str:
    """Text layer of one page (empty for scanned pages); used as a hint beside the image, never instead of the model."""
    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    return subprocess.run([exe, "-f", str(page), "-l", str(page), "-layout", pdf, "-"], capture_output=True, text=True).stdout


def title_block_text(pdf: str, page: int) -> str:
    """Text in the bottom-right corner, where drawing sets carry the drawing title and number. Empty if there is none."""
    info = subprocess.run([pdftoppm().replace("pdftoppm", "pdfinfo"), "-f", str(page), "-l", str(page), pdf], capture_output=True, text=True).stdout
    m = re.search(r"Page\s+\d*\s*size:\s+([\d.]+) x ([\d.]+)", info)
    w, h = (float(m.group(1)), float(m.group(2))) if m else (1190.0, 842.0)
    exe = pdftoppm().replace("pdftoppm", "pdftotext")
    args = [exe, "-f", str(page), "-l", str(page), "-x", str(int(w * 0.9)), "-y", str(int(h * 0.82)), "-W", str(int(w * 0.1)), "-H", str(int(h * 0.15)), "-layout", pdf, "-"]
    return re.sub(r"\s+", " ", subprocess.run(args, capture_output=True, text=True).stdout).strip()