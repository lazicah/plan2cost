from plan2cost.facts.notes import extract_notes


def test_notes_with_a_quote_not_on_the_page_are_dropped(monkeypatch):
    monkeypatch.setattr("plan2cost.facts.notes.page_text", lambda pdf, p: "0.7MM GAUGE, COLOUR COATED, LONG SPAN ALUMINUM ROOFING SHEET ATTACHED TO 75X50 PURLINS")
    fake = lambda prompt: {"notes": [
        {"page": 9, "topic": "roof_covering", "summary": "aluminium", "quote": "0.7mm gauge,  colour coated, long span aluminum roofing sheet"},
        {"page": 9, "topic": "roof_covering", "summary": "tiles", "quote": "concrete roofing tiles on battens"},
        {"page": 9, "topic": "other", "summary": "short", "quote": "75X50"}]}
    out = extract_notes("x.pdf", [9], chat=fake)
    assert [n["topic"] for n in out["notes"]] == ["roof_covering"] and out["dropped"] == 2


def test_pages_without_text_are_reported(monkeypatch):
    monkeypatch.setattr("plan2cost.facts.notes.page_text", lambda pdf, p: "")
    assert extract_notes("x.pdf", [3], chat=lambda p: {})["pages_without_text"] == [3]
