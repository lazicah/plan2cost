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
