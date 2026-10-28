# Run 005: plan6 openings from plan symbols (no schedule), muse-spark-1.3

The schedule pages were withheld. The ground and first floor plans were each cut into 4 tiles at 220 dpi and read tile by tile.
Widths are printed numbers; heights are not available without an elevation dimension, so they would fall back to defaults and be flagged.

| measure | result |
|---|---|
| openings in the author's schedule | 80 |
| openings found | 38 |
| matched (kind and width within 60mm) | 36 |
| recall | 45.0% |
| precision | 94.7% |

What it finds is nearly always right (precision), but it misses about half. A single whole-page read found about 20 openings; tiling roughly doubled that.
Next ideas: denser tiles, a second pass over the gaps, SAM 3.1 masks for door and window symbols, and a scale calibration to size openings with no printed width.

## Questions the agent asked instead of guessing

- West external window of G009 STAFF RM - no printed width found
- Opening between G005 KITCHEN and G011 TERRACE on west wall near 4570 dimension - unclear if 4570 is opening width and unclear kind
- 900 dimension in wall below G008 BATHROOM (610-900) - cannot confirm kind and wall classification
- 900 vertical dimension on east wall of G005 KITCHEN - cannot confirm if opening width and kind
- Openings east of grid 3 in G007/G004 area cut by right tile edge - excluded as belonging to neighbouring tile
- G018 GUEST BEDROOM SE door swing - adjacent 750/620/900 dims unclear which is leaf width - confirm size
- G019 BATHROOM S door and G021 BATHROOM entrance - symbols visible but no legible printed width - confirm sizes
- East external wall windows serving G020 STAFF RM., G021 BATHROOM and G016 KITCHEN to TERRACE - symbols visible but no legible printed widths - confirm sizes
- N wall window of G018 GUEST BEDROOM near W tile edge cut by grid 4 dashed line - confirm if centre is in this tile and size
- W wall of G016 KITCHEN 600/900 dims - unclear if openings or wall segments - confirm
- G006 PANTRY door with swing arc visible at top of tile - no printed opening width, cannot size
- North steps entrance with red arrow at top centre - opening width not dimensioned, cannot size
