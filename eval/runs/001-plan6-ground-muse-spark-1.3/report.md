# Run 001: plan6 ground floor, muse-spark-1.3

2026-10-27 13:38

## Girth vs the author's surveyed truth

| quantity | model (m) | error |
|---|---|---|
| ground_ext_girth_230_m | 72.24 | 26.7% |
| ground_int_girth_230_m | 80.8 | 4.2% |
| ground_int_girth_150_m | 3.9 | 33.6% |
| ground_total_girth_230_m | 153.04 | 16.3% |

## Notes

First end-to-end run, no prompt tuning. Dimension kinds were tagged sensibly and the agent asked useful questions (e.g. whether 400/450 upstands are masonry).
Failures: (1) external walls taken as the 19430 x 17150 bounding box, but the plan has porches, terraces and projections, so external girth is under-counted (72.24 vs 98.62 m);
(2) one digit misread: vertical overall printed 17130, model read 17150; (3) internal runs are one clear width per room type, not a walk along every wall, so the 4.2% internal-230 error is likely luck;
(4) grid bays came back with no thickness and were dropped into questions.
Next: prompt the model to walk the layout grid line by grid line and list every wall segment, following the author's method.

## Wall runs extracted

| label | length mm | kind | thickness mm | count |
|---|---|---|---|---|
| External E-W walls North and South - overall | 19430 | end_to_end | 230 | 2 |
| External N-S side walls East and West - overall | 17150 | end_to_end | 230 | 2 |
| Unit E-W width outer centre to party centre | 9600 | centre_line | 230 | 2 |
| Grid bay 1-2 and 6-7 | 1800 | centre_line | None | 2 |
| Grid bay 5-6 | 3600 | centre_line | None | 1 |
| Staff Rm clear width | 2770 | in_to_in | 230 | 2 |
| Guest Bedroom clear width | 3370 | in_to_in | 230 | 2 |
| Bathroom clear width | 1570 | in_to_in | 230 | 2 |
| Kitchen clear width | 3970 | in_to_in | 230 | 2 |
| Dining clear width | 3970 | in_to_in | 230 | 2 |
| Living Room clear length left | 5250 | in_to_in | 230 | 1 |
| Living Room clear length right | 5285 | in_to_in | 230 | 1 |
| Entrance Porch clear width | 4350 | in_to_in | 230 | 2 |
| V.T. clear width | 1720 | in_to_in | 150 | 2 |
| Pantry clear length | 3685 | in_to_in | 230 | 2 |

## Questions the agent asked instead of guessing

- Confirm external wall thickness - 230 labels seen on outer and party walls; are all external walls 230mm?
- Confirm internal partition thickness - 150 seen near V.T. vs 230 elsewhere; which internal walls are 150mm vs 230mm?
- Confirm N-S overall 17150 vs 10230+6900 breakdown - which vertical chain represents masonry girth?
- Confirm grid 2-3-4 dimensions (3400? 4200?) - top chain partially legible; provide clear grid-to-grid centre-line values for grids 2-3 and 3-4?
- Are pantry/terrace dwarf walls and entrance porch 400/450 upstands masonry? Thicknesses 400/450 seen at south end - include or exclude from girth?
- Grid bay 1-2 and 6-7: wall thickness or length is not readable on the drawing.
- Grid bay 5-6: wall thickness or length is not readable on the drawing.
