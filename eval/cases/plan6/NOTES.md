# plan6 truth: source and caveats

Source: author's surveyed `Block work Girth` sheet (General works.xlsx, plan6), read with openpyxl, values only.
Drawings: `reference/plan6/ground-floor.jpg`, `first-floor.jpg` (third-party architect drawings, kept out of git; the harness needs them copied in locally as `plan.jpg`).

| key | cell |
|---|---|
| ground_ext_girth_230_m | N15 (= N64) |
| ground_int_girth_230_m | V64 (sum of N17:N25) |
| ground_int_girth_150_m | W64 / O26 |
| ground_total_girth_230_m | N58 / N75 |
| first_ext_girth_230_m | V15 (= N65) |
| first_int_girth_230_m | V65 |
| first_int_girth_150_m | W65 |
| first_total_girth_230_m | V58 / N76 |

Keys use the thickness shown on the drawing (230); the author's sheet labels that column 225 (block size). Values are unchanged.
Zero-valued quantities (100mm blocks, foundation, 2nd/3rd floor) are omitted because the scorer divides by truth.
Ground and first-floor runs are "above DPC" wall lengths, each multiplied by a repeat count.

Open question for the author: confirm sheet lengths are centre-line (BESMM4 masonry M1). Thicknesses are used as drawn, never adjusted.

## Corrected blockwork areas (author-confirmed)

The author's sheet gives 507 (external) and 513 (internal) m2. Two inputs in the sheet were errors: storey height 3.3 m (the drawings give 3.0 m) and TD1 deducted at 0.95 m (the schedule gives 0.75 m). With the drawing values, external is 452 and internal is 466 (`ext_blockwork_230_m2`, `int_blockwork_230_m2`). External and internal openings are deducted from their own wall. ASD1 (3000 wide aluminium sliding door) is treated as internal, as in the sheet; open question whether it is an external opening.

Update: SD1 is 900 x 2150 (confirmed), so external deductions are 0.18 m2 larger; external blockwork is 451.62, still 452 after rounding up. Internal is unchanged at 466.
