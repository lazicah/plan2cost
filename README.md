# Plan2Cost

An AI agent that helps Africans building a home or small commercial building (especially diaspora families building remotely) go **from plan, to cost, to proof**:

1. **Plan → BoQ.** Reads a floor plan or sketch, computes a quantity take-off, and prices it with editable local rates.
2. **Quote audit.** Checks a contractor's quote line by line against the BoQ and explains every flag.
3. **Site proof.** Compares stage photos/videos with the BoQ to produce a milestone report. It states its confidence and defers to a surveyor when unsure.

Built for the Meta x Cerebral Valley Global AI Developer Hackathon (Indie track, theme: *Build for Your World*).

## What existed before the hackathon

Nothing. Plan2Cost started during the hackathon. The author is a quantity surveyor and drew on professional experience, textbooks and public sites for the measurement conventions, rates and
coefficients; the sources are named in `data/` and `CLAUDE.md`. The author's own bills and drawings used for checking are not in this repo.

## Built during the hackathon (Oct 27 – Nov 4, 2026)

Everything in this repository. See the git history for dated commits.

## Layout

Model reads, code measures: a model never overrides a measurement, and every line says whether it was measured from the plans or estimated from coefficients.

```
plan2cost/
  kit/        primitives with no domain logic: model client (Meta Model API / Muse Spark Open), PDF reading, the saved run (progress.py)
  drawing/    reading geometry: vector and raster line work, wall bands, scale, the verified drawing model, quality checks, annotated markup, openings tied to walls
  facts/      what the model reads that is printed or visible: room names, page facts for scale, review of the markup, quote lines, SAM 3.1 for site photos
  takeoff/    quantities and rules: walls, foundation, finishes, the estimator (rough.py), coefficients, BoQ and pricing, bills, quote and tender audit
  tools/      what the agent can call, one file per group (drawings, estimate, records, audit, submit)
  agent/      loop.py, system_instructions.md (the prompt), verify.py (the submit gate), view.py, CLI (python -m plan2cost.agent)
data/         editable rates, defaults, BESMM code map, coefficients (sourced ranges), coverage map
eval/         ground-truth cases, the scripts that score the wall and opening readings, and the one that derives coefficients from the author's own BOQs sheets
ui/           console: new estimate form, live progress, annotated plans, BoQ with ranges, bills, quote and bid audit
tests/        unit tests
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

Work in progress: floor plans to a budget estimate with ranges (measured from the plans where they show it, coefficients where they do not), bills in Excel and PDF, contractor quote and tender audit. The stage-photo check is next.
