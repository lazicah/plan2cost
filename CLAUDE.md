# Wall girth from drawings: results against the author's surveyed totals

Truth: the author's own `Block work Girth` sheets (numbers only, `eval/cases/planN/girth_truth.json`). Model-read page facts (stated scale, overall
dimensions) are cached in `eval/cases/planN/page_facts*.json`. Reproduce: `python eval/run_vector_walls.py`, `python eval/run_raster_walls.py [first]`.

One interpretation layer reads line work from a vector PDF page (exact) or a raster image (morphology), and the same wall machinery runs on both.
Nothing in it is tuned to one drawing. Total wall girth (external + internal), measured against surveyed:

| Source | Plan, floor | Measured | Surveyed | Error |
|---|---|---|---|---|
| vector PDF | plan 4 ground | 116.3 | 115.5 | +1% |
| vector PDF | plan 4 first | 123.9 | 118.9 | +4% |
| vector PDF | plan 4 pent | 78.0 | 86.1 | -9% |
| vector PDF | plan 6 ground | 209.6 | 185.9 | +13% |
| vector PDF | plan 6 first | 180.0 | 174.5 | +3% |
| vector PDF | plan 7 ground | 126.2 | 127.3 | -1% |
| raster image | plan 1 ground | 202.3 | 225.0 | -10% |
| raster image | plan 2 ground | 116.1 | 107.1 | +8% |
| raster image | plan 3 ground | 187.5 | 201.9 | -7% |
| raster image | plan 4 ground | 111.0 | 115.5 | -4% |
| raster image | plan 6 ground | 176.0 | 185.9 | -5% |
| raster image | plan 1 first | 248.0 | 240.5 | +3% |
| raster image | plan 2 first | 129.7 | 127.6 | +2% |
| raster image | plan 6 first | 228.6 | 174.5 | +31% |

Plan 5's workbook repeats plan 6's numbers, so it is not scored; its vector PDF (92.6) and raster image (85.6) agree with each other within 8%.

## Known weaknesses
- External girth (walls with outdoors on one side) differs from the author's outline-only convention by 5 to 45%; no closing radius fixes it across
  plans (best mean error 16.5%), so it is reported at lower confidence and the porch/terrace question is for the user.
- Thin partitions and walls split by openings are the main source of the remaining total error; plan 6 first floor (raster) is +31%.
- Walls are axis-aligned only (no angled walls).

## How a reading is trusted
Scale: printed dimensions against the lines they measure (stated scale is only a loose bound), else the wall thickness as a ruler with the block
size chosen by the model-read overall dimensions. A raster reading counts only if the walls at its final scale form a building and their extents match
the printed overall dimensions on both axes. A vector result is rejected (and the page read as raster) if its extents do not match the printed overall
dimensions. The model reads printed facts and nothing else; code measures every length.

## Drawing model and checks
Each measured floor is saved as a drawing model (`drawing_model_<floor>_p<page>.json`) with an annotated plan (`markup_<floor>_p<page>.jpg`). Checks that
code runs on it: overlapping runs (possible double count), runs past the last joint (grid or dimension lines merged into a wall), wall ends that meet
nothing, building size against the printed overall dimensions, weak scale evidence, and external-versus-outline convention. A model reviews the annotated
plan as well and can only add questions. Examples: plan 1 (image) is flagged for a missing north wall by both the extents check (11.0 m deep against
13.5 m printed) and the model review; plan 2's architectural page is flagged for two grid lines merged into walls.

