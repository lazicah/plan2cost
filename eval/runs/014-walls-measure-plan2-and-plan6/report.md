# Run 014: measure_walls on plan2 and plan6 (classical image processing, scale from the PDF)

Not a model run. One function: grid and scale from the text layer, walls from the page image, external/internal split by flood fill, junction ends counted.
A bug found on the way: wall pieces were merged by rounded centre-line position, so a 0.01% scale change moved the plan2 total from 98.4 m to 92.7 m. Now clustered by distance;
the total moves only 101.3 to 103.6 m across a 43.5 to 44.5 mm/pt scale range.

## Plan 2, ground floor (tuned on this drawing)
| quantity | measured | author's sheet | difference |
|---|---|---|---|
| blockwork girth (full runs) | 103.64 m | 104.835 m | -1.1% |
| trench girth (walls less pad widths 27.4 m less 26 junction ends x 0.23) | 70.26 m | 69.69 m | +0.8% |
| external walls | 52.9 m | 53.476 m | -1.1% |
| internal walls | 50.75 m | 53.651 m | -5.4% |

## Plan 6 (not tuned: does it transfer?)
| floor | measured total | author's sheet total (ext + int) | difference |
|---|---|---|---|
| ground | 70.41 m | 185.9 m | -62.1% |
| first | 63.26 m | 174.5 m | -63.7% |

It does not transfer to plan 6: the scale and grid are found, but its wall style differs (and the external/internal split fails), so only about a third of the wall length is found.
Next: let the model judge candidate wall segments (permissive geometric candidates, the model says wall or not on a crop), the pattern that took window finding from 50% to 86%.
