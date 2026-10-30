# Plan2Cost: demo script, recording checklist and submission checklist

The demo video is a primary judging artifact (3 minutes). Judging, from the participant guide: Stage 1 pass/fail (fits the theme, really uses the Meta Model API or open weights), then
Impact 30, Meta tooling 25, Demo 25, Technical depth 20. Bonuses: Open Weights, Agentic, Viral (a post on X), Community vote.

> The guide's page could not be read by the tool used to write this, so the rules below come from the notes taken from it earlier. **Compare section 1 against the live guide before recording.**

## 1. The rules, and how this project meets each one

| Rule (from the guide notes) | How we meet it | Check before submitting |
|---|---|---|
| Fits the theme "Build for Your World" | A cost estimate from a floor plan for people building a home (especially from abroad) in Nigeria and across Africa | Say the "your world" sentence in the first 15 s |
| Really uses the Meta Model API or open weights | Every model call goes through the Meta Model API (Muse Spark), or Muse Spark Open on Baseten (`P2C_PROFILE=open`); also Muse Voice Transcribe and Muse Image | Show the model names on screen once; do a Spark Open run for the clip |
| Meta tooling beyond a basic integration (25) | Agent loop with tools, vision on crops, model-checked walls, tag reading, voice input, image generation with a count check; model reads and judges, code measures | Show 3 of them working, not a list |
| Demo shows only what was built during the hackathon (Oct 27 to Nov 4) | Nothing existed before; git history is dated from Oct 27 | Do not show older work, other products or earlier screens |
| No code, data or assets we lack the rights to | Own code only; patterns from the Meta workshop credited; rates and coefficients are numbers derived from sources the author supplied, never scraped; third-party books, bills and drawings stay out of the repo | See "Rights" below |
| Public repo | README states what was built, the models used, the limits, and that Claude Code was used (the organisers said no disclosure is required, a note is fine) | Open the repo logged out and read the README as a stranger |
| Anti-projects (basic RAG, simple image analyser, chat wrapper, medical, political) | A measuring and costing pipeline with checks and audits, not an analyser or a chat | Do not describe it as "analyses images" |
| Submit on the Cerebral Valley platform by Nov 4, 9 PM ET | We submit on Nov 3 | Put it in the calendar for the morning of Nov 3 |
| Open Weights bonus: Muse Spark Open or Glimmer through partner inference, verified by the partner | Plan 10 ran end to end on Muse Spark Open on Baseten | Follow the partner's verification step in the guide; claim only what is verified |
| Viral bonus: post the demo on X and submit the link | Draft in section 5 | Submit the post link on the platform |

### Rights (read before recording)
- **Drawing.** The demo uses plan 2 (two floors, 3.0 m, hip roof). Use it only if you own it or have written permission to show it, and make sure no title block or name from a client is visible; if one is, blur it. Plan 10's title block carries a client's name, so keep it out of the video.
- **Rates.** Say they are the user's and editable. Do not show the bill PDFs they came from; show the app.
- **Published numbers.** `data/rates.json`, `data/coefficients.json` and `data/materials_labour.json` hold numbers derived from bills and calculators the author supplied (they name the Owerri and Asaba bills and nigeriabuildingcost.ng as sources), and `eval/cases` holds numbers from the author's own workbooks. The bills, drawings and workbooks themselves are not in the repo. **Confirm you are allowed to publish the derived rates**, or say so in the README if they are the author's own practice.
- **Books and standards** (BESMM4, the nigeriabuildingcost calculators): do not show pages or screens of them. The README names them as sources of the numbers.
- **Voice and music.** Record your own voice. No music unless it is licensed for this use.
- **Secrets.** Never show `.env`, an API key, a terminal that prints one, or the Meta dashboard.

## 2. The 3-minute script (about 430 spoken words)

Record the screen at 1080p, one take per scene, and cut the waiting. Times are targets.

**0:00 to 0:15. The problem** (face or title card, then the app)
> "If you are building a home in Nigeria from abroad, you cannot read the plan, you cannot check the contractor's quote, and you cannot see the site. Plan2Cost goes from plan, to cost, to proof." *(about 40 words)*

**0:15 to 0:35. Voice input** (new-estimate form, press the microphone)
> *(speak)* "A two-storey house, three metres floor to floor, hip roof, standard finish." *(the form fills; point at the transcript)* "Muse Voice Transcribe heard it, Muse Spark read it, and the form is filled. I check it." *(about 35 words)*

**0:35 to 1:05. Reading the plan** (choose the plan, press Estimate, show the progress lines)
> "I give it only the floor plans. The model reads what is printed and judges what it sees. Code measures every length. Watch the progress: scale from the printed dimensions, walls traced, then the model checks them." *(cut the wait; speed up 8x for the long step)* *(about 45 words)*

