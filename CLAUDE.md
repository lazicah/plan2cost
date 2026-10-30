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
nothing, building size against the printed overall dimensions, weak scale evidence, and external-versus-outline convention. Before that review, a model-checked pass (facts/verify_walls.py) runs: a run past the last joint is trimmed to the joint when the model sees no wall under it (closed question on a crop);
a pair of runs whose centre lines are closer than a wall thickness is the same wall found twice, and the shorter is dropped (geometry, no model call: the model's answer was not stable); a wall the model sees with no line is added only if code finds a bar
(solid, or two face lines a wall apart, hatched or not) across the building whose both ends meet walls. Each edit is logged as an issue. On plan 2 (images, full pipeline): ground floor 111.7 m against 107.1 surveyed (+4%; before the pass 116.1),
first floor 121.4 m against 127.6 (-5%; before 129.7, +2%, which had overshoots and duplicates cancelling missed walls). The author confirmed the hatched ground-floor partition is a wall (lighter faces than the others); it is found and added (11.0 m).
Still missed on plan 2: walls the model points to where a bar is found but its ends do not both meet walls (left as warnings). The eval table above is from the eval scripts and does not include this pass. The model
review of the annotated plan after that can only add questions. Examples: plan 1 (image) is flagged for a missing north wall by both the extents check (11.0 m deep against
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
flagged standard (coefficients door_height_m, window_height_m). Plan 6 ground floor against the author's window counts: 12 of 16 found at 600 mm, doors weaker. Two more candidate sources (Oct 30): windows drawn inside a thick wall (a sill line between the face lines, found between two heavy jamb lines),
and doors that are a gap between a wall end and the next wall. Plan 10 (one-storey bungalow, a PDF whose page is an image): windows 6 x 1200, 4 x 600, 1 x 750 all found, doors 4 of 4 found (1 x 1200 double, 3 read as 900: the clear gap measures about 870 for both the
750 and the 900 doors, and only the door leaf would tell them apart). Plan 2 (two images, no text layer): windows found rose from 3 on both floors to about 27 (the author's bill has 36) and doors to about 18 (bill 21), with no change in wall lengths; some 1800 and 2400 windows are probably wall between two frames, so wide windows raise a warning. Plan 6 ground with its schedule: windows 23 to 25, 600 mm ones 12 to 13 of 16, 900 mm ones 5 to 6 of 4 (one more over-counted).

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
quantities) for the same Asaba duplex: concrete is the 1:2:4 mix of the nigeriabuildingcost calculator (7 bags of cement, 0.74 t of sand, 1.39 t of granite per m3, 5% waste; the bill itself gives 6.2 to 7.2 bags, 1.76 t of sand and 1.61 t of granite, kept as evidence), 12 m bars 13.5 kg each,
0.88 planks and 1/75 bag of nails per m2 of formwork, 9.5 blocks and 0.15 bag of cement per m2 of wall, labour from the simplified bill (casting 2,500 a bag, bending 100 a kg, block laying 45, 200 in the
foundation, plastering 3,500 a m2). One building, so apart from concrete these are that contractor's practice, not a range.
Lines with no recipe (windows, doors, fittings, excavation, electrical) are carried at their BoQ rate.
Reinforcement (Oct 29): the rebar calculator's worked examples (column 123, beam 113, slab 48 kg per m3) agree within 10% with the element ratios derived from the Cubana bill (130, 115, 53), so those are stored as coefficients (net, before 5 to 10% waste). The estimator still uses the plan-derived steel ratio (median 160, range 88 to 228 kg per m3) for the whole frame because it is the more cautious and covers stair and beam variety. Rebar price in the materials bill is about 1,650 a kg (13.55 kg a 12 m bar = 22,363), the calculator's, since the simplified bill's figure is half that and the measured BoQ steel rates agree with the calculator. Bar weights Y8 to Y25 are in data/materials_labour.json.
Blockwork (Oct 29): per m2 of 225 mm wall, 10.5 blocks (10 plus 5% waste), 1:4 mortar for external and foundation walls (0.245 bag, 0.12 t sand) and 1:6 for internal (0.222 bag, 0.074 t), from the nigeriabuildingcost block wall calculator; laying 200 a block everywhere (the bill pays 45 above ground; the author chose 200). The bill's own 9.5 blocks, 0.153 bag, 0.036 t are kept under evidence. Plan 2 materials-and-labour total: about 91.0M (range 76.8M to 120.4M).
One-storey buildings and lintels (Oct 30, the author's rules): a one-storey building has strip foundation only (corner columns with pads only for very long spans, not estimated until the author gives the span) and no ring beam, beams or columns. Lintels are never counted in pieces: they are
reinforced concrete (m3), formwork (m2) and reinforcement (kg), as a chain lintel along the external walls (the author's practice: his plan 10 bill has 2 m3 of external lintel against 1.9 m3 from 36.2 m of external wall at 230 x 225) plus a lintel over each internal opening with 225 mm bearing each
end. Section is wall thickness x one block course (225 mm); steel is estimated at 120 to 195 kg per m3 from that bill. Plan 10 lintels now: 3 m3 (bill 2.55), 27 m2 (bill 30), 317 kg (bill 347); priced at the frame's concrete, formwork and steel rates.

Voice input (Oct 30): the new-estimate form has a microphone button. The browser records 16 kHz mono WAV, the server (`/api/voice`) sends it to Muse Voice Transcribe (`kit/voice.py`, POST /asr/transcribe, push-to-talk, WAV only, 10 minutes at most), and the model reads the transcript for storey height, roof type, pitch, overhang and finish level (`facts/spoken_inputs.py`); code keeps only values in the form's ranges and nothing is guessed. Tested on a synthesised recording: all four stated values read correctly.

Realistic pictures (Oct 30): the 3D view has a button that sends a screenshot to Muse Image (`kit/imagegen.py`, `agent/render.py`, POST /v1/images/edits, about 25 to 30 s, flat $0.01 an image). The prompt is built from the measured data (roof type, storeys, window and door counts) and forbids added features. A first try with a generic prompt changed the hip roof to a gable and dropped windows; a prompt that states the roof type and says the screenshot is the geometry kept the roof, storeys and window frames. It stays an illustration: never a source of quantities, saved under the run's renders folder.
Added walls must be drawn as heavily as the walls already measured (face lines at least 0.6 of their median weight): plan 10's porch edge, two light lines 225 mm apart, was added as a 5.6 m wall and covered the entrance porch in the 3D view.

Plan 2 openings with tags, lighter-face windows and space names (Oct 30, run 20261030-074723, 275 s): windows 17 on the ground floor and 19 on the first (36 in all; the author's bill has 36), doors 13 and 15 (28; bill 21, so some doors are false), three windows wider than 1.9 m flagged. About 33 opening tags are read per floor (more than the plan has: a tag seen twice far apart is not merged), 19 to 24 of them matched to an opening; the rest are reported as tags with no opening near them (probably in walls that were not measured). Wall lengths unchanged (62.9 + 48.8 and 52.7 + 68.6); estimate 83.7M (range 71.8M to 107.7M), lower than before because the first-floor "Void Over Main Lounge" now has no slab or floor finish. Space names: open-air spaces (porch, terrace, balcony...) cannot be crossed by an external wall, voids have no slab, lobbies are enclosed circulation; floor slabs in the 3D view follow the outline the walls enclose. Model calls time out after two minutes and retry: a dead connection had hung one floor for over ten minutes.
Glazing to a void (Oct 30): untagged windows within 1.5 m of a space named Void are kept (the author: windows that run from one floor to the next carry no tag and there is no elevation to show them), and the 3D view draws them from the floor below to the floor above (an assumption, flagged in its notes). Plan 2 (run 20261030-100058): the 1200 window at the top-left of the first-floor void is found (end-gap detector, 1146 mm clear); windows 18 + 22 = 40 (bill 36), doors 13 + 10 = 23 (bill 21); estimate 84.2M.
Doors and tag counts (Oct 30): a door candidate must have its own leaf or arc (a neighbour's arc does not count), and a door or opening stretch whose wall band is more than 38% dark (wall stubs measured 0.42 to 0.50, real door gaps 0.05 to 0.31) is wall; both false doors the author pointed out (a hatched wall stub beside a D2 arc, and the open gap to the lobby) are now left out or read as an opening. On a plan that tags its openings, the tag count is a ceiling on what is missing: windows or doors are added only where the plan prints more tags than openings were located (at a standard size, flagged). Plan 2 (run 20261030-104037): windows located 22 + 20 = 42 against 37 distinct window tags (bill 36), doors 11 + 11 = 22 against 21 door tags (bill 21), nothing needed adding; estimate 84.1M (range 72.3M to 108.1M). Windows located above the tag count (here 5) are probably false: a cap at the tag count is not applied yet.
Plan 2, tags beside unmeasured walls (Oct 30, run 20261030-105002): D1 and W3 beside the ground-floor porch (a thin double-line wall that no wall detector reads) are now counted from their printed tags; so are other tags with no opening of their kind within 2.5 m. Doors narrower than 650 mm clear are read as windows whatever tag was matched (tag positions from the model are coarse; a small window symbol beside a door's arc was read as a door). Counts in that run before the 650 rule: windows 44 and doors 26 (bill 36 and 21), so the additions overshoot a little; the cost effect is small (a window is about 69,000 naira against a total of 84 million), the markup is what shows the error. Estimate 84.6M.
Tags at their true place and walls where tags stand (Oct 30, run 20261030-110537, plan 2 ground floor alone): the model's first place for a tag is off by a few metres on a large sheet, so each tag gets a second look at a 7 m square around it (a tag not found there is dropped); 33 tags became 22, of which 20 matched an opening. A tag with no opening near it, with no wall near, triggers a search for a pair of lines a wall apart (even light ones) that runs between two walls: this found the thin wall between the porch and the pre-sit (3.8 m, W-026, low confidence), with D1 (a door) and W3 (windows) on it. The floor totals in the run were stale after edits (replaced, not changed in place): fixed, so the wall length now includes walls added at tags and after space names. Reading a floor now takes about 9 minutes when it is the only one in the run (526 s); the second looks are a large part of it.
