"""Render PDF pages to images with poppler (pdftoppm). Rendered pages are scratch files, never committed."""
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
