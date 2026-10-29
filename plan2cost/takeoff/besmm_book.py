"""Look up the measurement rules in the BESMM4 book. The book is the NIQS's publication, so it is not in the repo: point P2C_BESMM_PDF at
your copy (default reference/rules/BESMM4 PDF.pdf). Code finds the pages that mention the terms; the model reads them and decides the rule."""
import os
import re
from functools import lru_cache
from pathlib import Path

from plan2cost.kit.pdf import page_count, page_text

DEFAULT = "reference/rules/BESMM4 PDF.pdf"
STOP = {"the", "of", "and", "to", "a", "in", "for", "on", "with", "from", "by", "is", "are", "how", "what", "does", "do"}


def book_path() -> str | None:
    p = os.environ.get("P2C_BESMM_PDF") or DEFAULT
    return p if Path(p).exists() else None


@lru_cache(maxsize=2)
def _pages(pdf: str) -> list[str]:
    return [re.sub(r"\s+", " ", page_text(pdf, n)) for n in range(1, page_count(pdf) + 1)]


def search(query: str, top: int = 4, width: int = 700) -> list[dict]:
    """The pages that best match the query, with an excerpt around the first hit. Whole-phrase hits count most."""
    pdf = book_path()
    if not pdf:
        return []
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in STOP]
    if not terms:
        return []
    scored = []
    for n, text in enumerate(_pages(pdf), 1):
        low = text.lower()
        score = sum(low.count(t) for t in terms) + 5 * (query.lower() in low)
        hit = sum(1 for t in terms if t in low)
        if hit == len(terms):  # a page must carry every term
            scored.append((score, n, low.find(terms[0])))
    out = []
    for _, n, at in sorted(scored, reverse=True)[:top]:
        text = _pages(pdf)[n - 1]
        out.append({"page": n, "excerpt": text[max(0, at - width // 4): at + width]})
    return out
