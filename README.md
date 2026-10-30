# Plan2Cost

An AI agent that helps Africans building a home or small commercial building (especially diaspora families building remotely) go **from plan, to cost, to proof**. Built for the Meta x Cerebral Valley Global AI Developer Hackathon (Indie track, theme: *Build for Your World*).

## What it does

1. **Floor plans to a cost.** You give one floor plan per floor (PDF or image), the storey height (floor to floor) and a roof type (gable, hip or flat). Code measures wall girth, the building's size, doors, windows and wet rooms from the drawing. What a plan does not show (frame, slabs, stairs, steel, roof, services) is estimated from stored coefficient ranges. The result is a priced bill of quantities with a low, typical and high total, and every line is marked **measured** or **estimated**.
2. **3D check.** A "View the house in 3D" button shows the measured walls with their doors and windows cut out and a plain roof of the chosen type, built from the same drawing models as the bill (illustrative, never a source of quantities). A wall the reader missed shows up as a gap, so a person who cannot read a plan can see what was measured. From any view, "Make a realistic picture" sends a screenshot to Muse Image, with a prompt built from the measured roof type, storeys, windows and doors, and shows an illustration (labelled as an artist's impression; it never feeds a quantity).
3. **Bills.** Priced (for a client) and unpriced (for tender) bills in Excel and PDF, in the order of a real bill (substructure, superstructure, finishes, services, external works), plus a bill of materials and labour (cement bags, sand, blocks, bars, labour).
4. **Quote and tender audit.** A contractor's quote is checked line by line against the bill (arithmetic, quantities, rates, double charging, work left out). Contractors' returned tender bills are matched by item number and compared. Every flag says what to ask; none accuses.
5. **Site proof** (stage photos against the bill) is not built yet. SAM 3.1 is only tested.

## How it works

**The model reads and judges; code measures.** A model never sets a length. It reads printed facts (scale, overall dimensions, room names), says what a gap in a wall is (door, window, opening) and answers closed questions about crops of the plan. Code traces the line work, finds the walls and measures every length. The same wall machinery runs on vector PDFs (exact) and raster images (morphology).

- **Scale** comes from printed dimensions against the lines they measure; a reading counts only if the walls form a building whose size matches the printed overall dimensions.
- **Model-checked walls.** After measuring, the model is asked closed questions about the plan: is this stretch past the last joint a wall or a grid line, is this pair of lines one wall, is there a wall here with no line on it. Code trims, merges or adds a wall only when the model's answer and the geometry agree, and logs each edit. A second model review of the annotated plan can only add questions.
- **Checks** run on every floor: overlapping runs, runs past the last joint, wall ends that meet nothing, building size against printed dimensions, weak scale, and the external-wall convention. Open checks travel with the estimate and cannot be lost at submit.
- **A submit gate** (`agent/verify.py`) refuses to file an estimate until floors are read, the estimate is computed, nothing is pending and any given quote has been audited.
- **Rates are yours.** They live in `data/rates.json`, from two bills the author supplied (never scraped): the higher rate where both bills price the same product, and a Standard or Premium tier where they price different specifications. Coefficients carry sources and a confidence; prices and cost shares are sanity checks, never rates.

## Results

Wall girth (external plus internal) against the author's own surveyed totals, nothing tuned to one drawing. Full table and the weaknesses are in `CLAUDE.md`; the scripts are `eval/run_vector_walls.py` and `eval/run_raster_walls.py`.

| Source | Plans | Error range against surveyed |
|---|---|---|
| vector PDF | 6 floors on plans 4, 6, 7 | -9% to +13% (plan 4 ground +1%, plan 7 ground -1%) |
| raster image | 8 floors on plans 1, 2, 3, 4, 6 | -10% to +31% (most within 10%) |

After the model-checked wall pass, plan 2's ground floor measures 111.7 m against 107.1 surveyed (+4%) and its first floor 121.4 m against 127.6 (-5%); the table above is the plain measurement without that pass. End to end on plan 2 (two floor images, hip roof, 3.0 m): about 2.5 minutes, gross floor area 350.7 m2 against the author's 353 m2, a Standard-finish estimate of about 87.7M naira (range 74M to 114M). **No total has yet been checked against a surveyed bill for the same plan**, so treat the estimate as a budget, not a bill for tender. The quote audit was tested on a synthetic scanned quote with four planted errors (all four caught) and the tender audit on three synthetic returns, not yet on real ones.

## Known weaknesses

- Walls are axis-aligned only; thin partitions and walls split by openings are the main source of wall error. Plan 6 first floor (raster) is +31%.
- Openings are under-detected on some plans (plan 2: 2 found against 36 windows in the author's bill), so missing openings are estimated from the author's per-m2 ratios and marked estimated.
- External girth differs from the usual outline-only convention by 5 to 45%; it is reported at lower confidence and the porch and terrace question is left to the user.
- Column bases cannot be seen on a plan and are not included. Air-conditioning units and external works are not covered.
- Recipes for the materials bill come from one building (apart from concrete, blocks and bars, which use published calculators).

## Built during the hackathon (Oct 27 to Nov 4, 2026)

Everything in this repository. Nothing existed before: the author is a quantity surveyor and used professional experience, textbooks and public sites for the measurement conventions, rates and coefficients, with sources named in `data/` and `CLAUDE.md`. The author's own bills and drawings used for checking are not in this repo.

## Models

Plan 10 (one-storey bungalow) was run end to end on both hosts, the same code and the same plan. Muse Spark through the Meta Model API: external walls 36.2 m, internal 19.0 m, 11 windows and 4 doors, estimate 22.4M naira.
Muse Spark Open on Baseten (`P2C_PROFILE=open`): external 36.8 m, internal 25.1 m, 11 windows and 4 doors, estimate 23.0M naira (+2.5%), 3 turns and about 3.5 minutes. The differences are in the walls the model checks add or leave.

Every model call goes through an OpenAI-compatible endpoint: Muse Spark through the Meta Model API, or Muse Spark Open on Baseten (`P2C_PROFILE=open`). Configure it in `.env`. **Muse Voice Transcribe** is in the new-estimate form: press the microphone, say the storey height, roof type, finish level and so on, and the form is filled from what was heard (the transcript is shown and the fields stay editable); it always uses the Meta Model API. SAM 3.1 is planned for the site-photo check and is not in the estimate flow yet.

## AI assistance

The code was written with Claude Code (Anthropic's coding assistant), directed and reviewed by the author, who is responsible for the domain rules and decisions. The agent loop follows the pattern taught in the Meta agent workshops (loop, evidence, verification, escalation); no code was copied from the workshop repository or from other open-source projects.

## Layout

Model reads, code measures: a model never overrides a measurement, and every line says whether it was measured from the plans or estimated from coefficients.
Dependencies run one way: `kit` <- `takeoff`, `drawing` <- `facts` <- `tools` <- `agent`. A new tool is one function in a `tools/<group>.py` file plus an entry in that file's `TOOLS`.

```
plan2cost/
  kit/        primitives with no domain logic: model client (Meta Model API / Muse Spark Open), Muse Voice Transcribe (voice.py), Muse Image (imagegen.py),
              PDF reading, the saved run (progress.py)
  drawing/    reading geometry, no model calls except the closed questions about crops:
                vector.py, vector_walls.py, raster_lines.py, walls_cv.py   line work and wall bands (vector PDF exactly, raster by morphology)
                scale.py, grid.py, dims.py                                   scale from printed dimensions and grid bubbles
                interpret.py, measure.py                                     one entry point per page: the best route, with its confidence
                model.py, qc.py, markup.py                                   the verified drawing model, its quality checks, the annotated plan
                opening_candidates.py, openings.py                           where openings may be (five finders) and what they are (the model judges a crop, tags are evidence)
  facts/      what the model reads or judges, always checked by code: page facts (scale, overall dimensions), room names and spaces (rooms.py, spaces.py),
              opening tags (tags.py), wall checks (verify_walls.py, review.py), spoken inputs (spoken_inputs.py), quote lines (quote.py), SAM 3.1 (sam.py, not in the flow)
  takeoff/    quantities and rules: walls, foundation, finishes, the estimator (rough.py), coefficients, BoQ and pricing, bills, bill of materials and labour, quote and tender audit
  tools/      what the agent can call, one file per group (drawings, estimate, records, audit, submit)
  agent/      loop.py, system_instructions.md (the prompt), verify.py (the submit gate), view.py (what the console shows), massing.py and render.py (the 3D view and its picture),
              CLI (python -m plan2cost.agent) and the tender audit (bids.py)
data/         editable rates, defaults, BESMM code map, coefficients (sourced ranges), material and labour recipes, bill structure, coverage map
eval/         ground-truth cases, the scripts that score the wall and opening readings, and those that derive coefficients and recipes from the author's own sheets
ui/           console (server.py, index.html): new estimate form with voice input, live progress, annotated plans, BoQ with ranges, bills, 3D view, quote and bid audit
docs/         the demo script and checklists (demo-script.md), the measurement strategy, and notes kept for reference (notes/, not read by the code)
tests/        unit tests (python -m pytest -q)
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your key
python -m pytest -q
python -m plan2cost.agent --floor ground=ground.pdf --floor first=first.jpg --storey-height 3.0 --roof hip
python ui/server.py   # the console
```

Models are called through an OpenAI-compatible endpoint (Meta Model API, or Muse Spark Open on Baseten/Fireworks/Modal). Configure it in `.env`.

## Status

Work in progress: floor plans to a budget estimate with ranges, bills in Excel and PDF, contractor quote and tender audit. Next: validation against a surveyed bill for the same plan, and the stage-photo check.
