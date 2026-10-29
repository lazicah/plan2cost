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

## Openings tied to walls (plan 6 ground floor, raster route)
Candidates: stretches of a wall where both faces are broken (46) plus printed dimensions equal to a schedule width. The model looks at a crop of each
candidate (door, window, bare opening, not an opening) and reads its tag; tags in the text layer are used first and each tag belongs to one gap only.
Result against the author's window counts (ground floor: 16 at 600 mm and 4 at 900 mm): 12 found at 600 mm (AW1) and 5 at 900 mm (AW2), plus AW3 x4 and
AW4 x2 which the author's per-floor count does not list. Doors are weaker: the plan carries no door tags and several schedule types share one width, so
12 of 16 doors stay unmatched (they keep the schedule's old external/internal rule in the BoQ). Over-counts are flagged (AW3: 4 found, 2 in the whole
building's schedule) and the BoQ never deducts more than the schedule has.

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

## Finishes, rooms and lintels (BESMM4 1.28, 1.29, 1.13)
`read_rooms` (facts/rooms.py) has the model copy each room's name and the two internal dimensions printed beside it; a number not in the page's text layer is dropped and
the room says so, a room without both numbers is kept with its area unknown and asked about. Rooms are rectangles of the two printed numbers. `compute_boq` then adds floor,
ceiling, internal wall finish, internal paint and skirting (takeoff/finishes.py). Rules from the book (p.232, 236): area net (M1); no deduction for a void of 1.00 m2 or less
(M3); work internal unless stated external (M5); wall finish height to finished ceiling (M8). An external opening over 1.00 m2 comes off once, an internal one twice (two rooms).
External render and paint now follow the same 1.00 m2 rule (blockwork still deducts every opening, the author's method). Porches, terraces and balconies are left out until the user
says they count. Lintels (nr, 1.13.2.2.2) are one per opening, length = opening + bearing each end; the bearing, the finish specs and the skirting height are asked, never assumed.
Not built: wall tiling to wet rooms (needs the tile height and doors tied to rooms), roof, columns and beams, stairs, services.
Building length and width (slab, topsoil, fill) come from the outermost joints plus one wall thickness, not the bounding box of the runs: the strict bounding box stays as the
guard that rejects a vector reading with a grid line merged into a wall (plan 2 page 3), and a test holds both.

## Roof (BESMM4 1.17 and 1.16)
`read_roof` measures a vector roof plan (drawing/roof.py): the heaviest stroke weight is the roof skeleton; the outline is filled for the plan area; the scale is fixed
only when the outline matches printed overall dimensions on both axes (plan 2: 12370 x 20185 against the outline, axes agree to 0.01%; the sheet was plotted at about
1:125, not the stated 1:100, so the stated scale is only a bound). Edges with the outdoors on one side are eaves, interior axis lines ridges, interior 45-degree lines hips
or valleys: the roof is cut into planes, each plane slopes down toward the eave it touches, and a diagonal is a hip when both planes beside it slope away, a valley when
both slope toward it. The pitch is the printed rise (apex level less eaves level, read from the text layer by facts/roof_spec.py) over the plan's run from the main ridge
to its eave; all planes share it, so a hip not at 45 degrees is flagged. Lines (takeoff/roof.py): covering on the slope in m2 with the pitch stated, eaves, ridges, hips and
valleys in m (true lengths), rafters and purlins as slope area over the printed spacing, wall plates as the top floor's external girth. Not measured and asked: purlin
spacing when not printed, the number of trusses and tie beams, a fascia board or gutter. Weak spot: a raised or sunk area that touches no eave of its own (plan 2's central
diamond) makes the hip/valley split uncertain there; it is warned, and the annotated roof plan is saved for a person to check. Total roof area does not depend on that split.
Raster roof plans are not measured: the agent asks for the pitch and says the roof is not measured.

## Coefficients for a rough estimate (data/coefficients.json, takeoff/coefficients.py)
Author's direction (Oct 29): not detailed roof members or bar-by-bar reinforcement for now. When a client has only a floor plan, estimate material and cost from rules of
thumb: per m2 of roof, per m3 of beam, per storey. 72 entries, each a low, typical and high range with sources and a confidence; groups: concrete mixes, blockwork, reinforcement,
frame and slabs, stairs, roof, finishes, services, cost shares, price benchmarks. Prices and cost shares are sanity checks on a total, never rates (rates stay the user's). Sources
are web guides (7 fetched and read, the rest from search summaries, marked) plus the author's pasted notes. NOT yet checked against the author's own bills: the "Bill" sheets in
the plan workbooks are stale from other jobs (plan 2's bill lists 19 windows of 1800x2100 that plan 2 does not have, and a 40 m3 ground slab against its own sheet's 200.55 m2),
so no ratio is derived from them until the author says which bill belongs to which plan and its floor area. `coefficients.problems()` must stay empty (tested).
Known conflicts in the sources: cement per m3 of 1:2:4 runs 6.3 to 8; steel in columns 100 to 450 kg/m3; staircase steel 51 to 160 kg/m3; roof framing 3.5 m per m2 of roof is one
calculator's default with no second source (an actual roof set will differ a lot); no source found for mortar to 150mm blocks.
