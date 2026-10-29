# Plan2Cost

An AI agent that helps Africans building a home or small commercial building (especially diaspora families building remotely) go **from plan, to cost, to proof**:

1. **Plan → BoQ.** Reads a floor plan or sketch, computes a quantity take-off, and prices it with editable local rates.
2. **Quote audit.** Checks a contractor's quote line by line against the BoQ and explains every flag.
3. **Site proof.** Compares stage photos/videos with the BoQ to produce a milestone report. It states its confidence and defers to a surveyor when unsure.

Built for the Meta x Cerebral Valley Global AI Developer Hackathon (Indie track, theme: *Build for Your World*).

## What existed before the hackathon

- The author's personal Excel BoQ calculators. They are **not** included in this repo. They are used only as a reference to cross-check the agent's numbers.

## Built during the hackathon (Oct 27 – Nov 4, 2026)

Everything in this repository. See the git history for dated commits.

## Layout

Model reads, code measures: a model never overrides a measurement, and every checked fact carries its evidence.

```
plan2cost/
  kit/        primitives with no domain logic: model client (Meta Model API / Muse Spark Open), PDF reading, the saved run (progress.py)
  drawing/    reading geometry: vector and raster line work, wall bands, scale, interpretation, the verified drawing model, quality checks,
              annotated markup, openings tied to walls, strip footing layout from the structural drawing
  facts/      what the model reads that is printed on the sheets: page index, opening schedule, levels, notes, foundation section, column bases,
              page facts for scale, model review of the markup, SAM 3.1 for site photos
  takeoff/    deterministic quantities and rules: walls, foundation, substructure, BoQ and pricing, BESMM4 book and master bill, coverage checklist
  tools/      what the agent can call, one file per group (records, documents, drawings, structural, standards, estimate, submit)
  agent/      loop.py, system_instructions.md (the prompt), verify.py (the submit gate), view.py, CLI (python -m plan2cost.agent)
data/         editable rates, defaults, BESMM code map, coverage map (ids only)
eval/         ground-truth cases and the scripts that score the wall, opening and foundation readings
ui/           console: runs, turns, facts, drawing model markup, BoQ with BESMM4 codes and coverage
tests/        unit tests
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your key
python -m pytest -q
python -m plan2cost.agent --pdf <plans.pdf> [--structural <structural.pdf>]
python ui/server.py   # the console
```

Models are called through an OpenAI-compatible endpoint (Meta Model API, or Muse Spark Open on Baseten/Fireworks/Modal). Configure it in `.env`.

## Status

Work in progress: plan to BoQ works end to end (wall interpretation, openings, foundation, BESMM4-coded priced bill, coverage statement). Quote audit and stage-photo check are next.