## The product flow (floor plans only)
Input: one floor plan per floor (PDF or image), the storey height (floor to floor, not ceiling height) and the roof type (gable, hip or flat, the types we hold coefficients for),
optionally a pitch and an overhang. Nothing else is asked. `read_floor` measures a floor by code (walls, outer building size from the outermost joints plus a wall thickness,
doors and windows tied to their walls, room names for wet rooms); the model reads only printed facts (scale, overall dimensions, room names) and looks at crops to say what a gap in
a wall is. `compute_boq` (takeoff/rough.py) measures what plans show (blockwork, external and internal finishes by BESMM4 1.28 M3, lintels, strip foundation from the ground walls,
sanitary fittings from wet rooms, doors and windows) and estimates the rest from data/coefficients.json as low, typical and high (frame, suspended slab, stairs, steel, roof). Every
BoQ line is marked measured or estimated, with the coefficient ids behind an estimate. Column bases cannot be seen on a plan and are not included (an assumption says so). Floor area is
the building envelope less the walls; a flood-filled outline leaks where walls are missing, so it is not used. The roof-plan, section, structural and schedule readers were removed;
they are in git history (commit 647ba51 and earlier). A budget estimate is not a bill for tender, so the unpriced bill is made only when every line is measured.
Openings: candidates are gaps where both wall faces are broken; the model checks each crop (door, window, opening, not an opening) and reads its tag; width is measured, height is a
flagged standard (coefficients door_height_m, window_height_m). Plan 6 ground floor against the author's window counts: 12 of 16 found at 600 mm, doors weaker.

## Code layout
See README.md. Dependencies run one way: `kit` <- `takeoff`, `drawing` <- `facts` <- `tools` <- `agent`. A new tool is one function in a `tools/<group>.py` file plus an entry in that file's `TOOLS`; the prompt lives in `agent/system_instructions.md`.

## Quote audit
`audit_quote` (tools/audit.py, rules in takeoff/audit.py, quote reading in facts/quote.py) checks a contractor's quote against the filed BoQ. The model reads the
quote's lines (each number must be printed on the page when it has a text layer) and suggests which BoQ key each line matches (only real keys are kept); code does
every comparison: line and total arithmetic (total to the unit), quantity (over 10%), rate against the user's rate (over 15%), unit mismatch, double charging, work the quote
leaves out (largest priced items listed, the rest rolled up) and quote lines matching nothing. Each flag says what to ask; none accuses. Test on a synthetic scanned quote
built from the filed BoQ with four planted errors: all four caught. Not yet tried on a real quote. When a quote is given, submit is refused until it is audited.

