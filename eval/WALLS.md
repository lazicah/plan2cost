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
