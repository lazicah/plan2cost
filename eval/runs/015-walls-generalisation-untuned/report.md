# Run 015: does the wall measurement generalise? (classical image processing, no tuning on the new drawings)

`measure_walls` was tuned on plan2. Run unchanged on other drawing sets (ground floor page found by the model's page classifier):

| drawing | measured total wall girth | author's sheet (ground, ext + int) | difference |
|---|---|---|---|
| plan2 ground (tuned on this) | 108.9 m | 107.1 m | +2% |
| plan2 first (tuned on this) | 101.4 m | 127.6 m | -21% |
| plan6 ground | 70.4 m | 185.9 m | -62% |
| plan8 ground | 29.7 m | 105.3 m | -72% |
| plan4 ground | 23.4 m | 115.5 m | -80% |

plan7: the model found no floor plan page (text-less pages, only cover and other). plan9: no grid or scale could be read from the page's text layer.

Finding: it does not generalise. Different CAD styles draw walls differently (paired lines, one heavy face, solid fill, hatch, different line weights), and fixed thresholds only work for the style they were tuned on.
Direction: a permissive geometric candidate generator plus a Muse model judging each candidate on a crop (the pattern that took window finding from 50% to 86%), consistency checks between measures, and an honest low-confidence fallback.
