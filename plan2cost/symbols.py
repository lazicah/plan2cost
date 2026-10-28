"""Conventional plan symbols, written out for the model. Source: standard architectural drafting conventions (door, window,
wall-hatching, dimensioning and line-type conventions from an architectural symbols reference the author supplied). One legend,
used by every prompt that reads openings, so a correction lands everywhere."""

DOORS = """Door symbols on a plan (a door is a gap in the wall plus its leaf):
- Standard hinged: a thin leaf standing out from one jamb with a quarter-circle swing arc to the other jamb (the arc is often dashed).
- Double-action (swings both ways): leaf with a dashed arc on both sides of the wall.
- French or double doors: two leaves, each with its own arc, meeting in the middle.
- Sliding: offset parallel leaves overlapping in the wall thickness, no arc.
- Pocket: a dashed outline inside the wall where the leaf slides away.
- Bi-fold: a V or zigzag of two short leaves; accordion: a zigzag line.
- Dutch door: drawn like a standard door."""

WINDOWS = """Window symbols on a plan (a window is a gap in the wall crossed by thin lines, never an arc):
- The hatched wall stops at both jambs. In the gap sits a thin rectangle holding two or three parallel lines along the wall
  (frame, glass, sill); a dashed line may run alongside for the head or an overhang.
- Casement, awning, hopper, picture, fixed and double-hung windows all look like this in plan; casement and awning leaves may add
  a thin diagonal or a short swing line. Sliding windows show two offset parallel lines. Bay and bow windows project out of the wall.
- Small and high-level windows (bathrooms, stores) look the same but are narrow."""

WALLS_AND_HATCH = """Walls and hatching: cut walls are drawn as two thick parallel lines with a hatch between them (diagonal lines for brick or
blockwork, dots for concrete, cross-hatch for aluminium, plain or thin lines for partitions). A length of solid hatched wall is wall,
not an opening. Concrete columns are small filled or dotted squares."""

DIMENSIONS = """Dimensioning: a dimension line is a continuous thin line with a terminator (slash, arrow or dot) at each end and the figure
beside it; successive chains are stacked outward from the building, nearest chain first. Grid lines are dash-dot lines ending in a
numbered or lettered bubble. A figure in a bubble or box beside an opening (D1, W3, AW2) is its type tag. The title block gives the
scale (e.g. 1:100) and the sheet number."""

LEGEND = "\n\n".join([DOORS, WINDOWS, WALLS_AND_HATCH, DIMENSIONS])