## Bills: priced and unpriced; tender audit
Overhead, profit and preliminaries live inside the rates (author's practice), so the bill has no section for them. `submit_boq` writes `bill_priced.xlsx` (for a client) and
`bill_unpriced.xlsx` (for tender: rates blank, amount a formula, items numbered) plus `bill.json` with the issued item numbers. Contractors' returned bills are audited with
`python -m plan2cost.agent.bids --run <id> bid1.xlsx bid2.pdf`: Excel returns are read directly, PDF/image returns by the model; lines match by item number, so nothing is guessed.
Flags: unpriced or missing items, changed quantity or unit, wrong arithmetic or total, rate against the user's rate (15%), rate far from the other bids (25%, three or more bids),
added items. Totals are the bid's rates at our issued quantities; a bid with unpriced items is not comparable on total. Thresholds are defaults for a surveyor to set.
Checked on three synthetic returns made from the plan 2 BoQ; not yet on real bids.

## Coefficients for a rough estimate (data/coefficients.json, takeoff/coefficients.py)
Author's direction (Oct 29): not detailed roof members or bar-by-bar reinforcement for now. When a client has only a floor plan, estimate material and cost from rules of
thumb: per m2 of roof, per m3 of beam, per storey. 72 entries, each a low, typical and high range with sources and a confidence; groups: concrete mixes, blockwork, reinforcement,
frame and slabs, stairs, roof, finishes, services, cost shares, price benchmarks. Prices and cost shares are sanity checks on a total, never rates (rates stay the user's). Sources
are web guides (7 fetched and read, the rest from search summaries, marked) plus the author's pasted notes. NOT yet checked against the author's own bills: the "Bill" sheets in
the plan workbooks are stale from other jobs (plan 2's bill lists 19 windows of 1800x2100 that plan 2 does not have, and a 40 m3 ground slab against its own sheet's 200.55 m2),
so no ratio is derived from them until the author says which bill belongs to which plan and its floor area. `coefficients.problems()` must stay empty (tested).
Known conflicts in the sources: cement per m3 of 1:2:4 runs 6.3 to 8; steel in columns 100 to 450 kg/m3; staircase steel 51 to 160 kg/m3; roof framing 3.5 m per m2 of roof is one
calculator's default with no second source (an actual roof set will differ a lot); no source found for mortar to 150mm blocks.

### Scope for the hackathon (Oct 29)
Input: floor plans only (one per floor), the storey height (floor to floor, not ceiling height) and a roof type limited to those with coefficients: gable, hip, flat.
Measured from the plans: footprint, gross floor area, wall girth and areas, rooms, openings, wet rooms. Estimated from data/coefficients.json as low, typical and high: foundation, frame,
slabs, stairs, roof, services. The roof-plan, section and structural readers stay in the code, off the default path. The "My Duplex" PDF in reference/boq (gross floor area 306.2 m2) is a
bill generated by nigeriabuildingcost.ng from entered dimensions, not a surveyed bill: it shows what that estimator assumes and is not ground truth. Its internal plaster (225 m2 for
306 m2 of floor) looks low against a perimeter-times-height measurement, so do not adopt its wall ratios; walls are measured from the plan, not estimated by ratio.

## Rates, bill order, and the bill of materials and labour (Oct 29)
Rates (data/rates.json) come from two bills the author supplied, never scraped: the Owerri duplex bill (27 Oct 2026) and the Cubana bill, Asaba (April 2026). No rates per city (no data to separate
them): where both bills price the same product the higher is used (over-estimating is safer). Where they price different specifications (floor tiles, WC, basin, sink, shower, internal doors, luminaires, roof
covering) the cheaper is the Standard rate and the dearer the Premium rate, chosen by the finish level the user picks (default standard); `load_rates(tier)` and `tier_notes` say what differs. Taking the higher
rate everywhere had raised plan 2 by 23%, most of it from these specification lines, which is why the tiers exist. Asaba floor finish and skirting are a tile line plus a bed or backing line added together. The bill is arranged like the My Duplex bill (data/bill_structure.json, takeoff/sections.py): SUBSTRUCTURE (bill 2), SUPERSTRUCTURE (frame, upper floors,
roof, stairs, external walls, internal walls, windows, doors: bills 3 to 10), INTERNAL FINISHES (wall, floor, ceiling: 11 to 13), SERVICES (sanitary and water 14, electrical 15), EXTERNAL WORKS (16),
with a subtotal per bill and a summary in Excel, PDF and the console. Electrical lines are all estimated from floor area (two bills, so a spread; fans, TV and external lights come from one bill and have none).
The bill of materials and labour (takeoff/materials.py, ml_bill.py) turns each BoQ line into cement bags, sand and granite tonnes, 12 m bar lengths, planks, blocks, tiles, felt and the labour,
like the author's SIMPLIFIED BOQ. Recipes are data/materials_labour.json from `python -m eval.derive_materials`, which pairs SIMPLIFIED BOQ.pdf (materials) with the Cubana bill (measured
quantities) for the same Asaba duplex: cement 6.55 bags per m3 (5.9 to 7.2 across elements; foundation, bases and ground slab all 6.2), sand 1.76 t and granite 1.61 t per m3, 12 m bars 13.5 kg each,
0.88 planks and 1/75 bag of nails per m2 of formwork, 9.5 blocks and 0.15 bag of cement per m2 of wall, labour from the simplified bill (casting 2,500 a bag, bending 100 a kg, block laying 45, 200 in the
foundation, plastering 3,500 a m2). One building, so these are that contractor's practice, not a range. The sand quantity is about 2.4 times what a 1:2:4 mix needs: it is how that bill is priced, worth confirming.
Lines with no recipe (windows, doors, fittings, excavation, electrical) are carried at their BoQ rate.
