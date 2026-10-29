"""Tools that look up the measurement rules: BESMM4 items from the master bill and the rule book pages."""
from plan2cost.kit.progress import Run


def find_besmm_item(run: Run, query: str) -> dict:
    """Find BESMM4 items (code, wording, unit) in the master bill. Use it to choose the items that apply to this project and to word them;
    not everything in the bill is measured for every project, and conditional items should be confirmed with the user."""
    from plan2cost.takeoff.besmm_bill import find, path

    if not path():
        return {"error": "The BESMM4 master bill is not available here (set P2C_BESMM_XLSX). Say in the basis that the item was not checked."}
    hits = find(query)
    return {"query": query, "items": hits} if hits else {"query": query, "items": [], "note": "No item carries all the words; try fewer or different words."}


def lookup_besmm(run: Run, query: str) -> dict:
    """Find what the BESMM4 rule book says about something to be measured (unit, what is included or deducted, what the item description must
    state). Returns page numbers and excerpts for you to read; say which page your rule comes from when you record a fact based on it."""
    from plan2cost.takeoff.besmm_book import book_path, search

    if not book_path():
        return {"error": "The BESMM4 book is not available here (set P2C_BESMM_PDF). Say in the basis that the rule was not checked."}
    hits = search(query)
    return {"query": query, "pages": hits} if hits else {"query": query, "pages": [], "note": "No page carries all the words; try fewer or different words."}


TOOLS = {
    "find_besmm_item": (find_besmm_item, "query: words from the item wanted, e.g. 'sides of foundations'; returns BESMM4 codes, wording and units"),
    "lookup_besmm": (lookup_besmm, "query: what to look up in the BESMM4 book, e.g. 'remove topsoil'; returns pages and excerpts"),
}