**1:05 to 1:40. The markup** (annotated plan: red and blue walls, purple doors, teal windows)
> "Red walls are external, blue internal, doors purple, windows teal. Every opening is labelled with its width. When the model sees a wall that was missed, code only adds it if the geometry agrees. When it sees something that is not a wall, like this porch edge, it is taken out. Checks that stay open are listed, not hidden." *(about 60 words)*

**1:40 to 2:10. 3D and the picture** (open the 3D view, turn it, roof off, then "Make a realistic picture")
> "The 3D house is built from the same measured data as the bill, so it cannot disagree with it. A missed wall shows up as a gap. Muse Image turns this view into a picture, and Muse Spark counts the windows to hold it to the model. It is an illustration, labelled as one." *(about 55 words)*

**2:10 to 2:35. The bill** (the bill page: ranges, measured vs estimated, bill order, materials and labour, Excel)
> "The result is a priced bill in the order a surveyor expects. Every line says measured or estimated, with a range for the estimates. Rates are yours to edit. It also makes the bill of materials and labour, and an unpriced bill for contractors to tender on." *(about 50 words)*

**2:35 to 2:50. The audit** (upload a quote; show 2 flags)
> "Paste in a contractor's quote and it checks the arithmetic, quantities, rates and double charging, and asks questions instead of accusing." *(about 25 words)*

**2:50 to 3:00. Close** (title card with the models used and the repo)
> "Built this week with Muse Spark, Muse Spark Open, Muse Voice Transcribe and Muse Image. It is a budget estimate, not a bill for tender, and it says so." *(about 30 words)*

## 3. What to prepare before recording
0. **The demo run (plan 2), checked end to end through the console path** (upload, start, progress, files): run `20261030-120925` took 335 s and made the priced bill and the materials-and-labour bill (Excel and PDF), the 3D view and the estimate of about 84.8M naira (range 73.0M to 108.8M, 41% estimated). Make your own on the day with the same inputs.
   - **The quote for the audit scene:** `python -m eval.make_demo_quote <run id> workspace/demo_quote.pdf` builds a synthetic quote from the run's own bill with six errors planted (a rate 25% over, a quantity 20% over, a line total that does not multiply, one item charged twice, the roof covering left out, and a total 150,000 too high). The audit on that run found all six; show two of them. The quote says on its page that it is synthetic; say so in the video too.
1. `git pull`, run `python -m pytest -q` (all pass), restart the console: `pkill -f ui/server.py; python ui/server.py`. A stale server broke the 3D view once.
2. Start the run for the demo plan **in advance** and keep the finished run: a live read takes about 3.5 minutes (one floor) to 5 minutes (two). Film the start, speed up the wait, and show the finished run. Say "sped up" on screen if you cut time.
3. Make one picture from the 3D view beforehand and keep a second try, since the image model takes 30 to 60 seconds and can differ between tries.
4. Have a quote file ready (a synthetic one is fine, say so) and one audit already run.
5. Close every other window and notification; hide the browser bookmarks; use a clean profile.
6. Test the microphone in the browser once (Chrome asks for permission the first time).
7. Do one dry run against the clock. If it is over 3:00, cut the audit first, then shorten scene 3.

## 4. What not to claim
- Do not say it is validated against a surveyed bill. Say what is true: wall girth was checked against the author's own surveyed totals on several plans, mostly within 10%, with a worst case of +31%.
- Do not say SAM 3.1 or site-photo proof works. It is not built.
- Do not call the picture a render of the real house. It is an artist's impression.
- Do not show wall or opening counts as exact. Some doors and windows are missed or false; say the checks list them.

## 5. X post (draft) for the Viral bonus
> Building a house from abroad and can't read the plan? I built Plan2Cost this week for the Meta x Cerebral Valley hackathon: drop in your floor plans, speak the details, and get a measured and estimated cost, a 3D check of what was measured, and an audit of your contractor's quote. Muse Spark, Muse Spark Open, Muse Voice Transcribe and Muse Image. Demo: [link]. Code: [repo link]

Tag the official accounts the guide names (check the guide for the handles and any required hashtag). Submit the post link on the platform. Keep it to what the video shows.

## 6. Submission checklist (Nov 3)
- [ ] Repo public; README current (what it does, models, limits, AI assistance, nothing before the hackathon)
- [ ] No keys, `.env`, workspace, reference drawings, bills or books in the repo (`git status`, `git ls-files | grep -i env`)
- [ ] Video: 3:00 or less, shows only work from Oct 27 on, no client names, no secrets
- [ ] Open Weights: the Spark Open run recorded and the partner verification done (if claiming it)
- [ ] X post live and its link ready
- [ ] Meta credits claimed if still needed (by Nov 4; a card on file is required)
- [ ] Submitted on the Cerebral Valley platform by Nov 3, with the repo link, the video and a short description
