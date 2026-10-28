# Run 014: measure_walls on plan2 and plan6 (classical image processing, scale from the PDF)

Not a model run. One function: grid and scale from the text layer, walls from the page image, external/internal split by flood fill, junction ends counted.

## Plan 2, ground floor (tuned on this drawing)
| quantity | measured | author's sheet | difference |
|---|---|---|---|
| blockwork girth (full runs) | 94.57 m | 104.835 m | 9.8% |
| trench girth (walls less pad widths 27.4 m less 24 junction ends x 0.23) | 61.65 m | 69.69 m | 11.5% |
| external walls | 52.85 m | 53.476 m | 1.2% |
| internal walls | 41.72 m | 53.651 m | 22.2% |

## Plan 6 (not tuned: does it transfer?)
| floor | measured total | author's sheet total (ext + int) | difference |
|---|---|---|---|
| ground | 65.93 m | 185.9 m | 64.5% |
| first | 62.64 m | 174.5 m | 64.1% |

It does not transfer. On plan 6 the scale and grid are found, but wall styles differ (and its external/internal split fails), so only about a third of the wall length is found.
Next: let the model judge candidate wall segments (permissive geometric candidates, model says wall or not on a crop), the same pattern that took window finding from 50% to 86%.
