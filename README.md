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

```
plan2cost/        agent loop, model client, tools
  tools/          takeoff, pricing, quote audit, stage assessment
data/rates.json   editable placeholder rates (user-supplied, not scraped)
eval/             scoring harness + ground-truth cases
tests/            unit tests for the deterministic maths
docs/             notes
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your key
python -m eval.run --cases eval/cases
```

Models are called through an OpenAI-compatible endpoint (Meta Model API, or Muse Spark Open on Baseten/Fireworks/Modal). Configure it in `.env`.

## Status

Scaffold only. Work in progress.
