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
- `python -m pytest -q`; `python -m eval.run --cases eval/cases`
- Model client is OpenAI-compatible; configure via `.env` (see `.env.example`).
- The cloud sandbox cannot reach the model APIs, so model-calling code is run locally.

## Status
Scaffold done (PR #1). Next: model client smoke test on a real plan, extraction prompt + JSON schema, agent loop, quote audit, stage-photo spike, eval cases, demo.
