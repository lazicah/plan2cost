# Plan2Cost: project context for Claude Code

Solo entry (Indie track) in the Meta x Cerebral Valley Global AI Developer Hackathon. Build period Oct 27 – Nov 4, 2026. Submission due Nov 4, 9 PM ET (Nov 5, 3 AM Lagos). Submit a day early.
Owner: Lazarus (Quantity Surveying lecturer at FUTO, senior Flutter engineer). Domain expert, so ask him about QS conventions rather than guessing.

## What it is
Agent for Africans building homes or small commercial buildings (especially diaspora building remotely): plan -> cost -> proof.
1. Plan/sketch -> quantity take-off -> BoQ priced with editable local rates.
2. Contractor quote audit, line by line against the BoQ, with explained flags.
3. Stage site photos/videos vs BoQ -> milestone report with confidence; defer to a surveyor when unsure.
Priority: (1) and (2) are must-haves. (3) is the riskiest, so spike it first and keep it modest.

## Judging (weights)
Impact 30%, Use of Meta AI Tooling 25%, Demo 25%, Technical Depth 20%. The 3-minute demo video is a primary judging artifact.
Bonus prizes to aim for: Best Build on Open Weights (Muse Spark Open / Glimmer), Best Agentic Use-Case, Most Viral (post demo on X), Community Vote.

## Hard rules
- Public repo. New work only; the README must clearly separate prior work from hackathon work.
- Prior work: only the author's Excel BoQ calculators. They are not in this repo and are used only as a reference to cross-check numbers. Do not copy their contents in.
- Every runtime AI feature must use Meta models only: Muse Spark Open (`meta-models/muse-spark-open-1026` on Baseten/Fireworks/Modal), Muse Spark series, SAM 3.1 via Meta Model API.
- Avoid the listed anti-projects (basic RAG, simple image analyzers, chat wrappers, medical, political).
- Rates are user-editable; never scrape pricing data.
- Disclose AI coding assistance in the README.

## Design principles
- The model extracts dimensions; deterministic code does the maths (`plan2cost/tools/takeoff.py`).
- Self-check step: recompute areas, and ask the user for missing inputs instead of guessing.
- Evaluate against the author's own surveyed quantities (`eval/cases/<id>/plan.* + truth.json`).

## Dev
- Python 3.10+. `pip install -r requirements.txt`, then `python -m pytest -q` (all tests run offline; no network).
- Needs poppler (`pdftoppm`, `pdftotext`, `pdfinfo`); `plan2cost/pdf.py` also looks in /opt/local/bin (MacPorts) and /opt/homebrew/bin.
- `.env` (never print or commit it): `P2C_BASE_URL`, `P2C_API_KEY`, `P2C_MODEL` for the Meta Model API; `P2C_OPEN_*` for Muse Spark Open on Baseten. `P2C_PROFILE=open` runs everything on Spark Open.
- Run the agent: `python -m plan2cost.agent --pdf <drawing set.pdf>`; console: `python ui/server.py` then http://127.0.0.1:8765.
- `reference/` (the author's drawings, workbooks, rules, price data) and `workspace/` (agent runs) are gitignored. Drawings are third-party work: never copy them into the repo, only numbers read from them.
- The cloud sandbox cannot reach the model APIs, so model-calling code is run locally.

## Layout
- `plan2cost/agent/` the agent loop (checklist, quote-checked facts, ask_user pause and resume, submit gate), tools wrap everything below; `ui/` the console.
- `plan2cost/document.py` whole drawing set: page index and classification, opening schedules, levels, plan-symbol openings. `notes.py` spec notes with checked quotes.
- `plan2cost/dims.py`, `grid.py` printed dimensions, chains, grid bubbles and scale from the PDF text layer. `walls_cv.py` walls from raster plans (in progress). `sam.py` SAM 3.1 client (no matches on CAD line art; for photos).
- `plan2cost/tools/` deterministic take-off maths: `takeoff.py` girth by dimension kind, `foundation.py`, `walls.py`. `boq.py` BoQ items and pricing; `data/defaults.json`, `data/rates.json`.
- `eval/cases/<id>/` the author's surveyed truth; `eval/runs/` one report per model run (progress log for the Meta team).

## Rules of the domain (from the author, a quantity surveyor)
- Drawings are the guide; defaults are a flagged fallback. Never ask a non-technical user about girth or measurement terms.
- Dimension kinds: centre-line, end-to-end, in-to-in. Use wall thickness as drawn (230 stays 230). BESMM4: dimensions to the nearest 10mm (0.675 -> 0.68), whole units, minimum 1.
- Blockwork: full runs on the centre line, girth x storey height (from the section) less openings; external and internal walls are measured and deducted separately.
- Trench width is three times the block thickness unless the drawing prints it; with no foundation layout the ground floor plan stands in.
- Score girth against totals only (the author's sheets merge identical runs).

## BESMM4 (rule source)
- `reference/rules/BESMM4 PDF.pdf` (the book) and `Detailed BOQ Description BESMM4.xlsx` (master bill: every measurable item with code, wording, unit). Both are the NIQS's text: kept in `reference/`, never committed.
- Agent tools `lookup_besmm` (rule pages) and `find_besmm_item` (codes). `data/besmm_codes.json` maps our BoQ keys to codes; `data/besmm_check.json` records the rule check per line. Lines with no code are the author's own (working space, anti-termite, levelling); keep them optional and ask.
- Not every item applies to every project: pick the relevant ones, and ask the user about conditional ones (earthwork support only when specified).
- The author's sheet constants can be one-off choices (the 0.95 on topsoil); check the book and ask before treating a sheet value as a rule.

## Drawing interpretation (Oct 29)
`plan2cost/interpret.py` (`interpret_page`, `interpret_image`) reads walls from a vector PDF page, a raster page or an image through one machinery:
`vector.py` / `raster_lines.py` give line objects, `vector_walls.py` pairs them into wall bands, `scale.py` finds the scale from printed dimensions,
`page_facts.py` has the model read the stated scale and overall dimensions. Results and weaknesses: `eval/WALLS.md`. Never tune a constant to one plan.

## Verified drawing model (Oct 29)
`drawing_model.py` is the register: walls with stable ids (W-001...), a calibration record, evidence labels, issues. `qc.py` holds the checks (overlap,
dangling lines, free ends, extents against printed dimensions, scale evidence, external convention); none changes a measurement. `markup.py` draws the
walls on the plan (`model_for_page`, `model_for_image`); `review.py` is the model's advisory review of that image (flags only). The agent's
`read_wall_girth` builds it, saves open checks as assumptions, and the console shows the annotated plan. Not built yet: openings tied to walls, rooms, stairs.

## Status (Oct 28 night, superseded in part by the sections above)
Works: page classification and schedule/level/notes reading (both models); wall area and foundation maths reproduce the author's sheets; plan-symbol openings about 86 percent; agent loop, console, Spark Open.
Not working: wall girth from a plan (model reading about 20 percent off; image detector finds about 74 percent of plan2 wall length), so no trustworthy end-to-end estimate yet. Not built: roof, finishes, services, preliminaries, additions in the BoQ; quote audit; stage photos.
Next, in order: (1) finish `walls_cv.py` on plan2 (heavy exterior walls, stairs false positives, snap to printed breakpoints), footprint estimate as flagged fallback; (2) one complete plan2 BoQ end to end, compared with the author's own total; (3) quote audit; (4) SAM 3.1 stage-photo demo; (5) README (prior work vs new, AI-assistance disclosure), demo video, submit by Nov 3.
